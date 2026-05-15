CREATE TABLE "gene_versions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"gene_id" uuid NOT NULL,
	"version" varchar(16) NOT NULL,
	"manifest" jsonb NOT NULL,
	"changelog" text DEFAULT '' NOT NULL,
	"is_latest" boolean DEFAULT false NOT NULL,
	"published_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "genes" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(128) NOT NULL,
	"slug" varchar(128) NOT NULL,
	"version" varchar(16) NOT NULL,
	"description" text DEFAULT '' NOT NULL,
	"short_description" varchar(256) DEFAULT '' NOT NULL,
	"category" varchar(32) NOT NULL,
	"tags" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"icon" varchar(64),
	"source" varchar(16) DEFAULT 'official' NOT NULL,
	"source_ref" text,
	"manifest" jsonb NOT NULL,
	"compatibility" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"dependencies" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"synergies" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"parent_gene_id" uuid,
	"author" jsonb DEFAULT '{"type":"human","name":""}'::jsonb NOT NULL,
	"install_count" integer DEFAULT 0 NOT NULL,
	"avg_rating" real DEFAULT 0 NOT NULL,
	"effectiveness_score" real DEFAULT 0 NOT NULL,
	"review_status" varchar(16) DEFAULT 'draft' NOT NULL,
	"is_published" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"deleted_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "genomes" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(128) NOT NULL,
	"slug" varchar(128) NOT NULL,
	"version" varchar(16) NOT NULL,
	"description" text DEFAULT '' NOT NULL,
	"short_description" varchar(256) DEFAULT '' NOT NULL,
	"icon" varchar(64),
	"genes" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"compatibility" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"install_count" integer DEFAULT 0 NOT NULL,
	"avg_rating" real DEFAULT 0 NOT NULL,
	"author" jsonb DEFAULT '{"type":"human","name":""}'::jsonb NOT NULL,
	"is_published" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"deleted_at" timestamp with time zone
);
--> statement-breakpoint
ALTER TABLE "gene_versions" ADD CONSTRAINT "gene_versions_gene_id_genes_id_fk" FOREIGN KEY ("gene_id") REFERENCES "public"."genes"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "gene_versions_gene_id_idx" ON "gene_versions" USING btree ("gene_id");--> statement-breakpoint
CREATE UNIQUE INDEX "gene_versions_gene_version_idx" ON "gene_versions" USING btree ("gene_id","version");--> statement-breakpoint
CREATE UNIQUE INDEX "genes_slug_idx" ON "genes" USING btree ("slug");--> statement-breakpoint
CREATE INDEX "genes_category_idx" ON "genes" USING btree ("category");--> statement-breakpoint
CREATE INDEX "genes_source_idx" ON "genes" USING btree ("source");--> statement-breakpoint
CREATE INDEX "genes_review_status_idx" ON "genes" USING btree ("review_status");--> statement-breakpoint
CREATE UNIQUE INDEX "genomes_slug_idx" ON "genomes" USING btree ("slug");