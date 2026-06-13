/**
 * Vitest setup global.
 * Configureaza @testing-library/jest-dom + MSW server pentru toate testele.
 */
import { expect, afterAll, afterEach, beforeAll } from 'vitest'
import * as matchers from '@testing-library/jest-dom/matchers'
import { server } from './mocks/server.js'

// Extinde expect cu matcher-ele jest-dom (toBeInTheDocument, toBeDisabled, toHaveAttribute, etc.)
expect.extend(matchers)

// Pornește MSW înainte de toate testele
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))

// Resetează handler-ele după fiecare test (izolare)
afterEach(() => server.resetHandlers())

// Închide MSW la final
afterAll(() => server.close())

// jsdom nu are localStorage prin default — îl simulăm
if (typeof window !== 'undefined' && !window.localStorage) {
  const store = {}
  window.localStorage = {
    getItem: (k) => store[k] ?? null,
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: (k) => { delete store[k] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  }
}

// URL.createObjectURL nu există în jsdom — îl simulăm
if (typeof URL.createObjectURL === 'undefined') {
  URL.createObjectURL = () => 'blob:mock-url'
  URL.revokeObjectURL = () => {}
}
