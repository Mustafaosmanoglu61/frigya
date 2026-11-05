/**
 * Yönetim → MCP Erişimi — kişisel API token'ları
 * ─────────────────────────────────────────────────────────────
 *   1. Sekme /yonetim#tab-mcp ile doğrudan açılır
 *   2. Token oluşturulur: bir kez gösterilir, Claude Code / Desktop parçaları dolar, listeye eklenir
 *   3. Token uzak MCP'de (/mcp) çalışır: initialize → 200
 *   4. Token site yönetim API'sinde (/api/tokens) çalışmaz → 401
 *   5. İptal edilince listeden düşer ve /mcp → 401
 *
 * DB'ye yazar: benzersiz ad kullanır, oluşturduğu token'ı iptal eder.
 * Çalıştırma: npm run test:e2e -- mcp-tokens
 */

import { test, expect, Page } from '@playwright/test';

const MCP_INIT = {
  jsonrpc: '2.0', id: 1, method: 'initialize',
  params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'e2e', version: '0' } },
};

/** Portföy seçim modalı sayfayı kapatmasın: oturuma ilk portföyü yaz */
async function ensurePortfolioSession(page: Page) {
  const info = await (await page.request.get('/api/session/info')).json();
  if (!info.has_session && info.portfolios?.length) {
    await page.request.post('/api/session/portfolio', { data: { portfolio: info.portfolios[0] } });
  }
}

test.describe('MCP Erişimi — kişisel API token', () => {
  test.beforeEach(async ({ page }) => {
    page.on('dialog', d => d.accept());   // iptal onayı (confirm)
    await ensurePortfolioSession(page);
  });

  test('oluştur → /mcp ile kullan → iptal et', async ({ page, playwright, baseURL }) => {
    const name = `e2e-${Date.now()}`;
    await page.goto('/yonetim/#tab-mcp');
    await expect(page.locator('#tab-mcp')).toBeVisible();

    await page.fill('#token-name', name);
    await page.click('#token-create-btn');

    await expect(page.locator('#token-value')).toHaveValue(/^frg_[A-Za-z0-9_-]{40,}$/);
    const token = await page.locator('#token-value').inputValue();
    await expect(page.locator('#token-snippet-code')).toHaveValue(new RegExp(`/mcp --header "Authorization: Bearer ${token}"`));
    await expect(page.locator('#token-snippet-desktop')).toHaveValue(/mcp-remote@/);

    const row = page.locator('#tokens-tbody tr', { hasText: name });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText(token.slice(0, 12));

    // Cookie'siz istemci — gerçek bir MCP istemcisi gibi yalnızca Bearer token
    // (config'deki storageState'i açıkça boşalt; yoksa admin oturum cookie'si de gider)
    const client = await playwright.request.newContext({ baseURL, storageState: { cookies: [], origins: [] } });
    const headers = {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
    };
    const init = await client.post('/mcp', { headers, data: MCP_INIT });
    expect(init.status()).toBe(200);
    expect((await init.json()).result?.serverInfo?.name).toBe('frigya');

    const mgmt = await client.get('/api/tokens', { headers: { Authorization: `Bearer ${token}` } });
    expect(mgmt.status()).toBe(401);

    await row.getByRole('button', { name: /İptal et/ }).click();
    await expect(row).toHaveCount(0);

    const after = await client.post('/mcp', { headers, data: MCP_INIT });
    expect(after.status()).toBe(401);
    await client.dispose();
  });
});
