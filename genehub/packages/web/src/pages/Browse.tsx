import { Globe, Search, Shield } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { type FederatedGeneItem, federatedSearch, type Gene, listGenes } from '@/api/client';
import CategoryNav from '@/components/CategoryNav';
import FederatedSearchCard from '@/components/FederatedSearchCard';
import GeneCard from '@/components/GeneCard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/hooks/useAuth';

const REVIEW_STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'needs_improvement', label: '待改进' },
  { value: 'flagged', label: '已标记删除' },
  { value: 'rejected', label: '已拒绝' },
];

const SORT_OPTIONS = [
  { value: 'newest', label: '最新' },
  { value: 'popular', label: '最热' },
  { value: 'rating', label: '评分' },
];

const TAG_OPTIONS = [
  { value: '', label: '全部标签' },
  { value: 'ability', label: 'ability' },
  { value: 'personality', label: 'personality' },
  { value: 'knowledge', label: 'knowledge' },
  { value: 'tool', label: 'tool' },
];

const COMPAT_OPTIONS = [
  { value: '', label: '全部平台' },
  { value: 'openclaw', label: 'OpenClaw' },
  { value: 'nanobot', label: 'NanoBot' },
  { value: 'deskclaw', label: 'DeskClaw' },
  { value: 'generic', label: 'Generic' },
];

export default function Browse() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [genes, setGenes] = useState<Gene[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const { isAdmin } = useAuth();

  const [listError, setListError] = useState<string | null>(null);
  const [federatedMode, setFederatedMode] = useState(false);
  const [federatedItems, setFederatedItems] = useState<FederatedGeneItem[]>([]);
  const [federatedSources, setFederatedSources] = useState<{ local: number; clawhub: number }>({
    local: 0,
    clawhub: 0,
  });

  const q = searchParams.get('q') || '';
  const category = searchParams.get('category') || '';
  const tag = searchParams.get('tag') || '';
  const compatibility = searchParams.get('compatibility') || '';
  const sort = searchParams.get('sort') || 'newest';
  const reviewStatus = searchParams.get('review_status') || '';
  const page = Number(searchParams.get('page')) || 1;

  const updateParam = useCallback(
    (key: string, value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== 'page') next.delete('page');
        return next;
      });
    },
    [setSearchParams],
  );

  useEffect(() => {
    if (federatedMode && q.trim()) {
      setLoading(true);
      setListError(null);
      federatedSearch({ q, category: category || undefined, limit: 20 })
        .then((result) => {
          setFederatedItems(result.items);
          setFederatedSources(result.sources);
          setTotal(result.total);
          setTotalPages(1);
        })
        .catch(() => {
          setFederatedItems([]);
          setFederatedSources({ local: 0, clawhub: 0 });
          setTotal(0);
          setTotalPages(0);
          setListError('搜索加载失败，请刷新重试');
        })
        .finally(() => setLoading(false));
      return;
    }

    setLoading(true);
    setListError(null);
    listGenes({
      q: q || undefined,
      category: category || undefined,
      compatibility: compatibility || undefined,
      tag: tag || undefined,
      sort,
      page,
      page_size: 12,
      ...(isAdmin && { include_unpublished: true }),
      ...(isAdmin && reviewStatus && { review_status: reviewStatus }),
    })
      .then((data) => {
        setGenes(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
      })
      .catch(() => {
        setGenes([]);
        setTotal(0);
        setTotalPages(0);
        setListError('列表加载失败，请刷新重试');
      })
      .finally(() => setLoading(false));
  }, [q, category, tag, compatibility, sort, page, federatedMode, isAdmin, reviewStatus]);

  const showFederated = federatedMode && q.trim();

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">{q ? `搜索: "${q}"` : '浏览基因'}</h1>
        <p className="text-muted text-sm">
          {total} 个基因
          {showFederated && (
            <span className="ml-2">
              (本地 {federatedSources.local} · ClawHub {federatedSources.clawhub})
            </span>
          )}
        </p>
      </div>

      {/* Filters */}
      <div className="space-y-4 mb-6">
        {/* Search + Federated toggle */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
            <Input
              value={q}
              onChange={(e) => updateParam('q', e.target.value)}
              placeholder="搜索基因..."
              className="pl-9"
            />
          </div>
          <Button
            variant={federatedMode ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFederatedMode((v) => !v)}
            className="gap-1.5 shrink-0"
          >
            <Globe className="w-3.5 h-3.5" />
            联邦搜索
          </Button>
        </div>

        {/* Category + Sort + Tag + Compat */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <CategoryNav active={category} onChange={(c) => updateParam('category', c)} />
          <div className="flex items-center gap-2">
            <select
              value={tag}
              onChange={(e) => updateParam('tag', e.target.value)}
              className="px-3 py-2 rounded-lg border border-border text-sm bg-surface focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              {TAG_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <select
              value={compatibility}
              onChange={(e) => updateParam('compatibility', e.target.value)}
              className="px-3 py-2 rounded-lg border border-border text-sm bg-surface focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              {COMPAT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <select
              value={sort}
              onChange={(e) => updateParam('sort', e.target.value)}
              className="px-3 py-2 rounded-lg border border-border text-sm bg-surface focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Admin filters */}
        {isAdmin && (
          <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg">
            <Shield className="w-4 h-4 text-amber-600" />
            <span className="text-xs font-medium text-amber-700">管理员</span>
            <select
              value={reviewStatus}
              onChange={(e) => updateParam('review_status', e.target.value)}
              className="ml-2 px-2 py-1 rounded border border-amber-200 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-amber-300"
            >
              {REVIEW_STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Active filters */}
        {(tag || compatibility) && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted">筛选条件:</span>
            {tag && (
              <Badge
                variant="secondary"
                className="gap-1 cursor-pointer"
                onClick={() => updateParam('tag', '')}
              >
                标签: {tag} ×
              </Badge>
            )}
            {compatibility && (
              <Badge
                variant="secondary"
                className="gap-1 cursor-pointer"
                onClick={() => updateParam('compatibility', '')}
              >
                平台: {compatibility} ×
              </Badge>
            )}
          </div>
        )}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static skeleton placeholders
            <div key={i} className="rounded-xl border border-border p-5">
              <Skeleton className="h-5 w-1/2 mb-3" />
              <Skeleton className="h-4 w-full mb-2" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ))}
        </div>
      ) : listError ? (
        <div className="text-center py-20">
          <p className="text-red-600 text-sm">{listError}</p>
        </div>
      ) : showFederated ? (
        federatedItems.length === 0 ? (
          <div className="text-center py-20">
            <Search className="w-12 h-12 mx-auto mb-4 text-muted" />
            <p className="text-muted">没有找到匹配的基因</p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {federatedItems.map((item) => (
              <FederatedSearchCard key={`${item.source}-${item.slug}`} item={item} />
            ))}
          </div>
        )
      ) : genes.length === 0 ? (
        <div className="text-center py-20">
          <Search className="w-12 h-12 mx-auto mb-4 text-muted" />
          <p className="text-muted">没有找到匹配的基因</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {genes.map((gene) => (
            <GeneCard key={gene.id} gene={gene} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {!showFederated && totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-10">
          <Button
            variant="outline"
            size="sm"
            onClick={() => updateParam('page', String(page - 1))}
            disabled={page <= 1}
          >
            上一页
          </Button>
          <span className="px-4 py-2 text-sm text-muted">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => updateParam('page', String(page + 1))}
            disabled={page >= totalPages}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  );
}
