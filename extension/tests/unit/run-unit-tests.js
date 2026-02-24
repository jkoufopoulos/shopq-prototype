/**
 * Unit Test Runner for Reclaim Return Watch
 *
 * Runs pure function tests in Node.js without Chrome APIs.
 *
 * Usage: node tests/unit/run-unit-tests.js
 */

const fs = require('fs');
const path = require('path');

// Test state
let totalPassed = 0;
let totalFailed = 0;
let currentSuite = '';

// Console colors
const colors = {
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m',
  bold: '\x1b[1m',
};

/**
 * Assert helper for tests
 */
function assert(condition, message) {
  if (condition) {
    console.log(`  ${colors.green}✓${colors.reset} ${message}`);
    totalPassed++;
    return true;
  } else {
    console.log(`  ${colors.red}✗${colors.reset} ${message}`);
    totalFailed++;
    return false;
  }
}

/**
 * Assert equality helper
 */
function assertEqual(actual, expected, message) {
  const pass = JSON.stringify(actual) === JSON.stringify(expected);
  if (!pass) {
    console.log(`    Expected: ${JSON.stringify(expected)}`);
    console.log(`    Actual:   ${JSON.stringify(actual)}`);
  }
  return assert(pass, message);
}

/**
 * Define a test suite
 */
function describe(name, fn) {
  console.log(`\n${colors.blue}${colors.bold}${name}${colors.reset}`);
  currentSuite = name;
  fn();
}

/**
 * Define a test case
 */
function it(name, fn) {
  try {
    fn();
  } catch (error) {
    console.log(`  ${colors.red}✗${colors.reset} ${name}`);
    console.log(`    ${colors.red}Error: ${error.message}${colors.reset}`);
    totalFailed++;
  }
}

/**
 * Load a module file and execute it in a sandbox
 * Returns the global scope with all defined functions
 */
function loadModule(modulePath) {
  const absolutePath = path.resolve(__dirname, '../../', modulePath);
  const code = fs.readFileSync(absolutePath, 'utf-8');

  // Create a sandbox with common globals
  const sandbox = {
    console: console,
    Date: Date,
    Math: Math,
    JSON: JSON,
    parseInt: parseInt,
    parseFloat: parseFloat,
    isNaN: isNaN,
    String: String,
    Number: Number,
    Array: Array,
    Object: Object,
    RegExp: RegExp,
    Error: Error,
    Promise: Promise,
    Set: Set,
    Map: Map,
    // Mock chrome API (returns empty for storage calls)
    chrome: {
      storage: {
        local: {
          get: async () => ({}),
          set: async () => {},
        }
      }
    },
  };

  // Execute the module code
  const fn = new Function(...Object.keys(sandbox), code);
  fn(...Object.values(sandbox));

  // Return the sandbox which now has the module's functions
  return sandbox;
}

/**
 * Shared context with constants and utilities loaded from schema.js and linker.js
 * This is populated once and reused by all module loads
 */
let sharedContext = null;

/**
 * Initialize shared context with constants and shared functions
 */
function initSharedContext() {
  if (sharedContext) return sharedContext;

  // Base context with globals
  const baseContext = {
    console,
    Date,
    Math,
    JSON,
    parseInt,
    parseFloat,
    isNaN,
    String,
    Number,
    Array,
    Object,
    RegExp,
    Error,
    Promise,
    Set,
    Map,
    Infinity,
    setTimeout,
    encodeURIComponent,
    decodeURIComponent,
    escape,
    atob: (str) => Buffer.from(str, 'base64').toString('binary'),
    btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
    fetch: async () => ({ ok: false }),
    chrome: {
      storage: { local: { get: async () => ({}), set: async () => {} } },
      alarms: { create: () => {}, clear: () => {} },
      tabs: { get: async () => ({}), sendMessage: async () => {} },
      runtime: { id: 'test-extension-id' },
    },
    // Minimal CONFIG stub for modules that reference config constants
    CONFIG: {
      VERSION: '0.0.0-test',
      API_BASE_URL: 'http://localhost:8000',
      GMAIL_API_BASE: 'https://www.googleapis.com/gmail/v1/users/me',
      API_REQUEST_DELAY_MS: 0,
      MAX_MESSAGES_PER_QUERY: 100,
      BATCH_CHUNK_SIZE: 10,
      MESSAGE_RATE_LIMIT_MAX: 100,
      MESSAGE_RATE_LIMIT_WINDOW_MS: 1000,
      VERBOSE_LOGGING: false,
    },
  };

  // Load utils.js to get shared helpers (getToday, etc.)
  const utilsPath = path.resolve(__dirname, '../../modules/shared/utils.js');
  const utilsCode = fs.readFileSync(utilsPath, 'utf-8');
  const utilsWrapped = `
    ${utilsCode}
    return { getToday, extractDomain, redactForLog, sleep, logVerbose };
  `;
  const utilsFn = new Function(...Object.keys(baseContext), utilsWrapped);
  const utilsExports = utilsFn(...Object.values(baseContext));
  Object.assign(baseContext, utilsExports);

  // Load schema.js to get constants
  const schemaPath = path.resolve(__dirname, '../../modules/storage/schema.js');
  const schemaCode = fs.readFileSync(schemaPath, 'utf-8');
  const schemaWrapped = `
    ${schemaCode}
    return { STORAGE_KEYS, ORDER_STATUS, DEADLINE_CONFIDENCE, EMAIL_TYPE, generateOrderKey: hashOrderKey, createOrder, createOrderEmail };
  `;
  const schemaFn = new Function(...Object.keys(baseContext), schemaWrapped);
  const schemaExports = schemaFn(...Object.values(baseContext));

  // Add schema exports to context
  Object.assign(baseContext, schemaExports);

  // Load linker.js to get extractOrderId and extractTrackingNumber
  const linkerPath = path.resolve(__dirname, '../../modules/pipeline/linker.js');
  const linkerCode = fs.readFileSync(linkerPath, 'utf-8');
  const linkerWrapped = `
    ${linkerCode}
    return { extractOrderId, extractTrackingNumber, extractPrimaryKeys };
  `;
  const linkerFn = new Function(...Object.keys(baseContext), linkerWrapped);
  const linkerExports = linkerFn(...Object.values(baseContext));

  // Add linker exports to context
  Object.assign(baseContext, linkerExports);

  // Stub for computeNormalizedMerchant (defined in store.js, used by resolution.js + scanner.js).
  baseContext.computeNormalizedMerchant = function(order) {
    if (order.normalized_merchant) return order.normalized_merchant;
    let domain = (order.merchant_domain || '').toLowerCase().trim();
    domain = domain.replace(/^(www\.|shop\.|store\.|mail\.|email\.|orders?\.)/, '');
    return domain || (order.merchant_display_name || '').toLowerCase().replace(/[^a-z0-9]/g, '') || null;
  };

  // Stubs for scanner.js dependencies (only needed for module loading, not for pure function tests)
  baseContext.refreshState = { gmailTabId: null };
  baseContext.filterEmail = () => ({ blocked: false });
  baseContext.getAuthToken = async () => null;
  baseContext.getAuthenticatedUserId = async () => 'test-user';
  baseContext.getLastScanState = async () => ({ epoch_ms: 0, internal_date_ms: 0, window_days: 14 });
  baseContext.isEmailProcessed = async () => false;
  baseContext.markEmailProcessed = async () => {};
  baseContext.upsertOrder = async (o) => o;
  baseContext.cancelOrderByOrderId = async () => null;
  baseContext.processEmailBatch = async () => ({ success: false });
  baseContext.updateLastScanState = async () => {};
  baseContext.beginResolutionStats = () => {};
  baseContext.endResolutionStats = () => {};
  baseContext.getResolutionStats = () => null;
  baseContext.deduplicateStoredOrders = async () => ({ merged: 0 });
  baseContext.broadcastScanProgress = () => {};

  sharedContext = baseContext;
  return sharedContext;
}

/**
 * Load module and extract functions defined at global scope
 */
function loadModuleFunctions(modulePath) {
  const absolutePath = path.resolve(__dirname, '../../', modulePath);
  const code = fs.readFileSync(absolutePath, 'utf-8');

  // Get shared context with constants and utilities
  const context = { ...initSharedContext() };

  // Build wrapper that captures defined functions
  const wrappedCode = `
    ${code}
    return {
      ${extractFunctionNames(code).join(',\n      ')}
    };
  `;

  try {
    const fn = new Function(...Object.keys(context), wrappedCode);
    return fn(...Object.values(context));
  } catch (error) {
    console.error(`Error loading ${modulePath}: ${error.message}`);
    return {};
  }
}

/**
 * Extract function names from code
 */
function extractFunctionNames(code) {
  const functionPattern = /(?:async\s+)?function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(/g;
  const names = [];
  let match;
  while ((match = functionPattern.exec(code)) !== null) {
    names.push(match[1]);
  }
  return [...new Set(names)];
}

// Make helpers available globally for test files
global.assert = assert;
global.assertEqual = assertEqual;
global.describe = describe;
global.it = it;
global.loadModuleFunctions = loadModuleFunctions;
global.colors = colors;

/**
 * Run all unit tests
 */
async function runAllTests() {
  console.log(`${colors.bold}╔══════════════════════════════════════════╗${colors.reset}`);
  console.log(`${colors.bold}║   Reclaim Return Watch - Unit Tests        ║${colors.reset}`);
  console.log(`${colors.bold}╚══════════════════════════════════════════╝${colors.reset}`);

  const testFiles = [
    'filter.test.js',
    'classifier.test.js',
    'extractor.test.js',
    'evidence.test.js',
    'lifecycle.test.js',
    'resolution.test.js',
    'scanner.test.js',
  ];

  for (const file of testFiles) {
    const testPath = path.join(__dirname, file);
    if (fs.existsSync(testPath)) {
      console.log(`\n${colors.yellow}▶ Running ${file}${colors.reset}`);
      try {
        require(testPath);
      } catch (error) {
        console.error(`${colors.red}Error in ${file}: ${error.message}${colors.reset}`);
        console.error(error.stack);
      }
    } else {
      console.log(`${colors.yellow}⚠ Skipping ${file} (not found)${colors.reset}`);
    }
  }

  // Print summary
  console.log(`\n${colors.bold}═══════════════════════════════════════════${colors.reset}`);
  console.log(`${colors.bold}SUMMARY${colors.reset}`);
  console.log(`${colors.bold}═══════════════════════════════════════════${colors.reset}`);
  console.log(`  ${colors.green}Passed: ${totalPassed}${colors.reset}`);
  console.log(`  ${colors.red}Failed: ${totalFailed}${colors.reset}`);
  console.log(`  Total:  ${totalPassed + totalFailed}`);
  console.log(`${colors.bold}═══════════════════════════════════════════${colors.reset}`);

  // Exit with error code if tests failed
  process.exit(totalFailed > 0 ? 1 : 0);
}

// Run tests
runAllTests();
