/**
 * Unit Tests for mapper.js
 *
 * Tests classification to Gmail label mapping logic.
 * Run with: node extension/tests/mapper.test.js
 *
 * The mapper now uses client_label from API as the primary label source.
 * See: docs/TAXONOMY.md for client_label definitions
 * See: mailq/storage/classification.py compute_client_label() for mapping logic
 */

const fs = require('fs');
const path = require('path');

// Load mapper.js
const mapperPath = path.join(__dirname, '../modules/classification/mapper.js');
const mapperCode = fs.readFileSync(mapperPath, 'utf8');
eval(mapperCode);

// Test harness
class TestRunner {
  constructor() {
    this.passed = 0;
    this.failed = 0;
  }

  assertEqual(actual, expected, message) {
    const actualStr = JSON.stringify(actual);
    const expectedStr = JSON.stringify(expected);
    if (actualStr === expectedStr) {
      console.log(`  ✅ ${message}`);
      this.passed++;
    } else {
      console.error(`  ❌ ${message}`);
      console.error(`     Expected: ${expectedStr}`);
      console.error(`     Actual:   ${actualStr}`);
      this.failed++;
    }
  }

  assertIncludes(array, item, message) {
    if (array.includes(item)) {
      console.log(`  ✅ ${message}`);
      this.passed++;
    } else {
      console.error(`  ❌ ${message}`);
      console.error(`     Expected array to include: ${item}`);
      console.error(`     Actual: ${JSON.stringify(array)}`);
      this.failed++;
    }
  }

  assertNotIncludes(array, item, message) {
    if (!array.includes(item)) {
      console.log(`  ✅ ${message}`);
      this.passed++;
    } else {
      console.error(`  ❌ ${message}`);
      console.error(`     Expected array NOT to include: ${item}`);
      console.error(`     Actual: ${JSON.stringify(array)}`);
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

console.log('\n🧪 Running mapper.js Tests\n');
console.log('='.repeat(60));

// =============================================================================
// PRIMARY: client_label mapping (new system)
// =============================================================================
console.log('\n📋 client_label to Gmail label mapping (PRIMARY):');

const receiptsLabel = mapToLabels({ client_label: 'receipts', domains: [] });
test.assertIncludes(receiptsLabel, 'MailQ-Receipts', 'client_label=receipts maps to MailQ-Receipts');

const actionRequired = mapToLabels({ client_label: 'action-required', domains: [] });
test.assertIncludes(actionRequired, 'MailQ-Action-Required', 'client_label=action-required maps to MailQ-Action-Required');

const messagesLabel = mapToLabels({ client_label: 'messages', domains: [] });
test.assertIncludes(messagesLabel, 'MailQ-Messages', 'client_label=messages maps to MailQ-Messages');

const everythingElse = mapToLabels({ client_label: 'everything-else', domains: [] });
test.assertIncludes(everythingElse, 'MailQ-Everything-Else', 'client_label=everything-else maps to MailQ-Everything-Else');

// =============================================================================
// FALLBACK: Legacy type-based mapping (for backwards compatibility)
// =============================================================================
console.log('\n🔄 Legacy type-based fallback (when client_label missing):');

const legacyReceipt = mapToLabels({ type: 'receipt', domains: [], attention: 'none' });
test.assertIncludes(legacyReceipt, 'MailQ-Receipts', 'Legacy: type=receipt maps to MailQ-Receipts');

const legacyMessage = mapToLabels({ type: 'message', domains: [], attention: 'none' });
test.assertIncludes(legacyMessage, 'MailQ-Messages', 'Legacy: type=message maps to MailQ-Messages');

const legacyNewsletter = mapToLabels({ type: 'newsletter', domains: [], attention: 'none' });
test.assertIncludes(legacyNewsletter, 'MailQ-Everything-Else', 'Legacy: type=newsletter maps to MailQ-Everything-Else');

const legacyNotification = mapToLabels({ type: 'notification', domains: [], attention: 'none' });
test.assertIncludes(legacyNotification, 'MailQ-Everything-Else', 'Legacy: type=notification maps to MailQ-Everything-Else');

const legacyOtp = mapToLabels({ type: 'otp', domains: [], importance: 'critical' });
test.assertIncludes(legacyOtp, 'MailQ-Everything-Else', 'Legacy: type=otp maps to MailQ-Everything-Else (NOT action-required)');

const legacyUncategorized = mapToLabels({ type: 'uncategorized', domains: [], attention: 'none' });
test.assertIncludes(legacyUncategorized, 'MailQ-Everything-Else', 'Legacy: type=uncategorized maps to MailQ-Everything-Else');

// Legacy: action_required → action-required (except OTPs)
const legacyActionRequired = mapToLabels({ type: 'notification', attention: 'action_required', domains: [] });
test.assertIncludes(legacyActionRequired, 'MailQ-Action-Required', 'Legacy: notification with action_required maps to MailQ-Action-Required');

// Informational notification (no action required) → everything-else
const legacyInformational = mapToLabels({ type: 'notification', attention: 'none', domains: [] });
test.assertIncludes(legacyInformational, 'MailQ-Everything-Else', 'Legacy: notification with no action → MailQ-Everything-Else');

// =============================================================================
// OTP special handling
// =============================================================================
console.log('\n🔐 OTP special handling:');

// OTPs should NEVER get action-required, even with action_required attention
const otpWithClientLabel = mapToLabels({ client_label: 'everything-else', type: 'otp', attention: 'action_required', domains: [] });
test.assertIncludes(otpWithClientLabel, 'MailQ-Everything-Else', 'OTP with client_label maps to Everything-Else');
test.assertNotIncludes(otpWithClientLabel, 'MailQ-Action-Required', 'OTP does NOT get Action-Required (ephemeral)');

// Legacy fallback for OTPs
const otpLegacy = mapToLabels({ type: 'otp', attention: 'action_required', domains: [] });
test.assertIncludes(otpLegacy, 'MailQ-Everything-Else', 'Legacy OTP maps to Everything-Else');
test.assertNotIncludes(otpLegacy, 'MailQ-Action-Required', 'Legacy OTP does NOT get Action-Required');

// =============================================================================
// client_label only (gmail_labels ignored for clean UI)
// =============================================================================
console.log('\n🏷️  client_label only (gmail_labels ignored):');

// Extension uses client_label ONLY - ignores backend's gmail_labels for cleaner Gmail UI
const withBackendLabels = mapToLabels({
  client_label: 'receipts',
  gmail_labels: ['MailQ-Receipts', 'MailQ-Everything-Else']  // These are ignored - client_label is source of truth
});
test.assertEqual(withBackendLabels, ['MailQ-Receipts'], 'Only client_label used, gmail_labels ignored');

// Without gmail_labels, client_label is still used
const noBackendLabels = mapToLabels({
  client_label: 'receipts'
});
test.assertEqual(noBackendLabels, ['MailQ-Receipts'], 'client_label maps correctly');

// =============================================================================
// Edge cases
// =============================================================================
console.log('\n🚫 Edge cases:');

const nullClassification = mapToLabels(null);
test.assertEqual(nullClassification, ['MailQ-Everything-Else'], 'Null classification returns Everything-Else');

const emptyClassification = mapToLabels({});
test.assertEqual(emptyClassification, ['MailQ-Everything-Else'], 'Empty classification returns Everything-Else fallback');

const missingDomains = mapToLabels({
  client_label: 'receipts'
});
test.assertIncludes(missingDomains, 'MailQ-Receipts', 'Missing domains field handled gracefully');

// =============================================================================
// TAXONOMY.md alignment tests
// =============================================================================
console.log('\n📖 TAXONOMY.md alignment:');

// Order confirmation (type=receipt) → receipts
const orderConfirmation = mapToLabels({ client_label: 'receipts', type: 'receipt', importance: 'routine', domains: ['shopping'] });
test.assertIncludes(orderConfirmation, 'MailQ-Receipts', 'Order confirmation → receipts');

// Fraud alert (type=notification, importance=critical) → action-required
const fraudAlert = mapToLabels({ client_label: 'action-required', type: 'notification', importance: 'critical', domains: ['finance'] });
test.assertIncludes(fraudAlert, 'MailQ-Action-Required', 'Fraud alert → action-required');

// Listserv event (type=event) → everything-else
const listservEvent = mapToLabels({ client_label: 'everything-else', type: 'event', importance: 'time_sensitive', domains: [] });
test.assertIncludes(listservEvent, 'MailQ-Everything-Else', 'Listserv event → everything-else');

// Listserv discussion (type=message) → messages
const listservDiscussion = mapToLabels({ client_label: 'messages', type: 'message', importance: 'routine', domains: [] });
test.assertIncludes(listservDiscussion, 'MailQ-Messages', 'Listserv discussion → messages');

// Exit with code
const success = test.summary();
process.exit(success ? 0 : 1);
