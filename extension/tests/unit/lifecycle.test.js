/**
 * Unit Tests for P8: Lifecycle & Deadline Computation (lifecycle.js)
 *
 * Tests date math, deadline computation, and display helpers.
 */

// Load the lifecycle module
const lifecycle = loadModuleFunctions('modules/pipeline/lifecycle.js');

// Load utils for shared helpers (getToday moved from lifecycle to utils)
const utils = loadModuleFunctions('modules/shared/utils.js');

// Mock constants for testing
const ORDER_STATUS = { ACTIVE: 'active', RETURNED: 'returned', DISMISSED: 'dismissed' };
const DEADLINE_CONFIDENCE = { EXACT: 'exact', ESTIMATED: 'estimated', UNKNOWN: 'unknown' };

describe('P8: Lifecycle - addDays', () => {
  it('adds days to a date', () => {
    assertEqual(
      lifecycle.addDays('2024-01-15', 30),
      '2024-02-14',
      'Adds 30 days correctly'
    );
  });

  it('handles month boundary', () => {
    assertEqual(
      lifecycle.addDays('2024-01-31', 30),
      '2024-03-01',
      'Crosses month boundary correctly'
    );
  });

  it('handles year boundary', () => {
    assertEqual(
      lifecycle.addDays('2024-12-15', 30),
      '2025-01-14',
      'Crosses year boundary correctly'
    );
  });

  it('handles negative days', () => {
    assertEqual(
      lifecycle.addDays('2024-01-15', -10),
      '2024-01-05',
      'Subtracts days correctly'
    );
  });

  it('handles leap year', () => {
    assertEqual(
      lifecycle.addDays('2024-02-28', 1),
      '2024-02-29',
      'Handles leap year Feb 29'
    );
  });
});

describe('P8: Lifecycle - daysBetween', () => {
  it('calculates positive difference', () => {
    assertEqual(
      lifecycle.daysBetween('2024-01-01', '2024-01-15'),
      14,
      'Calculates 14 days between'
    );
  });

  it('calculates negative difference', () => {
    assertEqual(
      lifecycle.daysBetween('2024-01-15', '2024-01-01'),
      -14,
      'Returns negative for past date'
    );
  });

  it('returns zero for same date', () => {
    assertEqual(
      lifecycle.daysBetween('2024-01-15', '2024-01-15'),
      0,
      'Returns 0 for same date'
    );
  });
});

describe('P8: Lifecycle - getAnchorDate', () => {
  it('prefers delivery_date', () => {
    const order = {
      delivery_date: '2024-01-20',
      ship_date: '2024-01-15',
      purchase_date: '2024-01-10',
    };
    const result = lifecycle.getAnchorDate(order);
    assertEqual(result.anchor_date, '2024-01-20', 'Uses delivery_date');
    assertEqual(result.anchor_type, 'delivery', 'Type is delivery');
  });

  it('falls back to ship_date', () => {
    const order = {
      ship_date: '2024-01-15',
      purchase_date: '2024-01-10',
    };
    const result = lifecycle.getAnchorDate(order);
    assertEqual(result.anchor_date, '2024-01-15', 'Uses ship_date');
    assertEqual(result.anchor_type, 'ship', 'Type is ship');
  });

  it('falls back to purchase_date', () => {
    const order = {
      purchase_date: '2024-01-10',
    };
    const result = lifecycle.getAnchorDate(order);
    assertEqual(result.anchor_date, '2024-01-10', 'Uses purchase_date');
    assertEqual(result.anchor_type, 'purchase', 'Type is purchase');
  });

  it('returns null when no dates', () => {
    const order = {};
    const result = lifecycle.getAnchorDate(order);
    assertEqual(result.anchor_date, null, 'Returns null');
    assertEqual(result.anchor_type, null, 'Type is null');
  });
});

describe('P8: Lifecycle - getDaysRemaining', () => {
  it('calculates days remaining', () => {
    const today = utils.getToday();
    const futureDate = lifecycle.addDays(today, 10);
    const order = { return_by_date: futureDate };

    const remaining = lifecycle.getDaysRemaining(order);
    assertEqual(remaining, 10, 'Calculates 10 days remaining');
  });

  it('returns negative for expired', () => {
    const today = utils.getToday();
    const pastDate = lifecycle.addDays(today, -5);
    const order = { return_by_date: pastDate };

    const remaining = lifecycle.getDaysRemaining(order);
    assertEqual(remaining, -5, 'Returns -5 for expired');
  });

  it('returns null when no deadline', () => {
    const order = {};
    assertEqual(lifecycle.getDaysRemaining(order), null, 'Null when no deadline');
  });
});

describe('P8: Lifecycle - getUrgencyLevel', () => {
  it('returns expired for negative days', () => {
    const today = utils.getToday();
    const pastDate = lifecycle.addDays(today, -1);
    const order = { return_by_date: pastDate };

    assertEqual(lifecycle.getUrgencyLevel(order), 'expired', 'Expired for past date');
  });

  it('returns urgent for 0-3 days', () => {
    const today = utils.getToday();
    const urgentDate = lifecycle.addDays(today, 2);
    const order = { return_by_date: urgentDate };

    assertEqual(lifecycle.getUrgencyLevel(order), 'urgent', 'Urgent for 2 days');
  });

  it('returns soon for 4-7 days', () => {
    const today = utils.getToday();
    const soonDate = lifecycle.addDays(today, 5);
    const order = { return_by_date: soonDate };

    assertEqual(lifecycle.getUrgencyLevel(order), 'soon', 'Soon for 5 days');
  });

  it('returns normal for 8+ days', () => {
    const today = utils.getToday();
    const normalDate = lifecycle.addDays(today, 20);
    const order = { return_by_date: normalDate };

    assertEqual(lifecycle.getUrgencyLevel(order), 'normal', 'Normal for 20 days');
  });

  it('returns null when no deadline', () => {
    const order = {};
    assertEqual(lifecycle.getUrgencyLevel(order), null, 'Null when no deadline');
  });
});

describe('P8: Lifecycle - shouldShowInReturnWatch', () => {
  it('shows active orders with known deadline', () => {
    const today = utils.getToday();
    const futureDate = lifecycle.addDays(today, 10);
    const order = {
      order_status: 'active',
      deadline_confidence: 'exact',
      return_by_date: futureDate,
    };

    assert(lifecycle.shouldShowInReturnWatch(order) === true, 'Shows in Return Watch');
  });

  it('hides orders with unknown deadline', () => {
    const order = {
      order_status: 'active',
      deadline_confidence: 'unknown',
      return_by_date: null,
    };

    assert(lifecycle.shouldShowInReturnWatch(order) === false, 'Hidden with unknown deadline');
  });

  it('hides returned orders', () => {
    const today = utils.getToday();
    const futureDate = lifecycle.addDays(today, 10);
    const order = {
      order_status: 'returned',
      deadline_confidence: 'exact',
      return_by_date: futureDate,
    };

    assert(lifecycle.shouldShowInReturnWatch(order) === false, 'Hidden when returned');
  });

  it('hides expired orders', () => {
    const today = utils.getToday();
    const pastDate = lifecycle.addDays(today, -5);
    const order = {
      order_status: 'active',
      deadline_confidence: 'exact',
      return_by_date: pastDate,
    };

    assert(lifecycle.shouldShowInReturnWatch(order) === false, 'Hidden when expired');
  });
});

describe('P8: Lifecycle - shouldAlert', () => {
  it('alerts for exact deadline', () => {
    const today = utils.getToday();
    const futureDate = lifecycle.addDays(today, 5);
    const order = {
      order_status: 'active',
      deadline_confidence: 'exact',
      return_by_date: futureDate,
    };

    assert(lifecycle.shouldAlert(order) === true, 'Alerts for exact deadline');
  });

  it('alerts for estimated deadline with delivery_date', () => {
    const today = utils.getToday();
    const futureDate = lifecycle.addDays(today, 5);
    const order = {
      order_status: 'active',
      deadline_confidence: 'estimated',
      return_by_date: futureDate,
      delivery_date: '2024-01-15',
    };

    assert(lifecycle.shouldAlert(order) === true, 'Alerts for estimated with delivery');
  });

  it('does not alert for estimated without delivery_date', () => {
    const today = utils.getToday();
    const futureDate = lifecycle.addDays(today, 5);
    const order = {
      order_status: 'active',
      deadline_confidence: 'estimated',
      return_by_date: futureDate,
    };

    assert(lifecycle.shouldAlert(order) === false, 'No alert for estimated without delivery');
  });

  it('does not alert for unknown deadline', () => {
    const order = {
      order_status: 'active',
      deadline_confidence: 'unknown',
    };

    assert(lifecycle.shouldAlert(order) === false, 'No alert for unknown');
  });
});

describe('Utils - getToday', () => {
  it('returns ISO formatted date', () => {
    const today = utils.getToday();
    assert(/^\d{4}-\d{2}-\d{2}$/.test(today), 'Returns YYYY-MM-DD format');
  });

  it('returns current date', () => {
    const today = utils.getToday();
    const jsDate = new Date();
    const year = jsDate.getFullYear();
    assert(today.startsWith(String(year)), 'Year matches current year');
  });
});
