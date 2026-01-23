/**
 * P4: Sentinel Classification (Rules First)
 *
 * Classifies emails by type using keyword matching:
 * - confirmation: Order placed, receipt, invoice
 * - shipping: Shipped, on the way, tracking
 * - delivery: Delivered, left at door
 * - other: Doesn't match above patterns
 *
 * Also determines if an email confirms a purchase for order seeding.
 */

const CLASSIFIER_LOG_PREFIX = '[ReturnWatch:Classifier]';

// ============================================================
// CLASSIFICATION KEYWORDS
// ============================================================

/**
 * Keywords indicating a delivery email.
 * These are checked first (highest priority).
 */
const DELIVERY_KEYWORDS = [
  'delivered',
  'was delivered',
  'has been delivered',
  'left at your door',
  'left at door',
  'left at front door',
  'out for delivery',
  'delivery complete',
  'successfully delivered',
  'package arrived',
  'your package was',
  'dropped off',
];

/**
 * Keywords indicating a shipping email.
 */
const SHIPPING_KEYWORDS = [
  'shipped',
  'has shipped',
  'on the way',
  'on its way',
  'in transit',
  'tracking number',
  'track your package',
  'track your order',
  'shipment confirmation',
  'shipping confirmation',
  'your order is on the way',
  'dispatched',
  'out for shipping',
  'carrier picked up',
];

/**
 * Keywords indicating an order confirmation email.
 */
const CONFIRMATION_KEYWORDS = [
  'order confirmed',
  'order confirmation',
  'thanks for your order',
  'thank you for your order',
  'order placed',
  'your order has been placed',
  'receipt',
  'invoice',
  'order receipt',
  'purchase confirmation',
  'order received',
  'we got your order',
  'order #',
  'order number',
];

/**
 * Strong purchase phrases that indicate a real purchase
 * (even without an order_id).
 */
const STRONG_PURCHASE_PHRASES = [
  'your order total',
  'order subtotal',
  'payment received',
  'payment confirmed',
  'charged to your',
  'billing address',
  'shipping address',
  'items ordered',
  'qty:',
  'quantity:',
  'price:',
  'total:',
  'grand total',
];

/**
 * Amount patterns to detect if email has purchase amount.
 */
const AMOUNT_PATTERNS = [
  /\$\d+\.\d{2}/,                    // $123.45
  /\$\d+,\d{3}\.\d{2}/,              // $1,234.56
  /USD\s*\d+\.\d{2}/i,               // USD 123.45
  /total[:\s]+\$?\d+\.\d{2}/i,       // Total: $123.45
];

// ============================================================
// CLASSIFICATION FUNCTIONS
// ============================================================

/**
 * Check if text contains any keyword from a list.
 *
 * @param {string} text - Text to search
 * @param {string[]} keywords - Keywords to look for
 * @returns {boolean}
 */
function containsKeyword(text, keywords) {
  if (!text) return false;
  const lowerText = text.toLowerCase();

  for (const keyword of keywords) {
    if (lowerText.includes(keyword.toLowerCase())) {
      return true;
    }
  }

  return false;
}

/**
 * Check if text contains an amount pattern.
 *
 * @param {string} text
 * @returns {boolean}
 */
function containsAmount(text) {
  if (!text) return false;

  for (const pattern of AMOUNT_PATTERNS) {
    if (pattern.test(text)) {
      return true;
    }
  }

  return false;
}

/**
 * Extract amount from text if present.
 *
 * @param {string} text
 * @returns {number|null}
 */
function extractAmount(text) {
  if (!text) return null;

  // Try to match dollar amounts
  const match = text.match(/\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)/);
  if (match) {
    return parseFloat(match[1].replace(/,/g, ''));
  }

  return null;
}

/**
 * Classify email type based on subject and snippet.
 *
 * Priority order: delivery > shipping > confirmation > other
 *
 * @param {string} subject
 * @param {string} snippet
 * @returns {EmailType} 'confirmation' | 'shipping' | 'delivery' | 'other'
 */
function classifyEmailType(subject, snippet) {
  const text = `${subject || ''} ${snippet || ''}`;

  // Check in priority order
  if (containsKeyword(text, DELIVERY_KEYWORDS)) {
    return EMAIL_TYPE.DELIVERY;
  }

  if (containsKeyword(text, SHIPPING_KEYWORDS)) {
    return EMAIL_TYPE.SHIPPING;
  }

  if (containsKeyword(text, CONFIRMATION_KEYWORDS)) {
    return EMAIL_TYPE.CONFIRMATION;
  }

  return EMAIL_TYPE.OTHER;
}

/**
 * Determine if email confirms a purchase.
 *
 * purchase_confirmed = true if:
 * - order_id extracted (from linker), OR
 * - confirmation keywords AND amount found, OR
 * - confirmation keywords AND strong purchase phrase
 *
 * @param {string} subject
 * @param {string} snippet
 * @param {boolean} has_order_id - Whether order_id was extracted
 * @returns {boolean}
 */
function isPurchaseConfirmed(subject, snippet, has_order_id = false) {
  // If we have an order_id, it's confirmed
  if (has_order_id) {
    return true;
  }

  const text = `${subject || ''} ${snippet || ''}`;

  // Check for confirmation keywords
  const hasConfirmation = containsKeyword(text, CONFIRMATION_KEYWORDS);

  if (!hasConfirmation) {
    return false;
  }

  // Confirmation + amount = confirmed
  if (containsAmount(text)) {
    return true;
  }

  // Confirmation + strong phrase = confirmed
  if (containsKeyword(text, STRONG_PURCHASE_PHRASES)) {
    return true;
  }

  return false;
}

/**
 * Full classification: email type + purchase confirmation.
 *
 * @param {string} subject
 * @param {string} snippet
 * @param {boolean} [has_order_id=false] - Whether order_id was extracted
 * @returns {{email_type: EmailType, purchase_confirmed: boolean, amount: number|null}}
 */
function classifyEmail(subject, snippet, has_order_id = false) {
  const email_type = classifyEmailType(subject, snippet);
  const purchase_confirmed = isPurchaseConfirmed(subject, snippet, has_order_id);
  const amount = extractAmount(`${subject || ''} ${snippet || ''}`);

  console.log(CLASSIFIER_LOG_PREFIX, 'Classified:',
    'type=', email_type,
    'confirmed=', purchase_confirmed,
    'amount=', amount
  );

  return { email_type, purchase_confirmed, amount };
}

/**
 * Determine if email should seed a new Order.
 *
 * Seeding rules (updated):
 * - has order_id → create full Order (strongest signal)
 * - confirmation + purchase_confirmed → create full Order
 * - shipping/delivery + tracking_number → create partial Order
 * - shipping/delivery + order_id → create full Order (link by order_id)
 * - otherwise → do not create Order
 *
 * @param {EmailType} email_type
 * @param {boolean} purchase_confirmed
 * @param {boolean} has_tracking_number
 * @param {boolean} [has_order_id=false] - Whether order_id was extracted
 * @returns {{should_seed: boolean, seed_type: 'full' | 'partial' | null}}
 */
function shouldSeedOrder(email_type, purchase_confirmed, has_tracking_number, has_order_id = false) {
  // Full order: has order_id (strongest signal - we know it's a real order)
  if (has_order_id) {
    console.log(CLASSIFIER_LOG_PREFIX, 'SEED_DECISION: full order (has order_id)');
    return { should_seed: true, seed_type: 'full' };
  }

  // Full order: confirmation + confirmed purchase
  if (email_type === EMAIL_TYPE.CONFIRMATION && purchase_confirmed) {
    console.log(CLASSIFIER_LOG_PREFIX, 'SEED_DECISION: full order (confirmation + confirmed)');
    return { should_seed: true, seed_type: 'full' };
  }

  // Partial order: shipping/delivery + tracking
  if ((email_type === EMAIL_TYPE.SHIPPING || email_type === EMAIL_TYPE.DELIVERY) && has_tracking_number) {
    console.log(CLASSIFIER_LOG_PREFIX, 'SEED_DECISION: partial order (shipping/delivery + tracking)');
    return { should_seed: true, seed_type: 'partial' };
  }

  console.log(CLASSIFIER_LOG_PREFIX, 'SEED_DECISION: no seed');
  return { should_seed: false, seed_type: null };
}
