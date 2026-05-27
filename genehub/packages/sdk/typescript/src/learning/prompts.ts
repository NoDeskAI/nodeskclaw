import type { LearningTask } from './task.js';

export function generateLearningTaskMarkdown(task: LearningTask): string {
  const lines: string[] = [];

  lines.push('---');
  lines.push(`task_id: ${task.task_id}`);
  lines.push(`mode: ${task.mode}`);
  lines.push(`gene_slug: ${task.gene_slug}`);
  lines.push(`gene_version: ${task.gene_version}`);
  lines.push(`callback_path: ${task.callback_path}`);
  lines.push(`created_at: ${task.created_at}`);
  lines.push('---');
  lines.push('');
  lines.push(`# 学习任务: ${task.gene_name}`);
  lines.push('');
  lines.push(`> 类别: ${task.gene_meta.category} | 版本: ${task.gene_version}`);
  lines.push('');
  lines.push(`${task.gene_meta.description}`);
  lines.push('');

  if (task.learning?.objectives?.length) {
    lines.push('## 学习目标');
    lines.push('');
    for (const obj of task.learning.objectives) {
      lines.push(`- [ ] ${obj}`);
    }
    lines.push('');
  }

  if (task.learning?.scenarios?.length) {
    lines.push('## 练习场景');
    lines.push('');
    for (let i = 0; i < task.learning.scenarios.length; i++) {
      const s = task.learning.scenarios[i];
      lines.push(`### 场景 ${i + 1}: ${s.title}`);
      lines.push('');
      lines.push(`**上下文**: ${s.context}`);
      lines.push('');
      lines.push(`**预期关注点**: ${s.expected_focus}`);
      lines.push('');
      lines.push('**你的练习**:');
      lines.push('');
      lines.push('(请在此处记录你对该场景的分析和应对方案)');
      lines.push('');
    }
  }

  lines.push('## 技能原文');
  lines.push('');
  lines.push('```');
  lines.push(task.gene_content);
  lines.push('```');
  lines.push('');
  lines.push('## 完成学习');
  lines.push('');
  lines.push('学习完成后，请**严格按顺序**执行以下操作：');
  lines.push('');
  lines.push(`1. 在 \`${task.callback_path}\` 创建学习结果文件`);
  lines.push('2. 包含 YAML front matter（task_id, decision, self_eval）');
  lines.push('3. 如果你个性化了技能内容，将修改后的 SKILL.md 内容放在正文中');
  lines.push(
    `4. **删除本任务文件** — 确认结果文件写入成功后，立即删除 \`learning-tasks/${task.gene_slug}.md\`（即本文件），防止下次会话重复处理`,
  );
  lines.push('');
  lines.push('### 结果文件模板');
  lines.push('');
  lines.push('```markdown');
  lines.push('---');
  lines.push(`task_id: ${task.task_id}`);
  lines.push(`gene_slug: ${task.gene_slug}`);
  lines.push(`mode: ${task.mode}`);
  lines.push('decision: learned  # direct_install | learned | failed');
  lines.push('self_eval: 0.8     # 0.0 - 1.0 自评分');
  lines.push('reason: "我已理解并个性化了该技能"');
  lines.push('---');
  lines.push('');
  lines.push('(如果 decision 为 learned，在此放入个性化后的 SKILL.md 内容)');
  lines.push('```');

  return lines.join('\n');
}

export function generateForgetTaskMarkdown(
  slug: string,
  name: string,
  skillContent: string,
  callbackPath: string,
): string {
  const taskId = `forget-${slug}-${Date.now()}`;
  return [
    '---',
    `task_id: ${taskId}`,
    'mode: forget',
    `gene_slug: ${slug}`,
    `callback_path: ${callbackPath}`,
    `created_at: ${new Date().toISOString()}`,
    '---',
    '',
    `# 遗忘任务: ${name}`,
    '',
    '请回顾你使用该技能的经验，然后决定：',
    '',
    '- **forgotten**: 完全遗忘，清除所有痕迹',
    '- **simplified**: 保留精华，简化为更短的技能描述',
    '',
    '## 当前技能内容',
    '',
    '```',
    skillContent,
    '```',
    '',
    `请将遗忘结果写入 \`${callbackPath}\``,
    '',
    `**结果文件写入成功后，立即删除 \`learning-tasks/${slug}.md\`（即本文件），防止下次会话重复处理。**`,
  ].join('\n');
}
