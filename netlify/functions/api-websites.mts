import type { Config, Context } from "@netlify/functions";
import { db } from "../../db/index.js";
import { websites, activityLog } from "../../db/schema.js";
import { eq, desc } from "drizzle-orm";

export default async (req: Request, context: Context) => {
  const { id } = context.params;
  const method = req.method;

  try {
    // GET /api/websites
    if (method === "GET" && !id) {
      const all = await db.select().from(websites).orderBy(desc(websites.createdAt));
      return Response.json(all);
    }

    // GET /api/websites/:id
    if (method === "GET" && id) {
      const [site] = await db.select().from(websites).where(eq(websites.id, parseInt(id)));
      if (!site) return new Response("Not found", { status: 404 });
      return Response.json(site);
    }

    // POST /api/websites
    if (method === "POST" && !id) {
      const body = await req.json();
      if (!body.name || !body.url) {
        return new Response("name and url are required", { status: 400 });
      }
      const [site] = await db.insert(websites).values({
        name: body.name,
        url: body.url,
        description: body.description ?? null,
        status: body.status ?? "active",
      }).returning();

      await db.insert(activityLog).values({
        entityType: "website",
        entityId: site.id,
        entityName: site.name,
        action: "created",
        details: JSON.stringify({ url: site.url }),
      });

      return Response.json(site, { status: 201 });
    }

    // PATCH /api/websites/:id
    if (method === "PATCH" && id) {
      const body = await req.json();
      const [updated] = await db.update(websites).set({
        ...(body.name !== undefined && { name: body.name }),
        ...(body.url !== undefined && { url: body.url }),
        ...(body.description !== undefined && { description: body.description }),
        ...(body.status !== undefined && { status: body.status }),
        ...(body.lastChecked !== undefined && { lastChecked: new Date(body.lastChecked) }),
        updatedAt: new Date(),
      }).where(eq(websites.id, parseInt(id))).returning();

      if (!updated) return new Response("Not found", { status: 404 });

      await db.insert(activityLog).values({
        entityType: "website",
        entityId: updated.id,
        entityName: updated.name,
        action: "updated",
        details: JSON.stringify({ status: updated.status }),
      });

      return Response.json(updated);
    }

    // DELETE /api/websites/:id
    if (method === "DELETE" && id) {
      const [deleted] = await db.delete(websites).where(eq(websites.id, parseInt(id))).returning();
      if (!deleted) return new Response("Not found", { status: 404 });

      await db.insert(activityLog).values({
        entityType: "website",
        entityId: deleted.id,
        entityName: deleted.name,
        action: "deleted",
        details: null,
      });

      return new Response(null, { status: 204 });
    }

    return new Response("Method not allowed", { status: 405 });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Internal server error";
    return Response.json({ error: message }, { status: 500 });
  }
};

export const config: Config = {
  path: ["/api/websites", "/api/websites/:id"],
};
