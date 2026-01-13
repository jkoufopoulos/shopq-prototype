/**
 * Phase 6: Acceptance Tests for Verifier Layer
 *
 * Tests the selective second-pass verification logic that catches
 * first-pass classification errors (e.g., over-classification as action_required).
 *
 * Run with: node extension/tests/verifier.test.js
 */

// Load verifier functions (browser globals mock)
const fs = require('fs');
const path = require('path');

// Mock console if needed
if (typeof console === 'undefined') {
  global.console = { log: () => {} };
}

// Load verifier.js by evaluating it
const verifierPath = path.join(__dirname, '../modules/classification/verifier.js');
const verifierCode = fs.readFileSync(verifierPath, 'utf8');
eval(verifierCode);

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
    console.log('\n🧪 Running Phase 6 Verifier Tests\n');
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

function assertTrue(value, message) {
  if (!value) {
    throw new Error(`${message || 'Assertion failed'}: expected truthy value`);
  }
}

function assertFalse(value, message) {
  if (value) {
    throw new Error(`${message || 'Assertion failed'}: expected falsy value`);
  }
}

function assertNotNull(value, message) {
  if (value === null || value === undefined) {
    throw new Error(`${message || 'Assertion failed'}: expected non-null value`);
  }
}

function assertNull(value, message) {
  if (value !== null && value !== undefined) {
    throw new Error(`${message || 'Assertion failed'}: expected null value, got ${JSON.stringify(value)}`);
  }
}

function assertContains(array, value, message) {
  if (!array || !array.includes(value)) {
    throw new Error(`${message || 'Assertion failed'}: expected array to contain ${value}, got ${JSON.stringify(array)}`);
  }
}

function assertGreaterThan(actual, expected, message) {
  if (actual <= expected) {
    throw new Error(`${message || 'Assertion failed'}: expected ${actual} > ${expected}`);
  }
}

// Test suite
const runner = new TestRunner();

// ===== Feature Extraction Tests =====

runner.test('extractEmailFeatures - Detects order ID', () => {
  const email = {
    subject: 'Your Amazon order #D01123456 has shipped',
    snippet: 'Track your package',
    from: 'shipment-tracking@amazon.com'
  };

  const features = extractEmailFeatures(email);
  assertTrue(features.has_order_id, 'Should detect order ID pattern');
});

runner.test('extractEmailFeatures - Detects amount', () => {
  const email = {
    subject: 'Payment receipt',
    snippet: 'You paid $45.99 for your order',
    from: 'payments@store.com'
  };

  const features = extractEmailFeatures(email);
  assertTrue(features.has_amount, 'Should detect dollar amount');
});

runner.test('extractEmailFeatures - Detects calendar link', () => {
  const email = {
    subject: 'Meeting reminder',
    snippet: 'Join here: zoom.us/j/123456789',
    from: 'noreply@zoom.us'
  };

  const features = extractEmailFeatures(email);
  assertTrue(features.has_calendar_link, 'Should detect Zoom link');
});

runner.test('extractEmailFeatures - Detects review request', () => {
  const email = {
    subject: 'How was your experience?',
    snippet: 'Tell us what you think about your recent order',
    from: 'feedback@amazon.com'
  };

  const features = extractEmailFeatures(email);
  assertTrue(features.has_review_request, 'Should detect review request pattern');
});

runner.test('extractEmailFeatures - Detects OTP', () => {
  const email = {
    subject: 'Your verification code',
    snippet: '123456 is your verification code to sign in',
    from: 'security@bank.com'
  };

  const features = extractEmailFeatures(email);
  assertTrue(features.has_otp, 'Should detect OTP pattern');
});

runner.test('extractEmailFeatures - Detects promo words', () => {
  const email = {
    subject: 'Limited time offer - 50% off!',
    snippet: 'Save now before this deal expires',
    from: 'deals@store.com'
  };

  const features = extractEmailFeatures(email);
  assertTrue(features.has_promo_words, 'Should detect promotional language');
});

// ===== Multi-Purpose Sender Detection Tests =====

runner.test('isMultiPurposeSender - Amazon is multi-purpose', () => {
  const result = isMultiPurposeSender('no-reply@amazon.com');
  assertTrue(result, 'Amazon should be flagged as multi-purpose');
});

runner.test('isMultiPurposeSender - PayPal is multi-purpose', () => {
  const result = isMultiPurposeSender('service@paypal.com');
  assertTrue(result, 'PayPal should be flagged as multi-purpose');
});

runner.test('isMultiPurposeSender - Chase Bank is multi-purpose', () => {
  const result = isMultiPurposeSender('alerts@chase.com');
  assertTrue(result, 'Chase should be flagged as multi-purpose');
});

runner.test('isMultiPurposeSender - Small sender is NOT multi-purpose', () => {
  const result = isMultiPurposeSender('hello@smallbusiness.com');
  assertFalse(result, 'Small business should not be flagged');
});

// ===== Contradiction Detection Tests =====

runner.test('detectContradictions - Promotion with order tokens', () => {
  const classification = { type: 'promotion', attention: 'none' };
  const features = { has_order_id: true, has_amount: true };

  const contradictions = detectContradictions(classification, features);
  assertContains(contradictions, 'promotion_with_order_tokens', 'Should detect promo/receipt mismatch');
});

runner.test('detectContradictions - Action required without action words', () => {
  const classification = { type: 'notification', attention: 'action_required' };
  const features = { has_action_words: false, has_review_request: true };

  const contradictions = detectContradictions(classification, features);
  assertContains(contradictions, 'action_required_without_action_words', 'Should detect missing action language');
});

runner.test('detectContradictions - Review request marked action_required', () => {
  const classification = { type: 'notification', attention: 'action_required' };
  const features = { has_review_request: true };

  const contradictions = detectContradictions(classification, features);
  assertContains(contradictions, 'review_request_marked_action_required', 'Should detect review request over-classification');
});

runner.test('detectContradictions - Action required with promo language', () => {
  const classification = { type: 'promotion', attention: 'action_required' };
  const features = { has_promo_words: true };

  const contradictions = detectContradictions(classification, features);
  assertContains(contradictions, 'action_required_with_promo_language', 'Should detect promo pressure misclassified as urgent');
});

runner.test('detectContradictions - Receipt with unsubscribe but no order', () => {
  const classification = { type: 'receipt', attention: 'none' };
  const features = { has_unsubscribe: true, has_order_id: false };

  const contradictions = detectContradictions(classification, features);
  assertContains(contradictions, 'receipt_with_unsubscribe_no_order', 'Should detect fake receipt (promo with receipt claim)');
});

runner.test('detectContradictions - No contradictions for clean classification', () => {
  const classification = { type: 'receipt', attention: 'none' };
  const features = { has_order_id: true, has_amount: true, has_promo_words: false };

  const contradictions = detectContradictions(classification, features);
  assertEquals(contradictions.length, 0, 'Clean receipt should have no contradictions');
});

// ===== Weak Reasoning Detection Tests =====

runner.test('hasWeakReasoning - Detects "probably"', () => {
  const result = hasWeakReasoning('This is probably a promotional email');
  assertTrue(result, 'Should detect weak term "probably"');
});

runner.test('hasWeakReasoning - Detects "might be"', () => {
  const result = hasWeakReasoning('This might be a notification');
  assertTrue(result, 'Should detect weak term "might be"');
});

runner.test('hasWeakReasoning - Detects "unsure"', () => {
  const result = hasWeakReasoning('Unsure about the exact type');
  assertTrue(result, 'Should detect weak term "unsure"');
});

runner.test('hasWeakReasoning - Strong reasoning passes', () => {
  const result = hasWeakReasoning('This is a receipt because it contains an order ID and amount');
  assertFalse(result, 'Strong reasoning should not be flagged');
});

// ===== Verification Trigger Tests =====

runner.test('shouldVerify - Triggers on low confidence', () => {
  const email = { subject: 'Test', snippet: 'Test', from: 'test@example.com' };
  const classification = {
    type: 'notification',
    type_conf: 0.55,
    attention: 'none',
    decider: 'gemini',
    reason: 'Test reason'
  };

  const result = shouldVerify(email, classification);
  assertNotNull(result, 'Should trigger verification on low confidence');
  assertTrue(result.reason.includes('low_confidence'), 'Should mention low confidence in reason');
});

runner.test('shouldVerify - Triggers on multi-purpose sender', () => {
  const email = {
    subject: 'Test',
    snippet: 'Test',
    from: 'no-reply@amazon.com'
  };
  const classification = {
    type: 'promotion',
    type_conf: 0.85,
    attention: 'none',
    decider: 'gemini',
    reason: 'Promotional email'
  };

  const result = shouldVerify(email, classification);
  assertNotNull(result, 'Should trigger verification on multi-purpose sender');
  assertTrue(result.reason.includes('multi_purpose_sender'), 'Should mention multi-purpose sender');
});

runner.test('shouldVerify - Triggers on contradictions', () => {
  const email = {
    subject: 'How was your experience?',
    snippet: 'Rate your order and let us know',
    from: 'feedback@store.com'
  };
  const classification = {
    type: 'notification',
    type_conf: 0.88,
    attention: 'action_required',
    decider: 'gemini',
    reason: 'Review request'
  };

  const result = shouldVerify(email, classification);
  assertNotNull(result, 'Should trigger verification on review request + action_required contradiction');
  assertTrue(result.reason.includes('contradictions'), 'Should mention contradictions');
  assertGreaterThan(result.contradictions.length, 0, 'Should list specific contradictions');
});

runner.test('shouldVerify - Triggers on weak reasoning', () => {
  const email = { subject: 'Test', snippet: 'Test', from: 'test@example.com' };
  const classification = {
    type: 'notification',
    type_conf: 0.85,
    attention: 'none',
    decider: 'gemini',
    reason: 'This is probably a notification'
  };

  const result = shouldVerify(email, classification);
  assertNotNull(result, 'Should trigger verification on weak reasoning');
  assertTrue(result.reason.includes('weak_reasoning'), 'Should mention weak reasoning');
});

runner.test('shouldVerify - Does NOT trigger on high-confidence rule match', () => {
  const email = {
    subject: 'Your verification code: 123456',
    snippet: 'Use this code',
    from: 'security@bank.com'
  };
  const classification = {
    type: 'notification',
    type_conf: 0.95,
    attention: 'action_required',
    decider: 'rule',  // Rule detector (Phase 2)
    reason: 'OTP detected'
  };

  const result = shouldVerify(email, classification);
  assertNull(result, 'Should NOT verify rule-based detections (already high confidence)');
});

runner.test('shouldVerify - Does NOT trigger on high-confidence clean classification', () => {
  const email = {
    subject: 'Your order has shipped',
    snippet: 'Order #123-456 is on the way',
    from: 'shipment@store.com'
  };
  const classification = {
    type: 'receipt',
    type_conf: 0.92,
    attention: 'none',
    attention_conf: 0.90,
    importance_conf: 0.88,
    decider: 'gemini',
    reason: 'Shipping confirmation with order ID'
  };

  const result = shouldVerify(email, classification);
  assertNull(result, 'Should NOT verify high-confidence, contradiction-free classification');
});

// ===== Correction Acceptance Tests =====

runner.test('shouldAcceptCorrection - Accepts correction with rubric violations', () => {
  const verifierResult = {
    verdict: 'correct',
    confidence_delta: 0.10,
    rubric_violations: ['review_request_marked_action_required']
  };

  const result = shouldAcceptCorrection(verifierResult);
  assertTrue(result, 'Should accept correction when rubric violations found');
});

runner.test('shouldAcceptCorrection - Accepts correction with large confidence delta', () => {
  const verifierResult = {
    verdict: 'correct',
    confidence_delta: 0.25,
    rubric_violations: []
  };

  const result = shouldAcceptCorrection(verifierResult);
  assertTrue(result, 'Should accept correction with large confidence increase');
});

runner.test('shouldAcceptCorrection - Rejects correction with low confidence delta and no violations', () => {
  const verifierResult = {
    verdict: 'correct',
    confidence_delta: 0.08,
    rubric_violations: []
  };

  const result = shouldAcceptCorrection(verifierResult);
  assertFalse(result, 'Should reject marginal correction without rubric violations');
});

runner.test('shouldAcceptCorrection - Rejects when verdict is "confirm"', () => {
  const verifierResult = {
    verdict: 'confirm',
    confidence_delta: 0.0,
    rubric_violations: []
  };

  const result = shouldAcceptCorrection(verifierResult);
  assertFalse(result, 'Should not accept correction when verifier confirms original classification');
});

runner.test('shouldAcceptCorrection - Rejects null verifier result', () => {
  const result = shouldAcceptCorrection(null);
  assertFalse(result, 'Should handle null verifier result gracefully');
});

// ===== Integration Scenario Tests =====

runner.test('SCENARIO: Amazon review request should trigger verification', () => {
  const email = {
    subject: 'How was your Amazon Fresh experience?',
    snippet: 'We would love to hear about your recent Amazon Fresh delivery. Please take a moment to rate your order.',
    from: 'store-feedback@amazon.com'
  };

  const classification = {
    type: 'notification',
    type_conf: 0.75,
    attention: 'action_required',
    attention_conf: 0.68,
    decider: 'gemini',
    reason: 'Review request with action language'
  };

  const verifyContext = shouldVerify(email, classification);
  assertNotNull(verifyContext, 'Amazon review request should trigger verification');
  assertTrue(verifyContext.reason.includes('multi_purpose_sender'), 'Should flag Amazon as multi-purpose');
  assertTrue(verifyContext.reason.includes('contradictions'), 'Should detect action_required + review_request contradiction');
  assertGreaterThan(verifyContext.contradictions.length, 0, 'Should list contradictions');
});

runner.test('SCENARIO: Promotional action language should trigger verification', () => {
  const email = {
    subject: 'Reserve your grocery delivery time now!',
    snippet: 'Limited time offer - book your Amazon Fresh delivery slot today and save on your first order.',
    from: 'amazonfresh@amazon.com'
  };

  const classification = {
    type: 'notification',
    type_conf: 0.68,
    attention: 'action_required',
    attention_conf: 0.72,
    decider: 'gemini',
    reason: 'Reservation request with urgency'
  };

  const verifyContext = shouldVerify(email, classification);
  assertNotNull(verifyContext, 'Promo with action language should trigger verification');
  assertTrue(verifyContext.features.has_promo_words, 'Should detect promotional language');
});

runner.test('SCENARIO: Clean OTP from rule detector should NOT verify', () => {
  const email = {
    subject: 'Your verification code is 482619',
    snippet: 'Use this code to sign in',
    from: 'security@bank.com'
  };

  const classification = {
    type: 'notification',
    type_conf: 0.95,
    attention: 'action_required',
    attention_conf: 0.95,
    decider: 'rule',  // Caught by Phase 2 detector
    reason: 'OTP detected by rule'
  };

  const verifyContext = shouldVerify(email, classification);
  assertNull(verifyContext, 'Rule-based OTP detection should not trigger verifier (already high confidence)');
});

runner.test('SCENARIO: Clean receipt should NOT verify', () => {
  const email = {
    subject: 'Your order #123-456 has been delivered',
    snippet: 'Your package was delivered at 3:45 PM. Total: $42.99',
    from: 'shipment@store.com'
  };

  const classification = {
    type: 'receipt',
    type_conf: 0.92,
    attention: 'none',
    attention_conf: 0.94,
    importance_conf: 0.90,
    decider: 'gemini',
    reason: 'Delivery confirmation with order ID and amount'
  };

  const verifyContext = shouldVerify(email, classification);
  assertNull(verifyContext, 'Clean, high-confidence receipt should not need verification');
});

// Run all tests
runner.run().catch(err => {
  console.error('Test runner error:', err);
  process.exit(1);
});
