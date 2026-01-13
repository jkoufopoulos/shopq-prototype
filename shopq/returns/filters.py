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
    }

    # Keywords that suggest a shopping receipt (for unknown domains)
    SHOPPING_KEYWORDS: set[str] = {
        "order confirm",
        "order confirmation",
        "your order",
        "order #",
        "order number",
        "shipment",
        "shipped",
        "tracking",
        "delivery",
        "delivered",
        "out for delivery",
        "package",
        "receipt",
        "invoice",
        "purchase",
        "item",
        "quantity",
        "subtotal",
        "total",
        "shipping address",
        "ship to",
    }

    # Anti-keywords that suggest non-shopping receipt
    NON_SHOPPING_KEYWORDS: set[str] = {
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

    def _extract_domain(self, from_address: str) -> str:
        """
        Extract domain from email address.

        Handles formats:
        - "noreply@amazon.com" → "amazon.com"
        - "Amazon <noreply@amazon.com>" → "amazon.com"
        - "ship-confirm@amazon.com" → "amazon.com"
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

        # Handle subdomains - keep only last two parts
        # e.g., "ship.amazon.com" → "amazon.com"
        parts = domain.split(".")
        if len(parts) > 2:
            # Keep last two parts unless it's a known TLD pattern
            # e.g., "co.uk", "com.au"
            if parts[-2] in ("co", "com", "org", "net"):
                domain = ".".join(parts[-3:])
            else:
                domain = ".".join(parts[-2:])

        return domain

    def _check_heuristics(
        self, domain: str, subject: str, snippet: str
    ) -> FilterResult:
        """
        Use keyword heuristics for unknown domains.

        Checks for shopping-related keywords vs non-shopping keywords.
        """
        text = f"{subject} {snippet}".lower()

        # Count shopping vs non-shopping keyword matches
        shopping_score = sum(1 for kw in self.SHOPPING_KEYWORDS if kw in text)
        non_shopping_score = sum(1 for kw in self.NON_SHOPPING_KEYWORDS if kw in text)

        # Decision logic
        if shopping_score >= 2 and shopping_score > non_shopping_score:
            return FilterResult(
                is_candidate=True,
                reason=f"shopping_keywords({shopping_score})",
                domain=domain,
                match_type="heuristic",
            )

        if non_shopping_score >= 2:
            return FilterResult(
                is_candidate=False,
                reason=f"non_shopping_keywords({non_shopping_score})",
                domain=domain,
                match_type="heuristic",
            )

        # Borderline case: single shopping keyword match
        if shopping_score >= 1:
            return FilterResult(
                is_candidate=True,
                reason=f"weak_shopping_signal({shopping_score})",
                domain=domain,
                match_type="heuristic",
            )

        # No signal - default to pass (let LLM decide)
        # This is conservative: we'd rather have LLM reject than miss a purchase
        return FilterResult(
            is_candidate=True,
            reason="unknown_domain_no_signal",
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
