import { FlaskConical, Search, Shield } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { type Genome, listGenomes } from '@/api/client';
import GenomeCard from '@/components/GenomeCard';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/hooks/useAuth';

const SORT_OPTIONS = [
  { value: 'newest', label: '最新' },
  { value: 'popular', label: '最热' },
  { value: 'rating', label: '评分' },
];

export default function GenomeBrowse() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [genomes, setGenomes] = useState<Genome[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const { isAdmin } = useAuth();

  const q = searchParams.get('q') || '';
  const category = searchParams.get('category') || '';
  const sort = searchParams.get('sort') || 'newest';
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
    setLoading(true);
    setListError(null);
    listGenomes({
      q: q || undefined,
      category: category || undefined,
      sort,
      page,
      page_size: 12,
      ...(isAdmin && { include_unpublished: true }),
    })
      .then((data) => {
        setGenomes(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
      })
      .catch(() => {
        setGenomes([]);
        setTotal(0);
        setTotalPages(0);
        setListError('列表加载失败，请刷新重试');
      })
      .finally(() => setLoading(false));
  }, [q, category, sort, page, isAdmin]);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">
          {q ? `搜索基因组: "${q}"` : '浏览基因组'}
        </h1>
        <p className="text-muted text-sm">
          基因组是精选的基因合集，一键安装一套完整能力。共 {total} 个基因组。
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <Input
            value={q}
            onChange={(e) => updateParam('q', e.target.value)}
            placeholder="搜索基因组..."
            className="pl-9"
          />
        </div>
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

      {isAdmin && (
        <div className="flex items-center gap-2 px-3 py-2 mb-4 bg-amber-50 border border-amber-200 rounded-lg">
          <Shield className="w-4 h-4 text-amber-600" />
          <span className="text-xs font-medium text-amber-700">
            管理员模式：显示所有基因组（含未发布）
          </span>
        </div>
      )}

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
      ) : genomes.length === 0 ? (
        <div className="text-center py-20">
          <FlaskConical className="w-12 h-12 mx-auto mb-4 text-muted" />
          <p className="text-muted">暂无基因组</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {genomes.map((genome) => (
            <GenomeCard key={genome.id} genome={genome} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
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
