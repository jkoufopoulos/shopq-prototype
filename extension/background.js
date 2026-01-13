/**
 * ShopQ Return Watch Background Service Worker
 * Handles purchase email scanning and return tracking
 */

// InboxSDK MV3 pageWorld injection handler
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'inboxsdk__injectPageWorld' && sender.tab) {
    if (chrome.scripting) {
      let documentIds;
      let frameIds;
      if (sender.documentId) {
        documentIds = [sender.documentId];
      } else {
        frameIds = [sender.frameId];
      }
      chrome.scripting.executeScript({
        target: { tabId: sender.tab.id, documentIds, frameIds },
        world: 'MAIN',
        files: ['pageWorld.js'],
      });
      sendResponse(true);
    } else {
      sendResponse(false);
    }
    return true;
  }
});

// Load dependencies - only modules that exist for Return Watch
importScripts(
  'modules/shared/config.js',
  'modules/shared/utils.js',
  'modules/gmail/auth.js',
  'modules/returns/api.js'
);

console.log(`🛒 ShopQ Return Watch: Background service worker loaded v${CONFIG.VERSION}`);

/**
 * Scan recent emails for returnable purchases
 * Uses Gmail search to find potential purchase emails, then processes each
 * through the backend's extraction pipeline.
 */
async function scanForPurchases() {
  console.log('🛒 Starting purchase email scan...');

  try {
    const token = await getAuthToken();
    if (!token) {
      throw new Error('No auth token available');
    }

    // Get user ID from storage
    const stored = await chrome.storage.local.get('userId');
    const userId = stored.userId || 'default_user';

    // Search for recent emails that might be purchases
    const searchQueries = [
      'subject:(order confirmation) newer_than:30d',
      'subject:(your order) newer_than:30d',
      'subject:(order shipped) newer_than:30d',
      'subject:(delivery) newer_than:30d',
      'from:(amazon) subject:(order) newer_than:30d',
      'from:(target) subject:(order) newer_than:30d',
      'from:(walmart) subject:(order) newer_than:30d',
    ];

    const processedIds = new Set();
    let totalProcessed = 0;
    let totalReturnable = 0;

    for (const query of searchQueries) {
      try {
        // Search for messages matching query
        const searchResponse = await fetch(
          `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${encodeURIComponent(query)}&maxResults=10`,
          {
            headers: { 'Authorization': `Bearer ${token}` }
          }
        );

        if (!searchResponse.ok) {
          console.warn(`⚠️ Search failed for query "${query}":`, searchResponse.status);
          continue;
        }

        const searchData = await searchResponse.json();
        const messages = searchData.messages || [];

        console.log(`📧 Found ${messages.length} messages for query: ${query.substring(0, 30)}...`);

        // Process each message
        for (const msg of messages) {
          if (processedIds.has(msg.id)) {
            continue; // Skip duplicates
          }
          processedIds.add(msg.id);

          try {
            // Get full message details
            const msgResponse = await fetch(
              `https://gmail.googleapis.com/gmail/v1/users/me/messages/${msg.id}?format=full`,
              {
                headers: { 'Authorization': `Bearer ${token}` }
              }
            );

            if (!msgResponse.ok) {
              console.warn(`⚠️ Failed to fetch message ${msg.id}`);
              continue;
            }

            const msgData = await msgResponse.json();

            // Extract email details
            const headers = msgData.payload?.headers || [];
            const getHeader = (name) => headers.find(h => h.name.toLowerCase() === name.toLowerCase())?.value || '';

            const from = getHeader('From');
            const subject = getHeader('Subject');
            const body = extractBodyText(msgData.payload);

            // Send to backend extraction pipeline
            const apiUrl = CONFIG.SHOPQ_API_URL || CONFIG.API_BASE_URL;
            const processResponse = await fetch(`${apiUrl}/api/returns/process`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                user_id: userId,
                email_id: msg.id,
                from_address: from,
                subject: subject,
                body: body.substring(0, 5000), // Limit body size
              })
            });

            if (processResponse.ok) {
              const result = await processResponse.json();
              totalProcessed++;

              if (result.success) {
                totalReturnable++;
                console.log(`✅ Returnable purchase found: ${result.card?.merchant} - ${result.card?.item_summary}`);
              } else {
                console.log(`⏭️ Not returnable: ${subject.substring(0, 40)}... (${result.rejection_reason})`);
              }
            }

          } catch (msgError) {
            console.warn(`⚠️ Error processing message ${msg.id}:`, msgError.message);
          }
        }

      } catch (queryError) {
        console.warn(`⚠️ Error with query "${query}":`, queryError.message);
      }
    }

    console.log(`📊 Scan complete: ${totalProcessed} emails processed, ${totalReturnable} returnable purchases found`);

    return {
      success: true,
      processedCount: totalProcessed,
      returnableCount: totalReturnable,
    };

  } catch (error) {
    console.error('❌ Scan for purchases failed:', error);
    throw error;
  }
}

/**
 * Extract plain text body from Gmail message payload
 */
function extractBodyText(payload) {
  if (!payload) return '';

  // Check for plain text part
  if (payload.mimeType === 'text/plain' && payload.body?.data) {
    return decodeBase64(payload.body.data);
  }

  // Check for HTML part (will strip tags)
  if (payload.mimeType === 'text/html' && payload.body?.data) {
    const html = decodeBase64(payload.body.data);
    return stripHtmlTags(html);
  }

  // Handle multipart messages
  if (payload.parts) {
    for (const part of payload.parts) {
      const text = extractBodyText(part);
      if (text) return text;
    }
  }

  return '';
}

/**
 * Decode base64url encoded string
 */
function decodeBase64(data) {
  try {
    // Gmail uses URL-safe base64
    const base64 = data.replace(/-/g, '+').replace(/_/g, '/');
    return decodeURIComponent(escape(atob(base64)));
  } catch {
    return '';
  }
}

/**
 * Strip HTML tags from text
 */
function stripHtmlTags(html) {
  return html
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Handle messages from content scripts and popup
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      if (message.type === 'SCAN_FOR_PURCHASES') {
        console.log('🛒 Scanning for purchase emails...');
        try {
          const result = await scanForPurchases();
          console.log('📊 Scan result:', JSON.stringify(result));
          sendResponse(result);
        } catch (error) {
          console.error('❌ Scan failed:', error);
          sendResponse({ success: false, error: error.message });
        }
      }
      else if (message.type === 'CHECK_AUTH') {
        try {
          const token = await getAuthToken();
          sendResponse({ success: true, hasToken: !!token });
        } catch (error) {
          sendResponse({ success: false, error: error.message });
        }
      }
      else if (message.type === 'SHOW_NOTIFICATION') {
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icons/icon48.png',
          title: message.title || 'ShopQ Return Watch',
          message: message.message,
          priority: 2
        });
        sendResponse({ success: true });
      }
    } catch (error) {
      console.error('❌ Message handler error:', error);
      sendResponse({ success: false, error: error.message });
    }
  })();

  return true; // Keep message channel open for async response
});

/**
 * Handle extension install/update
 */
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('🎉 ShopQ Return Watch installed');
    // Set default user ID
    chrome.storage.local.set({ userId: 'default_user' });
  } else if (details.reason === 'update') {
    console.log(`📦 ShopQ Return Watch updated to v${CONFIG.VERSION}`);
  }
});

/**
 * Re-inject content script on navigation (for SPA Gmail)
 */
chrome.webNavigation.onCompleted.addListener(async (details) => {
  if (details.url?.includes('mail.google.com')) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId: details.tabId },
        files: ['dist/content.bundle.js']
      });
      console.log(`✅ Content script injected into Gmail tab ${details.tabId}`);
    } catch (error) {
      // Ignore errors (content script may already be loaded)
    }
  }
});
