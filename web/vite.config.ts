import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import { evaluationAssets } from './scripts/reports.ts';

// Server-only setting. Do not load repository .env or expose credentials to React.
const origin = process.env.ECOPROOF_API_ORIGIN ?? 'http://127.0.0.1:8000';
const target = new URL(origin);
if (!['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname)
    || target.protocol !== 'http:' || target.username || target.password
    || target.pathname !== '/' || target.search || target.hash) {
  throw new Error('ECOPROOF_API_ORIGIN must be a local HTTP origin without credentials or a path');
}
const proxy = { '/api': { target: target.origin, rewrite: (path: string) => path.replace(/^\/api(?=\/)/, '') } };

export default defineConfig({
  plugins: [react(), evaluationAssets(fileURLToPath(new URL('../reports', import.meta.url)))],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
  test: { include: ['src/**/*.test.ts', 'scripts/**/*.test.ts'] },
});
