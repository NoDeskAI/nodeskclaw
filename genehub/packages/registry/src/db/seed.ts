import { eq } from 'drizzle-orm';
import { db, schema } from './index.js';

const SEED_GENES = [
  {
    name: '代码审查专家',
    slug: 'code-review',
    version: '1.0.0',
    description: '帮助 Agent 进行深度代码审查，关注安全漏洞、性能问题和代码风格。',
    short_description: '深度代码审查与优化建议',
    category: 'development',
    tags: ['ability'],
    icon: 'search-code',
    source: 'official',
    manifest: {
      slug: 'code-review',
      name: '代码审查专家',
      version: '1.0.0',
      description: '帮助 Agent 进行深度代码审查，关注安全漏洞、性能问题和代码风格。',
      short_description: '深度代码审查与优化建议',
      category: 'development',
      tags: ['ability'],
      icon: 'search-code',
      author: { type: 'human', name: 'NoDeskAI' },
      compatibility: [
        { product: 'openclaw', min_version: '0.5.0' },
        { product: 'nanobot', min_version: '0.1.0' },
      ],
      dependencies: [],
      synergies: ['clean-code', 'test-driven-development'],
      skill: {
        name: 'code-review',
        always: false,
        content: [
          '---',
          'name: code-review',
          'description: 深度代码审查与优化建议',
          'metadata:',
          '  openclaw:',
          '    always: false',
          '  nanobot:',
          '    always: false',
          '---',
          '',
          '你是一位资深代码审查专家。在审查代码时，你应该关注：',
          '',
          '## 审查维度',
          '1. **安全性**：SQL 注入、XSS、敏感信息泄露',
          '2. **性能**：时间复杂度、内存泄漏、N+1 查询',
          '3. **可读性**：命名规范、函数粒度、注释质量',
          '4. **架构**：职责分离、依赖方向、接口设计',
          '',
          '## 输出格式',
          '对每个发现的问题，按以下格式输出：',
          '- 严重程度：Critical / Major / Minor / Suggestion',
          '- 位置：文件名:行号',
          '- 问题描述',
          '- 修复建议（含代码示例）',
        ].join('\n'),
      },
      rules: [],
      config: {
        openclaw: { tool_allow: ['file_read', 'file_write'] },
      },
      mcp_servers: [],
      learning: {
        force_deep_learn: false,
        objectives: [
          '理解代码审查的四个核心维度',
          '掌握安全漏洞的常见模式',
          '形成结构化的审查输出格式',
        ],
        scenarios: [
          {
            title: '审查一个 FastAPI 路由',
            context: '包含 SQL 注入风险的用户输入处理',
            expected_focus: 'security',
          },
        ],
      },
    },
    compatibility: ['openclaw', 'nanobot'],
    dependencies: [],
    synergies: ['clean-code', 'test-driven-development'],
    author: { type: 'human', name: 'NoDeskAI' },
    review_status: 'approved',
    is_published: true,
  },
  {
    name: '记忆管理',
    slug: 'memory',
    version: '1.0.0',
    description: 'Agent 持久化记忆管理能力，支持关键信息提取和长期记忆维护。',
    short_description: 'Agent 持久化记忆管理',
    category: 'efficiency',
    tags: ['ability'],
    icon: 'brain',
    source: 'official',
    manifest: {
      slug: 'memory',
      name: '记忆管理',
      version: '1.0.0',
      description: 'Agent 持久化记忆管理能力，支持关键信息提取和长期记忆维护。',
      short_description: 'Agent 持久化记忆管理',
      category: 'efficiency',
      tags: ['ability'],
      icon: 'brain',
      author: { type: 'human', name: 'NoDeskAI' },
      compatibility: [
        { product: 'openclaw', min_version: '0.5.0' },
        { product: 'nanobot', min_version: '0.1.0' },
      ],
      dependencies: [],
      synergies: [],
      skill: {
        name: 'memory',
        always: true,
        content: [
          '---',
          'name: memory',
          'description: 持久化记忆管理',
          'metadata:',
          '  nanobot:',
          '    always: true',
          '  openclaw:',
          '    always: true',
          '---',
          '',
          '你具备持久化记忆能力。每次对话结束时，你应该：',
          '',
          '1. 提取关键信息（用户偏好、重要决策、待办事项）',
          '2. 将信息写入记忆文件',
          '3. 在新对话开始时回顾记忆上下文',
        ].join('\n'),
      },
      rules: [],
      mcp_servers: [],
    },
    compatibility: ['openclaw', 'nanobot'],
    dependencies: [],
    synergies: [],
    author: { type: 'human', name: 'NoDeskAI' },
    review_status: 'approved',
    is_published: true,
  },
];

async function seed() {
  console.log('Seeding database...');

  for (const gene of SEED_GENES) {
    const existing = await db
      .select({ id: schema.genes.id })
      .from(schema.genes)
      .where(eq(schema.genes.slug, gene.slug));

    if (existing.length > 0) {
      console.log(`  = ${gene.slug} (already exists)`);
      continue;
    }

    const [inserted] = await db
      .insert(schema.genes)
      .values(gene)
      .onConflictDoNothing({ target: schema.genes.slug })
      .returning();

    if (inserted) {
      await db.insert(schema.geneVersions).values({
        gene_id: inserted.id,
        version: gene.version,
        manifest: gene.manifest,
        changelog: '初始版本',
        is_latest: true,
      });
      console.log(`  + ${gene.slug}@${gene.version}`);
    }
  }

  console.log('Seed complete.');
  process.exit(0);
}

seed().catch((err) => {
  console.error('Seed failed:', err);
  process.exit(1);
});
