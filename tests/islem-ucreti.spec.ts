/**
 * Yönetim → Portföyler → İşlem Ücreti
 * ─────────────────────────────────────────────────────────────
 *   1. Ayar kaydedilir ve formda kalıcı görünür
 *   2. Yeni işlem ücretle kaydedilir: nakit, tutar + ücret kadar azalır
 *   3. Ayar değişince kayıtlı işlemin ücreti değişmez (nakit aynı kalır)
 *   4. İşlem silinince ücreti de düşer
 *
 * DB'ye yazar: benzersiz sembol kullanır, işlemi siler, ayarı eski haline getirir.
 * Çalıştırma: npm run test:e2e -- islem-ucreti
 */

import { test, expect, Page } from '@playwright/test';

const SYMBOL = 'ZZFEE';
const DATE = '2020-01-02';

async function saveFee(page: Page, fee: string) {
  await page.goto('/yonetim/');
  await page.fill('#trade-fee', fee);
  await page.locator('form[action="/yonetim/islem-ucreti"] button[type=submit]').click();
  await expect(page.locator('.alert-success')).toContainText('İşlem ücreti kaydedildi');
}

/** Nakit sayfasındaki bakiye (USD) */
async function cash(page: Page, portfolio: string): Promise<number> {
  await page.goto(`/nakit?portfolio=${encodeURIComponent(portfolio)}`);
  const text = await page.locator('.card h4.fw-bold').first().innerText();
  return parseFloat(text.replace(/[$,]/g, ''));
}

test('ücret ayarı yeni işleme yazılır, eskisini değiştirmez', async ({ page }) => {
  const info = await (await page.request.get('/api/session/info')).json();
  const portfolio: string = info.portfolios[0];
  await page.request.post('/api/session/portfolio', { data: { portfolio } });

  await page.goto('/yonetim/');
  const original = await page.inputValue('#trade-fee');

  try {
    await saveFee(page, '2.25');
    await page.goto('/yonetim/');
    await expect(page.locator('#trade-fee')).toHaveValue('2.25');

    const before = await cash(page, portfolio);
    await page.request.post('/islemler/ekle', {
      form: { tx_date: DATE, symbol: SYMBOL, direction: 'Alış', quantity: '1', price: '10', portfolio },
    });
    expect(await cash(page, portfolio)).toBeCloseTo(before - 10 - 2.25, 2);

    await saveFee(page, '9');
    expect(await cash(page, portfolio)).toBeCloseTo(before - 10 - 2.25, 2);

    await page.goto(`/islemler?yil=2020&portfolio=${encodeURIComponent(portfolio)}`);
    page.on('dialog', d => d.accept());
    const row = page.locator('tr', { hasText: SYMBOL }).first();
    await row.locator('form[action^="/islemler/sil/"] button').click();
    expect(await cash(page, portfolio)).toBeCloseTo(before, 2);
  } finally {
    await saveFee(page, original);
  }
});
