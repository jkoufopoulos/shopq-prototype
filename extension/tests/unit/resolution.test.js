/**
 * Unit Tests for Entity Resolution (resolution.js)
 *
 * Tests pure matching/merging functions:
 * - normalizeItemTokens
 * - jaccardSimilarity
 * - orderRichness
 * - getEffectiveMatchTime
 * - resolveMatchingOrder
 */

const resolution = loadModuleFunctions('modules/storage/resolution.js');

describe('Resolution - normalizeItemTokens', () => {
  it('tokenizes a product description', () => {
    const tokens = resolution.normalizeItemTokens('Nike Air Max 270 Running Shoes');
    assert(tokens.has('nike'), 'Contains nike');
    assert(tokens.has('air'), 'Contains air');
    assert(tokens.has('max'), 'Contains max');
    assert(tokens.has('270'), 'Contains 270');
    assert(tokens.has('running'), 'Contains running');
    assert(tokens.has('shoes'), 'Contains shoes');
  });

  it('removes stop words', () => {
    const tokens = resolution.normalizeItemTokens('The shoes for your feet');
    assert(!tokens.has('the'), 'Removed "the"');
    assert(!tokens.has('for'), 'Removed "for"');
    assert(!tokens.has('your'), 'Removed "your"');
    assert(tokens.has('shoes'), 'Kept "shoes"');
    assert(tokens.has('feet'), 'Kept "feet"');
  });

  it('removes short tokens (< 3 chars)', () => {
    const tokens = resolution.normalizeItemTokens('XS size blue shirt');
    assert(!tokens.has('xs'), 'Removed 2-char token');
    assert(tokens.has('blue'), 'Kept 4-char token');
    assert(tokens.has('shirt'), 'Kept 5-char token');
  });

  it('strips punctuation and normalizes case', () => {
    const tokens = resolution.normalizeItemTokens('Levi\'s 501® Original Jeans');
    assert(tokens.has('levis'), 'Strips apostrophe');
    assert(tokens.has('501'), 'Keeps numbers');
    assert(tokens.has('original'), 'Lowercases');
    assert(tokens.has('jeans'), 'Keeps word');
  });

  it('returns empty set for null/empty input', () => {
    assertEqual(resolution.normalizeItemTokens(null).size, 0, 'Null returns empty');
    assertEqual(resolution.normalizeItemTokens('').size, 0, 'Empty string returns empty');
    assertEqual(resolution.normalizeItemTokens(undefined).size, 0, 'Undefined returns empty');
  });
});

describe('Resolution - jaccardSimilarity', () => {
  it('returns 1.0 for identical sets', () => {
    const set = new Set(['apple', 'banana', 'cherry']);
    assertEqual(resolution.jaccardSimilarity(set, set), 1.0, 'Identical sets = 1.0');
  });

  it('returns 0.0 for disjoint sets', () => {
    const a = new Set(['apple', 'banana']);
    const b = new Set(['cherry', 'date']);
    assertEqual(resolution.jaccardSimilarity(a, b), 0.0, 'Disjoint sets = 0.0');
  });

  it('returns 1.0 for two empty sets', () => {
    assertEqual(resolution.jaccardSimilarity(new Set(), new Set()), 1.0, 'Both empty = 1.0');
  });

  it('returns 0.0 when one set is empty', () => {
    const a = new Set(['apple']);
    assertEqual(resolution.jaccardSimilarity(a, new Set()), 0.0, 'One empty = 0.0');
    assertEqual(resolution.jaccardSimilarity(new Set(), a), 0.0, 'Reversed = 0.0');
  });

  it('computes partial overlap correctly', () => {
    const a = new Set(['apple', 'banana', 'cherry']);
    const b = new Set(['banana', 'cherry', 'date']);
    // Intersection: {banana, cherry} = 2, Union: {apple, banana, cherry, date} = 4
    const score = resolution.jaccardSimilarity(a, b);
    assertEqual(score, 0.5, '2/4 = 0.5');
  });

  it('is symmetric', () => {
    const a = new Set(['apple', 'banana']);
    const b = new Set(['banana', 'cherry', 'date']);
    const ab = resolution.jaccardSimilarity(a, b);
    const ba = resolution.jaccardSimilarity(b, a);
    assertEqual(ab, ba, 'Symmetric');
  });
});

describe('Resolution - orderRichness', () => {
  it('returns 0 for empty order', () => {
    assertEqual(resolution.orderRichness({}), 0, 'Empty order = 0');
  });

  it('scores delivery_date as 3', () => {
    assertEqual(resolution.orderRichness({ delivery_date: '2024-01-15' }), 3, 'delivery_date = 3');
  });

  it('scores return_by_date as 3', () => {
    assertEqual(resolution.orderRichness({ return_by_date: '2024-02-14' }), 3, 'return_by_date = 3');
  });

  it('scores order_id as 2', () => {
    assertEqual(resolution.orderRichness({ order_id: '123-456' }), 2, 'order_id = 2');
  });

  it('accumulates scores for rich orders', () => {
    const order = {
      delivery_date: '2024-01-15',
      return_by_date: '2024-02-14',
      order_id: '123',
      ship_date: '2024-01-10',
      amount: 99.99,
      tracking_number: '1Z123',
      explicit_return_by_date: '2024-02-14',
      return_window_days: 30,
    };
    // 3 + 3 + 2 + 1 + 1 + 1 + 2 + 1 = 14
    assertEqual(resolution.orderRichness(order), 14, 'Rich order = 14');
  });
});

describe('Resolution - getEffectiveMatchTime', () => {
  it('prefers match_time', () => {
    const order = {
      match_time: '2024-01-15T00:00:00Z',
      purchase_date: '2024-01-10T00:00:00Z',
      created_at: '2024-01-05T00:00:00Z',
    };
    assertEqual(
      resolution.getEffectiveMatchTime(order),
      new Date('2024-01-15T00:00:00Z').getTime(),
      'Uses match_time'
    );
  });

  it('falls back to purchase_date', () => {
    const order = {
      purchase_date: '2024-01-10T00:00:00Z',
      created_at: '2024-01-05T00:00:00Z',
    };
    assertEqual(
      resolution.getEffectiveMatchTime(order),
      new Date('2024-01-10T00:00:00Z').getTime(),
      'Uses purchase_date'
    );
  });

  it('falls back to created_at', () => {
    const order = { created_at: '2024-01-05T00:00:00Z' };
    assertEqual(
      resolution.getEffectiveMatchTime(order),
      new Date('2024-01-05T00:00:00Z').getTime(),
      'Uses created_at'
    );
  });

  it('returns Date.now() for empty order', () => {
    const before = Date.now();
    const result = resolution.getEffectiveMatchTime({});
    const after = Date.now();
    assert(result >= before && result <= after, 'Returns current time');
  });
});

describe('Resolution - resolveMatchingOrder', () => {
  // resolveMatchingOrder calls computeNormalizedMerchant (from store.js, loaded in global scope)
  // The test harness loads it into the shared context.

  it('matches by order_id (identity match)', () => {
    const newOrder = { order_id: 'ORD-123', item_summary: 'Blue Widget' };
    const orders = {
      'key1': { order_id: 'ORD-123', item_summary: 'Blue Widget' },
    };
    const orderIdIndex = { 'ORD-123': 'key1' };

    const result = resolution.resolveMatchingOrder(newOrder, orders, orderIdIndex, {}, {});
    assertEqual(result, 'key1', 'Matches by order_id');
  });

  it('matches by tracking_number (identity match)', () => {
    const newOrder = { tracking_number: '1Z999AA10123456784', item_summary: 'Red Widget' };
    const orders = {
      'key2': { tracking_number: '1Z999AA10123456784', item_summary: 'Red Widget' },
    };
    const trackingIndex = { '1Z999AA10123456784': 'key2' };

    const result = resolution.resolveMatchingOrder(newOrder, orders, {}, trackingIndex, {});
    assertEqual(result, 'key2', 'Matches by tracking_number');
  });

  it('returns null when no match exists', () => {
    const newOrder = { order_id: 'ORD-999', item_summary: 'Unique item' };
    const result = resolution.resolveMatchingOrder(newOrder, {}, {}, {}, {});
    assertEqual(result, null, 'No match returns null');
  });

  it('rejects fuzzy match when order_ids conflict', () => {
    const newOrder = {
      order_key: 'new_key',
      order_id: 'ORD-111',
      normalized_merchant: 'amazon.com',
      item_summary: 'Nike Air Max 270 Running Shoes Size 10',
      match_time: '2024-01-15T00:00:00Z',
    };
    const orders = {
      'existing_key': {
        order_key: 'existing_key',
        order_id: 'ORD-222',
        normalized_merchant: 'amazon.com',
        item_summary: 'Nike Air Max 270 Running Shoes Size 10',
        match_time: '2024-01-15T00:00:00Z',
      },
    };
    const merchantIndex = { 'amazon.com': ['existing_key'] };
    const stats = {};

    const result = resolution.resolveMatchingOrder(
      newOrder, orders, {}, {}, merchantIndex, stats
    );
    assertEqual(result, null, 'Rejects conflicting order_ids');
    assertEqual(stats.conflict_reject, 1, 'Tracks conflict rejection');
  });

  it('fuzzy matches similar items from same merchant within time window', () => {
    const newOrder = {
      order_key: 'new_key',
      normalized_merchant: 'amazon.com',
      item_summary: 'Nike Air Max 270 Running Shoes Size 10 Black',
      match_time: '2024-01-15T00:00:00Z',
    };
    const orders = {
      'existing_key': {
        order_key: 'existing_key',
        normalized_merchant: 'amazon.com',
        item_summary: 'Nike Air Max 270 Running Shoes Size 10 Black',
        match_time: '2024-01-16T00:00:00Z',
      },
    };
    const merchantIndex = { 'amazon.com': ['existing_key'] };
    const stats = {};

    const result = resolution.resolveMatchingOrder(
      newOrder, orders, {}, {}, merchantIndex, stats
    );
    assertEqual(result, 'existing_key', 'Fuzzy matches identical items');
    assertEqual(stats.fuzzy_match, 1, 'Tracks fuzzy match');
  });

  it('rejects fuzzy match when items are too different', () => {
    const newOrder = {
      order_key: 'new_key',
      normalized_merchant: 'amazon.com',
      item_summary: 'Samsung Galaxy S24 Ultra Phone',
      match_time: '2024-01-15T00:00:00Z',
    };
    const orders = {
      'existing_key': {
        order_key: 'existing_key',
        normalized_merchant: 'amazon.com',
        item_summary: 'Apple MacBook Pro Laptop Computer',
        match_time: '2024-01-15T00:00:00Z',
      },
    };
    const merchantIndex = { 'amazon.com': ['existing_key'] };

    const result = resolution.resolveMatchingOrder(
      newOrder, orders, {}, {}, merchantIndex
    );
    assertEqual(result, null, 'Rejects dissimilar items');
  });

  it('rejects fuzzy match outside time window', () => {
    const newOrder = {
      order_key: 'new_key',
      normalized_merchant: 'amazon.com',
      item_summary: 'Nike Air Max 270 Running Shoes Size 10 Black',
      match_time: '2024-01-01T00:00:00Z',
    };
    const orders = {
      'existing_key': {
        order_key: 'existing_key',
        normalized_merchant: 'amazon.com',
        item_summary: 'Nike Air Max 270 Running Shoes Size 10 Black',
        match_time: '2024-02-01T00:00:00Z',  // 31 days later
      },
    };
    const merchantIndex = { 'amazon.com': ['existing_key'] };

    const result = resolution.resolveMatchingOrder(
      newOrder, orders, {}, {}, merchantIndex
    );
    assertEqual(result, null, 'Rejects match outside 14-day window');
  });

  it('increments stats counters on no_match', () => {
    const stats = {};
    const newOrder = {
      order_key: 'new_key',
      merchant_domain: 'target.com',
      item_summary: 'Completely Different Gadget Device',
      match_time: '2024-01-15T00:00:00Z',
    };
    const orders = {
      'other_key': {
        order_key: 'other_key',
        merchant_domain: 'target.com',
        item_summary: 'Unrelated Kitchen Appliance Blender',
        match_time: '2024-01-15T00:00:00Z',
      },
    };
    const merchantIndex = { 'target.com': ['other_key'] };
    resolution.resolveMatchingOrder(newOrder, orders, {}, {}, merchantIndex, stats);
    assertEqual(stats.no_match, 1, 'Tracks no_match');
  });
});
