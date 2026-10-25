import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './browser',
  timeout: 45000,
  expect: {timeout: 15000},
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env.ECOPROOF_BROWSER_BASE_URL,
    channel: process.env.ECOPROOF_BROWSER_CHANNEL || 'chrome',
    headless: true,
    viewport: {width: 1440, height: 1000},
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
