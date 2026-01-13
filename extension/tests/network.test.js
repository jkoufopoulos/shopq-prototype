/**
 * Network resiliency tests for utilities.
 *
 * Run with: node extension/tests/network.test.js
 */

const fs = require('fs');
const path = require('path');

// Ensure console exists
if (typeof console === 'undefined') {
  global.console = { log: () => {}, warn: () => {}, error: () => {} };
}

// Load utils.js globals
const utilsPath = path.join(__dirname, '../modules/shared/utils.js');
const utilsCode = fs.readFileSync(utilsPath, 'utf8');
eval(utilsCode);

class TestRunner {
  constructor() {
    this.tests = [];
    this.passed = 0;
    this.failed = 0;
  }

  test(name, fn) {
    this.tests.push({ name, fn });
  }

  async run() {
    console.log('\n🧪 Running network resiliency tests\n');
    console.log('='.repeat(60));

    for (const { name, fn } of this.tests) {
      try {
        await fn();
        this.passed++;
        console.log(`✅ PASS: ${name}`);
      } catch (error) {
        this.failed++;
        console.log(`❌ FAIL: ${name}`);
        console.log(`   Error: ${error.message}`);
      }
    }

    console.log('='.repeat(60));
    console.log(`\n📊 Results: ${this.passed} passed, ${this.failed} failed\n`);

    if (this.failed > 0) {
      process.exit(1);
    }
  }
}

function assertEquals(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message || 'Assertion failed'}: expected ${expected}, got ${actual}`);
  }
}

function assertMatches(value, regex, message) {
  if (!regex.test(value)) {
    throw new Error(`${message || 'Assertion failed'}: "${value}" does not match ${regex}`);
  }
}

const runner = new TestRunner();

runner.test('redactForLog produces hashed preview', () => {
  const redacted = redactForLog('sensitive-string-value');
  assertMatches(redacted, /^.{1,8}…#[A-Za-z0-9]{1,8}$/, 'Output should contain preview and hash');
});

runner.test('resilientFetch succeeds without retries', async () => {
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
      text: async () => 'ok'
    };
  };

  const response = await resilientFetch(
    'https://api.test/ok',
    {},
    { fetchImpl, retries: 0, timeoutMs: 100, retryDelayMs: 0, jitterMs: 0 }
  );

  assertEquals(calls, 1, 'fetch should be called once');
  assertEquals(response.status, 200, 'response status should be 200');
});

runner.test('resilientFetch retries on 500 and then succeeds', async () => {
  const responses = [
    { ok: false, status: 500, json: async () => ({}), text: async () => 'error' },
    { ok: true, status: 200, json: async () => ({ ok: true }), text: async () => 'ok' }
  ];
  let calls = 0;

  const fetchImpl = async () => {
    const response = responses[calls];
    calls += 1;
    return response;
  };

  const response = await resilientFetch(
    'https://api.test/retry',
    {},
    { fetchImpl, retries: 2, timeoutMs: 100, retryDelayMs: 0, jitterMs: 0 }
  );

  assertEquals(calls, 2, 'fetch should be called twice');
  assertEquals(response.status, 200, 'response status should become 200');
});

runner.run();
