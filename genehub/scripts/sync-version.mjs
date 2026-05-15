#!/usr/bin/env node
/**
 * Reads the canonical version from /VERSION and syncs it to all package.json
 * files across the monorepo.
 *
 * VERSION format:  yyyy-MM-dd[-tag]     e.g. 2026-02-28, 2026-02-28-alpha
 * npm format:      yyyy.M.d[-tag]       e.g. 2026.2.28,  2026.2.28-alpha
 * git tag:         vyyyy-MM-dd[-tag]    e.g. v2026-02-28
 *
 * Usage:
 *   node scripts/sync-version.mjs           # sync VERSION → all package.json
 *   node scripts/sync-version.mjs --check   # verify all versions match (CI)
 *   node scripts/sync-version.mjs --tag     # print the git tag name
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const PACKAGES = [
  'package.json',
  'packages/types/package.json',
  'packages/sdk/typescript/package.json',
  'packages/cli/package.json',
  'packages/registry/package.json',
  'packages/web/package.json',
];

function readVersion() {
  return readFileSync(resolve(ROOT, 'VERSION'), 'utf-8').trim();
}

function toNpmVersion(canonical) {
  const match = canonical.match(/^(\d{4})-(\d{2})-(\d{2})(.*)$/);
  if (!match) {
    throw new Error(`Invalid VERSION format: "${canonical}" (expected yyyy-MM-dd[-tag])`);
  }
  const [, year, month, day, tag] = match;
  return `${year}.${Number(month)}.${Number(day)}${tag}`;
}

function toGitTag(canonical) {
  return `v${canonical}`;
}

function syncAll(npmVersion) {
  const updated = [];
  for (const rel of PACKAGES) {
    const abs = resolve(ROOT, rel);
    let content;
    try {
      content = readFileSync(abs, 'utf-8');
    } catch {
      continue;
    }
    const pkg = JSON.parse(content);
    if (pkg.version === npmVersion) continue;
    pkg.version = npmVersion;
    writeFileSync(abs, JSON.stringify(pkg, null, 2) + '\n');
    updated.push(rel);
  }
  return updated;
}

function checkAll(npmVersion) {
  const mismatched = [];
  for (const rel of PACKAGES) {
    const abs = resolve(ROOT, rel);
    let content;
    try {
      content = readFileSync(abs, 'utf-8');
    } catch {
      continue;
    }
    const pkg = JSON.parse(content);
    if (pkg.version !== npmVersion) {
      mismatched.push({ file: rel, current: pkg.version, expected: npmVersion });
    }
  }
  return mismatched;
}

const canonical = readVersion();
const npmVersion = toNpmVersion(canonical);
const args = process.argv.slice(2);

if (args.includes('--tag')) {
  console.log(toGitTag(canonical));
  process.exit(0);
}

if (args.includes('--npm-version')) {
  console.log(npmVersion);
  process.exit(0);
}

if (args.includes('--check')) {
  const mismatched = checkAll(npmVersion);
  if (mismatched.length === 0) {
    console.log(`✓ All packages match VERSION ${canonical} (npm: ${npmVersion})`);
    process.exit(0);
  }
  console.error(`✗ Version mismatch (expected ${npmVersion} from VERSION "${canonical}"):`);
  for (const m of mismatched) {
    console.error(`  ${m.file}: ${m.current} → ${m.expected}`);
  }
  process.exit(1);
}

const updated = syncAll(npmVersion);
if (updated.length === 0) {
  console.log(`All packages already at ${npmVersion} (VERSION: ${canonical})`);
} else {
  console.log(`Synced VERSION ${canonical} → npm ${npmVersion}`);
  for (const f of updated) {
    console.log(`  updated: ${f}`);
  }
}
