import { ArrowRight, Bot, CheckCircle, Dna, Plug, Rocket, Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { type Gene, listGenes } from '@/api/client';
import GeneCard from '@/components/GeneCard';
import LucideIcon from '@/components/LucideIcon';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

const CATEGORIES = [
  { id: 'development', label: '开发', icon: 'Code2', desc: '编码、测试、重构' },
  { id: 'efficiency', label: '效率', icon: 'Zap', desc: '流程、自动化、工具' },
  { id: 'data', label: '数据', icon: 'BarChart2', desc: '分析、可视化、建模' },
  { id: 'communication', label: '沟通', icon: 'MessageCircle', desc: '表达、协作、汇报' },
  { id: 'creative', label: '创意', icon: 'Palette', desc: '设计、写作、脑暴' },
  { id: 'security', label: '安全', icon: 'Shield', desc: '审计、加固、合规' },
  { id: 'operations', label: '运维', icon: 'Wrench', desc: '部署、监控、运维' },
  { id: 'network', label: '网络', icon: 'Globe', desc: '协议、API、网关' },
];

export default function Home() {
  const [featured, setFeatured] = useState<Gene[]>([]);
  const [recentApproved, setRecentApproved] = useState<Gene[]>([]);
  const [totalGenes, setTotalGenes] = useState(0);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [popularRes, approvedRes] = await Promise.all([
          listGenes({ sort: 'popular', page_size: 6 }),
          listGenes({ sort: 'newest', page_size: 6 }),
        ]);
        setFeatured(popularRes.items);
        setTotalGenes(popularRes.total);
        setRecentApproved(approvedRes.items.filter((g) => g.review_status === 'approved'));
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/browse?q=${encodeURIComponent(query.trim())}`);
    }
  }

  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-br from-indigo-600 via-purple-600 to-pink-500 text-white">
        <div className="max-w-6xl mx-auto px-4 py-20 text-center">
          <h1 className="text-4xl md:text-5xl font-bold mb-4 tracking-tight">AI 员工的基因库</h1>
          <p className="text-lg text-white/80 max-w-2xl mx-auto mb-8">
            发现、安装、分享 AI Agent 的能力基因。让你的 AI 员工持续进化。
          </p>
          <form onSubmit={handleSearch} className="max-w-lg mx-auto">
            <div className="flex bg-white/10 backdrop-blur-sm rounded-xl p-1.5">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/50" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索基因，如 code-review, TDD..."
                  className="w-full pl-9 pr-4 py-3 bg-transparent text-white placeholder:text-white/50 focus:outline-none text-base"
                />
              </div>
              <button
                type="submit"
                className="px-6 py-3 bg-white text-indigo-600 rounded-lg font-medium hover:bg-white/90 transition"
              >
                搜索
              </button>
            </div>
          </form>
          <div className="mt-6 flex justify-center items-center gap-4 text-sm text-white/60 flex-wrap">
            <span className="flex items-center gap-1.5">
              <Dna className="w-4 h-4 shrink-0" />
              {totalGenes > 0 ? `${totalGenes} 个基因` : '基因持续上新'}
            </span>
            <span>•</span>
            <span className="flex items-center gap-1.5">
              <Rocket className="w-4 h-4 shrink-0" />
              L0-L3 学习协议
            </span>
            <span>•</span>
            <span className="flex items-center gap-1.5">
              <Plug className="w-4 h-4 shrink-0" />
              多平台兼容
            </span>
            <span>•</span>
            <span className="flex items-center gap-1.5">
              <Bot className="w-4 h-4 shrink-0" />
              AI Curator 自动审核
            </span>
          </div>
        </div>
      </section>

      {/* Categories */}
      <section className="max-w-6xl mx-auto px-4 py-12">
        <h2 className="text-xl font-bold text-gray-900 mb-6">按分类浏览</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {CATEGORIES.map((cat) => (
            <Link
              key={cat.id}
              to={`/browse?category=${cat.id}`}
              className="bg-surface rounded-xl border border-border p-4 text-center hover:shadow-md hover:border-primary/30 transition-all"
            >
              <LucideIcon name={cat.icon} className="w-8 h-8 mx-auto mb-2" />
              <div className="font-medium text-gray-900 text-sm">{cat.label}</div>
              <div className="text-xs text-muted mt-1">{cat.desc}</div>
            </Link>
          ))}
        </div>
      </section>

      {/* Featured */}
      <section className="max-w-6xl mx-auto px-4 pb-12">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900">热门基因</h2>
          <Link
            to="/browse?sort=popular"
            className="text-sm text-primary hover:underline flex items-center gap-1"
          >
            查看全部 <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
        {loading ? (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-xl border border-border p-5">
                <Skeleton className="h-5 w-1/2 mb-3" />
                <Skeleton className="h-4 w-full mb-2" />
                <Skeleton className="h-4 w-3/4" />
              </div>
            ))}
          </div>
        ) : featured.length > 0 ? (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {featured.map((gene) => (
              <GeneCard key={gene.id} gene={gene} />
            ))}
          </div>
        ) : null}
      </section>

      {/* Recently Approved */}
      {recentApproved.length > 0 && (
        <section className="bg-emerald-50/50 py-12">
          <div className="max-w-6xl mx-auto px-4">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-emerald-600" />
                最新审核通过
              </h2>
              <Link
                to="/browse?sort=newest"
                className="text-sm text-primary hover:underline flex items-center gap-1"
              >
                查看全部 <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recentApproved.slice(0, 3).map((gene) => (
                <GeneCard key={gene.id} gene={gene} />
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="bg-gray-900 text-white py-16">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <h2 className="text-2xl font-bold mb-4">快速上手</h2>
          <p className="text-gray-400 mb-6">一行命令，安装基因并开始学习</p>
          <div className="bg-gray-800 rounded-xl p-4 max-w-md mx-auto text-left font-mono text-sm">
            <div className="text-gray-500">$ npm i -g @nodeskai/genehub</div>
            <div className="text-green-400">$ genehub install code-review --learn -p openclaw</div>
          </div>
          <div className="mt-8 flex justify-center gap-3">
            <Button asChild>
              <Link to="/browse">浏览基因</Link>
            </Button>
            <Button
              variant="outline"
              className="text-white border-gray-600 hover:bg-gray-800"
              asChild
            >
              <Link to="/genomes">浏览基因组</Link>
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
