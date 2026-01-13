import { defineConfig, devices } from '@playwright/test';
import path from 'path';

/**
 * Playwright configuration for ShopQ Chrome Extension E2E testing
 * Tests the full Gmail integration flow with real browser automation
 */
export default defineConfig({
  testDir: '../e2e',

  // Maximum time one test can run (Gmail can be slow)
  timeout: 120 * 1000,

  // Run tests sequentially to avoid Gmail rate limiting
  fullyParallel: false,
  workers: 1,

  // Fail fast on CI
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Reporter configuration
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['list'],
    ['json', { outputFile: 'test-results/results.json' }]
  ],

  // Shared test configuration
  use: {
    // Base URL for local backend API
    baseURL: 'http://localhost:8000',

    // Collect trace on failure
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Video on failure
    video: 'retain-on-failure',

    // Slow down operations for debugging (set to 0 for normal speed)
    launchOptions: {
      slowMo: process.env.DEBUG ? 100 : 0,
    },
  },

  // Project configuration for Chrome with extension
  // Note: Context and browser launch is handled in fixtures.js to support
  // both regular contexts and persistent contexts (for user Chrome profiles)
  projects: [
    {
      name: 'chrome-extension',
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],

  // Global setup/teardown
  globalSetup: '../e2e/global-setup.js',
  globalTeardown: '../e2e/global-teardown.js',
});
