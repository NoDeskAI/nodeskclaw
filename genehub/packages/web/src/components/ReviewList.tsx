import { Bot, MessageSquare, Send, ThumbsDown, ThumbsUp, User } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import {
  type GeneReview,
  getGeneReviews,
  getGenomeReviews,
  getTemplateReviews,
  type PagedData,
  submitReview,
} from '@/api/client';
import { useAuth } from '@/hooks/useAuth';
import { getReviewStatusConfig } from '@/lib/status';
import { Badge } from './ui/badge';
import { Skeleton } from './ui/skeleton';

type EntityType = 'gene' | 'genome' | 'template';

const FETCH_MAP: Record<EntityType, typeof getGeneReviews> = {
  gene: getGeneReviews,
  genome: getGenomeReviews,
  template: getTemplateReviews,
};

const VERDICT_OPTIONS = [
  { value: 'approved', label: '通过' },
  { value: 'needs_improvement', label: '待改进' },
  { value: 'rejected', label: '拒绝' },
  { value: 'flagged', label: '标记删除' },
];

function AdminReviewForm({
  slug,
  entityType,
  onSubmitted,
}: {
  slug: string;
  entityType: EntityType;
  onSubmitted: () => void;
}) {
  const [verdict, setVerdict] = useState('approved');
  const [score, setScore] = useState('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const comments = comment.trim() ? [comment.trim()] : [];
      await submitReview(entityType, slug, {
        verdict,
        score: score ? Number(score) : undefined,
        comments,
      });
      setComment('');
      setScore('');
      onSubmitted();
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border border-primary/20 rounded-xl p-5 bg-primary/5 space-y-4"
    >
      <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
        <Send className="w-4 h-4 text-primary" />
        管理员评审
      </h3>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="review-verdict" className="block text-xs text-muted mb-1">
            审核结论
          </label>
          <select
            id="review-verdict"
            value={verdict}
            onChange={(e) => setVerdict(e.target.value)}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-white"
          >
            {VERDICT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="review-score" className="block text-xs text-muted mb-1">
            评分 (0-10, 可选)
          </label>
          <input
            id="review-score"
            type="number"
            min="0"
            max="10"
            step="0.1"
            value={score}
            onChange={(e) => setScore(e.target.value)}
            placeholder="0-10"
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
          />
        </div>
      </div>

      <div>
        <label htmlFor="review-comment" className="block text-xs text-muted mb-1">
          评审意见 (可选)
        </label>
        <textarea
          id="review-comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="写下你的评审意见..."
          rows={3}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm resize-none"
        />
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 transition disabled:opacity-50"
      >
        {submitting ? '提交中...' : '提交评审'}
      </button>
    </form>
  );
}

export default function ReviewList({
  slug,
  entityType = 'gene',
}: {
  slug: string;
  entityType?: EntityType;
}) {
  const { isAdmin } = useAuth();
  const [data, setData] = useState<PagedData<GeneReview> | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const fetchReviews = useCallback(() => {
    setLoading(true);
    const fetcher = FETCH_MAP[entityType];
    fetcher(slug, { page, page_size: 10 })
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [slug, entityType, page]);

  useEffect(() => {
    fetchReviews();
  }, [fetchReviews]);

  function handleReviewSubmitted() {
    setPage(1);
    fetchReviews();
  }

  return (
    <div className="space-y-4">
      {isAdmin && (
        <AdminReviewForm slug={slug} entityType={entityType} onSubmitted={handleReviewSubmitted} />
      )}

      {loading ? (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div key={i} className="border border-border rounded-xl p-5 space-y-3">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="text-center py-12">
          <MessageSquare className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-muted">暂无评审记录</p>
        </div>
      ) : (
        <>
          {data.items.map((review) => {
            const verdictConfig = review.verdict ? getReviewStatusConfig(review.verdict) : null;
            const isCurator = review.reviewer === 'curator-agent';
            return (
              <div key={review.id} className="border border-border rounded-xl p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {isCurator ? (
                      <Bot className="w-4 h-4 text-indigo-500" />
                    ) : (
                      <User className="w-4 h-4 text-primary" />
                    )}
                    <span className="text-sm font-medium text-gray-900">
                      {isCurator ? 'AI Curator' : review.reviewer}
                    </span>
                    {review.model && <span className="text-xs text-muted">({review.model})</span>}
                    {!isCurator && (
                      <Badge variant="outline" className="text-[10px]">
                        管理员
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {review.score != null && (
                      <Badge variant="info" className="text-xs">
                        {review.score.toFixed(1)} 分
                      </Badge>
                    )}
                    {verdictConfig && (
                      <Badge variant={verdictConfig.variant}>{verdictConfig.label}</Badge>
                    )}
                    {review.feedback && (
                      <span title={`人工反馈: ${review.feedback}`}>
                        {review.feedback === 'helpful' ? (
                          <ThumbsUp className="w-3.5 h-3.5 text-green-600" />
                        ) : (
                          <ThumbsDown className="w-3.5 h-3.5 text-red-500" />
                        )}
                      </span>
                    )}
                  </div>
                </div>

                {review.comments.length > 0 && (
                  <ul className="space-y-1.5">
                    {review.comments.map((c, i) => (
                      // biome-ignore lint/suspicious/noArrayIndexKey: comments are plain strings
                      <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                        <span className="text-primary mt-0.5 shrink-0">-</span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                )}

                <time className="text-xs text-muted block">
                  {new Date(review.created_at).toLocaleString('zh-CN')}
                </time>
              </div>
            );
          })}

          {data.total_pages > 1 && (
            <div className="flex justify-center gap-2 pt-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1.5 rounded-lg border border-border text-xs disabled:opacity-40 hover:bg-gray-50 transition"
              >
                上一页
              </button>
              <span className="px-3 py-1.5 text-xs text-muted">
                {page} / {data.total_pages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
                disabled={page >= data.total_pages}
                className="px-3 py-1.5 rounded-lg border border-border text-xs disabled:opacity-40 hover:bg-gray-50 transition"
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
