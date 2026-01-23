/**
 * SEC-009: Encryption utilities for chrome.storage data protection
 *
 * Uses Web Crypto API for AES-GCM encryption of sensitive data.
 * Key is derived from a user-specific seed stored in chrome.storage.session
 * (ephemeral, cleared when browser closes).
 */

const CRYPTO_LOG_PREFIX = '[ReturnWatch:Crypto]';
const KEY_STORAGE_KEY = 'encryption_key_material';
const ENCRYPTION_ALGORITHM = 'AES-GCM';
const IV_LENGTH = 12; // 96 bits for GCM

/**
 * Get or create the encryption key.
 * Key material is stored in chrome.storage.session (ephemeral).
 * @returns {Promise<CryptoKey>}
 */
async function getEncryptionKey() {
  // Try to get existing key material from session storage
  const result = await chrome.storage.session.get(KEY_STORAGE_KEY);

  let keyMaterial;
  if (result[KEY_STORAGE_KEY]) {
    // Restore key from stored material
    keyMaterial = new Uint8Array(result[KEY_STORAGE_KEY]);
  } else {
    // Generate new key material
    keyMaterial = crypto.getRandomValues(new Uint8Array(32));
    // Store in session (cleared when browser closes)
    await chrome.storage.session.set({
      [KEY_STORAGE_KEY]: Array.from(keyMaterial),
    });
    console.log(CRYPTO_LOG_PREFIX, 'Generated new encryption key');
  }

  // Import as CryptoKey
  return crypto.subtle.importKey(
    'raw',
    keyMaterial,
    { name: ENCRYPTION_ALGORITHM },
    false, // not extractable
    ['encrypt', 'decrypt']
  );
}

/**
 * Encrypt a string value.
 * @param {string} plaintext - Data to encrypt
 * @returns {Promise<string>} Base64-encoded encrypted data (IV + ciphertext)
 */
async function encryptValue(plaintext) {
  if (!plaintext) return plaintext;

  try {
    const key = await getEncryptionKey();
    const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));
    const encoder = new TextEncoder();
    const data = encoder.encode(plaintext);

    const ciphertext = await crypto.subtle.encrypt(
      { name: ENCRYPTION_ALGORITHM, iv },
      key,
      data
    );

    // Combine IV + ciphertext and encode as base64
    const combined = new Uint8Array(iv.length + ciphertext.byteLength);
    combined.set(iv);
    combined.set(new Uint8Array(ciphertext), iv.length);

    return btoa(String.fromCharCode(...combined));
  } catch (error) {
    console.error(CRYPTO_LOG_PREFIX, 'Encryption failed:', error);
    throw error;
  }
}

/**
 * Decrypt a string value.
 * @param {string} encryptedBase64 - Base64-encoded encrypted data
 * @returns {Promise<string>} Decrypted plaintext
 */
async function decryptValue(encryptedBase64) {
  if (!encryptedBase64) return encryptedBase64;

  try {
    const key = await getEncryptionKey();

    // Decode base64 to bytes
    const combined = Uint8Array.from(atob(encryptedBase64), c => c.charCodeAt(0));

    // Split IV and ciphertext
    const iv = combined.slice(0, IV_LENGTH);
    const ciphertext = combined.slice(IV_LENGTH);

    const decrypted = await crypto.subtle.decrypt(
      { name: ENCRYPTION_ALGORITHM, iv },
      key,
      ciphertext
    );

    const decoder = new TextDecoder();
    return decoder.decode(decrypted);
  } catch (error) {
    console.error(CRYPTO_LOG_PREFIX, 'Decryption failed:', error);
    throw error;
  }
}

/**
 * Encrypt sensitive fields in an object.
 * @param {Object} obj - Object with data
 * @param {string[]} sensitiveFields - Field names to encrypt
 * @returns {Promise<Object>} Object with encrypted fields
 */
async function encryptSensitiveFields(obj, sensitiveFields) {
  if (!obj) return obj;

  const result = { ...obj };
  for (const field of sensitiveFields) {
    if (result[field] !== undefined && result[field] !== null) {
      const value = typeof result[field] === 'string'
        ? result[field]
        : JSON.stringify(result[field]);
      result[field] = await encryptValue(value);
      result[`${field}_encrypted`] = true;
    }
  }
  return result;
}

/**
 * Decrypt sensitive fields in an object.
 * @param {Object} obj - Object with encrypted data
 * @param {string[]} sensitiveFields - Field names to decrypt
 * @returns {Promise<Object>} Object with decrypted fields
 */
async function decryptSensitiveFields(obj, sensitiveFields) {
  if (!obj) return obj;

  const result = { ...obj };
  for (const field of sensitiveFields) {
    if (result[`${field}_encrypted`] && result[field]) {
      try {
        const decrypted = await decryptValue(result[field]);
        // Try to parse as JSON, otherwise keep as string
        try {
          result[field] = JSON.parse(decrypted);
        } catch {
          result[field] = decrypted;
        }
        delete result[`${field}_encrypted`];
      } catch (error) {
        console.warn(CRYPTO_LOG_PREFIX, `Failed to decrypt field ${field}:`, error);
        // Keep original value if decryption fails
      }
    }
  }
  return result;
}

// Sensitive fields that should be encrypted in Order objects
const ORDER_SENSITIVE_FIELDS = [
  'order_id',
  'tracking_number',
  'amount',
];

// Sensitive fields in OrderEmail objects
const ORDER_EMAIL_SENSITIVE_FIELDS = [
  'subject',
  'snippet',
];

/**
 * Encrypt an Order object's sensitive fields.
 * @param {Object} order
 * @returns {Promise<Object>}
 */
async function encryptOrder(order) {
  return encryptSensitiveFields(order, ORDER_SENSITIVE_FIELDS);
}

/**
 * Decrypt an Order object's sensitive fields.
 * @param {Object} order
 * @returns {Promise<Object>}
 */
async function decryptOrder(order) {
  return decryptSensitiveFields(order, ORDER_SENSITIVE_FIELDS);
}

/**
 * Encrypt an OrderEmail object's sensitive fields.
 * @param {Object} email
 * @returns {Promise<Object>}
 */
async function encryptOrderEmail(email) {
  return encryptSensitiveFields(email, ORDER_EMAIL_SENSITIVE_FIELDS);
}

/**
 * Decrypt an OrderEmail object's sensitive fields.
 * @param {Object} email
 * @returns {Promise<Object>}
 */
async function decryptOrderEmail(email) {
  return decryptSensitiveFields(email, ORDER_EMAIL_SENSITIVE_FIELDS);
}

// Export for use in store.js
// Note: In service worker context, these are global
