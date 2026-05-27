#!/usr/bin/env bash
set -euo pipefail

REGISTRY_URL="http://localhost:3000"
TOKEN="admin-dev-token"
TEST_DIR=$(mktemp -d)

echo "=== E2E Test: Multi-file Gene Publish & Install ==="
echo "Temp dir: ${TEST_DIR}"

# --- Step 1: Create a multi-file test gene ---
echo ""
echo "--- Step 1: Creating multi-file test gene ---"
GENE_DIR="${TEST_DIR}/e2e-multifile-gene"
mkdir -p "${GENE_DIR}/scripts" "${GENE_DIR}/rules"

cat > "${GENE_DIR}/gene.yaml" << 'YAML'
slug: e2e-multifile-gene
name: "E2E Multi-file Gene"
version: "1.0.0"
description: |
  End-to-end test gene with multiple files.
  Tests that all files are properly stored in Gitea and can be retrieved.
short_description: "E2E test gene with multiple files"
category: "development"
tags:
  - "ability"
  - "tool"
icon: "test-tube"
author:
  type: human
  name: e2e-tester
compatibility:
  - product: openclaw
    min_version: "0.1.0"
  - product: generic
    min_version: "0.1.0"
dependencies: []
synergies: []
skill:
  name: e2e-multifile-gene
  always: false
  file: "SKILL.md"
YAML

cat > "${GENE_DIR}/SKILL.md" << 'MD'
# E2E Multi-file Gene

This is a test gene for verifying multi-file support.

## Features
- Multiple file storage
- Git-based versioning
- Tarball distribution

## Usage
This gene is for testing purposes only.
MD

cat > "${GENE_DIR}/scripts/setup.sh" << 'SH'
#!/bin/bash
echo "Setup script for e2e-multifile-gene"
echo "This verifies additional script files work"
SH

cat > "${GENE_DIR}/rules/naming.md" << 'RMD'
# Naming Convention Rules

- Use kebab-case for file names
- Use camelCase for variables
- Use PascalCase for types
RMD

echo "Created gene with $(find ${GENE_DIR} -type f | wc -l | tr -d ' ') files"

# --- Step 2: Publish using CLI ---
echo ""
echo "--- Step 2: Publishing gene via CLI ---"
cd /Users/xzq/Desktop/NoDeskAI/code/genehub
GENEHUB_TOKEN="${TOKEN}" GENEHUB_REGISTRY_URL="${REGISTRY_URL}" \
  npx tsx packages/cli/src/index.ts publish "${GENE_DIR}"

echo ""
echo "--- Step 3: Verify gene via API ---"
echo "Getting gene details..."
GENE_RESPONSE=$(curl -s "${REGISTRY_URL}/api/v1/genes/e2e-multifile-gene")
echo "${GENE_RESPONSE}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
g = d['data']
print(f'  slug: {g[\"slug\"]}')
print(f'  version: {g[\"version\"]}')
print(f'  repository_url: {g.get(\"repository_url\", \"N/A\")}')
print(f'  file_count: {g.get(\"file_count\", 0)}')
"

echo ""
echo "--- Step 4: List gene files via API ---"
FILES_RESPONSE=$(curl -s "${REGISTRY_URL}/api/v1/genes/e2e-multifile-gene/files")
echo "${FILES_RESPONSE}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
files = d['data']
print(f'  File count from API: {len(files)}')
for f in files:
    print(f'    - {f[\"path\"]} ({f.get(\"size\", 0)} bytes)')
"

echo ""
echo "--- Step 5: Read file content via API ---"
SKILL_RESPONSE=$(curl -s "${REGISTRY_URL}/api/v1/genes/e2e-multifile-gene/files/SKILL.md")
echo "${SKILL_RESPONSE}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
content = d['data']['content']
print(f'  SKILL.md content length: {len(content)} chars')
print(f'  First line: {content.split(chr(10))[0]}')
"

SCRIPT_RESPONSE=$(curl -s "${REGISTRY_URL}/api/v1/genes/e2e-multifile-gene/files/scripts/setup.sh")
echo "${SCRIPT_RESPONSE}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
content = d['data']['content']
print(f'  scripts/setup.sh content length: {len(content)} chars')
print(f'  First line: {content.split(chr(10))[0]}')
"

echo ""
echo "--- Step 6: Install gene via CLI ---"
INSTALL_DIR="${TEST_DIR}/installed"
mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"
GENEHUB_TOKEN="${TOKEN}" GENEHUB_REGISTRY_URL="${REGISTRY_URL}" \
  npx tsx /Users/xzq/Desktop/NoDeskAI/code/genehub/packages/cli/src/index.ts \
  install e2e-multifile-gene -p generic --force

echo ""
echo "--- Step 7: Verify installed files ---"
INSTALLED_DIR="${INSTALL_DIR}/.genehub/genes/e2e-multifile-gene"
echo "Installed files:"
if [ -d "${INSTALLED_DIR}" ]; then
  find "${INSTALLED_DIR}" -type f | sort | while read f; do
    echo "  - $(echo $f | sed "s|${INSTALLED_DIR}/||")"
  done
  echo ""
  INSTALLED_COUNT=$(find "${INSTALLED_DIR}" -type f | wc -l | tr -d ' ')
  echo "Total installed files: ${INSTALLED_COUNT}"
else
  echo "  WARNING: Install directory not found at ${INSTALLED_DIR}"
  echo "  Checking what was created..."
  find "${INSTALL_DIR}" -type f | sort | head -20
fi

echo ""
echo "--- Step 8: Publish version 1.1.0 ---"
cd /Users/xzq/Desktop/NoDeskAI/code/genehub

# Update version
sed -i '' 's/version: "1.0.0"/version: "1.1.0"/' "${GENE_DIR}/gene.yaml"
cat >> "${GENE_DIR}/SKILL.md" << 'MD'

## Changelog v1.1.0
- Added new capabilities
MD

GENEHUB_TOKEN="${TOKEN}" GENEHUB_REGISTRY_URL="${REGISTRY_URL}" \
  npx tsx packages/cli/src/index.ts publish "${GENE_DIR}"

echo ""
echo "--- Step 9: Verify versions ---"
VERSIONS_RESPONSE=$(curl -s "${REGISTRY_URL}/api/v1/genes/e2e-multifile-gene/versions")
echo "${VERSIONS_RESPONSE}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
versions = d['data']
print(f'  Version count: {len(versions)}')
for v in versions:
    print(f'    - v{v[\"version\"]} (latest={v[\"is_latest\"]}, tag={v.get(\"git_tag\", \"N/A\")}, sha={v.get(\"commit_sha\", \"N/A\")[:8] if v.get(\"commit_sha\") else \"N/A\"})')
"

# --- Cleanup ---
echo ""
echo "--- Cleanup ---"
# Delete the test gene
curl -s -X DELETE -H "Authorization: Bearer ${TOKEN}" "${REGISTRY_URL}/api/v1/genes/e2e-multifile-gene" > /dev/null
rm -rf "${TEST_DIR}"

echo ""
echo "=== E2E Test PASSED ==="
