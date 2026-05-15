import { Download, Layers, Star, User } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { AgentTemplate } from '@/api/client';
import LucideIcon from './LucideIcon';
import { Badge } from './ui/badge';
import { Card } from './ui/card';

export default function TemplateCard({ template }: { template: AgentTemplate }) {
  return (
    <Link to={`/templates/${template.slug}`} className="block group">
      <Card className="p-5 h-full hover:shadow-md hover:border-primary/30 transition-all">
        <div className="flex items-start gap-3 mb-3">
          {template.avatar_url ? (
            <img
              src={template.avatar_url}
              alt={template.name}
              className="w-10 h-10 rounded-full object-cover shrink-0"
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <LucideIcon name={template.icon} className="w-5 h-5 text-primary" />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-gray-900 group-hover:text-primary transition truncate">
                {template.name}
              </h3>
              <span className="text-xs text-muted shrink-0 ml-2">v{template.version}</span>
            </div>
            {template.role && (
              <p className="text-xs text-primary/70 mt-0.5 flex items-center gap-1">
                <User className="w-3 h-3" />
                {template.role}
              </p>
            )}
          </div>
        </div>

        <p className="text-sm text-muted mb-4 line-clamp-2">
          {template.short_description || template.description}
        </p>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            {(template.genomes as { slug: string }[]).length > 0 && (
              <Badge variant="secondary" className="gap-1 text-[11px]">
                <Layers className="w-3 h-3" />
                {(template.genomes as { slug: string }[]).length} 个基因组
              </Badge>
            )}
            {(template.genes as { slug: string }[]).length > 0 && (
              <span className="text-[11px] text-muted">
                +{(template.genes as { slug: string }[]).length} 基因
              </span>
            )}
          </div>
          <div className="flex items-center gap-2.5 text-xs text-muted shrink-0 ml-2">
            {template.avg_rating > 0 && (
              <span className="flex items-center gap-0.5">
                <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                {template.avg_rating.toFixed(1)}
              </span>
            )}
            <span className="flex items-center gap-0.5" title="安装次数">
              <Download className="w-3 h-3" />
              {template.install_count}
            </span>
          </div>
        </div>
      </Card>
    </Link>
  );
}
