/**
 * İngilizce arayüz
 * ─────────────────────────────────────────────────────────────
 *   1. Her sayfa EN açılır: metinlerde ve title/placeholder'larda Türkçe harf kalmaz
 *      (gizli pencereler dahil; JS'in sonradan yazdığı metinler de sayılır)
 *   2. Sunucu mesajları (yönlendirme ve JSON hatası) oturum diline uyar
 *   3. Giriş ekranındaki dil düğmesi oturum açmadan çalışır
 *
 * DB'ye yazmaz; oturum dili test sonunda Türkçeye döner.
 * Kullanıcı verisi taranmaz sayılır: portföy adları yok sayılır, Türkçe harfli
 * sembol notu veya portföy açıklaması varsa burada görünür.
 * Çalıştırma: npm run test:e2e -- i18n-en
 */

import { test, expect, Page } from '@playwright/test';

const TURKISH = /[çğıİöşüÇĞÖŞÜâÂ]/;
const PAGES = ['/', '/islemler', '/nakit', '/semboller', '/sembol/AAPL', '/pozisyonlar', '/fiyatlar', '/yonetim/', '/ai'];

async function setLang(page: Page, lang: string) {
  const res = await page.request.post('/api/session/lang', { data: { lang } });
  expect(res.ok()).toBeTruthy();
}

/** Sayfadaki metin düğümleri ve title/placeholder/aria-label değerleri */
async function pageStrings(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const tag = node.parentElement?.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEXTAREA') continue;
      const text = (node.textContent || '').trim();
      if (text) out.push(text);
    }
    for (const el of Array.from(document.querySelectorAll('[title],[placeholder],[aria-label]'))) {
      for (const attr of ['title', 'placeholder', 'aria-label']) {
        const value = el.getAttribute(attr);
        if (value) out.push(value);
      }
    }
    return out;
  });
}

test.describe('İngilizce arayüz', () => {
  test.afterEach(async ({ page }) => {
    await setLang(page, 'tr');
  });

  test('sayfalarda Türkçe metin kalmaz', async ({ page }) => {
    const info = await (await page.request.get('/api/session/info')).json();
    const portfolio: string = info.portfolios[0];
    await page.request.post('/api/session/portfolio', { data: { portfolio } });
    await setLang(page, 'en');

    const leftovers: Record<string, string[]> = {};
    for (const path of PAGES) {
      await page.goto(path);
      await page.waitForTimeout(1500); // JS'in yazdığı metinler
      const hits = (await pageStrings(page)).filter(
        s => TURKISH.test(s) && !info.portfolios.some((p: string) => s.includes(p)),
      );
      if (hits.length) leftovers[path] = Array.from(new Set(hits));
    }
    expect(leftovers).toEqual({});
  });

  test('sunucu mesajları oturum diline uyar', async ({ page }) => {
    await setLang(page, 'en');

    const redirected = await page.request.post('/yonetim/islem-ucreti', { form: { fee: '999' } });
    await page.goto(redirected.url());
    await expect(page.locator('.alert-danger')).toContainText('Trade fee must be between 0 and 100');

    const json = await page.request.post('/api/tokens', { data: { name: '' } });
    expect(json.status()).toBe(400);
    expect((await json.json()).error).toBe('Token name is required');

    expect(await page.evaluate(() => (window as any)._t('{n} işlem', { n: 3 }))).toBe('3 trades');

    await setLang(page, 'tr');
    await page.goto('/yonetim/');
    expect(await page.evaluate(() => (window as any)._t('{n} işlem', { n: 3 }))).toBe('3 işlem');
  });
});

test('giriş ekranı dil düğmesi oturum açmadan çalışır', async ({ browser, baseURL }) => {
  const ctx = await browser.newContext({ baseURL, storageState: { cookies: [], origins: [] } });
  const page = await ctx.newPage();
  await page.goto('/auth/login');
  await expect(page.locator('.card-header')).toContainText('Giriş');
  await page.getByRole('link', { name: 'EN', exact: true }).click();
  await expect(page.locator('.card-header')).toContainText('Sign In');
  expect(TURKISH.test(await page.locator('body').innerText())).toBeFalsy();
  await page.getByRole('link', { name: 'TR', exact: true }).click();
  await expect(page.locator('.card-header')).toContainText('Giriş');
  await ctx.close();
});
