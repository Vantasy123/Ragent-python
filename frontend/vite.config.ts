import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { webcrypto } from 'crypto'

// Node 16 polyfill for crypto.getRandomValues
import cryptoModule from 'crypto'
if (cryptoModule && !cryptoModule.getRandomValues) {
  (cryptoModule as any).getRandomValues = function (arr: any) {
    return webcrypto.getRandomValues(arr)
  }
}
if (typeof globalThis.crypto === 'undefined') {
  Object.defineProperty(globalThis, 'crypto', {
    value: webcrypto,
    writable: true,
    configurable: true,
  })
}
if (typeof global.crypto === 'undefined') {
  Object.defineProperty(global, 'crypto', {
    value: webcrypto,
    writable: true,
    configurable: true,
  })
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
