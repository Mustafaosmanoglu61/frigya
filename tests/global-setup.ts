/**
 * Global setup — tek sefer login ol, session cookie'sini storageState olarak kaydet.
 * Her test bunu otomatik kullanır; her testte tekrar login yapmaz.
 */
import { chromium, FullConfig } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const BASE_URL = process.env.FRIGYA_BASE_URL || 'http://127.0.0.1:8000';
const EMAIL    = process.env.FRIGYA_EMAIL    || readDotEnv('INITIAL_ADMIN_EMAIL')    || 'admin@tax-portfolio.local';
const PASSWORD = process.env.FRIGYA_PASSWORD || readDotEnv('INITIAL_ADMIN_PASSWORD') || '';

const STATE_PATH = path.resolve(__dirname, '.auth', 'admin.json');

function readDotEnv(key: string): string | undefined {
  const envPath = path.resolve(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) return undefined;
  const txt = fs.readFileSync(envPath, 'utf-8');
  const re  = new RegExp('^' + key + '=(.*)$', 'm');
  const m   = txt.match(re);
  return m ? m[1].replace(/^["']|["']$/g, '') : undefined;
}

export default async function globalSetup(_config: FullConfig) {
  fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true });

  if (!PASSWORD) {
    throw new Error(
      'FRIGYA_PASSWORD bulunamadı. .env içindeki INITIAL_ADMIN_PASSWORD okunamadı ' +
      've FRIGYA_PASSWORD env değişkeni de atanmamış.'
    );
  }

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ baseURL: BASE_URL });
  const page = await ctx.newPage();

  // 1) Login formu
  await page.goto('/auth/login');
  await page.fill('input[name="email"]',    EMAIL);
  await page.fill('input[name="password"]', PASSWORD);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.startsWith('/auth/login'), { timeout: 10_000 }),
    page.click('button[type="submit"]'),
  ]);

  // 2) Dashboard yüklendi mi doğrula (login başarılı)
  await page.waitForSelector('h4:has-text("Dashboard")', { timeout: 8_000 });

  // 3) Cookie/storage state'i kaydet
  await ctx.storageState({ path: STATE_PATH });
  await browser.close();

  console.log(`✅ Login storageState saved → ${STATE_PATH}`);
}
