import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: [
      'extension/tests/**/*.{test,spec}.js',
      'extension/**/*.{test,spec}.js'
    ],
    exclude: [
      'node_modules/**',
      'dist/**',
      'build/**'
    ],
    environment: 'jsdom',
    globals: true,
    coverage: {
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'tests/',
        '**/*.spec.js',
        '**/*.test.js'
      ]
    }
  }
})
