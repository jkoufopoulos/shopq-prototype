const test = require('node:test');
const assert = require('node:assert/strict');

const verifier = require('../modules/classification/verifier.js');

function mkEmail(overrides = {}) {
  return {
    subject: 'Hello',
    from: 'sender@example.com',
    snippet: 'Test snippet',
    ...overrides,
  };
}

function mkCls(overrides = {}) {
  return {
    type: 'newsletter',
    attention: 'none',
    type_conf: 0.99,
    attention_conf: 0.99,
    importance_conf: 0.99,
    reason: 'clean reasoning',
    scores: {},
    decider: 'deterministic',
    ...overrides,
  };
}

globalThis.CONFIG = {
  CONFIDENCE_THRESHOLDS: {
    type_min: 0.7,
    attention: 0.7,
  },
};

test('Phase6: high-confidence non-attention classification early returns null', () => {
  const email = mkEmail();
  const cls = mkCls({ attention: 'none', type_conf: 0.97, attention_conf: 0.95 });
  const out = verifier.shouldVerify(email, cls);
  assert.equal(out, null);
});

test('Phase6: low confidence triggers verification', () => {
  const email = mkEmail();
  const cls = mkCls({ type_conf: 0.75, attention_conf: 0.65, importance_conf: 0.70, attention: 'none' });
  const out = verifier.shouldVerify(email, cls);
  assert.ok(out);
  assert.ok(out.reason.includes('low_confidence'));
});

test('Phase6: action_required attention bypasses early return even if confidences high', () => {
  const email = mkEmail();
  const cls = mkCls({ attention: 'action_required', type_conf: 0.99, attention_conf: 0.99 });
  const out = verifier.shouldVerify(email, cls);
  assert.notEqual(out, null);
});
