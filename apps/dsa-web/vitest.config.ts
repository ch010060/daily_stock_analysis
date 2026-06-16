import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom@28 + html-encoding-sniffer@6 + @exodus/bytes@1.15 (ESM-only) crashes
    // on Node 20 with ERR_REQUIRE_ESM. happy-dom avoids this dependency chain
    // entirely and is faster for unit tests.
    environment: 'happy-dom',
    globals: true,
    setupFiles: './src/setupTests.ts',
    exclude: [...configDefaults.exclude, 'e2e/**', 'playwright.config.ts'],
  },
});
