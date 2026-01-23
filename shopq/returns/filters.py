"""
Domain-based pre-filter for returnable purchase detection.

Stage 1 of the extraction pipeline. Fast, rule-based filtering
to eliminate obvious non-returnable receipts before LLM classification.

Cost: $0 (no LLM calls)
Expected pass-through rate: 30-40% of emails
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from shopq.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FilterResult:
    """Result of domain filter check."""

    is_candidate: bool
    reason: str
    domain: str
    match_type: str  # "allowlist" | "blocklist" | "heuristic" | "unknown"


class MerchantDomainFilter:
    """
    Pre-filter emails by sender domain before LLM classification.

    Fast rule-based check that:
    1. Blocks known non-returnable services (Uber, Netflix, etc.)
    2. Passes known shopping merchants (Amazon, Target, etc.)
    3. Uses keyword heuristics for unknown domains
    """

    # Known non-returnable services - block immediately
    # These never need LLM classification
    BLOCKLIST: set[str] = {
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
        "apple.com",  # Note: apple.com for iTunes/App Store; physical orders use different sender
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
        # Utilities & bills
        "xfinity.com",
        "spectrum.com",
        "att.com",
        "verizon.com",
        "t-mobile.com",
        # Donations & crowdfunding
        "gofundme.com",
        "kickstarter.com",
        "indiegogo.com",
        # Tickets & events (different refund process)
        "ticketmaster.com",
        "stubhub.com",
        "eventbrite.com",
        "seatgeek.com",
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
    }

    # Keywords that suggest PURCHASE CONFIRMATION (not shipping updates)
    # Per R1: Must have order ID, purchase amount + confirmation, or explicit confirmation language
    # Note: These are phrases that appear primarily in ORDER CONFIRMATIONS, not updates
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

    # Keywords that indicate DELIVERY (these are GOOD signals - means there's a purchase to track)
    # These should PASS to the LLM, not be rejected
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

    # Subject patterns that indicate NON-RETURNABLE purchases (block even from allowlisted domains)
    # Groceries, food, and perishables are consumed - NEVER returnable
    # NOTE: These must be specific enough to avoid false positives (e.g., "shipt" matches "shipped")
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
    }

    # Keywords for NON-PURCHASE emails (should be EXCLUDED)
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
    }

    def __init__(self, merchant_rules_path: Path | None = None):
        """
        Initialize filter with merchant rules.

        Args:
            merchant_rules_path: Path to merchant_rules.yaml.
                                 If None, uses default location.
        """
        if merchant_rules_path is None:
            merchant_rules_path = (
                Path(__file__).parent.parent.parent / "config" / "merchant_rules.yaml"
            )

        self.merchant_rules = self._load_merchant_rules(merchant_rules_path)
        self.allowlist = self._build_allowlist()

        logger.info(
            "MerchantDomainFilter initialized: %d allowlist, %d blocklist",
            len(self.allowlist),
            len(self.BLOCKLIST),
        )

    def _load_merchant_rules(self, path: Path) -> dict:
        """Load merchant rules from YAML config."""
        if not path.exists():
            logger.warning("Merchant rules not found at %s, using empty rules", path)
            return {"merchants": {}}

        with open(path) as f:
            return yaml.safe_load(f)

    def _build_allowlist(self) -> set[str]:
        """Build allowlist from merchant_rules.yaml."""
        merchants = self.merchant_rules.get("merchants", {})
        # Exclude _default since it's not a real merchant
        return {domain for domain in merchants.keys() if domain != "_default"}

    def filter(self, from_address: str, subject: str, snippet: str = "") -> FilterResult:
        """
        Check if email is a candidate for returnable purchase.

        Args:
            from_address: Email sender (e.g., "noreply@amazon.com")
            subject: Email subject line
            snippet: Email body snippet/preview

        Returns:
            FilterResult with is_candidate=True if should proceed to LLM,
            False if definitely not returnable.
        """
        domain = self._extract_domain(from_address)
        text_lower = f"{subject} {snippet}".lower()

        # Check grocery/perishable patterns first (never returnable, even from allowlisted domains)
        for pattern in self.GROCERY_PERISHABLE_PATTERNS:
            if pattern in text_lower:
                return FilterResult(
                    is_candidate=False,
                    reason=f"grocery_food:{pattern}",
                    domain=domain,
                    match_type="blocklist",
                )

        # Check blocklist first (fast reject)
        if domain in self.BLOCKLIST:
            return FilterResult(
                is_candidate=False,
                reason="blocklist",
                domain=domain,
                match_type="blocklist",
            )

        # Check allowlist (known shopping merchants)
        if domain in self.allowlist:
            return FilterResult(
                is_candidate=True,
                reason="known_merchant",
                domain=domain,
                match_type="allowlist",
            )

        # Unknown domain - use keyword heuristics
        return self._check_heuristics(domain, subject, snippet)

    # Shipping service domains where the subdomain indicates the merchant
    # e.g., bananarepublic.narvar.com -> bananarepublic.com
    SHIPPING_SERVICE_DOMAINS: set[str] = {
        "narvar.com",
        "narvar.io",
        "returnly.com",
        "loop.com",
        "happyreturns.com",
    }

    def _extract_domain(self, from_address: str) -> str:
        """
        Extract domain from email address.

        Handles formats:
        - "noreply@amazon.com" → "amazon.com"
        - "Amazon <noreply@amazon.com>" → "amazon.com"
        - "ship-confirm@amazon.com" → "amazon.com"
        - "bananarepublic@bananarepublic.narvar.com" → "bananarepublic.com" (shipping service)
        """
        # Extract email from "Name <email>" format
        match = re.search(r"<([^>]+)>", from_address)
        if match:
            from_address = match.group(1)

        # Extract domain part
        if "@" in from_address:
            domain = from_address.split("@")[-1].lower().strip()
        else:
            domain = from_address.lower().strip()

        # Handle subdomains
        parts = domain.split(".")

        # Check for shipping service domains (narvar, returnly, etc.)
        # e.g., "bananarepublic.narvar.com" -> extract "bananarepublic" and make "bananarepublic.com"
        if len(parts) >= 3:
            base_domain = ".".join(parts[-2:])
            if base_domain in self.SHIPPING_SERVICE_DOMAINS:
                # Use subdomain as merchant (e.g., bananarepublic.narvar.com -> bananarepublic.com)
                merchant_subdomain = parts[0]
                if merchant_subdomain and len(merchant_subdomain) > 2:
                    return f"{merchant_subdomain}.com"

        # Standard subdomain handling - keep only last two parts
        # e.g., "ship.amazon.com" → "amazon.com"
        if len(parts) > 2:
            # Keep last two parts unless it's a known TLD pattern
            # e.g., "co.uk", "com.au"
            if parts[-2] in ("co", "com", "org", "net"):
                domain = ".".join(parts[-3:])
            else:
                domain = ".".join(parts[-2:])

        return domain

    def _check_heuristics(self, domain: str, subject: str, snippet: str) -> FilterResult:
        """
        Use keyword heuristics for unknown domains.

        Philosophy: Be PERMISSIVE. Delivery signals are GOOD (means there's a purchase).
        Let the LLM decide what's returnable vs perishable.
        """
        text = f"{subject} {snippet}".lower()

        # Count keyword matches
        purchase_score = sum(1 for kw in self.PURCHASE_CONFIRMATION_KEYWORDS if kw in text)
        delivery_score = sum(1 for kw in self.DELIVERY_KEYWORDS if kw in text)
        non_purchase_score = sum(1 for kw in self.NON_PURCHASE_KEYWORDS if kw in text)

        # NEW LOGIC: Be permissive - delivery/shipping signals are GOOD
        # Let the LLM decide what's returnable

        # Rule 1: Delivery/shipping signals → PASS (this means there's a purchase!)
        if delivery_score >= 1:
            return FilterResult(
                is_candidate=True,
                reason=f"delivery_signal({delivery_score})",
                domain=domain,
                match_type="heuristic",
            )

        # Rule 2: Purchase confirmation → PASS
        if purchase_score >= 1:
            return FilterResult(
                is_candidate=True,
                reason=f"purchase_signal({purchase_score})",
                domain=domain,
                match_type="heuristic",
            )

        # Rule 3: Only reject if CLEARLY non-purchase (marketing, feedback, etc.)
        # AND no positive signals
        if non_purchase_score >= 2 and purchase_score == 0 and delivery_score == 0:
            return FilterResult(
                is_candidate=False,
                reason=f"marketing_only({non_purchase_score})",
                domain=domain,
                match_type="heuristic",
            )

        # Rule 4: Unknown - default to PASS (let LLM decide)
        # Better to let LLM filter than miss a purchase
        return FilterResult(
            is_candidate=True,
            reason="unknown_let_llm_decide",
            domain=domain,
            match_type="unknown",
        )

    def get_merchant_rule(self, domain: str) -> dict | None:
        """
        Get merchant return rule for a domain.

        Args:
            domain: Merchant domain (e.g., "amazon.com")

        Returns:
            Merchant rule dict with days, anchor, return_url, etc.
            Returns _default rule if domain not found.
            Returns None if no rules loaded.
        """
        merchants = self.merchant_rules.get("merchants", {})

        if domain in merchants:
            return merchants[domain]

        # Return default rule for unknown merchants
        return merchants.get("_default")

    def add_to_blocklist(self, domain: str) -> None:
        """
        Dynamically add a domain to blocklist.

        Useful for runtime updates based on user feedback.
        """
        self.BLOCKLIST.add(domain.lower())
        logger.info("Added %s to blocklist", domain)

    def add_to_allowlist(self, domain: str) -> None:
        """
        Dynamically add a domain to allowlist.

        Useful for runtime updates when new merchants are discovered.
        """
        self.allowlist.add(domain.lower())
        logger.info("Added %s to allowlist", domain)
