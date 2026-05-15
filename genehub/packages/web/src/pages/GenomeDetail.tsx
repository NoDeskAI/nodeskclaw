import { Calendar, Check, ChevronRight, Copy, Download, Layers, Star, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  type GeneFileEntry,
  type GeneVersion,
  type Genome,
  getGenome,
  getGenomeFileContent,
  getGenomeFiles,
  getGenomeVersions,
} from '@/api/client';
import LucideIcon from '@/components/LucideIcon';
import ReviewList from '@/components/ReviewList';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import VersionHistory from '@/components/VersionHistory';

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

function FileExplorer({ slug }: { slug: string }) {
  const [files, setFiles] = useState<GeneFileEntry[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getGenomeFiles(slug)
      .then(setFiles)
      .catch(() => setFiles([]))
      .finally(() => setLoading(false));
  }, [slug]);

  useEffect(() => {
    if (!selectedFile) {
      setFileContent('');
      return;
    }
    getGenomeFileContent(slug, selectedFile)
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

export default function GenomeDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [genome, setGenome] = useState<Genome | null>(null);
  const [versions, setVersions] = useState<GeneVersion[]>([]);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!slug) return;
    setError('');
    setGenome(null);
    setVersions([]);
    setVersionsError(null);
    getGenome(slug)
      .then(setGenome)
      .catch(() => setError('找不到该基因组'));
    getGenomeVersions(slug)
      .then(setVersions)
      .catch(() => setVersionsError('版本历史加载失败，请刷新重试'));
  }, [slug]);

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-20 text-center">
        <p className="text-xl text-gray-900 mb-2">{error}</p>
        <Link to="/genomes" className="text-primary hover:underline">
          返回浏览
        </Link>
      </div>
    );
  }

  if (!genome) {
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
          </div>
        </div>
      </div>
    );
  }

  const installCmd = `genehub install-genome ${genome.slug} -p openclaw`;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <nav className="flex items-center gap-1 text-sm text-muted mb-6">
        <Link to="/genomes" className="hover:text-gray-900 transition">
          基因组
        </Link>
        <ChevronRight className="w-3.5 h-3.5" />
        <span className="text-gray-900">{genome.name}</span>
      </nav>

      <div className="grid lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <div className="flex items-start gap-4">
            <LucideIcon name={genome.icon} className="w-9 h-9 text-primary" />
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{genome.name}</h1>
              <p className="text-muted text-sm mt-1">
                {genome.slug} · v{genome.version}
              </p>
              <p className="text-gray-700 mt-2">{genome.short_description}</p>
            </div>
          </div>

          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">概述</TabsTrigger>
              <TabsTrigger value="files">文件</TabsTrigger>
              <TabsTrigger value="reviews">评审记录</TabsTrigger>
              <TabsTrigger value="versions">版本历史</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-6">
              <Card>
                <CardContent className="pt-6">
                  <h2 className="text-lg font-semibold text-gray-900 mb-3">描述</h2>
                  <p className="text-gray-600 leading-relaxed whitespace-pre-wrap">
                    {genome.description}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="pt-6">
                  <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <Layers className="w-5 h-5" />
                    包含的基因 ({genome.genes.length})
                  </h2>
                  <div className="space-y-2">
                    {genome.genes.map((g) => (
                      <Link
                        key={g.slug}
                        to={`/genes/${g.slug}`}
                        className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-gray-50 hover:border-primary/30 transition-all"
                      >
                        <span className="text-sm font-medium text-primary">{g.slug}</span>
                        <Badge variant="outline" className="text-xs">
                          {g.version}
                        </Badge>
                      </Link>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <div>
                <h2 className="text-lg font-semibold text-gray-900 mb-3">安装</h2>
                <div className="bg-gray-900 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-red-500" />
                    <span className="w-3 h-3 rounded-full bg-yellow-500" />
                    <span className="w-3 h-3 rounded-full bg-green-500" />
                  </div>
                  <div className="p-4 font-mono text-sm text-gray-300 flex items-center justify-between gap-4">
                    <div>
                      <span className="text-green-400">$ {installCmd}</span>
                    </div>
                    <CopyButton text={installCmd} />
                  </div>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="files">{slug && <FileExplorer slug={slug} />}</TabsContent>

            <TabsContent value="reviews">
              {slug && <ReviewList slug={slug} entityType="genome" />}
            </TabsContent>

            <TabsContent value="versions">
              {versionsError ? (
                <p className="text-sm text-red-600">{versionsError}</p>
              ) : (
                <VersionHistory versions={versions} slug={genome.slug} entityType="genome" />
              )}
            </TabsContent>
          </Tabs>
        </div>

        <div className="space-y-4">
          <Card>
            <CardContent className="pt-5 space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">分类</span>
                <span className="text-gray-700">{genome.category}</span>
              </div>
              <Separator />
              <div className="flex justify-between">
                <span className="text-muted">作者</span>
                <span className="text-gray-700 flex items-center gap-1">
                  <User className="w-3 h-3" />
                  {genome.author?.name || '未知'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">基因数量</span>
                <span className="text-gray-700 flex items-center gap-1">
                  <Layers className="w-3 h-3" />
                  {genome.genes.length}
                </span>
              </div>
              <Separator />
              <div className="flex justify-between">
                <span className="text-muted">安装次数</span>
                <span className="text-gray-700 flex items-center gap-1">
                  <Download className="w-3 h-3" />
                  {genome.install_count}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">评分</span>
                <span className="text-gray-700">
                  {genome.avg_rating > 0 ? (
                    <span className="flex items-center gap-1">
                      <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                      {genome.avg_rating.toFixed(1)}
                    </span>
                  ) : (
                    '暂无'
                  )}
                </span>
              </div>
              <Separator />
              <div className="flex justify-between">
                <span className="text-muted">发布时间</span>
                <span className="text-gray-700 flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  {new Date(genome.created_at).toLocaleDateString('zh-CN')}
                </span>
              </div>
            </CardContent>
          </Card>

          {genome.tags.length > 0 && (
            <Card>
              <CardContent className="pt-5">
                <h3 className="text-sm font-medium text-gray-900 mb-3">标签</h3>
                <div className="flex flex-wrap gap-1.5">
                  {genome.tags.map((tag) => (
                    <Badge key={tag} variant="secondary">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {genome.compatibility.length > 0 && (
            <Card>
              <CardContent className="pt-5">
                <h3 className="text-sm font-medium text-gray-900 mb-3">兼容产品</h3>
                <div className="flex flex-wrap gap-1.5">
                  {genome.compatibility.map((p) => (
                    <Badge key={p} variant="info">
                      {p}
                    </Badge>
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
