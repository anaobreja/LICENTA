/**
 * MSW server pentru Node.js (jsdom) - folosit de Vitest în setup.js.
 */
import { setupServer } from 'msw/node'
import { handlers } from './handlers.js'

export const server = setupServer(...handlers)
