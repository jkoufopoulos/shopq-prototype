# How to Create a Google Cloud API Key (Step-by-Step)

## 🎯 Goal
Create an API key that starts with `AIza` (NOT `AQ.`)

---

## 📍 Step-by-Step Instructions

### Step 1: Go to the Credentials Page
Open this link in your browser:
```
https://console.cloud.google.com/apis/credentials?project=mailq-467118
```

### Step 2: Look at the Top of the Page
You should see a blue button that says **"+ CREATE CREDENTIALS"**

**IMPORTANT**: This is a DROPDOWN button with multiple options!

### Step 3: Click the Dropdown
When you click **"+ CREATE CREDENTIALS"**, you'll see a menu with options like:
- API key ⭐ **← SELECT THIS ONE**
- OAuth client ID
- Service account key
- Help me choose

### Step 4: Select "API key"
Click on **"API key"** (the first option)

### Step 5: Copy the Key Immediately
A popup appears with your new API key:
```
┌─────────────────────────────────────────────┐
│  API key created                            │
│                                             │
│  Your API key:                              │
│  AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz1234567   │
│                                             │
│  [COPY]  [RESTRICT KEY]  [CLOSE]           │
└─────────────────────────────────────────────┘
```

**Click "COPY" to copy the key to your clipboard**

### Step 6: Verify the Key Format
The key you copied should:
- ✅ Start with `AIza`
- ✅ Be about 39 characters long
- ✅ Have NO dots (`.`) in the middle
- ✅ Contain only letters, numbers, hyphens, and underscores

**Examples:**
- ✅ CORRECT: `AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz1234567`
- ✅ CORRECT: `AIzaSyCcRe425WSqz6nRNxF1pPISbWKK0607hNA` (the old one)
- ❌ WRONG: `AQ.Ab8RN6I5aYzm-zF5uNNeKrz8J1tQc1fVb6XNG-PIgDUlcvdd_Q`

### Step 7: (Optional) Restrict the Key
1. After copying, click **"RESTRICT KEY"**
2. Scroll down to "API restrictions"
3. Select **"Restrict key"**
4. Check the box for: ✅ **Generative Language API**
5. Click **"Save"** at the bottom

---

## 🚨 Common Mistakes

### Mistake 1: Creating OAuth Client ID Instead
**Wrong button clicked:**
- + CREATE CREDENTIALS → **OAuth client ID** ❌

**What you get:**
- A "client ID" ending in `.apps.googleusercontent.com`
- NOT what we need for Gemini API

**Correct button:**
- + CREATE CREDENTIALS → **API key** ✅

---

### Mistake 2: Copying the Wrong Value
After creating the API key, the page shows multiple values:

```
Name: API key 1
Type: API key
Created: Nov 12, 2024
Key: AIzaSy... ← COPY THIS
Key ID: AQ.Ab8... ← NOT THIS!
```

**Copy the "Key" field, NOT the "Key ID" field!**

---

### Mistake 3: Using Application Default Credentials
If you ran `gcloud auth application-default login`, that creates a different type of credential (JSON file, not API key).

**That's different from what we need here.**

---

## 🔍 Troubleshooting

### "I don't see the CREATE CREDENTIALS button"
- Make sure you're on the right page: https://console.cloud.google.com/apis/credentials?project=mailq-467118
- Make sure you're logged into the Google account that owns the project
- Check that you have "Editor" or "Owner" role on the project

### "The key still starts with AQ."
You copied the **Key ID** instead of the **Key**.

Go back to: https://console.cloud.google.com/apis/credentials?project=mailq-467118

Find the API key in the list, and look at the full "Key" column (you may need to click "Show key").

### "I created the key but lost it"
Go back to: https://console.cloud.google.com/apis/credentials?project=mailq-467118

Find your API key in the list of credentials. Click on it to view details, then click "Show key" to reveal it again.

---

## ✅ Success Criteria

You know you did it right when:
1. ✅ The key starts with `AIza`
2. ✅ The key is 39 characters long
3. ✅ You can see the key listed at: https://console.cloud.google.com/apis/credentials?project=mailq-467118

---

## 📞 If You're Still Stuck

If you're still having trouble, try this:

1. Take a screenshot of the Google Cloud Console credentials page
2. Show me what buttons you see
3. Or try using `gcloud` CLI instead:

```bash
gcloud auth login
gcloud config set project mailq-467118

# List existing API keys
gcloud alpha services api-keys list

# Create new API key
gcloud alpha services api-keys create \
  --display-name="MailQ Gemini API Key" \
  --api-target=service=generativelanguage.googleapis.com
```

This command will output the new API key (starting with `AIza`).

---

## 🎯 Final Note

The key format `AQ.Ab8RN6...` is NOT a Google Cloud API key. It's something else (possibly a Key ID, OAuth token, or access token).

You need to find and copy the actual API key that starts with `AIza`.
