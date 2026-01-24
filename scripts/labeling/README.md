# Email Labeling Workflow for ShopQ

This workflow lets you hand-label emails from your Gmail as purchase-related or not, then manually construct ReturnCard entities from the labeled purchases.

## Prerequisites

1. **Gmail OAuth credentials**: You need `credentials/credentials.json` from Google Cloud Console with Gmail API enabled.

2. **Python dependencies**: Make sure you have the project dependencies installed:
   ```bash
   uv sync
   ```

## Workflow Steps

### Step 1: Fetch Emails

Fetch emails from your Gmail for the last 30 days:

```bash
cd /Users/justinkoufopoulos/Projects/shopq-prototype
uv run python scripts/labeling/fetch_emails.py
```

Options:
- `--days 30` - Number of days to fetch (default: 30)
- `--max-results 500` - Maximum emails to fetch (default: 500)
- `--output FILE` - Custom output path

This will:
1. Open a browser for Gmail OAuth (first time only)
2. Fetch all emails from the specified period
3. Save to `data/labeling/emails_to_label.json`

### Step 2: Label Emails

Interactively label each email:

```bash
uv run python scripts/labeling/label_emails.py
```

Options:
- `--input FILE` - Input JSON file
- `--output FILE` - Output JSON file
- `--no-resume` - Start fresh (don't resume)

For each email, choose:
- **[P] PURCHASE** - Returnable physical product order/delivery email
- **[N] NOT_PURCHASE** - Service, subscription, digital, marketing, etc.
- **[S] SKIP** - Not relevant at all
- **[V] VIEW_FULL** - View full email body
- **[Q] QUIT** - Save and exit

For PURCHASE emails, you can optionally extract:
- Merchant name
- Item description
- Order number
- Amount
- Order date
- Delivery date
- Return-by date (if explicitly mentioned)

Progress is saved after each email, so you can quit and resume anytime.

### Step 3: Create ReturnCards

Create ReturnCard entities from labeled purchases:

```bash
uv run python scripts/labeling/create_entities.py
```

Options:
- `--input FILE` - Input JSON with labeled purchases
- `--output FILE` - Output JSON for ReturnCards
- `--db` - Also save to database
- `--export-only` - Skip interactive review
- `--user-id ID` - User ID for cards (default: labeling_user)

This will:
1. Load labeled purchases
2. Apply merchant return rules to compute return-by dates
3. Let you review/edit each before creating
4. Export ReturnCards to JSON
5. Optionally save to database

## Output Files

- `data/labeling/emails_to_label.json` - Raw emails from Gmail
- `data/labeling/labeled_emails.json` - Labels + extracted purchase info
- `data/labeling/return_cards.json` - Final ReturnCard entities

## Example Workflow

```bash
# 1. Fetch last 30 days of emails
uv run python scripts/labeling/fetch_emails.py --days 30

# 2. Label emails (can quit and resume)
uv run python scripts/labeling/label_emails.py

# 3. Create ReturnCards and save to database
uv run python scripts/labeling/create_entities.py --db
```

## Tips

- **Skip obviously non-purchase emails** - Marketing, newsletters, account notifications
- **Focus on order confirmations and delivery notifications** - These have the most useful data
- **Note explicit return-by dates** - Some merchants (like Amazon) include these in emails
- **Extract order numbers when visible** - Helps with deduplication
- **Use VIEW_FULL for ambiguous cases** - Sometimes the body has important details

## Labeling Guidelines

### PURCHASE (returnable physical goods)
- Order confirmations for physical products
- Shipping notifications
- Delivery confirmations
- Return reminders

### NOT_PURCHASE (not returnable)
- Digital purchases (ebooks, software, games)
- Subscriptions (Netflix, Spotify, etc.)
- Services (Uber, DoorDash, cleaning, etc.)
- Event tickets
- Gift cards
- Donations
- Bill payments
- Promotional emails (even from retailers)

### SKIP
- Newsletters with no purchase
- Account notifications (password reset, etc.)
- Marketing without purchase
- Personal emails
