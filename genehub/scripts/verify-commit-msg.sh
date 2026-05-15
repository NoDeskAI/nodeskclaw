#!/usr/bin/env bash
#
# commit message 格式校验
# 格式: <type>(<scope>): <subject>
# 允许: Merge commit、Revert commit

MSG=$(head -1 "$1")

PATTERN='^(feat|fix|docs|style|refactor|perf|test|chore|revert|build)(\(.+\))?: .+'
MERGE_PATTERN='^Merge '
REVERT_PATTERN='^Revert "'

if echo "$MSG" | grep -qE "$PATTERN"; then
  exit 0
elif echo "$MSG" | grep -qE "$MERGE_PATTERN"; then
  exit 0
elif echo "$MSG" | grep -qE "$REVERT_PATTERN"; then
  exit 0
fi

echo ""
echo "commit message 不符合规范!"
echo ""
echo "  格式: <type>(<scope>): <subject>"
echo "  类型: feat | fix | docs | style | refactor | perf | test | chore | revert | build"
echo "  scope: 选填 (registry / cli / sdk / protocol / genes 等)"
echo "  subject: 中文, 50 字以内"
echo ""
echo "  示例: feat(registry): 基因搜索 API 支持标签过滤"
echo "  当前: $MSG"
echo ""
exit 1
