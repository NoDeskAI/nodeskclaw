import { Dna, ExternalLink, Globe } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { FederatedGeneItem } from '@/api/client';
import { Badge } from './ui/badge';
import { Card } from './ui/card';

export default function FederatedSearchCard({ item }: { item: FederatedGeneItem }) {
  const isLocal = item.source === 'local';

  const content = (
    <Card className="p-5 h-full hover:shadow-md hover:border-primary/30 transition-all">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <Dna className="w-5 h-5 shrink-0 text-primary" />
          <h3 className="font-semibold text-gray-900 group-hover:text-primary transition truncate">
            {item.clawhub_display_name || item.name}
          </h3>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          <Badge variant={isLocal ? 'info' : 'outline'} className="text-[10px] px-1.5 py-0 gap-0.5">
            {!isLocal && <Globe className="w-2.5 h-2.5" />}
            {isLocal ? '本地' : 'ClawHub'}
          </Badge>
          {item.version && <span className="text-xs text-muted">v{item.version}</span>}
        </div>
      </div>

      <p className="text-sm text-muted mb-4 line-clamp-2">{item.description || '暂无描述'}</p>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {item.category && (
            <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-50 text-gray-600">
              {item.category}
            </span>
          )}
          {item.tags.slice(0, 2).map((t) => (
            <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
              {t}
            </span>
          ))}
        </div>
        {!isLocal && <ExternalLink className="w-3.5 h-3.5 text-muted" />}
      </div>
    </Card>
  );

  if (isLocal) {
    return (
      <Link to={`/genes/${item.slug}`} className="block group">
        {content}
      </Link>
    );
  }

  return <div className="opacity-90">{content}</div>;
}
