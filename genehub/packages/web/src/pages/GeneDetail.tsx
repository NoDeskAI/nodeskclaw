import {
  AlertCircle,
  Bot,
  Calendar,
  Check,
  ChevronRight,
  Copy,
  Download,
  ExternalLink,
  Layers,
  Star,
  Tag,
  User,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  type Gene,
  type GeneFileEntry,
  type GeneVersion,
  getGene,
  getGeneFileContent,
  getGeneFiles,
  getGeneVersions,
} from '@/api/client';
import LucideIcon from '@/components/LucideIcon';
import ReviewList from '@/components/ReviewList';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import VersionHistory from '@/components/VersionHistory';
import { CATEGORY_COLORS, getReviewStatusConfig } from '@/lib/status';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 transition flex items-center gap-1"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {copied ? '已复制' : '复制'}
    </button>
  );
}

function InstallBlock({ slug }: { slug: string }) {
  const commands = [
    { label: '安装', cmd: `genehub install ${slug} -p openclaw` },
    { label: '深度学习安装', cmd: `genehub install ${slug} --learn -p openclaw` },
  ];

  return (
    <div className="bg-gray-900 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
        <span className="w-3 h-3 rounded-full bg-red-500" />
        <span className="w-3 h-3 rounded-full bg-yellow-500" />
        <span className="w-3 h-3 rounded-full bg-green-500" />
      </div>
      <div className="p-4 space-y-3 font-mono text-sm text-gray-300">
        {commands.map((c) => (
          <div key={c.label} className="flex items-center justify-between gap-4">
            <div>
              <span className="text-gray-500 mr-2">#</span>
              <span className="text-gray-500">{c.label}</span>
              <div className="text-green-400">$ {c.cmd}</div>
            </div>
            <CopyButton text={c.cmd} />
          </div>
        ))}
      </div>
    </div>
  );
}

function FileExplorer({ slug }: { slug: string }) {
  const [files, setFiles] = useState<GeneFileEntry[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getGeneFiles(slug)
      .then(setFiles)
      .catch(() => setFiles([]))
      .finally(() => setLoading(false));
  }, [slug]);

  useEffect(() => {
    if (!selectedFile) {
      setFileContent('');
      return;
    }
    getGeneFileContent(slug, selectedFile)
      .then((data) => setFileContent(data.content))
      .catch(() => setFileContent('(无法加载文件内容)'));
  }, [slug, selectedFile]);

  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-6 w-1/2" />
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="text-center py-12">
        <Layers className="w-10 h-10 text-gray-300 mx-auto mb-3" />
        <p className="text-muted">暂无文件信息</p>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <div className="grid grid-cols-3 divide-x divide-border min-h-[300px]">
        <div className="col-span-1 bg-gray-50">
          <div className="px-3 py-2 border-b border-border text-xs font-medium text-muted">
            文件列表 ({files.length})
          </div>
          <div className="divide-y divide-border">
            {files.map((f) => (
              <button
                type="button"
                key={f.path}
                onClick={() => setSelectedFile(f.path === selectedFile ? null : f.path)}
                className={`w-full text-left px-3 py-2 text-sm font-mono hover:bg-white transition ${
                  selectedFile === f.path ? 'bg-white text-primary font-medium' : 'text-gray-700'
                }`}
              >
                {f.path}
                <span className="text-xs text-muted ml-2">
                  {f.size > 1024 ? `${(f.size / 1024).toFixed(1)}KB` : `${f.size}B`}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="col-span-2">
          {selectedFile ? (
            <>
              <div className="px-4 py-2 border-b border-border flex items-center justify-between bg-gray-50">
                <span className="text-sm font-mono text-gray-700">{selectedFile}</span>
                <CopyButton text={fileContent} />
              </div>
              <pre className="p-4 text-sm font-mono text-gray-800 overflow-auto max-h-[500px] whitespace-pre-wrap">
                {fileContent}
              </pre>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-muted text-sm">
              选择文件查看内容
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SidebarItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between items-start text-sm">
      <span className="text-muted shrink-0">{label}</span>
      <span className="text-gray-700 text-right">{children}</span>
    </div>
  );
}

export default function GeneDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [gene, setGene] = useState<Gene | null>(null);
  const [versions, setVersions] = useState<GeneVersion[]>([]);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!slug) return;
    setError('');
    setGene(null);
    setVersions([]);
    setVersionsError(null);
    getGene(slug)
      .then(setGene)
      .catch(() => setError('找不到该基因'));
    getGeneVersions(slug)
      .then(setVersions)
      .catch(() => setVersionsError('版本历史加载失败，请刷新重试'));
  }, [slug]);

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-20 text-center">
        <AlertCircle className="w-14 h-14 mx-auto mb-4 text-muted" />
        <p className="text-xl text-gray-900 mb-2">{error}</p>
        <Link to="/browse" className="text-primary hover:underline">
          返回浏览
        </Link>
      </div>
    );
  }

  if (!gene) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="grid lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-4">
            <Skeleton className="h-10 w-1/3" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-64 w-full" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        </div>
      </div>
    );
  }

  const manifest = gene.manifest as Record<string, unknown>;
  const learning = manifest.learning as { level?: string; objectives?: string[] } | undefined;
  const skill = manifest.skill as { description?: string } | undefined;
  const mcpServers = manifest.mcpServers as Record<string, unknown> | undefined;
  const rules = manifest.rules as { name: string; content: string }[] | undefined;
  const statusConfig = getReviewStatusConfig(gene.review_status);
  const catColor = CATEGORY_COLORS[gene.category] || 'bg-gray-50 text-gray-700';

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1 text-sm text-muted mb-6">
        <Link to="/browse" className="hover:text-gray-900 transition">
          浏览
        </Link>
        <ChevronRight className="w-3.5 h-3.5" />
        <Link to={`/browse?category=${gene.category}`} className="hover:text-gray-900 transition">
          {gene.category}
        </Link>
        <ChevronRight className="w-3.5 h-3.5" />
        <span className="text-gray-900">{gene.name}</span>
      </nav>

      <div className="grid lg:grid-cols-3 gap-8">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Header */}
          <div className="flex items-start gap-4">
            <LucideIcon name={gene.icon} className="w-9 h-9 text-primary" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl font-bold text-gray-900">{gene.name}</h1>
                <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
                {gene.ai_score != null && (
                  <Badge variant="info" className="gap-1">
                    <Bot className="w-3 h-3" />
                    AI {gene.ai_score.toFixed(1)}
                  </Badge>
                )}
              </div>
              <p className="text-muted text-sm mt-1">
                {gene.slug} · v{gene.version}
              </p>
              <p className="text-gray-700 mt-2">{gene.short_description}</p>
            </div>
          </div>

          {/* Tabs */}
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">概述</TabsTrigger>
              <TabsTrigger value="files">文件</TabsTrigger>
              <TabsTrigger value="reviews">评审记录</TabsTrigger>
              <TabsTrigger value="versions">版本历史</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-6">
              {/* Description */}
              <Card>
                <CardContent className="pt-6">
                  <h2 className="text-lg font-semibold text-gray-900 mb-3">描述</h2>
                  <p className="text-gray-600 leading-relaxed whitespace-pre-wrap">
                    {gene.description}
                  </p>
                </CardContent>
              </Card>

              {/* Skill */}
              {skill?.description && (
                <Card>
                  <CardContent className="pt-6">
                    <h2 className="text-lg font-semibold text-gray-900 mb-3">技能说明</h2>
                    <p className="text-gray-600 leading-relaxed whitespace-pre-wrap">
                      {skill.description}
                    </p>
                  </CardContent>
                </Card>
              )}

              {/* Rules */}
              {rules && rules.length > 0 && (
                <Card>
                  <CardContent className="pt-6">
                    <h2 className="text-lg font-semibold text-gray-900 mb-3">规则</h2>
                    <div className="space-y-3">
                      {rules.map((rule) => (
                        <div key={rule.name} className="bg-gray-50 rounded-lg px-4 py-3">
                          <span className="text-sm font-medium text-gray-900">{rule.name}</span>
                          <p className="text-sm text-gray-600 mt-1 whitespace-pre-wrap">
                            {rule.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* MCP Servers */}
              {mcpServers && Object.keys(mcpServers).length > 0 && (
                <Card>
                  <CardContent className="pt-6">
                    <h2 className="text-lg font-semibold text-gray-900 mb-3">MCP Servers</h2>
                    <div className="space-y-2">
                      {Object.entries(mcpServers).map(([name, config]) => (
                        <div key={name} className="bg-gray-50 rounded-lg px-4 py-3">
                          <span className="font-mono text-sm font-medium text-gray-900">
                            {name}
                          </span>
                          <pre className="text-xs text-muted mt-1 overflow-x-auto">
                            {JSON.stringify(config, null, 2)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Learning */}
              {learning && (
                <Card>
                  <CardContent className="pt-6">
                    <h2 className="text-lg font-semibold text-gray-900 mb-3">学习配置</h2>
                    {learning.level && (
                      <div className="mb-3">
                        <span className="text-sm font-medium text-gray-700">学习等级：</span>
                        <Badge variant="info" className="ml-2">
                          {learning.level}
                        </Badge>
                      </div>
                    )}
                    {learning.objectives && learning.objectives.length > 0 && (
                      <div>
                        <span className="text-sm font-medium text-gray-700 block mb-2">
                          学习目标：
                        </span>
                        <ul className="space-y-1">
                          {learning.objectives.map((obj) => (
                            <li key={obj} className="text-sm text-gray-600 flex items-start gap-2">
                              <span className="text-primary mt-0.5">▸</span>
                              {obj}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Install */}
              <div>
                <h2 className="text-lg font-semibold text-gray-900 mb-3">安装</h2>
                <InstallBlock slug={gene.slug} />
              </div>
            </TabsContent>

            <TabsContent value="files">{slug && <FileExplorer slug={slug} />}</TabsContent>

            <TabsContent value="reviews">{slug && <ReviewList slug={slug} />}</TabsContent>

            <TabsContent value="versions">
              {versionsError ? (
                <p className="text-sm text-red-600">{versionsError}</p>
              ) : (
                <VersionHistory versions={versions} slug={gene.slug} />
              )}
            </TabsContent>
          </Tabs>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Meta */}
          <Card>
            <CardContent className="pt-5 space-y-3">
              <SidebarItem label="分类">
                <Link
                  to={`/browse?category=${gene.category}`}
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${catColor} hover:opacity-80`}
                >
                  {gene.category}
                </Link>
              </SidebarItem>
              <Separator />
              <SidebarItem label="来源">
                {gene.source === 'github' && gene.source_ref ? (
                  <a
                    href={`https://github.com/${gene.source_ref}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    @{gene.source_ref}
                    <ExternalLink className="w-3 h-3" />
                  </a>
                ) : (
                  <>
                    {gene.source}
                    {gene.source_ref && (
                      <a
                        href={gene.source_ref}
                        target="_blank"
                        rel="noreferrer"
                        className="ml-1 inline-block align-middle"
                      >
                        <ExternalLink className="w-3 h-3 text-muted" />
                      </a>
                    )}
                  </>
                )}
              </SidebarItem>
              <SidebarItem label="作者">
                <span className="flex items-center gap-1">
                  <User className="w-3 h-3" />
                  {gene.author?.name || '未知'}
                </span>
              </SidebarItem>
              <Separator />
              <SidebarItem label="安装次数">
                <span className="flex items-center gap-1">
                  <Download className="w-3 h-3" />
                  {gene.install_count}
                </span>
              </SidebarItem>
              <SidebarItem label="用户评分">
                {gene.avg_rating > 0 ? (
                  <span className="flex items-center gap-1">
                    <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                    {gene.avg_rating.toFixed(1)}
                  </span>
                ) : (
                  '暂无'
                )}
              </SidebarItem>
              {gene.ai_score != null && (
                <SidebarItem label="AI 评分">
                  <span className="flex items-center gap-1 text-indigo-600 font-medium">
                    <Bot className="w-3 h-3" />
                    {gene.ai_score.toFixed(1)}
                  </span>
                </SidebarItem>
              )}
              {gene.effectiveness_score > 0 && (
                <SidebarItem label="有效性">{gene.effectiveness_score.toFixed(1)}</SidebarItem>
              )}
              <Separator />
              <SidebarItem label="发布时间">
                <span className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  {new Date(gene.created_at).toLocaleDateString('zh-CN')}
                </span>
              </SidebarItem>
            </CardContent>
          </Card>

          {/* Tags */}
          {gene.tags.length > 0 && (
            <Card>
              <CardContent className="pt-5">
                <h3 className="text-sm font-medium text-gray-900 mb-3 flex items-center gap-1.5">
                  <Tag className="w-3.5 h-3.5" />
                  标签
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {gene.tags.map((tag) => (
                    <Badge key={tag} variant="secondary">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Compatibility */}
          {gene.compatibility.length > 0 && (
            <Card>
              <CardContent className="pt-5">
                <h3 className="text-sm font-medium text-gray-900 mb-3">兼容产品</h3>
                <div className="flex flex-wrap gap-1.5">
                  {gene.compatibility.map((p) => (
                    <Badge key={p} variant="info">
                      {p}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Dependencies */}
          {gene.dependencies.length > 0 && (
            <Card>
              <CardContent className="pt-5">
                <h3 className="text-sm font-medium text-gray-900 mb-3">依赖</h3>
                <div className="space-y-1.5">
                  {gene.dependencies.map((dep) => (
                    <Link
                      key={dep.slug}
                      to={`/genes/${dep.slug}`}
                      className="flex justify-between text-sm hover:bg-gray-50 rounded px-2 py-1 -mx-2 transition"
                    >
                      <span className="text-primary">{dep.slug}</span>
                      <span className="text-muted">{dep.version}</span>
                    </Link>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Synergies */}
          {gene.synergies.length > 0 && (
            <Card>
              <CardContent className="pt-5">
                <h3 className="text-sm font-medium text-gray-900 mb-3">协同基因</h3>
                <div className="flex flex-wrap gap-1.5">
                  {gene.synergies.map((s) => (
                    <Link key={s} to={`/genes/${s}`}>
                      <Badge variant="outline" className="hover:bg-gray-50 cursor-pointer">
                        {s}
                      </Badge>
                    </Link>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
