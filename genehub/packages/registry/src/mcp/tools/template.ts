import { and, desc, eq, isNull, sql } from 'drizzle-orm';
import { db, schema } from '../../db/index.js';

const { agentTemplates, agentTemplateVersions } = schema;

export async function listTemplates(args: {
  category?: string;
  role?: string;
  q?: string;
  page?: number;
  page_size?: number;
}) {
  const page = Math.max(1, args.page ?? 1);
  const pageSize = Math.min(50, Math.max(1, args.page_size ?? 20));
  const offset = (page - 1) * pageSize;

  const conditions = [isNull(agentTemplates.deleted_at), eq(agentTemplates.is_published, true)];

  if (args.category) conditions.push(eq(agentTemplates.category, args.category));
  if (args.role) conditions.push(eq(agentTemplates.role, args.role));
  if (args.q) {
    const term = `%${args.q}%`;
    conditions.push(
      sql`(${agentTemplates.name} ILIKE ${term} OR ${agentTemplates.slug} ILIKE ${term} OR ${agentTemplates.short_description} ILIKE ${term} OR ${agentTemplates.role} ILIKE ${term})`,
    );
  }

  const where = and(...conditions);

  const [items, countResult] = await Promise.all([
    db
      .select({
        slug: agentTemplates.slug,
        name: agentTemplates.name,
        version: agentTemplates.version,
        short_description: agentTemplates.short_description,
        role: agentTemplates.role,
        category: agentTemplates.category,
        tags: agentTemplates.tags,
        install_count: agentTemplates.install_count,
        avg_rating: agentTemplates.avg_rating,
        genomes: agentTemplates.genomes,
        genes: agentTemplates.genes,
      })
      .from(agentTemplates)
      .where(where)
      .orderBy(desc(agentTemplates.install_count))
      .limit(pageSize)
      .offset(offset),
    db.select({ count: sql<number>`count(*)` }).from(agentTemplates).where(where),
  ]);

  return { items, total: Number(countResult[0]?.count ?? 0), page, pageSize };
}

export async function getTemplate(args: { slug: string }) {
  const result = await db
    .select()
    .from(agentTemplates)
    .where(and(eq(agentTemplates.slug, args.slug), isNull(agentTemplates.deleted_at)));

  if (result.length === 0) return { error: `AI 员工模板 ${args.slug} 不存在` };

  const template = result[0];
  const versions = await db
    .select({
      version: agentTemplateVersions.version,
      is_latest: agentTemplateVersions.is_latest,
    })
    .from(agentTemplateVersions)
    .where(eq(agentTemplateVersions.template_id, template.id))
    .orderBy(desc(agentTemplateVersions.published_at))
    .limit(10);

  return { template, versions };
}

export async function suggestTemplate(args: { needs: string; product?: string }) {
  const term = `%${args.needs}%`;
  const conditions = [
    isNull(agentTemplates.deleted_at),
    eq(agentTemplates.is_published, true),
    sql`(${agentTemplates.name} ILIKE ${term} OR ${agentTemplates.short_description} ILIKE ${term} OR ${agentTemplates.description} ILIKE ${term} OR ${agentTemplates.role} ILIKE ${term} OR ${agentTemplates.tags}::text ILIKE ${term})`,
  ];

  const candidates = await db
    .select({
      slug: agentTemplates.slug,
      name: agentTemplates.name,
      version: agentTemplates.version,
      short_description: agentTemplates.short_description,
      role: agentTemplates.role,
      category: agentTemplates.category,
      tags: agentTemplates.tags,
      install_count: agentTemplates.install_count,
      avg_rating: agentTemplates.avg_rating,
      genomes: agentTemplates.genomes,
      genes: agentTemplates.genes,
    })
    .from(agentTemplates)
    .where(and(...conditions))
    .orderBy(desc(agentTemplates.avg_rating), desc(agentTemplates.install_count))
    .limit(5);

  if (candidates.length === 0) {
    return { suggestions: [], hint: '没有找到匹配的 AI 员工模板，尝试更宽泛的描述' };
  }

  return { suggestions: candidates };
}
