import {
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  real,
  text,
  timestamp,
  uniqueIndex,
  uuid,
  varchar,
} from 'drizzle-orm/pg-core';

export const publishers = pgTable(
  'publishers',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    github_id: integer('github_id').notNull(),
    github_login: varchar('github_login', { length: 64 }).notNull(),
    github_name: varchar('github_name', { length: 128 }).notNull().default(''),
    github_avatar_url: text('github_avatar_url').notNull().default(''),
    github_profile_url: text('github_profile_url').notNull().default(''),
    created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    last_login_at: timestamp('last_login_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex('publishers_github_id_idx').on(table.github_id)],
);

export const apiKeys = pgTable(
  'api_keys',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    publisher_id: uuid('publisher_id')
      .notNull()
      .references(() => publishers.id, { onDelete: 'cascade' }),
    token_prefix: varchar('token_prefix', { length: 16 }).notNull(),
    token_hash: varchar('token_hash', { length: 64 }).notNull(),
    name: varchar('name', { length: 128 }).notNull().default('Default'),
    last_used_at: timestamp('last_used_at', { withTimezone: true }),
    created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    revoked_at: timestamp('revoked_at', { withTimezone: true }),
  },
  (table) => [
    index('api_keys_publisher_id_idx').on(table.publisher_id),
    uniqueIndex('api_keys_token_hash_idx').on(table.token_hash),
  ],
);

export const genes = pgTable(
  'genes',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    name: varchar('name', { length: 128 }).notNull(),
    slug: varchar('slug', { length: 128 }).notNull(),
    version: varchar('version', { length: 16 }).notNull(),
    description: text('description').notNull().default(''),
    short_description: varchar('short_description', { length: 256 }).notNull().default(''),
    category: varchar('category', { length: 32 }).notNull(),
    tags: jsonb('tags').$type<string[]>().notNull().default([]),
    icon: varchar('icon', { length: 64 }),
    source: varchar('source', { length: 16 }).notNull().default('official'),
    source_ref: text('source_ref'),
    repository_url: text('repository_url'),
    file_count: integer('file_count').notNull().default(0),
    manifest: jsonb('manifest').notNull(),
    compatibility: jsonb('compatibility').$type<string[]>().notNull().default([]),
    dependencies: jsonb('dependencies')
      .$type<{ slug: string; version: string }[]>()
      .notNull()
      .default([]),
    synergies: jsonb('synergies').$type<string[]>().notNull().default([]),
    publisher_id: uuid('publisher_id').references(() => publishers.id),
    parent_gene_id: uuid('parent_gene_id'),
    author: jsonb('author')
      .$type<{ type: string; id?: string; name: string }>()
      .notNull()
      .default({ type: 'human', name: '' }),
    install_count: integer('install_count').notNull().default(0),
    avg_rating: real('avg_rating').notNull().default(0),
    effectiveness_score: real('effectiveness_score').notNull().default(0),
    review_status: varchar('review_status', { length: 16 }).notNull().default('draft'),
    ai_score: real('ai_score'),
    ai_verdict: varchar('ai_verdict', { length: 24 }),
    ai_enriched: boolean('ai_enriched').notNull().default(false),
    is_published: boolean('is_published').notNull().default(false),
    created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    updated_at: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
    deleted_at: timestamp('deleted_at', { withTimezone: true }),
  },
  (table) => [
    uniqueIndex('genes_slug_idx').on(table.slug),
    index('genes_category_idx').on(table.category),
    index('genes_source_idx').on(table.source),
    index('genes_review_status_idx').on(table.review_status),
  ],
);

export const genomes = pgTable(
  'genomes',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    name: varchar('name', { length: 128 }).notNull(),
    slug: varchar('slug', { length: 128 }).notNull(),
    version: varchar('version', { length: 16 }).notNull(),
    description: text('description').notNull().default(''),
    short_description: varchar('short_description', { length: 256 }).notNull().default(''),
    category: varchar('category', { length: 32 }).notNull().default('general'),
    tags: jsonb('tags').$type<string[]>().notNull().default([]),
    icon: varchar('icon', { length: 64 }),
    genes: jsonb('genes')
      .$type<{ slug: string; version: string; config_override?: Record<string, unknown> }[]>()
      .notNull()
      .default([]),
    compatibility: jsonb('compatibility').$type<string[]>().notNull().default([]),
    install_count: integer('install_count').notNull().default(0),
    avg_rating: real('avg_rating').notNull().default(0),
    author: jsonb('author')
      .$type<{ type: string; id?: string; name: string }>()
      .notNull()
      .default({ type: 'human', name: '' }),
    repository_url: text('repository_url'),
    file_count: integer('file_count').notNull().default(0),
    is_published: boolean('is_published').notNull().default(false),
    created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    updated_at: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
    deleted_at: timestamp('deleted_at', { withTimezone: true }),
  },
  (table) => [
    uniqueIndex('genomes_slug_idx').on(table.slug),
    index('genomes_category_idx').on(table.category),
  ],
);

export const genomeVersions = pgTable(
  'genome_versions',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    genome_id: uuid('genome_id')
      .notNull()
      .references(() => genomes.id, { onDelete: 'cascade' }),
    version: varchar('version', { length: 16 }).notNull(),
    genes: jsonb('genes')
      .$type<{ slug: string; version: string; config_override?: Record<string, unknown> }[]>()
      .notNull(),
    commit_sha: varchar('commit_sha', { length: 40 }),
    git_tag: varchar('git_tag', { length: 64 }),
    files: jsonb('files').$type<{ path: string; size: number; sha: string }[]>(),
    changelog: text('changelog').notNull().default(''),
    is_latest: boolean('is_latest').notNull().default(false),
    published_at: timestamp('published_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index('genome_versions_genome_id_idx').on(table.genome_id),
    uniqueIndex('genome_versions_genome_version_idx').on(table.genome_id, table.version),
  ],
);

export const geneReviews = pgTable(
  'gene_reviews',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    gene_id: uuid('gene_id').references(() => genes.id, { onDelete: 'cascade' }),
    entity_type: varchar('entity_type', { length: 16 }).notNull().default('gene'),
    entity_slug: varchar('entity_slug', { length: 128 }),
    reviewer: varchar('reviewer', { length: 64 }).notNull().default('curator-agent'),
    score: real('score'),
    verdict: varchar('verdict', { length: 24 }),
    comments: jsonb('comments').$type<string[]>().notNull().default([]),
    changes_made: jsonb('changes_made').$type<Record<string, unknown>>(),
    feedback: varchar('feedback', { length: 32 }),
    model: varchar('model', { length: 64 }),
    created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index('gene_reviews_gene_id_idx').on(table.gene_id),
    index('gene_reviews_entity_idx').on(table.entity_type, table.entity_slug),
  ],
);

export const geneRelations = pgTable(
  'gene_relations',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    source_gene_id: uuid('source_gene_id')
      .notNull()
      .references(() => genes.id),
    target_gene_id: uuid('target_gene_id')
      .notNull()
      .references(() => genes.id),
    relation_type: varchar('relation_type', { length: 24 }).notNull(),
    strength: real('strength').notNull().default(0.5),
    reason: text('reason'),
    created_by: varchar('created_by', { length: 64 }).notNull().default('curator-agent'),
    created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index('gene_relations_source_idx').on(table.source_gene_id),
    index('gene_relations_target_idx').on(table.target_gene_id),
    uniqueIndex('gene_relations_pair_idx').on(
      table.source_gene_id,
      table.target_gene_id,
      table.relation_type,
    ),
  ],
);

export const agentTemplates = pgTable(
  'agent_templates',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    name: varchar('name', { length: 128 }).notNull(),
    slug: varchar('slug', { length: 128 }).notNull(),
    version: varchar('version', { length: 16 }).notNull(),
    description: text('description').notNull().default(''),
    short_description: varchar('short_description', { length: 256 }).notNull().default(''),
    role: varchar('role', { length: 64 }),
    category: varchar('category', { length: 32 }).notNull().default('general'),
    tags: jsonb('tags').$type<string[]>().notNull().default([]),
    icon: varchar('icon', { length: 64 }),
    avatar_url: text('avatar_url'),
    genomes: jsonb('genomes').$type<{ slug: string; version: string }[]>().notNull().default([]),
    genes: jsonb('genes').$type<{ slug: string; version: string }[]>().notNull().default([]),
    compatibility: jsonb('compatibility').$type<string[]>().notNull().default([]),
    install_count: integer('install_count').notNull().default(0),
    avg_rating: real('avg_rating').notNull().default(0),
    author: jsonb('author')
      .$type<{ type: string; id?: string; name: string }>()
      .notNull()
      .default({ type: 'human', name: '' }),
    repository_url: text('repository_url'),
    file_count: integer('file_count').notNull().default(0),
    publisher_id: uuid('publisher_id').references(() => publishers.id),
    is_published: boolean('is_published').notNull().default(false),
    created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    updated_at: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
    deleted_at: timestamp('deleted_at', { withTimezone: true }),
  },
  (table) => [
    uniqueIndex('agent_templates_slug_idx').on(table.slug),
    index('agent_templates_category_idx').on(table.category),
  ],
);

export const agentTemplateVersions = pgTable(
  'agent_template_versions',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    template_id: uuid('template_id')
      .notNull()
      .references(() => agentTemplates.id, { onDelete: 'cascade' }),
    version: varchar('version', { length: 16 }).notNull(),
    genomes: jsonb('genomes').$type<{ slug: string; version: string }[]>().notNull(),
    genes: jsonb('genes').$type<{ slug: string; version: string }[]>().notNull(),
    commit_sha: varchar('commit_sha', { length: 40 }),
    git_tag: varchar('git_tag', { length: 64 }),
    files: jsonb('files').$type<{ path: string; size: number; sha: string }[]>(),
    changelog: text('changelog').notNull().default(''),
    is_latest: boolean('is_latest').notNull().default(false),
    published_at: timestamp('published_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index('agent_template_versions_template_id_idx').on(table.template_id),
    uniqueIndex('agent_template_versions_template_version_idx').on(
      table.template_id,
      table.version,
    ),
  ],
);

export const geneVersions = pgTable(
  'gene_versions',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    gene_id: uuid('gene_id')
      .notNull()
      .references(() => genes.id, { onDelete: 'cascade' }),
    version: varchar('version', { length: 16 }).notNull(),
    manifest: jsonb('manifest').notNull(),
    commit_sha: varchar('commit_sha', { length: 40 }),
    git_tag: varchar('git_tag', { length: 64 }),
    files: jsonb('files').$type<{ path: string; size: number; sha: string }[]>(),
    changelog: text('changelog').notNull().default(''),
    is_latest: boolean('is_latest').notNull().default(false),
    published_at: timestamp('published_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index('gene_versions_gene_id_idx').on(table.gene_id),
    uniqueIndex('gene_versions_gene_version_idx').on(table.gene_id, table.version),
  ],
);
