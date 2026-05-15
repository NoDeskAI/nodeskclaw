ALTER TABLE "agent_template_versions" ADD COLUMN "commit_sha" varchar(40);--> statement-breakpoint
ALTER TABLE "agent_template_versions" ADD COLUMN "git_tag" varchar(64);--> statement-breakpoint
ALTER TABLE "agent_template_versions" ADD COLUMN "files" jsonb;--> statement-breakpoint
ALTER TABLE "agent_templates" ADD COLUMN "repository_url" text;--> statement-breakpoint
ALTER TABLE "agent_templates" ADD COLUMN "file_count" integer DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE "genome_versions" ADD COLUMN "commit_sha" varchar(40);--> statement-breakpoint
ALTER TABLE "genome_versions" ADD COLUMN "git_tag" varchar(64);--> statement-breakpoint
ALTER TABLE "genome_versions" ADD COLUMN "files" jsonb;--> statement-breakpoint
ALTER TABLE "genomes" ADD COLUMN "repository_url" text;--> statement-breakpoint
ALTER TABLE "genomes" ADD COLUMN "file_count" integer DEFAULT 0 NOT NULL;