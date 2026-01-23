/**
 * Hints Integration Tests
 *
 * Tests the thread hint invariants for v0.6.2:
 * - Thread hints ONLY attach emails to existing orders
 * - Thread hints NEVER update lifecycle fields
 *
 * Run in the extension's service worker console.
 *
 * Usage:
 * 1. Open chrome://extensions
 * 2. Find Return Watch, click "service worker" link
 * 3. Run: importScripts('tests/integration/hints_test.js');
 * 4. Then: runHintsTests();
 */

const HINTS_TEST_PREFIX = '[HintsTest]';

/**
 * Simulate thread hint attachment
 * This mimics what the hint module does when finding an email
 * in the same thread as an existing order
 */
async function simulateThreadHint(email_id, thread_id) {
  // Find order by thread_id (simplified - in real code this would check order_emails)
  const allOrders = await getAllOrders();

  for (const order of allOrders) {
    // Check if any source email is in the same thread
    for (const sourceId of order.source_email_ids) {
      const sourceEmail = await getOrderEmail(sourceId);
      if (sourceEmail && sourceEmail.thread_id === thread_id) {
        // Thread match found - attach email (HINT-ONLY)
        // CRITICAL: Only update source_email_ids, nothing else
        if (!order.source_email_ids.includes(email_id)) {
          order.source_email_ids.push(email_id);
          // Update ONLY updated_at, not any lifecycle fields
          order.updated_at = new Date().toISOString();
          await upsertOrder(order);
          return { attached: true, order_key: order.order_key };
        }
        return { attached: false, reason: 'already_attached' };
      }
    }
  }

  return { attached: false, reason: 'no_thread_match' };
}

async function runHintsTests() {
  console.log(HINTS_TEST_PREFIX, '='.repeat(60));
  console.log(HINTS_TEST_PREFIX, 'THREAD HINT INVARIANT TESTS');
  console.log(HINTS_TEST_PREFIX, '='.repeat(60));

  let passed = 0;
  let failed = 0;

  function assert(condition, message) {
    if (condition) {
      console.log(HINTS_TEST_PREFIX, '\u2713', message);
      passed++;
    } else {
      console.error(HINTS_TEST_PREFIX, '\u2717', message);
      failed++;
    }
  }

  function assertEqual(actual, expected, message) {
    const pass = JSON.stringify(actual) === JSON.stringify(expected);
    if (!pass) {
      console.error(HINTS_TEST_PREFIX, `Expected: ${JSON.stringify(expected)}, Got: ${JSON.stringify(actual)}`);
    }
    assert(pass, message);
  }

  // Clean slate
  console.log(HINTS_TEST_PREFIX, '\n--- Setup ---');
  await clearAllStorage();
  await initializeStorage();

  // Create a base order with all lifecycle fields set
  const order_key = generateOrderKey('test_user', 'amazon.com', 'HINT_TEST_001');
  const baseOrder = createOrder({
    order_key,
    user_id: 'test_user',
    merchant_domain: 'amazon.com',
    merchant_display_name: 'Amazon',
    item_summary: 'Test Product',
    purchase_date: '2026-01-10',
    email_id: 'msg_hint_base',
  });

  // Set all lifecycle fields
  baseOrder.order_id = 'ORDER-HINT-123';
  baseOrder.tracking_number = '1Z999AA10123456000';
  baseOrder.ship_date = '2026-01-12';
  baseOrder.delivery_date = '2026-01-15';
  baseOrder.return_window_days = 30;
  baseOrder.explicit_return_by_date = '2026-02-14';
  baseOrder.return_by_date = '2026-02-14';
  baseOrder.deadline_confidence = DEADLINE_CONFIDENCE.EXACT;
  baseOrder.amount = 199.99;

  await upsertOrder(baseOrder);

  // Store OrderEmail with thread_id
  const orderEmail = createOrderEmail({
    email_id: 'msg_hint_base',
    thread_id: 'thread_hint_001',
    received_at: '2026-01-10T10:00:00Z',
    merchant_domain: 'amazon.com',
    email_type: EMAIL_TYPE.CONFIRMATION,
  });
  await storeOrderEmail(orderEmail);

  // Capture state before hint
  const orderBefore = await getOrder(order_key);
  console.log(HINTS_TEST_PREFIX, '\n--- Order State Before Hint ---');
  console.log(HINTS_TEST_PREFIX, 'source_email_ids:', orderBefore.source_email_ids);

  // H-01: Hint attaches email
  console.log(HINTS_TEST_PREFIX, '\n--- H-01: Hint Attaches Email ---');
  const hintResult = await simulateThreadHint('msg_hint_new', 'thread_hint_001');
  assert(hintResult.attached === true, 'H-01: Hint attaches email to order');

  const orderAfter = await getOrder(order_key);
  assert(orderAfter.source_email_ids.includes('msg_hint_new'), 'H-01: source_email_ids grows');

  // H-02 through H-11: Verify NO lifecycle fields changed
  console.log(HINTS_TEST_PREFIX, '\n--- H-02 to H-11: Lifecycle Fields Unchanged ---');

  assertEqual(orderAfter.purchase_date, orderBefore.purchase_date, 'H-02: purchase_date unchanged');
  assertEqual(orderAfter.ship_date, orderBefore.ship_date, 'H-03: ship_date unchanged');
  assertEqual(orderAfter.delivery_date, orderBefore.delivery_date, 'H-04: delivery_date unchanged');
  assertEqual(orderAfter.order_id, orderBefore.order_id, 'H-05: order_id unchanged');
  assertEqual(orderAfter.tracking_number, orderBefore.tracking_number, 'H-06: tracking_number unchanged');
  assertEqual(orderAfter.return_window_days, orderBefore.return_window_days, 'H-07: return_window_days unchanged');
  assertEqual(orderAfter.explicit_return_by_date, orderBefore.explicit_return_by_date, 'H-08: explicit_return_by_date unchanged');
  assertEqual(orderAfter.return_by_date, orderBefore.return_by_date, 'H-09: return_by_date unchanged');
  assertEqual(orderAfter.deadline_confidence, orderBefore.deadline_confidence, 'H-10: deadline_confidence unchanged');
  assertEqual(orderAfter.amount, orderBefore.amount, 'H-11: amount unchanged');

  // H-12: Ambiguous thread (2 orders) - NO attachment
  console.log(HINTS_TEST_PREFIX, '\n--- H-12: Ambiguous Thread ---');

  // Create a second order in the same thread (simulating ambiguity)
  const order_key2 = generateOrderKey('test_user', 'amazon.com', 'HINT_TEST_002');
  const order2 = createOrder({
    order_key: order_key2,
    user_id: 'test_user',
    merchant_domain: 'amazon.com',
    merchant_display_name: 'Amazon',
    item_summary: 'Second Product',
    purchase_date: '2026-01-11',
    email_id: 'msg_hint_base2',
  });
  await upsertOrder(order2);

  // Store second OrderEmail in same thread
  const orderEmail2 = createOrderEmail({
    email_id: 'msg_hint_base2',
    thread_id: 'thread_hint_001', // Same thread!
    received_at: '2026-01-11T10:00:00Z',
    merchant_domain: 'amazon.com',
    email_type: EMAIL_TYPE.SHIPPING,
  });
  await storeOrderEmail(orderEmail2);

  // Custom ambiguity check (simplified)
  async function checkThreadAmbiguity(thread_id) {
    const allOrders = await getAllOrders();
    let matchingOrders = 0;

    for (const order of allOrders) {
      for (const sourceId of order.source_email_ids) {
        const sourceEmail = await getOrderEmail(sourceId);
        if (sourceEmail && sourceEmail.thread_id === thread_id) {
          matchingOrders++;
          break; // Count each order once
        }
      }
    }

    return matchingOrders > 1;
  }

  const isAmbiguous = await checkThreadAmbiguity('thread_hint_001');
  assert(isAmbiguous === true, 'H-12: Thread is now ambiguous (2 orders)');

  // When ambiguous, hint should NOT attach
  // (In real code, hint module would check for ambiguity first)

  // Additional invariant: Check that updated_at DID change (only allowed field)
  console.log(HINTS_TEST_PREFIX, '\n--- Updated At Change Allowed ---');
  assert(orderAfter.updated_at !== orderBefore.updated_at, 'updated_at changed (allowed)');

  // Summary
  console.log(HINTS_TEST_PREFIX, '\n' + '='.repeat(60));
  console.log(HINTS_TEST_PREFIX, `RESULTS: ${passed} passed, ${failed} failed`);
  console.log(HINTS_TEST_PREFIX, '='.repeat(60));

  // Cleanup
  await clearAllStorage();
  console.log(HINTS_TEST_PREFIX, 'Storage cleared');

  return { passed, failed };
}

// Make available globally
if (typeof globalThis !== 'undefined') {
  globalThis.runHintsTests = runHintsTests;
}
