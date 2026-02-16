/**
 * Storage Module Tests
 *
 * Run this in the extension's service worker console:
 * 1. Open chrome://extensions
 * 2. Find Return Watch, click "service worker" link
 * 3. Paste this script and run
 *
 * Or load via: importScripts('tests/storage_test.js');
 */

const TEST_PREFIX = '[StorageTest]';

async function runStorageTests() {
  console.log(TEST_PREFIX, '='.repeat(60));
  console.log(TEST_PREFIX, 'STORAGE MODULE TESTS');
  console.log(TEST_PREFIX, '='.repeat(60));

  let passed = 0;
  let failed = 0;

  function assert(condition, message) {
    if (condition) {
      console.log(TEST_PREFIX, '✓', message);
      passed++;
    } else {
      console.error(TEST_PREFIX, '✗', message);
      failed++;
    }
  }

  // Clean slate
  console.log(TEST_PREFIX, '\n--- Setup ---');
  await clearAllStorage();

  // Test 1: Initialize storage
  console.log(TEST_PREFIX, '\n--- Test 1: Initialize Storage ---');
  await initializeStorage();
  const stats1 = await getStorageStats();
  assert(stats1.order_count === 0, 'Order count is 0 after init');
  assert(stats1.processed_count === 0, 'Processed count is 0 after init');

  // Test 2: Create an Order
  console.log(TEST_PREFIX, '\n--- Test 2: Create Order ---');
  const order_key = hashOrderKey('test_user', 'amazon.com', 'ORDER-123');
  const order1 = createOrder({
    order_key,
    user_id: 'test_user',
    merchant_domain: 'amazon.com',
    merchant_display_name: 'Amazon',
    item_summary: 'Sony WH-1000XM5 Headphones',
    purchase_date: '2026-01-10',
    email_id: 'msg_001',
  });
  order1.order_id = 'ORDER-123';
  order1.amount = 348.00;

  await upsertOrder(order1);
  const retrieved = await getOrder(order_key);
  assert(retrieved !== null, 'Order can be retrieved by order_key');
  assert(retrieved.merchant_display_name === 'Amazon', 'Merchant name matches');
  assert(retrieved.order_id === 'ORDER-123', 'Order ID matches');

  // Test 3: Find by order_id index
  console.log(TEST_PREFIX, '\n--- Test 3: Find by Order ID ---');
  const foundByOrderId = await findOrderByOrderId('ORDER-123');
  assert(foundByOrderId !== null, 'Order found by order_id');
  assert(foundByOrderId.order_key === order_key, 'Order key matches');

  // Test 4: Update with tracking number
  console.log(TEST_PREFIX, '\n--- Test 4: Add Tracking Number ---');
  order1.tracking_number = '1Z999AA10123456784';
  order1.ship_date = '2026-01-12';
  await upsertOrder(order1);

  const foundByTracking = await findOrderByTracking('1Z999AA10123456784');
  assert(foundByTracking !== null, 'Order found by tracking number');
  assert(foundByTracking.ship_date === '2026-01-12', 'Ship date updated');

  // Test 5: Link additional email
  console.log(TEST_PREFIX, '\n--- Test 5: Link Email ---');
  await linkEmailToOrder('msg_002', order_key);
  const orderWithLinkedEmail = await getOrder(order_key);
  assert(orderWithLinkedEmail.source_email_ids.length === 2, 'Email linked (2 total)');
  assert(orderWithLinkedEmail.source_email_ids.includes('msg_002'), 'New email ID in list');

  // Test 6: Processed email tracking
  console.log(TEST_PREFIX, '\n--- Test 6: Processed Emails ---');
  assert(!(await isEmailProcessed('msg_003')), 'msg_003 not processed initially');
  await markEmailProcessed('msg_003');
  assert(await isEmailProcessed('msg_003'), 'msg_003 marked as processed');

  // Test 7: Create second order (for merge test)
  console.log(TEST_PREFIX, '\n--- Test 7: Create Second Order ---');
  const order_key2 = hashOrderKey('test_user', 'amazon.com', '1Z999AA10123456799');
  const order2 = createOrder({
    order_key: order_key2,
    user_id: 'test_user',
    merchant_domain: 'amazon.com',
    merchant_display_name: 'Amazon',
    item_summary: 'Same Headphones',
    purchase_date: '2026-01-10',
    email_id: 'msg_004',
  });
  order2.tracking_number = '1Z999AA10123456799';
  await upsertOrder(order2);

  const allOrders = await getAllOrders();
  assert(allOrders.length === 2, 'Two orders exist');

  // Test 8: Merge orders (escalation)
  console.log(TEST_PREFIX, '\n--- Test 8: Merge Orders ---');
  await mergeOrders(order_key, order_key2);
  const afterMerge = await getAllOrders();
  assert(afterMerge.length === 1, 'One order after merge');
  const mergedOrder = await getOrder(order_key);
  assert(mergedOrder.source_email_ids.includes('msg_004'), 'Merged order has source email from second');

  // Test 9: OrderEmail operations
  console.log(TEST_PREFIX, '\n--- Test 9: OrderEmail ---');
  const orderEmail = createOrderEmail({
    email_id: 'msg_005',
    thread_id: 'thread_001',
    received_at: '2026-01-10T10:00:00Z',
    merchant_domain: 'amazon.com',
    email_type: EMAIL_TYPE.CONFIRMATION,
  });
  await storeOrderEmail(orderEmail);
  const retrievedEmail = await getOrderEmail('msg_005');
  assert(retrievedEmail !== null, 'OrderEmail stored and retrieved');
  assert(retrievedEmail.email_type === 'confirmation', 'Email type matches');

  // Test 10: Update OrderEmail with extraction
  console.log(TEST_PREFIX, '\n--- Test 10: Update OrderEmail ---');
  await updateOrderEmailExtracted('msg_005', {
    order_id: 'ORDER-456',
    amount: 99.99,
  });
  const updatedEmail = await getOrderEmail('msg_005');
  assert(updatedEmail.extracted.order_id === 'ORDER-456', 'Extraction stored');
  assert(updatedEmail.processed === true, 'Marked as processed');

  // Test 11: Orders with deadlines
  console.log(TEST_PREFIX, '\n--- Test 11: Orders with Deadlines ---');
  const orderWithDeadline = await getOrder(order_key);
  orderWithDeadline.return_by_date = '2026-02-09';
  orderWithDeadline.deadline_confidence = DEADLINE_CONFIDENCE.ESTIMATED;
  await upsertOrder(orderWithDeadline);

  const deadlineOrders = await getOrdersWithDeadlines();
  assert(deadlineOrders.length === 1, 'One order with deadline');
  assert(deadlineOrders[0].return_by_date === '2026-02-09', 'Deadline matches');

  // Test 12: Scan state
  console.log(TEST_PREFIX, '\n--- Test 12: Scan State ---');
  await updateLastScanState(Date.now(), 1704931200000, 7);
  const scanState = await getLastScanState();
  assert(scanState.epoch_ms > 0, 'Scan epoch stored');
  assert(scanState.internal_date_ms === 1704931200000, 'Internal date stored');
  assert(scanState.window_days === 7, 'Window days stored');

  // Test 12b: Merchant rules
  console.log(TEST_PREFIX, '\n--- Test 12b: Merchant Rules ---');
  await setMerchantRule('amazon.com', 30);
  const amazonRule = await getMerchantRule('amazon.com');
  assert(amazonRule === 30, 'Amazon rule is 30 days');

  await setMerchantRule('target.com', 90);
  const allRules = await getAllMerchantRules();
  assert(Object.keys(allRules).length === 2, 'Two merchant rules exist');
  assert(allRules['target.com'] === 90, 'Target rule is 90 days');

  await deleteMerchantRule('target.com');
  const afterDelete = await getAllMerchantRules();
  assert(Object.keys(afterDelete).length === 1, 'One rule after delete');
  assert(afterDelete['target.com'] === undefined, 'Target rule deleted');

  // Test 13: Template cache
  console.log(TEST_PREFIX, '\n--- Test 13: Template Cache ---');
  const hash = 'tmpl_abc123';
  await setTemplateCache(hash, {
    window_days: 30,
    confidence: DEADLINE_CONFIDENCE.ESTIMATED,
    quote: '30 days to return',
  });
  const cached = await getTemplateCache(hash);
  assert(cached !== null, 'Template cached');
  assert(cached.window_days === 30, 'Window days matches');

  // Test 14: findExistingOrder helper
  console.log(TEST_PREFIX, '\n--- Test 14: findExistingOrder ---');
  const found1 = await findExistingOrder('ORDER-123', null);
  assert(found1 !== null, 'Found by order_id alone');
  const found2 = await findExistingOrder(null, '1Z999AA10123456784');
  assert(found2 !== null, 'Found by tracking alone');
  const found3 = await findExistingOrder('ORDER-123', '1Z999AA10123456784');
  assert(found3 !== null, 'Found with both (prefers order_id)');

  // Final stats
  console.log(TEST_PREFIX, '\n--- Final Stats ---');
  const finalStats = await getStorageStats();
  console.log(TEST_PREFIX, 'Stats:', JSON.stringify(finalStats, null, 2));

  // Summary
  console.log(TEST_PREFIX, '\n' + '='.repeat(60));
  console.log(TEST_PREFIX, `RESULTS: ${passed} passed, ${failed} failed`);
  console.log(TEST_PREFIX, '='.repeat(60));

  // Cleanup
  await clearAllStorage();
  console.log(TEST_PREFIX, 'Storage cleared');

  return { passed, failed };
}

// Auto-run if loaded directly
if (typeof window === 'undefined') {
  // Service worker context
  runStorageTests().then(result => {
    console.log(TEST_PREFIX, 'Tests complete:', result);
  }).catch(err => {
    console.error(TEST_PREFIX, 'Test error:', err);
  });
}
