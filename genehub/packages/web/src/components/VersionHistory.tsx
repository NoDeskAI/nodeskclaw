import { Check, ChevronRight, Copy, Layers, Tag } from 'lucide-react';
import { useState } from 'react';
import {
  type GeneVersion,
  getGeneFileContent,
  getGenomeFileContent,
  getTemplateFileContent,
} from '@/api/client';
import { Badge } from '@/components/ui/badge';

type EntityType = 'gene' | 'genome' | 'template';

const FILE_FETCHERS: Record<
  EntityType,
  (slug: string, path: string, version?: string) => Promise<{ path: string; content: string }>
> = {
  gene: getGeneFileContent,
  genome: getGenomeFileContent,
  template: getTemplateFileContent,
};

const INSTALL_PREFIXES: Record<EntityType, string> = {
  gene: 'genehub install',
  genome: 'genehub genome install',
  template: 'genehub template install',
};

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        });
      }}
      className="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 transition flex items-center gap-1 shrink-0"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {copied ? '已复制' : '复制'}
    </button>
  );
}

export default function VersionHistory({
  versions,
  slug,
  entityType = 'gene',
}: {
  versions: GeneVersion[];
  slug: string;
  entityType?: EntityType;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<{ path: string; content: string } | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);

  if (versions.length === 0) {
    return (
      <div className="text-center py-12">
        <Layers className="w-10 h-10 text-gray-300 mx-auto mb-3" />
        <p className="text-muted">暂无版本记录</p>
      </div>
    );
  }

  function handleToggle(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
    setFileContent(null);
  }

  async function handleFileClick(version: string, filePath: string) {
    setLoadingFile(true);
    try {
      const fetcher = FILE_FETCHERS[entityType];
      const data = await fetcher(slug, filePath, version);
      setFileContent(data);
    } catch {
      setFileContent({ path: filePath, content: '(无法加载文件内容)' });
    } finally {
      setLoadingFile(false);
    }
  }

  const installPrefix = INSTALL_PREFIXES[entityType];

  return (
    <div className="space-y-3">
      {versions.map((v) => {
        const isExpanded = expandedId === v.id;
        return (
          <div key={v.id} className="border border-border rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => handleToggle(v.id)}
              className="w-full flex items-start justify-between px-5 py-4 hover:bg-gray-50 transition text-left"
            >
              <div>
                <div className="flex items-center gap-2">
                  <ChevronRight
                    className={`w-4 h-4 text-muted transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                  />
                  <span className="font-mono text-sm font-medium text-gray-900">v{v.version}</span>
                  {v.is_latest && (
                    <Badge variant="success" className="text-[10px] px-1.5 py-0">
                      latest
                    </Badge>
                  )}
                </div>
                {v.changelog && <p className="text-sm text-muted mt-1 ml-6">{v.changelog}</p>}
              </div>
              <time className="text-xs text-muted whitespace-nowrap">
                {new Date(v.published_at).toLocaleDateString('zh-CN')}
              </time>
            </button>

            {isExpanded && (
              <div className="border-t border-border px-5 py-4 bg-gray-50/50 space-y-4">
                <div className="bg-gray-900 rounded-lg px-4 py-3 flex items-center justify-between">
                  <code className="text-sm text-green-400 font-mono">
                    $ {installPrefix} {slug}@{v.version}
                  </code>
                  <CopyBtn text={`${installPrefix} ${slug}@${v.version}`} />
                </div>

                <div className="flex flex-wrap gap-4 text-xs text-muted">
                  {v.git_tag && (
                    <span className="flex items-center gap-1">
                      <Tag className="w-3 h-3" /> {v.git_tag}
                    </span>
                  )}
                  {v.commit_sha && <span className="font-mono">{v.commit_sha.slice(0, 8)}</span>}
                </div>

                {v.files && v.files.length > 0 && (
                  <div className="border border-border rounded-lg overflow-hidden bg-white">
                    <div className="px-3 py-2 border-b border-border text-xs font-medium text-muted bg-gray-50">
                      文件 ({v.files.length})
                    </div>
                    <div className="grid grid-cols-3 divide-x divide-border min-h-[200px]">
                      <div className="col-span-1 divide-y divide-border">
                        {v.files.map((f) => (
                          <button
                            type="button"
                            key={f.path}
                            onClick={() => handleFileClick(v.version, f.path)}
                            className={`w-full text-left px-3 py-2 text-xs font-mono hover:bg-gray-50 transition ${
                              fileContent?.path === f.path
                                ? 'bg-white text-primary font-medium'
                                : 'text-gray-700'
                            }`}
                          >
                            {f.path}
                            <span className="text-muted ml-1">
                              {f.size > 1024 ? `${(f.size / 1024).toFixed(1)}K` : `${f.size}B`}
                            </span>
                          </button>
                        ))}
                      </div>
                      <div className="col-span-2">
                        {loadingFile ? (
                          <div className="flex items-center justify-center h-full text-muted text-sm">
                            加载中...
                          </div>
                        ) : fileContent ? (
                          <>
                            <div className="px-3 py-2 border-b border-border flex items-center justify-between bg-gray-50">
                              <span className="text-xs font-mono text-gray-700">
                                {fileContent.path}
                              </span>
                              <CopyBtn text={fileContent.content} />
                            </div>
                            <pre className="p-3 text-xs font-mono text-gray-800 overflow-auto max-h-[400px] whitespace-pre-wrap">
                              {fileContent.content}
                            </pre>
                          </>
                        ) : (
                          <div className="flex items-center justify-center h-full text-muted text-xs">
                            点击左侧文件查看内容
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
