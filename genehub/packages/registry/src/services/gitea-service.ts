const GITEA_URL = (process.env.GITEA_URL || 'http://localhost:3001').replace(/\/$/, '');
const GITEA_USER = process.env.GITEA_ADMIN_USER || 'genehub';
const GITEA_PASSWORD = process.env.GENEHUB_ADMIN_TOKEN || 'admin-dev-token';

export const GITEA_GENES_ORG = process.env.GITEA_ORG || 'genes';
export const GITEA_GENOMES_ORG = 'genomes';
export const GITEA_TEMPLATES_ORG = 'templates';

const AUTH_HEADER = `Basic ${Buffer.from(`${GITEA_USER}:${GITEA_PASSWORD}`).toString('base64')}`;

export type GiteaFileEntry = {
  path: string;
  size: number;
  sha: string;
  type: 'file' | 'dir';
};

export type GiteaCommitResult = {
  sha: string;
};

async function giteaFetch<T = unknown>(
  path: string,
  init?: RequestInit & { rawResponse?: boolean },
): Promise<T> {
  const url = `${GITEA_URL}/api/v1${path}`;
  const headers: Record<string, string> = {
    Authorization: AUTH_HEADER,
    ...(init?.headers as Record<string, string>),
  };
  if (!init?.rawResponse) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Gitea API ${init?.method || 'GET'} ${path} failed: ${res.status} ${text}`);
  }

  if (init?.rawResponse) return res as unknown as T;
  return res.json() as Promise<T>;
}

export async function isGiteaAvailable(): Promise<boolean> {
  try {
    await giteaFetch('/version');
    return true;
  } catch {
    return false;
  }
}

export async function ensureOrg(org = GITEA_GENES_ORG): Promise<void> {
  const labels: Record<string, { fullName: string; desc: string }> = {
    [GITEA_GENES_ORG]: { fullName: 'GeneHub Genes', desc: 'Gene repository storage' },
    [GITEA_GENOMES_ORG]: { fullName: 'GeneHub Genomes', desc: 'Genome repository storage' },
    [GITEA_TEMPLATES_ORG]: {
      fullName: 'GeneHub Templates',
      desc: 'Agent template repository storage',
    },
  };
  const label = labels[org] ?? { fullName: org, desc: `${org} storage` };

  try {
    await giteaFetch(`/orgs/${org}`);
  } catch {
    await giteaFetch('/orgs', {
      method: 'POST',
      body: JSON.stringify({
        username: org,
        full_name: label.fullName,
        description: label.desc,
        visibility: 'public',
      }),
    });
  }
}

export async function repoExists(slug: string, org = GITEA_GENES_ORG): Promise<boolean> {
  try {
    await giteaFetch(`/repos/${org}/${slug}`);
    return true;
  } catch {
    return false;
  }
}

export async function createRepo(
  slug: string,
  description: string,
  org = GITEA_GENES_ORG,
): Promise<void> {
  await ensureOrg(org);
  await giteaFetch(`/orgs/${org}/repos`, {
    method: 'POST',
    body: JSON.stringify({
      name: slug,
      description,
      auto_init: true,
      default_branch: 'main',
      private: false,
    }),
  });
}

export async function uploadFiles(
  slug: string,
  files: Record<string, string>,
  commitMessage: string,
  org = GITEA_GENES_ORG,
): Promise<GiteaCommitResult> {
  let lastSha = '';

  for (const [filePath, content] of Object.entries(files)) {
    const encoded = Buffer.from(content, 'utf-8').toString('base64');
    const apiPath = `/repos/${org}/${slug}/contents/${filePath}`;

    let existingSha: string | undefined;
    try {
      const existing = await giteaFetch<{ sha: string }>(apiPath);
      existingSha = existing.sha;
    } catch {
      // file doesn't exist yet
    }

    const body: Record<string, unknown> = {
      content: encoded,
      message: commitMessage,
    };
    if (existingSha) {
      body.sha = existingSha;
    }

    const result = await giteaFetch<{ content: { sha: string }; commit: { sha: string } }>(
      apiPath,
      {
        method: existingSha ? 'PUT' : 'POST',
        body: JSON.stringify(body),
      },
    );
    lastSha = result.commit.sha;
  }

  return { sha: lastSha };
}

export async function createTag(
  slug: string,
  tagName: string,
  commitSha: string,
  org = GITEA_GENES_ORG,
): Promise<void> {
  await giteaFetch(`/repos/${org}/${slug}/tags`, {
    method: 'POST',
    body: JSON.stringify({
      tag_name: tagName,
      target: commitSha,
      message: `Release ${tagName}`,
    }),
  });
}

export async function getFileTree(
  slug: string,
  ref = 'main',
  org = GITEA_GENES_ORG,
): Promise<GiteaFileEntry[]> {
  const tree = await giteaFetch<{
    tree: { path: string; size: number; sha: string; type: string }[];
  }>(`/repos/${org}/${slug}/git/trees/${ref}?recursive=true`);

  return tree.tree
    .filter((entry) => entry.type === 'blob')
    .map((entry) => ({
      path: entry.path,
      size: entry.size,
      sha: entry.sha,
      type: 'file' as const,
    }));
}

export async function getFileContent(
  slug: string,
  filePath: string,
  ref = 'main',
  org = GITEA_GENES_ORG,
): Promise<string> {
  const file = await giteaFetch<{ content: string; encoding: string }>(
    `/repos/${org}/${slug}/contents/${filePath}?ref=${encodeURIComponent(ref)}`,
  );

  if (file.encoding === 'base64') {
    return Buffer.from(file.content, 'base64').toString('utf-8');
  }
  return file.content;
}

export async function getArchiveStream(
  slug: string,
  ref: string,
  org = GITEA_GENES_ORG,
): Promise<ReadableStream<Uint8Array>> {
  const res = await giteaFetch<Response>(
    `/repos/${org}/${slug}/archive/${encodeURIComponent(ref)}.tar.gz`,
    { rawResponse: true },
  );
  if (!res.body) throw new Error('No body in archive response');
  return res.body;
}

export async function deleteRepo(slug: string, org = GITEA_GENES_ORG): Promise<void> {
  await giteaFetch(`/repos/${org}/${slug}`, { method: 'DELETE' });
}

export function getRepoUrl(slug: string, org = GITEA_GENES_ORG): string {
  return `${org}/${slug}`;
}
