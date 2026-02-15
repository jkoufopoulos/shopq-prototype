"""
Module: filter_data
Purpose: Keyword and domain constants for the Stage 1 domain filter.
Dependencies: None (pure data, no imports)

Separates filter policy data from filter logic. Edit this file to add/remove
domains or keywords without touching the filtering algorithm in filters.py.
"""

# ---------------------------------------------------------------------------
# Default blocklist — known non-returnable services
# Block immediately, no LLM call needed
# ---------------------------------------------------------------------------

DEFAULT_BLOCKLIST: frozenset[str] = frozenset(
    {
        # Ride-sharing & transportation
        "uber.com",
        "lyft.com",
        "bird.co",
        "lime.bike",
        # Food delivery (consumables, not returnable)
        "doordash.com",
        "grubhub.com",
        "postmates.com",
        "ubereats.com",
        "seamless.com",
        "caviar.com",
        "instacart.com",
        # Streaming & subscriptions
        "netflix.com",
        "spotify.com",
        "hulu.com",
        "disneyplus.com",
        "hbomax.com",
        "peacocktv.com",
        "paramount.com",
        "apple.com",  # iTunes/App Store; physical orders use different sender
        "music.apple.com",
        "itunes.com",
        # Digital games & software
        "steampowered.com",
        "epicgames.com",
        "playstation.com",
        "xbox.com",
        "nintendo.com",
        "gog.com",
        "humblebundle.com",
        # AI / SaaS services
        "anthropic.com",
        "openai.com",
        "mobbin.com",
        # News & memberships
        "nytimes.com",
        "wsj.com",
        "washingtonpost.com",
        "patreon.com",
        "substack.com",
        "medium.com",
        # Financial services
        "venmo.com",
        "paypal.com",
        "cashapp.com",
        "zelle.com",
        "chase.com",
        "bankofamerica.com",
        "wellsfargo.com",
        # Telecom & eSIM providers
        "xfinity.com",
        "spectrum.com",
        "att.com",
        "verizon.com",
        "t-mobile.com",
        "mintmobile.com",
        "holafly.com",
        # Donations & crowdfunding
        "gofundme.com",
        "kickstarter.com",
        "indiegogo.com",
        # Tickets & events (different refund process)
        "ticketmaster.com",
        "stubhub.com",
        "eventbrite.com",
        "seatgeek.com",
        "shotgun.live",
        "dice.fm",
        # Travel (different refund process)
        "expedia.com",
        "booking.com",
        "airbnb.com",
        "hotels.com",
        "kayak.com",
        "priceline.com",
        # Restaurants & hospitality
        "starbucks.com",
        "dunkindonuts.com",
        "mcdonalds.com",
        "chipotle.com",
        "opentable.com",
        "resy.com",
        # E-cards & greetings (not purchases)
        "jibjab.com",
        "hallmark.com",
        "americangreetings.com",
        "bluemountain.com",
        # Services (warranty, insurance, return processing)
        "happyreturns.com",
        "asurion.com",
        "squaretrade.com",
    }
)

# ---------------------------------------------------------------------------
# Purchase confirmation keywords
# Per R1: Must have order ID, purchase amount + confirmation, or explicit
# confirmation language. These appear primarily in ORDER CONFIRMATIONS.
# ---------------------------------------------------------------------------

PURCHASE_CONFIRMATION_KEYWORDS: set[str] = {
    # Strong confirmation phrases
    "order confirm",
    "order confirmation",
    "order confirmed",
    "thanks for your order",
    "thank you for your order",
    "thank you for your purchase",
    "thanks for your purchase",
    "payment received",
    "payment confirmed",
    "purchase confirmation",
    "purchase confirmed",
    # Order identifiers (with specific patterns)
    "confirmation #",
    "confirmation number",
    "receipt",
    "invoice",
    # Financial indicators
    "subtotal",
    "order total",
    # Order patterns
    "you ordered",
    "your order of",
    "order of",  # e.g., "Amazon.com order of Product Name"
}

# ---------------------------------------------------------------------------
# Delivery keywords — GOOD signals (means there's a purchase to track)
# These should PASS to the LLM, not be rejected.
# ---------------------------------------------------------------------------

DELIVERY_KEYWORDS: set[str] = {
    "shipped",
    "has shipped",
    "is shipping",
    "out for delivery",
    "has been delivered",
    "was delivered",
    "delivery update",
    "on its way",
    "in transit",
    "en route",
    "arriving",
    "your package",
    "delivered",
}

# ---------------------------------------------------------------------------
# Grocery / perishable patterns — NEVER returnable
# Block even from allowlisted domains. Must be specific enough to avoid
# false positives (e.g., "shipt" vs "shipped").
# ---------------------------------------------------------------------------

GROCERY_PERISHABLE_PATTERNS: set[str] = {
    # Grocery services - use full names to avoid substring matches
    "whole foods",
    "whole foods market",
    "amazon fresh",
    "instacart order",
    "your grocery",
    "grocery order",
    "grocery delivery",
    "fresh delivery",
    "walmart grocery",
    "target grocery",
    "shipt order",  # Specific to avoid matching "shipped"
    "shipt delivery",
    # Food delivery
    "food delivery",
    "doordash order",
    "grubhub order",
    "uber eats",
    "postmates order",
    "seamless order",
    "caviar order",
    # Meal kits
    "meal kit",
    "hello fresh",
    "hellofresh",
    "blue apron",
    "freshly",
    "factor meals",
    "factor_",
    "home chef",
    "homechef",
    "sunbasket",
    "green chef",
    # Perishables
    "flowers",
    "flower delivery",
    "bouquet",
    "1-800-flowers",
    "ftd",
    "proflowers",
    "fresh produce",
    "perishable",
    # Consumable health/nutrition products
    "protein shake",
    "protein bar",
    "energy drink",
    "vitamins",
    "supplements",
    "snack",
    "snacks",
}

# ---------------------------------------------------------------------------
# Survey / feedback subject keywords — free rejection before LLM
# ---------------------------------------------------------------------------

SURVEY_SUBJECT_KEYWORDS: list[str] = [
    "share your thoughts",
    "leave a review",
    "write a review",
    "rate your",
    "how did we do",
]

# ---------------------------------------------------------------------------
# Non-purchase keywords — emails to EXCLUDE
# ---------------------------------------------------------------------------

NON_PURCHASE_KEYWORDS: set[str] = {
    # Order updates (not confirmations)
    "update to your order",
    "an update to",
    "order update",
    "update on your order",
    "changes to your order",
    "order has been received",  # Ambiguous - seller received vs. delivered
    "order placed",  # Just placed, not confirmed
    # Shipping/delivery notifications
    "rate your experience",
    "rate your order",
    "how was your",
    "leave a review",
    "write a review",
    "feedback",
    # Return reminders (not purchases)
    "return your items",
    "return deadline",
    "time to return",
    "return window",
    "don't forget to return",
    # Marketing
    "sale ends",
    "shop now",
    "buy now",
    "limited time",
    "% off",
    "discount code",
    # Subscriptions & services
    "subscription",
    "monthly plan",
    "recurring",
    "membership",
    "ride",
    "trip",
    "your driver",
    "donation",
    "contribution",
    "tip",
    "gratuity",
    "streaming",
    "download",
    "digital",
    "e-book",
    "ebook",
    "license",
    "activation",
    # E-cards & non-products
    "special delivery from",  # JibJab-style e-cards
    "sent you",
    "e-card",
    "ecard",
    "greeting",
    # Cancellation emails (no product to return)
    "cancelled",
    "item cancelled",
    "cancellation",
    "order cancelled",
    "has been cancelled",
    "successfully cancelled",
    # Return confirmation emails (outgoing, not incoming products)
    "return is approved",
    "return approved",
    "return has been processed",
    "refund has been",
    "refund processed",
    "return confirmation",
    # Warranty/protection plans (service contracts, not physical products)
    "protection plan",
    "warranty plan",
    "extended warranty",
    "terms and conditions",
    # Verification / auth codes (not purchases)
    "verification code",
    "is your verification",
    # Digital passes / eSIM (not physical goods)
    "esim",
    "e-sim",
    # Misc non-purchase
    "keep your",
    "open drawing",
}

# ---------------------------------------------------------------------------
# Shipping service domains — subdomain indicates the merchant
# e.g., bananarepublic.narvar.com → bananarepublic.com
# ---------------------------------------------------------------------------

SHIPPING_SERVICE_DOMAINS: set[str] = {
    "narvar.com",
    "narvar.io",
    "returnly.com",
    "loop.com",
    "happyreturns.com",
}
