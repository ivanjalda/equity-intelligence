#!/usr/bin/env python3
"""Equity Intrinsic: textos de los avisos de Telegram (formato HTML, con colores y enlace a la web).
Solo se usan datos reales calculados por los motores; aquí no se inventa nada.

Cada función build_* devuelve el texto en español (que enviará el motor al canal en español) y, además,
envía la misma información en inglés al canal inglés si existe TELEGRAM_CHAT_ID_EN. Si el canal inglés
no está configurado o falla, el aviso en español no se ve afectado."""
import html, os, re, urllib.parse, urllib.request

SITE_URL = os.environ.get("SITE_URL", "https://equityintrinsic.com/")
AVISO = "⚠️ <i>Información, no asesoramiento financiero. Invertir conlleva riesgo de perder dinero.</i>"
AVISO_EN = "⚠️ <i>Information, not financial advice. Investing involves the risk of losing money.</i>"
MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
EN_HOR = {"largo": "long term", "medio": "medium term", "corto": "short term"}
EN_SAL = {"sólida": "solid", "aceptable": "acceptable", "frágil": "fragile"}
EN_FIA = {"alta": "high", "media": "medium", "baja": "low"}
EN_DESC = {
    "bonos del tesoro a 20 años": "20-year Treasury bonds", "bonos del tesoro a 10 años": "10-year Treasury bonds",
    "bonos del tesoro a 2 años": "2-year Treasury bonds", "bonos del tesoro (referencia: 10 años)": "Treasury bonds (reference: 10-year)",
    "bonos de ee. uu. (referencia: tesoro a 10 años)": "US bonds (reference: 10-year Treasury)",
    "letras del tesoro a 3 meses": "3-month Treasury bills", "bonos del tesoro ligados a la inflación": "inflation-linked Treasury bonds",
    "bonos de empresas de alta calidad": "investment-grade corporate bonds", "bonos de empresas de alto riesgo": "high-yield corporate bonds",
    "bonos de empresas de países emergentes": "emerging-market corporate bonds",
    "oro": "gold", "plata": "silver", "platino": "platinum", "paladio": "palladium", "petróleo (wti)": "oil (WTI)",
    "petróleo (referencia wti)": "oil (WTI reference)", "gas natural": "natural gas", "cobre": "copper",
    "índice global de materias primas": "global commodities index", "índice global de alimentos": "global food index",
    "500 mayores empresas": "500 largest companies", "100 mayores empresas del nasdaq": "100 largest Nasdaq companies",
    "empresas fuera de las 500 mayores": "companies outside the 500 largest",
}
EN_TIPO = {"Bonos": "BONDS", "Índices": "INDEXES", "Materias primas": "COMMODITIES"}


def _en_num(txt):
    """'1.234,5' (formato español) -> '1,234.5'."""
    return txt.replace(".", "§").replace(",", ".").replace("§", ",")


def _ord(n):
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _desc_en(d):
    return EN_DESC.get(d.strip().lower(), d.strip().lower())


def traducir_resumen(es):
    """Traduce las tres frases que generan los motores de bonos, materias primas e índices."""
    m = re.match(r"^(.+): (rendimiento|diferencial sobre el tesoro) del ([\d.,]+) %, en el percentil (\d+) de la última década\.$", es)
    if m:
        d = _desc_en(m.group(1))
        lab = "yield" if m.group(2) == "rendimiento" else "spread over Treasuries"
        return f"{d[0].upper() + d[1:]}: {lab} of {_en_num(m.group(3))}%, at the {_ord(m.group(4))} percentile of the last decade."
    m = re.match(r"^Precio real del (.+) en el percentil (\d+) de su historia \((\d+) años\)\.$", es)
    if m:
        return f"Real price of {_desc_en(m.group(1))} at the {_ord(m.group(2))} percentile of its history ({m.group(3)} years)."
    m = re.match(r"^(.+): margen de seguridad agregado del ([\d.,\-]+) %$", es)
    if m:
        d = _desc_en(m.group(1))
        return f"{d[0].upper() + d[1:]}: aggregate margin of safety of {_en_num(m.group(2))}%"
    return es


def enviar_en(text):
    """Envía el aviso en inglés al canal inglés. Nunca interrumpe el aviso en español."""
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID_EN")
    if not tok or not chat:
        print("Telegram inglés no configurado: se omite el aviso en inglés.")
        return
    if len(text) > 4000:
        text = text[:3990].rsplit("\n", 1)[0]
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=body), timeout=30)
        print("Aviso en inglés enviado.")
    except urllib.error.HTTPError as e:
        print(f"Telegram inglés rechazó el mensaje (código {e.code}): {e.read()[:300]!r}")
    except Exception as e:
        print(f"Telegram inglés no respondió: {e}")


def esc(x):
    return html.escape(str(x), quote=False)


def num(x, d=2, lg="es"):
    s = f"{x:,.{d}f}"
    if lg == "en":
        return s
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def pc(x, d=0, lg="es"):
    return f"{x:.{d}f}%" if lg == "en" else f"{x:.{d}f} %"


def fecha(iso, lg="es"):
    a, m, d = str(iso)[:10].split("-")
    if lg == "en":
        return f"{MESES[int(m) - 1]} {int(d)}, {a}"
    return f"{d}/{m}/{a}"


def historial(sig, market, lg="es"):
    """Resumen del historial de señales, calculado igual que en la web: solo cuentan las señales
    que ya tienen un precio actual con el que medirlas."""
    en = lg == "en"
    n = len(sig or [])
    if not n:
        return "📈 <b>Signal track record:</b> no signals recorded yet." if en else "📈 <b>Historial de señales:</b> aún no hay señales registradas."
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
        return (f"📈 <b>Signal track record:</b> {n} recorded, none measurable yet." if en
                else f"📈 <b>Historial de señales:</b> {n} registradas, ninguna medible todavía.")
    if en:
        txt = f"📈 <b>Signal track record:</b> {len(rs)} measured out of {n} · average return {pc(sum(rs) / len(rs), 1, lg)}"
        if bs:
            txt += f" versus {pc(sum(bs) / len(bs), 1, lg)} for the S&amp;P 500"
        if len(rs) < 30:
            txt += "\n<i>Sample still small: it proves nothing. Results are never edited.</i>"
        return txt
    txt = f"📈 <b>Historial de señales:</b> {len(rs)} medidas de {n} · rendimiento medio {num(sum(rs) / len(rs), 1)} %"
    if bs:
        txt += f" frente a {num(sum(bs) / len(bs), 1)} % del S&amp;P 500"
    if len(rs) < 30:
        txt += "\n<i>Muestra todavía pequeña: no demuestra nada. Los resultados no se editan.</i>"
    return txt


def cierre(sig, market, lg="es"):
    if lg == "en":
        return ["", historial(sig, market, lg), "", f'🌐 <a href="{SITE_URL.rstrip("/")}/en/">See the full analysis on the website</a>', AVISO_EN]
    return ["", historial(sig, market), "", f'🌐 <a href="{SITE_URL}">Ver el análisis completo en la web</a>', AVISO]


def _linea_compra(mg, t, e, iv, precio, nuevo, lg="es"):
    extra = []
    if lg == "en":
        hz, sl, fb = str(e.get("horizon") or "").lower(), str(e.get("health") or "").lower(), str(e.get("fiab") or "").lower()
        if hz:
            extra.append(EN_HOR.get(hz, esc(hz)))
        if sl:
            extra.append(f"{EN_SAL.get(sl, esc(sl))} health")
        if e.get("cyclical"):
            extra.append("cyclical")
        if fb:
            extra.append(f"{EN_FIA.get(fb, esc(fb))} reliability")
        return [f"{'🆕 ' if nuevo else '🟢 '}<b>{esc(t)}</b> · ${num(precio, 2, lg)} → value ${num(iv, 2, lg)}",
                f"      margin of safety <b>{pc(mg, 0, lg)}</b>" + (" · " + " · ".join(extra) if extra else "")]
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


def _aviso_compras(buys, new, market, sig, today, lg, titulo, subtitulo, filas):
    en = lg == "en"
    L = [f"{titulo} · {fecha(today, lg)}", subtitulo, ""]
    if buys:
        L.append(f"🟢 <b>{'BUY OPPORTUNITIES' if en else 'OPORTUNIDADES DE COMPRA'} ({len(buys)})</b>")
        for mg, t, e, iv in filas[:8]:
            L += _linea_compra(mg, t, e, iv, market[t]["c"], t in new, lg)
        if len(buys) > 8:
            L.append(f"…and {len(buys) - 8} more on the website." if en else f"…y {len(buys) - 8} más en la web.")
    else:
        if en:
            L.append("🟡 Today there are no opportunities with a sufficient margin of safety" + (" (minimum 25%)." if titulo.startswith("📊") else "."))
        else:
            L.append("🟡 Hoy no hay oportunidades con margen de seguridad suficiente" + (" (mínimo 25 %)." if titulo.startswith("📊") else "."))
    return "\n".join(L + cierre(sig, market, lg))


def build_main(buys, new, market, sig, today):
    """buys: lista de (margen, ticker, item, valor_intrínseco) ya ordenada. Devuelve el texto en español
    y envía la versión inglesa al canal inglés."""
    filas = [(mg, t, e, iv) for mg, t, e, iv in buys]
    try:
        enviar_en(_aviso_compras(buys, new, market, sig, today, "en", "📊 <b>EQUITY INTRINSIC</b>", "<i>Main list · end-of-day prices</i>", filas))
    except Exception as ex:
        print(f"Aviso en inglés (lista principal) no preparado: {ex}")
    return _aviso_compras(buys, new, market, sig, today, "es", "📊 <b>EQUITY INTRINSIC</b>", "<i>Lista principal · precios al cierre de mercado</i>", filas)


def build_broad(buys, new, n_analizadas, market, sig, today):
    """buys: lista de (margen, ticker, valor_intrínseco, item) ya ordenada. Devuelve el texto en español
    y envía la versión inglesa al canal inglés."""
    filas = [(mg, t, e, iv) for mg, t, iv, e in buys]
    try:
        enviar_en(_aviso_compras(buys, new, market, sig, today, "en", "🔎 <b>BROAD MARKET</b>", f"<i>{n_analizadas} US stocks analyzed · end-of-day prices</i>", filas))
    except Exception as ex:
        print(f"Aviso en inglés (mercado amplio) no preparado: {ex}")
    return _aviso_compras(buys, new, market, sig, today, "es", "🔎 <b>MERCADO AMPLIO</b>", f"<i>{n_analizadas} acciones de EE. UU. analizadas · precios al cierre</i>", filas)


def _macro(grupos, sig, market, today, lg):
    en = lg == "en"
    L = [f"🌍 <b>{'BONDS, INDEXES AND COMMODITIES' if en else 'BONOS, ÍNDICES Y MATERIAS PRIMAS'}</b> · {fecha(today, lg)}", ""]
    for tipo, icono in (("Bonos", "🏦"), ("Índices", "📈"), ("Materias primas", "🛢️")):
        g = [x for x in grupos if x["tipo"] == tipo]
        if not g:
            continue
        L.append(f"{icono} <b>{EN_TIPO[tipo] if en else tipo.upper()}</b>")
        for x in g:
            L.append(f"{'🆕 ' if x['nuevo'] else '🟢 '}{esc(traducir_resumen(x['resumen']) if en else x['resumen'])}")
            L.append(f"      <i>{esc(', '.join(x['tickers']))}</i>")
        L.append("")
    L.pop() if L and L[-1] == "" else None
    return "\n".join(L + cierre(sig, market, lg))


def build_macro(grupos, sig, market, today):
    """grupos: lista de dicts {tipo: 'Bonos'|'Materias primas'|'Índices', tickers: [...], resumen: str, nuevo: bool}.
    Devuelve el texto en español y envía la versión inglesa al canal inglés."""
    try:
        enviar_en(_macro(grupos, sig, market, today, "en"))
    except Exception as ex:
        print(f"Aviso en inglés (bonos, índices y materias primas) no preparado: {ex}")
    return _macro(grupos, sig, market, today, "es")
