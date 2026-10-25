import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { Plugin } from 'vite';

export const chartName = /^eval-[a-f0-9]{32}\.png$/;

/** Only the published report and its named PNG, never the repository directory. */
export async function reportAssets(directory: string): Promise<Map<string, Buffer>> {
  const content = await readFile(join(directory, 'eval.json'));
  const report = JSON.parse(content.toString('utf8'));
  if (typeof report.chart !== 'string' || !chartName.test(report.chart)) {
    throw new Error('Evaluation chart must be a generated eval-<id>.png filename');
  }
  const chart = await readFile(join(directory, report.chart));
  if (!chart.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
    throw new Error('Evaluation chart is not a PNG');
  }
  return new Map([['reports/eval.json', content], [`reports/${report.chart}`, chart]]);
}

export function evaluationAssets(directory: string): Plugin {
  return {
    name: 'ecoproof-evaluation-assets',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const path = (req.url ?? '').split('?')[0];
        if (!path.startsWith('/reports/')) return next();
        if (path !== '/reports/eval.json' && !chartName.test(path.slice('/reports/'.length))) {
          res.writeHead(404).end(); return;
        }
        try {
          const assets = await reportAssets(directory);
          const body = assets.get(path.slice(1));
          if (!body) { res.writeHead(404).end(); return; }
          res.writeHead(200, { 'Content-Type': path.endsWith('.png') ? 'image/png' : 'application/json',
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' }).end(body);
        } catch {
          res.writeHead(503, { 'Content-Type': 'application/json' }).end(JSON.stringify({detail: 'Evaluation report or chart is unavailable'}));
        }
      });
    },
    async generateBundle() {
      try {
        for (const [fileName, source] of await reportAssets(directory)) {
          this.emitFile({type: 'asset', fileName, source});
        }
      } catch {
        this.warn('Evaluation report/chart unavailable; the Evaluation view will show an unavailable state.');
      }
    },
  };
}
