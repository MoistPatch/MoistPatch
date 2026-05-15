import type { Config, Context } from "@netlify/functions";
import { db } from "../../db/index.js";
import { agents, activityLog } from "../../db/schema.js";
import { eq, desc } from "drizzle-orm";

export default async (req: Request, context: Context) => {
  const { id } = context.params;
  const method = req.method;

  try {
    // GET /api/agents
    if (method === "GET" && !id) {
      const all = await db.select().from(agents).orderBy(desc(agents.createdAt));
      return Response.json(all);
    }

    // GET /api/agents/:id
    if (method === "GET" && id) {
      const [agent] = await db.select().from(agents).where(eq(agents.id, parseInt(id)));
      if (!agent) return new Response("Not found", { status: 404 });
      return Response.json(agent);
    }

    // POST /api/agents
    if (method === "POST" && !id) {
      const body = await req.json();
      if (!body.name || !body.slug || !body.type) {
        return new Response("name, slug, and type are required", { status: 400 });
      }
      const [agent] = await db.insert(agents).values({
        name: body.name,
        slug: body.slug,
        description: body.description ?? null,
        type: body.type,
        status: body.status ?? "idle",
      }).returning();

      await db.insert(activityLog).values({
        entityType: "agent",
        entityId: agent.id,
        entityName: agent.name,
        action: "registered",
        details: JSON.stringify({ type: agent.type }),
      });

      return Response.json(agent, { status: 201 });
    }

    // PATCH /api/agents/:id
    if (method === "PATCH" && id) {
      const body = await req.json();
      const [updated] = await db.update(agents).set({
        ...(body.name !== undefined && { name: body.name }),
        ...(body.description !== undefined && { description: body.description }),
        ...(body.status !== undefined && { status: body.status }),
        ...(body.lastResult !== undefined && { lastResult: body.lastResult }),
        ...(body.lastRun !== undefined && { lastRun: new Date(body.lastRun) }),
        updatedAt: new Date(),
      }).where(eq(agents.id, parseInt(id))).returning();

      if (!updated) return new Response("Not found", { status: 404 });

      return Response.json(updated);
    }

    // DELETE /api/agents/:id
    if (method === "DELETE" && id) {
      const [deleted] = await db.delete(agents).where(eq(agents.id, parseInt(id))).returning();
      if (!deleted) return new Response("Not found", { status: 404 });

      await db.insert(activityLog).values({
        entityType: "agent",
        entityId: deleted.id,
        entityName: deleted.name,
        action: "removed",
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
  path: ["/api/agents", "/api/agents/:id"],
};
