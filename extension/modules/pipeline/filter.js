/**
 * P1: Early Filter (FREE)
 *
 * Blocks emails from categories that should never create Orders:
 * - Groceries (Whole Foods, Instacart, meal kits)
 * - Digital goods (ebooks, app stores, streaming)
 * - Subscriptions/renewals
 * - Rideshare/travel (Uber, Lyft, airlines, hotels)
 * - Banking/financial alerts
 *
 * Note: 'unsubscribe' in footer is NOT a block signal.
 */

const FILTER_LOG_PREFIX = '[ReturnWatch:Filter]';

// ============================================================
// BLOCKLIST CONFIGURATION
// ============================================================

/**
 * Domains that are hard-blocked (no Orders created).
 * Organized by category for maintainability.
 */
const BLOCKED_DOMAINS = {
  // Groceries
  groceries: [
    'wholefoodsmarket.com',
    'wholefoods.com',
    'instacart.com',
    'shipt.com',
    'freshdirect.com',
    'peapod.com',
    'safeway.com',
    'kroger.com',
    'albertsons.com',
    'publix.com',
    'wegmans.com',
    'traderjoes.com',
    'aldi.com',
    'costco.com', // Primarily groceries
  ],

  // Meal kits
  meal_kits: [
    'hellofresh.com',
    'blueapron.com',
    'homechef.com',
    'sunbasket.com',
    'greenchef.com',
    'freshly.com',
    'factor75.com',
    'dailyharvest.com',
  ],

  // Digital goods & SaaS
  // NOTE: amazon.com is NOT blocked by domain - legitimate retail purchases come from it.
  // Digital Amazon purchases are blocked by keywords (ebook, kindle edition, etc.)
  digital: [
    'apple.com',        // App Store, iTunes
    'itunes.com',
    'google.com',       // Play Store
    'play.google.com',
    'kindle.com',       // Kindle ebooks
    'audible.com',      // Audiobooks
    'steam.com',
    'steampowered.com',
    'epicgames.com',
    'gog.com',
    'humblebundle.com',
    'anthropic.com',    // AI SaaS
    'openai.com',       // AI SaaS
    'mobbin.com',       // Design tool SaaS
  ],

  // Subscriptions/streaming
  subscriptions: [
    'netflix.com',
    'spotify.com',
    'hulu.com',
    'disneyplus.com',
    'hbomax.com',
    'max.com',
    'peacocktv.com',
    'paramountplus.com',
    'appletv.com',
    'primevideo.com',
    'youtube.com',
    'twitch.tv',
    'crunchyroll.com',
    'pandora.com',
    'tidal.com',
    'deezer.com',
    'dropbox.com',
    'icloud.com',
    'onedrive.com',
    'notion.so',
    'slack.com',
    'zoom.us',
    'adobe.com',
    'microsoft.com',    // Microsoft 365
    'office.com',
  ],

  // Rideshare/food delivery
  rideshare: [
    'uber.com',
    'lyft.com',
    'doordash.com',
    'grubhub.com',
    'postmates.com',
    'caviar.com',
    'seamless.com',
    'ubereats.com',
  ],

  // Tickets & events
  tickets: [
    'shotgun.live',
    'ticketmaster.com',
    'stubhub.com',
    'eventbrite.com',
    'seatgeek.com',
    'dice.fm',
  ],

  // Telecom & eSIM (digital passes, not physical goods)
  telecom: [
    'mintmobile.com',
    'holafly.com',
    't-mobile.com',
    'att.com',
    'verizon.com',
    'xfinity.com',
    'spectrum.com',
  ],

  // Services (warranty, insurance, returns processing)
  services: [
    'asurion.com',
    'happyreturns.com',
    'allstate.com',
    'squaretrade.com',
  ],

  // Travel
  travel: [
    'united.com',
    'delta.com',
    'aa.com',           // American Airlines
    'southwest.com',
    'jetblue.com',
    'spirit.com',
    'frontier.com',
    'alaskaair.com',
    'airbnb.com',
    'vrbo.com',
    'booking.com',
    'expedia.com',
    'hotels.com',
    'marriott.com',
    'hilton.com',
    'hyatt.com',
    'ihg.com',
    'kayak.com',
    'priceline.com',
    'tripadvisor.com',
  ],

  // Banking/financial
  banking: [
    'chase.com',
    'bankofamerica.com',
    'wellsfargo.com',
    'citibank.com',
    'capitalone.com',
    'discover.com',
    'americanexpress.com',
    'amex.com',
    'paypal.com',
    'venmo.com',
    'cashapp.com',
    'zelle.com',
    'mint.com',
    'robinhood.com',
    'coinbase.com',
    'fidelity.com',
    'schwab.com',
    'vanguard.com',
    'etrade.com',
    'tdameritrade.com',
    'chime.com',
  ],
};

/**
 * Keywords in subject/snippet that indicate non-returnable categories.
 * These are checked even if domain is not in blocklist.
 */
const BLOCKED_KEYWORDS = {
  // Digital purchases & services
  digital: [
    'ebook',
    'e-book',
    'kindle edition',
    'digital download',
    'digital purchase',
    'app store',
    'play store',
    'in-app purchase',
    'subscription',
    'your membership',
    'monthly plan',
    'annual plan',
    'renewal',
    'auto-renewal',
    'prime video',
    'watch now',
    'stream now',
    'digital order',
    'verification code',
    'is your verification',
    'esim',
    'e-sim',
    'protection plan',
    'protection plan terms',
    'terms and conditions',
    'keep your',
    'open drawing',
  ],

  // Food/groceries
  groceries: [
    'grocery',
    'groceries',
    'produce',
    'fresh food',
    'meal kit',
    'food delivery',
    'restaurant order',
    'whole foods',
    'whole foods market',
  ],

  // Travel/rideshare/telecom
  travel: [
    'your ride',
    'trip receipt',
    'flight confirmation',
    'hotel reservation',
    'booking confirmation',
    'itinerary',
    'travel receipt',
    'roaming',
    'vodafone travel',
  ],

  // Banking/refunds
  banking: [
    'account statement',
    'bank statement',
    'transaction alert',
    'payment received',
    'direct deposit',
    'wire transfer',
    'credit card statement',
    'your refund',
    'refund processed',
    'refund confirmation',
  ],
};

// Flatten domain lists for quick lookup
const BLOCKED_DOMAIN_SET = new Set(
  Object.values(BLOCKED_DOMAINS).flat()
);

// Flatten keyword lists for checking
const BLOCKED_KEYWORD_LIST = Object.values(BLOCKED_KEYWORDS).flat();

// ============================================================
// FILTER FUNCTIONS
// ============================================================

/**
 * Extract merchant domain from email From address.
 *
 * @param {string} from_address - e.g., "Amazon <ship-confirm@amazon.com>"
 * @returns {string} Domain like "amazon.com"
 */
function extractMerchantDomain(from_address) {
  if (!from_address) return '';

  // Extract email from "Name <email@domain.com>" or plain "email@domain.com"
  const emailMatch = from_address.match(/<([^>]+)>/) || from_address.match(/([^\s<>]+@[^\s<>]+)/);
  if (!emailMatch) return '';

  const email = emailMatch[1] || emailMatch[0];
  const atIndex = email.indexOf('@');
  if (atIndex === -1) return '';

  let domain = email.substring(atIndex + 1).toLowerCase();

  // Handle subdomains: ship-confirm@amazon.com -> amazon.com
  // But keep multi-part TLDs: orders@store.co.uk -> store.co.uk
  const parts = domain.split('.');
  if (parts.length > 2) {
    // Check for common multi-part TLDs
    const lastTwo = parts.slice(-2).join('.');
    const multiPartTLDs = ['co.uk', 'com.au', 'co.jp', 'com.br', 'co.nz'];
    if (multiPartTLDs.includes(lastTwo)) {
      domain = parts.slice(-3).join('.');
    } else {
      domain = parts.slice(-2).join('.');
    }
  }

  return domain;
}

/**
 * Check if a domain is in the blocklist.
 *
 * @param {string} merchant_domain
 * @returns {boolean}
 */
function isDomainBlocked(merchant_domain) {
  if (!merchant_domain) return false;
  return BLOCKED_DOMAIN_SET.has(merchant_domain.toLowerCase());
}

/**
 * Check if subject/snippet contains blocked keywords.
 *
 * @param {string} subject
 * @param {string} snippet
 * @returns {{blocked: boolean, reason: string|null}}
 */
function checkBlockedKeywords(subject, snippet) {
  const text = `${subject || ''} ${snippet || ''}`.toLowerCase();

  for (const keyword of BLOCKED_KEYWORD_LIST) {
    if (text.includes(keyword.toLowerCase())) {
      return { blocked: true, reason: `keyword: ${keyword}` };
    }
  }

  return { blocked: false, reason: null };
}

/**
 * Get the category of a blocked domain.
 *
 * @param {string} merchant_domain
 * @returns {string|null} Category name or null if not blocked
 */
function getBlockedCategory(merchant_domain) {
  if (!merchant_domain) return null;
  const domain = merchant_domain.toLowerCase();

  for (const [category, domains] of Object.entries(BLOCKED_DOMAINS)) {
    if (domains.includes(domain)) {
      return category;
    }
  }

  return null;
}

/**
 * Main filter function: Check if an email should be blocked.
 *
 * @param {string} from_address - Full From header
 * @param {string} subject
 * @param {string} snippet
 * @returns {{blocked: boolean, reason: string|null, merchant_domain: string}}
 */
function filterEmail(from_address, subject, snippet) {
  const merchant_domain = extractMerchantDomain(from_address);

  // Check domain blocklist
  if (isDomainBlocked(merchant_domain)) {
    const category = getBlockedCategory(merchant_domain);
    const reason = `domain_blocked: ${merchant_domain} (${category})`;
    console.log(FILTER_LOG_PREFIX, 'FILTER_BLOCKED', reason);
    return { blocked: true, reason, merchant_domain };
  }

  // Check keyword blocklist
  const keywordCheck = checkBlockedKeywords(subject, snippet);
  if (keywordCheck.blocked) {
    console.log(FILTER_LOG_PREFIX, 'FILTER_BLOCKED', keywordCheck.reason);
    return { blocked: true, reason: keywordCheck.reason, merchant_domain };
  }

  return { blocked: false, reason: null, merchant_domain };
}

/**
 * Check if an email is blocked by domain only (quick check).
 *
 * @param {string} merchant_domain
 * @returns {boolean}
 */
function isBlocked(merchant_domain) {
  return isDomainBlocked(merchant_domain);
}

/**
 * Extract a display name for the merchant from the From address.
 *
 * @param {string} from_address - e.g., "Amazon.com <ship-confirm@amazon.com>"
 * @returns {string} Display name like "Amazon.com"
 */
function extractMerchantDisplayName(from_address) {
  if (!from_address) return 'Unknown';

  // Try to extract name from "Name <email>" format
  const nameMatch = from_address.match(/^([^<]+)</);
  if (nameMatch) {
    return nameMatch[1].trim().replace(/"/g, '');
  }

  // Fall back to domain
  const domain = extractMerchantDomain(from_address);
  if (domain) {
    // Capitalize first letter: amazon.com -> Amazon.com
    return domain.charAt(0).toUpperCase() + domain.slice(1);
  }

  return 'Unknown';
}
