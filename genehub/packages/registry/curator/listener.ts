import { spawn, type ChildProcess } from 'node:child_process';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import postgres from 'postgres';

const DATABASE_URL =
  process.env.DATABASE_URL || 'postgres://genehub:genehub@localhost:5432/genehub';
const CURATOR_CMD = process.env.CURATOR_CMD || 'opencode';
const CURATOR_CWD = process.env.CURATOR_CWD || dirname(fileURLToPath(import.meta.url));
const HARD_TIMEOUT_MS = 90_000;
const IDLE_TIMEOUT_MS = 45_000;
const MAX_RETRIES = 2;

const TAG = '[curator]';
const sql = postgres(DATABASE_URL);

const queue: string[] = [];
let processing = false;

type OpenCodeEvent = {
  type: string;
  sessionID?: string;
  part?: {
    type?: string;
    text?: string;
    tool?: string;
    reason?: string;
    state?: { status?: string };
  };
};

const REVIEW_ACTIONS = ['post_review', 'approve_gene', 'flag_for_deletion', 'review_genome', 'review_template'];

const RETRY_PROMPTS = [
  '你必须自己做决策。立刻调用 post_review 提交评分和详细评语（verdict 可选: approved / rejected / needs_improvement / flagged）。post_review 会同时更新审核状态，无需再调 approve_gene。',
  '最后一次机会。直接调用 post_review(score, verdict, comments)。verdict 填 approved / rejected / needs_improvement / flagged 之一。不要输出文字，直接调用工具。',
];

function buildPrompt(event: { type: string; slug: string; source: string }): string | null {
  switch (event.type) {
    case 'gene.created':
    case 'gene.updated':
      return `审核基因 ${event.slug}，来源: ${event.source}。使用 get_gene 获取详情，用 find_similar 检查重复，评估实用性、完整性、安全性。然后调用 post_review 提交评分和详细评语。verdict 根据质量选择: approved(>=7分) / needs_improvement(4-6分) / rejected(<4分) / flagged(垃圾/安全风险)。post_review 会自动更新审核状态，无需额外调用 approve_gene。`;
    case 'genome.created':
    case 'genome.updated':
      return `审核基因组 ${event.slug}，来源: ${event.source}。使用 get_genome 获取详情，检查基因组合理性、基因引用完整性、描述质量，然后调用 review_genome 提交审核结论。`;
    case 'template.created':
    case 'template.updated':
      return `审核 AI 员工模板 ${event.slug}，来源: ${event.source}。使用 get_template 获取详情，检查模板角色定义、基因组引用完整性、配置合理性，然后调用 review_template 提交审核结论。`;
    default:
      return null;
  }
}

async function listen() {
  console.log('[listener] Connecting to gene_events channel...');

  await sql.listen('gene_events', (payload) => {
    try {
      const event = JSON.parse(payload);
      console.log(`[listener] Received: ${event.type} — ${event.slug}`);

      const prompt = buildPrompt(event);
      if (prompt) {
        enqueue(prompt);
      }
    } catch (err) {
      console.error('[listener] Failed to parse event:', err);
    }
  });

  console.log('[listener] Listening for gene_events...');
}

function enqueue(prompt: string) {
  queue.push(prompt);
  console.log(`[listener] Queued (${queue.length} pending): ${prompt}`);
  processNext();
}

function forceKill(child: ChildProcess) {
  if (!child.pid) return;
  try {
    // Kill the entire process group (opencode + its MCP child processes)
    process.kill(-child.pid, 'SIGTERM');
  } catch {
    child.kill('SIGTERM');
  }
  setTimeout(() => {
    if (!child.killed) {
      try {
        process.kill(-child.pid!, 'SIGKILL');
      } catch {
        child.kill('SIGKILL');
      }
    }
  }, 5_000);
}

function isReviewAction(toolName: string): boolean {
  const bare = toolName.replace(/^genehub_/, '');
  return REVIEW_ACTIONS.includes(bare);
}

function processNext() {
  if (processing || queue.length === 0) return;
  processing = true;
  const prompt = queue.shift()!;
  runCurator(prompt, null, 0);
}

function runCurator(prompt: string, sessionId: string | null, attempt: number) {
  const isRetry = attempt > 0;
  const label = isRetry ? `${TAG} [retry ${attempt}]` : TAG;
  console.log(`${label} Running (${queue.length} remaining): ${prompt}`);

  const args = ['run', '--format', 'json', '--dir', CURATOR_CWD];
  if (sessionId) {
    args.push('--session', sessionId, '--continue');
  }
  args.push(prompt);

  const calledTools: string[] = [];
  let capturedSessionId: string | null = sessionId;
  let lastActivityMs = Date.now();
  let buffer = '';

  const child = spawn(CURATOR_CMD, args, {
    cwd: CURATOR_CWD,
    env: { ...process.env },
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true,
  });

  function parseEvents(raw: string) {
    buffer += raw;
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const event: OpenCodeEvent = JSON.parse(line);
        handleEvent(event);
      } catch {
        if (line.trim()) console.log(`${label} ${line}`);
      }
    }
  }

  function handleEvent(event: OpenCodeEvent) {
    lastActivityMs = Date.now();

    if (event.sessionID && !capturedSessionId) {
      capturedSessionId = event.sessionID;
    }

    switch (event.type) {
      case 'text':
        if (event.part?.text) {
          for (const l of event.part.text.split('\n')) {
            if (l.trim()) console.log(`${label} ${l}`);
          }
        }
        break;

      case 'tool_use': {
        const toolName = event.part?.tool ?? 'unknown';
        calledTools.push(toolName);
        const status = event.part?.state?.status ?? '';
        console.log(`${label} tool: ${toolName} (${status})`);
        break;
      }

      case 'step_finish': {
        const reason = event.part?.reason;
        console.log(`${label} step done (reason: ${reason})`);

        if (reason === 'stop' || reason === 'end_turn') {
          const hasAction = calledTools.some(isReviewAction);
          if (!hasAction) {
            console.warn(`${label} Model stopped without review action, killing for retry...`);
            forceKill(child);
          }
        }
        break;
      }
    }
  }

  child.stdout.on('data', (chunk: Buffer) => {
    lastActivityMs = Date.now();
    parseEvents(chunk.toString());
  });

  child.stderr.on('data', (chunk: Buffer) => {
    lastActivityMs = Date.now();
    for (const line of chunk.toString().split('\n')) {
      if (line.trim() && !line.includes('getConfigContext')) {
        console.error(`${label} [stderr] ${line}`);
      }
    }
  });

  const hardTimer = setTimeout(() => {
    console.error(`${label} Hard timeout (${HARD_TIMEOUT_MS / 1000}s), killing...`);
    forceKill(child);
  }, HARD_TIMEOUT_MS);

  const idleChecker = setInterval(() => {
    const idleMs = Date.now() - lastActivityMs;
    if (idleMs > IDLE_TIMEOUT_MS) {
      console.error(`${label} Idle timeout (${Math.round(idleMs / 1000)}s no output), killing...`);
      forceKill(child);
    }
  }, 5_000);

  function cleanup(code: number | null) {
    clearTimeout(hardTimer);
    clearInterval(idleChecker);

    const hasAction = calledTools.some(isReviewAction);
    const toolList = calledTools.length > 0 ? calledTools.join(', ') : 'none';

    if (hasAction) {
      console.log(`${label} OK (code=${code}, tools=[${toolList}])`);
      processing = false;
      processNext();
      return;
    }

    // Retry via session continuation with escalating prompts
    if (attempt < MAX_RETRIES && capturedSessionId) {
      const retryPrompt = RETRY_PROMPTS[Math.min(attempt, RETRY_PROMPTS.length - 1)];
      console.warn(
        `${label} INCOMPLETE (code=${code}, tools=[${toolList}]) — retry ${attempt + 1}/${MAX_RETRIES} via session ${capturedSessionId}`,
      );
      runCurator(retryPrompt, capturedSessionId, attempt + 1);
    } else {
      console.error(
        `${label} FAILED after ${attempt + 1} attempts (code=${code}, tools=[${toolList}])`,
      );
      processing = false;
      processNext();
    }
  }

  child.on('close', (code) => cleanup(code));

  child.on('error', (err) => {
    clearTimeout(hardTimer);
    clearInterval(idleChecker);
    console.error(`${label} Spawn error: ${err.message}`);
    processing = false;
    processNext();
  });
}

listen().catch((err) => {
  console.error('[listener] Fatal error:', err);
  process.exit(1);
});
