import { defineConfig } from 'tsup';

export default defineConfig({
  entry: ['src/index.ts', 'src/mcp/index.ts', 'src/db/migrate.ts'],
  format: ['esm'],
  dts: true,
  clean: true,
  sourcemap: true,
  bundle: true,
  noExternal: [/.*/],
  banner: {
    js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);",
  },
});
