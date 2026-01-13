/**
 * Unit Tests for utils.js
 *
 * Tests pure utility functions for correctness and edge cases.
 * Run with: node extension/tests/utils.test.js
 */

const fs = require('fs');
const path = require('path');

// Load signatures.js first (utils.js depends on generateDedupeKey)
const signaturesPath = path.join(__dirname, '../modules/shared/signatures.js');
const signaturesCode = fs.readFileSync(signaturesPath, 'utf8');
eval(signaturesCode);

// Load utils.js
const utilsPath = path.join(__dirname, '../modules/shared/utils.js');
const utilsCode = fs.readFileSync(utilsPath, 'utf8');
eval(utilsCode);

// Simple test harness
class TestRunner {
  constructor() {
    this.passed = 0;
    this.failed = 0;
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

  assertEqual(actual, expected, message) {
    const match = JSON.stringify(actual) === JSON.stringify(expected);
    if (match) {
      console.log(`  ✅ ${message}`);
      this.passed++;
    } else {
      console.error(`  ❌ ${message}`);
      console.error(`     Expected: ${JSON.stringify(expected)}`);
      console.error(`     Actual:   ${JSON.stringify(actual)}`);
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

console.log('\n🧪 Running utils.js Tests\n');
console.log('='.repeat(60));

// Test extractDomain
console.log('\n📧 extractDomain() tests:');
test.assertEqual(
  extractDomain('user@example.com'),
  'example.com',
  'Extract domain from standard email'
);
test.assertEqual(
  extractDomain('USER@EXAMPLE.COM'),
  'example.com',
  'Lowercase domain from uppercase email'
);
test.assertEqual(
  extractDomain('test@sub.example.com'),
  'sub.example.com',
  'Extract subdomain'
);
test.assertEqual(
  extractDomain('invalid-email'),
  'invalid-email',
  'Return input for invalid email (no @)'
);
test.assertEqual(
  extractDomain(''),
  '',
  'Return empty string for empty input'
);

// Test deduplicateBySender - now uses composite key (sender|subject_signature)
console.log('\n🔀 deduplicateBySender() tests:');

// Same sender, different subject types -> keep both
const emails1 = [
  { from: 'user@example.com', subject: 'Your receipt for Order #12345' },
  { from: 'user@example.com', subject: '20% off today only!' },
  { from: 'other@test.com', subject: 'Meeting reminder' }
];
const deduped1 = deduplicateBySender(emails1);
test.assertEqual(deduped1.length, 3, 'Different subject types from same sender are kept');

// Same sender, same subject signature -> deduplicate
const emails2 = [
  { from: 'user@example.com', subject: 'Your receipt for Order #12345' },
  { from: 'user@example.com', subject: 'Your receipt for Order #67890' },  // Same signature
  { from: 'other@test.com', subject: 'Test 3' }
];
const deduped2 = deduplicateBySender(emails2);
test.assertEqual(deduped2.length, 2, 'Same sender+signature is deduplicated');

// Empty array
const emails3 = [];
test.assertEqual(
  deduplicateBySender(emails3).length,
  0,
  'Handle empty array'
);

// Test getToday
console.log('\n📅 getToday() tests:');
const today = getToday();
test.assert(
  /^\d{4}-\d{2}-\d{2}$/.test(today),
  'Returns YYYY-MM-DD format'
);
test.assert(
  today === new Date().toISOString().split('T')[0],
  'Matches current date'
);

// Test case-insensitive sender matching with subject signatures
console.log('\n🔑 Integration test:');
const mixedCase = [
  { from: 'user@EXAMPLE.COM', subject: 'Order confirmation' },
  { from: 'other@example.com', subject: 'Order confirmation' },  // Different sender, same subject
  { from: 'different@test.com', subject: 'Order confirmation' }
];
const dedupedMixed = deduplicateBySender(mixedCase);
test.assertEqual(
  dedupedMixed.length,
  3,
  'Different senders with same subject are all kept'
);

// Same sender (case-insensitive) with same subject should dedupe
const caseInsensitive = [
  { from: 'user@EXAMPLE.COM', subject: 'Order #12345 shipped' },
  { from: 'user@example.com', subject: 'Order #67890 shipped' }  // Same sender (case diff), same signature
];
const dedupedCase = deduplicateBySender(caseInsensitive);
test.assertEqual(
  dedupedCase.length,
  1,
  'Case-insensitive sender deduplication works'
);

// Exit with appropriate code
const success = test.summary();
process.exit(success ? 0 : 1);
