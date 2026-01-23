/**
 * Unit Tests for P1: Early Filter (filter.js)
 *
 * Tests blocklist logic for domain and keyword filtering.
 */

// Load the filter module
const filter = loadModuleFunctions('modules/pipeline/filter.js');

describe('P1: Filter - extractMerchantDomain', () => {
  it('extracts domain from standard email format', () => {
    assertEqual(
      filter.extractMerchantDomain('Amazon <ship-confirm@amazon.com>'),
      'amazon.com',
      'Extract domain from "Name <email>" format'
    );
  });

  it('extracts domain from email-only format', () => {
    assertEqual(
      filter.extractMerchantDomain('noreply@target.com'),
      'target.com',
      'Extract domain from plain email'
    );
  });

  it('extracts root domain from subdomain', () => {
    assertEqual(
      filter.extractMerchantDomain('noreply@email.target.com'),
      'target.com',
      'Extract root domain from subdomain'
    );
  });

  it('handles nested subdomains', () => {
    assertEqual(
      filter.extractMerchantDomain('alerts@mail.notifications.amazon.com'),
      'amazon.com',
      'Extract root from deeply nested subdomain'
    );
  });

  it('returns empty string for empty input', () => {
    assertEqual(
      filter.extractMerchantDomain(''),
      '',
      'Return empty string for empty string'
    );
  });

  it('returns empty string for null input', () => {
    assertEqual(
      filter.extractMerchantDomain(null),
      '',
      'Return empty string for null input'
    );
  });
});

describe('P1: Filter - isDomainBlocked / isBlocked', () => {
  it('blocks grocery domains', () => {
    assert(
      filter.isBlocked('instacart.com') === true,
      'Instacart is blocked (grocery)'
    );
    assert(
      filter.isBlocked('wholefoodsmarket.com') === true,
      'Whole Foods is blocked (grocery)'
    );
  });

  it('blocks digital goods domains', () => {
    assert(
      filter.isBlocked('itunes.com') === true,
      'iTunes is blocked (digital)'
    );
    assert(
      filter.isBlocked('steampowered.com') === true,
      'Steam is blocked (digital)'
    );
  });

  it('blocks subscription domains', () => {
    assert(
      filter.isBlocked('netflix.com') === true,
      'Netflix is blocked (subscription)'
    );
    assert(
      filter.isBlocked('spotify.com') === true,
      'Spotify is blocked (subscription)'
    );
  });

  it('blocks rideshare domains', () => {
    assert(
      filter.isBlocked('uber.com') === true,
      'Uber is blocked (rideshare)'
    );
    assert(
      filter.isBlocked('lyft.com') === true,
      'Lyft is blocked (rideshare)'
    );
  });

  it('blocks banking domains', () => {
    assert(
      filter.isBlocked('chase.com') === true,
      'Chase is blocked (banking)'
    );
    assert(
      filter.isBlocked('paypal.com') === true,
      'PayPal is blocked (banking)'
    );
  });

  it('allows retail domains', () => {
    assert(
      filter.isBlocked('amazon.com') === false,
      'Amazon is NOT blocked (retail)'
    );
    assert(
      filter.isBlocked('target.com') === false,
      'Target is NOT blocked (retail)'
    );
    assert(
      filter.isBlocked('bestbuy.com') === false,
      'Best Buy is NOT blocked (retail)'
    );
  });

  it('allows unknown domains', () => {
    assert(
      filter.isBlocked('randomstore.com') === false,
      'Unknown domains are NOT blocked'
    );
  });

  it('handles case insensitivity', () => {
    assert(
      filter.isBlocked('UBER.COM') === true,
      'Blocking is case-insensitive'
    );
  });
});

describe('P1: Filter - checkBlockedKeywords', () => {
  it('blocks subscription keywords', () => {
    const result = filter.checkBlockedKeywords(
      'Your Netflix subscription renewal',
      ''
    );
    assert(result.blocked === true, 'Blocks "subscription" keyword');
  });

  it('blocks renewal keywords', () => {
    const result = filter.checkBlockedKeywords(
      'Your subscription has been renewed',
      ''
    );
    assert(result.blocked === true, 'Blocks "renewal" keyword');
  });

  it('blocks your membership keywords', () => {
    const result = filter.checkBlockedKeywords(
      'Your membership is active',
      ''
    );
    assert(result.blocked === true, 'Blocks "your membership" keyword');
  });

  it('allows normal purchase emails', () => {
    const result = filter.checkBlockedKeywords(
      'Your Amazon.com order has shipped',
      'Track your package'
    );
    assert(result.blocked === false, 'Allows normal shipping emails');
  });

  it('checks both subject and snippet', () => {
    const result = filter.checkBlockedKeywords(
      'Thank you',
      'Your subscription has been renewed'
    );
    assert(result.blocked === true, 'Checks snippet for blocked keywords');
  });
});

describe('P1: Filter - filterEmail (full filter)', () => {
  it('blocks by domain', () => {
    const result = filter.filterEmail(
      'Uber Receipts <receipts@uber.com>',
      'Your trip with Uber',
      'Total: $25.50'
    );
    assert(result.blocked === true, 'Blocks Uber by domain');
    assertEqual(result.merchant_domain, 'uber.com', 'Returns merchant domain');
    assert(result.reason.includes('domain_blocked'), 'Reason mentions domain');
  });

  it('blocks by keyword', () => {
    const result = filter.filterEmail(
      'Amazon <no-reply@amazon.com>',
      'Your Prime subscription renewal',
      'Your subscription renews today'
    );
    assert(result.blocked === true, 'Blocks by subscription keyword');
    assert(result.reason.includes('keyword'), 'Reason mentions keyword');
  });

  it('allows valid purchase emails', () => {
    const result = filter.filterEmail(
      'Amazon <ship-confirm@amazon.com>',
      'Your Amazon.com order #123-4567890 has shipped',
      'Your package is on its way. Track your package.'
    );
    assert(result.blocked === false, 'Allows valid Amazon shipping email');
    assertEqual(result.merchant_domain, 'amazon.com', 'Returns amazon.com domain');
    assertEqual(result.reason, null, 'No reason for allowed emails');
  });

  it('allows Target purchase emails', () => {
    const result = filter.filterEmail(
      'Target <orders@target.com>',
      'Your Target order was delivered',
      'Your package was delivered today'
    );
    assert(result.blocked === false, 'Allows valid Target email');
    assertEqual(result.merchant_domain, 'target.com', 'Returns target.com domain');
  });
});

describe('P1: Filter - extractMerchantDisplayName', () => {
  it('extracts name from "Name <email>" format', () => {
    assertEqual(
      filter.extractMerchantDisplayName('Amazon.com <ship-confirm@amazon.com>'),
      'Amazon.com',
      'Extracts display name before angle bracket'
    );
  });

  it('handles quoted names', () => {
    assertEqual(
      filter.extractMerchantDisplayName('"Target" <orders@target.com>'),
      'Target',
      'Removes quotes from display name'
    );
  });

  it('falls back to domain when no name', () => {
    assertEqual(
      filter.extractMerchantDisplayName('orders@bestbuy.com'),
      'Bestbuy.com',
      'Capitalizes domain as fallback'
    );
  });

  it('returns Unknown for empty input', () => {
    assertEqual(
      filter.extractMerchantDisplayName(''),
      'Unknown',
      'Returns Unknown for empty string'
    );
  });
});

describe('P1: Filter - getBlockedCategory', () => {
  it('returns category for blocked domains', () => {
    assertEqual(
      filter.getBlockedCategory('uber.com'),
      'rideshare',
      'Returns rideshare for Uber'
    );
    assertEqual(
      filter.getBlockedCategory('netflix.com'),
      'subscriptions',
      'Returns subscriptions for Netflix'
    );
    assertEqual(
      filter.getBlockedCategory('chase.com'),
      'banking',
      'Returns banking for Chase'
    );
  });

  it('returns null for non-blocked domains', () => {
    assertEqual(
      filter.getBlockedCategory('amazon.com'),
      null,
      'Returns null for Amazon'
    );
  });
});
