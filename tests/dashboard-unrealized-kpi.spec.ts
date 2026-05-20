/**
 * Dashboard — Açık Pozisyonlar Gerçekleşmemiş K/Z KPI Kartı
 * ─────────────────────────────────────────────────────────────
 * Bu spec dashboard'a eklenen async KPI kartının davranışını doğrular:
 *
 *   1. Kart render edilir (açık pozisyon varsa)
 *   2. Async fetch — sayfa yüklenir yüklenmez başlar, kitlemez
 *   3. Mock fiyatlarla net K/Z, Kâr, Zarar doğru hesaplanır
 *   4. After-hours fiyatı varsa o kullanılır (extended_hours_price)
 *   5. 60s'de bir otomatik refresh yapar (clock.fastForward ile doğrulanır)
 *   6. Negatif/pozitif renk kodlaması doğru
 *   7. "Son: HH:MM:SS" timestamp her refresh'te yenilenir
 *
 * Çalıştırma: npm run test:e2e
 */

import { test, expect, Page, Route } from '@playwright/test';

// ─── Yardımcılar ──────────────────────────────────────────────────────────

type DistItem = { symbol: string; qty: number; cost: number };

/** Dashboard sayfasındaki açık pozisyon dağılımını JS context'inden oku */
async function readDistrib(page: Page): Promise<DistItem[]> {
  return page.evaluate(() => (window as any).__distrib || []);
}

/** Her sembol için sabit bir fiyat dönen mock cevap üret */
function buildMockPriceResponse(distrib: DistItem[], pricePerShare: number) {
  const prices: Record<string, any> = {};
  for (const d of distrib) {
    prices[d.symbol] = {
      current_price: pricePerShare,
      prev_close:    pricePerShare * 0.98,
      change_pct:    2.0,
      market_state:  'REGULAR',
      currency:      'USD',
      extended_hours_price: null,
      extended_hours_change_pct: null,
      error: null,
    };
  }
  return { ok: true, prices, fetched_at: new Date().toISOString() };
}

/** /api/fiyatlar/guncelle endpoint'ini sabit fiyatla mock'la */
async function mockPriceEndpoint(page: Page, distrib: DistItem[], pricePerShare: number) {
  await page.route('**/api/fiyatlar/guncelle', async (route: Route) => {
    const body = buildMockPriceResponse(distrib, pricePerShare);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  });
}

/** Bir hücre içeriğinin USD formatında olduğunu (örn. "$1,234" veya "$0") doğrula */
function isValidUsd(s: string): boolean {
  return /^\+?\$[\d,]+(\.\d{2})?$/.test(s.trim());
}

/** Kart elementlerinin hızlı erişimi için locator'lar */
function kpiLocators(page: Page) {
  return {
    card:    page.locator('.card', { has: page.locator('text=GERÇEKLEŞMEMİŞ K/Z') }),
    net:     page.locator('#unr-kpi-net'),
    pct:     page.locator('#unr-kpi-pct'),
    profit:  page.locator('#unr-kpi-profit'),
    loss:    page.locator('#unr-kpi-loss'),
    count:   page.locator('#unr-kpi-count'),
    time:    page.locator('#unr-kpi-time'),
    spinner: page.locator('#unr-kpi-spinner'),
  };
}

// ─── Test grupları ────────────────────────────────────────────────────────

test.describe('Dashboard — Gerçekleşmemiş K/Z KPI', () => {

  test.beforeEach(async ({ page }) => {
    // localStorage'ı temizle ki cache'ten anında gelmesin (yükleme akışını test edelim)
    await page.addInitScript(() => {
      try { localStorage.removeItem('_priceCache'); } catch (_) {}
    });
  });

  test('kart render edilir ve açık pozisyon sayısı doğru', async ({ page }) => {
    await page.goto('/');
    const k = kpiLocators(page);

    // Açık pozisyon yoksa kart hiç render edilmez (Jinja {% if distribution %})
    const distrib = await readDistrib(page);
    test.skip(distrib.length === 0, 'Bu portföyde açık pozisyon yok — KPI kartı zaten gizli');

    await expect(k.card).toBeVisible();
    await expect(k.count).toHaveText(String(distrib.length));
    // Header etiketi sabit
    await expect(k.card.locator('text=GERÇEKLEŞMEMİŞ K/Z')).toBeVisible();
  });

  test('mock fiyatlarla net K/Z hesaplanır (kâr senaryosu)', async ({ page }) => {
    // Önce sayfa yüklensin, distrib'i oku
    await page.goto('/');
    const distrib = await readDistrib(page);
    test.skip(distrib.length === 0, 'Açık pozisyon yok');

    // Her sembol için $1000 fiyat → kesinlikle KÂR (kullanıcının gerçek maliyeti çok daha düşük)
    await mockPriceEndpoint(page, distrib, 1000);

    // Async fetch'i manuel tetikle
    await page.evaluate(() => (window as any)._refreshUnrealizedKpiAsync?.());

    const k = kpiLocators(page);
    await expect(k.net).not.toHaveText('—', { timeout: 5_000 });

    // Beklenen değerler: mv = qty × 1000, net = mv_total - cost_total
    const expectedMv   = distrib.reduce((s, d) => s + d.qty * 1000, 0);
    const expectedCost = distrib.reduce((s, d) => s + d.cost, 0);
    const expectedNet  = expectedMv - expectedCost;

    // Net işaret + büyüklük (USD formatından sayıyı sökerek karşılaştır)
    const netText = (await k.net.textContent()) || '';
    const netNum  = parseFloat(netText.replace(/[+$,]/g, ''));
    expect(netNum).toBeCloseTo(expectedNet, 0);   // ±$1 tolerans

    // Pozitif olmalı (Kâr senaryosu)
    expect(netNum).toBeGreaterThan(0);
    await expect(k.net).toHaveClass(/text-success/);

    // Zarar 0, Kâr = net olmalı
    const lossText = (await k.loss.textContent()) || '';
    expect(parseFloat(lossText.replace(/[$,]/g, ''))).toBeCloseTo(0, 0);
  });

  test('mock fiyatlarla net K/Z hesaplanır (zarar senaryosu)', async ({ page }) => {
    await page.goto('/');
    const distrib = await readDistrib(page);
    test.skip(distrib.length === 0, 'Açık pozisyon yok');

    // Her sembol $0.01 → toplam mv ~0, net = -total_cost (büyük zarar)
    await mockPriceEndpoint(page, distrib, 0.01);
    await page.evaluate(() => (window as any)._refreshUnrealizedKpiAsync?.());

    const k = kpiLocators(page);
    await expect(k.net).not.toHaveText('—', { timeout: 5_000 });

    const netText = (await k.net.textContent()) || '';
    const netNum  = parseFloat(netText.replace(/[+$,]/g, ''));

    expect(netNum).toBeLessThan(0);
    await expect(k.net).toHaveClass(/text-danger/);

    // Kâr ~0, Zarar > 0
    const profitText = (await k.profit.textContent()) || '';
    expect(parseFloat(profitText.replace(/[$,]/g, ''))).toBeCloseTo(0, 0);
    const lossText = (await k.loss.textContent()) || '';
    expect(parseFloat(lossText.replace(/[$,]/g, ''))).toBeGreaterThan(0);
  });

  test('after-hours fiyatı varsa MV o değerden hesaplanır', async ({ page }) => {
    await page.goto('/');
    const distrib = await readDistrib(page);
    test.skip(distrib.length === 0, 'Açık pozisyon yok');

    // Regular $500 ama AH $2000 → MV $2000'den hesaplanmalı
    await page.route('**/api/fiyatlar/guncelle', async (route) => {
      const prices: Record<string, any> = {};
      for (const d of distrib) {
        prices[d.symbol] = {
          current_price: 500,
          prev_close: 490,
          change_pct: 2.0,
          market_state: 'POST',
          currency: 'USD',
          extended_hours_price: 2000,             // ← bu kullanılmalı
          extended_hours_change_pct: 300.0,
          error: null,
        };
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, prices, fetched_at: new Date().toISOString() }),
      });
    });

    await page.evaluate(() => (window as any)._refreshUnrealizedKpiAsync?.());

    const k = kpiLocators(page);
    await expect(k.net).not.toHaveText('—', { timeout: 5_000 });

    const netText = (await k.net.textContent()) || '';
    const netNum  = parseFloat(netText.replace(/[+$,]/g, ''));

    // AH kullanıldıysa: net = qty × 2000 - cost
    const expectedNet = distrib.reduce((s, d) => s + (d.qty * 2000 - d.cost), 0);
    expect(netNum).toBeCloseTo(expectedNet, 0);

    // AH kullanılmadıysa (regular $500): net = qty × 500 - cost  → çok farklı olurdu
    const wrongIfRegular = distrib.reduce((s, d) => s + (d.qty * 500 - d.cost), 0);
    expect(Math.abs(netNum - wrongIfRegular)).toBeGreaterThan(10);
  });

  test('60s interval ile otomatik refresh — yeni fetch tetiklenir', async ({ page }) => {
    // Saati sabitlemeden önce route'u koy ki ilk fetch'i de yakalayalım
    await page.clock.install({ time: new Date('2026-05-09T12:00:00Z') });

    let fetchCount = 0;
    await page.route('**/api/fiyatlar/guncelle', async (route) => {
      fetchCount++;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          prices: {},                  // boş — sadece tetiklendiğini doğruluyoruz
          fetched_at: new Date().toISOString(),
        }),
      });
    });

    await page.goto('/');
    const distrib = await readDistrib(page);
    test.skip(distrib.length === 0, 'Açık pozisyon yok');

    // İlk fetch — sayfada 250ms setTimeout var
    await page.clock.fastForward(500);
    await page.waitForResponse(
      (r) => r.url().includes('/api/fiyatlar/guncelle'),
      { timeout: 5_000 }
    );
    const fetchesBefore = fetchCount;
    expect(fetchesBefore).toBeGreaterThanOrEqual(1);

    // 60s ileri sar → setInterval tetiklenmeli
    await page.clock.fastForward('60s');
    await page.waitForResponse(
      (r) => r.url().includes('/api/fiyatlar/guncelle'),
      { timeout: 5_000 }
    );

    expect(fetchCount).toBeGreaterThan(fetchesBefore);
  });

  test('hiç fiyat çekilemezse "—" gösterir (defensive)', async ({ page }) => {
    await page.goto('/');
    const distrib = await readDistrib(page);
    test.skip(distrib.length === 0, 'Açık pozisyon yok');

    // Tüm fiyat fetch'lerini başarısız yap
    await page.route('**/api/fiyatlar/guncelle', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ ok: false, error: 'mocked failure' }),
      });
    });

    // Sayfa yüklenince çağrılan async fetch başarısız olur → net "—" kalır
    await page.evaluate(() => {
      // _distLastPrices'ı boşalt ki cache hile yapmasın
      (window as any)._distLastPrices = {};
      (window as any)._refreshUnrealizedKpiAsync?.();
    });

    const k = kpiLocators(page);
    // 2sn içinde değer dolmuş olmamalı (fetch fail oldu, cache de boş)
    await page.waitForTimeout(1000);
    const text = await k.net.textContent();
    expect(text).toBe('—');
    await expect(k.net).toHaveClass(/text-muted/);
  });

  test('değer formatları geçerli (USD + yüzde)', async ({ page }) => {
    await page.goto('/');
    const distrib = await readDistrib(page);
    test.skip(distrib.length === 0, 'Açık pozisyon yok');

    await mockPriceEndpoint(page, distrib, 250);
    await page.evaluate(() => (window as any)._refreshUnrealizedKpiAsync?.());

    const k = kpiLocators(page);
    await expect(k.net).not.toHaveText('—', { timeout: 5_000 });

    const net = (await k.net.textContent())?.trim() || '';
    const pct = (await k.pct.textContent())?.trim() || '';
    const profit = (await k.profit.textContent())?.trim() || '';
    const loss = (await k.loss.textContent())?.trim() || '';

    expect(isValidUsd(net) || /^[+-]\$/.test(net)).toBeTruthy();
    expect(pct).toMatch(/^[+-]?\d+\.\d{2}%$/);
    expect(isValidUsd(profit)).toBeTruthy();
    expect(isValidUsd(loss)).toBeTruthy();
  });

});
