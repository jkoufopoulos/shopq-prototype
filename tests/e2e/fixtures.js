/**
 * Playwright test fixtures for ShopQ extension testing
 * Provides reusable utilities for Gmail and extension interaction
 */

import { test as base, chromium } from '@playwright/test';
import path from 'path';

/**
 * Extended test fixture with Gmail and extension helpers
 */
export const test = base.extend({
  // Override context to use persistent context when CHROME_USER_DATA is set
  context: async ({}, use) => {
    const userDataDir = process.env.CHROME_USER_DATA;
    const extensionPath = path.resolve('./extension');

    let context;

    if (userDataDir) {
      // Use persistent context with user's Chrome profile
      console.log(`📁 Using Chrome profile: ${userDataDir}`);

      context = await chromium.launchPersistentContext(userDataDir, {
        headless: false,
        args: [
          `--disable-extensions-except=${extensionPath}`,
          `--load-extension=${extensionPath}`,
          '--no-sandbox',
          '--disable-setuid-sandbox',
        ],
        channel: 'chrome',
        viewport: { width: 1920, height: 1080 },
      });
    } else {
      // Use regular context without persistent profile
      const browser = await chromium.launch({
        headless: false,
        args: [
          `--disable-extensions-except=${extensionPath}`,
          `--load-extension=${extensionPath}`,
          '--no-sandbox',
          '--disable-setuid-sandbox',
        ],
        channel: 'chrome',
      });

      context = await browser.newContext({
        viewport: { width: 1920, height: 1080 },
      });
    }

    await use(context);
    await context.close();
  },

  // Override page to use the page from our custom context
  page: async ({ context }, use) => {
    const pages = context.pages();
    const page = pages.length > 0 ? pages[0] : await context.newPage();
    await use(page);
  },
  /**
   * Gmail page helper - provides utilities for interacting with Gmail
   */
  gmailPage: async ({ page, context }, use) => {
    const helpers = {
      /**
       * Navigate to Gmail and wait for it to load
       */
      async goto() {
        await page.goto('https://mail.google.com/mail/u/0/#inbox');
        await page.waitForLoadState('networkidle');
        // Wait for Gmail to fully initialize
        await page.waitForTimeout(2000);
      },

      /**
       * Get all emails in current view
       */
      async getEmails() {
        // Try multiple selectors for email rows
        const selectors = [
          'tr[role="row"]',
          '.zA',
          '[data-legacy-thread-id]',
          '[data-thread-id]'
        ];

        for (const selector of selectors) {
          const emails = await page.$$(selector);
          if (emails.length > 0) {
            return emails;
          }
        }

        return [];
      },

      /**
       * Get email by subject (partial match)
       */
      async getEmailBySubject(subject) {
        const emails = await this.getEmails();

        for (const email of emails) {
          const text = await email.textContent();
          if (text && text.includes(subject)) {
            return email;
          }
        }

        return null;
      },

      /**
       * Get labels for a specific email
       */
      async getEmailLabels(emailElement) {
        // Try to find label elements within email row
        const labelSelectors = [
          '.ar', // Gmail label class
          '.xY', // Alternative label class
          '[data-tooltip*="Labels"]',
          'span[title]'
        ];

        const labels = [];
        for (const selector of labelSelectors) {
          const labelElements = await emailElement.$$(selector);
          for (const label of labelElements) {
            const text = await label.textContent();
            if (text && text.trim()) {
              labels.push(text.trim());
            }
          }
        }

        return labels;
      },

      /**
       * Search Gmail using search box
       */
      async search(query) {
        const searchBox = await page.$('input[aria-label="Search mail"]');
        if (!searchBox) {
          throw new Error('Gmail search box not found');
        }

        await searchBox.fill(query);
        await searchBox.press('Enter');
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1000);
      },

      /**
       * Count emails in current view
       */
      async countEmails() {
        const emails = await this.getEmails();
        return emails.length;
      },

      /**
       * Check if an email has a specific label
       */
      async emailHasLabel(emailElement, labelName) {
        const labels = await this.getEmailLabels(emailElement);
        return labels.some(label => label.includes(labelName));
      },

      /**
       * Wait for extension to finish processing
       * Monitors console logs for completion messages
       */
      async waitForExtensionProcessing(timeout = 30000) {
        return new Promise((resolve, reject) => {
          const timeoutId = setTimeout(() => {
            reject(new Error('Extension processing timeout'));
          }, timeout);

          page.on('console', (msg) => {
            const text = msg.text();
            // Look for completion messages
            if (text.includes('labeled successfully') ||
                text.includes('No more unlabeled emails')) {
              clearTimeout(timeoutId);
              resolve();
            }
          });
        });
      },

      /**
       * Trigger ShopQ auto-organize by clicking extension icon
       */
      async triggerAutoOrganize() {
        // Get extension ID from background page
        const backgroundPages = context.backgroundPages();
        if (backgroundPages.length === 0) {
          throw new Error('Extension background page not found');
        }

        // Trigger organize via message to extension
        await page.evaluate(() => {
          chrome.runtime.sendMessage({ action: 'organizeNow' });
        });

        // Wait for processing to complete
        await this.waitForExtensionProcessing();
      },

      /**
       * Get extension console logs
       */
      async getExtensionLogs() {
        const logs = [];
        page.on('console', (msg) => {
          logs.push({
            type: msg.type(),
            text: msg.text(),
            timestamp: new Date().toISOString()
          });
        });
        return logs;
      },

      /**
       * Check if email is in inbox
       */
      async isInInbox(subject) {
        await page.goto('https://mail.google.com/mail/u/0/#inbox');
        await page.waitForLoadState('networkidle');
        const email = await this.getEmailBySubject(subject);
        return email !== null;
      },

      /**
       * Remove all ShopQ labels from an email
       */
      async removeShopQLabels(emailElement) {
        // Click on email to open
        await emailElement.click();
        await page.waitForTimeout(500);

        // Find and click label button
        const labelButton = await page.$('button[aria-label*="Labels"]');
        if (!labelButton) {
          return;
        }

        await labelButton.click();
        await page.waitForTimeout(500);

        // Find all ShopQ labels and uncheck them
        const mailqLabels = await page.$$('div[role="menuitemcheckbox"]:has-text("ShopQ")');
        for (const label of mailqLabels) {
          const isChecked = await label.getAttribute('aria-checked');
          if (isChecked === 'true') {
            await label.click();
            await page.waitForTimeout(200);
          }
        }

        // Close label menu
        await page.keyboard.press('Escape');
        await page.waitForTimeout(500);
      }
    };

    await use(helpers);
  },

  /**
   * Extension background page helper
   */
  extensionBackground: async ({ context }, use) => {
    const helpers = {
      /**
       * Get extension background page
       */
      async getBackgroundPage() {
        const backgroundPages = context.backgroundPages();
        if (backgroundPages.length === 0) {
          // Wait a bit for extension to initialize
          await new Promise(resolve => setTimeout(resolve, 2000));
          const pages = context.backgroundPages();
          if (pages.length === 0) {
            throw new Error('Extension background page not found - extension may not be loaded');
          }
          return pages[0];
        }
        return backgroundPages[0];
      },

      /**
       * Execute code in extension background context
       */
      async evaluate(fn, ...args) {
        const bg = await this.getBackgroundPage();
        return bg.evaluate(fn, ...args);
      },

      /**
       * Get extension ID
       */
      async getExtensionId() {
        const bg = await this.getBackgroundPage();
        return bg.url().match(/chrome-extension:\/\/([a-z]+)\//)?.[1];
      }
    };

    await use(helpers);
  }
});

export { expect } from '@playwright/test';
