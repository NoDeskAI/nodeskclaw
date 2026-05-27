/**
 * NoDeskClaw → GeneHub 批量导入脚本
 *
 * 从 NoDeskClaw 的 PostgreSQL 数据库读取基因和基因组数据，
 * 通过 NoDeskClawAdapter 全量同步到 GeneHub。
 *
 * 用法:
 *   NODESKCLAW_DATABASE_URL="postgres://..." tsx src/scripts/import-nodeskclaw.ts [--full] [--limit N]
 *
 * 选项:
 *   --full    强制全量导入（忽略增量时间戳）
 *   --limit N 每批最多处理 N 条（默认不限制）
 */

import { NoDeskClawAdapter } from '../adapters/nodeskclaw/sync.js';

const NODESKCLAW_DATABASE_URL = process.env.NODESKCLAW_DATABASE_URL;

if (!NODESKCLAW_DATABASE_URL) {
  console.error('缺少环境变量 NODESKCLAW_DATABASE_URL');
  console.error(
    '用法: NODESKCLAW_DATABASE_URL="postgres://..." tsx src/scripts/import-nodeskclaw.ts',
  );
  process.exit(1);
}

const args = process.argv.slice(2);
const full = args.includes('--full');
const limitIdx = args.indexOf('--limit');
const limit = limitIdx !== -1 ? Number(args[limitIdx + 1]) : undefined;

async function run() {
  console.log('=== NoDeskClaw → GeneHub 批量导入 ===');
  console.log(`模式: ${full ? '全量导入' : '增量同步'}`);
  if (limit) console.log(`限制: ${limit} 条`);
  console.log();

  const adapter = new NoDeskClawAdapter({ databaseUrl: NODESKCLAW_DATABASE_URL as string });

  const stats = { created: 0, updated: 0, skipped: 0, failed: 0 };
  const failures: { slug: string; message: string }[] = [];
  const startTime = Date.now();

  try {
    for await (const event of adapter.sync({ full, limit })) {
      const key =
        event.kind === 'created'
          ? 'created'
          : event.kind === 'updated'
            ? 'updated'
            : event.kind === 'skipped'
              ? 'skipped'
              : 'failed';
      stats[key]++;

      const icon =
        event.kind === 'created'
          ? '+'
          : event.kind === 'updated'
            ? '~'
            : event.kind === 'skipped'
              ? '='
              : '!';
      const ver = 'version' in event ? `@${event.version}` : '';
      const msg = 'message' in event ? ` (${event.message})` : '';
      console.log(`  ${icon} ${event.slug}${ver}${msg}`);

      if (event.kind === 'failed') {
        failures.push({ slug: event.slug, message: 'message' in event ? event.message : '' });
      }
    }
  } finally {
    await adapter.close();
  }

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const total = stats.created + stats.updated + stats.skipped + stats.failed;

  console.log();
  console.log(`=== 导入完成（${elapsed}s）===`);
  console.log(`  总计: ${total}`);
  console.log(`  新增: ${stats.created}`);
  console.log(`  更新: ${stats.updated}`);
  console.log(`  跳过: ${stats.skipped}`);
  console.log(`  失败: ${stats.failed}`);

  if (failures.length > 0) {
    console.log();
    console.log('失败详情:');
    for (const f of failures) {
      console.log(`  ! ${f.slug}: ${f.message}`);
    }
  }

  process.exit(stats.failed > 0 ? 1 : 0);
}

run().catch((err) => {
  console.error('导入脚本异常:', err);
  process.exit(1);
});
