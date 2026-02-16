# Chrome Web Store Pre-Submission Checklist

Everything needed before uploading to the Chrome Web Store.

---

## Code Readiness (all passing)

- [x] Manifest V3 compliant
- [x] `minimum_chrome_version`: "116"
- [x] Icons: 16, 48, 128px present and referenced in manifest
- [x] CSP configured (`script-src 'self'`, no `unsafe-eval`)
- [x] No remote code loading (no `eval()`, no fetched scripts)
- [x] No `unlimitedStorage` permission
- [x] XSS prevention: `escapeHtml()` on all user-controlled content
- [x] Message sender validation (`isTrustedSender()`)
- [x] Rate limiting on message handlers
- [x] Onboarding page on first install
- [x] Privacy policy in repo (`PRIVACY_POLICY.md`) and hosted (`docs/index.html`)

---

## GCP / OAuth Setup

- [ ] **OAuth consent screen in production mode**
  - Go to [GCP Console → APIs & Services → OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent?project=shopq-467118)
  - Must be "In production" (not "Testing") — CWS reviewers won't be in your test users list
  - Verify scopes listed: `gmail.readonly`, `userinfo.profile`

- [ ] **OAuth client ID matches**
  - Extension manifest `oauth2.client_id`: `142227390702-a1v5icgnl8sjc1e7t87gono0ebl55q6v.apps.googleusercontent.com`
  - This must be a "Chrome App" type client in GCP
  - After CWS assigns a stable extension ID, update GCP authorized origins

- [ ] **Backend API accessible**
  ```bash
  curl -s https://reclaim-api-142227390702.us-central1.run.app/health
  ```
  Must return 200 during CWS review period. Cloud Run cold starts are OK.

---

## Store Listing Assets (required)

- [ ] **Short description** (up to 132 chars)
  > Tracks return deadlines on your online purchases so you never miss a return window.

- [ ] **Detailed description** (up to 4000 chars)
  - What it does (scan Gmail for purchases, extract deadlines, track returns)
  - How it works (3 bullets: scan, extract, track)
  - Privacy highlights (local storage, PII redaction, no data retention)
  - Adapt from `README.md`

- [ ] **Screenshots** (1280x800 or 640x400, PNG or JPG, 2-5 images)
  1. Gmail sidebar showing return cards list
  2. Return card detail view with deadline and evidence
  3. Onboarding page
  4. (Optional) Popup showing active returns count
  5. (Optional) Expiring-soon notification

- [ ] **Promotional tile** (440x280, PNG or JPG)
  - Marquee image for the store listing

- [ ] **Category**: Productivity

- [ ] **Language**: English

---

## Privacy & Compliance

- [ ] **Privacy policy URL** — publicly accessible
  - GitHub Pages: verify `docs/index.html` is deployed and reachable
  - URL to enter in CWS dashboard: `https://<your-github-pages-url>/`

- [ ] **CWS Privacy Practices form** — declare what data you access:
  | Data Type | Collected? | Usage |
  |---|---|---|
  | Email content | Yes (read-only) | Scanned for purchase info, not stored server-side |
  | Authentication info | Yes | Google OAuth for Gmail access |
  | Personal info | No | PII redacted before AI processing |
  | Web history | No | Only Gmail, not browsing history |
  | Financial info | Partially | Order amounts extracted, stored locally only |

- [ ] **Single purpose description** — CWS requires a clear single purpose:
  > "Track return windows on online purchases detected in Gmail"

- [ ] **Permissions justification** — CWS may ask why you need each permission:
  | Permission | Justification |
  |---|---|
  | `identity` | OAuth authentication with Google to read Gmail |
  | `storage` | Store return card data locally in the browser |
  | `tabs` | Detect when Gmail is open to trigger scans |
  | `scripting` | Inject content script for InboxSDK sidebar |
  | `notifications` | Alert users about expiring return deadlines |
  | `alarms` | Schedule periodic background scans |
  | Host: `mail.google.com` | Read purchase emails from Gmail |
  | Host: `googleapis.com` | Gmail API and OAuth token endpoints |
  | Host: `reclaim-api-...` | Backend API for AI extraction |
  | Host: `inboxsdk.com` | InboxSDK library for Gmail sidebar |

---

## Build & Package

```bash
cd extension
npm run build
# Create the zip for upload (exclude dev files)
zip -r ../reclaim-extension.zip . \
  -x "node_modules/*" \
  -x "src/*" \
  -x ".gitignore" \
  -x "package.json" \
  -x "package-lock.json" \
  -x "webpack.config.js" \
  -x "eslint.config.mjs" \
  -x "tests/*"
```

- [ ] Verify zip contains: `manifest.json`, `background.js`, `popup.html`, `popup.js`, `onboarding.html`, `onboarding.js`, `returns-sidebar.html`, `returns-sidebar-inner.js`, `theme.css`, `theme-sync.js`, `pageWorld.js`, `styles.css`, `dist/`, `icons/`, `modules/`
- [ ] Verify zip does NOT contain: `node_modules/`, `src/`, test files, config files

---

## Submission Steps

1. Go to [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
2. Pay one-time $5 developer fee (if not already registered)
3. Click "New Item" → upload `reclaim-extension.zip`
4. Fill in store listing (description, screenshots, category)
5. Fill in privacy practices form
6. Enter privacy policy URL
7. Submit for review

**Review timeline**: Typically 1-3 business days. Extensions requesting `gmail.readonly` may get extra scrutiny.

---

## Post-Submission

- [ ] Monitor developer dashboard for review feedback
- [ ] If rejected, check email for specific policy violations
- [ ] After approval, verify the published listing looks correct
- [ ] Test installing from the CWS listing (clean Chrome profile)
- [ ] Update `homepage_url` in manifest to point to CWS listing URL
