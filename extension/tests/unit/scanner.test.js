/**
 * Smoke Tests for Scanner (scanner.js)
 *
 * Tests pure functions that don't require Chrome APIs or network access:
 * - extractOrderNumber
 * - normalizeMerchantDomain
 * - generateOrderKey
 * - detectCancelledOrders
 */

const scanner = loadModuleFunctions('modules/sync/scanner.js');

// ============================================================
// extractOrderNumber
// ============================================================

describe('Scanner - extractOrderNumber', () => {
  it('extracts Amazon order number (3-7-7)', () => {
    assertEqual(
      scanner.extractOrderNumber('Your order 123-4567890-1234567 has shipped'),
      '123-4567890-1234567',
      'Amazon format'
    );
  });

  it('extracts Order # format', () => {
    assertEqual(
      scanner.extractOrderNumber('Order #ABC-12345 confirmed'),
      'ABC-12345',
      'Order # format'
    );
  });

  it('extracts Order #: format', () => {
    assertEqual(
      scanner.extractOrderNumber('Order #: WMT-98765 is on its way'),
      'WMT-98765',
      'Order #: format'
    );
  });

  it('extracts Confirmation # format', () => {
    assertEqual(
      scanner.extractOrderNumber('Confirmation #CONF-555'),
      'CONF-555',
      'Confirmation # format'
    );
  });

  it('returns null for no order number', () => {
    assertEqual(
      scanner.extractOrderNumber('Thank you for your purchase'),
      null,
      'No order number'
    );
  });

  it('returns null for null input', () => {
    assertEqual(scanner.extractOrderNumber(null), null, 'Null input');
  });

  it('returns null for empty string', () => {
    assertEqual(scanner.extractOrderNumber(''), null, 'Empty string');
  });
});

// ============================================================
// normalizeMerchantDomain
// ============================================================

describe('Scanner - normalizeMerchantDomain', () => {
  it('strips www prefix', () => {
    assertEqual(scanner.normalizeMerchantDomain('www.amazon.com'), 'amazon.com', 'www prefix');
  });

  it('strips shop prefix', () => {
    assertEqual(scanner.normalizeMerchantDomain('shop.nike.com'), 'nike.com', 'shop prefix');
  });

  it('strips store prefix', () => {
    assertEqual(scanner.normalizeMerchantDomain('store.apple.com'), 'apple.com', 'store prefix');
  });

  it('strips order prefix', () => {
    assertEqual(scanner.normalizeMerchantDomain('order.target.com'), 'target.com', 'order prefix');
  });

  it('strips email prefix', () => {
    assertEqual(scanner.normalizeMerchantDomain('email.nordstrom.com'), 'nordstrom.com', 'email prefix');
  });

  it('lowercases domain', () => {
    assertEqual(scanner.normalizeMerchantDomain('Amazon.COM'), 'amazon.com', 'Lowercases');
  });

  it('maps domain aliases', () => {
    assertEqual(scanner.normalizeMerchantDomain('iliabeauty.com'), 'ilia.com', 'Maps alias');
  });

  it('returns null for email service domains', () => {
    assertEqual(scanner.normalizeMerchantDomain('shopifyemail.com'), null, 'Shopify email → null');
    assertEqual(scanner.normalizeMerchantDomain('sendgrid.net'), null, 'SendGrid → null');
    assertEqual(scanner.normalizeMerchantDomain('klaviyo.com'), null, 'Klaviyo → null');
  });

  it('returns "unknown" for null input', () => {
    assertEqual(scanner.normalizeMerchantDomain(null), 'unknown', 'Null → unknown');
  });

  it('returns "unknown" for empty string', () => {
    assertEqual(scanner.normalizeMerchantDomain(''), 'unknown', 'Empty → unknown');
  });
});

// ============================================================
// generateOrderKey
// ============================================================

describe('Scanner - generateOrderKey', () => {
  it('uses domain + order_number when both present', () => {
    const card = {
      merchant_domain: 'amazon.com',
      order_number: '123-4567890-1234567',
    };
    assertEqual(
      scanner.generateOrderKey(card),
      'amazon.com::123-4567890-1234567',
      'domain::order_number'
    );
  });

  it('normalizes domain in key', () => {
    const card = {
      merchant_domain: 'www.Amazon.com',
      order_number: 'ABC-123',
    };
    assertEqual(
      scanner.generateOrderKey(card),
      'amazon.com::ABC-123',
      'Normalized domain'
    );
  });

  it('extracts order number from item_summary as fallback', () => {
    const card = {
      merchant_domain: 'amazon.com',
      item_summary: 'Your order 111-2222222-3333333 shipped',
    };
    assertEqual(
      scanner.generateOrderKey(card),
      'amazon.com::111-2222222-3333333',
      'Extracted from item_summary'
    );
  });

  it('falls back to item hash when no order number', () => {
    const card = {
      merchant_domain: 'target.com',
      item_summary: 'Nike Air Max Running Shoes',
    };
    const key = scanner.generateOrderKey(card);
    assert(key.startsWith('target.com::item::'), 'Uses item hash fallback');
  });

  it('falls back to card.id when nothing else available', () => {
    const card = {
      merchant_domain: 'target.com',
      id: 'backend-uuid-123',
    };
    assertEqual(scanner.generateOrderKey(card), 'backend-uuid-123', 'Falls back to id');
  });

  it('uses merchant name when domain is email service', () => {
    const card = {
      merchant_domain: 'shopifyemail.com',
      merchant: 'Allbirds',
      order_number: 'AB-5555',
    };
    const key = scanner.generateOrderKey(card);
    assert(key.startsWith('allbirds::'), 'Uses merchant name for email service domain');
  });

  it('produces deterministic keys', () => {
    const card = {
      merchant_domain: 'amazon.com',
      order_number: 'ORD-999',
    };
    const key1 = scanner.generateOrderKey(card);
    const key2 = scanner.generateOrderKey(card);
    assertEqual(key1, key2, 'Same input → same key');
  });
});

// ============================================================
// detectCancelledOrders
// ============================================================

describe('Scanner - detectCancelledOrders', () => {
  it('detects cancelled Amazon order from subject', () => {
    const metas = [{
      id: 'msg1',
      subject: 'Your order 123-4567890-1234567 has been cancelled',
      snippet: '',
    }];
    const result = scanner.detectCancelledOrders(metas);
    assert(result.has('123-4567890-1234567'), 'Detected cancelled order');
  });

  it('detects refund signal in subject', () => {
    const metas = [{
      id: 'msg2',
      subject: 'Refund issued for order 111-2222222-3333333',
      snippet: '',
    }];
    const result = scanner.detectCancelledOrders(metas);
    assert(result.has('111-2222222-3333333'), 'Detected refund order');
  });

  it('detects cancellation from body snippet', () => {
    const metas = [{
      id: 'msg3',
      subject: 'Update on order 999-8888888-7777777',
      snippet: 'Your order was cancelled due to payment issue',
    }];
    const result = scanner.detectCancelledOrders(metas);
    assert(result.has('999-8888888-7777777'), 'Detected from snippet');
  });

  it('returns empty set when no cancellations', () => {
    const metas = [{
      id: 'msg4',
      subject: 'Your order has shipped',
      snippet: 'Arriving tomorrow',
    }];
    const result = scanner.detectCancelledOrders(metas);
    assertEqual(result.size, 0, 'No cancellations');
  });

  it('handles empty input', () => {
    assertEqual(scanner.detectCancelledOrders([]).size, 0, 'Empty input');
  });

  it('handles multiple cancelled orders', () => {
    const metas = [
      { id: 'a', subject: 'Cancelled: 111-1111111-1111111', snippet: '' },
      { id: 'b', subject: 'Cancellation: 222-2222222-2222222', snippet: '' },
    ];
    const result = scanner.detectCancelledOrders(metas);
    assertEqual(result.size, 2, 'Two cancelled orders');
  });
});
