/**
 * Unit Tests for Evidence Validation (evidence.js)
 *
 * Tests that extracted values appear literally in source quotes.
 */

// Load the evidence module
const evidence = loadModuleFunctions('modules/enrichment/evidence.js');

describe('Evidence - dateAppearsInQuote', () => {
  it('finds ISO date in quote', () => {
    assert(
      evidence.dateAppearsInQuote('Return by 2024-01-15', '2024-01-15') === true,
      'ISO date found in quote'
    );
  });

  it('finds US formatted date in quote', () => {
    assert(
      evidence.dateAppearsInQuote('Return by January 15, 2024', '2024-01-15') === true,
      'US long date found in quote'
    );
  });

  it('finds short US date in quote', () => {
    assert(
      evidence.dateAppearsInQuote('Return by Jan 15, 2024', '2024-01-15') === true,
      'US short date found in quote'
    );
  });

  it('finds numeric date in quote', () => {
    assert(
      evidence.dateAppearsInQuote('Return by 1/15/2024', '2024-01-15') === true,
      'Numeric date found in quote'
    );
  });

  it('returns false when date not in quote', () => {
    assert(
      evidence.dateAppearsInQuote('Thank you for your order', '2024-01-15') === false,
      'Returns false when date missing'
    );
  });

  it('handles null inputs', () => {
    assert(
      evidence.dateAppearsInQuote(null, '2024-01-15') === false,
      'Handles null quote'
    );
    assert(
      evidence.dateAppearsInQuote('some quote', null) === false,
      'Handles null date'
    );
  });
});

describe('Evidence - daysAppearsInQuote', () => {
  it('finds days in quote (space)', () => {
    assert(
      evidence.daysAppearsInQuote('30 day return policy', 30) === true,
      'Finds "30 day" pattern'
    );
  });

  it('finds days in quote (hyphenated)', () => {
    assert(
      evidence.daysAppearsInQuote('30-day return policy', 30) === true,
      'Finds "30-day" pattern'
    );
  });

  it('returns false when days not in quote', () => {
    assert(
      evidence.daysAppearsInQuote('return policy', 30) === false,
      'Returns false when days missing'
    );
  });

  it('handles null inputs', () => {
    assert(
      evidence.daysAppearsInQuote(null, 30) === false,
      'Handles null quote'
    );
    assert(
      evidence.daysAppearsInQuote('30 day', null) === false,
      'Handles null days'
    );
  });
});

describe('Evidence - amountAppearsInQuote', () => {
  it('finds dollar amount in quote', () => {
    assert(
      evidence.amountAppearsInQuote('Total: $99.99', 99.99) === true,
      'Finds $99.99 in quote'
    );
  });

  it('finds amount with comma', () => {
    assert(
      evidence.amountAppearsInQuote('Order total: $1,299.00', 1299.00) === true,
      'Finds $1,299.00 in quote'
    );
  });

  it('returns false when amount not in quote', () => {
    assert(
      evidence.amountAppearsInQuote('Thank you', 99.99) === false,
      'Returns false when amount missing'
    );
  });
});

describe('Evidence - findQuoteContaining', () => {
  it('finds quote containing search term', () => {
    const body = 'Thank you for your order. You have 30 days to return. Thank you!';
    const quote = evidence.findQuoteContaining(body, '30 days', 100);
    assert(quote !== null, 'Returns a quote');
    assert(quote.includes('30 days'), 'Quote contains search term');
  });

  it('returns null when term not found', () => {
    const quote = evidence.findQuoteContaining('Thank you', 'not found', 100);
    assertEqual(quote, null, 'Returns null when term missing');
  });
});

describe('Evidence - validateExtraction', () => {
  it('validates extraction with matching quote', () => {
    const extraction = {
      return_by_date: '2024-01-15',
      evidence_quote: 'Return by January 15, 2024',
    };
    const result = evidence.validateExtraction(extraction, 'full body text');
    // Note: valid can be truthy (the quote string) due to && operator behavior
    assert(!!result.valid, 'Validation passes');
    assertEqual(result.validated.return_by_date, '2024-01-15', 'Date is validated');
    assert(result.validated.evidence_quote !== null, 'Quote is preserved');
  });

  it('rejects extraction when date not in quote', () => {
    const extraction = {
      return_by_date: '2024-01-15',
      evidence_quote: 'Thank you for your order',
    };
    const result = evidence.validateExtraction(extraction, 'Thank you for your order');
    // Should fail validation since date isn't in quote OR body
    assert(result.errors.length > 0 || result.validated.return_by_date === undefined,
      'Rejects when date not found');
  });

  it('validates return_window_days', () => {
    const extraction = {
      return_window_days: 30,
      evidence_quote: '30 day return policy',
    };
    const result = evidence.validateExtraction(extraction, 'body');
    assertEqual(result.validated.return_window_days, 30, 'Days validated');
  });

  it('handles null extraction', () => {
    const result = evidence.validateExtraction(null, 'body');
    assertEqual(result.valid, false, 'Invalid for null extraction');
    assert(result.errors.length > 0, 'Has error message');
  });
});

describe('Evidence - findDateQuote', () => {
  it('finds quote containing date', () => {
    const body = 'Your order will be delivered. Return by January 15, 2024 for full refund.';
    const quote = evidence.findDateQuote(body, '2024-01-15');
    assert(quote !== null, 'Finds date quote');
    assert(quote.includes('January 15') || quote.includes('2024-01-15'), 'Quote contains date');
  });

  it('returns null when date not in body', () => {
    const quote = evidence.findDateQuote('Thank you for shopping', '2024-01-15');
    assertEqual(quote, null, 'Returns null when date not found');
  });
});
