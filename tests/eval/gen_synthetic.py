"""
Synthetic email generator for the Reclaim extraction pipeline eval harness.

Template-based, deterministic, no LLM calls. Generates test emails across:
- Merchants (10 major retailers)
- Email types (order, shipping, delivery)
- Variations (with/without dates, order numbers, HTML)
- Edge cases (newsletters, subscriptions, cancellations)

Usage:
    python tests/eval/gen_synthetic.py              # Generate all cases
    python tests/eval/gen_synthetic.py --count      # Print count only
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
OUTPUT_FILE = FIXTURES_DIR / "synthetic-emails.json"


# ---------------------------------------------------------------------------
# Merchant definitions
# ---------------------------------------------------------------------------

MERCHANTS = {
    "amazon": {
        "domain": "amazon.com",
        "from": "auto-confirm@amazon.com",
        "return_window_days": 30,
        "anchor": "delivery",
        "order_prefix": "112-",
        "order_format": "112-{a}-{b}",
    },
    "target": {
        "domain": "target.com",
        "from": "no-reply@target.com",
        "return_window_days": 90,
        "anchor": "order",
        "order_prefix": "10",
        "order_format": "10{a}",
    },
    "walmart": {
        "domain": "walmart.com",
        "from": "help@walmart.com",
        "return_window_days": 90,
        "anchor": "delivery",
        "order_prefix": "200",
        "order_format": "200{a}-{b}",
    },
    "nike": {
        "domain": "nike.com",
        "from": "info@nike.com",
        "return_window_days": 60,
        "anchor": "delivery",
        "order_prefix": "C",
        "order_format": "C{a}",
    },
    "apple": {
        "domain": "apple.com",
        "from": "no_reply@email.apple.com",
        "return_window_days": 14,
        "anchor": "delivery",
        "order_prefix": "W",
        "order_format": "W{a}",
    },
    "zappos": {
        "domain": "zappos.com",
        "from": "cs@zappos.com",
        "return_window_days": 365,
        "anchor": "delivery",
        "order_prefix": "114-",
        "order_format": "114-{a}",
    },
    "nordstrom": {
        "domain": "nordstrom.com",
        "from": "nordstrom@e.nordstrom.com",
        "return_window_days": 40,
        "anchor": "order",
        "order_prefix": "3",
        "order_format": "3{a}",
    },
    "bestbuy": {
        "domain": "bestbuy.com",
        "from": "BestBuyInfo@emailinfo.bestbuy.com",
        "return_window_days": 15,
        "anchor": "order",
        "order_prefix": "BBY01-",
        "order_format": "BBY01-{a}",
    },
    "etsy": {
        "domain": "etsy.com",
        "from": "transaction@etsy.com",
        "return_window_days": 30,
        "anchor": "delivery",
        "order_prefix": "",
        "order_format": "{a}",
    },
    "allbirds": {
        "domain": "allbirds.com",
        "from": "hello@allbirds.com",
        "return_window_days": 30,
        "anchor": "delivery",
        "order_prefix": "AB-",
        "order_format": "AB-{a}",
    },
}


# ---------------------------------------------------------------------------
# Template functions
# ---------------------------------------------------------------------------

def _order_number(merchant_key: str, seq: int) -> str:
    m = MERCHANTS[merchant_key]
    a = str(1000000 + seq)[-7:]
    b = str(2000000 + seq)[-7:]
    return m["order_format"].format(a=a, b=b)


def _base_dates(offset_days: int = 5) -> dict:
    """Generate a set of plausible dates."""
    order = datetime(2026, 1, 15, 10, 30)
    ship = order + timedelta(days=2)
    delivery = order + timedelta(days=offset_days)
    return {
        "order": order,
        "ship": ship,
        "delivery": delivery,
        "order_str": order.strftime("%B %d, %Y"),
        "ship_str": ship.strftime("%B %d, %Y"),
        "delivery_str": delivery.strftime("%B %d, %Y"),
    }


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

def _order_confirmation(merchant_key: str, seq: int, *, include_order_num: bool = True,
                         item: str = "Wireless Bluetooth Headphones") -> dict:
    m = MERCHANTS[merchant_key]
    d = _base_dates()
    order_num = _order_number(merchant_key, seq) if include_order_num else None
    merchant_name = merchant_key.replace("bestbuy", "Best Buy").replace("allbirds", "Allbirds").title()

    order_line = f"Order #{order_num}\n" if order_num else ""
    body = (
        f"Thank you for your order!\n\n"
        f"{order_line}"
        f"Item: {item}\n"
        f"Order Date: {d['order_str']}\n"
        f"Estimated Delivery: {d['delivery_str']}\n"
        f"Total: $79.99\n\n"
        f"Thank you for shopping with {merchant_name}."
    )

    tags = [merchant_key, "order_confirmation"]
    if include_order_num:
        tags.append("with_order_number")
    else:
        tags.append("without_order_number")

    return {
        "id": f"syn-{merchant_key}-{seq:03d}",
        "from_address": m["from"],
        "subject": f"Your {merchant_name} order" + (f" #{order_num}" if order_num else ""),
        "body": body,
        "body_html": None,
        "expected": {
            "should_extract": True,
            "merchant_domain": m["domain"],
            "has_order_number": include_order_num,
            "order_number": order_num,
            "has_return_date": True,
            "return_window_days": m["return_window_days"],
            "confidence": "estimated",
            "must_not": [],
        },
        "tags": tags,
    }


def _shipping_notification(merchant_key: str, seq: int, *, item: str = "Wireless Bluetooth Headphones") -> dict:
    m = MERCHANTS[merchant_key]
    d = _base_dates()
    order_num = _order_number(merchant_key, seq)
    merchant_name = merchant_key.replace("bestbuy", "Best Buy").replace("allbirds", "Allbirds").title()

    body = (
        f"Great news! Your order has shipped.\n\n"
        f"Order #{order_num}\n"
        f"Item: {item}\n"
        f"Shipped: {d['ship_str']}\n"
        f"Estimated Delivery: {d['delivery_str']}\n"
        f"Tracking: 1Z999AA10123456784\n\n"
        f"Track your package at {merchant_name.lower()}.com/track"
    )

    return {
        "id": f"syn-{merchant_key}-{seq:03d}",
        "from_address": m["from"],
        "subject": f"Your {merchant_name} order has shipped",
        "body": body,
        "body_html": None,
        "expected": {
            "should_extract": True,
            "merchant_domain": m["domain"],
            "has_order_number": True,
            "order_number": order_num,
            "has_return_date": True,
            "return_window_days": m["return_window_days"],
            "confidence": "estimated",
            "must_not": [],
        },
        "tags": [merchant_key, "shipping_notification", "with_order_number"],
    }


def _delivery_confirmation(merchant_key: str, seq: int, *, item: str = "Wireless Bluetooth Headphones") -> dict:
    m = MERCHANTS[merchant_key]
    d = _base_dates()
    order_num = _order_number(merchant_key, seq)
    merchant_name = merchant_key.replace("bestbuy", "Best Buy").replace("allbirds", "Allbirds").title()

    body = (
        f"Your package has been delivered!\n\n"
        f"Order #{order_num}\n"
        f"Item: {item}\n"
        f"Delivered: {d['delivery_str']}\n\n"
        f"Thank you for shopping with {merchant_name}."
    )

    return {
        "id": f"syn-{merchant_key}-{seq:03d}",
        "from_address": m["from"],
        "subject": f"Your {merchant_name} order has been delivered",
        "body": body,
        "body_html": None,
        "expected": {
            "should_extract": True,
            "merchant_domain": m["domain"],
            "has_order_number": True,
            "order_number": order_num,
            "has_return_date": True,
            "return_window_days": m["return_window_days"],
            "confidence": "estimated",
            "must_not": [],
        },
        "tags": [merchant_key, "delivery_confirmation", "with_order_number"],
    }


def _order_with_explicit_return_date(merchant_key: str, seq: int) -> dict:
    m = MERCHANTS[merchant_key]
    d = _base_dates()
    order_num = _order_number(merchant_key, seq)
    merchant_name = merchant_key.replace("bestbuy", "Best Buy").replace("allbirds", "Allbirds").title()
    return_date = d["delivery"] + timedelta(days=m["return_window_days"])

    body = (
        f"Thank you for your order!\n\n"
        f"Order #{order_num}\n"
        f"Item: Running Shoes - Size 10\n"
        f"Order Date: {d['order_str']}\n"
        f"Total: $129.99\n\n"
        f"Return Policy: You may return this item by {return_date.strftime('%B %d, %Y')}.\n"
        f"To start a return, visit {merchant_name.lower()}.com/returns"
    )

    return {
        "id": f"syn-{merchant_key}-{seq:03d}",
        "from_address": m["from"],
        "subject": f"Your {merchant_name} order #{order_num}",
        "body": body,
        "body_html": None,
        "expected": {
            "should_extract": True,
            "merchant_domain": m["domain"],
            "has_order_number": True,
            "order_number": order_num,
            "has_return_date": True,
            "return_window_days": m["return_window_days"],
            "confidence": "exact",
            "must_not": [],
        },
        "tags": [merchant_key, "order_confirmation", "explicit_return_date", "with_order_number"],
    }


def _html_only_email(merchant_key: str, seq: int) -> dict:
    m = MERCHANTS[merchant_key]
    d = _base_dates()
    order_num = _order_number(merchant_key, seq)
    merchant_name = merchant_key.replace("bestbuy", "Best Buy").replace("allbirds", "Allbirds").title()

    body_html = (
        f"<html><body>"
        f"<h1>Order Confirmation</h1>"
        f"<p>Thank you for your order!</p>"
        f"<table>"
        f"<tr><td>Order</td><td>#{order_num}</td></tr>"
        f"<tr><td>Item</td><td>Cotton T-Shirt - Blue, Large</td></tr>"
        f"<tr><td>Date</td><td>{d['order_str']}</td></tr>"
        f"<tr><td>Total</td><td>$34.99</td></tr>"
        f"</table>"
        f"<p>Estimated delivery: {d['delivery_str']}</p>"
        f"</body></html>"
    )

    return {
        "id": f"syn-{merchant_key}-{seq:03d}",
        "from_address": m["from"],
        "subject": f"Your {merchant_name} order #{order_num}",
        "body": "",  # empty body — forces HTML conversion
        "body_html": body_html,
        "expected": {
            "should_extract": True,
            "merchant_domain": m["domain"],
            "has_order_number": True,
            "order_number": order_num,
            "has_return_date": True,
            "return_window_days": m["return_window_days"],
            "confidence": "estimated",
            "must_not": [],
        },
        "tags": [merchant_key, "html_only", "order_confirmation", "with_order_number"],
    }


def _multi_item_email(merchant_key: str, seq: int) -> dict:
    m = MERCHANTS[merchant_key]
    d = _base_dates()
    order_num = _order_number(merchant_key, seq)
    merchant_name = merchant_key.replace("bestbuy", "Best Buy").replace("allbirds", "Allbirds").title()

    body = (
        f"Thank you for your order!\n\n"
        f"Order #{order_num}\n\n"
        f"Items:\n"
        f"  1. Wireless Mouse - Black ($29.99)\n"
        f"  2. USB-C Hub Adapter ($49.99)\n"
        f"  3. Laptop Stand - Silver ($39.99)\n\n"
        f"Order Date: {d['order_str']}\n"
        f"Estimated Delivery: {d['delivery_str']}\n"
        f"Subtotal: $119.97\n"
        f"Tax: $9.60\n"
        f"Total: $129.57\n\n"
        f"Thank you for shopping with {merchant_name}."
    )

    return {
        "id": f"syn-{merchant_key}-{seq:03d}",
        "from_address": m["from"],
        "subject": f"Your {merchant_name} order #{order_num} - 3 items",
        "body": body,
        "body_html": None,
        "expected": {
            "should_extract": True,
            "merchant_domain": m["domain"],
            "has_order_number": True,
            "order_number": order_num,
            "has_return_date": True,
            "return_window_days": m["return_window_days"],
            "confidence": "estimated",
            "must_not": [],
        },
        "tags": [merchant_key, "order_confirmation", "multi_item", "with_order_number"],
    }


# ---------------------------------------------------------------------------
# Edge cases (non-purchase, subscriptions, cancellations)
# ---------------------------------------------------------------------------

def _newsletter_email(domain: str, seq: int) -> dict:
    return {
        "id": f"syn-edge-newsletter-{seq:03d}",
        "from_address": f"deals@{domain}",
        "subject": "This week's deals you don't want to miss!",
        "body": (
            "SALE! Up to 50% off selected items.\n\n"
            "Shop now at our biggest sale of the year.\n"
            "Free shipping on orders over $50.\n\n"
            "Unsubscribe | View in browser"
        ),
        "body_html": None,
        "expected": {
            "should_extract": False,
            "merchant_domain": domain,
            "has_order_number": False,
            "order_number": None,
            "has_return_date": False,
            "return_window_days": None,
            "confidence": None,
            "must_not": [],
        },
        "tags": ["edge_case", "newsletter", "should_reject"],
    }


def _marketing_email(seq: int) -> dict:
    return {
        "id": f"syn-edge-marketing-{seq:03d}",
        "from_address": "hello@shopify.com",
        "subject": "Grow your business with Shopify",
        "body": (
            "Start your free trial today.\n\n"
            "Join millions of entrepreneurs who trust Shopify.\n"
            "No credit card required.\n\n"
            "Start Free Trial"
        ),
        "body_html": None,
        "expected": {
            "should_extract": False,
            "merchant_domain": "shopify.com",
            "has_order_number": False,
            "order_number": None,
            "has_return_date": False,
            "return_window_days": None,
            "confidence": None,
            "must_not": [],
        },
        "tags": ["edge_case", "marketing", "should_reject"],
    }


def _subscription_email(seq: int) -> dict:
    return {
        "id": f"syn-edge-subscription-{seq:03d}",
        "from_address": "no-reply@netflix.com",
        "subject": "Your Netflix payment receipt",
        "body": (
            "Payment Confirmation\n\n"
            "Amount: $15.49\n"
            "Plan: Standard\n"
            "Billing Date: January 15, 2026\n"
            "Next Billing Date: February 15, 2026\n\n"
            "Manage your subscription at netflix.com/account"
        ),
        "body_html": None,
        "expected": {
            "should_extract": False,
            "merchant_domain": "netflix.com",
            "has_order_number": False,
            "order_number": None,
            "has_return_date": False,
            "return_window_days": None,
            "confidence": None,
            "must_not": [],
        },
        "tags": ["edge_case", "subscription", "non_returnable", "should_reject"],
    }


def _digital_purchase_email(seq: int) -> dict:
    return {
        "id": f"syn-edge-digital-{seq:03d}",
        "from_address": "noreply@steampowered.com",
        "subject": "Thank you for your purchase!",
        "body": (
            "Thank you for your purchase on Steam!\n\n"
            "Game: Cyberpunk 2077\n"
            "Price: $59.99\n"
            "Date: January 15, 2026\n\n"
            "Download now from your Steam library."
        ),
        "body_html": None,
        "expected": {
            "should_extract": False,
            "merchant_domain": "steampowered.com",
            "has_order_number": False,
            "order_number": None,
            "has_return_date": False,
            "return_window_days": None,
            "confidence": None,
            "must_not": [],
        },
        "tags": ["edge_case", "digital", "non_returnable", "should_reject"],
    }


def _cancellation_email(seq: int) -> dict:
    order_num = "112-1234567-7654321"
    return {
        "id": f"syn-edge-cancellation-{seq:03d}",
        "from_address": "auto-confirm@amazon.com",
        "subject": f"Your order #{order_num} has been cancelled",
        "body": (
            f"Your order has been cancelled.\n\n"
            f"Order #{order_num}\n"
            f"Item: Wireless Bluetooth Headphones\n\n"
            f"Your order was cancelled as requested. "
            f"If you were charged, a refund will be issued within 3-5 business days.\n"
        ),
        "body_html": None,
        "expected": {
            "should_extract": False,
            "merchant_domain": "amazon.com",
            "has_order_number": True,
            "order_number": order_num,
            "has_return_date": False,
            "return_window_days": None,
            "confidence": None,
            "must_not": [],
        },
        "tags": ["edge_case", "cancellation", "should_reject"],
    }


def _ride_receipt_email(seq: int) -> dict:
    return {
        "id": f"syn-edge-ride-{seq:03d}",
        "from_address": "no-reply@uber.com",
        "subject": "Your trip receipt from Uber",
        "body": (
            "Thanks for riding with Uber\n\n"
            "Trip: Downtown to Airport\n"
            "Date: January 15, 2026\n"
            "Total: $32.45\n"
            "Payment: Visa ending in 4242\n"
        ),
        "body_html": None,
        "expected": {
            "should_extract": False,
            "merchant_domain": "uber.com",
            "has_order_number": False,
            "order_number": None,
            "has_return_date": False,
            "return_window_days": None,
            "confidence": None,
            "must_not": [],
        },
        "tags": ["edge_case", "service", "non_returnable", "should_reject"],
    }


def _food_delivery_email(seq: int) -> dict:
    return {
        "id": f"syn-edge-food-{seq:03d}",
        "from_address": "no-reply@doordash.com",
        "subject": "Your DoorDash order is confirmed",
        "body": (
            "Your order from Chipotle is confirmed!\n\n"
            "Items:\n"
            "  Burrito Bowl ($11.50)\n"
            "  Chips and Guac ($4.25)\n\n"
            "Total: $15.75\n"
            "Estimated Delivery: 30-40 minutes\n"
        ),
        "body_html": None,
        "expected": {
            "should_extract": False,
            "merchant_domain": "doordash.com",
            "has_order_number": False,
            "order_number": None,
            "has_return_date": False,
            "return_window_days": None,
            "confidence": None,
            "must_not": [],
        },
        "tags": ["edge_case", "food_delivery", "non_returnable", "should_reject"],
    }


def _no_order_number_no_item(merchant_key: str, seq: int) -> dict:
    """Email that passes filter but has too little detail for a useful card."""
    m = MERCHANTS[merchant_key]
    merchant_name = merchant_key.replace("bestbuy", "Best Buy").replace("allbirds", "Allbirds").title()

    body = (
        f"Thanks for your order!\n\n"
        f"Your order has been placed. We'll send tracking info once it ships.\n\n"
        f"Thank you for shopping with {merchant_name}."
    )

    return {
        "id": f"syn-{merchant_key}-{seq:03d}",
        "from_address": m["from"],
        "subject": f"Your {merchant_name} order has been placed",
        "body": body,
        "body_html": None,
        "expected": {
            "should_extract": False,
            "merchant_domain": m["domain"],
            "has_order_number": False,
            "order_number": None,
            "has_return_date": False,
            "return_window_days": None,
            "confidence": None,
            "must_not": [],
        },
        "tags": [merchant_key, "edge_case", "empty_card", "should_reject"],
    }


def _international_merchant(seq: int) -> dict:
    return {
        "id": f"syn-edge-international-{seq:03d}",
        "from_address": "order@asos.com",
        "subject": "Your ASOS order #987654321 has been dispatched",
        "body": (
            "Your order has been dispatched!\n\n"
            "Order #987654321\n"
            "Item: Oversized Denim Jacket - Size M\n"
            "Dispatched: January 17, 2026\n"
            "Estimated Delivery: January 24, 2026\n"
            "Total: $89.00\n\n"
            "Free returns within 28 days of delivery."
        ),
        "body_html": None,
        "expected": {
            "should_extract": True,
            "merchant_domain": "asos.com",
            "has_order_number": True,
            "order_number": "987654321",
            "has_return_date": True,
            "return_window_days": 30,
            "confidence": "estimated",
            "must_not": [],
        },
        "tags": ["edge_case", "international", "with_order_number"],
    }


# ---------------------------------------------------------------------------
# Case generation
# ---------------------------------------------------------------------------

def generate_cases() -> list[dict]:
    """Generate all synthetic email cases."""
    cases = []
    seq = 1

    # --- Standard merchant emails (3 types x 10 merchants = 30) ---
    items_by_merchant = {
        "amazon": "Wireless Bluetooth Headphones",
        "target": "KitchenAid Stand Mixer",
        "walmart": "Samsung 55\" 4K TV",
        "nike": "Air Max 90 Running Shoes",
        "apple": "AirPods Pro (2nd gen)",
        "zappos": "New Balance 990v5 Sneakers",
        "nordstrom": "Cashmere Sweater - Navy",
        "bestbuy": "Sony WH-1000XM5 Headphones",
        "etsy": "Handmade Ceramic Vase",
        "allbirds": "Tree Runners - Natural White",
    }

    for mk in MERCHANTS:
        item = items_by_merchant[mk]
        cases.append(_order_confirmation(mk, seq, item=item))
        seq += 1
        cases.append(_shipping_notification(mk, seq, item=item))
        seq += 1
        cases.append(_delivery_confirmation(mk, seq, item=item))
        seq += 1

    # --- Variations ---

    # Order without order number (3 merchants)
    for mk in ["amazon", "target", "nike"]:
        cases.append(_order_confirmation(mk, seq, include_order_num=False, item=items_by_merchant[mk]))
        seq += 1

    # Explicit return date (3 merchants)
    for mk in ["amazon", "zappos", "nordstrom"]:
        cases.append(_order_with_explicit_return_date(mk, seq))
        seq += 1

    # HTML-only body (2 merchants)
    for mk in ["bestbuy", "walmart"]:
        cases.append(_html_only_email(mk, seq))
        seq += 1

    # Multi-item orders (2 merchants)
    for mk in ["amazon", "target"]:
        cases.append(_multi_item_email(mk, seq))
        seq += 1

    # --- Edge cases ---
    cases.append(_newsletter_email("amazon.com", seq)); seq += 1
    cases.append(_newsletter_email("target.com", seq)); seq += 1
    cases.append(_marketing_email(seq)); seq += 1
    cases.append(_subscription_email(seq)); seq += 1
    cases.append(_digital_purchase_email(seq)); seq += 1
    cases.append(_cancellation_email(seq)); seq += 1
    cases.append(_ride_receipt_email(seq)); seq += 1
    cases.append(_food_delivery_email(seq)); seq += 1
    cases.append(_international_merchant(seq)); seq += 1

    # Empty card edge cases (2 merchants)
    for mk in ["amazon", "target"]:
        cases.append(_no_order_number_no_item(mk, seq))
        seq += 1

    return cases


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic email test cases")
    parser.add_argument("--count", action="store_true", help="Print case count only")
    args = parser.parse_args()

    cases = generate_cases()

    if args.count:
        print(f"{len(cases)} cases")
        return

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(cases, indent=2, default=str))
    print(f"Generated {len(cases)} cases -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
