ALTER TABLE "gene_versions" ADD COLUMN "commit_sha" varchar(40);--> statement-breakpoint
ALTER TABLE "gene_versions" ADD COLUMN "git_tag" varchar(64);--> statement-breakpoint
ALTER TABLE "gene_versions" ADD COLUMN "files" jsonb;--> statement-breakpoint
ALTER TABLE "genes" ADD COLUMN "repository_url" text;--> statement-breakpoint
ALTER TABLE "genes" ADD COLUMN "file_count" integer DEFAULT 0 NOT NULL;