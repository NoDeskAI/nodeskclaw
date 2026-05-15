export type AuthUser = {
  id: string;
  github_login: string;
  github_name: string;
  github_avatar_url: string;
  github_profile_url: string;
  role: 'admin' | 'publisher';
};

export type ApiKeyItem = {
  id: string;
  name: string;
  token_prefix: string;
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
};

export type CreateKeyResult = ApiKeyItem & { token: string };

type ApiResponse<T> = { code: number; message: string; data: T };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'include', ...init });
  if (!res.ok) throw new Error(`API ${res.status}`);
  const json: ApiResponse<T> = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

export async function getMe(): Promise<AuthUser | null> {
  return request<AuthUser | null>('/auth/me');
}

export async function logout(): Promise<void> {
  await request('/auth/logout', { method: 'POST' });
}

export async function listKeys(): Promise<ApiKeyItem[]> {
  return request<ApiKeyItem[]>('/api/v1/keys');
}

export async function createKey(name: string): Promise<CreateKeyResult> {
  return request<CreateKeyResult>('/api/v1/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function revokeKey(id: string): Promise<void> {
  await request(`/api/v1/keys/${id}`, { method: 'DELETE' });
}
