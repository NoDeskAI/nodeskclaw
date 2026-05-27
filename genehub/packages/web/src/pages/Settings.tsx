import { Copy, Key, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { type ApiKeyItem, type CreateKeyResult, createKey, listKeys, revokeKey } from '../api/auth';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { useAuth } from '../hooks/useAuth';

export default function Settings() {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState<CreateKeyResult | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadKeys = useCallback(async () => {
    try {
      const result = await listKeys();
      setKeys(result);
    } catch {
      /* ignored */
    }
  }, []);

  useEffect(() => {
    if (!isLoading && !user) {
      navigate('/');
      return;
    }
    if (user) loadKeys();
  }, [user, isLoading, navigate, loadKeys]);

  async function handleCreate() {
    if (!newKeyName.trim()) return;
    setIsCreating(true);
    try {
      const result = await createKey(newKeyName.trim());
      setCreatedKey(result);
      setNewKeyName('');
      await loadKeys();
    } finally {
      setIsCreating(false);
    }
  }

  async function handleRevoke(id: string) {
    await revokeKey(id);
    await loadKeys();
  }

  function handleCopy() {
    if (!createdKey) return;
    navigator.clipboard.writeText(createdKey.token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (isLoading) return <div className="max-w-2xl mx-auto px-4 py-12 text-muted">Loading...</div>;
  if (!user) return null;

  const activeKeys = keys.filter((k) => !k.revoked_at);
  const revokedKeys = keys.filter((k) => k.revoked_at);

  return (
    <div className="max-w-2xl mx-auto px-4 py-12 space-y-8">
      <div>
        <h1 className="text-2xl font-bold">API Keys</h1>
        <p className="text-muted mt-1">
          API Key 用于 CLI 和 SDK 认证。创建后请妥善保存，密钥仅在创建时显示一次。
        </p>
      </div>

      {createdKey && (
        <Card className="border-green-200 bg-green-50">
          <CardContent className="py-4">
            <p className="text-sm font-medium text-green-800 mb-2">
              Key "{createdKey.name}" 创建成功。请立即复制保存，此密钥不会再次显示：
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 px-3 py-2 bg-white rounded border text-sm font-mono break-all">
                {createdKey.token}
              </code>
              <Button variant="outline" size="sm" onClick={handleCopy}>
                <Copy className="w-4 h-4 mr-1" />
                {copied ? '已复制' : '复制'}
              </Button>
            </div>
            <p className="text-xs text-muted mt-2">
              在 CLI 中使用: <code>genehub config set token {createdKey.token_prefix}...</code>
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Plus className="w-5 h-5" />
            创建新 Key
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleCreate();
            }}
            className="flex gap-2"
          >
            <Input
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="Key 名称（如 My Laptop）"
              className="flex-1"
            />
            <Button type="submit" disabled={isCreating || !newKeyName.trim()}>
              {isCreating ? '创建中...' : '创建'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {activeKeys.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Key className="w-5 h-5" />
              活跃 Keys ({activeKeys.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="divide-y">
            {activeKeys.map((k) => (
              <div
                key={k.id}
                className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
              >
                <div>
                  <p className="font-medium text-sm">{k.name}</p>
                  <p className="text-xs text-muted">
                    <code>{k.token_prefix}****</code>
                    {' -- '}
                    创建于 {new Date(k.created_at).toLocaleDateString('zh-CN')}
                    {k.last_used_at && (
                      <>, 最后使用 {new Date(k.last_used_at).toLocaleDateString('zh-CN')}</>
                    )}
                  </p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => handleRevoke(k.id)}>
                  <Trash2 className="w-4 h-4 text-red-500" />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {revokedKeys.length > 0 && (
        <Card className="opacity-60">
          <CardHeader>
            <CardTitle className="text-lg text-muted">已撤销 ({revokedKeys.length})</CardTitle>
          </CardHeader>
          <CardContent className="divide-y">
            {revokedKeys.map((k) => (
              <div key={k.id} className="py-3 first:pt-0 last:pb-0">
                <p className="font-medium text-sm line-through">{k.name}</p>
                <p className="text-xs text-muted">
                  <code>{k.token_prefix}****</code>
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
