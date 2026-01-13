/**
 * Acceptance Tests for Detector Layer
 *
 * Deterministic tests to lock in behavior and prevent regressions.
 * Run with: node extension/tests/detectors.test.js
 *
 * Updated to align with TAXONOMY.md:
 * - OTPs: type='otp', importance='critical', attention='none'
 * - AttentionType: only 'action_required' or 'none' (no 'follow_up')
 * - All detectors return 'importance' field
 */

// Load detector functions (browser globals mock)
const fs = require('fs');
const path = require('path');

// Mock console if needed
if (typeof console === 'undefined') {
  global.console = { log: () => {} };
}

// Load detectors.js by evaluating it
const detectorsPath = path.join(__dirname, '../modules/classification/detectors.js');
const detectorsCode = fs.readFileSync(detectorsPath, 'utf8');
eval(detectorsCode);

// Test harness
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
    console.log('\n🧪 Running Detector Tests (TAXONOMY.md aligned)\n');
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

// Assertion helpers
function assertEquals(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message || 'Assertion failed'}: expected ${expected}, got ${actual}`);
  }
}

function assertContains(array, value, message) {
  if (!array || !array.includes(value)) {
    throw new Error(`${message || 'Assertion failed'}: expected array to contain ${value}, got ${JSON.stringify(array)}`);
  }
}

function assertNotNull(value, message) {
  if (value === null || value === undefined) {
    throw new Error(`${message || 'Assertion failed'}: expected non-null value`);
  }
}

function assertHasField(obj, field, message) {
  if (!(field in obj)) {
    throw new Error(`${message || 'Assertion failed'}: expected object to have field '${field}'`);
  }
}

// Test suite
const runner = new TestRunner();

// =============================================================================
// OTP Detection Tests (TAXONOMY.md: type='otp', importance='critical')
// =============================================================================

runner.test('otp_6_digit - "Your login code: 2530"', () => {
  const email = {
    subject: 'Your login code: 2530',
    snippet: 'Use this code to sign in to your account.',
    from: 'noreply@service.com'
  };

  const result = detectOTP(email);
  assertNotNull(result, 'OTP detector should match');
  assertEquals(result.type, 'otp', 'Type should be otp (per TAXONOMY.md)');
  assertEquals(result.importance, 'critical', 'OTPs are critical in the moment');
  assertEquals(result.attention, 'none', 'OTPs do not require action_required (ephemeral)');
  assertEquals(result.decider, 'rule', 'Decider should be rule');
  assertHasField(result, 'importance', 'Should have importance field');
});

runner.test('otp_8_digit - "Your verification code is 12345678"', () => {
  const email = {
    subject: 'Your verification code is 12345678',
    snippet: 'Enter this code to verify your account.',
    from: 'security@bank.com'
  };

  const result = detectOTP(email);
  assertNotNull(result, 'OTP detector should match 8-digit codes');
  assertEquals(result.type, 'otp', 'Type should be otp');
  assertEquals(result.importance, 'critical', 'OTPs are critical');
  assertEquals(result.attention, 'none', 'OTPs attention=none (handled differently)');
});

// =============================================================================
// Receipt Detection Tests
// =============================================================================

runner.test('receipt_delivery - "Delivered: Charmin Ultra Strong …"', () => {
  const email = {
    subject: 'Delivered: "Charmin Ultra Strong …"',
    snippet: 'Your Amazon.com package was delivered. Order #123-4567890-1234567',
    from: 'shipment-tracking@amazon.com'
  };

  const result = detectReceipt(email);
  assertNotNull(result, 'Receipt detector should match');
  assertEquals(result.type, 'receipt', 'Type should be receipt');
  assertEquals(result.attention, 'none', 'Attention should be none (already delivered)');
  assertEquals(result.importance, 'routine', 'Receipts are routine by default');
  assertHasField(result, 'importance', 'Should have importance field');
});

runner.test('kindle_problem - "Action Required: Problem with Your Kindle Order #D0112345"', () => {
  const email = {
    subject: 'Action Required: Problem with Your Kindle Order #D0112345',
    snippet: 'We encountered an issue with your order. Please review.',
    from: 'digital@amazon.com'
  };

  const result = detectReceipt(email);
  assertNotNull(result, 'Receipt detector should match (order ID present)');
  assertEquals(result.type, 'receipt', 'Type should be receipt');
  // Note: The "action required" aspect would be handled by the verifier
  // or backend guardrails, not the detector
});

// =============================================================================
// Calendar Event Detection Tests (AttentionType: only 'action_required' or 'none')
// =============================================================================

runner.test('event_reminder - "Don\'t forget: Drawing Hive starts in 1 hour"', () => {
  const email = {
    subject: "Don't forget: Drawing Hive starts in 1 hour",
    snippet: 'Your event is starting soon. Join here: zoom.us/j/123456',
    from: 'events@eventbrite.com'
  };

  const result = detectCalendarEvent(email);
  assertNotNull(result, 'Event detector should match');
  assertEquals(result.type, 'event', 'Type should be event');
  assertEquals(result.attention, 'action_required', 'Imminent event should be action_required');
  assertEquals(result.importance, 'time_sensitive', 'Imminent events are time_sensitive');
  assertEquals(result.phase, 'pre_event', 'Phase should be pre_event');
  assertHasField(result, 'importance', 'Should have importance field');
});

runner.test('event_recording - "Recording for River Road Drop-in Class now available"', () => {
  const email = {
    subject: 'Recording for River Road Drop-in Class now available',
    snippet: 'Thank you for attending. Watch the replay here: zoom.us/rec/123456',
    from: 'noreply@zoom.us'
  };

  const result = detectCalendarEvent(email);
  assertNotNull(result, 'Event recording detector should match');
  assertEquals(result.type, 'event', 'Type should be event');
  // Per TAXONOMY.md: AttentionType = Literal["action_required", "none"]
  // Post-event recordings are not action_required
  assertEquals(result.attention, 'none', 'Post-event recordings are attention=none');
  assertEquals(result.importance, 'routine', 'Post-event recordings are routine');
  assertEquals(result.phase, 'post_event', 'Phase should be post_event');
});

runner.test('event_recording_alt - "Meeting recording is ready"', () => {
  const email = {
    subject: 'Meeting recording is ready',
    snippet: 'The recording for yesterday\'s meeting is now available.',
    from: 'noreply@zoom.us'
  };

  const result = detectCalendarEvent(email);
  assertNotNull(result, 'Event recording should match "recording" keyword');
  assertEquals(result.type, 'event', 'Type should be event');
  assertEquals(result.attention, 'none', 'Recording attention=none (not action_required)');
  assertEquals(result.importance, 'routine', 'Recordings are routine');
});

runner.test('calendar_google - Google Calendar notification', () => {
  const email = {
    subject: 'Notification: Team Meeting @ Wed Oct 23',
    snippet: 'Reminder for your upcoming event',
    from: 'calendar-notification@google.com'
  };

  const result = detectCalendarEvent(email);
  assertNotNull(result, 'Should detect Google Calendar format');
  assertEquals(result.type, 'event', 'Type should be event');
  assertHasField(result, 'importance', 'Should have importance field');
});

// =============================================================================
// Proxy Vote Detection Tests
// =============================================================================

runner.test('proxy_vote - "Make your voice heard: Cast your proxy vote today"', () => {
  const email = {
    subject: 'Make your voice heard: Cast your proxy vote today',
    snippet: 'Annual shareholder meeting voting is now open.',
    from: 'investor.relations@company.com'
  };

  const result = detectProxyVote(email);
  assertNotNull(result, 'Proxy vote detector should match');
  assertEquals(result.type, 'notification', 'Type should be notification');
  assertEquals(result.attention, 'action_required', 'Proxy votes need action');
  assertEquals(result.importance, 'time_sensitive', 'Proxy votes have deadlines');
  assertHasField(result, 'importance', 'Should have importance field');
});

// =============================================================================
// Security Alert Detection Tests
// =============================================================================

runner.test('security_alert - "Unusual sign-in activity detected"', () => {
  const email = {
    subject: 'Unusual sign-in activity detected',
    snippet: 'We noticed a new sign-in from an unrecognized device.',
    from: 'security@google.com'
  };

  const result = detectAccountSecurity(email);
  assertNotNull(result, 'Security alert detector should match');
  assertEquals(result.type, 'notification', 'Type should be notification');
  // Per TAXONOMY.md: AttentionType = Literal["action_required", "none"]
  // Security alerts are critical (handled by guardrails) but attention is informational
  assertEquals(result.attention, 'none', 'Security alerts attention=none (importance handles urgency)');
  assertEquals(result.importance, 'critical', 'Security changes are critical');
  assertHasField(result, 'importance', 'Should have importance field');
});

// =============================================================================
// Edge Cases
// =============================================================================

runner.test('no_match - Generic email should return null', () => {
  const email = {
    subject: 'Weekly newsletter: Tech trends',
    snippet: 'This week in technology...',
    from: 'newsletter@techblog.com'
  };

  const result = runDetectors(email);
  assertEquals(result, null, 'Generic newsletter should not match any detector');
});

// Run all tests
runner.run().catch(err => {
  console.error('Test runner error:', err);
  process.exit(1);
});
