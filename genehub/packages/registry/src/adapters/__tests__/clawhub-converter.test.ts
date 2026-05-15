import { describe, expect, it } from 'vitest';
import type { ClawHubSkillVersion } from '../clawhub/client.js';
import {
  type ClawHubSkillPayload,
  convertClawHubSkill,
  extractClawHubMetadata,
  isSkillSafe,
} from '../clawhub/converter.js';

function makePayload(overrides: Partial<ClawHubSkillPayload> = {}): ClawHubSkillPayload {
  return {
    detail: {
      skill: {
        slug: 'my-skill',
        displayName: 'My Skill',
        summary: 'A useful skill for testing',
        tags: {},
        stats: { installs: 120, stars: 4 },
        createdAt: 1700000000000,
        updatedAt: 1700100000000,
      },
      latestVersion: {
        version: '2.1.0',
        createdAt: 1700100000000,
        changelog: 'bug fixes',
      },
      owner: {
        handle: 'alice',
        displayName: 'Alice Dev',
        image: null,
      },
    },
    version: {
      version: {
        version: '2.1.0',
        createdAt: 1700100000000,
        changelog: 'bug fixes',
        security: { status: 'clean', hasWarnings: false, checkedAt: 1700100000000, model: null },
      },
      skill: { slug: 'my-skill', displayName: 'My Skill' },
    },
    instructionsContent: '# My Skill\nDo great things.',
    ...overrides,
  };
}

function getSkill(p: ClawHubSkillPayload) {
  const s = p.detail.skill;
  if (!s) throw new Error('skill is null in test fixture');
  return s;
}

// ---------------------------------------------------------------------------
// isSkillSafe
// ---------------------------------------------------------------------------

describe('isSkillSafe', () => {
  it('returns true for clean security status', () => {
    const ver: ClawHubSkillVersion = {
      version: {
        version: '1.0.0',
        createdAt: 0,
        changelog: '',
        security: { status: 'clean', hasWarnings: false, checkedAt: 0, model: null },
      },
      skill: null,
    };
    expect(isSkillSafe(ver)).toBe(true);
  });

  it('returns true when no security field is present', () => {
    const ver: ClawHubSkillVersion = {
      version: { version: '1.0.0', createdAt: 0, changelog: '' },
      skill: null,
    };
    expect(isSkillSafe(ver)).toBe(true);
  });

  it('returns false for malicious status', () => {
    const ver: ClawHubSkillVersion = {
      version: {
        version: '1.0.0',
        createdAt: 0,
        changelog: '',
        security: { status: 'malicious', hasWarnings: true, checkedAt: 0, model: null },
      },
      skill: null,
    };
    expect(isSkillSafe(ver)).toBe(false);
  });

  it('returns false for suspicious status', () => {
    const ver: ClawHubSkillVersion = {
      version: {
        version: '1.0.0',
        createdAt: 0,
        changelog: '',
        security: { status: 'suspicious', hasWarnings: true, checkedAt: 0, model: null },
      },
      skill: null,
    };
    expect(isSkillSafe(ver)).toBe(false);
  });

  it('returns true for pending status', () => {
    const ver: ClawHubSkillVersion = {
      version: {
        version: '1.0.0',
        createdAt: 0,
        changelog: '',
        security: { status: 'pending', hasWarnings: false, checkedAt: null, model: null },
      },
      skill: null,
    };
    expect(isSkillSafe(ver)).toBe(true);
  });

  it('returns false when version object itself is null', () => {
    expect(isSkillSafe(null)).toBe(false);
  });

  it('returns false when version.version is null', () => {
    const ver: ClawHubSkillVersion = { version: null, skill: null };
    expect(isSkillSafe(ver)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// convertClawHubSkill
// ---------------------------------------------------------------------------

describe('convertClawHubSkill', () => {
  it('maps core fields correctly', () => {
    const result = convertClawHubSkill(makePayload());
    expect(result.slug).toBe('my-skill');
    expect(result.name).toBe('My Skill');
    expect(result.version).toBe('2.1.0');
    expect(result.description).toBe('A useful skill for testing');
    expect(result.short_description).toBe('A useful skill for testing');
  });

  it('sets skill.content from instructionsContent', () => {
    const result = convertClawHubSkill(makePayload());
    expect(result.skill.content).toBe('# My Skill\nDo great things.');
    expect(result.skill.name).toBe('My Skill');
  });

  it('sets author from owner', () => {
    const result = convertClawHubSkill(makePayload());
    expect(result.author).toEqual({ type: 'human', name: 'Alice Dev', ref: 'alice' });
  });

  it('defaults compatibility to openclaw', () => {
    const result = convertClawHubSkill(makePayload());
    expect(result.compatibility).toEqual([{ product: 'openclaw', min_version: '0.0.0' }]);
  });

  it('defaults version to 1.0.0 when no version info', () => {
    const p = makePayload();
    p.detail.latestVersion = null;
    p.version = null;
    const result = convertClawHubSkill(p);
    expect(result.version).toBe('1.0.0');
  });

  it('handles null summary gracefully', () => {
    const p = makePayload();
    getSkill(p).summary = null;
    const result = convertClawHubSkill(p);
    expect(result.description).toBe('');
    expect(result.short_description).toBe('');
  });

  it('truncates long summary for short_description', () => {
    const p = makePayload();
    getSkill(p).summary = 'x'.repeat(300);
    const result = convertClawHubSkill(p);
    expect(result.short_description.length).toBeLessThanOrEqual(256);
  });

  it('handles null owner', () => {
    const p = makePayload();
    p.detail.owner = null;
    const result = convertClawHubSkill(p);
    expect(result.author).toEqual({ type: 'human', name: '', ref: '' });
  });

  it('normalizes slug with special characters', () => {
    const p = makePayload();
    getSkill(p).slug = 'My_Weird.Skill Name!';
    const result = convertClawHubSkill(p);
    expect(result.slug).toMatch(/^[a-z0-9-]+$/);
    expect(result.slug).not.toMatch(/--/);
  });

  it('sets source to clawhub', () => {
    const result = convertClawHubSkill(makePayload());
    expect(result.compatibility[0].product).toBe('openclaw');
  });

  it('defaults tags to ["ability"] when no metadata hints', () => {
    const result = convertClawHubSkill(makePayload());
    expect(result.tags).toEqual(['ability']);
  });

  it('infers tags as ["tool"] when install metadata is present', () => {
    const p = makePayload();
    getSkill(p).tags = {
      install: [{ id: 'node', kind: 'node', package: 'some-pkg' }],
    };
    const result = convertClawHubSkill(p);
    expect(result.tags).toEqual(['tool']);
  });

  it('infers tags as ["tool"] when requires.bins is present', () => {
    const p = makePayload();
    getSkill(p).tags = {
      requires: { bins: ['docker'] },
    };
    const result = convertClawHubSkill(p);
    expect(result.tags).toEqual(['tool']);
  });

  it('maps requires into config.openclaw', () => {
    const p = makePayload();
    getSkill(p).tags = {
      requires: { bins: ['git'], env: ['GITHUB_TOKEN'] },
    };
    const result = convertClawHubSkill(p);
    expect(result.config?.openclaw?.openclaw_config).toEqual({
      requires_bins: ['git'],
      requires_env: ['GITHUB_TOKEN'],
    });
  });

  it('skips config when no requires metadata', () => {
    const result = convertClawHubSkill(makePayload());
    expect(result.config).toBeUndefined();
  });

  it('converts dependencies from metadata', () => {
    const p = makePayload();
    getSkill(p).tags = {
      dependencies: [
        { name: 'some-dep', type: 'npm', version: '>=2.0.0' },
        { name: 'another', type: 'pip' },
      ],
    };
    const result = convertClawHubSkill(p);
    expect(result.dependencies).toEqual([
      { slug: 'some-dep', version: '>=2.0.0', optional: false },
      { slug: 'another', version: '*', optional: false },
    ]);
  });

  it('throws when detail.skill is null', () => {
    const p = makePayload();
    p.detail.skill = null;
    expect(() => convertClawHubSkill(p)).toThrow();
  });
});

// ---------------------------------------------------------------------------
// extractClawHubMetadata
// ---------------------------------------------------------------------------

describe('extractClawHubMetadata', () => {
  it('extracts source and stats correctly', () => {
    const meta = extractClawHubMetadata(makePayload());
    expect(meta.source).toBe('clawhub');
    expect(meta.source_ref).toBe('https://clawhub.ai/skills/my-skill');
    expect(meta.install_count).toBe(120);
    expect(meta.avg_rating).toBe(4);
    expect(meta.is_published).toBe(false);
  });

  it('defaults stats when not present', () => {
    const p = makePayload();
    getSkill(p).stats = {};
    const meta = extractClawHubMetadata(p);
    expect(meta.install_count).toBe(0);
    expect(meta.avg_rating).toBe(0);
  });
});
