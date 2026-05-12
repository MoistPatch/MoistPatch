"""Tests for the discovery / crawl extension (Phase 1).

Run with:  python3 -m unittest tests.test_discovery -v
"""

from __future__ import annotations

import asyncio
import gzip
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from agents.price_intelligence.discovery import (
    discover_product_urls,
    match_any,
    parse_sitemap,
)
from agents.price_intelligence.extractor import (
    ExtractionError,
    extract_product_info,
)
from agents.price_intelligence.models import DiscoveredProduct, synthesise_our_sku
from agents.price_intelligence.storage import PriceStore


SITEMAP_URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/product/rtx-5090</loc><lastmod>2026-05-01</lastmod></url>
  <url><loc>https://example.com/product/rx-9070-xt</loc></url>
  <url><loc>https://example.com/blog/best-gpus-2026</loc></url>
  <url><loc>https://example.com/category/graphics-cards</loc></url>
</urlset>"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-products.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-blog.xml</loc></sitemap>
</sitemapindex>"""

SITEMAP_NO_NS = """<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://example.com/product/foo</loc></url>
  <url><loc>https://example.com/product/bar</loc></url>
</urlset>"""

PRODUCT_HTML = """<!DOCTYPE html><html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"NVIDIA GeForce RTX 5090 24GB",
 "sku":"GPU-5090-MSI","mpn":"5090-VENTUS-3X",
 "offers":{"@type":"Offer","price":"3499.00","priceCurrency":"AUD",
           "availability":"https://schema.org/InStock"}}
</script></head><body><h1>RTX 5090</h1></body></html>"""

NON_PRODUCT_HTML = """<!DOCTYPE html><html><head><title>Blog post</title></head>
<body><article>Some article without any Product schema.</article></body></html>"""

WRONG_CURRENCY_HTML = """<!DOCTYPE html><html><head>
<script type="application/ld+json">
{"@type":"Product","name":"Foo",
 "offers":{"@type":"Offer","price":"1000","priceCurrency":"USD"}}
</script></head></html>"""

OUT_OF_RANGE_HTML = """<!DOCTYPE html><html><head>
<script type="application/ld+json">
{"@type":"Product","name":"Foo",
 "offers":{"@type":"Offer","price":"0.50","priceCurrency":"AUD"}}
</script></head></html>"""


class SitemapParseTests(unittest.TestCase):
    def test_parse_urlset(self):
        urls, subs = parse_sitemap(SITEMAP_URLSET.encode("utf-8"))
        self.assertEqual(len(urls), 4)
        self.assertEqual(subs, [])
        self.assertIn("https://example.com/product/rtx-5090", urls)

    def test_parse_sitemapindex(self):
        urls, subs = parse_sitemap(SITEMAP_INDEX.encode("utf-8"))
        self.assertEqual(urls, [])
        self.assertEqual(len(subs), 2)
        self.assertIn("https://example.com/sitemap-products.xml", subs)

    def test_parse_no_namespace(self):
        urls, subs = parse_sitemap(SITEMAP_NO_NS.encode("utf-8"))
        self.assertEqual(len(urls), 2)
        self.assertEqual(subs, [])

    def test_parse_malformed_returns_empty(self):
        urls, subs = parse_sitemap(b"<not><well-formed>")
        self.assertEqual(urls, [])
        self.assertEqual(subs, [])


class PatternMatchTests(unittest.TestCase):
    def test_match_any_accepts_all_when_empty(self):
        self.assertTrue(match_any("https://example.com/anything", []))

    def test_match_glob_pattern(self):
        self.assertTrue(match_any("https://example.com/product/foo", ["*/product/*"]))
        self.assertFalse(match_any("https://example.com/blog/foo", ["*/product/*"]))

    def test_match_multiple_patterns(self):
        patterns = ["*/product/*", "*/pro/*"]
        self.assertTrue(match_any("https://example.com/pro/123", patterns))
        self.assertTrue(match_any("https://example.com/product/abc", patterns))
        self.assertFalse(match_any("https://example.com/foo", patterns))


class DiscoverUrlsTests(unittest.TestCase):
    def test_discover_with_pattern_filter(self):
        # Use a httpx MockTransport so we never hit the network
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow:\n")
            if request.url.path == "/sitemap.xml":
                return httpx.Response(
                    200, content=SITEMAP_URLSET.encode("utf-8"),
                    headers={"content-type": "application/xml"},
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        async def run() -> list[str]:
            try:
                return await discover_product_urls(
                    client, "https://example.com",
                    include_patterns=["*/product/*"],
                )
            finally:
                await client.aclose()

        urls = asyncio.run(run())
        self.assertEqual(len(urls), 2)
        self.assertTrue(all("/product/" in u for u in urls))

    def test_discover_follows_sitemap_index(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/robots.txt":
                return httpx.Response(200, text="")
            if path == "/sitemap.xml":
                return httpx.Response(200, content=SITEMAP_INDEX.encode("utf-8"))
            if path == "/sitemap-products.xml":
                return httpx.Response(200, content=SITEMAP_URLSET.encode("utf-8"))
            if path == "/sitemap-blog.xml":
                # Empty
                empty = (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'
                )
                return httpx.Response(200, content=empty.encode("utf-8"))
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        async def run() -> list[str]:
            try:
                return await discover_product_urls(
                    client, "https://example.com",
                    include_patterns=["*/product/*"],
                )
            finally:
                await client.aclose()

        urls = asyncio.run(run())
        self.assertEqual(len(urls), 2)

    def test_discover_handles_gzip(self):
        gz_body = gzip.compress(SITEMAP_URLSET.encode("utf-8"))

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/robots.txt":
                return httpx.Response(200, text="Sitemap: https://example.com/sitemap.xml.gz\n")
            if path == "/sitemap.xml.gz":
                return httpx.Response(
                    200, content=gz_body,
                    headers={"content-type": "application/x-gzip"},
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        async def run() -> list[str]:
            try:
                return await discover_product_urls(
                    client, "https://example.com",
                    include_patterns=["*/product/*"],
                )
            finally:
                await client.aclose()

        urls = asyncio.run(run())
        self.assertEqual(len(urls), 2)

    def test_respects_max_urls_cap(self):
        # Generate a sitemap with 50 product URLs
        items = "".join(
            f"<url><loc>https://example.com/product/sku{i}</loc></url>"
            for i in range(50)
        )
        big = (
            f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'{items}</urlset>'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/sitemap.xml":
                return httpx.Response(200, content=big.encode("utf-8"))
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        async def run() -> list[str]:
            try:
                return await discover_product_urls(
                    client, "https://example.com",
                    include_patterns=["*/product/*"],
                    max_urls=10,
                )
            finally:
                await client.aclose()

        urls = asyncio.run(run())
        self.assertEqual(len(urls), 10)


class DiscoveryExtractionTests(unittest.TestCase):
    def test_extract_from_product_page(self):
        info = extract_product_info(
            PRODUCT_HTML, "https://example.com/product/rtx-5090",
            default_currency="AUD",
        )
        self.assertIsNotNone(info)
        self.assertEqual(info["external_id"], "GPU-5090-MSI")
        self.assertEqual(info["price"], Decimal("3499.00"))
        self.assertEqual(info["currency"], "AUD")
        self.assertEqual(info["extractor_method"], "jsonld")
        self.assertTrue(info["in_stock"])
        self.assertIn("RTX 5090", info["name"])

    def test_no_product_schema_returns_none(self):
        info = extract_product_info(
            NON_PRODUCT_HTML, "https://example.com/blog/something",
        )
        self.assertIsNone(info)

    def test_wrong_currency_raises(self):
        with self.assertRaises(ExtractionError):
            extract_product_info(
                WRONG_CURRENCY_HTML, "https://example.com/p/foo",
                default_currency="AUD",
            )

    def test_out_of_range_raises(self):
        with self.assertRaises(ExtractionError):
            extract_product_info(
                OUT_OF_RANGE_HTML, "https://example.com/p/foo",
                default_currency="AUD",
                price_min=Decimal("1.00"),
                price_max=Decimal("50000.00"),
            )

    def test_falls_back_to_url_slug_for_id(self):
        html = """<!DOCTYPE html><html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"No-SKU Product",
         "offers":{"@type":"Offer","price":"99","priceCurrency":"AUD"}}
        </script></head></html>"""
        info = extract_product_info(html, "https://x.com/p/widget-2000")
        self.assertEqual(info["external_id"], "widget-2000")


class SynthesiseOurSkuTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(synthesise_our_sku("Centre Com", "RTX5090"), "EXT-CC-RTX5090")
        self.assertEqual(synthesise_our_sku("Mwave", "ABC-123"), "EXT-M-ABC-123")
        self.assertEqual(synthesise_our_sku("PLE Computers", "x"), "EXT-PC-X")

    def test_special_chars_stripped(self):
        self.assertEqual(
            synthesise_our_sku("Scorptec", "foo/bar baz"),
            "EXT-S-FOO-BAR-BAZ",
        )


class DiscoveredStorageTests(unittest.TestCase):
    def test_upsert_and_list(self):
        with tempfile.TemporaryDirectory() as td:
            store = PriceStore(Path(td) / "p.db")
            now = datetime.now(timezone.utc)
            dp = DiscoveredProduct(
                competitor="Centre Com",
                external_id="GPU-1",
                our_sku="EXT-CC-GPU-1",
                product_name="Test GPU",
                url="https://example.com/p/gpu-1",
                first_seen=now,
                last_seen=now,
            )
            store.upsert_discovered(dp)
            # second upsert with same external_id should update, not duplicate
            store.upsert_discovered(dp)

            rows = store.list_discovered(competitor="Centre Com")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["product_name"], "Test GPU")
            self.assertEqual(store.count_discovered(), 1)


if __name__ == "__main__":
    unittest.main()
