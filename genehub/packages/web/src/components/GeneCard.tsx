import { Bot, Download, Star } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Gene } from '@/api/client';
import { CATEGORY_COLORS, getReviewStatusConfig } from '@/lib/status';
import LucideIcon from './LucideIcon';
import { Badge } from './ui/badge';
import { Card } from './ui/card';

export default function GeneCard({ gene }: { gene: Gene }) {
  const catColor = CATEGORY_COLORS[gene.category] || 'bg-gray-50 text-gray-700';
  const status = getReviewStatusConfig(gene.review_status);

  return (
    <Link to={`/genes/${gene.slug}`} className="block group">
      <Card className="p-5 h-full hover:shadow-md hover:border-primary/30 transition-all">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <LucideIcon name={gene.icon} className="w-5 h-5 shrink-0 text-primary" />
            <h3 className="font-semibold text-gray-900 group-hover:text-primary transition truncate">
              {gene.name}
            </h3>
          </div>
          <div className="flex items-center gap-1.5 shrink-0 ml-2">
            <Badge variant={status.variant} className="text-[10px] px-1.5 py-0">
              {status.label}
            </Badge>
            <span className="text-xs text-muted">v{gene.version}</span>
          </div>
        </div>

        <p className="text-sm text-muted mb-4 line-clamp-2">
          {gene.short_description || gene.description}
        </p>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${catColor}`}>
              {gene.category}
            </span>
            {gene.compatibility.slice(0, 2).map((p) => (
              <span key={p} className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                {p}
              </span>
            ))}
          </div>

          <div className="flex items-center gap-2.5 text-xs text-muted shrink-0 ml-2">
            {gene.ai_score != null && (
              <span
                className="flex items-center gap-0.5 text-indigo-600 font-medium"
                title="AI 评分"
              >
                <Bot className="w-3 h-3" />
                {gene.ai_score.toFixed(1)}
              </span>
            )}
            {gene.avg_rating > 0 && (
              <span className="flex items-center gap-0.5" title="用户评分">
                <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                {gene.avg_rating.toFixed(1)}
              </span>
            )}
            <span className="flex items-center gap-0.5" title="安装次数">
              <Download className="w-3 h-3" />
              {gene.install_count}
            </span>
          </div>
        </div>
      </Card>
    </Link>
  );
}
