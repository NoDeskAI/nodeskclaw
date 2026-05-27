import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import {
  getGenome,
  listGenomes as listGenomesMcp,
  suggestGenome,
  validateGenome,
} from './tools/genome.js';
import {
  mergeGenes,
  updateGeneCategory,
  updateGeneDescription,
  updateGeneSynergies,
} from './tools/manage.js';
import {
  evaluateInContext,
  findSimilar,
  getGene,
  getLibraryStats,
  listGenes,
  searchGenes,
} from './tools/query.js';
import {
  approveGene,
  flagForDeletion,
  postReview,
  reviewGenome,
  reviewTemplate,
} from './tools/review.js';
import {
  getTemplate,
  listTemplates as listTemplatesMcp,
  suggestTemplate,
} from './tools/template.js';

export function createMcpServer() {
  const server = new McpServer({
    name: 'genehub',
    version: '1.0.0',
  });

  // --- Query tools ---

  server.tool(
    'list_genes',
    '列出基因库中的基因，支持按分类、来源、审核状态过滤',
    {
      category: z.string().optional().describe('按分类过滤'),
      source: z.string().optional().describe('按来源过滤: official, clawhub, evomap, community'),
      review_status: z
        .string()
        .optional()
        .describe('按审核状态过滤: draft, pending, approved, rejected, flagged'),
      ai_enriched: z.boolean().optional().describe('是否已被 AI 处理'),
      page: z.number().optional().describe('页码'),
      page_size: z.number().optional().describe('每页数量'),
    },
    async (args) => {
      const result = await listGenes(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'get_gene',
    '获取基因完整详情，包括已有的点评和关联关系',
    { slug: z.string().describe('基因 slug') },
    async (args) => {
      const result = await getGene(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'search_genes',
    '关键词搜索基因（名称、描述、slug）',
    {
      query: z.string().describe('搜索关键词'),
      limit: z.number().optional().describe('返回数量上限'),
    },
    async (args) => {
      const result = await searchGenes(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'find_similar',
    '查找与指定基因相似的候选基因（同分类 + tag 重叠度）',
    { slug: z.string().describe('基因 slug') },
    async (args) => {
      const result = await findSimilar(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool('get_library_stats', '获取基因库总览统计', {}, async () => {
    const result = await getLibraryStats();
    return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
  });

  server.tool(
    'evaluate_in_context',
    '上下文评估：返回基因详情 + 同类基因对比 + 历史点评 + 被覆盖的决策，供决策参考',
    { slug: z.string().describe('基因 slug') },
    async (args) => {
      const result = await evaluateInContext(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  // --- Genome tools ---

  server.tool(
    'list_genomes',
    '列出基因组，支持按分类和关键词过滤',
    {
      category: z.string().optional().describe('按分类过滤'),
      q: z.string().optional().describe('搜索关键词'),
      page: z.number().optional().describe('页码'),
      page_size: z.number().optional().describe('每页数量'),
    },
    async (args) => {
      const result = await listGenomesMcp(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'get_genome',
    '获取基因组完整详情，包括版本历史',
    { slug: z.string().describe('基因组 slug') },
    async (args) => {
      const result = await getGenome(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'suggest_genome',
    '根据需求描述推荐合适的基因组',
    {
      needs: z.string().describe('需求描述，例如"全栈 TypeScript 项目" 或 "React Native 移动应用"'),
      product: z.string().optional().describe('目标产品/平台'),
    },
    async (args) => {
      const result = await suggestGenome(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'validate_genome',
    '校验一组基因能否组成合法的基因组：检查基因存在性、发布状态、冲突关系',
    { gene_slugs: z.array(z.string()).describe('待校验的基因 slug 列表') },
    async (args) => {
      const result = await validateGenome(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  // --- Template tools ---

  server.tool(
    'list_templates',
    '列出 AI 员工模板，支持按分类、角色和关键词过滤',
    {
      category: z.string().optional().describe('按分类过滤'),
      role: z.string().optional().describe('按角色过滤'),
      q: z.string().optional().describe('搜索关键词'),
      page: z.number().optional().describe('页码'),
      page_size: z.number().optional().describe('每页数量'),
    },
    async (args) => {
      const result = await listTemplatesMcp(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'get_template',
    '获取 AI 员工模板完整详情，包括版本历史',
    { slug: z.string().describe('模板 slug') },
    async (args) => {
      const result = await getTemplate(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'suggest_template',
    '根据需求描述推荐合适的 AI 员工模板',
    {
      needs: z.string().describe('需求描述，例如"营销专员" 或 "全栈开发工程师"'),
      product: z.string().optional().describe('目标产品/平台'),
    },
    async (args) => {
      const result = await suggestTemplate(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  // --- Manage tools ---

  server.tool(
    'update_gene_category',
    '重新分类基因（修改 category 和 tags），需提供理由',
    {
      slug: z.string().describe('基因 slug'),
      category: z.string().describe('新的分类'),
      tags: z.array(z.string()).optional().describe('新的标签列表'),
      reason: z.string().describe('变更理由'),
    },
    async (args) => {
      const result = await updateGeneCategory(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'update_gene_description',
    '改善基因的描述文本',
    {
      slug: z.string().describe('基因 slug'),
      description: z.string().optional().describe('新的完整描述'),
      short_description: z.string().optional().describe('新的简短描述'),
    },
    async (args) => {
      const result = await updateGeneDescription(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'update_gene_synergies',
    '设置两个基因之间的关联关系',
    {
      slug: z.string().describe('源基因 slug'),
      target_slug: z.string().describe('目标基因 slug'),
      relation_type: z
        .enum(['synergy', 'conflict', 'extends', 'replaces'])
        .describe('关系类型: synergy(协同) / conflict(冲突) / extends(扩展) / replaces(替代)'),
      strength: z.number().min(0).max(1).optional().describe('关系强度 0-1'),
      reason: z.string().optional().describe('关系说明'),
    },
    async (args) => {
      const result = await updateGeneSynergies(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'merge_genes',
    '合并重复基因：将 source 基因标记删除并指向 target 基因，合并安装量和协同关系',
    {
      source_slug: z.string().describe('被合并的基因 slug（将被标记删除）'),
      target_slug: z.string().describe('合并目标基因 slug（保留）'),
      reason: z.string().describe('合并理由'),
    },
    async (args) => {
      const result = await mergeGenes(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  // --- Review tools ---

  server.tool(
    'post_review',
    '发布基因点评（评分 + 评语），会出现在基因的评论区',
    {
      slug: z.string().describe('基因 slug'),
      score: z.number().min(0).max(10).describe('评分 0-10'),
      verdict: z.enum(['approve', 'reject', 'needs_improvement', 'flagged']).describe('审核结论'),
      comments: z.array(z.string()).describe('评语列表，每条评语对应一个评论'),
      model: z.string().optional().describe('使用的 AI 模型'),
    },
    async (args) => {
      const result = await postReview(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'flag_for_deletion',
    '标记基因待删除（需人工确认才会真正删除），会将 review_status 设为 flagged',
    {
      slug: z.string().describe('基因 slug'),
      reason: z.string().describe('标记删除的理由'),
      model: z.string().optional().describe('使用的 AI 模型'),
    },
    async (args) => {
      const result = await flagForDeletion(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'approve_gene',
    '审核通过基因，将 review_status 设为 approved',
    {
      slug: z.string().describe('基因 slug'),
      model: z.string().optional().describe('使用的 AI 模型'),
    },
    async (args) => {
      const result = await approveGene(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'review_genome',
    '审核基因组：评分 + 评语，verdict 为 approve 时发布',
    {
      slug: z.string().describe('基因组 slug'),
      score: z.number().min(0).max(10).describe('评分 0-10'),
      verdict: z.enum(['approve', 'reject', 'needs_improvement']).describe('审核结论'),
      comments: z.array(z.string()).describe('评语列表'),
      model: z.string().optional().describe('使用的 AI 模型'),
    },
    async (args) => {
      const result = await reviewGenome(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    'review_template',
    '审核 AI 员工模板：评分 + 评语，verdict 为 approve 时发布',
    {
      slug: z.string().describe('模板 slug'),
      score: z.number().min(0).max(10).describe('评分 0-10'),
      verdict: z.enum(['approve', 'reject', 'needs_improvement']).describe('审核结论'),
      comments: z.array(z.string()).describe('评语列表'),
      model: z.string().optional().describe('使用的 AI 模型'),
    },
    async (args) => {
      const result = await reviewTemplate(args);
      return { content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }] };
    },
  );

  return server;
}
