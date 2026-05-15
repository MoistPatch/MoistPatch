import { pgTable, serial, text, timestamp, integer } from "drizzle-orm/pg-core";

export const websites = pgTable("websites", {
  id: serial().primaryKey(),
  name: text("name").notNull(),
  url: text("url").notNull(),
  description: text("description"),
  status: text("status").notNull().default("active"),
  lastChecked: timestamp("last_checked"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const agents = pgTable("agents", {
  id: serial().primaryKey(),
  name: text("name").notNull(),
  slug: text("slug").notNull().unique(),
  description: text("description"),
  type: text("type").notNull(),
  status: text("status").notNull().default("idle"),
  lastRun: timestamp("last_run"),
  lastResult: text("last_result"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const activityLog = pgTable("activity_log", {
  id: serial().primaryKey(),
  entityType: text("entity_type").notNull(),
  entityId: integer("entity_id"),
  entityName: text("entity_name"),
  action: text("action").notNull(),
  details: text("details"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});
