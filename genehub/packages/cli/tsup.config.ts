import { defineConfig } from 'tsup';

export default defineConfig({
  entry: ['src/index.ts'],
  format: ['esm'],
  clean: true,
  sourcemap: true,
  banner: { js: '#!/usr/bin/env node' },
  noExternal: ['@nodeskai/genehub-sdk', '@nodeskai/genehub-types'],
});
