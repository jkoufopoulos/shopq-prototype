# Google Credentials Setup Guide - Complete Rebuild

You deleted all your Google credentials. Here's how to recreate **everything** you need for MailQ.

## 🎯 What You Need to Create

1. **Google Cloud API Key** - For Gemini AI classification
2. **OAuth 2.0 Client ID (Chrome Extension)** - For extension Gmail access
3. **OAuth 2.0 Client ID (Desktop App)** - For backend scripts

---

## 📋 Step-by-Step Instructions

### Prerequisites
- Google Cloud Project: `mailq-467118`
- Access to: https://console.cloud.google.com/

---

## PART 1: Enable Required APIs

### Step 1: Go to APIs & Services
1. Navigate to: https://console.cloud.google.com/apis/library?project=mailq-467118
2. Enable these APIs if not already enabled:
   - **Gmail API** (for reading/organizing emails)
   - **Generative Language API** (for Gemini)
   - **Vertex AI API** (for Gemini Pro)

---

## PART 2: Create Google Cloud API Key

### Step 2: Create API Key
1. Go to: https://console.cloud.google.com/apis/credentials?project=mailq-467118
2. Click **"Create Credentials"** → **"API key"**
3. A popup shows your new API key → **COPY IT NOW**
4. Click **"Restrict Key"** (recommended)

### Step 3: Restrict the API Key (Recommended)
1. Under "API restrictions":
   - Select **"Restrict key"**
   - Check: ✅ **Generative Language API**
   - Check: ✅ **Vertex AI API**
2. Click **"Save"**

### Step 4: Save to .env
```bash
# Add to /Users/justinkoufopoulos/Projects/mailq-prototype/.env
GOOGLE_API_KEY=AIzaSy...your-new-key-here...
```

✅ **Part 1 Complete!** API Key created.

---

## PART 3: Create OAuth 2.0 Consent Screen

**NOTE: You only need to do this ONCE, even if you create multiple OAuth clients.**

### Step 5: Configure OAuth Consent Screen
1. Go to: https://console.cloud.google.com/apis/credentials/consent?project=mailq-467118
2. Choose **"External"** (if asked) → Click **"Create"**
3. Fill in:
   - **App name**: `MailQ`
   - **User support email**: Your email
   - **Developer contact**: Your email
4. Click **"Save and Continue"**

### Step 6: Add Scopes
1. Click **"Add or Remove Scopes"**
2. Filter and select:
   - ✅ `.../auth/gmail.modify` (Read, compose, send, and permanently delete email)
   - ✅ `.../auth/gmail.labels` (Manage mailbox labels)
3. Click **"Update"** → **"Save and Continue"**

### Step 7: Add Test Users (if app is in Testing mode)
1. Click **"Add Users"**
2. Add your Gmail address
3. Click **"Save and Continue"**

### Step 8: Review and Submit
1. Review settings
2. Click **"Back to Dashboard"**

✅ **Part 2 Complete!** OAuth consent screen configured.

---

## PART 4: Create OAuth Client ID for Chrome Extension

### Step 9: Create Chrome Extension OAuth Client
1. Go to: https://console.cloud.google.com/apis/credentials?project=mailq-467118
2. Click **"Create Credentials"** → **"OAuth client ID"**
3. Application type: **"Chrome app"**
4. Name: `MailQ Chrome Extension`
5. Application ID:
   - If you have the extension ID already: Enter it
   - If you don't: Enter a placeholder like `abcdefghijklmnopqrstuvwxyz123456`
   - (You'll update this later after publishing the extension)
6. Click **"Create"**
7. **COPY the Client ID** (looks like: `488078904670-xxxxxx.apps.googleusercontent.com`)

### Step 10: Update manifest.json
```bash
# Open extension/manifest.json and update line 46:
"client_id": "YOUR-NEW-CLIENT-ID-HERE.apps.googleusercontent.com"
```

✅ **Part 3 Complete!** Chrome Extension OAuth configured.

---

## PART 5: Create OAuth Client ID for Backend Scripts

### Step 11: Create Desktop App OAuth Client
1. Go to: https://console.cloud.google.com/apis/credentials?project=mailq-467118
2. Click **"Create Credentials"** → **"OAuth client ID"**
3. Application type: **"Desktop app"**
4. Name: `MailQ Backend Scripts`
5. Click **"Create"**
6. **DOWNLOAD JSON** (click the download icon)
7. A file named `client_secret_*.json` downloads

### Step 12: Save credentials.json
```bash
# Move the downloaded file:
mv ~/Downloads/client_secret_*.json /Users/justinkoufopoulos/Projects/mailq-prototype/credentials/credentials.json
```

✅ **Part 4 Complete!** Backend OAuth configured.

---

## 📝 Final Checklist

After completing all steps, verify:

- [ ] `.env` has `GOOGLE_API_KEY=AIzaSy...`
- [ ] `extension/manifest.json` has new `client_id` (line 46)
- [ ] `credentials/credentials.json` exists with downloaded OAuth credentials
- [ ] All credential files are gitignored:
  ```bash
  git check-ignore .env credentials/credentials.json
  # Should show both files are ignored
  ```

---

## 🧪 Test Your Credentials

### Test 1: API Key
```bash
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$(grep GOOGLE_API_KEY .env | cut -d= -f2)"
# Should return list of available models
```

### Test 2: Extension OAuth
1. Load extension in Chrome: `chrome://extensions`
2. Enable Developer Mode
3. Click "Load unpacked" → Select `extension/` folder
4. Click the MailQ extension icon
5. It should prompt for Gmail permissions

### Test 3: Backend Scripts OAuth
```bash
# Run a test script (it will open browser for auth)
cd /Users/justinkoufopoulos/Projects/mailq-prototype
python scripts/pull_gmail_golden_set.py
# Browser opens → Click "Allow" → Script runs
```

---

## 🔒 Security Verification

Run this to ensure secrets are NOT committed:

```bash
# Check gitignore
git check-ignore -v .env credentials/credentials.json

# Check git status (these should NOT appear)
git status | grep -E "\.env|credentials\.json"

# Scan for hardcoded keys
grep -r "AIza" --exclude-dir=.git . | grep -v ".env.example" | grep -v "SECURITY" | grep -v "GOOGLE_CREDENTIALS"
```

---

## 📚 Reference

- Google Cloud Console: https://console.cloud.google.com/apis/credentials?project=mailq-467118
- OAuth 2.0 Guide: https://developers.google.com/identity/protocols/oauth2
- Gmail API Scopes: https://developers.google.com/gmail/api/auth/scopes

---

## 🆘 Troubleshooting

### "API key not valid"
- Verify API is enabled: https://console.cloud.google.com/apis/library?project=mailq-467118
- Check API restrictions on key

### "Access blocked: This app's request is invalid"
- OAuth consent screen not configured properly
- App still in "Testing" mode and user not added as test user
- Scopes not added to consent screen

### "The origin is not allowed"
- Chrome Extension Client ID doesn't match Application ID
- Need to publish extension and update Client ID

### "credentials.json not found"
- File not in correct location: `/Users/justinkoufopoulos/Projects/mailq-prototype/credentials/credentials.json`
- Download the Desktop App OAuth client credentials

---

## ✅ You're Done!

Once all three credentials are created and saved:
1. API Key → `.env`
2. Chrome Extension Client ID → `extension/manifest.json`
3. Backend OAuth Credentials → `credentials/credentials.json`

Your MailQ app is ready to run!
