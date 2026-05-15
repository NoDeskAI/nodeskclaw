import { Download, Layers, Star } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Genome } from '@/api/client';
import LucideIcon from './LucideIcon';
import { Badge } from './ui/badge';
import { Card } from './ui/card';

export default function GenomeCard({ genome }: { genome: Genome }) {
  return (
    <Link to={`/genomes/${genome.slug}`} className="block group">
      <Card className="p-5 h-full hover:shadow-md hover:border-primary/30 transition-all">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <LucideIcon name={genome.icon} className="w-5 h-5 shrink-0 text-primary" />
            <h3 className="font-semibold text-gray-900 group-hover:text-primary transition truncate">
              {genome.name}
            </h3>
          </div>
          <span className="text-xs text-muted shrink-0 ml-2">v{genome.version}</span>
        </div>

        <p className="text-sm text-muted mb-4 line-clamp-2">
          {genome.short_description || genome.description}
        </p>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Badge variant="secondary" className="gap-1 text-[11px]">
              <Layers className="w-3 h-3" />
              {genome.genes.length} 个基因
            </Badge>
            {genome.compatibility.slice(0, 2).map((p) => (
              <span key={p} className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                {p}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-2.5 text-xs text-muted shrink-0 ml-2">
            {genome.avg_rating > 0 && (
              <span className="flex items-center gap-0.5">
                <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                {genome.avg_rating.toFixed(1)}
              </span>
            )}
            <span className="flex items-center gap-0.5" title="安装次数">
              <Download className="w-3 h-3" />
              {genome.install_count}
            </span>
          </div>
        </div>
      </Card>
    </Link>
  );
}
