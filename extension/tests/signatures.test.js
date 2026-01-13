/**
 * Unit Tests for signatures.js
 *
 * Tests subject signature generation for cache keys.
 * Run with: node extension/tests/signatures.test.js
 */

const fs = require('fs');
const path = require('path');

// Load signatures.js
const signaturesPath = path.join(__dirname, '../modules/shared/signatures.js');
const signaturesCode = fs.readFileSync(signaturesPath, 'utf8');
eval(signaturesCode);

// Test harness
class TestRunner {
  constructor() {
    this.passed = 0;
    this.failed = 0;
  }

  assertEqual(actual, expected, message) {
    if (actual === expected) {
      console.log(`  ✅ ${message}`);
      this.passed++;
    } else {
      console.error(`  ❌ ${message}`);
      console.error(`     Expected: "${expected}"`);
      console.error(`     Actual:   "${actual}"`);
      this.failed++;
    }
  }

  assert(condition, message) {
    if (condition) {
      console.log(`  ✅ ${message}`);
      this.passed++;
    } else {
      console.error(`  ❌ ${message}`);
      this.failed++;
    }
  }

  summary() {
    console.log('\n' + '='.repeat(60));
    console.log(`📊 SUMMARY: ${this.passed} passed, ${this.failed} failed`);
    console.log('='.repeat(60));
    return this.failed === 0;
  }
}

const test = new TestRunner();

console.log('\n🧪 Running signatures.js Tests\n');
console.log('='.repeat(60));

// Test generateSubjectSignature - strips Re:/Fwd:
console.log('\n📧 Reply/Forward prefix removal:');
test.assertEqual(
  generateSubjectSignature('Re: Your order has shipped'),
  'your order has shipped',
  'Remove Re: prefix'
);
test.assertEqual(
  generateSubjectSignature('Fwd: Important meeting'),
  'important meeting',
  'Remove Fwd: prefix'
);
test.assertEqual(
  generateSubjectSignature('re: RE: Re: Multiple prefixes'),
  're: re: multiple prefixes',
  'Remove first re: prefix only'
);

// Test order ID normalization
console.log('\n🔢 Order ID normalization:');
test.assertEqual(
  generateSubjectSignature('Your Order #123456 has shipped'),
  'your order <id> has shipped',
  'Replace order number with <ID>'
);
test.assertEqual(
  generateSubjectSignature('Receipt for order 98765'),
  'receipt for order <id>',
  'Replace 5+ digit numbers with <ID>'
);
test.assertEqual(
  generateSubjectSignature('Tracking: ABC123XYZ456'),
  'tracking: <id>',
  'Replace alphanumeric IDs'
);

// Test date removal
console.log('\n📅 Date pattern removal:');
test.assertEqual(
  generateSubjectSignature('Delivered: Charmin Ultra Strong Oct 23'),
  'delivered: charmin ultra strong 23',
  'Remove month name (day remains)'
);
test.assertEqual(
  generateSubjectSignature('Your 2024 Annual Report'),
  'your annual report',
  'Remove year'
);
test.assertEqual(
  generateSubjectSignature('Meeting on 12/25 is confirmed'),
  'meeting on is confirmed',
  'Remove date pattern MM/DD'
);

// Test emoji removal (basic)
console.log('\n😀 Emoji removal:');
const withEmoji = 'Your order 🎉 has shipped';
const cleaned = generateSubjectSignature(withEmoji);
test.assert(
  !cleaned.includes('🎉'),
  'Remove emoji from subject'
);

// Test whitespace normalization
console.log('\n⬜ Whitespace normalization:');
test.assertEqual(
  generateSubjectSignature('Your  order   has    shipped'),
  'your order has shipped',
  'Collapse multiple spaces'
);
test.assertEqual(
  generateSubjectSignature('  Trim spaces  '),
  'trim spaces',
  'Trim leading/trailing spaces'
);

// Test empty/null handling
console.log('\n🚫 Edge cases:');
test.assertEqual(
  generateSubjectSignature(''),
  '',
  'Handle empty string'
);
test.assertEqual(
  generateSubjectSignature(null),
  '',
  'Handle null input'
);
test.assertEqual(
  generateSubjectSignature(undefined),
  '',
  'Handle undefined input'
);

// Test generateCacheKey
console.log('\n🔑 generateCacheKey() tests:');
const key3 = generateCacheKey('user@example.com', 'Receipt for purchase');
const key4 = generateCacheKey('other@test.com', 'Receipt for purchase');
test.assert(
  key3 !== key4,
  'Different keys for different senders'
);

const key7 = generateCacheKey('user@example.com', 'Test');
const key8 = generateCacheKey('user@example.com', 'Test');
test.assert(
  key7 === key8,
  'Same key for identical sender+subject'
);

// Exit with code
const success = test.summary();
process.exit(success ? 0 : 1);
