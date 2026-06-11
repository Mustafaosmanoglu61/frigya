# frigya-mcp

Frigya portföy analizini **MCP servisi** olarak sunar. Claude Desktop (veya herhangi bir MCP client) bu servisi çağırır; servis yerelde çalışıp `tax.db`'ye erişir.

## Mimari ilke

```
Claude Desktop / herhangi bir chat
        │  (MCP tool çağrısı)
        ▼
   frigya-mcp SERVİSİ   ← yerelde çalışır, DB sahibi
        │  (subprocess)
        ▼
   frigya-analiz scriptleri  →  ~/Tax_Portfolilo/webapp/tax.db
```

**Servis DB'ye erişir, client/skill doğrudan değil.** Bu sayede sandbox'taki bir agent yerel dosyaya hiç dokunmadan analiz alabilir. İş mantığı `~/.claude/skills/frigya-analiz/scripts/` altındaki scriptlerde tek hakikat kaynağı olarak kalır; bu server onları subprocess ile sarmalar.

## Araçlar (7)

| Tool | Tip | Ne yapar |
|---|---|---|
| `frigya_sembol_analiz` | okuma | Sembolün komple sentezi (DB + notlar + opsiyonel Massive piyasa passthrough) |
| `frigya_portfoy_tara` | okuma | Tüm açık pozisyonlar + watchlist + hedefler |
| `frigya_davranis_analiz` | okuma | Davranış paternleri (sektör, hold süresi, aylık trend) |
| `frigya_render_markdown` | okuma | Sentez JSON → kompakt markdown |
| `frigya_render_html` | okuma | Sentez JSON → HTML artifact (Chart.js grafikli) |
| `frigya_hedef_guncelle` | **yazma** | Taktiksel hedef/stop yaz (default dry-run, apply=true ile yazar) |
| `frigya_analist_hedef` | **yazma** | Uzun vade analyst range yaz (default dry-run) |

Yazma araçları **varsayılan dry-run** — `apply=true` verilmedikçe DB'ye dokunmaz.

## Massive Market verisi

Server Massive API'sine doğrudan çağrı yapmaz (key gerektirmez). `frigya_sembol_analiz`
opsiyonel `market_json` passthrough alır: client önce Massive MCP'sinden veriyi çeker,
JSON olarak geçirir, server teknik + DB + notları birleştirir. Beklenen yapı:

```json
{
  "teknik": {"sma": "<raw>", "rsi": "<raw>", "macd": "<raw>", "daily": "<aggs CSV>"},
  "haber": "<news CSV>",
  "meta": {"overview": "<csv>", "related": "<csv>", "market_status": "<csv>"}
}
```

## Claude Desktop kurulumu

`~/Library/Application Support/Claude/claude_desktop_config.json` içine (zaten eklendi):

```json
{
  "mcpServers": {
    "frigya": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["run", "--directory", "/Users/mustafa/Tax_Portfolilo/frigya-mcp", "python", "server.py"],
      "env": {
        "FRIGYA_SCRIPTS_DIR": "/Users/mustafa/.claude/skills/frigya-analiz/scripts",
        "DB_PATH": "/Users/mustafa/Tax_Portfolilo/webapp/tax.db"
      }
    }
  }
}
```

Ekledikten sonra **Claude Desktop'ı yeniden başlat**. Massive MCP'sini de ekli tutarsan
tam piyasa analizi için ikisini birlikte orkestre eder.

## Geliştirme / test

```bash
cd ~/Tax_Portfolilo/frigya-mcp

# Hızlı self-test (MCP client olmadan, tool'ları doğrudan dener)
uv run --python 3.12 python server.py --selftest

# Gerçek MCP stdio handshake testi
uv run --python 3.12 python _smoke.py
```

## Bağımlılıklar

- `uv` (Python sürümünü + venv'i yönetir; brew ile kuruldu)
- Python 3.12 (uv otomatik indirir)
- `mcp` SDK (pyproject.toml'da)
- Scriptler sadece stdlib kullanır (sqlite3, json, re) — ekstra bağımlılık yok

## Gelecek

- Frigya webapp `routers/ai.py` bu MCP'yi tool olarak çağırabilir (web tarafı entegrasyon)
- Massive doğrudan-fetch tool'u (MASSIVE_API_KEY env ile) — şu an passthrough yeterli
- Scriptler ileride bu projeye taşınabilir; `FRIGYA_SCRIPTS_DIR` repointlenir, kod değişmez
