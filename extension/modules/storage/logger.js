/**
 * Classification Logger - Captures all classification results for analysis
 *
 * Stores classifications in IndexedDB for later export and analysis.
 * Each entry includes email metadata, classification results, and context.
 */

const LOGGER_DB_NAME = 'ShopQLogger';
const LOGGER_STORE_NAME = 'classifications';
const LOGGER_VERSION = 1;

class ClassificationLogger {
  constructor() {
    this.db = null;
    this.enabled = true;
    this.initDB();
  }

  /**
   * Initialize IndexedDB for storing classification logs
   */
  async initDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(LOGGER_DB_NAME, LOGGER_VERSION);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        // Create object store with auto-incrementing key
        if (!db.objectStoreNames.contains(LOGGER_STORE_NAME)) {
          const store = db.createObjectStore(LOGGER_STORE_NAME, {
            keyPath: 'id',
            autoIncrement: true
          });

          // Indexes for querying
          store.createIndex('timestamp', 'timestamp', { unique: false });
          store.createIndex('messageId', 'messageId', { unique: false });
          store.createIndex('decider', 'decider', { unique: false });
          store.createIndex('type', 'classification.type', { unique: false });
        }
      };
    });
  }

  /**
   * Log a classification result
   * @param {Object} email - Email metadata
   * @param {Object} classification - Classification result from API
   * @param {Array} labels - Gmail labels applied
   * @param {Object} context - Additional context (verifier info, etc.)
   */
  async logClassification(email, classification, labels, context = {}) {
    if (!this.enabled) return;
    if (!this.db) await this.initDB();

    const entry = {
      timestamp: new Date().toISOString(),
      messageId: email.id,
      threadId: email.threadId, // For Gmail deep links
      from: email.from,
      subject: email.subject,
      snippet: email.snippet?.substring(0, 200), // Truncate for storage
      emailTimestamp: email.timestamp, // Gmail's internalDate (milliseconds since epoch)
      classification: {
        type: classification.type,
        type_conf: classification.type_conf,
        attention: classification.attention,
        attention_conf: classification.attention_conf,
        importance: classification.importance,  // Used by digest for section assignment
        importance_conf: classification.importance_conf,
        client_label: classification.client_label,  // Used by digest for footer label counts
        relationship: classification.relationship,
        relationship_conf: classification.relationship_conf,
        decider: classification.decider,
        reason: classification.reason
      },
      labels: labels,
      verifier: context.verifier || null,
      detectorUsed: context.detector || null,
      processingTimeMs: context.processingTimeMs || null
    };

    return new Promise((resolve, reject) => {
      try {
        const transaction = this.db.transaction([LOGGER_STORE_NAME], 'readwrite');
        const store = transaction.objectStore(LOGGER_STORE_NAME);
        const request = store.add(entry);

        request.onsuccess = () => {
          logVerbose(`📝 Logged classification for: ${email.subject?.substring(0, 50)}...`);
          resolve(request.result);
        };
        request.onerror = () => {
          console.error(`❌ Failed to log classification for: ${email.subject}`, request.error);
          reject(request.error);
        };
      } catch (error) {
        // Database connection might be stale after extension reload
        console.warn('⚠️ Logger DB connection error, reinitializing...', error);
        this.db = null;
        reject(error);
      }
    });
  }

  /**
   * Get all logged classifications
   * @param {Object} filters - Optional filters (startDate, endDate, type, decider)
   */
  async getClassifications(filters = {}) {
    if (!this.db) await this.initDB();

    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([LOGGER_STORE_NAME], 'readonly');
      const store = transaction.objectStore(LOGGER_STORE_NAME);
      const request = store.getAll();

      request.onsuccess = () => {
        let results = request.result;

        logVerbose(`📊 [LOGGER] Total classifications in DB: ${results.length}`);
        if (results.length > 0) {
          logVerbose(`📊 [LOGGER] First timestamp: ${results[0].timestamp}`);
          logVerbose(`📊 [LOGGER] Last timestamp: ${results[results.length - 1].timestamp}`);
        }

        // Apply filters
        if (filters.startDate) {
          logVerbose(`📊 [LOGGER] Filtering by startDate >= ${filters.startDate}`);
          const beforeFilter = results.length;
          results = results.filter(r => r.timestamp >= filters.startDate);
          logVerbose(`📊 [LOGGER] After startDate filter: ${results.length}/${beforeFilter} remaining`);
        }
        if (filters.endDate) {
          results = results.filter(r => r.timestamp <= filters.endDate);
        }
        if (filters.type) {
          results = results.filter(r => r.classification.type === filters.type);
        }
        if (filters.decider) {
          results = results.filter(r => r.classification.decider === filters.decider);
        }

        resolve(results);
      };
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Export classifications as JSONL (one JSON object per line)
   * @param {Object} filters - Optional filters
   * @returns {string} JSONL string
   */
  async exportJSONL(filters = {}) {
    const classifications = await this.getClassifications(filters);
    return classifications.map(c => JSON.stringify(c)).join('\n');
  }

  /**
   * Export classifications as downloadable file
   * @param {string} filename - Output filename
   */
  async downloadExport(filename = null) {
    if (!filename) {
      const date = new Date().toISOString().split('T')[0];
      filename = `mailq-classifications-${date}.jsonl`;
    }

    const jsonl = await this.exportJSONL();

    // Check if we're in a service worker context
    if (typeof document === 'undefined') {
      // Use chrome.downloads API from service worker
      const blob = new Blob([jsonl], { type: 'application/x-ndjson' });
      const reader = new FileReader();

      return new Promise((resolve, reject) => {
        reader.onload = () => {
          chrome.downloads.download({
            url: reader.result,
            filename: filename,
            saveAs: true
          }, (downloadId) => {
            if (chrome.runtime.lastError) {
              reject(chrome.runtime.lastError);
            } else {
              console.log(`📥 Exported ${filename} (download ID: ${downloadId})`);
              resolve(downloadId);
            }
          });
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
    } else {
      // Use DOM download from web page context
      const blob = new Blob([jsonl], { type: 'application/x-ndjson' });
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();

      URL.revokeObjectURL(url);
      console.log(`📥 Exported ${filename}`);
    }
  }

  /**
   * Get summary statistics
   */
  async getStats() {
    const classifications = await this.getClassifications();

    const stats = {
      total: classifications.length,
      byType: {},
      byDecider: {},
      lowConfidence: 0,
      verifierCorrections: 0,
      avgConfidence: 0
    };

    let totalConf = 0;

    classifications.forEach(c => {
      // By type
      const type = c.classification.type;
      stats.byType[type] = (stats.byType[type] || 0) + 1;

      // By decider
      const decider = c.classification.decider;
      stats.byDecider[decider] = (stats.byDecider[decider] || 0) + 1;

      // Low confidence
      if (c.classification.type_conf < 0.85) {
        stats.lowConfidence++;
      }

      // Verifier corrections
      if (c.verifier && c.verifier.verdict === 'reject') {
        stats.verifierCorrections++;
      }

      totalConf += c.classification.type_conf;
    });

    stats.avgConfidence = classifications.length > 0
      ? (totalConf / classifications.length).toFixed(2)
      : 0;

    return stats;
  }

  /**
   * Clear all logged classifications
   */
  async clear() {
    if (!this.db) return;

    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([LOGGER_STORE_NAME], 'readwrite');
      const store = transaction.objectStore(LOGGER_STORE_NAME);
      const request = store.clear();

      request.onsuccess = () => {
        console.log('🗑️ Classification log cleared');
        resolve();
      };
      request.onerror = () => reject(request.error);
    });
  }
}

// Create singleton instance
const logger = new ClassificationLogger();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = logger;
}
