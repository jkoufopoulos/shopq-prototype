"""
Synthetic email generator for the Reclaim extraction pipeline eval harness.

Adapted from pulse-sms eval approach: template-based, deterministic, no LLM calls.
Generates realistic test emails across:
- Merchants (10 major retailers + unknown domains)
- Email types (order, shipping, delivery, return confirmations)
- Variations (with/without dates, order numbers, HTML-heavy, minimal)
- Edge cases (newsletters, subscriptions, password resets, gift cards, grocery,
  review requests, digital purchases, cancellations)

Each case includes an `expected` block for expectation evals and `tags` for filtering.

Usage:
    python tests/eval/gen_synthetic.py              # Generate all cases
    python tests/eval/gen_synthetic.py --count      # Print count only
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
OUTPUT_FILE = FIXTURES_DIR / "synthetic-emails.json"


# ---------------------------------------------------------------------------
# Merchant definitions — domains, from addresses, policies
# ---------------------------------------------------------------------------

MERCHANTS = {
    "amazon": {
        "domain": "amazon.com",
        "from": "auto-confirm@amazon.com",
        "ship_from": "shipment-tracking@amazon.com",
        "name": "Amazon.com",
        "return_window_days": 30,
        "order_format": "112-{a}-{b}",
    },
    "target": {
        "domain": "target.com",
        "from": "no-reply@target.com",
        "ship_from": "no-reply@target.com",
        "name": "Target",
        "return_window_days": 90,
        "order_format": "10{a}",
    },
    "walmart": {
        "domain": "walmart.com",
        "from": "help@walmart.com",
        "ship_from": "help@walmart.com",
        "name": "Walmart",
        "return_window_days": 90,
        "order_format": "200{a}-{b}",
    },
    "nike": {
        "domain": "nike.com",
        "from": "info@nike.com",
        "ship_from": "info@nike.com",
        "name": "Nike",
        "return_window_days": 60,
        "order_format": "C{a}",
    },
    "apple": {
        "domain": "apple.com",
        "from": "no_reply@email.apple.com",
        "ship_from": "no_reply@email.apple.com",
        "name": "Apple",
        "return_window_days": 14,
        "order_format": "W{a}",
    },
    "zappos": {
        "domain": "zappos.com",
        "from": "cs@zappos.com",
        "ship_from": "cs@zappos.com",
        "name": "Zappos",
        "return_window_days": 365,
        "order_format": "114-{a}",
    },
    "nordstrom": {
        "domain": "nordstrom.com",
        "from": "nordstrom@e.nordstrom.com",
        "ship_from": "nordstrom@e.nordstrom.com",
        "name": "Nordstrom",
        "return_window_days": 45,
        "order_format": "3{a}",
    },
    "bestbuy": {
        "domain": "bestbuy.com",
        "from": "BestBuyInfo@emailinfo.bestbuy.com",
        "ship_from": "BestBuyInfo@emailinfo.bestbuy.com",
        "name": "Best Buy",
        "return_window_days": 15,
        "order_format": "BBY01-{a}",
    },
    "etsy": {
        "domain": "etsy.com",
        "from": "transaction@etsy.com",
        "ship_from": "transaction@etsy.com",
        "name": "Etsy",
        "return_window_days": 30,
        "order_format": "{a}",
    },
    "allbirds": {
        "domain": "allbirds.com",
        "from": "hello@allbirds.com",
        "ship_from": "hello@allbirds.com",
        "name": "Allbirds",
        "return_window_days": 30,
        "order_format": "AB-{a}",
    },
    "gap": {
        "domain": "gap.com",
        "from": "orders@gap.com",
        "ship_from": "orders@gap.com",
        "name": "Gap",
        "return_window_days": 30,
        "order_format": "1NRV{a}",
    },
    "oldnavy": {
        "domain": "oldnavy.com",
        "from": "orders@oldnavy.com",
        "ship_from": "orders@oldnavy.com",
        "name": "Old Navy",
        "return_window_days": 30,
        "order_format": "1NRV{a}",
    },
    "jcrew": {
        "domain": "jcrew.com",
        "from": "jcrew@order.jcrew.com",
        "ship_from": "jcrew@order.jcrew.com",
        "name": "J.Crew",
        "return_window_days": 30,
        "order_format": "{a}",
    },
    "athleta": {
        "domain": "athleta.com",
        "from": "orders@athleta.com",
        "ship_from": "orders@athleta.com",
        "name": "Athleta",
        "return_window_days": 60,
        "order_format": "1NRV{a}",
    },
    "uniqlo": {
        "domain": "uniqlo.com",
        "from": "info@mail.uniqlo.com",
        "ship_from": "info@mail.uniqlo.com",
        "name": "UNIQLO",
        "return_window_days": 30,
        "order_format": "UQ{a}",
    },
    "zara": {
        "domain": "zara.com",
        "from": "info@e.zara.com",
        "ship_from": "info@e.zara.com",
        "name": "Zara",
        "return_window_days": 30,
        "order_format": "{a}",
    },
    "hm": {
        "domain": "hm.com",
        "from": "no-reply@email.hm.com",
        "ship_from": "no-reply@email.hm.com",
        "name": "H&M",
        "return_window_days": 30,
        "order_format": "{a}",
    },
    "adidas": {
        "domain": "adidas.com",
        "from": "confirm@adidas.com",
        "ship_from": "confirm@adidas.com",
        "name": "adidas",
        "return_window_days": 30,
        "order_format": "AD{a}",
    },
    "ikea": {
        "domain": "ikea.com",
        "from": "no-reply@order.ikea.com",
        "ship_from": "no-reply@order.ikea.com",
        "name": "IKEA",
        "return_window_days": 365,
        "order_format": "{a}",
    },
    "wayfair": {
        "domain": "wayfair.com",
        "from": "orders@wayfair.com",
        "ship_from": "orders@wayfair.com",
        "name": "Wayfair",
        "return_window_days": 30,
        "order_format": "{a}",
    },
    "costco": {
        "domain": "costco.com",
        "from": "costco@online.costco.com",
        "ship_from": "costco@online.costco.com",
        "name": "Costco",
        "return_window_days": 90,
        "order_format": "{a}",
    },
}

# Items that are realistic per merchant
ITEMS = {
    "amazon": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones, Black",
    "target": "KitchenAid Artisan Series 5-Qt Stand Mixer - Empire Red",
    "walmart": "Samsung 55\" Class 4K UHD Smart LED TV (UN55AU8000)",
    "nike": "Nike Air Max 90 - Men's - White/Black - Size 10.5",
    "apple": "AirPods Pro (2nd generation) with MagSafe Charging Case",
    "zappos": "New Balance Fresh Foam 990v5 - Grey/Castlerock - Size 11 D",
    "nordstrom": "Vince Cashmere Crewneck Sweater - Navy - Size L",
    "bestbuy": "LG C3 65\" 4K OLED evo Smart TV - OLED65C3PUA",
    "etsy": "Handmade Ceramic Pour-Over Coffee Dripper - Speckled White",
    "allbirds": "Men's Tree Runners - Natural White/Natural White - Size 10",
    "gap": "Relaxed Taper GapFlex Jeans with Washwell - Dark Wash - 32x32",
    "oldnavy": "PowerSoft Cropped Tank Top - Active - Black - XS",
    "jcrew": "Ludlow Slim-Fit Suit Jacket in Italian Wool - Navy - 40R",
    "athleta": "Salutation Stash Pocket II Tight - Black - M",
    "uniqlo": "Ultra Light Down Jacket - Navy - M",
    "zara": "Oversize Biker Jacket - Black - M",
    "hm": "Relaxed Fit Cotton T-shirt (3-pack) - White - M",
    "adidas": "Ultraboost Light Running Shoes - Core Black - Size 10",
    "ikea": "KALLAX Shelf Unit, 4x4 - White",
    "wayfair": "Mercer41 Velvet Sofa - Navy Blue",
    "costco": "KitchenAid Professional 5 Plus Stand Mixer - Silver",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seq_id(prefix: str, seq: int) -> str:
    return f"syn-{prefix}-{seq:03d}"


def _order_number(merchant_key: str, seq: int) -> str:
    fmt = MERCHANTS[merchant_key]["order_format"]
    a = str(1000000 + seq)[-7:]
    b = str(2000000 + seq)[-7:]
    return fmt.format(a=a, b=b)


def _dates(order_offset: int = 0) -> dict:
    """Generate plausible dates. offset shifts the base order date."""
    order = datetime(2026, 1, 15 + order_offset, 10, 30)
    ship = order + timedelta(days=2)
    delivery = order + timedelta(days=5)
    return {
        "order": order,
        "ship": ship,
        "delivery": delivery,
        "order_str": order.strftime("%B %d, %Y"),
        "order_short": order.strftime("%m/%d/%Y"),
        "ship_str": ship.strftime("%B %d, %Y"),
        "delivery_str": delivery.strftime("%B %d, %Y"),
        "delivery_short": delivery.strftime("%m/%d/%y"),
    }


def _expect_extract(domain: str, order_num: str | None = None, *,
                     confidence: str = "estimated",
                     return_days: int | None = None,
                     must_not: list[str] | None = None) -> dict:
    return {
        "should_extract": True,
        "merchant_domain": domain,
        "has_order_number": order_num is not None,
        "order_number": order_num,
        "has_return_date": True,
        "return_window_days": return_days,
        "confidence": confidence,
        "must_not": must_not or [],
    }


def _expect_reject(domain: str = "", *, must_not: list[str] | None = None) -> dict:
    return {
        "should_extract": False,
        "merchant_domain": domain,
        "has_order_number": False,
        "order_number": None,
        "has_return_date": False,
        "return_window_days": None,
        "confidence": None,
        "must_not": must_not or [],
    }


# ---------------------------------------------------------------------------
# Realistic email footers (most real emails have these)
# ---------------------------------------------------------------------------

AMAZON_FOOTER = (
    "\n\n---\n"
    "If you were not expecting this order, or if you believe an unauthorized "
    "person has accessed your account, you can go to Your Orders in Your Account "
    "to view, edit, or cancel orders.\n\n"
    "This email was sent from a notification-only address that cannot accept "
    "incoming email. Please do not reply to this message.\n\n"
    "Amazon.com, Inc. | 410 Terry Ave N, Seattle, WA 98109\n"
    "1-888-280-4331 | Conditions of Use | Privacy Notice\n"
)

TARGET_FOOTER = (
    "\n\n---\n"
    "Target Corporation | 1000 Nicollet Mall, Minneapolis, MN 55403\n"
    "Manage your communication preferences | Unsubscribe\n"
    "Privacy Policy | CA Privacy Rights | Terms & Conditions\n"
)

GENERIC_FOOTER = (
    "\n\n---\n"
    "If you have questions about your order, please contact customer service.\n"
    "Manage email preferences | Unsubscribe\n"
)


# ---------------------------------------------------------------------------
# Template: Amazon (most common merchant — test thoroughly)
# ---------------------------------------------------------------------------

def amazon_order_realistic(seq: int) -> dict:
    """Realistic Amazon order confirmation with full boilerplate."""
    d = _dates()
    order_num = _order_number("amazon", seq)
    item = ITEMS["amazon"]

    body = (
        f"Hello,\n\n"
        f"Thank you for your order. We'll send a confirmation when your item ships.\n\n"
        f"Order Confirmed\n"
        f"Order# {order_num}\n\n"
        f"Arriving {d['delivery_str']}\n\n"
        f"{item}\n"
        f"Qty: 1\n"
        f"$348.00\n\n"
        f"Shipping Address:\n"
        f"John D.\n"
        f"New York, NY\n\n"
        f"Order Total: $348.00\n"
        f"Payment: Visa ending in 4242"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("amz-order", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": f"Your Amazon.com order of {item[:40]}... and target delivery date",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("amazon.com", order_num, return_days=30),
        "tags": ["amazon", "order_confirmation", "with_order_number", "realistic"],
    }


def amazon_shipped_realistic(seq: int) -> dict:
    """Amazon shipping notification — different from/subject pattern."""
    d = _dates()
    order_num = _order_number("amazon", seq)
    item = ITEMS["amazon"]

    body = (
        f"Hello,\n\n"
        f"Your package is on the way.\n\n"
        f"Track your package:\n"
        f"https://www.amazon.com/gp/css/shipment-tracking/ref=pe_385040_121528400_TE_SIMP_typ?ie=UTF8\n\n"
        f"{item}\n\n"
        f"Shipped with USPS Tracking\n"
        f"Tracking ID: 9400111899223033005282\n\n"
        f"Arriving {d['delivery_str']}\n\n"
        f"Order #{order_num}"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("amz-ship", seq),
        "from_address": "shipment-tracking@amazon.com",
        "subject": f"Your Amazon.com order #{order_num} has shipped",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("amazon.com", order_num, return_days=30),
        "tags": ["amazon", "shipping_notification", "with_order_number", "realistic"],
    }


def amazon_delivered_realistic(seq: int) -> dict:
    """Amazon delivery confirmation."""
    d = _dates()
    order_num = _order_number("amazon", seq)
    item = ITEMS["amazon"]

    body = (
        f"Hello,\n\n"
        f"Your package was delivered.\n\n"
        f"Delivered {d['delivery_str']}\n"
        f"Your package was left near the front door.\n\n"
        f"{item}\n\n"
        f"Order #{order_num}\n\n"
        f"How was your delivery experience? Rate your delivery"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("amz-deliv", seq),
        "from_address": "shipment-tracking@amazon.com",
        "subject": f"Delivered: Your Amazon.com order #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("amazon.com", order_num, return_days=30),
        "tags": ["amazon", "delivery_confirmation", "with_order_number", "realistic"],
    }


def amazon_multi_item(seq: int) -> dict:
    """Amazon order with multiple items (common case)."""
    d = _dates()
    order_num = _order_number("amazon", seq)

    body = (
        f"Hello,\n\n"
        f"Thank you for your order. We'll send a confirmation when your items ship.\n\n"
        f"Order# {order_num}\n\n"
        f"Arriving {d['delivery_str']}\n\n"
        f"Anker USB C Charger, 65W (2 pack)\n"
        f"Qty: 1\n"
        f"$23.99\n\n"
        f"Logitech MX Master 3S Wireless Mouse - Graphite\n"
        f"Qty: 1\n"
        f"$89.99\n\n"
        f"Rain-X Latitude Water Repellency 2-in-1 Wiper Blades, 24\" and 18\"\n"
        f"Qty: 1\n"
        f"$47.98\n\n"
        f"Order Total: $161.96"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("amz-multi", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": f"Your Amazon.com order of Anker USB C Charger... and 2 more items",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("amazon.com", order_num, return_days=30),
        "tags": ["amazon", "order_confirmation", "multi_item", "with_order_number", "realistic"],
    }


def amazon_no_order_number(seq: int) -> dict:
    """Amazon order where the order number doesn't appear in body."""
    d = _dates()

    body = (
        f"Hi there,\n\n"
        f"Your order is confirmed!\n\n"
        f"Sony WH-1000XM5 Wireless Headphones\n"
        f"Arriving {d['delivery_str']}\n\n"
        f"Total: $348.00"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("amz-nonum", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": "Your Amazon.com order has been confirmed",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("amazon.com", confidence="estimated", return_days=30),
        "tags": ["amazon", "order_confirmation", "without_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Target (different format from Amazon)
# ---------------------------------------------------------------------------

def target_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("target", seq)
    item = ITEMS["target"]

    body = (
        f"Thanks for your Target.com order!\n\n"
        f"Order number: {order_num}\n"
        f"Placed on {d['order_str']}\n\n"
        f"Shipping to store\n"
        f"Estimated arrival: {d['delivery_str']}\n\n"
        f"1x {item}\n"
        f"$349.99\n\n"
        f"Subtotal: $349.99\n"
        f"Estimated tax: $31.50\n"
        f"Order total: $381.49\n\n"
        f"Need to make changes? You can cancel this order within 1 hour of placing it."
        + TARGET_FOOTER
    )

    return {
        "id": _seq_id("tgt-order", seq),
        "from_address": "no-reply@target.com",
        "subject": f"Thanks for your order, #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("target.com", order_num, return_days=90),
        "tags": ["target", "order_confirmation", "with_order_number", "realistic"],
    }


def target_shipped(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("target", seq)

    body = (
        f"Great news — your order is on the way!\n\n"
        f"Order number: {order_num}\n\n"
        f"Your items\n"
        f"KitchenAid Artisan Series 5-Qt Stand Mixer - Empire Red\n"
        f"Shipped via UPS\n"
        f"Tracking: 1Z12345E0205271688\n\n"
        f"Estimated delivery: {d['delivery_str']}"
        + TARGET_FOOTER
    )

    return {
        "id": _seq_id("tgt-ship", seq),
        "from_address": "no-reply@target.com",
        "subject": f"Your Target.com order #{order_num} has shipped!",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("target.com", order_num, return_days=90),
        "tags": ["target", "shipping_notification", "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Best Buy (HTML-heavy — body text is often almost empty)
# ---------------------------------------------------------------------------

def bestbuy_html_order(seq: int) -> dict:
    """Best Buy sends mostly HTML — plain text body is just a link."""
    d = _dates()
    order_num = _order_number("bestbuy", seq)
    item = ITEMS["bestbuy"]

    body_html = (
        "<html><body style='font-family:Arial,sans-serif;'>"
        "<div style='max-width:600px;margin:0 auto;'>"
        "<div style='background:#0046be;padding:20px;color:white;text-align:center;'>"
        "<h1 style='margin:0;'>Best Buy</h1></div>"
        f"<div style='padding:20px;'>"
        f"<h2>Thanks for your order!</h2>"
        f"<p>Order Number: <strong>{order_num}</strong></p>"
        f"<p>Ordered: {d['order_str']}</p>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<tr style='border-bottom:1px solid #eee;'>"
        f"<td style='padding:10px;'>"
        f"<strong>{item}</strong><br>"
        f"Qty: 1<br>"
        f"$1,296.99</td></tr></table>"
        f"<p><strong>Estimated Delivery:</strong> {d['delivery_str']}</p>"
        f"<p style='margin-top:20px;'>"
        f"<a href='https://www.bestbuy.com/orders/{order_num}' "
        f"style='background:#0046be;color:white;padding:10px 20px;text-decoration:none;'>"
        f"Track Your Order</a></p>"
        f"</div>"
        "<div style='padding:20px;font-size:11px;color:#666;'>"
        "Best Buy Co., Inc. | 7601 Penn Ave S, Richfield, MN 55423<br>"
        "Contact Us | Returns &amp; Exchanges | Unsubscribe"
        "</div></div></body></html>"
    )

    return {
        "id": _seq_id("bby-html", seq),
        "from_address": "BestBuyInfo@emailinfo.bestbuy.com",
        "subject": f"Order Confirmation - #{order_num}",
        # Best Buy body is often just "View as a Web page" link
        "body": "Having trouble viewing this email? View as a Web page: https://emailinfo.bestbuy.com/...",
        "body_html": body_html,
        "expected": _expect_extract("bestbuy.com", order_num, return_days=15),
        "tags": ["bestbuy", "html_only", "order_confirmation", "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Nike (direct-to-consumer brand style)
# ---------------------------------------------------------------------------

def nike_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("nike", seq)
    item = ITEMS["nike"]

    body = (
        f"WE'VE GOT YOUR ORDER.\n\n"
        f"Hi there,\n\n"
        f"We've received your order and are getting it ready.\n\n"
        f"ORDER NUMBER: {order_num}\n"
        f"ORDER DATE: {d['order_short']}\n\n"
        f"{item}\n"
        f"$130.00\n\n"
        f"ESTIMATED DELIVERY\n"
        f"{d['delivery_str']}\n\n"
        f"SHIPPING TO\n"
        f"John D.\n"
        f"123 Main St, New York, NY 10001\n\n"
        f"ORDER TOTAL: $138.45\n\n"
        f"Need help? Visit nike.com/help or call 1-800-344-6453"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("nike-order", seq),
        "from_address": "info@nike.com",
        "subject": f"We've Got Your Order {order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("nike.com", order_num, return_days=60),
        "tags": ["nike", "order_confirmation", "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Nordstrom (upscale, different tone)
# ---------------------------------------------------------------------------

def nordstrom_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("nordstrom", seq)
    item = ITEMS["nordstrom"]

    body = (
        f"Thank you for your order.\n\n"
        f"Order #{order_num}\n"
        f"Date: {d['order_str']}\n\n"
        f"{item}\n"
        f"$198.00\n\n"
        f"Estimated arrival: {d['delivery_str']}\n\n"
        f"Free shipping and free returns, always.\n\n"
        f"Questions? Contact us anytime at 1.888.282.6060 or nordstrom.com/contact."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("nord-order", seq),
        "from_address": "nordstrom@e.nordstrom.com",
        "subject": f"We got your order #{order_num}!",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("nordstrom.com", order_num, return_days=45),
        "tags": ["nordstrom", "order_confirmation", "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Etsy (marketplace with seller info)
# ---------------------------------------------------------------------------

def etsy_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("etsy", seq)
    item = ITEMS["etsy"]

    body = (
        f"You made a purchase from CeramicStudioNY!\n\n"
        f"Order #{order_num}\n\n"
        f"1x {item}\n"
        f"$45.00\n"
        f"Shipping: $6.99\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"This order is sold by CeramicStudioNY. "
        f"If you need help, you can contact the seller directly.\n\n"
        f"View your order: https://www.etsy.com/your/purchases/{order_num}"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("etsy-order", seq),
        "from_address": "transaction@etsy.com",
        "subject": f"You made a purchase from CeramicStudioNY",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("etsy.com", order_num, return_days=30),
        "tags": ["etsy", "order_confirmation", "with_order_number", "marketplace", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Apple (terse, premium)
# ---------------------------------------------------------------------------

def apple_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("apple", seq)
    item = ITEMS["apple"]

    body = (
        f"Your order has been placed.\n\n"
        f"Order {order_num}\n"
        f"Placed {d['order_str']}\n\n"
        f"{item}\n"
        f"$249.00\n\n"
        f"Delivers: {d['delivery_str']}\n"
        f"Ships to: John D.\n\n"
        f"View or manage your order:\n"
        f"https://store.apple.com/xc/track/{order_num}\n\n"
        f"Apple Online Store | 1-800-MY-APPLE"
    )

    return {
        "id": _seq_id("apple-order", seq),
        "from_address": "no_reply@email.apple.com",
        "subject": f"Your order {order_num} has been placed.",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("apple.com", order_num, return_days=14),
        "tags": ["apple", "order_confirmation", "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Zappos (365-day return window, friendly tone)
# ---------------------------------------------------------------------------

def zappos_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("zappos", seq)
    item = ITEMS["zappos"]

    body = (
        f"Woo-hoo! Your order is confirmed!\n\n"
        f"Order Number: {order_num}\n\n"
        f"{item}\n"
        f"$174.95\n\n"
        f"Estimated Delivery: {d['delivery_str']}\n\n"
        f"Remember — Zappos offers FREE 365-day returns!\n"
        f"Not the right fit? No worries, send it back anytime.\n\n"
        f"Customer Loyalty Team\n"
        f"1-800-927-7671"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("zappos-order", seq),
        "from_address": "cs@zappos.com",
        "subject": f"Zappos.com Order Confirmation #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("zappos.com", order_num, return_days=365),
        "tags": ["zappos", "order_confirmation", "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Walmart (different shipping format)
# ---------------------------------------------------------------------------

def walmart_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("walmart", seq)
    item = ITEMS["walmart"]

    body = (
        f"Your order's been placed.\n\n"
        f"Order # {order_num}\n\n"
        f"Shipping\n"
        f"Arriving by {d['delivery_str']}\n\n"
        f"1 x {item}\n"
        f"$397.99\n\n"
        f"Payment method: Visa ****4242\n"
        f"Order total: $432.67\n\n"
        f"Track your order at walmart.com/orders"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("wmt-order", seq),
        "from_address": "help@walmart.com",
        "subject": f"Your Walmart.com order confirmation #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("walmart.com", order_num, return_days=90),
        "tags": ["walmart", "order_confirmation", "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Template: Allbirds (DTC minimal)
# ---------------------------------------------------------------------------

def allbirds_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("allbirds", seq)
    item = ITEMS["allbirds"]

    body = (
        f"Order Confirmed\n\n"
        f"Hi there, thanks for your purchase!\n\n"
        f"Order {order_num}\n\n"
        f"{item}\n"
        f"$98.00\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"Made from natural materials, designed for everyday.\n\n"
        f"Questions? hello@allbirds.com"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("allb-order", seq),
        "from_address": "hello@allbirds.com",
        "subject": f"Order confirmed #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("allbirds.com", order_num, return_days=30),
        "tags": ["allbirds", "order_confirmation", "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Variation: Explicit return date in email body
# ---------------------------------------------------------------------------

def explicit_return_date(merchant_key: str, seq: int) -> dict:
    m = MERCHANTS[merchant_key]
    d = _dates()
    order_num = _order_number(merchant_key, seq)
    return_date = d["delivery"] + timedelta(days=m["return_window_days"])

    body = (
        f"Order Confirmation\n\n"
        f"Order #{order_num}\n\n"
        f"Nike Air Max 90 - Men's - White/Black - Size 10.5\n"
        f"$130.00\n\n"
        f"Order Date: {d['order_str']}\n"
        f"Estimated Delivery: {d['delivery_str']}\n\n"
        f"RETURN POLICY\n"
        f"You can return this item for a full refund by {return_date.strftime('%B %d, %Y')}.\n"
        f"Start a return at {m['name'].lower().replace(' ', '')}.com/returns\n\n"
        f"Order Total: $138.45"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id(f"{merchant_key[:4]}-explicit", seq),
        "from_address": m["from"],
        "subject": f"Your {m['name']} order #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract(
            m["domain"], order_num,
            confidence="exact",
            return_days=m["return_window_days"],
        ),
        "tags": [merchant_key, "order_confirmation", "explicit_return_date",
                 "with_order_number", "realistic"],
    }


# ---------------------------------------------------------------------------
# Variation: Unknown merchant (tests heuristic path in filter)
# ---------------------------------------------------------------------------

def unknown_merchant_order(seq: int) -> dict:
    """Order from a merchant NOT in the allowlist or blocklist."""
    d = _dates()

    body = (
        f"Order Confirmation\n\n"
        f"Thank you for your purchase from Outdoor Voices!\n\n"
        f"Order #OV-87654\n\n"
        f"1x CloudKnit Sweatpant - Charcoal - M\n"
        f"$98.00\n\n"
        f"Estimated delivery: {d['delivery_str']}\n"
        f"Order total: $106.82\n\n"
        f"Need help? support@outdoorvoices.com"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("unk-ov", seq),
        "from_address": "hello@outdoorvoices.com",
        "subject": "Your Outdoor Voices order is confirmed! #OV-87654",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("outdoorvoices.com", "OV-87654", return_days=30),
        "tags": ["unknown_merchant", "order_confirmation", "with_order_number",
                 "heuristic_path", "realistic"],
    }


def unknown_merchant_shopify(seq: int) -> dict:
    """Order from a Shopify-powered store (from shopifyemail.com)."""
    d = _dates()

    body = (
        f"Thank you for your purchase!\n\n"
        f"Order #1042\n\n"
        f"ILIA Super Serum Skin Tint SPF 40\n"
        f"Shade: Balos ST3\n"
        f"$48.00\n\n"
        f"Shipping address:\n"
        f"Jane D., New York, NY\n\n"
        f"Estimated delivery: {d['delivery_str']}\n"
        f"Subtotal: $48.00\n"
        f"Shipping: Free\n"
        f"Total: $51.12"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("unk-shopify", seq),
        "from_address": "no-reply@iliabeauty.com",
        "subject": "Order #1042 confirmed",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("iliabeauty.com", "1042", return_days=30),
        "tags": ["unknown_merchant", "shopify", "order_confirmation",
                 "with_order_number", "heuristic_path", "realistic"],
    }


# ---------------------------------------------------------------------------
# Variation: International merchant
# ---------------------------------------------------------------------------

def international_merchant(seq: int) -> dict:
    d = _dates()

    body = (
        f"Your order has been dispatched!\n\n"
        f"Order No: 987654321\n\n"
        f"ASOS DESIGN Oversized Denim Jacket\n"
        f"Colour: Blue\n"
        f"Size: M\n"
        f"$89.00\n\n"
        f"Dispatched: {d['ship_str']}\n"
        f"Estimated Delivery: {d['delivery_str']}\n\n"
        f"Returns\n"
        f"Free returns within 28 days of delivery.\n"
        f"Start a return at asos.com/returns\n\n"
        f"ASOS | Unsubscribe | Privacy Policy"
    )

    return {
        "id": _seq_id("intl-asos", seq),
        "from_address": "order@asos.com",
        "subject": "Your ASOS order no. 987654321 has been dispatched",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("asos.com", "987654321", return_days=30),
        "tags": ["international", "order_confirmation", "with_order_number",
                 "heuristic_path", "realistic"],
    }


# ---------------------------------------------------------------------------
# Edge case: Newsletter / promotional (should REJECT)
# ---------------------------------------------------------------------------

def newsletter_from_retailer(merchant_key: str, seq: int) -> dict:
    """Newsletter FROM a known retailer domain — tricky because domain passes filter."""
    m = MERCHANTS[merchant_key]

    body = (
        f"CLEARANCE EVENT\n"
        f"Up to 70% off thousands of items!\n\n"
        f"SHOP NOW >\n\n"
        f"Plus, get free shipping on orders over $35.\n"
        f"Hurry — sale ends Monday!\n\n"
        f"New arrivals | Women's | Men's | Home\n\n"
        f"{m['name']} | Unsubscribe | Privacy Policy | Terms"
    )

    return {
        "id": _seq_id(f"{merchant_key[:4]}-news", seq),
        "from_address": f"deals@{m['domain']}",
        "subject": f"CLEARANCE: Up to 70% off at {m['name']}!",
        "body": body,
        "body_html": None,
        "expected": _expect_reject(m["domain"]),
        "tags": [merchant_key, "edge_case", "newsletter", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Review / survey request from retailer (should REJECT)
# ---------------------------------------------------------------------------

def review_request(merchant_key: str, seq: int) -> dict:
    """Post-purchase review request — NOT an order email."""
    m = MERCHANTS[merchant_key]

    body = (
        f"How did we do?\n\n"
        f"Tell us about your recent purchase. "
        f"Your feedback helps us improve.\n\n"
        f"Rate your experience:\n"
        f"https://{m['domain']}/review?ref=email\n\n"
        f"Thank you for being a {m['name']} customer."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id(f"{merchant_key[:4]}-review", seq),
        "from_address": m["from"],
        "subject": f"How was your recent {m['name']} purchase?",
        "body": body,
        "body_html": None,
        "expected": _expect_reject(m["domain"]),
        "tags": [merchant_key, "edge_case", "review_request", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Password reset from retailer (tricky false positive)
# ---------------------------------------------------------------------------

def password_reset_from_retailer(seq: int) -> dict:
    """Password reset from amazon.com — domain matches allowlist but not a purchase."""
    body = (
        "Hello,\n\n"
        "We received a request to reset the password for your Amazon account.\n\n"
        "Click the link below to reset your password:\n"
        "https://www.amazon.com/ap/forgotpassword?arb=abc123\n\n"
        "If you didn't request this change, you can ignore this email.\n"
        "Your password won't be changed until you click the link above.\n\n"
        "Amazon.com Customer Service"
    )

    return {
        "id": _seq_id("edge-pwreset", seq),
        "from_address": "account-update@amazon.com",
        "subject": "Reset your Amazon.com password",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "password_reset", "false_positive_risk", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Gift card purchase (digital, non-returnable)
# ---------------------------------------------------------------------------

def gift_card_purchase(seq: int) -> dict:
    body = (
        "Hello,\n\n"
        "Thank you for purchasing an Amazon.com Gift Card!\n\n"
        "Gift Card Amount: $50.00\n"
        "Delivery Method: Email\n"
        "Recipient: jane@example.com\n\n"
        "The gift card has been delivered to the recipient's email address.\n\n"
        "Order #112-9876543-1234567"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-giftcard", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": "Your Amazon.com Gift Card order",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "gift_card", "non_returnable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Subscription / digital service (blocklisted domains)
# ---------------------------------------------------------------------------

def subscription_netflix(seq: int) -> dict:
    body = (
        "Payment Confirmation\n\n"
        "Hi John,\n\n"
        "Thanks for your payment of $15.49.\n\n"
        "Plan: Standard\n"
        "Billing period: Jan 15, 2026 - Feb 15, 2026\n"
        "Payment method: Visa ending in 4242\n\n"
        "Manage your account at netflix.com/account"
    )

    return {
        "id": _seq_id("edge-netflix", seq),
        "from_address": "info@mailer.netflix.com",
        "subject": "Your Netflix payment receipt",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("netflix.com"),
        "tags": ["edge_case", "subscription", "blocklisted", "non_returnable", "should_reject"],
    }


def subscription_spotify(seq: int) -> dict:
    body = (
        "Your receipt from Spotify\n\n"
        "Spotify Premium\n"
        "Individual Plan\n"
        "Amount: $10.99\n"
        "Date: January 15, 2026\n"
        "Payment method: PayPal\n\n"
        "View your account | Get help"
    )

    return {
        "id": _seq_id("edge-spotify", seq),
        "from_address": "no-reply@spotify.com",
        "subject": "Your Spotify receipt",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("spotify.com"),
        "tags": ["edge_case", "subscription", "blocklisted", "non_returnable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Digital purchase (Steam — blocklisted)
# ---------------------------------------------------------------------------

def digital_purchase_steam(seq: int) -> dict:
    body = (
        "Thank you for your Steam purchase!\n\n"
        "Cyberpunk 2077\n"
        "CDPROJEKTRED\n"
        "$59.99\n\n"
        "Date of purchase: Jan 15, 2026\n"
        "Payment method: Visa ending in 4242\n\n"
        "This game has been added to your library.\n"
        "Download and play from the Steam client."
    )

    return {
        "id": _seq_id("edge-steam", seq),
        "from_address": "noreply@steampowered.com",
        "subject": "Thank you for your purchase!",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("steampowered.com"),
        "tags": ["edge_case", "digital", "blocklisted", "non_returnable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Ride receipt (blocklisted)
# ---------------------------------------------------------------------------

def ride_receipt_uber(seq: int) -> dict:
    body = (
        "Thanks for riding, John\n\n"
        "Jan 15, 2026\n\n"
        "Trip fare\n"
        "Distance: 8.3 mi\n"
        "Time: 22 min\n\n"
        "Base fare: $3.50\n"
        "Distance: $12.80\n"
        "Time: $5.40\n"
        "Booking fee: $3.08\n"
        "Tip: $4.00\n\n"
        "Total: $28.78\n"
        "Visa ****4242\n\n"
        "Rate your driver: 5 stars | 4 stars | 3 stars"
    )

    return {
        "id": _seq_id("edge-uber", seq),
        "from_address": "no-reply@uber.com",
        "subject": "Your Tuesday evening trip with Uber",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("uber.com"),
        "tags": ["edge_case", "ride_receipt", "blocklisted", "non_returnable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Food delivery (blocklisted)
# ---------------------------------------------------------------------------

def food_delivery_doordash(seq: int) -> dict:
    body = (
        "Your DoorDash order is confirmed!\n\n"
        "From: Chipotle Mexican Grill\n\n"
        "1x Burrito Bowl - Chicken, Brown Rice, Black Beans\n"
        "  $11.50\n"
        "1x Chips & Guacamole\n"
        "  $4.25\n\n"
        "Subtotal: $15.75\n"
        "Delivery Fee: $3.99\n"
        "Service Fee: $2.36\n"
        "Tip: $3.00\n"
        "Total: $25.10\n\n"
        "Estimated arrival: 30-40 minutes"
    )

    return {
        "id": _seq_id("edge-doordash", seq),
        "from_address": "no-reply@doordash.com",
        "subject": "Your DoorDash order from Chipotle Mexican Grill",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("doordash.com"),
        "tags": ["edge_case", "food_delivery", "blocklisted", "non_returnable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Grocery / perishable order
# ---------------------------------------------------------------------------

def grocery_amazon_fresh(seq: int) -> dict:
    """Amazon Fresh grocery order — technically amazon.com but perishable."""
    body = (
        "Your Amazon Fresh order is on the way!\n\n"
        "Delivery window: Today, 2:00 PM - 4:00 PM\n\n"
        "Your items:\n"
        "- Organic Whole Milk, 1 gallon\n"
        "- Fresh Atlantic Salmon, 1 lb\n"
        "- Avocados, bag of 5\n"
        "- Dave's Killer Bread, Whole Wheat\n\n"
        "Subtotal: $32.47\n"
        "Delivery: Free\n"
        "Total: $34.63\n\n"
        "Your order was placed through Amazon Fresh."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-fresh", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": "Your Amazon Fresh order is on the way",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "grocery", "perishable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Cancellation email
# ---------------------------------------------------------------------------

def cancellation_email(seq: int) -> dict:
    order_num = "112-1234567-7654321"

    body = (
        f"Hello,\n\n"
        f"As you requested, we've cancelled item(s) in order #{order_num}.\n\n"
        f"Cancelled item:\n"
        f"Sony WH-1000XM5 Wireless Headphones\n"
        f"$348.00\n\n"
        f"Your payment method has not been charged for this item.\n\n"
        f"If you still need this item, you can place a new order at amazon.com."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-cancel", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": f"Your order #{order_num} has been cancelled",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "cancellation", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Refund / return confirmation (not a new purchase)
# ---------------------------------------------------------------------------

def refund_confirmation(seq: int) -> dict:
    body = (
        "Hello,\n\n"
        "We've processed your return for the following item:\n\n"
        "Sony WH-1000XM5 Wireless Headphones\n\n"
        "Refund amount: $348.00\n"
        "Refund method: Visa ending in 4242\n"
        "Expected: 3-5 business days\n\n"
        "Order #112-7654321-1234567\n\n"
        "Thank you for returning this item."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-refund", seq),
        "from_address": "returns@amazon.com",
        "subject": "Your Amazon.com refund of $348.00",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "refund", "return_confirmation", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Shipping carrier email (not from merchant)
# ---------------------------------------------------------------------------

def carrier_notification(seq: int) -> dict:
    """UPS delivery notification — not a purchase email."""
    body = (
        "UPS Delivery Notification\n\n"
        "A package is scheduled to be delivered today.\n\n"
        "Tracking Number: 1Z999AA10123456784\n"
        "Scheduled Delivery: January 20, 2026\n"
        "Ship To: JOHN D\n"
        "          NEW YORK, NY 10001\n\n"
        "Delivered By: End of Day\n\n"
        "Track your package at ups.com"
    )

    return {
        "id": _seq_id("edge-ups", seq),
        "from_address": "auto-notify@ups.com",
        "subject": "UPS Update: Package Scheduled for Delivery Today",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("ups.com"),
        "tags": ["edge_case", "carrier", "not_merchant", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Financial transaction (blocklisted)
# ---------------------------------------------------------------------------

def venmo_payment(seq: int) -> dict:
    body = (
        "You paid Mike S. $42.00\n\n"
        "Note: Dinner 🍕\n\n"
        "Date: January 15, 2026\n"
        "Payment method: Venmo balance\n\n"
        "View transaction in the Venmo app"
    )

    return {
        "id": _seq_id("edge-venmo", seq),
        "from_address": "venmo@venmo.com",
        "subject": "You paid Mike S. $42.00",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("venmo.com"),
        "tags": ["edge_case", "financial", "blocklisted", "non_returnable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Travel booking (blocklisted)
# ---------------------------------------------------------------------------

def travel_booking(seq: int) -> dict:
    body = (
        "Your booking is confirmed!\n\n"
        "Confirmation #: 84729163\n\n"
        "Hotel Americano\n"
        "518 W 27th St, New York, NY 10001\n\n"
        "Check-in: January 20, 2026\n"
        "Check-out: January 22, 2026\n"
        "2 nights | 1 room\n\n"
        "Total: $489.00\n\n"
        "Manage your booking at expedia.com"
    )

    return {
        "id": _seq_id("edge-travel", seq),
        "from_address": "bookings@expedia.com",
        "subject": "Booking confirmed - Hotel Americano, Jan 20-22",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("expedia.com"),
        "tags": ["edge_case", "travel", "blocklisted", "non_returnable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Empty / minimal body
# ---------------------------------------------------------------------------

def minimal_order_email(seq: int) -> dict:
    """Very minimal order email — tests extraction with sparse info."""
    body = (
        "Your order has been placed.\n\n"
        "Nike Air Max 90\n"
        "$130.00\n"
    )

    return {
        "id": _seq_id("edge-minimal", seq),
        "from_address": "info@nike.com",
        "subject": "Order confirmation",
        "body": body,
        "body_html": None,
        # May or may not extract depending on pipeline — being generous here
        "expected": _expect_extract("nike.com", confidence="estimated", return_days=60),
        "tags": ["nike", "edge_case", "minimal_body", "without_order_number"],
    }


def body_is_just_boilerplate(merchant_key: str, seq: int) -> dict:
    """Email where body has no real content — just an order confirmation subject."""
    m = MERCHANTS[merchant_key]

    body = (
        f"Thanks for your order!\n\n"
        f"Your order has been placed. We'll send you shipping updates soon.\n\n"
        f"Thank you for shopping with {m['name']}."
    )

    return {
        "id": _seq_id(f"{merchant_key[:4]}-boiler", seq),
        "from_address": m["from"],
        "subject": f"Your {m['name']} order has been placed",
        "body": body,
        "body_html": None,
        "expected": _expect_reject(m["domain"]),
        "tags": [merchant_key, "edge_case", "empty_card", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Marketing disguised as order email
# ---------------------------------------------------------------------------

def marketing_disguised_as_order(seq: int) -> dict:
    """Subject looks like an order, but body is marketing."""
    body = (
        "Your next order is waiting!\n\n"
        "Based on your recent purchases, we think you'll love:\n\n"
        "- Bose QuietComfort Ultra Headphones — $379.00\n"
        "- Apple Watch Series 9 — $399.00\n"
        "- Sonos Move 2 — $449.00\n\n"
        "Shop these personalized picks at amazon.com\n\n"
        "Unsubscribe | Privacy Policy"
    )

    return {
        "id": _seq_id("edge-mktg-order", seq),
        "from_address": "recommendations@amazon.com",
        "subject": "Your next order: Top picks for you",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "marketing_disguised", "false_positive_risk",
                 "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Price drop alert (from retailer domain)
# ---------------------------------------------------------------------------

def price_drop_alert(seq: int) -> dict:
    body = (
        "Price drop on your wishlist item!\n\n"
        "Sony WH-1000XM5 Wireless Headphones\n"
        "Was: $399.99\n"
        "Now: $298.00\n"
        "Save: $101.99 (26%)\n\n"
        "Add to cart >\n\n"
        "You're getting this email because this item is on your Amazon Wish List."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-pricedrop", seq),
        "from_address": "store-news@amazon.com",
        "subject": "Price drop! Sony WH-1000XM5 is now $298.00",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "price_alert", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Ticket / event purchase (non-returnable, blocklisted)
# ---------------------------------------------------------------------------

def event_ticket(seq: int) -> dict:
    body = (
        "You're going!\n\n"
        "Order #TM-91827364\n\n"
        "Radiohead\n"
        "Madison Square Garden\n"
        "March 15, 2026 - 8:00 PM\n\n"
        "Section: 204\n"
        "Row: E\n"
        "Seats: 7-8\n\n"
        "2 tickets x $125.00 = $250.00\n"
        "Service Fee: $48.50\n"
        "Total: $298.50\n\n"
        "Your tickets will be available in the Ticketmaster app."
    )

    return {
        "id": _seq_id("edge-ticket", seq),
        "from_address": "orders@ticketmaster.com",
        "subject": "Your tickets to Radiohead at MSG",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("ticketmaster.com"),
        "tags": ["edge_case", "event_ticket", "blocklisted", "non_returnable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Edge case: Shipment from Narvar (shipping service with merchant subdomain)
# ---------------------------------------------------------------------------

def narvar_shipping(seq: int) -> dict:
    """Narvar tracking email — from_address is narvar.com but email is about a Nike order."""
    d = _dates()

    body = (
        f"Your order is on the way!\n\n"
        f"Nike Air Max 90 - Men's - Size 10.5\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"Track your shipment:\n"
        f"https://nike.narvar.com/tracking/nike/usps?tracking=9400111899223\n\n"
        f"Order #C1000042"
    )

    return {
        "id": _seq_id("edge-narvar", seq),
        "from_address": "nike@ship.narvar.com",
        "subject": "Your Nike order is on the way",
        "body": body,
        "body_html": None,
        # Narvar emails are tricky — from_address is narvar.com, but the order
        # is from Nike. Pipeline may extract narvar/ship domain or nike.com.
        # Don't assert merchant_domain since it's legitimately ambiguous.
        "expected": _expect_extract("", "C1000042", return_days=60),
        "tags": ["nike", "edge_case", "narvar", "shipping_service",
                 "shipping_notification", "with_order_number"],
    }


# ===========================================================================
# BATCH 2: 50 additional cases for broader coverage
# ===========================================================================


# ---------------------------------------------------------------------------
# New Merchants from merchant_rules.yaml (EXTRACT)
# ---------------------------------------------------------------------------

def gap_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("gap", seq)
    item = ITEMS["gap"]

    body = (
        f"Thanks for shopping with us!\n\n"
        f"Order #{order_num}\n"
        f"Placed on {d['order_str']}\n\n"
        f"1x {item}\n"
        f"$69.95\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"Free returns within 30 days at any Gap, Old Navy, or Banana Republic store.\n\n"
        f"Gap Inc. | Manage your order at gap.com/orders"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("gap-order", seq),
        "from_address": "orders@gap.com",
        "subject": f"Your Gap order #{order_num} is confirmed",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("gap.com", order_num, return_days=30),
        "tags": ["gap", "order_confirmation", "with_order_number", "realistic"],
    }


def oldnavy_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("oldnavy", seq)
    item = ITEMS["oldnavy"]

    body = (
        f"Yay! Your order is confirmed.\n\n"
        f"Order Number: {order_num}\n\n"
        f"{item}\n"
        f"$16.99\n\n"
        f"Estimated delivery: {d['delivery_str']}\n"
        f"Shipping: FREE on orders $50+\n\n"
        f"Old Navy | Gap Inc."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("on-order", seq),
        "from_address": "orders@oldnavy.com",
        "subject": f"Order confirmed! #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("oldnavy.com", order_num, return_days=30),
        "tags": ["oldnavy", "order_confirmation", "with_order_number", "realistic"],
    }


def jcrew_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("jcrew", seq)
    item = ITEMS["jcrew"]

    body = (
        f"We've received your order.\n\n"
        f"Order {order_num}\n\n"
        f"1 x {item}\n"
        f"$398.00\n\n"
        f"Ships by: {d['ship_str']}\n"
        f"Estimated arrival: {d['delivery_str']}\n\n"
        f"Free returns within 30 days — in stores or by mail.\n\n"
        f"J.Crew Group, Inc. | 225 Liberty Street, New York, NY 10281"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("jcrew-order", seq),
        "from_address": "jcrew@order.jcrew.com",
        "subject": f"Your J.Crew order #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("jcrew.com", order_num, return_days=30),
        "tags": ["jcrew", "order_confirmation", "with_order_number", "realistic"],
    }


def athleta_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("athleta", seq)
    item = ITEMS["athleta"]

    body = (
        f"Your order is confirmed!\n\n"
        f"Order #{order_num}\n\n"
        f"1x {item}\n"
        f"$109.00\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"Give-It-A-Workout Guarantee:\n"
        f"Work out in it, wash it, and if it doesn't perform, return it "
        f"within 60 days — no questions asked.\n\n"
        f"Athleta | A Gap Inc. Brand"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("athl-order", seq),
        "from_address": "orders@athleta.com",
        "subject": f"Athleta order confirmed #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("athleta.com", order_num, return_days=60),
        "tags": ["athleta", "order_confirmation", "with_order_number", "realistic"],
    }


def uniqlo_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("uniqlo", seq)
    item = ITEMS["uniqlo"]

    body = (
        f"Thank you for your order.\n\n"
        f"Order Number: {order_num}\n\n"
        f"{item}\n"
        f"$79.90\n\n"
        f"Estimated Delivery: {d['delivery_str']}\n\n"
        f"You may return unworn items with tags within 30 days.\n\n"
        f"UNIQLO USA LLC"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("uq-order", seq),
        "from_address": "info@mail.uniqlo.com",
        "subject": f"UNIQLO: Order Confirmation #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("uniqlo.com", order_num, return_days=30),
        "tags": ["uniqlo", "order_confirmation", "with_order_number", "realistic"],
    }


def zara_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("zara", seq)
    item = ITEMS["zara"]

    body = (
        f"YOUR ORDER IS ON ITS WAY\n\n"
        f"Order: {order_num}\n\n"
        f"{item}\n"
        f"89.90 USD\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"You have 30 days from the shipping date to make a return.\n"
        f"In store or by mail — it's up to you.\n\n"
        f"ZARA | Industria de Diseño Textil, S.A."
    )

    return {
        "id": _seq_id("zara-order", seq),
        "from_address": "info@e.zara.com",
        "subject": f"Your order is on its way | {order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("zara.com", order_num, return_days=30),
        "tags": ["zara", "order_confirmation", "with_order_number", "realistic"],
    }


def hm_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("hm", seq)
    item = ITEMS["hm"]

    body = (
        f"Order Confirmation\n\n"
        f"Hi there,\n\n"
        f"Thank you for your order at hm.com.\n\n"
        f"Order number: {order_num}\n\n"
        f"{item}\n"
        f"$29.97\n\n"
        f"Delivery: Standard Shipping\n"
        f"Estimated delivery date: {d['delivery_str']}\n\n"
        f"H&M Hennes & Mauritz | hm.com/returns"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("hm-order", seq),
        "from_address": "no-reply@email.hm.com",
        "subject": f"H&M order confirmation #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("hm.com", order_num, return_days=30),
        "tags": ["hm", "order_confirmation", "with_order_number", "realistic"],
    }


def adidas_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("adidas", seq)
    item = ITEMS["adidas"]

    body = (
        f"ORDER CONFIRMED\n\n"
        f"Thanks for your order.\n\n"
        f"ORDER NUMBER: {order_num}\n"
        f"ORDER DATE: {d['order_short']}\n\n"
        f"{item}\n"
        f"$190.00\n\n"
        f"ESTIMATED DELIVERY: {d['delivery_str']}\n\n"
        f"FREE RETURNS\n"
        f"Not the right fit? Return for free within 30 days.\n\n"
        f"adidas America, Inc."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("adi-order", seq),
        "from_address": "confirm@adidas.com",
        "subject": f"adidas order confirmation #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("adidas.com", order_num, return_days=30),
        "tags": ["adidas", "order_confirmation", "with_order_number", "realistic"],
    }


def ikea_order(seq: int) -> dict:
    """IKEA — 365 day return policy, large furniture items."""
    d = _dates()
    order_num = _order_number("ikea", seq)
    item = ITEMS["ikea"]

    body = (
        f"Tack! Your order has been placed.\n\n"
        f"Order number: {order_num}\n\n"
        f"{item}\n"
        f"$179.00\n\n"
        f"Delivery method: Home Delivery\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"365-day return policy\n"
        f"Changed your mind? Return new, unopened products within 365 days "
        f"with your receipt for a full refund.\n\n"
        f"IKEA | Inter IKEA Systems B.V."
    )

    return {
        "id": _seq_id("ikea-order", seq),
        "from_address": "no-reply@order.ikea.com",
        "subject": f"IKEA order confirmation #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("ikea.com", order_num, return_days=365),
        "tags": ["ikea", "order_confirmation", "with_order_number", "realistic",
                 "large_item", "long_return_window"],
    }


def wayfair_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("wayfair", seq)
    item = ITEMS["wayfair"]

    body = (
        f"Your Wayfair order is confirmed!\n\n"
        f"Order Number: {order_num}\n\n"
        f"{item}\n"
        f"$629.99\n\n"
        f"Estimated Delivery: {d['delivery_str']}\n\n"
        f"Most items can be returned within 30 days of delivery.\n"
        f"Start a return at wayfair.com/myaccount\n\n"
        f"Wayfair LLC | 4 Copley Place, Boston, MA 02116"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("wfr-order", seq),
        "from_address": "orders@wayfair.com",
        "subject": f"Your Wayfair order #{order_num} is confirmed!",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("wayfair.com", order_num, return_days=30),
        "tags": ["wayfair", "order_confirmation", "with_order_number", "realistic",
                 "large_item"],
    }


def costco_order(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("costco", seq)
    item = ITEMS["costco"]

    body = (
        f"Thank you for your Costco.com order.\n\n"
        f"Order #: {order_num}\n"
        f"Date: {d['order_str']}\n\n"
        f"{item}\n"
        f"$379.99\n\n"
        f"Shipping Method: Standard\n"
        f"Estimated Delivery: {d['delivery_str']}\n\n"
        f"Costco's return policy: We guarantee your satisfaction on every "
        f"product we sell, with a full refund.\n\n"
        f"Costco Wholesale | costco.com"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("cost-order", seq),
        "from_address": "costco@online.costco.com",
        "subject": f"Costco.com Order Confirmation #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("costco.com", order_num, return_days=90),
        "tags": ["costco", "order_confirmation", "with_order_number", "realistic"],
    }


def ebay_purchase(seq: int) -> dict:
    """eBay marketplace purchase — from ebay.com domain."""
    d = _dates()

    body = (
        f"You bought an item!\n\n"
        f"Canon EOS R6 Mark II Mirrorless Camera Body\n"
        f"Item price: $2,299.00\n"
        f"Shipping: FREE\n\n"
        f"Seller: camera-outlet-deals (99.8% positive)\n\n"
        f"Order number: 12-34567-89012\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"eBay Buyer Protection covers your purchase.\n"
        f"If the item doesn't match the listing, you can return it."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("ebay-buy", seq),
        "from_address": "ebay@ebay.com",
        "subject": "You bought Canon EOS R6 Mark II Mirrorless Camera Body",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("ebay.com", "12-34567-89012", return_days=30),
        "tags": ["ebay", "marketplace", "order_confirmation", "with_order_number",
                 "heuristic_path", "realistic"],
    }


# ---------------------------------------------------------------------------
# More email types for existing merchants (EXTRACT)
# ---------------------------------------------------------------------------

def target_store_pickup(seq: int) -> dict:
    """Target BOPIS — Buy Online, Pick Up In Store."""
    d = _dates()
    order_num = _order_number("target", seq)

    body = (
        f"Your order is ready for pickup!\n\n"
        f"Order number: {order_num}\n\n"
        f"Pick up at:\n"
        f"Target - Brooklyn Junction\n"
        f"139 Flatbush Ave, Brooklyn, NY 11217\n\n"
        f"Items ready:\n"
        f"Dyson V8 Cordless Vacuum\n"
        f"$349.99\n\n"
        f"Please pick up by {d['delivery_str']}.\n"
        f"Bring a valid photo ID."
        + TARGET_FOOTER
    )

    return {
        "id": _seq_id("tgt-pickup", seq),
        "from_address": "no-reply@target.com",
        "subject": f"Your order #{order_num} is ready for pickup!",
        "body": body,
        "body_html": None,
        # Store pickup may get "unknown" confidence since there's no delivery date
        "expected": _expect_extract("target.com", order_num, confidence="unknown", return_days=90),
        "tags": ["target", "store_pickup", "bopis", "with_order_number", "realistic"],
    }


def nordstrom_shipped(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("nordstrom", seq)

    body = (
        f"Your order is on its way!\n\n"
        f"Order #{order_num}\n\n"
        f"Vince Cashmere Crewneck Sweater - Navy - Size L\n"
        f"$198.00\n\n"
        f"Shipped via UPS\n"
        f"Tracking: 1Z9999W99999999999\n\n"
        f"Estimated arrival: {d['delivery_str']}\n\n"
        f"Free shipping. Free returns. All the time."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("nord-ship", seq),
        "from_address": "nordstrom@e.nordstrom.com",
        "subject": f"Your Nordstrom.com order #{order_num} has shipped",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("nordstrom.com", order_num, return_days=45),
        "tags": ["nordstrom", "shipping_notification", "with_order_number", "realistic"],
    }


def walmart_delivered(seq: int) -> dict:
    d = _dates()
    order_num = _order_number("walmart", seq)

    body = (
        f"Your Walmart.com order has been delivered!\n\n"
        f"Order # {order_num}\n\n"
        f"Samsung 55\" Class 4K UHD Smart LED TV\n\n"
        f"Delivered on {d['delivery_str']}\n"
        f"Left at: Front Door\n\n"
        f"Not satisfied? Start a return at walmart.com/returns\n"
        f"Most items can be returned within 90 days."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("wmt-deliv", seq),
        "from_address": "help@walmart.com",
        "subject": f"Delivered: Your Walmart.com order #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("walmart.com", order_num, return_days=90),
        "tags": ["walmart", "delivery_confirmation", "with_order_number", "realistic"],
    }


def amazon_preorder(seq: int) -> dict:
    """Pre-order for a physical product — should still extract."""
    order_num = _order_number("amazon", seq)

    body = (
        f"Hello,\n\n"
        f"Thank you for pre-ordering with Amazon.\n\n"
        f"Pre-order Confirmed\n"
        f"Order# {order_num}\n\n"
        f"PlayStation 6 DualSense Wireless Controller - Volcanic Red\n"
        f"$74.99\n\n"
        f"Expected release date: March 15, 2026\n"
        f"We'll charge your payment method and ship when the item is released.\n"
        f"You can cancel your pre-order at any time before it ships."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("amz-preorder", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": f"Your Amazon.com pre-order of PlayStation 6...",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("amazon.com", order_num, return_days=30),
        "tags": ["amazon", "pre_order", "order_confirmation", "with_order_number"],
    }


def subscription_box_physical(seq: int) -> dict:
    """Stitch Fix — physical clothing subscription box."""
    d = _dates()

    body = (
        f"Your Fix is on the way!\n\n"
        f"Fix #87654\n\n"
        f"Your stylist picked 5 items for you:\n"
        f"1. Kut from the Kloth Diana Skinny Jean\n"
        f"2. Market & Spruce Corwin Textured Pullover\n"
        f"3. 41Hawthorn Breyson Polka Dot Blouse\n"
        f"4. Liverpool Kelsey Knit Trouser\n"
        f"5. Fate Danna V-Neck Sweater\n\n"
        f"Total if you keep all 5: $289.00 (25% styling discount)\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"Try everything on at home. Keep what you love, return the rest.\n"
        f"Returns are always free — just use the prepaid bag."
    )

    return {
        "id": _seq_id("stitchfix", seq),
        "from_address": "fix@stitchfix.com",
        "subject": "Your Fix is on the way!",
        "body": body,
        "body_html": None,
        # "Fix #87654" is unusual — pipeline may not recognize it as an order number
        "expected": _expect_extract("stitchfix.com", confidence="estimated", return_days=30),
        "tags": ["unknown_merchant", "subscription_box", "physical_items",
                 "order_confirmation", "heuristic_path"],
    }


# ---------------------------------------------------------------------------
# Non-purchase emails from known retail domains (should REJECT)
# ---------------------------------------------------------------------------

def amazon_security_alert(seq: int) -> dict:
    body = (
        "Hello,\n\n"
        "We noticed a new sign-in to your Amazon account.\n\n"
        "When: January 16, 2026, 3:42 PM EST\n"
        "Device: Chrome browser on Windows\n"
        "Near: New York, NY\n\n"
        "If this was you, you can disregard this message.\n"
        "If this WASN'T you, click here to secure your account:\n"
        "https://www.amazon.com/ap/signin\n\n"
        "Amazon.com Security"
    )

    return {
        "id": _seq_id("edge-amzsec", seq),
        "from_address": "account-update@amazon.com",
        "subject": "Amazon.com sign-in alert: new device detected",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "security_alert", "should_reject"],
    }


def target_circle_rewards(seq: int) -> dict:
    body = (
        "You've earned a reward!\n\n"
        "Congratulations — you've reached Target Circle Gold status!\n\n"
        "Your rewards:\n"
        "- 2% earnings on every purchase\n"
        "- Free same-day delivery on orders $35+\n"
        "- Exclusive offers just for you\n\n"
        "Start shopping: target.com\n\n"
        "Thanks for being a loyal Target shopper!"
        + TARGET_FOOTER
    )

    return {
        "id": _seq_id("edge-tgtcircle", seq),
        "from_address": "no-reply@target.com",
        "subject": "You earned a Target Circle reward!",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("target.com"),
        "tags": ["target", "edge_case", "loyalty_program", "should_reject"],
    }


def nike_membership_welcome(seq: int) -> dict:
    body = (
        "WELCOME TO NIKE MEMBERSHIP\n\n"
        "You're in. As a Nike Member, you get:\n\n"
        "- Free shipping on every order\n"
        "- Birthday rewards\n"
        "- Early access to new releases\n"
        "- Member-only products\n\n"
        "Download the Nike App to get started.\n\n"
        "JUST DO IT"
    )

    return {
        "id": _seq_id("edge-nikemem", seq),
        "from_address": "info@nike.com",
        "subject": "Welcome to Nike Membership",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("nike.com"),
        "tags": ["nike", "edge_case", "membership", "should_reject"],
    }


def amazon_shipping_delay(seq: int) -> dict:
    """Shipping delay — NOT a confirmation. References an order but is an update."""
    body = (
        "Hello,\n\n"
        "We're writing to let you know that your delivery is running behind schedule.\n\n"
        "Order #112-7777777-8888888\n\n"
        "Sony WH-1000XM5 Wireless Headphones\n\n"
        "Original delivery estimate: January 20, 2026\n"
        "New delivery estimate: January 25, 2026\n\n"
        "We're sorry for the inconvenience. You don't need to take any action — "
        "your order is still on its way.\n\n"
        "If you'd like to cancel, visit Your Orders."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-amzdelay", seq),
        "from_address": "shipment-tracking@amazon.com",
        "subject": "Update on your Amazon.com order #112-7777777-8888888",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "shipping_delay", "order_update", "should_reject"],
    }


def walmart_savings_alert(seq: int) -> dict:
    body = (
        "WEEKLY AD\n\n"
        "Great Savings This Week!\n\n"
        "Rollback: Samsung 65\" TV — Was $599.99, Now $449.99\n"
        "Rollback: Dyson V15 Vacuum — Was $749.99, Now $549.99\n"
        "New Low Price: KitchenAid Mixer — $299.99\n\n"
        "Shop these deals at walmart.com\n\n"
        "Valid through January 25, 2026"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("edge-wmtsave", seq),
        "from_address": "help@walmart.com",
        "subject": "This week's biggest savings at Walmart!",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("walmart.com"),
        "tags": ["walmart", "edge_case", "newsletter", "marketing", "should_reject"],
    }


def nordstrom_sale_email(seq: int) -> dict:
    body = (
        "NORDSTROM ANNIVERSARY SALE\n\n"
        "Early Access starts now!\n\n"
        "Up to 40% off new fall arrivals:\n"
        "- Cashmere sweaters from $89.90\n"
        "- Leather boots from $129.90\n"
        "- Designer handbags from $199.90\n\n"
        "Shop the sale: nordstrom.com/anniversary\n\n"
        "Prices go up August 6."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("edge-nordsale", seq),
        "from_address": "nordstrom@e.nordstrom.com",
        "subject": "Nordstrom Anniversary Sale: Early Access!",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("nordstrom.com"),
        "tags": ["nordstrom", "edge_case", "newsletter", "sale", "should_reject"],
    }


def amazon_return_reminder(seq: int) -> dict:
    """Return reminder — already-tracked order, NOT a new purchase."""
    body = (
        "Hello,\n\n"
        "Reminder: Your return window is closing soon.\n\n"
        "Order #112-5555555-6666666\n"
        "Sony WH-1000XM5 Wireless Headphones\n\n"
        "Return by: January 30, 2026\n\n"
        "If you'd like to return this item, start the process at:\n"
        "https://www.amazon.com/returns\n\n"
        "After the return window closes, this item will no longer be eligible for return."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-amzretrem", seq),
        "from_address": "returns@amazon.com",
        "subject": "Reminder: Return window closing for your order",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "return_reminder", "should_reject"],
    }


def amazon_wishlist_notification(seq: int) -> dict:
    body = (
        "Items on your Wish List are on sale!\n\n"
        "2 items on your list have price drops:\n\n"
        "Bose QuietComfort Ultra Headphones\n"
        "Was: $429.00 | Now: $329.00 | Save 23%\n\n"
        "Kindle Scribe (64 GB)\n"
        "Was: $389.99 | Now: $289.99 | Save 26%\n\n"
        "View your Wish List: amazon.com/wishlist\n\n"
        "Prices and availability are subject to change."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-amzwish", seq),
        "from_address": "store-news@amazon.com",
        "subject": "Price drops on 2 items in your Wish List",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "wishlist", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Grocery / perishable from allowed domains (should REJECT)
# ---------------------------------------------------------------------------

def hellofresh_meal_kit(seq: int) -> dict:
    body = (
        "Your HelloFresh box is on the way!\n\n"
        "Box #HF-98765\n\n"
        "This week's meals:\n"
        "- One-Pan Southwest Chicken\n"
        "- Firecracker Meatballs with Sesame Rice\n"
        "- Crispy Parmesan Chicken with Lemon Butter Pasta\n\n"
        "Delivering: Thursday, January 16, 2026\n"
        "Carrier: FedEx\n\n"
        "Keep refrigerated upon arrival.\n\n"
        "HelloFresh | Manage your subscription at hellofresh.com"
    )

    return {
        "id": _seq_id("edge-hfresh", seq),
        "from_address": "info@hellofresh.com",
        "subject": "Your HelloFresh box ships tomorrow!",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("hellofresh.com"),
        "tags": ["edge_case", "meal_kit", "perishable", "subscription", "should_reject"],
    }


def amazon_supplements(seq: int) -> dict:
    """Vitamins/supplements from amazon.com — perishable/consumable."""
    d = _dates()
    order_num = _order_number("amazon", seq)

    body = (
        f"Hello,\n\n"
        f"Thank you for your order.\n\n"
        f"Order# {order_num}\n\n"
        f"Garden of Life Raw Organic Protein Powder - Vanilla - 20 oz\n"
        f"Qty: 1\n"
        f"$32.99\n\n"
        f"Nature Made Multivitamin Gummies, 150 count\n"
        f"Qty: 1\n"
        f"$14.49\n\n"
        f"Arriving {d['delivery_str']}\n"
        f"Order Total: $47.48"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-amzsupp", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": f"Your Amazon.com order of Garden of Life...",
        "body": body,
        "body_html": None,
        # Classifier prompt says supplements/vitamins are perishable = not returnable
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "supplements", "perishable", "should_reject"],
    }


def whole_foods_order(seq: int) -> dict:
    body = (
        "Your Whole Foods Market order is confirmed!\n\n"
        "Delivery window: Today, 10:00 AM - 12:00 PM\n\n"
        "Order summary:\n"
        "- 365 Organic Baby Spinach, 5 oz\n"
        "- Wild-caught Sockeye Salmon, 1 lb\n"
        "- Organic Avocados, 4 ct\n"
        "- 365 Organic Whole Milk, half gallon\n"
        "- Siggi's Vanilla Yogurt, 5.3 oz (x3)\n\n"
        "Subtotal: $48.73\n"
        "Delivery: Free (Prime)\n"
        "Total: $52.15\n\n"
        "Whole Foods Market | An Amazon company"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-wfm", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": "Your Whole Foods Market order is on its way",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "grocery", "whole_foods", "perishable",
                 "should_reject"],
    }


def target_grocery(seq: int) -> dict:
    body = (
        "Your Target Same Day Delivery order is on the way!\n\n"
        "Order #1099887766\n\n"
        "Good & Gather Organic Bananas\n"
        "Good & Gather 2% Reduced Fat Milk, 1 gal\n"
        "Market Pantry Large White Eggs, 12 ct\n"
        "Good & Gather Sharp Cheddar Cheese, 8 oz\n"
        "Coca-Cola, 12-pack cans\n\n"
        "Delivery window: 4:00 PM - 5:00 PM\n"
        "Subtotal: $24.67\n"
        "Same Day Delivery fee: $9.99"
        + TARGET_FOOTER
    )

    return {
        "id": _seq_id("edge-tgtgroc", seq),
        "from_address": "no-reply@target.com",
        "subject": "Your Target grocery order is on the way!",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("target.com"),
        "tags": ["target", "edge_case", "grocery", "perishable", "should_reject"],
    }


def flowers_1800(seq: int) -> dict:
    body = (
        "Order Confirmation\n\n"
        "Thank you for your 1-800-Flowers order!\n\n"
        "Order #W123456789\n\n"
        "Abundant Rose Bouquet\n"
        "Deluxe (24 stems)\n"
        "$79.99\n\n"
        "Delivery Date: January 20, 2026\n"
        "Recipient: Jane Smith\n"
        "Message: Happy Birthday!\n\n"
        "1-800-Flowers.com, Inc."
    )

    return {
        "id": _seq_id("edge-flowers", seq),
        "from_address": "orders@1800flowers.com",
        "subject": "Your 1-800-Flowers order confirmation",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("1800flowers.com"),
        "tags": ["edge_case", "flowers", "perishable", "should_reject"],
    }


def instacart_grocery(seq: int) -> dict:
    body = (
        "Your Instacart order is being shopped!\n\n"
        "From: Trader Joe's\n\n"
        "Items:\n"
        "- Everything But The Bagel Seasoning\n"
        "- Mandarin Orange Chicken\n"
        "- Triple Ginger Snaps\n"
        "- Unexpected Cheddar Cheese\n\n"
        "Delivery window: 2:00 PM - 3:00 PM\n\n"
        "Your shopper is Sarah L.\n"
        "Tip: $5.00"
    )

    return {
        "id": _seq_id("edge-instacart", seq),
        "from_address": "no-reply@instacart.com",
        "subject": "Your Trader Joe's order is being shopped",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("instacart.com"),
        "tags": ["edge_case", "grocery", "blocklisted", "perishable", "should_reject"],
    }


def walmart_grocery(seq: int) -> dict:
    body = (
        "Your Walmart Grocery order is confirmed!\n\n"
        "Pickup: Today, 4:00 PM - 5:00 PM\n"
        "Store: Walmart Supercenter #1234\n\n"
        "Great Value Whole Milk, 1 gal — $3.36\n"
        "Bananas, bunch — $0.58\n"
        "Foster Farms Chicken Breast, 2 lb — $7.98\n"
        "Lay's Classic Potato Chips, 10 oz — $4.98\n"
        "Wonder Classic White Bread — $3.12\n\n"
        "Subtotal: $20.02\n\n"
        "We'll text you when your order is ready."
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("edge-wmtgroc", seq),
        "from_address": "help@walmart.com",
        "subject": "Your Walmart Grocery pickup order is confirmed",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("walmart.com"),
        "tags": ["walmart", "edge_case", "grocery", "perishable", "should_reject"],
    }


# ---------------------------------------------------------------------------
# More blocklisted domain rejections (REJECT)
# ---------------------------------------------------------------------------

def airbnb_booking(seq: int) -> dict:
    body = (
        "Reservation confirmed\n\n"
        "You're going to Brooklyn!\n\n"
        "Sunny Studio in Williamsburg\n"
        "Hosted by Maria\n\n"
        "Check-in: January 20, 2026 (3:00 PM)\n"
        "Check-out: January 23, 2026 (11:00 AM)\n"
        "3 nights\n\n"
        "Total: $487.50\n\n"
        "Confirmation code: HMKX9B7Z\n\n"
        "Message your host"
    )

    return {
        "id": _seq_id("edge-airbnb", seq),
        "from_address": "automated@airbnb.com",
        "subject": "Reservation confirmed - Sunny Studio in Williamsburg",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("airbnb.com"),
        "tags": ["edge_case", "travel", "blocklisted", "should_reject"],
    }


def starbucks_mobile_order(seq: int) -> dict:
    body = (
        "Your order is ready!\n\n"
        "Pick up at: Starbucks - 7th Ave & 23rd St\n\n"
        "1x Iced Caramel Macchiato (Grande)\n"
        "  Oat Milk, Extra Shot\n"
        "  $6.45\n\n"
        "1x Butter Croissant\n"
        "  $3.95\n\n"
        "Total: $10.40\n"
        "Paid with: Starbucks Card ****1234\n\n"
        "Earn Stars with every purchase!"
    )

    return {
        "id": _seq_id("edge-sbux", seq),
        "from_address": "starbucks@e.starbucks.com",
        "subject": "Your Starbucks order is ready for pickup",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("starbucks.com"),
        "tags": ["edge_case", "food", "blocklisted", "should_reject"],
    }


def adobe_subscription(seq: int) -> dict:
    body = (
        "Invoice for your Adobe subscription\n\n"
        "Adobe Creative Cloud - All Apps\n\n"
        "Billing period: Jan 15, 2026 — Feb 14, 2026\n"
        "Amount: $54.99\n"
        "Payment: Visa ending in 4242\n\n"
        "Manage your plan: account.adobe.com\n\n"
        "Adobe Inc. | 345 Park Avenue, San Jose, CA 95110"
    )

    return {
        "id": _seq_id("edge-adobe", seq),
        "from_address": "mail@mail.adobe.com",
        "subject": "Your Adobe invoice is ready",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("adobe.com"),
        "tags": ["edge_case", "subscription", "software", "should_reject"],
    }


def kickstarter_backed(seq: int) -> dict:
    body = (
        "You're a backer!\n\n"
        "You just backed: Minimal Titanium EDC Pen\n"
        "by Workshop Studios\n\n"
        "Pledge: $45.00 (Early Bird)\n"
        "Estimated Delivery: April 2026\n\n"
        "Reward: 1x Titanium Pen + Carrying Case\n\n"
        "This is a crowdfunded project. Rewards are not guaranteed.\n"
        "Kickstarter does not guarantee projects or investigate a "
        "creator's ability to complete their project."
    )

    return {
        "id": _seq_id("edge-kick", seq),
        "from_address": "no-reply@kickstarter.com",
        "subject": "You backed Minimal Titanium EDC Pen",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("kickstarter.com"),
        "tags": ["edge_case", "crowdfunding", "blocklisted", "should_reject"],
    }


def gofundme_donation(seq: int) -> dict:
    body = (
        "Thank you for your donation!\n\n"
        "You donated $25.00 to:\n"
        "Help the Johnson Family Rebuild After Fire\n\n"
        "Organized by: Mike Johnson\n"
        "Your donation brings the total to $12,450 of $20,000 goal.\n\n"
        "Share this fundraiser to help spread the word.\n\n"
        "Receipt #GFM-87654321\n"
        "Your donation may be tax-deductible."
    )

    return {
        "id": _seq_id("edge-gfm", seq),
        "from_address": "info@gofundme.com",
        "subject": "Thank you for your donation to Help the Johnson Family...",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("gofundme.com"),
        "tags": ["edge_case", "donation", "blocklisted", "should_reject"],
    }


def chipotle_order(seq: int) -> dict:
    body = (
        "Your Chipotle order is confirmed!\n\n"
        "Order #ABC123\n\n"
        "1x Chicken Burrito Bowl\n"
        "  White Rice, Black Beans, Fresh Tomato Salsa,\n"
        "  Sour Cream, Cheese, Guacamole\n"
        "  $11.75\n\n"
        "1x Chips & Guacamole\n"
        "  $4.70\n\n"
        "Subtotal: $16.45\n"
        "Tax: $1.48\n"
        "Total: $17.93\n\n"
        "Pickup at: Chipotle - Union Square"
    )

    return {
        "id": _seq_id("edge-chipotle", seq),
        "from_address": "no-reply@chipotle.com",
        "subject": "Your Chipotle order is confirmed",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("chipotle.com"),
        "tags": ["edge_case", "food", "blocklisted", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Tricky edge cases (REJECT)
# ---------------------------------------------------------------------------

def asurion_warranty(seq: int) -> dict:
    """Extended warranty — from a warranty service, not a physical product."""
    body = (
        "Your protection plan is confirmed.\n\n"
        "Asurion Complete Protect\n"
        "Covered device: iPhone 15 Pro Max\n\n"
        "Plan: $14.99/month\n"
        "Coverage: Accidental damage, loss, theft\n"
        "Deductible: $99\n\n"
        "File a claim at asurion.com/claims\n\n"
        "Terms and conditions apply."
    )

    return {
        "id": _seq_id("edge-asurion", seq),
        "from_address": "no-reply@asurion.com",
        "subject": "Your Asurion protection plan is active",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("asurion.com"),
        "tags": ["edge_case", "warranty", "service", "blocklisted", "should_reject"],
    }


def amazon_kindle_ebook(seq: int) -> dict:
    """Digital purchase from amazon.com — tricky because domain is allowed."""
    order_num = "D01-1234567-8901234"

    body = (
        f"Hello,\n\n"
        f"Thank you for your purchase.\n\n"
        f"Digital Order: {order_num}\n\n"
        f"Project Hail Mary: A Novel\n"
        f"by Andy Weir\n"
        f"Kindle Edition\n"
        f"$13.99\n\n"
        f"Your book is ready to read. Open the Kindle app or go to:\n"
        f"https://read.amazon.com\n\n"
        f"This is a digital item. It has been added to your Kindle library."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-kindle", seq),
        "from_address": "digital-no-reply@amazon.com",
        "subject": "Your Kindle purchase: Project Hail Mary",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "digital", "ebook", "should_reject"],
    }


def fedex_carrier(seq: int) -> dict:
    """FedEx delivery notification — carrier, not merchant."""
    body = (
        "FedEx Delivery Manager\n\n"
        "Your package is scheduled for delivery tomorrow.\n\n"
        "Tracking Number: 7489274892748927\n"
        "Status: In Transit\n"
        "Estimated Delivery: January 20, 2026 by end of day\n\n"
        "Ship To:\n"
        "JOHN D.\n"
        "NEW YORK, NY 10001\n\n"
        "Shipment Facts:\n"
        "Weight: 3.2 lbs\n"
        "Service: FedEx Home Delivery\n\n"
        "Customize your delivery at fedex.com/delivery-manager"
    )

    return {
        "id": _seq_id("edge-fedex", seq),
        "from_address": "TrackingUpdates@fedex.com",
        "subject": "FedEx: Your package is scheduled for delivery tomorrow",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("fedex.com"),
        "tags": ["edge_case", "carrier", "not_merchant", "should_reject"],
    }


def return_approved_email(seq: int) -> dict:
    """Return already approved — outgoing, not incoming product."""
    body = (
        "Hello,\n\n"
        "Your return has been approved!\n\n"
        "Order #112-3333333-4444444\n"
        "Item: Nike Air Max 90 - Men's - Size 10.5\n\n"
        "Return method: UPS Drop-off\n"
        "Return label: Print from Your Orders\n\n"
        "Please ship the item within 7 days.\n"
        "Your refund of $130.00 will be processed within 3-5 business days "
        "after we receive the item.\n\n"
        "Need help? Contact us at amazon.com/help"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-retappr", seq),
        "from_address": "returns@amazon.com",
        "subject": "Your return is approved — ship by January 25",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "return_approved", "should_reject"],
    }


def order_address_change(seq: int) -> dict:
    """Order modification email — NOT a new purchase."""
    body = (
        "Hello,\n\n"
        "Your shipping address has been updated.\n\n"
        "Order #112-9999999-0000000\n\n"
        "New shipping address:\n"
        "John D.\n"
        "456 Broadway, Apt 7B\n"
        "New York, NY 10013\n\n"
        "Estimated delivery: January 20, 2026\n\n"
        "If you didn't make this change, please contact us immediately."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-addrchg", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": "Address updated for your Amazon order #112-9999999-0000000",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "order_update", "address_change", "should_reject"],
    }


def amazon_prime_video(seq: int) -> dict:
    """Digital rental from Amazon — same domain, digital content."""
    body = (
        f"Thank you for renting with Prime Video.\n\n"
        f"Dune: Part Two (2024)\n"
        f"Rental: $5.99\n\n"
        f"You have 30 days to start watching and 48 hours to finish "
        f"once you start.\n\n"
        f"Watch now: primevideo.com\n\n"
        f"This is a digital rental. No physical item will be shipped."
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("edge-primevid", seq),
        "from_address": "digital-no-reply@amazon.com",
        "subject": "Your Prime Video rental: Dune: Part Two",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "digital", "video_rental", "should_reject"],
    }


def poshmark_purchase(seq: int) -> dict:
    """Poshmark — secondhand marketplace for clothing."""
    d = _dates()

    body = (
        f"Congratulations on your purchase!\n\n"
        f"Order #PM-5678901234\n\n"
        f"Lululemon Align High-Rise Pant 25\" - Black - Size 6\n"
        f"$48.00\n\n"
        f"Seller: @fashionista_nyc\n"
        f"Condition: Like New\n\n"
        f"Order Date: {d['order_str']}\n"
        f"The seller will ship your order soon.\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"Poshmark Buyer Protection: If the item isn't as described, "
        f"you can open a case after delivery."
    )

    return {
        "id": _seq_id("posh-buy", seq),
        "from_address": "support@poshmark.com",
        "subject": "You purchased Lululemon Align High-Rise Pant",
        "body": body,
        "body_html": None,
        # Poshmark has short return policy; pipeline uses default 30 days
        "expected": _expect_extract("poshmark.com", "PM-5678901234", return_days=30),
        "tags": ["poshmark", "marketplace", "secondhand", "order_confirmation",
                 "with_order_number", "heuristic_path", "realistic"],
    }


# ---------------------------------------------------------------------------
# 5 more targeted cases
# ---------------------------------------------------------------------------

def amazon_third_party_seller(seq: int) -> dict:
    """Amazon 3P seller — 'Sold by XYZ, Fulfilled by Amazon' pattern."""
    d = _dates()
    order_num = _order_number("amazon", seq)

    body = (
        f"Hello,\n\n"
        f"Thank you for your order.\n\n"
        f"Order# {order_num}\n\n"
        f"Anker 313 Charger (Ace, 45W) USB C Charger\n"
        f"Sold by: AnkerDirect\n"
        f"Fulfilled by Amazon\n"
        f"$15.99\n\n"
        f"Arriving {d['delivery_str']}\n\n"
        f"Order Total: $17.03"
        + AMAZON_FOOTER
    )

    return {
        "id": _seq_id("amz-3p", seq),
        "from_address": "auto-confirm@amazon.com",
        "subject": f"Your Amazon.com order #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("amazon.com", order_num, return_days=30),
        "tags": ["amazon", "third_party_seller", "order_confirmation",
                 "with_order_number", "realistic"],
    }


def back_market_refurbished(seq: int) -> dict:
    """Back Market — refurbished electronics marketplace."""
    d = _dates()

    body = (
        f"Your order is confirmed!\n\n"
        f"Order #BM-789012345\n\n"
        f"iPhone 14 Pro - 256GB - Space Black\n"
        f"Condition: Excellent — like new, no visible marks\n"
        f"Seller: TechRenew Pro\n"
        f"$699.00\n\n"
        f"1-year warranty included\n"
        f"30-day money-back guarantee\n\n"
        f"Estimated delivery: {d['delivery_str']}\n\n"
        f"Back Market | The best deals on refurbished tech"
    )

    return {
        "id": _seq_id("bkmkt-order", seq),
        "from_address": "no-reply@backmarket.com",
        "subject": "Order confirmed: iPhone 14 Pro",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("backmarket.com", "BM-789012345", return_days=30),
        "tags": ["backmarket", "refurbished", "marketplace", "order_confirmation",
                 "with_order_number", "heuristic_path", "realistic"],
    }


def usps_carrier(seq: int) -> dict:
    """USPS delivery notification — carrier, not merchant."""
    body = (
        "USPS Tracking Update\n\n"
        "Your package is arriving today!\n\n"
        "Tracking Number: 9400111899223033005282\n\n"
        "Status: Out for Delivery\n"
        "Expected Delivery: January 20, 2026\n\n"
        "Delivery Address:\n"
        "JOHN D\n"
        "NEW YORK, NY 10001\n\n"
        "Sign up for Informed Delivery at informeddelivery.usps.com"
    )

    return {
        "id": _seq_id("edge-usps", seq),
        "from_address": "USPSInformedDelivery@usps.gov",
        "subject": "USPS: Your package is arriving today",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("usps.gov"),
        "tags": ["edge_case", "carrier", "not_merchant", "should_reject"],
    }


def square_instore_receipt(seq: int) -> dict:
    """Digital receipt from Square POS — in-store, not online."""
    body = (
        "Receipt from Blue Bottle Coffee\n\n"
        "January 15, 2026 at 8:42 AM\n\n"
        "1x New Orleans Iced Coffee (Large)\n"
        "   $6.50\n"
        "1x Giant Step Espresso Blend (12oz bag)\n"
        "   $22.00\n\n"
        "Subtotal: $28.50\n"
        "Tax: $2.53\n"
        "Total: $31.03\n\n"
        "Visa ****4242\n\n"
        "Powered by Square\n"
        "View receipt: squareup.com/receipt/..."
    )

    return {
        "id": _seq_id("edge-square", seq),
        "from_address": "receipts@squareup.com",
        "subject": "Receipt from Blue Bottle Coffee",
        "body": body,
        "body_html": None,
        # In-store coffee/food receipt — not a returnable online purchase
        "expected": _expect_reject("squareup.com"),
        "tags": ["edge_case", "instore_receipt", "pos", "food", "should_reject"],
    }


def costco_electronics(seq: int) -> dict:
    """Costco electronics order — same 90-day window (Costco policy)."""
    d = _dates()
    order_num = _order_number("costco", seq)

    body = (
        f"Thank you for your Costco.com order.\n\n"
        f"Order #: {order_num}\n"
        f"Date: {d['order_str']}\n\n"
        f"Samsung 75\" Class QN85D Neo QLED 4K Smart TV\n"
        f"$1,599.99\n\n"
        f"Shipping: White Glove Delivery & Setup\n"
        f"Estimated Delivery: {d['delivery_str']}\n\n"
        f"Electronics have a 90-day return policy.\n"
        f"Costco.com | Member Services: 1-800-955-2292"
        + GENERIC_FOOTER
    )

    return {
        "id": _seq_id("cost-elec", seq),
        "from_address": "costco@online.costco.com",
        "subject": f"Costco.com Order Confirmation #{order_num}",
        "body": body,
        "body_html": None,
        "expected": _expect_extract("costco.com", order_num, return_days=90),
        "tags": ["costco", "order_confirmation", "electronics", "with_order_number",
                 "large_item", "realistic"],
    }


# ===========================================================================
# BATCH 3: Services, appointments, digital subscriptions, SaaS
# ===========================================================================


# ---------------------------------------------------------------------------
# Appointments & local services (should REJECT)
# ---------------------------------------------------------------------------

def barber_appointment(seq: int) -> dict:
    body = (
        "Appointment Confirmed\n\n"
        "Hi John,\n\n"
        "Your appointment is booked!\n\n"
        "Service: Men's Haircut + Beard Trim\n"
        "Barber: Tony V.\n"
        "Date: Saturday, January 18, 2026 at 2:00 PM\n"
        "Duration: 45 minutes\n\n"
        "Location:\n"
        "Blind Barber\n"
        "339 E 10th St, New York, NY 10009\n\n"
        "Price: $55.00 + tip\n\n"
        "Need to cancel or reschedule? Do so at least 4 hours in advance.\n"
        "Book again: blindbarber.com"
    )

    return {
        "id": _seq_id("edge-barber", seq),
        "from_address": "appointments@blindbarber.com",
        "subject": "Your haircut is booked — Saturday at 2:00 PM",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("blindbarber.com"),
        "tags": ["edge_case", "appointment", "service", "local_business", "should_reject"],
    }


def dentist_appointment(seq: int) -> dict:
    body = (
        "Appointment Reminder\n\n"
        "Hi John,\n\n"
        "This is a reminder for your upcoming dental appointment.\n\n"
        "Provider: Dr. Sarah Chen, DDS\n"
        "Date: Monday, January 20, 2026\n"
        "Time: 9:30 AM\n"
        "Service: Cleaning & Exam\n\n"
        "Location:\n"
        "Downtown Dental Associates\n"
        "123 Broadway, Suite 4F, New York, NY 10006\n\n"
        "Insurance: Aetna PPO\n"
        "Estimated copay: $25.00\n\n"
        "Please arrive 10 minutes early. Cancel 24 hours in advance "
        "to avoid a $50 cancellation fee."
    )

    return {
        "id": _seq_id("edge-dentist", seq),
        "from_address": "no-reply@downtowndental.com",
        "subject": "Reminder: Dental appointment Monday 9:30 AM",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("downtowndental.com"),
        "tags": ["edge_case", "appointment", "healthcare", "service", "should_reject"],
    }


def auto_repair_receipt(seq: int) -> dict:
    body = (
        "Service Complete — Invoice\n\n"
        "Thank you for choosing Midas!\n\n"
        "Invoice #: MID-2026-45678\n"
        "Date: January 16, 2026\n\n"
        "Vehicle: 2022 Honda Civic LX\n\n"
        "Services performed:\n"
        "- Full Synthetic Oil Change (0W-20) ............ $69.99\n"
        "- Tire Rotation ............................... $29.99\n"
        "- Brake Inspection (no charge) ................ $0.00\n"
        "- Multi-point Vehicle Inspection .............. $0.00\n\n"
        "Parts:\n"
        "- Oil Filter .................................. $12.99\n"
        "- 5 qt Mobil 1 Synthetic ...................... (incl.)\n\n"
        "Subtotal: $112.97\n"
        "Tax: $10.17\n"
        "Total: $123.14\n"
        "Paid: Visa ****4242\n\n"
        "Next service due: April 2026 or 5,000 miles"
    )

    return {
        "id": _seq_id("edge-autorepair", seq),
        "from_address": "service@midas.com",
        "subject": "Your Midas service receipt — Invoice MID-2026-45678",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("midas.com"),
        "tags": ["edge_case", "service", "auto_repair", "receipt", "should_reject"],
    }


def dog_grooming(seq: int) -> dict:
    body = (
        "Appointment Confirmed!\n\n"
        "PetSmart Grooming Salon\n\n"
        "Pet: Max (Golden Retriever)\n"
        "Service: Full Grooming Package\n"
        "Date: Saturday, January 18, 2026 at 10:00 AM\n"
        "Location: PetSmart - Union Square\n\n"
        "Includes: Bath, haircut, nail trim, ear cleaning, teeth brushing\n"
        "Price: $75.00\n\n"
        "Please bring Max in at least 10 minutes early.\n"
        "Drop-off window: 10:00 AM - 10:30 AM\n"
        "Estimated pickup: 1:00 PM"
    )

    return {
        "id": _seq_id("edge-groom", seq),
        "from_address": "no-reply@petsmart.com",
        "subject": "Grooming appointment confirmed for Max",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("petsmart.com"),
        "tags": ["edge_case", "appointment", "service", "pet", "should_reject"],
    }


def house_cleaning(seq: int) -> dict:
    body = (
        "Booking Confirmed\n\n"
        "Your cleaning is scheduled!\n\n"
        "Service: Standard Cleaning (2 bedrooms, 1 bathroom)\n"
        "Professional: Maria R. (4.9 stars, 312 cleans)\n"
        "Date: Thursday, January 16, 2026\n"
        "Time: 10:00 AM - 12:30 PM\n\n"
        "Total: $120.00\n"
        "Service fee: $18.00\n"
        "Tip (suggested): $24.00\n\n"
        "Special instructions: Please use products under the kitchen sink.\n\n"
        "Handy | Cancel up to 24 hours in advance for a full refund."
    )

    return {
        "id": _seq_id("edge-cleaning", seq),
        "from_address": "bookings@handy.com",
        "subject": "Your cleaning is booked for Thursday",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("handy.com"),
        "tags": ["edge_case", "appointment", "service", "home_service", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Digital subscriptions & AI/SaaS renewals (should REJECT)
# ---------------------------------------------------------------------------

def claude_pro_renewal(seq: int) -> dict:
    """Anthropic/Claude subscription — in the blocklist."""
    body = (
        "Your subscription has renewed\n\n"
        "Hi John,\n\n"
        "Your Claude Pro subscription has been renewed.\n\n"
        "Plan: Claude Pro\n"
        "Amount: $20.00/month\n"
        "Billing date: January 15, 2026\n"
        "Next billing date: February 15, 2026\n"
        "Payment method: Visa ending in 4242\n\n"
        "Manage your subscription at claude.ai/settings\n\n"
        "Anthropic, PBC | San Francisco, CA"
    )

    return {
        "id": _seq_id("edge-claude", seq),
        "from_address": "billing@anthropic.com",
        "subject": "Your Claude Pro subscription has renewed",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("anthropic.com"),
        "tags": ["edge_case", "subscription", "ai_saas", "blocklisted", "should_reject"],
    }


def chatgpt_plus_renewal(seq: int) -> dict:
    """OpenAI/ChatGPT subscription — in the blocklist."""
    body = (
        "Payment receipt\n\n"
        "OpenAI\n\n"
        "Thank you for your payment.\n\n"
        "ChatGPT Plus\n"
        "Amount: $20.00\n"
        "Date: January 15, 2026\n"
        "Payment method: Mastercard ending in 5678\n\n"
        "Your subscription will auto-renew on February 15, 2026.\n\n"
        "Manage subscription: chat.openai.com/settings"
    )

    return {
        "id": _seq_id("edge-chatgpt", seq),
        "from_address": "noreply@openai.com",
        "subject": "Receipt for your ChatGPT Plus subscription",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("openai.com"),
        "tags": ["edge_case", "subscription", "ai_saas", "blocklisted", "should_reject"],
    }


def github_copilot(seq: int) -> dict:
    body = (
        "Thanks for your payment\n\n"
        "GitHub\n\n"
        "Here's your receipt for GitHub Copilot.\n\n"
        "GitHub Copilot Individual\n"
        "$10.00/month\n"
        "Billing period: Jan 15 - Feb 15, 2026\n"
        "Payment method: Visa ****4242\n\n"
        "Receipt #: GH-REC-9876543\n\n"
        "Download your receipt: github.com/settings/billing\n\n"
        "GitHub, Inc. | 88 Colin P Kelly Jr St, San Francisco, CA 94107"
    )

    return {
        "id": _seq_id("edge-ghcopilot", seq),
        "from_address": "noreply@github.com",
        "subject": "Your receipt from GitHub — $10.00",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("github.com"),
        "tags": ["edge_case", "subscription", "developer_tool", "should_reject"],
    }


def onepassword_renewal(seq: int) -> dict:
    body = (
        "Payment receipt\n\n"
        "1Password\n\n"
        "Subscription: 1Password Families\n"
        "Amount: $4.99/month\n"
        "Next billing date: February 15, 2026\n"
        "Payment method: Apple Pay\n\n"
        "Thank you for keeping your passwords safe.\n\n"
        "Manage your account: my.1password.com"
    )

    return {
        "id": _seq_id("edge-1pass", seq),
        "from_address": "billing@1password.com",
        "subject": "Your 1Password receipt — $4.99",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("1password.com"),
        "tags": ["edge_case", "subscription", "software", "should_reject"],
    }


def notion_workspace(seq: int) -> dict:
    body = (
        "Invoice from Notion\n\n"
        "Notion Plus Plan\n"
        "Workspace: John's Projects\n\n"
        "Amount: $10.00/month\n"
        "Period: Jan 15, 2026 - Feb 14, 2026\n"
        "Payment: Visa ****4242\n\n"
        "Invoice #NOT-2026-00456\n\n"
        "View invoice: notion.so/settings/billing\n\n"
        "Notion Labs, Inc."
    )

    return {
        "id": _seq_id("edge-notion", seq),
        "from_address": "team@makenotion.com",
        "subject": "Your Notion invoice for January 2026",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("makenotion.com"),
        "tags": ["edge_case", "subscription", "saas", "should_reject"],
    }


def icloud_storage(seq: int) -> dict:
    """iCloud storage — from apple.com domain (blocklisted)."""
    body = (
        "Your receipt from Apple.\n\n"
        "iCloud+ 200 GB\n"
        "$2.99/month\n\n"
        "Billed to: Visa ****4242\n"
        "Date: January 15, 2026\n"
        "Order ID: MN5P9K4HTC\n\n"
        "Manage your iCloud storage at appleid.apple.com\n\n"
        "Apple Distribution International Ltd."
    )

    return {
        "id": _seq_id("edge-icloud", seq),
        "from_address": "no_reply@email.apple.com",
        "subject": "Your receipt from Apple — iCloud+ 200 GB",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("apple.com"),
        "tags": ["edge_case", "subscription", "cloud_storage", "blocklisted",
                 "should_reject"],
    }


# ---------------------------------------------------------------------------
# Cloud/hosting/developer services (should REJECT)
# ---------------------------------------------------------------------------

def aws_bill(seq: int) -> dict:
    body = (
        "Amazon Web Services Billing Statement\n\n"
        "Account: 123456789012\n"
        "Period: December 1-31, 2025\n\n"
        "Total charges: $47.23\n\n"
        "Service breakdown:\n"
        "EC2 .............. $18.40\n"
        "S3 ............... $3.21\n"
        "RDS .............. $15.80\n"
        "CloudFront ....... $2.45\n"
        "Route 53 ......... $1.50\n"
        "Other ............ $5.87\n\n"
        "Payment will be charged to Visa ****4242.\n\n"
        "View your bill: console.aws.amazon.com/billing"
    )

    return {
        "id": _seq_id("edge-aws", seq),
        "from_address": "aws-billing@amazon.com",
        "subject": "Your AWS bill for December 2025 — $47.23",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("amazon.com"),
        "tags": ["amazon", "edge_case", "cloud_hosting", "bill", "should_reject"],
    }


def vercel_hosting(seq: int) -> dict:
    body = (
        "Invoice from Vercel\n\n"
        "Vercel Pro Plan\n"
        "Team: john-personal\n\n"
        "Amount: $20.00/month\n"
        "Period: January 2026\n"
        "Payment: Visa ****4242\n\n"
        "Usage this month:\n"
        "Bandwidth: 124 GB / 1 TB\n"
        "Serverless Function Invocations: 890K / 1M\n"
        "Build Minutes: 450 / 6,000\n\n"
        "Vercel Inc."
    )

    return {
        "id": _seq_id("edge-vercel", seq),
        "from_address": "billing@vercel.com",
        "subject": "Vercel Pro invoice — January 2026",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("vercel.com"),
        "tags": ["edge_case", "cloud_hosting", "developer_tool", "should_reject"],
    }


def domain_renewal(seq: int) -> dict:
    body = (
        "Domain Renewal Confirmation\n\n"
        "Hi John,\n\n"
        "Your domain has been renewed successfully.\n\n"
        "Domain: myproject.dev\n"
        "Renewal period: 1 year\n"
        "New expiration: January 15, 2027\n"
        "Amount: $12.98\n\n"
        "Receipt #: NMC-2026-1234567\n\n"
        "Manage your domains: namecheap.com/myaccount\n\n"
        "Namecheap, Inc."
    )

    return {
        "id": _seq_id("edge-domain", seq),
        "from_address": "support@namecheap.com",
        "subject": "Domain renewal confirmation: myproject.dev",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("namecheap.com"),
        "tags": ["edge_case", "domain_hosting", "digital", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Online education & courses (should REJECT)
# ---------------------------------------------------------------------------

def coursera_enrollment(seq: int) -> dict:
    body = (
        "You're enrolled!\n\n"
        "Machine Learning Specialization\n"
        "by Andrew Ng | Stanford University & DeepLearning.AI\n\n"
        "You've enrolled in this 3-course specialization.\n\n"
        "Course 1: Supervised Machine Learning\n"
        "Starts: January 20, 2026\n"
        "Duration: ~4 weeks\n\n"
        "Coursera Plus: $59.00/month\n"
        "Payment: Visa ****4242\n\n"
        "Start learning: coursera.org/learn/machine-learning"
    )

    return {
        "id": _seq_id("edge-coursera", seq),
        "from_address": "no-reply@coursera.org",
        "subject": "You're enrolled in Machine Learning Specialization",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("coursera.org"),
        "tags": ["edge_case", "education", "subscription", "digital", "should_reject"],
    }


def masterclass_sub(seq: int) -> dict:
    body = (
        "Welcome to MasterClass!\n\n"
        "Your annual membership is active.\n\n"
        "Plan: MasterClass Standard\n"
        "Amount: $120.00/year\n"
        "Started: January 15, 2026\n"
        "Renews: January 15, 2027\n\n"
        "Start watching:\n"
        "- Gordon Ramsay Teaches Cooking\n"
        "- Martin Scorsese Teaches Filmmaking\n"
        "- Serena Williams Teaches Tennis\n\n"
        "MasterClass | Stream anytime on any device"
    )

    return {
        "id": _seq_id("edge-masterclass", seq),
        "from_address": "support@masterclass.com",
        "subject": "Welcome to MasterClass — your membership is active",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("masterclass.com"),
        "tags": ["edge_case", "education", "subscription", "streaming", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Fitness & wellness (should REJECT)
# ---------------------------------------------------------------------------

def classpass_credits(seq: int) -> dict:
    body = (
        "Your ClassPass credits have refreshed!\n\n"
        "Plan: 40 credits/month\n"
        "Amount charged: $79.00\n"
        "New billing cycle: Jan 15 - Feb 14, 2026\n\n"
        "Credits available: 40\n"
        "Rollover credits: 8\n"
        "Total: 48 credits\n\n"
        "Top studios near you:\n"
        "- Barry's Bootcamp (12 credits)\n"
        "- Y7 Studio Yoga (8 credits)\n"
        "- SoulCycle (14 credits)\n\n"
        "Book a class: classpass.com"
    )

    return {
        "id": _seq_id("edge-classpass", seq),
        "from_address": "hello@classpass.com",
        "subject": "Your credits have refreshed — 48 credits available",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("classpass.com"),
        "tags": ["edge_case", "fitness", "subscription", "service", "should_reject"],
    }


def peloton_membership(seq: int) -> dict:
    body = (
        "Payment confirmation\n\n"
        "Peloton All-Access Membership\n"
        "$44.00/month\n\n"
        "Billing date: January 15, 2026\n"
        "Payment: Visa ****4242\n\n"
        "This month's featured classes:\n"
        "- 30 min HIIT Ride with Robin Arzón\n"
        "- 45 min Power Zone with Matt Wilpers\n"
        "- 20 min Full Body Strength with Jess Sims\n\n"
        "Peloton Interactive, Inc."
    )

    return {
        "id": _seq_id("edge-peloton", seq),
        "from_address": "no-reply@onepeloton.com",
        "subject": "Your Peloton membership payment — $44.00",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("onepeloton.com"),
        "tags": ["edge_case", "fitness", "subscription", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Professional & financial services (should REJECT)
# ---------------------------------------------------------------------------

def turbotax_purchase(seq: int) -> dict:
    """TurboTax — digital software, no physical product."""
    body = (
        "Thank you for your purchase!\n\n"
        "TurboTax Deluxe 2025\n"
        "Federal + State\n"
        "$69.00\n\n"
        "Order #: TT-2026-8765432\n\n"
        "Your software is ready. Sign in to start your return:\n"
        "turbotax.intuit.com\n\n"
        "Important: File by April 15, 2026.\n\n"
        "Intuit Inc. | Mountain View, CA"
    )

    return {
        "id": _seq_id("edge-turbotax", seq),
        "from_address": "no-reply@intuit.com",
        "subject": "Your TurboTax purchase confirmation",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("intuit.com"),
        "tags": ["edge_case", "digital", "software", "should_reject"],
    }


def lemonade_insurance(seq: int) -> dict:
    body = (
        "Policy Active\n\n"
        "Welcome to Lemonade, John!\n\n"
        "Your Renters Insurance policy is now active.\n\n"
        "Policy #: LM-2026-12345\n"
        "Coverage: $50,000 personal property\n"
        "Deductible: $500\n"
        "Monthly premium: $12.00\n\n"
        "Effective: January 15, 2026\n"
        "Renews: January 15, 2027\n\n"
        "File a claim in 3 minutes: lemonade.com/claims\n\n"
        "Lemonade Insurance Company"
    )

    return {
        "id": _seq_id("edge-insurance", seq),
        "from_address": "support@lemonade.com",
        "subject": "Your Lemonade renters insurance is active",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("lemonade.com"),
        "tags": ["edge_case", "insurance", "service", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Car & transit services (should REJECT)
# ---------------------------------------------------------------------------

def spothero_parking(seq: int) -> dict:
    body = (
        "Reservation Confirmed\n\n"
        "SpotHero\n\n"
        "Parking at: Icon Parking - 303 W 42nd St\n"
        "Date: Saturday, January 18, 2026\n"
        "Time: 6:00 PM - 11:59 PM\n\n"
        "Total: $28.95\n"
        "Booking #: SH-9876543\n\n"
        "Show this email or the SpotHero app on arrival.\n\n"
        "Cancel up to 1 hour before for a full refund."
    )

    return {
        "id": _seq_id("edge-parking", seq),
        "from_address": "no-reply@spothero.com",
        "subject": "Parking confirmed — Icon Parking, Sat 6 PM",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("spothero.com"),
        "tags": ["edge_case", "parking", "service", "should_reject"],
    }


def car_wash_receipt(seq: int) -> dict:
    body = (
        "Receipt\n\n"
        "Mister Car Wash\n"
        "Location: 7th Ave, NYC\n\n"
        "Service: Ultimate Wash\n"
        "Date: January 16, 2026\n"
        "Time: 11:23 AM\n\n"
        "Price: $24.99\n"
        "Tax: $2.22\n"
        "Total: $27.21\n"
        "Paid: Visa ****4242\n\n"
        "Join Unlimited Wash Club — $39.99/month\n"
        "mistercarwash.com"
    )

    return {
        "id": _seq_id("edge-carwash", seq),
        "from_address": "noreply@mistercarwash.com",
        "subject": "Your car wash receipt",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("mistercarwash.com"),
        "tags": ["edge_case", "service", "car_wash", "receipt", "should_reject"],
    }


# ---------------------------------------------------------------------------
# App store & gaming purchases (should REJECT)
# ---------------------------------------------------------------------------

def apple_app_store(seq: int) -> dict:
    """App Store purchase — from apple.com (blocklisted) but also digital."""
    body = (
        "Your receipt from Apple.\n\n"
        "Apple ID: john@example.com\n\n"
        "Procreate\n"
        "In-App Purchase: Brush Pack - Watercolors\n"
        "$4.99\n\n"
        "Halide Mark II — Pro Camera\n"
        "$2.99/month (subscription)\n\n"
        "Date: January 15, 2026\n"
        "Order ID: MXKL9N4HBT\n\n"
        "Report a Problem: reportaproblem.apple.com"
    )

    return {
        "id": _seq_id("edge-appstore", seq),
        "from_address": "no_reply@email.apple.com",
        "subject": "Your receipt from Apple",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("apple.com"),
        "tags": ["edge_case", "digital", "app_store", "blocklisted", "should_reject"],
    }


def google_play(seq: int) -> dict:
    body = (
        "Google Play receipt\n\n"
        "Thanks for your purchase.\n\n"
        "Monument Valley 3\n"
        "$4.99\n\n"
        "Order number: GPA.3398-1234-5678-90123\n"
        "Date: January 15, 2026\n"
        "Payment: Google Pay (Visa ****4242)\n\n"
        "View order: play.google.com/store/account/orderhistory\n\n"
        "Google LLC | 1600 Amphitheatre Parkway, Mountain View, CA 94043"
    )

    return {
        "id": _seq_id("edge-gplay", seq),
        "from_address": "googleplay-noreply@google.com",
        "subject": "Your Google Play order receipt",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("google.com"),
        "tags": ["edge_case", "digital", "app_store", "should_reject"],
    }


# ---------------------------------------------------------------------------
# VPN & security tools (should REJECT)
# ---------------------------------------------------------------------------

def vpn_subscription(seq: int) -> dict:
    body = (
        "Subscription renewed\n\n"
        "NordVPN\n\n"
        "Your NordVPN subscription has been renewed.\n\n"
        "Plan: 2-Year Plan\n"
        "Amount: $83.76 ($3.49/month)\n"
        "Next billing: January 15, 2028\n\n"
        "Your account:\n"
        "Devices connected: 3 of 6\n"
        "Server: United States #4521\n\n"
        "Download the app: nordvpn.com/download\n\n"
        "Nord Security | Panama"
    )

    return {
        "id": _seq_id("edge-vpn", seq),
        "from_address": "support@nordvpn.com",
        "subject": "NordVPN subscription renewed — $83.76",
        "body": body,
        "body_html": None,
        "expected": _expect_reject("nordvpn.com"),
        "tags": ["edge_case", "subscription", "software", "vpn", "should_reject"],
    }


# ---------------------------------------------------------------------------
# Case generation
# ---------------------------------------------------------------------------

def generate_cases() -> list[dict]:
    """Generate all synthetic email cases."""
    cases: list[dict] = []
    seq = 1

    # ===== TIER 1: Realistic merchant emails (core pipeline test) =====

    # Amazon — most common, test all email types
    cases.append(amazon_order_realistic(seq)); seq += 1
    cases.append(amazon_shipped_realistic(seq)); seq += 1
    cases.append(amazon_delivered_realistic(seq)); seq += 1
    cases.append(amazon_multi_item(seq)); seq += 1
    cases.append(amazon_no_order_number(seq)); seq += 1

    # Other major merchants
    cases.append(target_order(seq)); seq += 1
    cases.append(target_shipped(seq)); seq += 1
    cases.append(bestbuy_html_order(seq)); seq += 1
    cases.append(nike_order(seq)); seq += 1
    cases.append(nordstrom_order(seq)); seq += 1
    cases.append(etsy_order(seq)); seq += 1
    cases.append(apple_order(seq)); seq += 1
    cases.append(zappos_order(seq)); seq += 1
    cases.append(walmart_order(seq)); seq += 1
    cases.append(allbirds_order(seq)); seq += 1

    # ===== TIER 2: Variations =====

    # Explicit return dates
    cases.append(explicit_return_date("nike", seq)); seq += 1
    cases.append(explicit_return_date("amazon", seq)); seq += 1

    # Unknown merchants (heuristic filter path)
    cases.append(unknown_merchant_order(seq)); seq += 1
    cases.append(unknown_merchant_shopify(seq)); seq += 1

    # International
    cases.append(international_merchant(seq)); seq += 1

    # ===== TIER 3: Edge cases — should REJECT =====

    # Newsletter/promo from known retailer domains (tricky — domain matches)
    cases.append(newsletter_from_retailer("amazon", seq)); seq += 1
    cases.append(newsletter_from_retailer("target", seq)); seq += 1
    cases.append(newsletter_from_retailer("nike", seq)); seq += 1

    # Review / survey requests from retailers
    cases.append(review_request("amazon", seq)); seq += 1
    cases.append(review_request("target", seq)); seq += 1

    # Password reset from retailer (false positive risk)
    cases.append(password_reset_from_retailer(seq)); seq += 1

    # Gift card (digital, non-returnable)
    cases.append(gift_card_purchase(seq)); seq += 1

    # Blocklisted services
    cases.append(subscription_netflix(seq)); seq += 1
    cases.append(subscription_spotify(seq)); seq += 1
    cases.append(digital_purchase_steam(seq)); seq += 1
    cases.append(ride_receipt_uber(seq)); seq += 1
    cases.append(food_delivery_doordash(seq)); seq += 1
    cases.append(venmo_payment(seq)); seq += 1
    cases.append(travel_booking(seq)); seq += 1
    cases.append(event_ticket(seq)); seq += 1

    # Cancellation / refund (from known domain, but not a new purchase)
    cases.append(cancellation_email(seq)); seq += 1
    cases.append(refund_confirmation(seq)); seq += 1

    # Carrier notification (UPS, not a retailer)
    cases.append(carrier_notification(seq)); seq += 1

    # Grocery / perishable
    cases.append(grocery_amazon_fresh(seq)); seq += 1

    # Marketing disguised as order
    cases.append(marketing_disguised_as_order(seq)); seq += 1
    cases.append(price_drop_alert(seq)); seq += 1

    # Minimal / boilerplate body
    cases.append(minimal_order_email(seq)); seq += 1
    cases.append(body_is_just_boilerplate("amazon", seq)); seq += 1
    cases.append(body_is_just_boilerplate("target", seq)); seq += 1

    # Narvar shipping service
    cases.append(narvar_shipping(seq)); seq += 1

    # ===== BATCH 2: 50 additional cases =====

    # --- New merchants from merchant_rules.yaml (13 cases) ---
    cases.append(gap_order(seq)); seq += 1
    cases.append(oldnavy_order(seq)); seq += 1
    cases.append(jcrew_order(seq)); seq += 1
    cases.append(athleta_order(seq)); seq += 1
    cases.append(uniqlo_order(seq)); seq += 1
    cases.append(zara_order(seq)); seq += 1
    cases.append(hm_order(seq)); seq += 1
    cases.append(adidas_order(seq)); seq += 1
    cases.append(ikea_order(seq)); seq += 1
    cases.append(wayfair_order(seq)); seq += 1
    cases.append(costco_order(seq)); seq += 1
    cases.append(ebay_purchase(seq)); seq += 1
    cases.append(poshmark_purchase(seq)); seq += 1

    # --- More email type variations (5 cases) ---
    cases.append(target_store_pickup(seq)); seq += 1
    cases.append(nordstrom_shipped(seq)); seq += 1
    cases.append(walmart_delivered(seq)); seq += 1
    cases.append(amazon_preorder(seq)); seq += 1
    cases.append(subscription_box_physical(seq)); seq += 1

    # --- Non-purchase from known retail domains (8 cases) ---
    cases.append(amazon_security_alert(seq)); seq += 1
    cases.append(target_circle_rewards(seq)); seq += 1
    cases.append(nike_membership_welcome(seq)); seq += 1
    cases.append(amazon_shipping_delay(seq)); seq += 1
    cases.append(walmart_savings_alert(seq)); seq += 1
    cases.append(nordstrom_sale_email(seq)); seq += 1
    cases.append(amazon_return_reminder(seq)); seq += 1
    cases.append(amazon_wishlist_notification(seq)); seq += 1

    # --- Grocery/perishable from allowed domains (7 cases) ---
    cases.append(hellofresh_meal_kit(seq)); seq += 1
    cases.append(amazon_supplements(seq)); seq += 1
    cases.append(whole_foods_order(seq)); seq += 1
    cases.append(target_grocery(seq)); seq += 1
    cases.append(flowers_1800(seq)); seq += 1
    cases.append(instacart_grocery(seq)); seq += 1
    cases.append(walmart_grocery(seq)); seq += 1

    # --- More blocklisted domain rejections (6 cases) ---
    cases.append(airbnb_booking(seq)); seq += 1
    cases.append(starbucks_mobile_order(seq)); seq += 1
    cases.append(adobe_subscription(seq)); seq += 1
    cases.append(kickstarter_backed(seq)); seq += 1
    cases.append(gofundme_donation(seq)); seq += 1
    cases.append(chipotle_order(seq)); seq += 1

    # --- Tricky edge cases (7 cases) ---
    cases.append(asurion_warranty(seq)); seq += 1
    cases.append(amazon_kindle_ebook(seq)); seq += 1
    cases.append(fedex_carrier(seq)); seq += 1
    cases.append(return_approved_email(seq)); seq += 1
    cases.append(order_address_change(seq)); seq += 1
    cases.append(amazon_prime_video(seq)); seq += 1

    # --- 5 more targeted cases to reach 50 new ---
    cases.append(amazon_third_party_seller(seq)); seq += 1
    cases.append(back_market_refurbished(seq)); seq += 1
    cases.append(usps_carrier(seq)); seq += 1
    cases.append(square_instore_receipt(seq)); seq += 1
    cases.append(costco_electronics(seq)); seq += 1

    # ===== BATCH 3: Services, appointments, digital subscriptions =====

    # --- Appointments & local services (5 cases) ---
    cases.append(barber_appointment(seq)); seq += 1
    cases.append(dentist_appointment(seq)); seq += 1
    cases.append(auto_repair_receipt(seq)); seq += 1
    cases.append(dog_grooming(seq)); seq += 1
    cases.append(house_cleaning(seq)); seq += 1

    # --- Digital subscriptions & AI/SaaS (6 cases) ---
    cases.append(claude_pro_renewal(seq)); seq += 1
    cases.append(chatgpt_plus_renewal(seq)); seq += 1
    cases.append(github_copilot(seq)); seq += 1
    cases.append(onepassword_renewal(seq)); seq += 1
    cases.append(notion_workspace(seq)); seq += 1
    cases.append(icloud_storage(seq)); seq += 1

    # --- Cloud/hosting/developer (3 cases) ---
    cases.append(aws_bill(seq)); seq += 1
    cases.append(vercel_hosting(seq)); seq += 1
    cases.append(domain_renewal(seq)); seq += 1

    # --- Online education (2 cases) ---
    cases.append(coursera_enrollment(seq)); seq += 1
    cases.append(masterclass_sub(seq)); seq += 1

    # --- Fitness & wellness (2 cases) ---
    cases.append(classpass_credits(seq)); seq += 1
    cases.append(peloton_membership(seq)); seq += 1

    # --- Professional & financial (2 cases) ---
    cases.append(turbotax_purchase(seq)); seq += 1
    cases.append(lemonade_insurance(seq)); seq += 1

    # --- Car & transit (2 cases) ---
    cases.append(spothero_parking(seq)); seq += 1
    cases.append(car_wash_receipt(seq)); seq += 1

    # --- App store & gaming (2 cases) ---
    cases.append(apple_app_store(seq)); seq += 1
    cases.append(google_play(seq)); seq += 1

    # --- VPN & security (1 case) ---
    cases.append(vpn_subscription(seq)); seq += 1

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

    # Summary
    extract = sum(1 for c in cases if c["expected"]["should_extract"])
    reject = sum(1 for c in cases if not c["expected"]["should_extract"])
    tags: dict[str, int] = {}
    for c in cases:
        for t in c.get("tags", []):
            tags[t] = tags.get(t, 0) + 1

    print(f"Generated {len(cases)} cases -> {OUTPUT_FILE}")
    print(f"  Expected extractions: {extract}")
    print(f"  Expected rejections:  {reject}")
    print(f"  Top tags: {', '.join(f'{t}({n})' for t, n in sorted(tags.items(), key=lambda x: -x[1])[:8])}")


if __name__ == "__main__":
    main()
