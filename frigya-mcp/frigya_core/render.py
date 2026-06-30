"""
frigya_core.render — sentez dict → markdown / HTML (skill render/*.py'den port).

render_markdown(d) → str
render_html(d)     → str
"""
import json


def _fmt_money(v, default="—"):
    if v is None:
        return default
    return f"${v:,.2f}" if abs(v) < 10000 else f"${v:,.0f}"


def _fmt_pct(v, default="—"):
    if v is None:
        return default
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def render_markdown(d):
    sym = d["meta"]["symbol"]
    tag = d["meta"].get("tag") or "—"
    pos = d["position"]
    hist = d["frigya_history"]
    targets = d.get("targets", [])
    market = d.get("market", {})
    notes = d.get("notes", {})
    news = d.get("news") or {}
    meta_co = d.get("company_meta") or {}
    syn = d["synthesis"]
    gaps = d.get("data_gaps", [])

    out = []
    out.append(f"# {sym} — Frigya Analiz · {d['meta']['as_of']}")
    if tag and tag != "—":
        out.append(f"*Tag: {tag}*")
    if meta_co.get("name"):
        mcap = meta_co.get("market_cap_fmt") or ""
        out.append(f"*{meta_co['name']} · {mcap} · {meta_co.get('exchange', '')}*")
    out.append("")

    out.append("## Pozisyon")
    if pos["open_qty"]:
        out.append(f"- {syn.get('current_state') or '—'}")
        if pos.get("lot_count", 0) > 1:
            out.append(f"- Lot detay ({pos['lot_count']} lot):")
            for lot in pos.get("lots", []):
                line = f"  - {lot['date']} · {lot['qty']:.1f} @ {_fmt_money(lot['price'])} ({lot['portfolio']})"
                if "unrealized" in lot:
                    line += f" → {_fmt_money(lot['unrealized'])} / {_fmt_pct(lot['unrealized_pct'])}"
                out.append(line)
    else:
        out.append("- Açık pozisyon yok — temiz sayfa.")
    out.append("")

    if market and not market.get("_status"):
        out.append("## Piyasa")
        bits = []
        if market.get("last_close"): bits.append(f"Kapanış {_fmt_money(market['last_close'])}")
        if market.get("high_60d") and market.get("drawdown_from_peak") is not None:
            bits.append(f"60g zirve {_fmt_money(market['high_60d'])} ({_fmt_pct(market['drawdown_from_peak'])})")
        if market.get("stoch_pct_k") is not None: bits.append(f"Stoch %K {market['stoch_pct_k']:.1f}")
        if market.get("rsi14") is not None: bits.append(f"RSI {market['rsi14']:.1f}")
        out.append("- " + " · ".join(bits))
        if syn.get("short_term_view"):
            out.append(f"- **Kısa vade**: {syn['short_term_view']}")
        if syn.get("long_term_view"):
            out.append(f"- **Uzun vade**: {syn['long_term_view']}")
        out.append("")

    if targets:
        out.append("## Tanımlı Hedef/Stop")
        out.append("| Portföy | Hedef | Taban | Stop |")
        out.append("|---|---|---|---|")
        for t in targets:
            out.append(f"| {t['portfolio']} | {_fmt_money(t['hedef'])} | {_fmt_money(t['taban'])} | {_fmt_money(t['stop'])} |")
        if syn.get("target_position"):
            out.append(f"\n_{syn['target_position']}_")
        out.append("")

    sn_raw = notes.get("symbol_notes_raw", [])
    pn_raw = notes.get("portfolio_notes_raw", [])
    if sn_raw or pn_raw:
        out.append("## Notlar")
        overlay = notes.get("parsed_overlay", {})
        if overlay:
            bits = []
            if overlay.get("stop"):    bits.append(f"stop ${overlay['stop']}")
            if overlay.get("taban"):   bits.append(f"taban ${overlay['taban']}")
            if "hedef_min" in overlay:  bits.append(f"hedef ${overlay['hedef_min']}-${overlay['hedef_max']}")
            elif overlay.get("hedef"):  bits.append(f"hedef ${overlay['hedef']}")
            out.append(f"- **Senin notundaki seviyeler**: {', '.join(bits)} ← bunlar esas")
        for n in sn_raw[:2]:
            out.append(f"- _{(n.get('created_at') or '')[:10]} (sembol)_: {(n.get('note') or '')[:160]}")
        for n in pn_raw[:2]:
            out.append(f"- _{(n.get('created_at') or '')[:10]} ({n.get('portfolio')})_: {(n.get('note') or '')[:160]}")
        if notes.get("earnings_hint"):
            eh = notes["earnings_hint"]
            out.append(f"- ⚡ **Earnings ipucu**: {eh.get('date_hint') or '?'} — {eh.get('snippet', '')[:80]}")
        if notes.get("macro_mentions"):
            macros = list(set(m["name"] for m in notes["macro_mentions"]))
            out.append(f"- Makro mention'lar: {', '.join(macros[:5])}")
        out.append("")

    if hist["realized_count"]:
        out.append("## Frigya geçmişi (bu sembolde)")
        ah = hist.get("avg_hold_days")
        ah_str = f"{ah:.1f}g" if ah else "?g"
        out.append(
            f"- {hist['realized_count']} realized trade · win rate %{hist.get('win_rate_pct', 0):.0f} · "
            f"ort. hold {ah_str} · net K/Z {_fmt_money(hist.get('net_pnl'))}"
        )
        if syn.get("behavioral_warning"):
            out.append(f"- ⚠ {syn['behavioral_warning']}")
        out.append("")

    if news and news.get("articles"):
        out.append("## Haberler (son " + str(news["article_count"]) + ")")
        ss = news.get("sentiment_summary", {})
        out.append(f"- Sentiment: +{ss.get('positive', 0)} / -{ss.get('negative', 0)} / ~{ss.get('neutral', 0)} (net {ss.get('net_score', 0)})")
        for a in news["articles"][:4]:
            emoji = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(a.get("sentiment"), "")
            out.append(f"- {emoji} _{a.get('date', '')}_ **{a.get('title', '')}** ({a.get('publisher', '')})")
            if a.get("sentiment_reasoning"):
                out.append(f"  → {a['sentiment_reasoning'][:160]}")
        out.append("")

    if meta_co.get("related_tickers"):
        out.append(f"**İlişkili**: {', '.join(meta_co['related_tickers'])}")
        out.append("")

    if syn.get("actionable_decision") or syn.get("open_questions"):
        out.append("## Karar / Aksiyon")
        if syn.get("actionable_decision"):
            out.append(f"- **{syn['actionable_decision']}**")
        for q in syn.get("open_questions", []):
            out.append(f"- ❓ {q}")
        out.append("")

    if gaps:
        out.append("_Veri boşlukları: " + " · ".join(gaps) + "_")

    return "\n".join(out)


def render_html(d):
    sym = d["meta"]["symbol"]
    tag = d["meta"].get("tag") or ""
    pos = d.get("position", {})
    hist = d.get("frigya_history", {})
    targets = d.get("targets", [])
    market = d.get("market") or {}
    notes = d.get("notes", {})
    news = d.get("news") or {}
    meta_co = d.get("company_meta") or {}
    syn = d.get("synthesis", {})

    user_trades = []
    for lot in pos.get("lots", []):
        user_trades.append({"t": lot.get("date"), "p": lot.get("price"), "dir": "buy", "qty": lot.get("qty")})
    for rt in hist.get("recent_trades", []):
        user_trades.append({"t": rt.get("date"), "p": rt.get("price"), "dir": "sell", "qty": rt.get("qty")})

    verdict, verdict_class = "Bekle", "neut"
    if pos.get("unrealized_pct") is not None:
        if pos["unrealized_pct"] >= 10:
            verdict, verdict_class = "Kâr — değerlendir", "bull"
        elif pos["unrealized_pct"] <= -15:
            verdict, verdict_class = "Risk — gözden geçir", "bear"
    if not pos.get("open_qty"):
        verdict, verdict_class = "Pozisyon yok", "neut"

    bars = market.get("bars") or []
    bars_json = json.dumps([{"t": b["t"], "c": b["c"]} for b in bars if b.get("t") and b.get("c") is not None])
    user_trades_json = json.dumps(user_trades)

    metrics_html = ""
    def tile(label, value, klass=""):
        return f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value {klass}">{value}</div></div>'

    if pos.get("open_qty"):
        metrics_html += tile("Açık adet", f"{pos['open_qty']:.0f}")
        metrics_html += tile("Avg maliyet", _fmt_money(pos.get("avg_cost")))
    if market.get("last_close"):
        metrics_html += tile("Kapanış", _fmt_money(market["last_close"]))
    if pos.get("unrealized") is not None:
        metrics_html += tile("Unrealized", f"{_fmt_money(pos['unrealized'])} / {_fmt_pct(pos['unrealized_pct'])}",
                             "green" if pos["unrealized"] >= 0 else "red")
    if market.get("sma20"):
        metrics_html += tile("SMA20", _fmt_money(market["sma20"]),
                             "red" if market["last_close"] and market["last_close"] < market["sma20"] else "green")
    if market.get("rsi14") is not None:
        rsi_klass = "red" if market["rsi14"] > 70 else "orange" if market["rsi14"] > 60 else "" if 40 < market["rsi14"] < 60 else "green"
        metrics_html += tile("RSI(14)", f"{market['rsi14']:.1f}", rsi_klass)
    if market.get("stoch_pct_k") is not None:
        metrics_html += tile("Stoch %K", f"{market['stoch_pct_k']:.1f}",
                             "red" if market["stoch_pct_k"] < 20 or market["stoch_pct_k"] > 80 else "")
    if market.get("high_14d"):
        metrics_html += tile("14g zirve", _fmt_money(market["high_14d"]))
    if market.get("low_14d"):
        metrics_html += tile("14g dip", _fmt_money(market["low_14d"]))
    if market.get("drawdown_from_peak") is not None:
        metrics_html += tile("60g zirveden", _fmt_pct(market["drawdown_from_peak"]),
                             "red" if market["drawdown_from_peak"] < 0 else "green")

    signals_html = ""
    def card(name, badge_text, badge_class, desc):
        return f"""<div class="signal-card">
        <div class="signal-header"><span class="signal-name">{name}</span><span class="signal-badge {badge_class}">{badge_text}</span></div>
        <div class="signal-desc">{desc}</div></div>"""

    if market.get("sma10") and market.get("last_close"):
        below = market["last_close"] < market["sma10"]
        signals_html += card("Trend (kısa)", "Bearish" if below else "Bullish", "bear" if below else "bull",
                             f"Fiyat SMA10 ({_fmt_money(market['sma10'])}) {'altında' if below else 'üstünde'}.")
    if market.get("sma50") and market.get("last_close"):
        below = market["last_close"] < market["sma50"]
        signals_html += card("Trend (uzun)", "Bearish" if below else "Bullish", "bear" if below else "bull",
                             f"Fiyat SMA50 ({_fmt_money(market['sma50'])}) {'altında' if below else 'üstünde'}.")
    if market.get("rsi14") is not None:
        r = market["rsi14"]
        if r < 30:
            signals_html += card("RSI(14)", "Aşırı satım", "bull", f"{r:.1f} — tepki potansiyeli.")
        elif r > 70:
            signals_html += card("RSI(14)", "Aşırı alım", "bear", f"{r:.1f} — düzeltme riski.")
        else:
            signals_html += card("RSI(14)", "Nötr", "neut", f"{r:.1f} — yön belirsiz.")
    if market.get("stoch_pct_k") is not None:
        s = market["stoch_pct_k"]
        if s < 20:
            signals_html += card("Stochastic", "Aşırı satım", "bull", f"%K = {s:.1f} — dipte.")
        elif s > 80:
            signals_html += card("Stochastic", "Aşırı alım", "bear", f"%K = {s:.1f} — zirvede.")
    if market.get("macd"):
        h = market["macd"].get("histogram")
        if h is not None:
            signals_html += card("MACD", "Bearish" if h < 0 else "Bullish", "bear" if h < 0 else "bull",
                                 f"Histogram {h:+.2f} ({'düşüş' if h < 0 else 'yükseliş'} momentum)")
    if pos.get("open_qty"):
        signals_html += card("Pozisyon", f"{pos['open_qty']:.0f} adet", "info",
                             f"Avg {_fmt_money(pos.get('avg_cost'))} · {pos.get('lot_count', 0)} lot")
    else:
        signals_html += card("Pozisyon", "Yok", "neut", "Açık lot yok")
    if news and news.get("sentiment_summary"):
        ss = news["sentiment_summary"]
        net = ss.get("net_score", 0)
        klass = "bull" if net > 0.2 else "bear" if net < -0.2 else "neut"
        label = "Pozitif" if net > 0.2 else "Negatif" if net < -0.2 else "Karışık"
        signals_html += card("Haber sentiment", label, klass,
                             f"+{ss.get('positive', 0)} / -{ss.get('negative', 0)} (net {net})")

    notes_html = ""
    overlay = notes.get("parsed_overlay", {})
    if overlay:
        bits = []
        if overlay.get("stop"):    bits.append(f"stop ${overlay['stop']}")
        if overlay.get("taban"):   bits.append(f"taban ${overlay['taban']}")
        if "hedef_min" in overlay:  bits.append(f"hedef ${overlay['hedef_min']}-${overlay['hedef_max']}")
        elif overlay.get("hedef"):  bits.append(f"hedef ${overlay['hedef']}")
        notes_html += f'<div class="note-card note-self"><div class="note-meta">Senin notundaki seviyeler (esas)</div><strong>{", ".join(bits)}</strong></div>'
    for n in notes.get("symbol_notes_raw", [])[:3]:
        txt = (n.get("note") or "")[:280].replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        notes_html += f'<div class="note-card"><div class="note-meta">{(n.get("created_at") or "")[:10]} · sembol notu</div>{txt}</div>'
    for n in notes.get("portfolio_notes_raw", [])[:2]:
        txt = (n.get("note") or "")[:240].replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        notes_html += f'<div class="note-card"><div class="note-meta"><span class="note-pf-badge">{n.get("portfolio", "")}</span> {(n.get("created_at") or "")[:10]} · portföy notu</div>{txt}</div>'
    eh = notes.get("earnings_hint")
    if eh:
        notes_html += f'<div class="note-card note-earn">⚡ <strong>Earnings ipucu</strong>: {eh.get("date_hint") or "?"} — {eh.get("snippet", "")[:200]}</div>'

    trades_html = ""
    for rt in hist.get("recent_trades", [])[-6:]:
        klass = "green" if (rt.get("pnl") or 0) >= 0 else "red"
        trades_html += f"""<tr>
            <td>{rt.get('date')}</td><td>{rt.get('qty'):.1f}</td><td>{_fmt_money(rt.get('price'))}</td>
            <td class="{klass}">{_fmt_money(rt.get('pnl'))}</td>
            <td class="{klass}">{rt.get('pnl_pct', 0):+.1f}%</td>
            <td>{rt.get('portfolio', '')}</td>
        </tr>"""

    news_html = ""
    for a in (news.get("articles") or [])[:5]:
        emoji = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(a.get("sentiment"), "")
        title = (a.get("title") or "").replace("<", "&lt;").replace(">", "&gt;")
        reasoning = (a.get("sentiment_reasoning") or "")[:200].replace("<", "&lt;").replace(">", "&gt;")
        news_html += f"""<div class="news-card">
            <div class="news-head">{emoji} <strong>{title}</strong> <span class="news-meta">— {a.get('publisher', '')} · {a.get('date', '')}</span></div>
            {f'<div class="news-reasoning">{reasoning}</div>' if reasoning else ''}
        </div>"""

    targets_html = ""
    for t in targets:
        targets_html += f"""<tr><td>{t['portfolio']}</td><td>{_fmt_money(t.get('hedef'))}</td>
            <td>{_fmt_money(t.get('taban'))}</td><td>{_fmt_money(t.get('stop'))}</td></tr>"""

    related = (meta_co or {}).get("related_tickers") or []
    related_str = ", ".join(related) if related else "—"

    decision_html = ""
    if syn.get("actionable_decision"):
        decision_html += f"<p><strong>{syn['actionable_decision']}</strong></p>"
    if syn.get("note_evaluation"):
        decision_html += f"<p style='color: var(--color-text-secondary)'>{syn['note_evaluation']}</p>"
    if syn.get("behavioral_warning"):
        decision_html += f"<p style='color: var(--color-text-secondary)'>⚠ {syn['behavioral_warning']}</p>"

    company_line = ""
    if meta_co.get("name"):
        company_line = f"{meta_co['name']} · {meta_co.get('market_cap_fmt') or ''} · {meta_co.get('exchange', '')}"

    html = f"""<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --font-sans: -apple-system, 'Segoe UI', Roboto, sans-serif;
  --color-text-primary: var(--color-text-primary, #1a1a1a);
  --color-text-secondary: var(--color-text-secondary, #666);
  --color-background-primary: var(--color-background-primary, #fff);
  --color-background-secondary: var(--color-background-secondary, #f4f4f0);
  --color-border-tertiary: var(--color-border-tertiary, #e3e3df);
  --border-radius-md: 6px;
  --border-radius-lg: 10px;
}}
.wrap {{ font-family: var(--font-sans); padding: 1rem 0; color: var(--color-text-primary); }}
.top-bar {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem; flex-wrap: wrap; gap: 8px; }}
.ticker-name {{ font-size: 18px; font-weight: 500; }}
.ticker-sub {{ font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }}
.tag-badge {{ display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 99px; background: #E6EEF7; color: #185FA5; font-weight: 500; margin-left: 6px; vertical-align: middle; }}
.verdict-badge {{ display: inline-block; font-size: 12px; padding: 4px 10px; border-radius: 99px; font-weight: 600; }}
.verdict-badge.bull {{ background: #EAF3DE; color: #27500A; }}
.verdict-badge.bear {{ background: #FCEBEB; color: #791F1F; }}
.verdict-badge.neut {{ background: var(--color-background-secondary); color: var(--color-text-secondary); }}
.metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 8px; margin-bottom: 1rem; }}
.metric {{ background: var(--color-background-secondary); border-radius: var(--border-radius-md); padding: 10px 12px; }}
.metric-label {{ font-size: 11px; color: var(--color-text-secondary); margin-bottom: 4px; }}
.metric-value {{ font-size: 15px; font-weight: 500; }}
.metric-value.red {{ color: #A32D2D; }}
.metric-value.green {{ color: #3B6D11; }}
.metric-value.orange {{ color: #854F0B; }}
.chart-area {{ background: var(--color-background-primary); border: 0.5px solid var(--color-border-tertiary); border-radius: var(--border-radius-lg); padding: 12px; margin-bottom: 8px; }}
.chart-title {{ font-size: 11px; font-weight: 500; color: var(--color-text-secondary); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }}
canvas {{ display: block; width: 100%; }}
.signal-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin-top: 8px; }}
.signal-card {{ border: 0.5px solid var(--color-border-tertiary); border-radius: var(--border-radius-md); padding: 10px 12px; }}
.signal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
.signal-name {{ font-size: 12px; color: var(--color-text-secondary); }}
.signal-badge {{ font-size: 11px; font-weight: 500; padding: 2px 8px; border-radius: 99px; }}
.bear {{ background: #FCEBEB; color: #791F1F; }}
.bull {{ background: #EAF3DE; color: #27500A; }}
.neut {{ background: var(--color-background-secondary); color: var(--color-text-secondary); }}
.info {{ background: #E6EEF7; color: #185FA5; }}
.signal-desc {{ font-size: 12px; }}
.section {{ margin-top: 12px; }}
.section h3 {{ font-size: 12px; font-weight: 500; color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th, td {{ padding: 6px 8px; text-align: left; border-bottom: 0.5px solid var(--color-border-tertiary); }}
th {{ font-weight: 500; color: var(--color-text-secondary); font-size: 11px; }}
tr:last-child td {{ border-bottom: none; }}
td.red {{ color: #A32D2D; }} td.green {{ color: #3B6D11; }}
.note-card {{ border-left: 3px solid #7F77DD; background: var(--color-background-secondary); padding: 8px 12px; border-radius: var(--border-radius-md); margin-bottom: 6px; font-size: 12.5px; }}
.note-meta {{ font-size: 11px; color: var(--color-text-secondary); margin-bottom: 4px; }}
.note-self {{ border-left-color: #3B6D11; background: #F1F7E8; }}
.note-earn {{ border-left-color: #EF9F27; background: #FAEEDA; color: #633806; }}
.note-pf-badge {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; background: #E6EEF7; color: #185FA5; font-weight: 500; }}
.news-card {{ border-left: 2px solid var(--color-border-tertiary); padding: 6px 10px; margin-bottom: 6px; font-size: 12px; }}
.news-meta {{ color: var(--color-text-secondary); font-weight: normal; font-size: 11px; }}
.news-reasoning {{ font-size: 11px; color: var(--color-text-secondary); margin-top: 3px; }}
.decision-box {{ background: var(--color-background-secondary); border-radius: var(--border-radius-md); padding: 10px 12px; margin-top: 8px; font-size: 13px; line-height: 1.5; }}
</style>

<div class="wrap">

<div class="top-bar">
  <div>
    <div class="ticker-name">{sym}{f' <span class="tag-badge">{tag.upper()}</span>' if tag else ''}</div>
    <div class="ticker-sub">{company_line} · {d['meta']['as_of']}</div>
  </div>
  <span class="verdict-badge {verdict_class}">{verdict}</span>
</div>

<div class="metrics">{metrics_html}</div>

{'<div class="chart-area"><div class="chart-title">Günlük kapanış (son 60g) — kendi alış/satış işlemlerin işaretli</div><canvas id="priceChart" height="180"></canvas></div>' if bars_json != '[]' else ''}

<div class="signal-grid">{signals_html}</div>

{f'<div class="section"><h3>Notlar</h3>{notes_html}</div>' if notes_html else ''}

{f'<div class="section"><h3>Tanımlı hedef/stop</h3><table><thead><tr><th>Portföy</th><th>Hedef</th><th>Taban</th><th>Stop</th></tr></thead><tbody>{targets_html}</tbody></table></div>' if targets_html else ''}

{('<div class="section"><h3>Frigya geçmişi · son trade&#39;ler</h3><table><thead><tr><th>Tarih</th><th>Adet</th><th>Fiyat</th><th>K/Z</th><th>%</th><th>Portföy</th></tr></thead><tbody>' + trades_html + '</tbody></table></div>') if trades_html else ''}

{f'<div class="section"><h3>Haberler ({news.get("article_count", 0)} adet)</h3>{news_html}</div>' if news_html else ''}

{f'<div class="section"><h3>İlişkili semboller</h3><p style="font-size: 12px">{related_str}</p></div>' if related else ''}

{f'<div class="section"><h3>Karar</h3><div class="decision-box">{decision_html}</div></div>' if decision_html else ''}

</div>

{'<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>' if bars_json != '[]' else ''}
{f'''<script>
const bars = {bars_json};
const userTrades = {user_trades_json};
const closes = bars.map(b => b.c);
const labels = bars.map(b => {{ const dt = new Date(b.t); return (dt.getMonth()+1)+'/'+dt.getDate(); }});
function sma(arr, p) {{ return arr.map((_, i) => i < p-1 ? null : arr.slice(i-p+1, i+1).reduce((a,b)=>a+b,0)/p); }}
const sma20 = sma(closes, 20);
const sma50 = sma(closes, 50);
const buyPts = bars.map(b => {{ const t = userTrades.find(u => (new Date(b.t).toISOString().slice(0,10) === u.t)); return (t && t.dir === 'buy') ? t.p : null; }});
const sellPts = bars.map(b => {{ const t = userTrades.find(u => (new Date(b.t).toISOString().slice(0,10) === u.t)); return (t && t.dir === 'sell') ? t.p : null; }});
const isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
const gridC = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
const textC = isDark ? '#aaa' : '#888';
new Chart(document.getElementById('priceChart'), {{
  type: 'line',
  data: {{ labels, datasets: [
    {{ label: 'Kapanış', data: closes, borderColor: '#185FA5', borderWidth: 1.5, pointRadius: 0, tension: 0.3 }},
    {{ label: 'SMA20', data: sma20, borderColor: '#EF9F27', borderWidth: 1, borderDash: [5,3], pointRadius: 0, tension: 0.3 }},
    {{ label: 'SMA50', data: sma50, borderColor: '#639922', borderWidth: 1.5, pointRadius: 0, tension: 0.3 }},
    {{ label: 'Alış', data: buyPts, borderColor: '#3B6D11', backgroundColor: '#3B6D11', pointRadius: 7, pointStyle: 'triangle', showLine: false }},
    {{ label: 'Satış', data: sellPts, borderColor: '#A32D2D', backgroundColor: '#A32D2D', pointRadius: 7, pointStyle: 'triangle', rotation: 180, showLine: false }}
  ]}},
  options: {{
    responsive: true, animation: false,
    plugins: {{ legend: {{ labels: {{ color: textC, font: {{size:11}}, boxWidth: 20, usePointStyle: true }} }} }},
    scales: {{
      x: {{ ticks: {{ color: textC, font: {{size:10}}, maxTicksLimit: 12 }}, grid: {{ color: gridC }} }},
      y: {{ ticks: {{ color: textC, font: {{size:10}}, callback: v => '$'+v }}, grid: {{ color: gridC }} }}
    }}
  }}
}});
</script>''' if bars_json != '[]' else ''}
"""
    return html
