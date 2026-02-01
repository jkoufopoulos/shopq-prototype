"""HTML-to-text conversion for email bodies.

Many merchant emails (Walmart, Calvin Klein, etc.) are HTML-only with no
text/plain MIME part. This module converts HTML to readable plain text
for the extraction pipeline.
"""

from __future__ import annotations

import re

from shopq.observability.logging import get_logger

logger = get_logger(__name__)


def html_to_text(html: str) -> str:
    """Convert HTML email body to plain text.

    Uses BeautifulSoup if available, falls back to regex stripping.

    Args:
        html: Raw HTML string from email body.

    Returns:
        Plain text extracted from the HTML.
    """
    if not html:
        return ""

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style", "head"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
    except ImportError:
        logger.warning("beautifulsoup4 not installed, using regex fallback for HTML conversion")
        text = _regex_html_to_text(html)

    # Collapse whitespace: multiple blank lines -> single, strip each line
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _regex_html_to_text(html: str) -> str:
    """Fallback HTML-to-text using regex when BeautifulSoup is unavailable."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", "", text)
    return text
