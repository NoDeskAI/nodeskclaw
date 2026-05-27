CREATE TABLE "gene_relations" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"source_gene_id" uuid NOT NULL,
	"target_gene_id" uuid NOT NULL,
	"relation_type" varchar(24) NOT NULL,
	"strength" real DEFAULT 0.5 NOT NULL,
	"reason" text,
	"created_by" varchar(64) DEFAULT 'curator-agent' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "gene_reviews" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"gene_id" uuid NOT NULL,
	"reviewer" varchar(64) DEFAULT 'curator-agent' NOT NULL,
	"score" real,
	"verdict" varchar(24),
	"comments" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"changes_made" jsonb,
	"feedback" varchar(32),
	"model" varchar(64),
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "genome_versions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"genome_id" uuid NOT NULL,
	"version" varchar(16) NOT NULL,
	"genes" jsonb NOT NULL,
	"changelog" text DEFAULT '' NOT NULL,
	"is_latest" boolean DEFAULT false NOT NULL,
	"published_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "genes" ADD COLUMN "ai_score" real;--> statement-breakpoint
ALTER TABLE "genes" ADD COLUMN "ai_verdict" varchar(24);--> statement-breakpoint
ALTER TABLE "genes" ADD COLUMN "ai_enriched" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "genomes" ADD COLUMN "category" varchar(32) DEFAULT 'general' NOT NULL;--> statement-breakpoint
ALTER TABLE "genomes" ADD COLUMN "tags" jsonb DEFAULT '[]'::jsonb NOT NULL;--> statement-breakpoint
ALTER TABLE "gene_relations" ADD CONSTRAINT "gene_relations_source_gene_id_genes_id_fk" FOREIGN KEY ("source_gene_id") REFERENCES "public"."genes"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "gene_relations" ADD CONSTRAINT "gene_relations_target_gene_id_genes_id_fk" FOREIGN KEY ("target_gene_id") REFERENCES "public"."genes"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "gene_reviews" ADD CONSTRAINT "gene_reviews_gene_id_genes_id_fk" FOREIGN KEY ("gene_id") REFERENCES "public"."genes"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "genome_versions" ADD CONSTRAINT "genome_versions_genome_id_genomes_id_fk" FOREIGN KEY ("genome_id") REFERENCES "public"."genomes"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "gene_relations_source_idx" ON "gene_relations" USING btree ("source_gene_id");--> statement-breakpoint
CREATE INDEX "gene_relations_target_idx" ON "gene_relations" USING btree ("target_gene_id");--> statement-breakpoint
CREATE UNIQUE INDEX "gene_relations_pair_idx" ON "gene_relations" USING btree ("source_gene_id","target_gene_id","relation_type");--> statement-breakpoint
CREATE INDEX "gene_reviews_gene_id_idx" ON "gene_reviews" USING btree ("gene_id");--> statement-breakpoint
CREATE INDEX "genome_versions_genome_id_idx" ON "genome_versions" USING btree ("genome_id");--> statement-breakpoint
CREATE UNIQUE INDEX "genome_versions_genome_version_idx" ON "genome_versions" USING btree ("genome_id","version");--> statement-breakpoint
CREATE INDEX "genomes_category_idx" ON "genomes" USING btree ("category");