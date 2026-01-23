/**
 * Unit Tests for P5: Field Extraction (extractor.js)
 *
 * Tests regex-based extraction of order data from emails.
 */

// Load the extractor module
const extractor = loadModuleFunctions('modules/pipeline/extractor.js');

// Load the linker module for primary key extraction functions
const linker = loadModuleFunctions('modules/pipeline/linker.js');

describe('P5: Extractor - Date Parsing', () => {
  it('parses ISO dates', () => {
    assertEqual(
      extractor.parseDateToISO('2024-01-15'),
      '2024-01-15',
      'Parses ISO format'
    );
  });

  it('parses US long format (January 15, 2024)', () => {
    assertEqual(
      extractor.parseDateToISO('January 15, 2024'),
      '2024-01-15',
      'Parses "January 15, 2024"'
    );
  });

  it('parses US short format (Jan 15, 2024)', () => {
    assertEqual(
      extractor.parseDateToISO('Jan 15, 2024'),
      '2024-01-15',
      'Parses "Jan 15, 2024"'
    );
  });

  it('parses numeric format (1/15/2024)', () => {
    assertEqual(
      extractor.parseDateToISO('1/15/2024'),
      '2024-01-15',
      'Parses "1/15/2024"'
    );
  });

  it('returns null for invalid dates', () => {
    assertEqual(
      extractor.parseDateToISO('not a date'),
      null,
      'Returns null for invalid input'
    );
  });
});

describe('P5: Extractor - extractDates', () => {
  it('extracts multiple dates from text', () => {
    const dates = extractor.extractDates('Order placed Jan 10, 2024. Delivery by Jan 15, 2024.');
    assert(dates.length >= 2, 'Extracts multiple dates');
    assert(dates.includes('2024-01-10'), 'Includes first date');
    assert(dates.includes('2024-01-15'), 'Includes second date');
  });

  it('returns empty array for no dates', () => {
    const dates = extractor.extractDates('Thank you for your order');
    assertEqual(dates.length, 0, 'Returns empty array when no dates');
  });
});

describe('P5: Linker - Order ID Extraction', () => {
  it('extracts Amazon order ID', () => {
    const result = linker.extractOrderId('Order #123-4567890-1234567');
    assertEqual(result, '123-4567890-1234567', 'Extracts Amazon order ID');
  });

  it('extracts simple order number', () => {
    const result = linker.extractOrderId('Order: 12345678');
    assertEqual(result, '12345678', 'Extracts simple order number');
  });

  it('extracts order ID with prefix', () => {
    const result = linker.extractOrderId('Order Number: ORD-12345');
    assert(result !== null, 'Extracts order ID with prefix');
  });

  it('returns null when no order ID', () => {
    const result = linker.extractOrderId('Thank you for your purchase');
    assertEqual(result, null, 'Returns null when no order ID');
  });
});

describe('P5: Linker - Tracking Number Extraction', () => {
  it('extracts UPS tracking number', () => {
    const result = linker.extractTrackingNumber('Tracking: 1Z999AA10123456784');
    assertEqual(result, '1Z999AA10123456784', 'Extracts UPS tracking');
  });

  it('extracts FedEx tracking number', () => {
    const result = linker.extractTrackingNumber('Track: 123456789012');
    assertEqual(result, '123456789012', 'Extracts FedEx 12-digit tracking');
  });

  it('extracts USPS tracking number', () => {
    const result = linker.extractTrackingNumber('9400111899223033005014');
    assertEqual(result, '9400111899223033005014', 'Extracts USPS tracking');
  });

  it('returns null when no tracking', () => {
    const result = linker.extractTrackingNumber('Your order has shipped');
    assertEqual(result, null, 'Returns null when no tracking');
  });
});

describe('P5: Extractor - Amount Extraction', () => {
  it('extracts dollar amount', () => {
    const result = extractor.extractAmount('Total: $99.99');
    assertEqual(result.amount, 99.99, 'Extracts amount value');
    assertEqual(result.currency, 'USD', 'Currency is USD');
  });

  it('extracts amount with comma', () => {
    const result = extractor.extractAmount('Order total: $1,299.00');
    assertEqual(result.amount, 1299.00, 'Extracts amount with comma');
  });

  it('returns null when no amount', () => {
    const result = extractor.extractAmount('Thank you');
    assertEqual(result.amount, null, 'Returns null when no amount');
  });
});

describe('P5: Extractor - Return Policy Extraction', () => {
  it('extracts return window days', () => {
    // The pattern requires space: "30 day" or "30 days"
    assertEqual(
      extractor.extractReturnWindowDays('30 day return policy'),
      30,
      'Extracts "30 day"'
    );
    assertEqual(
      extractor.extractReturnWindowDays('return within 60 days'),
      60,
      'Extracts "within 60 days"'
    );
  });

  it('extracts explicit return-by date', () => {
    const result = extractor.extractReturnByDate('Return by January 31, 2024');
    assertEqual(result, '2024-01-31', 'Extracts return-by date');
  });

  it('returns null when no return policy', () => {
    assertEqual(
      extractor.extractReturnWindowDays('Thank you for shopping'),
      null,
      'Returns null when no window'
    );
  });
});

describe('P5: Extractor - Return Anchors Detection', () => {
  it('detects return policy anchors', () => {
    // Returns { hasAnchors, isFinalSale, anchors }
    const result = extractor.detectReturnAnchors('30 day return window');
    assert(result.hasAnchors === true, 'Detects return anchor');
    assert(result.anchors.length > 0, 'Has anchor matches');
  });

  it('returns empty array when no anchors', () => {
    const result = extractor.detectReturnAnchors('Thank you for your purchase');
    assert(result.hasAnchors === false, 'No anchors in generic text');
    assertEqual(result.anchors.length, 0, 'Anchors array is empty');
  });

  it('detects return policy phrases', () => {
    // "return window" matches the pattern
    const result = extractor.detectReturnAnchors('Check return window details');
    assert(result.hasAnchors === true, 'Detects "return window" anchor');
  });
});

describe('P5: Extractor - extractFields (full)', () => {
  it('extracts all fields from email', () => {
    // Use full Amazon order ID format (3 parts)
    const subject = 'Your Amazon order #123-4567890-1234567 has shipped';
    const snippet = 'Track your package: 1Z999AA10123456784';
    const body = 'Order total: $99.99. Delivery by Jan 20, 2024.';

    const result = extractor.extractFields(subject, snippet, body);

    assertEqual(result.order_id, '123-4567890-1234567', 'Extracts order_id');
    assertEqual(result.tracking_number, '1Z999AA10123456784', 'Extracts tracking');
    assertEqual(result.amount, 99.99, 'Extracts amount');
    assert(result.item_summary !== null, 'Has item summary');
  });

  it('handles missing fields gracefully', () => {
    const result = extractor.extractFields('Thank you', '', '');
    assertEqual(result.order_id, null, 'order_id is null');
    assertEqual(result.tracking_number, null, 'tracking is null');
  });
});

describe('P5: Extractor - Item Summary', () => {
  it('extracts item from subject', () => {
    const result = extractor.extractItemSummary(
      'Your Sony WH-1000XM5 Headphones have shipped',
      ''
    );
    assert(result !== null && result.length > 0, 'Extracts item from subject');
  });

  it('uses subject as fallback', () => {
    const result = extractor.extractItemSummary('Order #123 shipped', '');
    assert(result !== null, 'Returns something even for generic subject');
  });
});
