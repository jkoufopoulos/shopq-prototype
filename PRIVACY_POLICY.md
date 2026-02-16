# Privacy Policy for Reclaim

**Last Updated:** February 15, 2026

Reclaim ("we", "our", or "the extension") is a browser extension that helps you track return windows on online purchases. This privacy policy explains what data we collect, how we use it, and your rights.

## Summary

- We read your Gmail to find order confirmation emails
- We extract order details (merchant, items, dates) to calculate return deadlines
- **All order data is stored locally in your browser** — nothing is saved on any server
- Email content from purchase-related emails is sent to Google's Gemini AI for analysis. Content is processed in real-time and not stored on any server.
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
- Your Google account email address (for authentication)
- No passwords are ever collected or stored

### Usage Data
- Extension feature usage (anonymized)
- Error logs for debugging (no personal data)

---

## How We Use Your Data

1. **Calculate return deadlines** — We analyze order emails to determine when return windows expire
2. **Send reminders** — We notify you before return deadlines pass
3. **Improve the service** — Anonymized usage data helps us fix bugs and add features

We do **NOT**:
- Sell your data to third parties
- Use your data for advertising
- Share your data with marketers
- Train AI models on your personal data

---

## Where Data Is Stored

### On Your Device (Primary Storage)
All extracted order data — return cards, merchant details, deadlines, and order metadata — is stored locally in your browser using `chrome.storage.local`. This data never leaves your device except during email processing (described below).

### Transient Server Processing
When scanning emails, the extension sends email content to our backend server for AI-powered extraction. The server:
- Receives email content, processes it through the extraction pipeline, and returns structured order data
- **Does not store any email content or order data** — processing is entirely transient
- Runs on Google Cloud Run (US region) with TLS 1.3 encryption in transit

### Third-Party Services

| Service | Purpose | Data Shared | Retention |
|---------|---------|-------------|-----------|
| Google Gmail API | Read order emails | Email content (read-only access) | None — read in real-time |
| Google Gemini AI | Extract order details from email text | Email text sent for processing | None — processed transiently, not stored |
| Google Cloud Run | Host extraction API | Email text passed through for processing | None — stateless, no data persisted |

---

## Data Retention

- **Local data**: Kept in your browser until you clear it or uninstall the extension
- **Server-side**: No data is retained — all processing is transient
- **Account deletion**: Clear all local data from Settings > Clear Data, then revoke Gmail access

---

## Your Rights

You have the right to:

1. **Access your data** — View all data we have about you in the extension sidebar
2. **Delete your data** — Remove all stored data from Settings > Clear Data
3. **Revoke access** — Disconnect Gmail access from your Google Account settings

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

We may update this privacy policy from time to time. We will notify you of significant changes through the extension.

---

## Contact Us

For privacy questions or data requests:

- **GitHub Issues**: https://github.com/jkoufopoulos/shopq-prototype/issues

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

**Data Controller**: Justin Koufopoulos
**Contact**: https://github.com/jkoufopoulos/shopq-prototype/issues
