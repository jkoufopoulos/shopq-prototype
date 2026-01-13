"""

from __future__ import annotations

ShopQ Digest Delivery

SMTP email delivery for digest emails.
"""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from shopq.observability.logging import get_logger

logger = get_logger(__name__)


class DigestDelivery:
    """Handles email delivery for digests"""

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        from_email: str | None = None,
        from_name: str = "ShopQ",
    ):
        """
        Initialize SMTP delivery

        Environment variables (if params not provided):
        - SMTP_HOST: SMTP server hostname
        - SMTP_PORT: SMTP server port (default: 587)
        - SMTP_USER: SMTP username
        - SMTP_PASSWORD: SMTP password
        - SMTP_FROM_EMAIL: From email address
        - SMTP_FROM_NAME: From name (default: "ShopQ")
        """
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.from_email = from_email or os.getenv("SMTP_FROM_EMAIL", self.smtp_user)
        self.from_name = os.getenv("SMTP_FROM_NAME", from_name)

        # Validate configuration
        if not all([self.smtp_host, self.smtp_user, self.smtp_password, self.from_email]):
            logger.warning("SMTP not fully configured. Set SMTP_* environment variables.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(
                "SMTP delivery configured: %s@%s:%s",
                self.smtp_user,
                self.smtp_host,
                self.smtp_port,
            )

    def send_digest(self, to_email: str, subject: str, content: str, format: str = "html") -> bool:
        """
        Send a digest email

        Args:
            to_email: Recipient email address
            subject: Email subject
            content: Email body (HTML or plaintext)
            format: "html" or "plaintext"

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.error("SMTP delivery not enabled. Configure SMTP_* environment variables.")
            return False

        try:
            assert self.smtp_host is not None
            assert self.smtp_port is not None
            assert self.smtp_user is not None
            assert self.smtp_password is not None
            assert self.from_email is not None
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email
            msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")

            # Add content
            if format == "html":
                # Include plaintext fallback
                plaintext = self._html_to_plaintext(content)
                msg.attach(MIMEText(plaintext, "plain"))
                msg.attach(MIMEText(content, "html"))
            else:
                msg.attach(MIMEText(content, "plain"))

            # Connect and send
            logger.info("Connecting to %s:%s", self.smtp_host, self.smtp_port)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info("Digest sent to %s", to_email)
            logger.info("Subject: %s", subject)
            return True

        except Exception as e:
            logger.exception("Failed to send digest: %s", e)
            return False

    def send_test_email(self, to_email: str) -> bool:
        """Send a test email to verify SMTP configuration"""
        test_content = f"""
        <html>
        <body>
            <h2>ShopQ Test Email</h2>
            <p>This is a test email from ShopQ Digest.</p>
            <p>If you receive this, your SMTP configuration is working correctly.</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                Sent at {datetime.now().isoformat()}
            </p>
        </body>
        </html>
        """

        return self.send_digest(
            to_email=to_email,
            subject="ShopQ Test Email",
            content=test_content,
            format="html",
        )

    def _html_to_plaintext(self, html: str) -> str:
        """
        Simple HTML to plaintext conversion

        For better conversion, consider using html2text library
        """
        import re

        # Remove style and script tags
        text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)

        # Replace common tags with plaintext equivalents
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<hr\s*/?>", "\n---\n", text)
        text = re.sub(r"<h[1-6][^>]*>", "\n\n", text)
        text = re.sub(r"</h[1-6]>", "\n", text)
        text = re.sub(r"<p[^>]*>", "\n", text)
        text = re.sub(r"</p>", "\n", text)
        text = re.sub(r"<div[^>]*>", "\n", text)
        text = re.sub(r"</div>", "\n", text)

        # Remove all other HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Decode HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")

        # Clean up whitespace
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()

    def get_config_status(self) -> dict[str, Any]:
        """Get SMTP configuration status"""
        return {
            "enabled": self.enabled,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_user": self.smtp_user,
            "smtp_password_set": bool(self.smtp_password),
            "from_email": self.from_email,
            "from_name": self.from_name,
        }


# Convenience function for quick testing
def test_smtp_config(to_email: str) -> None:
    """
    Quick test of SMTP configuration

    Usage:
        from shopq.digest.delivery import test_smtp_config
        test_smtp_config("your-email@example.com")
    """
    delivery = DigestDelivery()

    logger.info("\n" + "=" * 80)
    logger.info("SMTP Configuration Status")
    logger.info("=" * 80)

    config = delivery.get_config_status()
    for key, value in config.items():
        logger.info("%s: %s", key, value)

    logger.info("\n" + "=" * 80)
    logger.info("Sending test email...")
    logger.info("=" * 80 + "\n")

    success = delivery.send_test_email(to_email)

    if success:
        logger.info("\n✅ Test email sent successfully!")
        logger.info("Check %s for the test message.", to_email)
    else:
        logger.error("\n❌ Test email failed.")
        logger.info("\nTroubleshooting:")
        logger.info("1. Check SMTP_* environment variables in .env")
        logger.info("2. Verify SMTP credentials are correct")
        logger.info("3. Check if less secure apps / app passwords are enabled")
        logger.info("4. For Gmail: Use app-specific password, not main password")

    return success


if __name__ == "__main__":
    # CLI for testing SMTP
    import sys

    if len(sys.argv) < 2:
        logger.info("Usage: python -m shopq.digest_delivery <email>")
        logger.info("Example: python -m shopq.digest_delivery user@example.com")
        sys.exit(1)

    test_email = sys.argv[1]
    test_smtp_config(test_email)
