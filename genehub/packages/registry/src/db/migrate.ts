import fs from 'node:fs/promises';
import path from 'node:path';
import postgres from 'postgres';

const DATABASE_URL =
  process.env.DATABASE_URL || 'postgres://genehub:genehub@localhost:5432/genehub';
const MIGRATIONS_DIR = process.env.GENEHUB_MIGRATIONS_DIR || './drizzle';

const sql = postgres(DATABASE_URL, { max: 1 });

async function listMigrationFiles(): Promise<string[]> {
  const entries = await fs.readdir(MIGRATIONS_DIR);
  return entries.filter((entry) => entry.endsWith('.sql')).sort();
}

async function markExistingSchemaAsApplied(files: string[]): Promise<boolean> {
  const [schemaState] = await sql<{ has_schema: string | null }[]>`
    SELECT to_regclass('public.genes')::text AS has_schema
  `;
  const applied = await sql<{ id: string }[]>`
    SELECT id FROM genehub_meta.schema_migrations LIMIT 1
  `;

  if (!schemaState?.has_schema || applied.length > 0) {
    return false;
  }

  for (const file of files) {
    await sql`
      INSERT INTO genehub_meta.schema_migrations (id)
      VALUES (${file})
      ON CONFLICT (id) DO NOTHING
    `;
  }
  console.log(`GeneHub schema already exists, marked ${files.length} migrations as applied.`);
  return true;
}

async function runMigrationFile(file: string): Promise<void> {
  const fullPath = path.join(MIGRATIONS_DIR, file);
  const content = await fs.readFile(fullPath, 'utf8');
  const statements = content
    .split('--> statement-breakpoint')
    .map((statement) => statement.trim())
    .filter(Boolean);

  await sql.begin(async (tx) => {
    for (const statement of statements) {
      await tx.unsafe(statement);
    }
    await tx.unsafe(
      'INSERT INTO genehub_meta.schema_migrations (id) VALUES ($1) ON CONFLICT (id) DO NOTHING',
      [file],
    );
  });
}

async function main(): Promise<void> {
  await sql`CREATE SCHEMA IF NOT EXISTS genehub_meta`;
  await sql`
    CREATE TABLE IF NOT EXISTS genehub_meta.schema_migrations (
      id text PRIMARY KEY,
      applied_at timestamptz NOT NULL DEFAULT now()
    )
  `;

  const files = await listMigrationFiles();
  if (await markExistingSchemaAsApplied(files)) {
    return;
  }

  const appliedRows = await sql<{ id: string }[]>`
    SELECT id FROM genehub_meta.schema_migrations
  `;
  const applied = new Set(appliedRows.map((row) => row.id));

  for (const file of files) {
    if (applied.has(file)) {
      continue;
    }
    console.log(`Applying GeneHub migration ${file}`);
    await runMigrationFile(file);
  }
  console.log('GeneHub database migrations completed.');
}

main()
  .catch((error) => {
    console.error('GeneHub database migration failed:', error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await sql.end({ timeout: 5 });
  });
