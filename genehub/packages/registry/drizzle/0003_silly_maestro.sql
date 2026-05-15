CREATE TABLE "agent_template_versions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"template_id" uuid NOT NULL,
	"version" varchar(16) NOT NULL,
	"genomes" jsonb NOT NULL,
	"genes" jsonb NOT NULL,
	"changelog" text DEFAULT '' NOT NULL,
	"is_latest" boolean DEFAULT false NOT NULL,
	"published_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "agent_templates" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(128) NOT NULL,
	"slug" varchar(128) NOT NULL,
	"version" varchar(16) NOT NULL,
	"description" text DEFAULT '' NOT NULL,
	"short_description" varchar(256) DEFAULT '' NOT NULL,
	"role" varchar(64),
	"category" varchar(32) DEFAULT 'general' NOT NULL,
	"tags" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"icon" varchar(64),
	"avatar_url" text,
	"genomes" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"genes" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"compatibility" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"install_count" integer DEFAULT 0 NOT NULL,
	"avg_rating" real DEFAULT 0 NOT NULL,
	"author" jsonb DEFAULT '{"type":"human","name":""}'::jsonb NOT NULL,
	"publisher_id" uuid,
	"is_published" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"deleted_at" timestamp with time zone
);
--> statement-breakpoint
ALTER TABLE "agent_template_versions" ADD CONSTRAINT "agent_template_versions_template_id_agent_templates_id_fk" FOREIGN KEY ("template_id") REFERENCES "public"."agent_templates"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent_templates" ADD CONSTRAINT "agent_templates_publisher_id_publishers_id_fk" FOREIGN KEY ("publisher_id") REFERENCES "public"."publishers"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "agent_template_versions_template_id_idx" ON "agent_template_versions" USING btree ("template_id");--> statement-breakpoint
CREATE UNIQUE INDEX "agent_template_versions_template_version_idx" ON "agent_template_versions" USING btree ("template_id","version");--> statement-breakpoint
CREATE UNIQUE INDEX "agent_templates_slug_idx" ON "agent_templates" USING btree ("slug");--> statement-breakpoint
CREATE INDEX "agent_templates_category_idx" ON "agent_templates" USING btree ("category");