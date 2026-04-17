/**
 * Price Worker — Arka planda asenkron fiyat güncelleme
 * Tüm tabs arasında BroadcastChannel ile senkronize
 */

let refreshInterval = 60; // saniye
let isRunning = false;
let intervalId = null;

const channel = new BroadcastChannel('price-updates');

// ── Worker mesajı dinle (ana sayfadan) ─────────────────────────────────────
channel.onmessage = (e) => {
  const { cmd, interval } = e.data;

  if (cmd === 'start') {
    console.log('[Worker] Başlat:', interval);
    refreshInterval = interval || 60;
    if (!isRunning) {
      isRunning = true;
      startAutoUpdate();
    }
  } else if (cmd === 'stop') {
    console.log('[Worker] Durdur');
    isRunning = false;
    if (intervalId) clearInterval(intervalId);
  } else if (cmd === 'update-interval') {
    refreshInterval = interval || 60;
    if (isRunning && intervalId) {
      clearInterval(intervalId);
      startAutoUpdate();
    }
  }
};

// ── Otomatik güncelleme ────────────────────────────────────────────────────
function startAutoUpdate() {
  if (intervalId) clearInterval(intervalId);

  intervalId = setInterval(async () => {
    try {
      const resp = await fetch('/api/fiyatlar/guncelle', { method: 'POST' });
      const data = await resp.json();

      if (data.ok && data.prices) {
        // localStorage'a kaydet (session boyunca)
        try {
          localStorage.setItem('_priceCache', JSON.stringify({
            timestamp: new Date().toISOString(),
            prices: data.prices,
          }));
        } catch (e) {
          console.warn('[Worker] localStorage quota exceeded:', e.message);
        }

        // Tüm tabs'e broadcast et
        channel.postMessage({
          type: 'price-update',
          prices: data.prices,
          fetched_at: data.fetched_at,
        });

        console.log('[Worker] Güncelleme tamamlandı:', Object.keys(data.prices).length, 'sembol');
      }
    } catch (e) {
      console.error('[Worker] Güncelleme hatası:', e.message);
    }
  }, refreshInterval * 1000);
}

console.log('[Worker] Başlatıldı');
