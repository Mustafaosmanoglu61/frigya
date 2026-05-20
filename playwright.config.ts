import { defineConfig, devices } from '@playwright/test';

/**
 * Frigya E2E config
 *
 * Çalıştırma:
 *   1) Sunucuyu ayrı terminalde başlat:
 *        cd webapp && uvicorn main:app --reload --port 8000
 *   2) Bu kökten:
 *        npm install
 *        npm run playwright:install
 *        npm run test:e2e
 *
 * Veya tek seferde, otomatik server başlatma için:
 *        PW_AUTO_SERVER=1 npm run test:e2e
 *
 * Login bilgileri .env'den okunur; alternatifler için env değişkenleri:
 *   FRIGYA_BASE_URL  (default: http://127.0.0.1:8000)
 *   FRIGYA_EMAIL     (default: .env INITIAL_ADMIN_EMAIL)
 *   FRIGYA_PASSWORD  (default: .env INITIAL_ADMIN_PASSWORD)
 */

const BASE_URL = process.env.FRIGYA_BASE_URL || 'http://127.0.0.1:8000';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,           // tek SQLite — testler sıralı çalışsın
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  timeout: 30_000,
  expect: { timeout: 5_000 },

  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 8_000,
    navigationTimeout: 12_000,
    // İlk login'den sonra storageState kaydedilir — sonraki testler hızlı açılır
    storageState: 'tests/.auth/admin.json',
  },

  globalSetup: require.resolve('./tests/global-setup.ts'),

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Sunucu env değişkeniyle açıkça istendiyse otomatik başlat (default: kapalı)
  webServer: process.env.PW_AUTO_SERVER
    ? {
        command: 'cd webapp && uvicorn main:app --port 8000',
        url: BASE_URL,
        timeout: 60_000,
        reuseExistingServer: true,
      }
    : undefined,
});
