import { test, expect, type Page } from '@playwright/test';

if (!process.env.ECOPROOF_BROWSER_BASE_URL || process.env.ECOPROOF_BROWSER_FIXTURE !== 'synthetic') {
  throw new Error('Run this suite through python -m pytest -s tests/test_web.py, which owns the synthetic data and local EVM.');
}
const errors = new WeakMap<Page, string[]>();
test.beforeEach(async ({page}) => {
  errors.set(page, []); page.on('pageerror', error => errors.get(page)!.push(error.message));
  // Only basemap delivery is disabled: all normal data/proof/verify calls use FastAPI.
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
});
test.afterEach(async ({page}) => expect(errors.get(page)).toEqual([]));

async function openProof(page: Page, station = 'Synthetic Central') {
  await page.goto('/#monitor');
  await page.locator('.station-option').filter({hasText: station}).click();
  await page.getByRole('button', {name: 'Inspect record proof'}).click();
  await expect(page.getByLabel('Record JSON')).toBeVisible();
}

test('map, keyboard station selection, wind and nearby time series use the API', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'Air quality, with evidence.'})).toBeVisible();
  await expect(page.locator('.station-pin')).toHaveCount(7);
  await page.getByLabel('Show Synthetic Gardens: Valid').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', {name: 'Synthetic Gardens', exact: true})).toBeVisible();
  await expect(page.locator('.reading-chart')).toBeVisible();
  await page.getByLabel('Compare a nearby station').selectOption('b');
  await expect(page.locator('.chart-legend')).toContainText('Nearby b');
  await expect(page.locator('.reading-inspector .wind')).toContainText('toward 90°');
  await expect(page.getByText('Map tiles unavailable.', {exact: false})).toBeVisible();
  await page.screenshot({path: 'test-results/monitor-desktop.png', fullPage: true});
  await page.getByLabel('Show Synthetic Riverside: Valid').focus();
  await page.keyboard.press('Space');
  await expect(page.getByRole('heading', {name: 'Synthetic Riverside', exact: true, level: 2})).toBeVisible();
  await page.locator('.station-option').filter({hasText: 'Synthetic Sparse'}).click();
  await expect(page.locator('.reading-inspector .badge')).toHaveText('Low confidence');
  await expect(page.getByRole('button', {name: 'Inspect record proof'})).toBeDisabled();
});

test('events filter and reveal saved neighbor evidence', async ({page}) => {
  await page.goto('/');
  await page.getByRole('combobox', {name: 'Show', exact: true}).selectOption('VERIFIED_PLUME_EVENT');
  await expect(page.locator('.event-card')).toHaveCount(1);
  await page.locator('.event-card summary').click();
  await expect(page.locator('.event-card')).toContainText('rose 8 µg/m³');
  await page.getByRole('combobox', {name: 'Show', exact: true}).selectOption('SENSOR_FAULT_DRIFT');
  await expect(page.locator('.event-card')).toContainText('Suspected fault');
  await page.getByRole('button', {name: 'Inspect event readings'}).click();
  await expect(page.getByRole('heading', {name: 'Synthetic Roadside', exact: true, level: 2})).toBeVisible();
});

test('single-leaf proof passes, edited record fails, and restoring passes on the real local EVM', async ({page}) => {
  await openProof(page);
  await expect(page.getByText('Single-record batch:', {exact: false})).toBeVisible();
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await expect(page.getByRole('heading', {name: '✓ Record verified', exact: true})).toBeVisible();
  await expect(page.locator('.verification-result')).toContainText('Local test chain (31337)');
  await expect(page.locator('.verification-result a')).toHaveCount(0);
  await page.screenshot({path: 'test-results/verify-desktop.png', fullPage: true});
  const editor = page.getByLabel('Record JSON'); const original = await editor.inputValue();
  const changed = JSON.parse(original); changed.value += .0001;
  await editor.fill(JSON.stringify(changed));
  await expect(page.locator('.verification-result')).toHaveCount(0);
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Record verification failed', exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Restore saved record'}).click();
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await expect(page.getByRole('heading', {name: '✓ Record verified', exact: true})).toBeVisible();
});

test('odd-leaf path and high-precision edits are verified without browser rounding', async ({page}) => {
  await openProof(page, 'Synthetic Gardens');
  await expect(page.locator('.merkle-path li')).toHaveCount(2);
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await expect(page.getByRole('heading', {name: '✓ Record verified', exact: true})).toBeVisible();
  const editor = page.getByLabel('Record JSON'); const original = await editor.inputValue();
  expect(original).toContain('"value":12.5000');
  await editor.fill(original.replace('"value":12.5000', '"value":12.500050000000000000001'));
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Record verification failed', exact: true})).toBeVisible();
});

test('a delayed success for an old edit cannot become the current verdict', async ({page}) => {
  await openProof(page);
  let release!: () => void, received!: () => void, finished!: () => void;
  const barrier = new Promise<void>(resolve => release = resolve);
  const intercepted = new Promise<void>(resolve => received = resolve);
  const done = new Promise<void>(resolve => finished = resolve);
  await page.route('**/api/verify', async route => {
    const response = await route.fetch(); received(); await barrier;
    try {await route.fulfill({response});} catch { /* Browser has aborted this obsolete upload. */ }
    finally {finished();}
  });
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await intercepted;
  const editor = page.getByLabel('Record JSON');
  await editor.fill((await editor.inputValue()).replace('"value":12.5000', '"value":13.5000'));
  release(); await done;
  await expect(page.locator('.verification-result')).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Verify record', exact: true})).toBeEnabled();
});

test('server validation and chain unavailability never display a verification success', async ({page}) => {
  await openProof(page);
  await page.getByLabel('Record JSON').fill('null');
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await expect(page.getByText('Verification unavailable', {exact: true})).toBeVisible();
  await expect(page.locator('.verification-result')).toHaveCount(0);
  await page.getByRole('button', {name: 'Restore saved record'}).click();
  // Explicit failure fixture; successful checks in other tests use the real EVM.
  await page.route('**/api/verify', route => route.fulfill({status: 503, json: {detail: 'Synthetic RPC unavailable'}}));
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await expect(page.getByText('No verification verdict was returned.')).toBeVisible();
  await expect(page.locator('.verification-result')).toHaveCount(0);
});

test('empty and failed datasets are distinct and cannot manufacture readings', async ({page}) => {
  await page.route('**/api/stations', route => route.fulfill({json: []}));
  await page.route('**/api/events?**', route => route.fulfill({status: 503, json: {detail: 'Synthetic missing Gold fixture'}}));
  await page.goto('/');
  await expect(page.getByText('No stations to plot')).toBeVisible();
  await expect(page.locator('.station-pin')).toHaveCount(0);
  await expect(page.locator('.station-detail')).toHaveCount(0);
  await expect(page.getByText('Event evidence unavailable', {exact: true})).toBeVisible();
  await page.unroute('**/api/stations');
  await page.route('**/api/stations', route => route.fulfill({status: 503, json: {detail: 'Synthetic data unavailable'}}));
  await page.getByRole('button', {name: 'Refresh observations'}).click();
  await expect(page.getByText('Station data unavailable', {exact: true})).toBeVisible();
  await expect(page.locator('.stat strong').first()).toHaveText('—');
});

test('evaluation uses the published JSON and actual chart, without invented metrics', async ({page, request}) => {
  const reportResponse = await request.get('/reports/eval.json'); expect(reportResponse.ok()).toBe(true);
  const report = await reportResponse.json();
  await page.goto('/#evaluation');
  await expect(page.getByText('Synthetic interventions', {exact: true})).toBeVisible();
  const image = page.locator('.evaluation-chart'); await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  if (report.status === 'blocked') {
    await expect(page.getByRole('heading', {name: 'Evaluation has not run'})).toBeVisible();
    await expect(page.locator('table')).toHaveCount(0);
  } else {
    await expect(page.getByRole('heading', {name: 'Detection results'})).toBeVisible();
    await expect(page.locator('tbody tr')).toHaveCount(Object.keys(report.metrics).length * 2);
  }
  await page.screenshot({path: 'test-results/evaluation-desktop.png', fullPage: true});
});

test('mobile navigation, record proof, and evaluation fit without page overflow', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/');
  await expect(page.locator('.station-pin')).toHaveCount(7);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path: 'test-results/monitor-mobile.png', fullPage: true});
  await page.getByRole('button', {name: 'Inspect record proof'}).click();
  await expect(page.getByLabel('Record JSON')).toBeVisible();
  await page.getByRole('button', {name: 'Verify record', exact: true}).click();
  await expect(page.getByRole('heading', {name: '✓ Record verified', exact: true})).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path: 'test-results/verify-mobile.png', fullPage: true});
  await page.getByRole('link', {name: 'Evaluation', exact: true}).click();
  await expect(page.locator('.evaluation-chart')).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
