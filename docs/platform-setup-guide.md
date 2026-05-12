# Neural Hardware – Platform Account Setup Guide

> Complete field-by-field instructions for every sales and social channel.
> Estimated total setup time: ~12–16 hours across 3–4 weeks.

---

## Prerequisites (Complete These First)

Before setting up ANY platform, have the following ready:

| Item | Status | Notes |
|------|--------|-------|
| ABN (Australian Business Number) | [ ] | Apply free at business.gov.au – takes 5 min |
| ACN (if Pty Ltd) | [ ] | ASIC – $538 registration fee |
| Business name registered | [ ] | ASIC BizReg – $44/yr (online) or $102/3yr |
| Business bank account | [ ] | ANZ, NAB Business, or Westpac – see checklist |
| .com.au domain | [ ] | neuralhardware.com.au via VentraIP or Crazy Domains |
| Business email | [ ] | support@neuralhardware.com.au via Google Workspace ($9/mo) |
| Mobile number for 2FA | [ ] | Use a dedicated business SIM |
| Logo + banner images | [ ] | 1000×1000 logo, 1200×628 banner (Canva free tier) |
| Proof of ID | [ ] | Driver's licence or passport scan |
| Product photos (min 5 SKUs) | [ ] | White background + lifestyle shots |

---

## 1. eBay Australia – Seller Account & Store

### Sign-Up URL
https://www.ebay.com.au/register

### Requirements
- Personal or business email
- ABN (for GST tax invoicing)
- Bank account (for PayPal/eBay payouts)
- Mobile number

### Step-by-Step Setup

**Step 1 – Create Business Account**
1. Go to https://www.ebay.com.au/register
2. Click **"Create a business account"** (not personal)
3. Enter business name: `Neural Hardware` (or your registered business name)
4. Enter business email: support@neuralhardware.com.au
5. Create a strong password (16+ chars, store in 1Password or Bitwarden)
6. Verify your email

**Step 2 – Add Identity Verification**
1. Go to My eBay → Account → Personal Information
2. Enter ABN under "Tax information"
3. Upload photo ID when prompted
4. Add your business address (use a registered office address if home-based)

**Step 3 – Set Up Payments**
1. Go to Payments → Manage Payments
2. Connect your Australian bank account (BSB + account number)
3. Verify the two micro-deposits (1–2 business days)
4. Set payout frequency: Daily

**Step 4 – Open an eBay Store Subscription**
1. Go to https://www.ebay.com.au/pages/storefront/subscriptions.html
2. Choose **"Basic Store"** ($22.99/mo) to start – gives 250 free fixed-price listings
3. Enter your store name: `Neural Hardware`
4. Upload your store logo (800×800px minimum)
5. Add store description: mention ABN, ACL compliance, Australian warranty

**Step 5 – Configure Seller Settings**
- Shipping policy: Create "AustraliaPost Standard (3–7 days)" and "Express Post (1–3 days)"
- Return policy: **"30-day returns accepted"** – this is MANDATORY for good standing and ACL compliance
- Business policies (My eBay → Business Policies): Create templates for payment, postage, returns

**Step 6 – List Your First Product**
1. My eBay → Sell → Create Listing
2. Choose category: `Computers/Tablets & Networking → Computer Components & Parts`
3. Fill: Title (80 chars max, use keywords like "NVIDIA RTX 5090 GPU AU Warranty")
4. Condition: New
5. Photos: Minimum 4 photos, max 24
6. Price: Set BIN (Buy It Now) price; avoid auctions initially
7. Include in description: ABN, warranty terms, ACL statement, GST invoice on request

**Step 7 – Performance Targets**
- Aim for Top Rated Seller status (98%+ positive feedback, same-day dispatch)
- Response time: under 12 hours

### Common Mistakes & Fixes

| Mistake | Fix |
|---------|-----|
| Using personal account for business | Create separate business account; cannot convert |
| Not adding ABN | Legal requirement for GST; add under Tax Settings |
| "No returns" policy | Violates ACL; always set 30-day returns |
| Listing without tracking | Always include tracked shipping for buyer/seller protection |
| Duplicate listings | eBay will suppress; use Variation listings instead |

### eBay → Shopify Connection
1. Install "CedCommerce eBay Integration" app from Shopify App Store ($29/mo)
2. Connect eBay seller account via OAuth
3. Sync inventory bidirectionally (Shopify is master; eBay mirrors)

---

## 2. Shopify – Main Store

### Sign-Up URL
https://www.shopify.com/au

### Requirements
- Email address
- Credit card (for monthly subscription)
- ABN + GST registration
- Custom domain (neuralhardware.com.au)

### Step-by-Step Setup

**Step 1 – Start Free Trial**
1. Go to https://www.shopify.com/au
2. Click "Start free trial" → enter email → create password
3. Answer onboarding questions: "I'm selling physical products" / "I already have products"
4. Choose plan: **Basic Shopify ($56 AUD/mo)** to start

**Step 2 – Configure Store Settings**
1. Settings → General
   - Store name: Neural Hardware
   - Legal business name: Neural Hardware Pty Ltd
   - Store address: your registered business address
   - Store email: support@neuralhardware.com.au
   - Store phone: your business mobile
   - Unit system: Metric | Currency: AUD

2. Settings → Taxes
   - Tick "Charge taxes on products"
   - Add GST: 10% on all products
   - Tick "All prices include tax" (GST-inclusive pricing for AU consumers)
   - Add your ABN under Tax Registration

3. Settings → Payments
   - Primary: **Shopify Payments** (best rates for AU: 1.7%–2.4% + 30c)
   - Add: PayPal, Afterpay, Zip Pay
   - Fraud prevention: Enable 3D Secure + CVV

**Step 3 – Connect Custom Domain**
1. Settings → Domains → Buy new domain (Shopify $18/yr) OR connect existing
2. If external (e.g., VentraIP): Add Shopify's DNS records (CNAME + A record) at registrar
3. Enable SSL certificate (auto-generated, takes 1–24 hours)
4. Set neuralhardware.com.au as primary domain; redirect www

**Step 4 – Choose & Customise Theme**
1. Online Store → Themes → Visit Theme Store
2. Free option: **Dawn** (clean, fast, recommended for electronics)
3. Paid option: **Impulse** ($380 one-time, excellent for tech stores) – worth it after first $2k revenue
4. Customise: Upload logo, set brand colours (see site colour guide), add hero banner

**Step 5 – Add Products**
1. Products → Add Product
2. Fill: Title, Description, Media (min 3 photos), Price ($XX.XX incl. GST), Compare-at price
3. Inventory: Add SKU (e.g., NH-RTX5090), Barcode (optional), Track quantity
4. Shipping: Tick "This is a physical product"; set weight in kg
5. Variants: Add if selling multiple colours/specs
6. SEO: Add meta title and description; use target keywords

**Step 6 – Configure Shipping**
1. Settings → Shipping and Delivery
2. Create shipping zones:
   - Australia: Free over $199; Flat $9.95 under $199; Express $14.95
   - International: Quote-based initially
3. Connect Australia Post eParcel for live rates (requires AusPost business account)
4. Print labels directly from Shopify Orders page

**Step 7 – Legal Pages**
1. Settings → Legal → Generate templates then customise:
   - Privacy Policy (add GDPR + Privacy Act 1988 AU references)
   - Terms of Service (add ACL consumer guarantee clauses)
   - Refund Policy (30-day change-of-mind; ACL warranties)
   - Shipping Policy
2. Settings → Legal → Add ABN, ACN, GST registration number

**Step 8 – Essential Apps to Install**
| App | Purpose | Cost |
|-----|---------|------|
| Klaviyo | Email marketing & abandoned cart | Free to 500 contacts |
| Yotpo Reviews | Product reviews + Google integration | Free plan |
| Loox | Photo reviews | $9.99/mo |
| Google & YouTube | Google Shopping feed | Free |
| Facebook & Instagram | Social commerce | Free |
| Afterpay | BNPL payments | Per-transaction fee |
| ShipStation | Multi-carrier shipping | $9/mo |
| Gorgias | Customer support ticketing | $10/mo |

### Common Mistakes & Fixes

| Mistake | Fix |
|---------|-----|
| Not enabling GST | Legal requirement for AU businesses with $75k+ turnover |
| Generic theme with no branding | Spend 2 hours customising colours, fonts, logo |
| No abandoned cart emails | Set up Klaviyo flow on day 1 – worth $50–100/day |
| Not adding product reviews | Install Yotpo or Loox before launch |
| No live chat | Add Tidio or Gorgias chat widget |

### Shopify → Facebook/Instagram Connection
1. Sales Channels → Facebook & Instagram (add channel)
2. Connect your Facebook Page + Facebook Business Manager
3. Enable Commerce Manager for shopping
4. Sync product catalogue (automatic after connection)

---

## 3. WooCommerce (Optional Secondary Store)

### Why Consider It
- Lower ongoing cost than Shopify (~$10–30/mo hosting vs $56/mo)
- More control over data and customisation
- Good if you already have WordPress skills

### Sign-Up URL
https://woocommerce.com (plugin) + hosting at https://ventraip.com.au

### Requirements
- Web hosting (VentraIP AU Business Hosting $9.95/mo)
- Domain
- WordPress.org installed (one-click at host)
- SSL certificate (free via Let's Encrypt)

### Step-by-Step Setup

**Step 1 – Get Hosting**
1. Go to https://ventraip.com.au → Hosting → Business Hosting → $9.95/mo plan
2. Install WordPress via cPanel → Softaculous (1-click)
3. Point your domain's nameservers to VentraIP

**Step 2 – Install WooCommerce**
1. WordPress Admin → Plugins → Add New → Search "WooCommerce"
2. Install & Activate
3. Run Setup Wizard: currency (AUD), location (Australia), product type (Physical)

**Step 3 – Configure Tax**
1. WooCommerce → Settings → Tax → Enable Tax
2. Add Tax Rate: Country = AU, Rate = 10%, Name = GST, Shipping = Yes
3. Set prices entered inclusive of tax = YES (AU standard)

**Step 4 – Configure Payments**
1. WooCommerce → Settings → Payments
2. Enable: Stripe (via WooCommerce Stripe plugin), PayPal
3. For Afterpay: Install "Afterpay Gateway for WooCommerce" (free plugin)

**Step 5 – Shipping**
1. WooCommerce → Settings → Shipping → Add Zone → "Australia"
2. Add methods: Free shipping (min order $199), Flat rate ($9.95), Local pickup

### Recommendation
Start with Shopify. Only add WooCommerce if: (a) you outgrow Shopify's customisation limits, or (b) you want to serve B2B clients on a custom pricing portal.

---

## 4. Instagram Business + Shop

### Sign-Up URL
https://www.instagram.com (create new account) or convert existing

### Requirements
- Facebook Page (required for shopping)
- Business registered in Australia
- Product catalogue connected via Facebook
- At least 9 feed posts before applying for shopping

### Step-by-Step Setup

**Step 1 – Create/Convert to Business Account**
1. Download Instagram app → Create new account
2. Use username: @neuralhardware.au (or @neuralhardwareaustralia)
3. Profile → Settings → Account → Switch to Professional Account
4. Select: Business → Electronics Store
5. Connect to your Facebook Page (must exist first)

**Step 2 – Optimise Profile**
- Profile photo: Your logo (800×800px, on white or transparent background)
- Bio (150 chars): "Australia's AI & GPU hardware store 🇦🇺 | Fast local shipping | ACL warranty | Shop link 👇"
- Link in bio: Use Linktree (free) or direct Shopify store URL
- Add contact email + phone

**Step 3 – Set Up Instagram Shopping**
1. Profile → Settings → Business → Set Up Instagram Shopping
2. Follow prompts to connect your Facebook Product Catalogue
3. Submit for review (1–3 business days)
4. Once approved: Tag products in posts and Stories

**Step 4 – Content Strategy (First 30 Days)**
- 3 posts/week minimum
- Content mix: Product photos (40%), educational/tips (30%), behind-the-scenes (20%), UGC (10%)
- Use Reels for reach (algorithm favours Reels 3–5x over static posts)
- Hashtags: #australiagaming #pcbuild #AIhardware #gpuaustralia #techau #neuralhardware

**Step 5 – Run First Instagram Ad**
1. Post a product photo → "Boost Post"
2. Audience: Australia, age 18–45, interests: PC gaming, AI, technology
3. Budget: $10/day for 7 days = $70 test
4. Goal: "Website visits" or "Shop now"

### Common Mistakes & Fixes

| Mistake | Fix |
|---------|-----|
| Applying for shopping before 9 posts | Post 9 quality posts first |
| Using personal account for business | Switch or create new business account |
| Inconsistent posting | Use Buffer or Later to schedule 2 weeks ahead |
| Not using product tags | Tag every relevant product in every applicable post |

---

## 5. Facebook Page + Commerce Manager

### Sign-Up URL
https://www.facebook.com/pages/create + https://business.facebook.com

### Requirements
- Personal Facebook account (to create Business Manager)
- ABN for payouts
- Bank account
- Product photos and descriptions ready

### Step-by-Step Setup

**Step 1 – Create Facebook Business Manager**
1. Go to https://business.facebook.com
2. Click "Create Account" → enter business name, your name, email
3. Add your business details (address, ABN in tax settings)
4. Verify your domain: Add meta tag to Shopify's theme.liquid file (Settings → Meta Tags section) OR use DNS TXT record at your registrar

**Step 2 – Create Facebook Page**
1. From Business Manager: Pages → Add → Create New Page
2. Page name: Neural Hardware Australia
3. Category: Electronics Store / Computer Store
4. Description: "Australia's trusted AI & GPU hardware store. Local warranty. Fast shipping. ACL compliant."
5. Upload profile photo (logo) and cover photo (hero banner)
6. Add website, email, phone, business hours

**Step 3 – Set Up Commerce Manager**
1. Go to https://www.facebook.com/commerce_manager
2. Click "Get Started" → Create a Shop
3. Select: "Checkout on another website" → link Shopify store URL
4. Business Info: Enter ABN, address, bank account for AU payouts
5. Connect your Shopify product catalogue (via Shopify Facebook & Instagram app)
6. Submit for review

**Step 4 – Create Meta Pixel**
1. Business Manager → Events Manager → Connect Data Sources → Web → Meta Pixel
2. Name: "Neural Hardware Pixel"
3. Connect via Shopify → Facebook & Instagram app (auto-installs pixel)
4. Verify pixel is firing: Install "Meta Pixel Helper" Chrome extension
5. Set up Standard Events: PageView, ViewContent, AddToCart, InitiateCheckout, Purchase

**Step 5 – Run First Facebook Ad**
1. Ads Manager → Create Campaign
2. Objective: "Sales" (Conversion)
3. Audience: Australia, 18–45, Interests: PC Building, Gaming, Artificial Intelligence, GPU
4. Placement: Automatic (lets Meta optimise)
5. Budget: $20/day
6. Ad format: Single image or carousel with product photos
7. Pixel event: Purchase

### Common Mistakes & Fixes

| Mistake | Fix |
|---------|-----|
| Not verifying domain | Without verification, ad attribution is limited; verify in Business Manager |
| Using personal account for ads | Always use Business Manager |
| No Pixel installed | Install before running any ads; loses data otherwise |
| Commerce Manager rejection | Usually due to missing policy pages; add ToS, Refund, Privacy to site |
| Ad account spending limits | New accounts start at $50/day limit; request increase after 30 days spend |

---

## 6. TikTok Business Account + TikTok Shop

### Sign-Up URL
https://business.tiktok.com + https://seller-au.tiktok.com

### Requirements
- Australian business registration (ABN)
- Product that complies with TikTok's prohibited/restricted items list
- Bank account for payouts
- Mobile phone number

### Eligibility Check – TikTok Shop Australia
As of 2025, TikTok Shop is live in Australia. Requirements:
- Business entity registered in Australia
- Valid ABN
- Products must not be on prohibited list (most tech hardware is approved)
- Bank account: Australian business account

### Step-by-Step Setup

**Step 1 – Create TikTok Business Account**
1. Download TikTok app → Create account
2. Profile → Settings → Manage Account → Switch to Business Account
3. Category: Electronics / E-commerce
4. Username: @neuralhardware (or @neuralhardwareau)
5. Bio: "🇦🇺 AI & GPU Hardware | Fast AU shipping | Shop link 👇"
6. Add website link (Shopify store)

**Step 2 – Set Up TikTok Business Center**
1. Go to https://business.tiktok.com
2. Register with business email
3. Add your ABN and business details
4. Create TikTok Pixel: Business Center → Assets → Events → Web Events → Pixel
5. Install Pixel via Shopify TikTok app (Shopify App Store → TikTok → Connect)

**Step 3 – Apply for TikTok Shop**
1. Go to https://seller-au.tiktok.com
2. Click "Sign Up as Seller"
3. Select account type: "Individual Business" or "Company"
4. Enter ABN, upload ABN/business registration certificate
5. Upload bank statement or voided cheque for payout account
6. Upload product listings (at least 3 SKUs to start)
7. Wait for verification: 1–3 business days

**Step 4 – Link TikTok Shop to Shopify**
1. Shopify App Store → Install "TikTok" app (official)
2. Connect TikTok Business Account and TikTok Shop
3. Sync product catalogue (products, prices, inventory)
4. Enable "Shop" tab on TikTok profile

**Step 5 – Content Strategy**
- Post 1× per day minimum (short-form, 15–60 seconds)
- Content types that perform for hardware: Unboxing, benchmarks, before/after temps, "Which GPU for your budget?" comparisons
- Use trending sounds
- Always include a Call to Action: "Link in bio" or use TikTok Shop product links
- Reply to EVERY comment in the first hour of posting (boosts algorithm)

**Step 6 – TikTok Ads (after 30 days organic)**
1. Ads Manager: https://ads.tiktok.com
2. Campaign type: "Product Sales" → TikTok Shop
3. Target: Australia, 18–35, interests: technology, gaming, AI
4. Budget: $20/day
5. Creative: Use your best-performing organic videos as ad creatives ("Spark Ads")

### Common Mistakes & Fixes

| Mistake | Fix |
|---------|-----|
| Not posting consistently | Use CapCut (free) for quick video editing; batch 1 week of content |
| Applying without ABN | Must have ABN; can register same day |
| Not using product links | Tag products in every video; this drives direct purchases |
| Ignoring TikTok Live | Go live 2×/week for 20 min; Live Shopping is the #1 TikTok commerce driver in AU |
| No Spark Ads | Best ROI comes from boosting organic content that already has engagement |

---

## Platform Connection Summary

```
Shopify (master)
    ├── Facebook & Instagram (via Shopify app → Commerce Manager)
    ├── TikTok (via Shopify TikTok app → TikTok Shop)
    ├── eBay Australia (via CedCommerce or Codisto app)
    ├── Google Shopping (via Google & YouTube app)
    └── Amazon AU (future – via Codisto or M2E Pro)
```

## All Platform Logins Checklist

| Platform | Email Used | 2FA Enabled | Notes |
|----------|-----------|-------------|-------|
| eBay.com.au | | [ ] | |
| Shopify | | [ ] | |
| Instagram | | [ ] | |
| Facebook Business Manager | | [ ] | |
| TikTok Business | | [ ] | |
| Google Analytics 4 | | [ ] | |
| Google Merchant Center | | [ ] | |
| Meta Business Suite | | [ ] | |
| PayPal Business | | [ ] | |
| Afterpay Merchant | | [ ] | |

> Store all credentials in a password manager (1Password, Bitwarden) – NEVER in a spreadsheet or browser.
