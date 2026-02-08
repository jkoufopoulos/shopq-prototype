"""
Domain-based pre-filter for returnable purchase detection.

Stage 1 of the extraction pipeline. Fast, rule-based filtering
to eliminate obvious non-returnable receipts before LLM classification.

Cost: $0 (no LLM calls)
Expected pass-through rate: 30-40% of emails
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from shopq.observability.logging import get_logger
from shopq.returns.filter_data import (
    DEFAULT_BLOCKLIST,
    DELIVERY_KEYWORDS,
    GROCERY_PERISHABLE_PATTERNS,
    NON_PURCHASE_KEYWORDS,
    PURCHASE_CONFIRMATION_KEYWORDS,
    SHIPPING_SERVICE_DOMAINS,
    SURVEY_SUBJECT_KEYWORDS,
)
from shopq.returns.types import FilterResult

logger = get_logger(__name__)


class MerchantDomainFilter:
    """
    Pre-filter emails by sender domain before LLM classification.

    Fast rule-based check that:
    1. Blocks known non-returnable services (Uber, Netflix, etc.)
    2. Passes known shopping merchants (Amazon, Target, etc.)
    3. Uses keyword heuristics for unknown domains

    Keyword/domain constants live in filter_data.py.
    """

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

        # CODE-009: Copy to instance to prevent cross-worker state issues
        self.blocklist: set[str] = set(DEFAULT_BLOCKLIST)

        self.merchant_rules = self._load_merchant_rules(merchant_rules_path)
        self.allowlist = self._build_allowlist()

        logger.info(
            "MerchantDomainFilter initialized: %d allowlist, %d blocklist",
            len(self.allowlist),
            len(self.blocklist),
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
        return {domain for domain in merchants if domain != "_default"}

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
        for pattern in GROCERY_PERISHABLE_PATTERNS:
            if pattern in text_lower:
                return FilterResult(
                    is_candidate=False,
                    reason=f"grocery_food:{pattern}",
                    domain=domain,
                    match_type="blocklist",
                )

        # Check survey/feedback subject keywords (free rejection)
        subject_lower = subject.lower()
        for keyword in SURVEY_SUBJECT_KEYWORDS:
            if keyword in subject_lower:
                return FilterResult(
                    is_candidate=False,
                    reason=f"survey_feedback:{keyword}",
                    domain=domain,
                    match_type="blocklist",
                )

        # Check blocklist first (fast reject)
        if domain in self.blocklist:
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
        # e.g., "bananarepublic.narvar.com" -> "bananarepublic.com"
        if len(parts) >= 3:
            base_domain = ".".join(parts[-2:])
            if base_domain in SHIPPING_SERVICE_DOMAINS:
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
        purchase_score = sum(1 for kw in PURCHASE_CONFIRMATION_KEYWORDS if kw in text)
        delivery_score = sum(1 for kw in DELIVERY_KEYWORDS if kw in text)
        non_purchase_score = sum(1 for kw in NON_PURCHASE_KEYWORDS if kw in text)

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

        CODE-009: Now modifies instance variable instead of class variable.
        Useful for runtime updates based on user feedback.
        """
        self.blocklist.add(domain.lower())
        logger.info("Added %s to blocklist", domain)

    def add_to_allowlist(self, domain: str) -> None:
        """
        Dynamically add a domain to allowlist.

        Useful for runtime updates when new merchants are discovered.
        """
        self.allowlist.add(domain.lower())
        logger.info("Added %s to allowlist", domain)
