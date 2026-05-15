CREATE TABLE "activity_log" (
	"id" serial PRIMARY KEY,
	"entity_type" text NOT NULL,
	"entity_id" integer,
	"entity_name" text,
	"action" text NOT NULL,
	"details" text,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "agents" (
	"id" serial PRIMARY KEY,
	"name" text NOT NULL,
	"slug" text NOT NULL UNIQUE,
	"description" text,
	"type" text NOT NULL,
	"status" text DEFAULT 'idle' NOT NULL,
	"last_run" timestamp,
	"last_result" text,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "websites" (
	"id" serial PRIMARY KEY,
	"name" text NOT NULL,
	"url" text NOT NULL,
	"description" text,
	"status" text DEFAULT 'active' NOT NULL,
	"last_checked" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
