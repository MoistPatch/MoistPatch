import type { Config, Context } from "@netlify/functions";
import { db } from "../../db/index.js";
import { agents, activityLog } from "../../db/schema.js";
import { eq } from "drizzle-orm";

export default async (req: Request, context: Context) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const { id } = context.params;

  try {
    const [agent] = await db.select().from(agents).where(eq(agents.id, parseInt(id)));
    if (!agent) return new Response("Agent not found", { status: 404 });

    if (agent.status === "running") {
      return Response.json({ error: "Agent is already running" }, { status: 409 });
    }

    const now = new Date();
    const [updated] = await db.update(agents).set({
      status: "running",
      lastRun: now,
      updatedAt: now,
    }).where(eq(agents.id, parseInt(id))).returning();

    await db.insert(activityLog).values({
      entityType: "agent",
      entityId: updated.id,
      entityName: updated.name,
      action: "triggered",
      details: JSON.stringify({ triggeredAt: now.toISOString() }),
    });

    return Response.json({ message: "Agent triggered", agent: updated });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Internal server error";
    return Response.json({ error: message }, { status: 500 });
  }
};

export const config: Config = {
  path: "/api/agents/:id/trigger",
  method: "POST",
};
