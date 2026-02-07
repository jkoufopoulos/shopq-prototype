# Privacy Policy for Reclaim

**Last Updated:** February 7, 2026

Reclaim ("we", "our", or "the extension") is a browser extension that helps you track return windows on online purchases. This privacy policy explains what data we collect, how we use it, and your rights.

## Summary

- We read your Gmail to find order confirmation emails
- We extract order details (merchant, items, dates) to calculate return deadlines
- Data is stored locally on your device and on our secure servers
- We never sell your data or show you ads
- You can delete your data at any time

---

## What Data We Collect

### Email Data
When you use Reclaim, we access your Gmail to find purchase-related emails. We collect:

- **Email metadata**: Subject line, sender, date received
- **Order information**: Merchant name, items purchased, order numbers, delivery dates
- **Return policy details**: Return deadlines extracted from emails

We do **NOT** collect:
- Email content unrelated to purchases
- Attachments
- Your contacts or address book
- Emails you send

### Account Information
- Your Google account email address (for user identification)
- No passwords are ever collected or stored

### Usage Data
- Extension feature usage (anonymized)
- Error logs for debugging (no personal data)

---

## How We Use Your Data

1. **Calculate return deadlines** - We analyze order emails to determine when return windows expire
2. **Send reminders** - We notify you before return deadlines pass
3. **Improve the service** - Anonymized usage data helps us fix bugs and add features

We do **NOT**:
- Sell your data to third parties
- Use your data for advertising
- Share your data with marketers
- Train AI models on your personal data

---

## Where Data Is Stored

### On Your Device
- Order information is cached locally in your browser's storage
- This data never leaves your device unless you use our sync features

### On Our Servers
- Order metadata is stored on Google Cloud Run (US region)
- Data is encrypted in transit (TLS 1.3) and at rest
- Servers are secured with Google Cloud's enterprise security

### Third-Party Services

| Service | Purpose | Data Shared |
|---------|---------|-------------|
| Google Gmail API | Read order emails | Email content (read-only) |
| Google Gemini API | Extract order details | Email text for processing |
| Google Cloud Run | Store order data | Order metadata |

---

## Data Retention

- **Active orders**: Kept until 90 days after return window expires
- **Expired orders**: Automatically deleted after 90 days
- **Account deletion**: All data deleted within 30 days of request

---

## Your Rights

You have the right to:

1. **Access your data** - View all data we have about you in the extension
2. **Delete your data** - Remove all stored data from Settings > Clear Data
3. **Export your data** - Download your order history (coming soon)
4. **Revoke access** - Disconnect Gmail access from your Google Account settings

### How to Delete Your Data

1. Open the Reclaim extension
2. Click Settings (gear icon)
3. Click "Clear All Data"
4. Confirm deletion

To also revoke Gmail access:
1. Go to https://myaccount.google.com/permissions
2. Find "Reclaim" in the list
3. Click "Remove Access"

---

## Children's Privacy

Reclaim is not intended for users under 13 years of age. We do not knowingly collect data from children.

---

## Changes to This Policy

We may update this privacy policy from time to time. We will notify you of significant changes through the extension or by email.

---

## Contact Us

For privacy questions or data requests:

- **Email**: privacy@[your-domain].com
- **GitHub**: https://github.com/jkoufopoulos/shopq-prototype/issues

---

## California Privacy Rights (CCPA)

California residents have additional rights:
- Right to know what data is collected
- Right to delete personal information
- Right to opt-out of data sales (we don't sell data)
- Right to non-discrimination for exercising privacy rights

---

## European Privacy Rights (GDPR)

EU residents have additional rights under GDPR:
- Right to access, rectification, and erasure
- Right to restrict processing
- Right to data portability
- Right to object to processing
- Right to lodge a complaint with a supervisory authority

**Legal Basis for Processing**: Legitimate interest (providing the service you requested)

**Data Controller**: [Your name/company]
**Contact**: privacy@[your-domain].com
