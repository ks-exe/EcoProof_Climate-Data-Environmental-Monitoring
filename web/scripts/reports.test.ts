import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { afterEach, beforeEach, expect, it } from 'vitest';
import { reportAssets } from './reports';

const directories: string[] = [];
beforeEach(async () => { await mkdir(resolve('node_modules/.cache'), {recursive: true}); });
afterEach(async () => {
  for (const directory of directories.splice(0)) {
    if (!directory.startsWith(resolve('node_modules/.cache/report-test-'))) throw new Error('Unexpected test cleanup path');
    await rm(directory, {recursive: true, force: true});
  }
});
it('packages exactly the actual report and referenced chart bytes', async () => {
  const directory = resolve('../reports');
  const assets = await reportAssets(directory);
  const source = await readFile(join(directory, 'eval.json'));
  const report = JSON.parse(source.toString());
  expect([...assets.keys()]).toEqual(['reports/eval.json', `reports/${report.chart}`]);
  expect(assets.get('reports/eval.json')).toEqual(source);
  expect(assets.get(`reports/${report.chart}`)).toEqual(await readFile(join(directory, report.chart)));
});
it('rejects path traversal instead of packaging another file', async () => {
  const directory = await mkdtemp(resolve('node_modules/.cache/report-test-')); directories.push(directory);
  await writeFile(join(directory, 'eval.json'), JSON.stringify({chart: '../../.env'}));
  await expect(reportAssets(directory)).rejects.toThrow('generated eval-<id>.png');
});
it('rejects a non-PNG chart', async () => {
  const directory = await mkdtemp(resolve('node_modules/.cache/report-test-')); directories.push(directory);
  const chart = `eval-${'a'.repeat(32)}.png`;
  await writeFile(join(directory, 'eval.json'), JSON.stringify({chart}));
  await writeFile(join(directory, chart), '<html>not a chart</html>');
  await expect(reportAssets(directory)).rejects.toThrow('not a PNG');
});
