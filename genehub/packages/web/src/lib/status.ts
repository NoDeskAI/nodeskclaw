import type { BadgeProps } from '@/components/ui/badge';

type StatusConfig = {
  label: string;
  variant: BadgeProps['variant'];
};

const REVIEW_STATUS_MAP: Record<string, StatusConfig> = {
  draft: { label: '草稿', variant: 'secondary' },
  pending: { label: '待审核', variant: 'warning' },
  approve: { label: '已通过', variant: 'success' },
  approved: { label: '已通过', variant: 'success' },
  needs_improvement: { label: '待改进', variant: 'warning' },
  rejected: { label: '已拒绝', variant: 'destructive' },
  flagged: { label: '已标记', variant: 'destructive' },
};

export function getReviewStatusConfig(status: string): StatusConfig {
  return REVIEW_STATUS_MAP[status] ?? { label: status, variant: 'secondary' };
}

const SOURCE_MAP: Record<string, StatusConfig> = {
  local: { label: '本地', variant: 'info' },
  clawhub: { label: 'ClawHub', variant: 'outline' },
  official: { label: '官方', variant: 'default' },
  community: { label: '社区', variant: 'secondary' },
  imported: { label: '导入', variant: 'outline' },
};

export function getSourceConfig(source: string): StatusConfig {
  return SOURCE_MAP[source] ?? { label: source, variant: 'secondary' };
}

export const CATEGORY_COLORS: Record<string, string> = {
  development: 'bg-blue-50 text-blue-700',
  efficiency: 'bg-green-50 text-green-700',
  data: 'bg-purple-50 text-purple-700',
  communication: 'bg-amber-50 text-amber-700',
  security: 'bg-red-50 text-red-700',
  creative: 'bg-pink-50 text-pink-700',
  operations: 'bg-cyan-50 text-cyan-700',
  network: 'bg-orange-50 text-orange-700',
  general: 'bg-gray-50 text-gray-700',
};
