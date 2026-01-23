/**
 * Unit Tests for P4: Email Classification (classifier.js)
 *
 * Tests email type classification and order seeding logic.
 */

// Load the classifier module
const classifier = loadModuleFunctions('modules/pipeline/classifier.js');

describe('P4: Classifier - classifyEmailType', () => {
  it('classifies confirmation emails', () => {
    assertEqual(
      classifier.classifyEmailType('Your order confirmed!', ''),
      'confirmation',
      'Recognizes "order confirmed"'
    );
    assertEqual(
      classifier.classifyEmailType('Order confirmation', ''),
      'confirmation',
      'Recognizes "Order confirmation"'
    );
    assertEqual(
      classifier.classifyEmailType('Thank you for your order', ''),
      'confirmation',
      'Recognizes "Thank you for your order"'
    );
  });

  it('classifies shipping emails', () => {
    assertEqual(
      classifier.classifyEmailType('Your package has shipped', ''),
      'shipping',
      'Recognizes "has shipped"'
    );
    assertEqual(
      classifier.classifyEmailType('Your order is on its way', ''),
      'shipping',
      'Recognizes "on its way"'
    );
  });

  it('classifies delivery emails', () => {
    assertEqual(
      classifier.classifyEmailType('Your package was delivered', ''),
      'delivery',
      'Recognizes "was delivered"'
    );
    assertEqual(
      classifier.classifyEmailType('Your order has been delivered', ''),
      'delivery',
      'Recognizes "has been delivered"'
    );
  });

  it('prioritizes delivery over shipping', () => {
    assertEqual(
      classifier.classifyEmailType('Shipped and delivered today', ''),
      'delivery',
      'Delivery takes priority over shipping'
    );
  });

  it('classifies other emails', () => {
    assertEqual(
      classifier.classifyEmailType('Thank you for contacting us', ''),
      'other',
      'Unrecognized emails are "other"'
    );
  });

  it('checks both subject and snippet', () => {
    assertEqual(
      classifier.classifyEmailType('Update', 'Your package was delivered'),
      'delivery',
      'Checks snippet for keywords'
    );
  });
});

describe('P4: Classifier - isPurchaseConfirmed', () => {
  it('confirms when order_id is present', () => {
    assert(
      classifier.isPurchaseConfirmed('Random subject', '', true) === true,
      'Confirmed when has_order_id=true'
    );
  });

  it('confirms with amount in confirmation email', () => {
    assert(
      classifier.isPurchaseConfirmed('Order confirmed $99.99', '', false) === true,
      'Confirmed with amount in confirmation'
    );
  });

  it('confirms with purchase phrases', () => {
    // Uses "order confirmation" keyword + "payment received" strong phrase
    assert(
      classifier.isPurchaseConfirmed('Order confirmation - payment received', '', false) === true,
      'Confirmed with confirmation keyword + strong phrase'
    );
  });

  it('does not confirm shipping updates without order_id', () => {
    assert(
      classifier.isPurchaseConfirmed('Your package has shipped', '', false) === false,
      'Not confirmed for shipping without order_id'
    );
  });
});

describe('P4: Classifier - shouldSeedOrder', () => {
  it('seeds full order for confirmed confirmation', () => {
    const result = classifier.shouldSeedOrder('confirmation', true, false);
    assertEqual(result.should_seed, true, 'Should seed');
    assertEqual(result.seed_type, 'full', 'Full seed type');
  });

  it('seeds partial order for shipping with tracking', () => {
    const result = classifier.shouldSeedOrder('shipping', false, true);
    assertEqual(result.should_seed, true, 'Should seed');
    assertEqual(result.seed_type, 'partial', 'Partial seed type');
  });

  it('seeds partial order for delivery with tracking', () => {
    const result = classifier.shouldSeedOrder('delivery', false, true);
    assertEqual(result.should_seed, true, 'Should seed');
    assertEqual(result.seed_type, 'partial', 'Partial seed type');
  });

  it('does not seed for other emails without purchase confirmation', () => {
    const result = classifier.shouldSeedOrder('other', false, false);
    assertEqual(result.should_seed, false, 'Should not seed');
  });

  it('does not seed for shipping without tracking', () => {
    const result = classifier.shouldSeedOrder('shipping', false, false);
    assertEqual(result.should_seed, false, 'Should not seed shipping without tracking');
  });
});

describe('P4: Classifier - containsAmount', () => {
  it('detects dollar amounts', () => {
    assert(
      classifier.containsAmount('Total: $99.99') === true,
      'Detects $99.99'
    );
    assert(
      classifier.containsAmount('Order total: $1,234.56') === true,
      'Detects $1,234.56 with comma'
    );
  });

  it('does not detect non-amounts', () => {
    assert(
      classifier.containsAmount('Thank you for your order') === false,
      'No false positive for text without amount'
    );
  });
});

describe('P4: Classifier - classifyEmail (full)', () => {
  it('returns email_type and purchase_confirmed', () => {
    const result = classifier.classifyEmail(
      'Your Amazon order #123-456 is confirmed',
      'Total: $99.99',
      true
    );
    assertEqual(result.email_type, 'confirmation', 'Correct email type');
    assertEqual(result.purchase_confirmed, true, 'Purchase is confirmed');
  });

  it('handles shipping emails', () => {
    const result = classifier.classifyEmail(
      'Your package has shipped',
      'Track your package',
      false
    );
    assertEqual(result.email_type, 'shipping', 'Correct email type');
    assertEqual(result.purchase_confirmed, false, 'Not a purchase confirmation');
  });
});
