import { defineConfig } from 'vitest/config'

// Vitest v4 foloseste Vite 8 cu OXC care transforma JSX nativ.
// @vitejs/plugin-react (Babel) nu e necesar in mediul de test
// si produce avertismente de deprecare din cauza optiunilor esbuild
// pe care Vite 8 nu le mai accepta.
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    css: false,
    include: ['tests/**/*.test.{js,jsx}'],
  },
})
