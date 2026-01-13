/**
 * Classification Cache Module
 *
 * Uses composite cache keys (sender|subject_signature) to prevent
 * per-sender generalization. Includes legacy fallback for migration.
 *
 * Depends on: modules/signatures.js (loaded via importScripts in background.js)
 */


/**
 * Check which emails are cached vs need classification
 * @param {Array} emails - Emails to check
 * @returns {Promise<{cached: Array, uncached: Array}>}
 */
async function checkCache(emails) {
  // TUNING MODE: Skip cache entirely to force fresh classifications
  if (CONFIG.TUNING_MODE) {
    console.log('🔧 TUNING MODE: Cache disabled - all emails will be freshly classified');
    return { cached: [], uncached: emails };
  }

  try {
    const result = await chrome.storage.local.get(CONFIG.KEYS.CACHE);
    const cache = result[CONFIG.KEYS.CACHE] || {};

    const cached = [];
    const uncached = [];
    const now = Date.now();
    const maxAge = CONFIG.CACHE_EXPIRY_MS || (24 * 60 * 60 * 1000);

    for (const email of emails) {
      // Phase 1: Use composite key (sender|subject_signature)
      const cacheKey = generateCacheKey(email.from, email.subject);
      let cacheEntry = cache[cacheKey];

      // Graceful migration: fallback to legacy sender-only key if composite key not found
      if (!cacheEntry) {
        const legacyKey = email.from.toLowerCase();
        cacheEntry = cache[legacyKey];

        if (cacheEntry) {
          console.log(`📦 Cache: Using legacy key for ${email.from}`);
        }
      }

      // Check if cached and not expired
      if (cacheEntry && (now - cacheEntry.timestamp) < maxAge) {
        // Return cached classification with email metadata
        cached.push({
          ...email,
          ...cacheEntry,
          from: email.from  // Preserve original casing
        });
      } else {
        uncached.push(email);
      }
    }

    return { cached, uncached };
  } catch (error) {
    console.error('❌ Cache check failed:', error);
    // On error, treat all as uncached
    return { cached: [], uncached: emails };
  }
}

/**
 * Update cache with new classifications
 * @param {Array} classifications - New classifications to cache (must include subject field)
 */
async function updateCache(classifications) {
  try {
    const result = await chrome.storage.local.get(CONFIG.KEYS.CACHE);
    const cache = result[CONFIG.KEYS.CACHE] || {};

    const now = Date.now();

    // Phase 1: Add new classifications using composite key (sender|subject_signature)
    for (const item of classifications) {
      const cacheKey = generateCacheKey(item.from, item.subject);

      cache[cacheKey] = {
        labels: item.labels,
        labels_conf: item.labels_conf,
        type: item.type,
        type_conf: item.type_conf,
        attention: item.attention,
        attention_conf: item.attention_conf,
        importance: item.importance,  // Used by digest for section assignment
        importance_conf: item.importance_conf,
        client_label: item.client_label,  // Used by mapper and digest
        relationship: item.relationship,
        relationship_conf: item.relationship_conf,
        decider: item.decider,
        reason: item.reason,
        propose_rule: item.propose_rule,
        timestamp: now
      };
    }

    // Clean old entries (older than 24 hours)
    const maxAge = CONFIG.CACHE_EXPIRY_MS || (24 * 60 * 60 * 1000);

    for (const [key, entry] of Object.entries(cache)) {
      if (now - entry.timestamp > maxAge) {
        delete cache[key];
      }
    }

    // Limit cache size
    const entries = Object.entries(cache);
    if (entries.length > CONFIG.CACHE_MAX_ENTRIES) {
      // Sort by timestamp, keep newest
      entries.sort((a, b) => b[1].timestamp - a[1].timestamp);
      const limitedCache = {};
      for (let i = 0; i < CONFIG.CACHE_MAX_ENTRIES; i++) {
        limitedCache[entries[i][0]] = entries[i][1];
      }
      await chrome.storage.local.set({ [CONFIG.KEYS.CACHE]: limitedCache });
    } else {
      await chrome.storage.local.set({ [CONFIG.KEYS.CACHE]: cache });
    }

    console.log(`💾 Cache updated: ${Object.keys(cache).length} entries`);
  } catch (error) {
    console.error('⚠️ Cache update failed (non-critical):', error);
  }
}

/**
 * Clear all cached classifications
 * Useful when tuning classifier or testing changes
 * @returns {Promise<void>}
 */
async function clearCache() {
  try {
    await chrome.storage.local.remove(CONFIG.KEYS.CACHE);
    console.log('✅ Classification cache cleared');
  } catch (error) {
    console.error('❌ Failed to clear cache:', error);
  }
}

/**
 * Get cache statistics for debugging
 * @returns {Promise<Object>} Cache stats
 */
async function getCacheStats() {
  try {
    const result = await chrome.storage.local.get(CONFIG.KEYS.CACHE);
    const cache = result[CONFIG.KEYS.CACHE] || {};
    const entries = Object.entries(cache);
    const now = Date.now();
    const maxAge = CONFIG.CACHE_EXPIRY_MS || (24 * 60 * 60 * 1000);

    const stats = {
      total: entries.length,
      fresh: 0,
      stale: 0,
      oldestTimestamp: null,
      newestTimestamp: null
    };

    entries.forEach(([key, entry]) => {
      const age = now - entry.timestamp;
      if (age < maxAge) {
        stats.fresh++;
      } else {
        stats.stale++;
      }

      if (!stats.oldestTimestamp || entry.timestamp < stats.oldestTimestamp) {
        stats.oldestTimestamp = entry.timestamp;
      }
      if (!stats.newestTimestamp || entry.timestamp > stats.newestTimestamp) {
        stats.newestTimestamp = entry.timestamp;
      }
    });

    if (stats.oldestTimestamp) {
      stats.oldestAge = Math.floor((now - stats.oldestTimestamp) / 1000 / 60 / 60); // hours
      stats.newestAge = Math.floor((now - stats.newestTimestamp) / 1000 / 60); // minutes
    }

    return stats;
  } catch (error) {
    console.error('❌ Failed to get cache stats:', error);
    return { error: error.message };
  }
}
