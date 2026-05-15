/**
 * Migration script: creates Gitea repos for existing genes that
 * have manifest content embedded in DB but no repository_url.
 *
 * Usage: tsx src/scripts/migrate-genes-to-gitea.ts
 */
import { and, eq, isNull } from 'drizzle-orm';
import { stringify } from 'yaml';
import { db, schema } from '../db/index.js';
import * as gitea from '../services/gitea-service.js';

const { genes, geneVersions } = schema;

async function main() {
  console.log('Checking Gitea availability...');
  const isReady = await gitea.isGiteaAvailable();
  if (!isReady) {
    console.error('ERROR: Gitea is not available. Start it first.');
    process.exit(1);
  }

  await gitea.ensureOrg();

  const genesWithoutRepo = await db
    .select()
    .from(genes)
    .where(and(isNull(genes.repository_url), isNull(genes.deleted_at)));

  console.log(`Found ${genesWithoutRepo.length} genes without Gitea repo.`);

  let migrated = 0;
  let skipped = 0;

  for (const gene of genesWithoutRepo) {
    const slug = gene.slug;
    console.log(`\nProcessing: ${slug} v${gene.version}...`);

    try {
      const manifest = gene.manifest as Record<string, unknown>;
      const skill = manifest.skill as
        | { content?: string; name?: string; file?: string }
        | undefined;

      const files: Record<string, string> = {};

      const yamlManifest = { ...manifest };
      if (yamlManifest.skill && typeof yamlManifest.skill === 'object') {
        const s = { ...yamlManifest.skill } as Record<string, unknown>;
        delete s.content;
        yamlManifest.skill = s;
      }
      files['gene.yaml'] = stringify(yamlManifest);

      if (skill?.content) {
        files['SKILL.md'] = skill.content;
      }

      const hasRepo = await gitea.repoExists(slug);
      if (!hasRepo) {
        await gitea.createRepo(slug, gene.short_description || gene.description);
      }

      const tag = `v${gene.version}`;
      const result = await gitea.uploadFiles(slug, files, `chore: migrate from DB (${tag})`);

      try {
        await gitea.createTag(slug, tag, result.sha);
      } catch {
        console.log(`  Tag ${tag} may already exist, skipping.`);
      }

      const repoUrl = gitea.getRepoUrl(slug);
      const fileList = Object.entries(files).map(([path, content]) => ({
        path,
        size: Buffer.byteLength(content, 'utf-8'),
        sha: '',
      }));

      await db
        .update(genes)
        .set({
          repository_url: repoUrl,
          file_count: fileList.length,
          updated_at: new Date(),
        })
        .where(eq(genes.id, gene.id));

      await db
        .update(geneVersions)
        .set({
          commit_sha: result.sha,
          git_tag: tag,
          files: fileList,
        })
        .where(and(eq(geneVersions.gene_id, gene.id), eq(geneVersions.version, gene.version)));

      console.log(`  OK: ${slug} -> ${repoUrl} (${fileList.length} files)`);
      migrated++;
    } catch (err) {
      console.error(`  FAIL: ${slug} - ${err instanceof Error ? err.message : err}`);
      skipped++;
    }
  }

  console.log(`\nMigration complete: ${migrated} migrated, ${skipped} skipped.`);
  process.exit(0);
}

main();
