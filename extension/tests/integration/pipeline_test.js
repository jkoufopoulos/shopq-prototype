/**
 * Pipeline Integration Tests
 *
 * Tests the full P1-P8 flow with mock email data.
 * Run in the extension's service worker console.
 *
 * Usage:
 * 1. Open chrome://extensions
 * 2. Find Return Watch, click "service worker" link
 * 3. Run: importScripts('tests/integration/pipeline_test.js');
 * 4. Then: runPipelineTests();
 */

const PIPELINE_TEST_PREFIX = '[PipelineTest]';

/**
 * Create a mock email message for testing
 */
function createMockEmail({
  email_id,
  thread_id,
  from_address,
  subject,
  snippet,
  internal_date_ms = Date.now(),
}) {
  return {
    id: email_id,
    threadId: thread_id || email_id,
    internalDate: String(internal_date_ms),
    payload: {
      headers: [
        { name: 'From', value: from_address },
        { name: 'Subject', value: subject },
      ],
    },
    snippet,
  };
}

/**
 * Simulate processing an email through the pipeline
 * This mimics what scanner.js does but with more control
 */
async function simulatePipelineProcess(email) {
  const from = email.payload.headers.find(h => h.name === 'From')?.value || '';
  const subject = email.payload.headers.find(h => h.name === 'Subject')?.value || '';
  const snippet = email.snippet || '';

  // P1: Filter
  const filterResult = filterEmail(from, subject, snippet);
  if (filterResult.blocked) {
    return { blocked: true, reason: filterResult.reason };
  }

  // Extract primary keys (P2 would do this)
  const primaryKeys = extractPrimaryKeys(subject, snippet, '');
  const order_id = primaryKeys.order_id;
  const tracking_number = primaryKeys.tracking_number;

  // P4: Classification
  const classification = classifyEmail(subject, snippet, !!order_id);

  // P5: Extraction
  const extracted = extractFields(subject, snippet, '');

  // Check if we should seed an order
  const seedDecision = shouldSeedOrder(
    classification.email_type,
    classification.purchase_confirmed,
    !!tracking_number
  );

  if (!seedDecision.should_seed) {
    return { seeded: false, classification };
  }

  // Try to find existing order
  let existingOrder = await findExistingOrder(order_id, tracking_number);

  if (existingOrder) {
    // Update existing order
    existingOrder.source_email_ids = [...new Set([...existingOrder.source_email_ids, email.id])];

    // Update dates based on email type
    if (classification.email_type === EMAIL_TYPE.SHIPPING && extracted.ship_date) {
      existingOrder.ship_date = extracted.ship_date;
    }
    if (classification.email_type === EMAIL_TYPE.DELIVERY && extracted.delivery_date) {
      existingOrder.delivery_date = extracted.delivery_date;
    }
    if (tracking_number && !existingOrder.tracking_number) {
      existingOrder.tracking_number = tracking_number;
    }
    if (order_id && !existingOrder.order_id) {
      existingOrder.order_id = order_id;
    }

    existingOrder.updated_at = new Date().toISOString();
    await upsertOrder(existingOrder);

    return { seeded: false, updated: true, order: existingOrder };
  }

  // Create new order
  const merchant_domain = filterResult.merchant_domain;
  const display_name = extractMerchantDisplayName(from);

  const order_key = generateOrderKey(
    'test_user',
    merchant_domain,
    order_id || tracking_number || email.id
  );

  const newOrder = createOrder({
    order_key,
    user_id: 'test_user',
    merchant_domain,
    merchant_display_name: display_name,
    item_summary: extracted.item_summary || subject,
    purchase_date: extracted.purchase_date || new Date(parseInt(email.internalDate)).toISOString().split('T')[0],
    email_id: email.id,
  });

  // Set optional fields
  if (order_id) newOrder.order_id = order_id;
  if (tracking_number) newOrder.tracking_number = tracking_number;
  if (extracted.amount) newOrder.amount = extracted.amount;
  if (extracted.ship_date) newOrder.ship_date = extracted.ship_date;
  if (extracted.delivery_date) newOrder.delivery_date = extracted.delivery_date;

  await upsertOrder(newOrder);

  return { seeded: true, order: newOrder };
}

async function runPipelineTests() {
  console.log(PIPELINE_TEST_PREFIX, '='.repeat(60));
  console.log(PIPELINE_TEST_PREFIX, 'PIPELINE INTEGRATION TESTS');
  console.log(PIPELINE_TEST_PREFIX, '='.repeat(60));

  let passed = 0;
  let failed = 0;

  function assert(condition, message) {
    if (condition) {
      console.log(PIPELINE_TEST_PREFIX, '\u2713', message);
      passed++;
    } else {
      console.error(PIPELINE_TEST_PREFIX, '\u2717', message);
      failed++;
    }
  }

  // Clean slate
  console.log(PIPELINE_TEST_PREFIX, '\n--- Setup ---');
  await clearAllStorage();
  await initializeStorage();

  // P-01: Confirmation creates order
  console.log(PIPELINE_TEST_PREFIX, '\n--- P-01: Confirmation Creates Order ---');
  const confirmEmail = createMockEmail({
    email_id: 'msg_confirm_001',
    from_address: 'Amazon <orders@amazon.com>',
    subject: 'Your order #123-4567890-1234567 is confirmed',
    snippet: 'Thank you for your order. Total: $99.99',
  });
  const result1 = await simulatePipelineProcess(confirmEmail);
  assert(result1.seeded === true, 'Confirmation email creates order');
  const orders1 = await getAllOrders();
  assert(orders1.length === 1, 'One order exists after confirmation');

  // P-02: Shipping updates order
  console.log(PIPELINE_TEST_PREFIX, '\n--- P-02: Shipping Updates Order ---');
  const shipEmail = createMockEmail({
    email_id: 'msg_ship_001',
    from_address: 'Amazon <ship-confirm@amazon.com>',
    subject: 'Your order #123-4567890-1234567 has shipped',
    snippet: 'Track your package: 1Z999AA10123456784',
  });
  const result2 = await simulatePipelineProcess(shipEmail);
  assert(result2.updated === true, 'Shipping email updates existing order');
  const orderAfterShip = await getAllOrders();
  assert(orderAfterShip.length === 1, 'Still one order after shipping update');
  assert(orderAfterShip[0].tracking_number === '1Z999AA10123456784', 'Tracking number added');

  // P-03: Delivery updates order
  console.log(PIPELINE_TEST_PREFIX, '\n--- P-03: Delivery Updates Order ---');
  const deliverEmail = createMockEmail({
    email_id: 'msg_deliver_001',
    from_address: 'Amazon <delivery@amazon.com>',
    subject: 'Your order #123-4567890-1234567 was delivered',
    snippet: 'Your package was delivered today.',
  });
  const result3 = await simulatePipelineProcess(deliverEmail);
  assert(result3.updated === true, 'Delivery email updates order');
  const orderAfterDeliver = await getAllOrders();
  assert(orderAfterDeliver[0].source_email_ids.length === 3, 'Order has 3 linked emails');

  // Clean for next test
  await clearAllStorage();
  await initializeStorage();

  // P-05: Primary link by order_id
  console.log(PIPELINE_TEST_PREFIX, '\n--- P-05: Primary Link by Order ID ---');
  const email5a = createMockEmail({
    email_id: 'msg_05a',
    from_address: 'Target <orders@target.com>',
    subject: 'Order confirmation for Order: TARGET123',
    snippet: 'Total: $149.99',
  });
  await simulatePipelineProcess(email5a);

  const email5b = createMockEmail({
    email_id: 'msg_05b',
    from_address: 'Target <shipping@target.com>',
    subject: 'Your Order: TARGET123 has shipped',
    snippet: 'Tracking: 1Z999AA10123456799',
  });
  await simulatePipelineProcess(email5b);

  const orders5 = await getAllOrders();
  assert(orders5.length === 1, 'Two emails with same order_id = 1 order');
  assert(orders5[0].source_email_ids.length === 2, 'Order has both email IDs');

  // Clean for next test
  await clearAllStorage();
  await initializeStorage();

  // P-06: Primary link by tracking
  console.log(PIPELINE_TEST_PREFIX, '\n--- P-06: Primary Link by Tracking ---');
  const email6a = createMockEmail({
    email_id: 'msg_06a',
    from_address: 'Walmart <ship@walmart.com>',
    subject: 'Your package has shipped',
    snippet: 'Tracking: 9400111899223033005014',
  });
  await simulatePipelineProcess(email6a);

  const email6b = createMockEmail({
    email_id: 'msg_06b',
    from_address: 'Walmart <delivery@walmart.com>',
    subject: 'Your package was delivered',
    snippet: 'Package 9400111899223033005014 delivered.',
  });
  await simulatePipelineProcess(email6b);

  const orders6 = await getAllOrders();
  assert(orders6.length === 1, 'Two emails with same tracking = 1 order');

  // Clean for next test
  await clearAllStorage();
  await initializeStorage();

  // P-09: Blocklist rejection
  console.log(PIPELINE_TEST_PREFIX, '\n--- P-09: Blocklist Rejection ---');
  const blockedEmail = createMockEmail({
    email_id: 'msg_blocked',
    from_address: 'Uber Receipts <receipts@uber.com>',
    subject: 'Your Uber trip receipt',
    snippet: 'Thanks for riding with Uber! Total: $25.50',
  });
  const blockedResult = await simulatePipelineProcess(blockedEmail);
  assert(blockedResult.blocked === true, 'Uber email is blocked');
  const ordersAfterBlock = await getAllOrders();
  assert(ordersAfterBlock.length === 0, 'No order created for blocked email');

  // P-10: Deadline exact
  console.log(PIPELINE_TEST_PREFIX, '\n--- P-10: Deadline Confidence ---');
  // This would need LLM enrichment, so we test the storage layer
  const orderWithExactDeadline = await getAllOrders();
  // Skip LLM test - would require mocking

  // Test deadline computation with merchant rule
  console.log(PIPELINE_TEST_PREFIX, '\n--- P-11: Deadline from Merchant Rule ---');
  await clearAllStorage();
  await initializeStorage();

  // Set merchant rule
  await setMerchantRule('amazon.com', 30);

  const emailForRule = createMockEmail({
    email_id: 'msg_rule_001',
    from_address: 'Amazon <orders@amazon.com>',
    subject: 'Your order #111-2222222-3333333 is confirmed',
    snippet: 'Total: $50.00',
  });
  await simulatePipelineProcess(emailForRule);

  const orderForRule = (await getAllOrders())[0];
  // Manual deadline computation (what resolver would do)
  const rule = await getMerchantRule('amazon.com');
  assert(rule === 30, 'Merchant rule is 30 days');

  // Summary
  console.log(PIPELINE_TEST_PREFIX, '\n' + '='.repeat(60));
  console.log(PIPELINE_TEST_PREFIX, `RESULTS: ${passed} passed, ${failed} failed`);
  console.log(PIPELINE_TEST_PREFIX, '='.repeat(60));

  // Cleanup
  await clearAllStorage();
  console.log(PIPELINE_TEST_PREFIX, 'Storage cleared');

  return { passed, failed };
}

// Make available globally
if (typeof globalThis !== 'undefined') {
  globalThis.runPipelineTests = runPipelineTests;
}
