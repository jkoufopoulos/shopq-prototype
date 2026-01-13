/**
 * Console Logger for MailQ Extension
 *
 * Simple, flow-focused logging for debugging.
 * One log per major event, with context that matters.
 *
 * Usage:
 *   import { log } from './console-logger.js';
 *
 *   log.startup({ version: '1.0.13', rawDigest: true, testMode: true });
 *   log.organize.start(12);
 *   log.organize.done({ receipts: 3, events: 2, newsletters: 7 });
 *   log.digest.fetch(44, true);
 *   log.digest.done(2960);
 *   log.error('API', 'Failed to fetch', error);
 */

const log = {
  /**
   * Startup: Extension loaded with config
   */
  startup({ version, rawDigest = false, testMode = false, cacheSize = 0 }) {
    const flags = [];
    if (rawDigest) flags.push('raw_digest');
    if (testMode) flags.push('test_mode');
    const flagStr = flags.length ? ` (${flags.join(', ')})` : '';
    console.log(`🚀 MailQ v${version}${flagStr}`);
    if (cacheSize > 0) {
      console.log(`   └─ ${cacheSize} cached threads`);
    }
  },

  /**
   * Config: Sync complete
   */
  configReady(testMode = false) {
    if (testMode) {
      console.log('⚙️  Config ready (test mode)');
    }
  },

  /**
   * Backend connectivity
   */
  backend: {
    ok(url) {
      // Extract just the host for cleaner logs
      const host = url ? new URL(url).host : 'unknown';
      console.log(`🌐 Backend: ${host}`);
    },
    error(url, error) {
      const host = url ? new URL(url).host : 'unknown';
      console.error(`❌ Backend unreachable: ${host}`, error?.message || error);
    }
  },

  /**
   * Organize flow
   */
  organize: {
    start(emailCount) {
      console.log(`📧 Organizing ${emailCount} emails...`);
    },
    done(results) {
      // results: { receipts: 3, events: 2, newsletters: 7 } or just count
      if (typeof results === 'number') {
        console.log(`✅ Classified ${results} emails`);
      } else {
        const parts = Object.entries(results)
          .filter(([_, count]) => count > 0)
          .map(([type, count]) => `${count} ${type}`)
          .join(', ');
        console.log(`✅ Classified → ${parts || 'no emails'}`);
      }
    },
    skip(reason) {
      console.log(`⏸️  Organize skipped: ${reason}`);
    },
    error(error) {
      console.error('❌ Organize failed:', error?.message || error);
    }
  },

  /**
   * Digest flow
   */
  digest: {
    fetch(emailCount, rawDigest = false) {
      const mode = rawDigest ? ' (raw LLM)' : '';
      console.log(`📝 Fetching digest${mode}...`);
    },
    done(charCount) {
      console.log(`✅ Digest loaded (${charCount} chars)`);
    },
    empty() {
      console.log('📭 Digest: no emails to summarize');
    },
    elevated(count) {
      // Log noise elevation results (keywords or LLM rescued emails)
      console.log(`🔺 Elevated: ${count} email${count !== 1 ? 's' : ''} rescued from noise`);
    },
    error(error) {
      console.error('❌ Digest failed:', error?.message || error);
    }
  },

  /**
   * Auth
   */
  auth: {
    ok(cached = false) {
      // Only log on fresh token, not cached (too noisy)
      if (!cached) {
        console.log('🔑 Auth: token obtained');
      }
    },
    error(error) {
      console.error('❌ Auth failed:', error?.message || error);
    }
  },

  /**
   * Cache
   */
  cache: {
    synced(count) {
      if (count > 0) {
        console.log(`💾 Cache: synced ${count} threads`);
      }
    },
    updated(count) {
      if (count > 0) {
        console.log(`💾 Cache: updated ${count} badges`);
      }
    }
  },

  /**
   * Sidebar
   */
  sidebar: {
    ready() {
      console.log('📋 Sidebar ready');
    }
  },

  /**
   * General error
   */
  error(context, message, error = null) {
    if (error) {
      console.error(`❌ ${context}: ${message}`, error?.message || error);
    } else {
      console.error(`❌ ${context}: ${message}`);
    }
  },

  /**
   * Warning
   */
  warn(context, message) {
    console.warn(`⚠️  ${context}: ${message}`);
  },

  /**
   * Debug (only logs if DEBUG flag is set)
   */
  debug(message, data = null) {
    if (typeof window !== 'undefined' && window.MAILQ_DEBUG) {
      if (data) {
        console.debug(`🔍 ${message}`, data);
      } else {
        console.debug(`🔍 ${message}`);
      }
    }
  }
};

// Export for CommonJS and service worker (importScripts)
// Note: ES6 export is NOT supported by importScripts() in service workers
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { log };
} else if (typeof self !== 'undefined') {
  // Service worker global
  self.log = log;
} else if (typeof window !== 'undefined') {
  // Browser global
  window.log = log;
}
