#!/usr/bin/env python3
"""Equity Intelligence: textos de los avisos de Telegram (formato HTML, con colores y enlace a la web).
Solo se usan datos reales calculados por los motores; aquí no se inventa nada."""
import html, os

SITE_URL = os.environ.get("SITE_URL", "https://ivanjalda.github.io/equity-intelligence/")
AVISO = "⚠️ <i>Información, no asesoramiento financiero. Invertir conlleva riesgo de perder dinero.</i>"


def esc(x):
    return html.escape(str(x), quote=False)


def num(x, d=2):
    s = f"{x:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fecha(iso):
    a, m, d = str(iso)[:10].split("-")
    return f"{d}/{m}/{a}"


def historial(sig, market):
    """Resumen del historial de señales, calculado igual que en la web: solo cuentan las señales
    que ya tienen un precio actual con el que medirlas."""
    n = len(sig or [])
    if not n:
        return "📈 <b>Historial de señales:</b> aún no hay señales registradas."
    spy = (market.get("SPY") or {}).get("c")
    rs, bs = [], []
    for s in sig:
        p = (market.get(s["ticker"]) or {}).get("c")
        if p and s.get("price"):
            r = (p / s["price"] - 1) * 100
            rs.append(r)
            if spy and s.get("spy"):
                bs.append((spy / s["spy"] - 1) * 100)
    if not rs:
        return f"📈 <b>Historial de señales:</b> {n} registradas, ninguna medible todavía."
    txt = f"📈 <b>Historial de señales:</b> {len(rs)} medidas de {n} · rendimiento medio {num(sum(rs) / len(rs), 1)} %"
    if bs:
        txt += f" frente a {num(sum(bs) / len(bs), 1)} % del S&amp;P 500"
    if len(rs) < 30:
        txt += "\n<i>Muestra todavía pequeña: no demuestra nada. Los resultados no se editan.</i>"
    return txt


def cierre(sig, market):
    return ["", historial(sig, market), "", f'🌐 <a href="{SITE_URL}">Ver el análisis completo en la web</a>', AVISO]


def _linea_compra(mg, t, e, iv, precio, nuevo):
    extra = []
    if e.get("horizon"):
        extra.append(f"plazo {esc(e['horizon'])}")
    if e.get("health"):
        extra.append(f"salud {esc(str(e['health']).lower())}")
    if e.get("cyclical"):
        extra.append("cíclica")
    if e.get("fiab"):
        extra.append(f"fiabilidad {esc(e['fiab'])}")
    return [f"{'🆕 ' if nuevo else '🟢 '}<b>{esc(t)}</b> · ${num(precio)} → valor ${num(iv)}",
            f"      margen de seguridad <b>{mg:.0f} %</b>" + (" · " + " · ".join(extra) if extra else "")]


def build_main(buys, new, market, sig, today):
    """buys: lista de (margen, ticker, item, valor_intrínseco) ya ordenada."""
    L = [f"📊 <b>EQUITY INTELLIGENCE</b> · {fecha(today)}", "<i>Lista principal · precios al cierre de mercado</i>", ""]
    if buys:
        L.append(f"🟢 <b>OPORTUNIDADES DE COMPRA ({len(buys)})</b>")
        for mg, t, e, iv in buys[:8]:
            L += _linea_compra(mg, t, e, iv, market[t]["c"], t in new)
        if len(buys) > 8:
            L.append(f"…y {len(buys) - 8} más en la web.")
    else:
        L.append("🟡 Hoy no hay oportunidades con margen de seguridad suficiente (mínimo 25 %).")
    return "\n".join(L + cierre(sig, market))


def build_broad(buys, new, n_analizadas, market, sig, today):
    """buys: lista de (margen, ticker, valor_intrínseco, item) ya ordenada."""
    L = [f"🔎 <b>MERCADO AMPLIO</b> · {fecha(today)}", f"<i>{n_analizadas} acciones de EE. UU. analizadas · precios al cierre</i>", ""]
    if buys:
        L.append(f"🟢 <b>OPORTUNIDADES DE COMPRA ({len(buys)})</b>")
        for mg, t, iv, e in buys[:8]:
            L += _linea_compra(mg, t, e, iv, market[t]["c"], t in new)
        if len(buys) > 8:
            L.append(f"…y {len(buys) - 8} más en la web.")
    else:
        L.append("🟡 Hoy no hay oportunidades con margen de seguridad suficiente.")
    return "\n".join(L + cierre(sig, market))


def build_macro(grupos, sig, market, today):
    """grupos: lista de dicts {tipo: 'Bonos'|'Materias primas'|'Índices', tickers: [...], resumen: str, nuevo: bool}."""
    L = [f"🌍 <b>BONOS, ÍNDICES Y MATERIAS PRIMAS</b> · {fecha(today)}", ""]
    for tipo, icono in (("Bonos", "🏦"), ("Índices", "📈"), ("Materias primas", "🛢️")):
        g = [x for x in grupos if x["tipo"] == tipo]
        if not g:
            continue
        L.append(f"{icono} <b>{tipo.upper()}</b>")
        for x in g:
            L.append(f"{'🆕 ' if x['nuevo'] else '🟢 '}{esc(x['resumen'])}")
            L.append(f"      <i>{esc(', '.join(x['tickers']))}</i>")
        L.append("")
    L.pop() if L and L[-1] == "" else None
    return "\n".join(L + cierre(sig, market))
