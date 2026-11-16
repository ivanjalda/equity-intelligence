#!/usr/bin/env python3
"""Equity Intrinsic: resumen diario por correo. Solo datos reales de data/*.json; nada inventado.
Genera data/correo.html y data/correo.txt (español) y data/correo-en.html y data/correo-en.txt (inglés).
Envía cada idioma a su propia lista de Brevo: BREVO_LIST_ID (español) y BREVO_LIST_ID_EN (inglés).
Sin BREVO_API_KEY solo genera la vista previa (no envía nada). Sin BREVO_LIST_ID_EN no se envía el inglés."""
import html, json, os, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from engine import verdict, rank, spread  # mismas reglas que la web y Telegram

DATA = Path(os.environ.get("DATA_DIR", "data"))
SITE0 = os.environ.get("SITE_URL", "https://equityintrinsic.com/").rstrip("/") + "/"
SITE = SITE0
LG = "es"
TODAY = date.today().isoformat()
IDX = [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DIA", "Dow Jones"), ("IWM", "Russell 2000")]
MAT = [("GLD", "Oro"), ("SLV", "Plata"), ("USO", "Petróleo"), ("UNG", "Gas natural"), ("CPER", "Cobre")]
BON = [("TLT", "Bonos EE. UU. largo plazo"), ("IEF", "Bonos EE. UU. medio plazo"), ("SHY", "Bonos EE. UU. corto plazo"), ("LQD", "Deuda de empresas sólidas"), ("HYG", "Deuda de empresas de más riesgo")]
NEXUS = os.environ.get("NEXUS_URL", "https://nexusterminalalerts.com")
METODOS = ("dcf", "graham", "multiples", "pb", "gnum")
EN_NAMES = {"Oro": "Gold", "Plata": "Silver", "Petróleo": "Oil", "Gas natural": "Natural gas", "Cobre": "Copper",
            "Bonos EE. UU. largo plazo": "US long-term bonds", "Bonos EE. UU. medio plazo": "US medium-term bonds", "Bonos EE. UU. corto plazo": "US short-term bonds",
            "Deuda de empresas sólidas": "Investment-grade corporate debt", "Deuda de empresas de más riesgo": "Higher-risk corporate debt"}
EN_TIPS = [
    ("Margin of safety", "It is the difference between what a business is worth and what you pay for it. The cheaper you buy relative to its value, the more cushion you have if your calculation is wrong. It is an idea from Benjamin Graham."),
    ("Intrinsic value", "It is what a company is worth based on the cash it will be able to generate, not on today's price. That is why we calculate it with three different methods and check whether they agree."),
    ("P/E ratio", "Price divided by earnings per share. A P/E of 15 means you pay 15 years of current earnings. Lower is not always better: compare it with the company's own history and its sector."),
    ("Free cash flow", "It is the money a company has left after paying its expenses and investments. It is hard to disguise, which is why it is the basis of one of our valuation methods."),
    ("Cyclical companies", "Their earnings rise and fall with the economy (oil, mining, cars…). Valuing them on a single year is misleading, so we use the average of several years."),
    ("Bonds and interest rates", "When interest rates rise, the price of existing bonds falls, and vice versa. The longer the bond, the more it moves."),
    ("13F reports", "Large US managers must report their portfolios to the SEC every quarter, up to 45 days late. They help you see trends, not copy trades blindly."),
]
EN_HOR = {"largo": "long term", "medio": "medium term", "corto": "short term"}
EN_SAL = {"sólida": "solid", "aceptable": "acceptable", "frágil": "fragile"}
EN_FIA = {"alta": "High", "media": "Medium", "baja": "Low"}
EN_ROL = {"Consejero": "Director", "Accionista >10 %": "10% owner", "Directivo": "Officer"}
VERDE, ROJO, ORO, TXT, SUAVE = "#0b8043", "#c5221f", "#b8860b", "#1f2937", "#6b7280"

TIPS = [
    ("Margen de seguridad", "Es la diferencia entre lo que vale un negocio y lo que pagas por él. Cuanto más barato compras respecto a su valor, más colchón tienes si te equivocas en el cálculo. Es una idea de Benjamin Graham."),
    ("Valor intrínseco", "Es lo que vale una empresa por el dinero que será capaz de generar, no por lo que marque el precio hoy. Por eso lo calculamos con tres métodos distintos y miramos si coinciden."),
    ("PER", "Precio entre beneficio por acción. Un PER de 15 significa que pagas 15 años de beneficios actuales. Más bajo no siempre es mejor: hay que compararlo con el propio historial de la empresa y con su sector."),
    ("Flujo de caja libre", "Es el dinero que le queda a una empresa después de pagar sus gastos y sus inversiones. Es difícil de maquillar, por eso es la base de uno de nuestros métodos de valoración."),
    ("Empresas cíclicas", "Sus beneficios suben y bajan con la economía (petróleo, minería, automóviles…). Valorarlas con un solo año engaña, así que usamos la media de varios años."),
    ("Bonos y tipos de interés", "Cuando suben los tipos de interés, el precio de los bonos ya emitidos baja, y al revés. Cuanto más largo es el bono, más se mueve."),
    ("Informes 13F", "Los grandes gestores de EE. UU. deben informar a la SEC de sus carteras cada trimestre, con hasta 45 días de retraso. Sirven para ver tendencias, no para copiar operaciones a ciegas."),
]


def load(n, d):
    p = DATA / n
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return d


def e(x):
    return html.escape(str(x), quote=True)


def num(x, d=2):
    if LG == "en":
        return f"{x:,.{d}f}"
    return f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def tr(es, en):
    return en if LG == "en" else es


def pc(x, d=0):
    """Porcentaje con el formato de cada idioma."""
    return f"{x:.{d}f}%" if LG == "en" else f"{x:.{d}f} %"


def dinero(x, d=2):
    return f"${num(x, d)}"


MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fecha(iso):
    a, m, d = str(iso)[:10].split("-")
    if LG == "en":
        return f"{MESES[int(m) - 1]} {int(d)}, {a}"
    return f"{d}/{m}/{a}"


def pct(ch):
    col = VERDE if ch >= 0 else ROJO
    return f'<span style="font-weight:bold;color:{col}">{"+" if ch >= 0 else ""}{num(ch)}{"%" if LG == "en" else " %"}</span>'


def calcular(vals, market):
    """Devuelve (oportunidades ordenadas, conteo de veredictos) con las mismas reglas que la web."""
    ops, cuenta = [], {"COMPRAR": 0, "ESPERAR": 0, "CARO": 0, "REVISAR": 0, "total": 0}
    for t, it in (vals.get("items") or {}).items():
        c = (market.get(t) or {}).get("c")
        nums = [it[k] for k in METODOS if isinstance(it.get(k), (int, float)) and it[k] > 0]
        if not c or not nums or it.get("type", "ACCIONES") != "ACCIONES":
            continue
        iv = sum(nums) / len(nums)
        mg = (iv - c) / iv * 100
        v = verdict(mg, it.get("health"), it.get("fiab"))
        cuenta["total"] += 1
        if v in cuenta:
            cuenta[v] += 1
        if v == "COMPRAR":
            ops.append((rank(mg, it.get("health"), it.get("cyclical"), spread(it), it.get("fiab")), mg, t, iv, c, it))
    ops.sort(key=lambda x: x[0], reverse=True)
    return ops, cuenta


def cambios(market, pares):
    r = []
    for t, n in pares:
        m = market.get(t) or {}
        if m.get("c") and m.get("p"):
            r.append((n, m["c"], (m["c"] / m["p"] - 1) * 100))
    return r


def movers(market, vals):
    L = []
    for t, m in market.items():
        if m.get("type") == "ACCIONES" and m.get("c") and m.get("p"):
            nombre = ((vals.get("items") or {}).get(t) or {}).get("name") or ""
            L.append((t, nombre, m["c"], (m["c"] / m["p"] - 1) * 100))
    L.sort(key=lambda x: x[3], reverse=True)
    return L[:5], [x for x in L[::-1][:5] if x[3] < 0]


def filas(items, vacio):
    """items: lista de (izquierda_html, derecha_html)."""
    if not items:
        return f'<div style="font-size:13px;color:{SUAVE};padding:4px 0">{vacio}</div>'
    return "".join(
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-bottom:1px solid #f0f1f3"><tr>'
        f'<td style="padding:6px 0;font-size:13px;color:{TXT}">{i}</td><td align="right" style="padding:6px 0;font-size:13px;white-space:nowrap">{d}</td></tr></table>'
        for i, d in items)


def caja(titulo, cuerpo, nota=""):
    n = f'<div style="font-size:11px;color:{SUAVE};margin-top:6px;line-height:15px">{nota}</div>' if nota else ""
    return (f'<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;background:#ffffff">'
            f'<div style="font-weight:bold;font-size:15px;color:#111827;margin-bottom:6px">{titulo}</div>{cuerpo}{n}</div>')


def dos(izq, der):
    return ('<tr><td style="padding:6px 14px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td class="col" width="50%" valign="top" style="padding:0 6px 0 0">{izq}</td>'
            f'<td class="col" width="50%" valign="top" style="padding:0 0 0 6px">{der}</td></tr></table></td></tr>')


def uno(cont):
    return f'<tr><td style="padding:6px 14px">{cont}</td></tr>'


def fondo(x):
    t, n = x.get("ticker"), (x.get("name") or "")[:30]
    if t:
        return f'<b>{e(t)}</b> <span style="color:{SUAVE};font-size:11px">{e(n)}</span>'
    return f'<b>{e(n)}</b>'


def build():
    market = load("market-data.json", {})
    vals = load("valuations.json", {"items": {}})
    todas = (load("news.json", {}) or {}).get("items", [])
    ins = (load("insiders.json", {}) or {}).get("items", [])
    sig = load("signals.json", [])
    f13 = load("13f.json", {}) or {}
    ops, cuenta = calcular(vals, market)
    items = (vals.get("items") or {})

    H = []
    a = H.append
    a(f'<!doctype html><html lang="{LG}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Equity Intrinsic · {fecha(TODAY)}</title>'
      '<style>@media only screen and (max-width:680px){td.col{display:block!important;width:100%!important;padding:0 0 10px 0!important}td.tile{display:inline-block!important;width:46%!important}}</style></head>')
    a('<body style="margin:0;padding:0;background:#f7f8fa;font-family:Arial,Helvetica,sans-serif;color:#1f2937">')
    a('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%"><tr><td align="center" style="padding:0">')
    a('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background:#f7f8fa">')

    # Cabecera
    a(f'<tr><td style="background:#0b0f19;padding:16px 22px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
      f'<td width="84" valign="middle"><a href="{SITE}"><img src="{SITE0}logo-email.jpg" width="76" alt="Equity Intrinsic" style="display:block;border:0;border-radius:6px"></a></td>'
      f'<td valign="middle" style="padding-left:14px"><div style="font-size:22px;font-weight:bold;color:#d4a72c;letter-spacing:.5px">Equity Intrinsic</div>'
      f'<div style="font-size:12px;color:#9ca3af;margin-top:2px">{tr('Resumen diario','Daily summary')} · {fecha(TODAY)} · {tr('precios al cierre de mercado','end-of-day prices')}</div></td>'
      f'<td align="right" valign="middle"><a href="{SITE}" style="background:#d4a72c;color:#111;text-decoration:none;font-weight:bold;font-size:13px;padding:9px 16px;border-radius:6px;display:inline-block">{tr("Abrir la web","Open the website")}</a></td></tr></table></td></tr>')

    # Cifras del día
    if cuenta["total"]:
        def tile(t, v, col=TXT):
            return (f'<td class="tile" width="25%" valign="top" style="padding:0 4px"><div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:10px 6px;text-align:center">'
                    f'<div style="font-size:11px;color:{SUAVE}">{t}</div><div style="font-size:24px;font-weight:bold;color:{col}">{v}</div></div></td>')
        a('<tr><td style="padding:12px 10px 4px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
          + tile(tr("Acciones valoradas", "Stocks valued"), num(cuenta["total"], 0))
          + tile(tr("Oportunidades de compra", "Buy opportunities"), cuenta["COMPRAR"], VERDE)
          + tile(tr("Mejor esperar", "Better to wait"), cuenta["ESPERAR"])
          + tile(tr("Caras ahora", "Expensive now"), cuenta["CARO"], ROJO) + '</tr></table></td></tr>')

    # Mercado
    idx, mat, bon = cambios(market, IDX), cambios(market, MAT), cambios(market, BON)
    sub, baj = movers(market, vals)
    f = lambda L: [(e(EN_NAMES.get(n, n) if LG == "en" else n), f'{num(c)} &nbsp; {pct(ch)}') for n, c, ch in L]
    a(dos(caja(tr("Índices", "Indexes"), filas(f(idx), tr("Sin datos hoy.", "No data today.")), tr("Referencia: fondos que replican cada índice, al último cierre.", "Reference: funds that track each index, at the last close.")),
          caja(tr("Materias primas", "Commodities"), filas(f(mat), tr("Sin datos hoy.", "No data today.")), tr("Fondos que replican cada materia prima.", "Funds that track each commodity."))))
    g = lambda L: [(f'<b>{e(t)}</b> <span style="color:{SUAVE};font-size:11px">{e(n[:26])}</span>', f'{dinero(c)} &nbsp; {pct(ch)}') for t, n, c, ch in L]
    a(dos(caja(tr("Más suben hoy", "Biggest gainers today"), filas(g(sub), tr("Sin datos hoy.", "No data today.")), tr("Entre las acciones de nuestra lista principal.", "Among the stocks on our main list.")),
          caja(tr("Más bajan hoy", "Biggest decliners today"), filas(g(baj), tr("Hoy no hay caídas destacadas.", "No notable declines today.")), tr("Entre las acciones de nuestra lista principal.", "Among the stocks on our main list."))))
    a(dos(caja(tr("Bonos y deuda", "Bonds and debt"), filas(f(bon), tr("Sin datos hoy.", "No data today.")), tr("Fondos que replican cada tipo de bono. Si suben los tipos de interés, su precio baja.", "Funds that track each type of bond. If interest rates rise, their price falls.")),
          caja(tr("Conceptos del día", "Concepts of the day"), "".join(f'<div style="margin-bottom:10px"><b style="font-size:13px;color:#111111">{e((EN_TIPS if LG == "en" else TIPS)[(date.today().toordinal() + k) % len(TIPS)][0])}</b><div style="font-size:13px;line-height:19px;color:{TXT}">{e((EN_TIPS if LG == "en" else TIPS)[(date.today().toordinal() + k) % len(TIPS)][1])}</div></div>' for k in (0, 1))
               + f'<div><a href="{SITE}" style="color:{ORO};font-size:12px;font-weight:bold;text-decoration:none">{tr("Cómo funciona todo →", "How it all works →")}</a></div>')))

    # Oportunidades
    a(uno(f'<div style="font-weight:bold;font-size:17px;color:#111827;padding:6px 0 0">{tr("Oportunidades de compra", "Buy opportunities")} ({len(ops)})</div>'
          f'<div style="font-size:12px;color:{SUAVE};margin-bottom:2px">{tr('Precio por debajo de su valor intrínseco con margen de seguridad de al menos 25 %. Ordenadas por nuestro motor.','Price below its intrinsic value with a margin of safety of at least 25%. Ranked by our engine.')}</div>'))
    top = ops[:8]
    if top:
        def card(x):
            _, mg, t, iv, c, it = x
            hz, sl, fb_ = str(it.get("horizon") or "").lower(), str(it.get("health") or "").lower(), it.get("fiab")
            if LG == "en":
                extra = " · ".join(z for z in [hz and EN_HOR.get(hz, hz), sl and f"{EN_SAL.get(sl, sl)} health", fb_ and f"{EN_FIA.get(str(fb_).lower(), fb_)} reliability"] if z)
            else:
                extra = " · ".join(z for z in [hz and f"plazo {hz}", sl and f"salud {sl}", fb_ and f"fiabilidad {fb_}"] if z)
            return (f'<a href="{SITE}" style="text-decoration:none;color:inherit"><div style="border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px;background:#fff;margin-bottom:8px">'
                    f'<span style="font-weight:bold;font-size:14px;color:#111827">{e(it.get("name") or t)}</span> <span style="color:{SUAVE};font-size:12px">{e(t)}</span><br>'
                    f'<span style="font-size:13px">{tr("Precio","Price")} {dinero(c)} → {tr("valor intrínseco","intrinsic value")} {dinero(iv)}</span> <span style="color:{VERDE};font-weight:bold;font-size:13px">· {tr("margen","margin")} {pc(mg)}</span><br>'
                    f'<span style="font-size:11px;color:{SUAVE}">{e(extra)}</span></div></a>')
        izq = "".join(card(x) for x in top[0::2])
        der = "".join(card(x) for x in top[1::2])
        a(dos(izq, der))
    else:
        a(uno(f'<div style="font-size:14px;padding:4px 0">{tr("Hoy no hay oportunidades con margen de seguridad suficiente. Esperar también es una decisión.", "Today there are no opportunities with a sufficient margin of safety. Waiting is also a decision.")}</div>'))

    # Señales nuevas + directivos
    recientes = []
    if isinstance(sig, list) and sig:
        comp = [s for s in sig if s.get("verdict") == "COMPRAR"]
        comp.sort(key=lambda s: str(s.get("date", "")), reverse=True)
        recientes = comp[:5]
    sf = [(f'<b>{e(s.get("ticker",""))}</b> <span style="color:{SUAVE};font-size:11px">{e((items.get(s.get("ticker","")) or {}).get("name","")[:24])}</span><br><span style="font-size:11px;color:{SUAVE}">{tr("Señal de compra","Buy signal")} · {fecha(s.get("date", TODAY))}</span>', dinero(s["price"]) if isinstance(s.get("price"), (int, float)) else "") for s in recientes]
    titulo_sig = tr("Señales de compra más recientes", "Most recent buy signals")
    compras = [x for x in ins if str(x.get("k", "")).upper().startswith(("P", "C", "BUY", "COMPRA"))][:5]
    cf = []
    for x in compras:
        rol = (x.get("r") or "").strip()
        quien = " · ".join(z for z in [(x.get("w") or "").strip(), EN_ROL.get(rol, rol) if LG == "en" else rol] if z)
        imp = dinero(x["v"], 0) if isinstance(x.get("v"), (int, float)) else ""
        cf.append((f'<b>{e(x.get("t",""))}</b> <span style="color:{SUAVE};font-size:11px">{e((x.get("n") or "")[:30])}</span><br><span style="font-size:11px;color:{SUAVE}">{e(quien)} · {fecha(x.get("d", TODAY))}</span>', imp))
    a(dos(caja(titulo_sig, filas(sf, tr("Sin señales nuevas de compra.", "No new buy signals.")), tr("Cada señal queda con su fecha y su resultado real en el historial de la web.", "Each signal is kept with its date and its real result in the track record on the website.")),
          caja(tr("Directivos que compran con su dinero", "Executives buying with their own money"), filas(cf, tr("Sin compras destacadas en los últimos días.", "No notable purchases in recent days.")), tr("Operaciones de al menos 50.000 $ en el mercado (formulario 4 de la SEC).", "Open-market transactions of at least $50,000 (SEC Form 4)."))))

    # Grandes fondos
    if f13.get("buys") or f13.get("sells"):
        fb = [(fondo(x), f'{x.get("funds","")} {tr("fondos","funds")}') for x in (f13.get("buys") or [])[:6]]
        fs = [(fondo(x), f'{x.get("funds","")} {tr("fondos","funds")}') for x in (f13.get("sells") or [])[:6]]
        nota = (f"Informes 13F de {e(f13.get('quarter',''))} (presentados hasta 45 días después del trimestre). Sirven para ver tendencias, no para copiar operaciones." if LG == "es" else f"13F reports for {e(str(f13.get('quarter','')).replace('-T', '-Q'))} (filed up to 45 days after quarter-end). They help you see trends, not copy trades.")
        a(dos(caja(tr("Grandes fondos: lo que más compran", "Large funds: what they buy most"), filas(fb, tr("Sin datos.", "No data.")), nota), caja(tr("Grandes fondos: lo que más venden", "Large funds: what they sell most"), filas(fs, tr("Sin datos.", "No data.")), nota)))

    # Noticias
    def noticias(L):
        return "".join(
            f'<div style="padding:6px 0;border-bottom:1px solid #f0f1f3"><a href="{e(n.get("u","#"))}" style="color:#1a56db;text-decoration:none;font-size:13px;line-height:18px">{e(n.get("t",""))}</a>'
            f'<div style="font-size:11px;color:{SUAVE}">{e(n.get("s",""))}</div></div>' for n in L) or f'<div style="font-size:13px;color:{SUAVE}">{tr("Sin noticias hoy.", "No news today.")}</div>'
    if LG == "en":
        ing = [x for x in todas if x.get("l") == "en" and x.get("t")]
        a(dos(caja("Market news", noticias(ing[:6])), caja("More US market headlines", noticias(ing[6:12]))))
    else:
        es_ = [x for x in todas if x.get("l") == "es" and x.get("t")][:6]
        en_ = [x for x in todas if x.get("l") != "es" and x.get("t")][:6]
        a(dos(caja("Noticias de mercado", noticias(es_)), caja("Mercados de EE. UU. (titulares en inglés)", noticias(en_))))

    # CTA
    a(f'<tr><td align="center" style="padding:14px 14px 6px"><a href="{SITE}" style="background:#b8860b;color:#fff;text-decoration:none;padding:13px 30px;border-radius:6px;font-weight:bold;font-size:15px;display:inline-block">{tr("Ver el análisis completo en la web", "See the full analysis on the website")}</a></td></tr>')

    # Publicidad propia
    btn = 'display:inline-block;background:#d4a72c;color:#111111;text-decoration:none;font-weight:bold;font-size:12px;padding:8px 16px;border-radius:5px'
    cx = 'border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;font-size:12px;line-height:18px;color:#374151;background:#fff'
    a(uno(f'<div style="font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px">{tr("Publicidad", "Advertising")}</div>'))
    a(dos(f'<div style="{cx}"><b style="font-size:14px;color:#111111">Valmont &amp; Co. · {tr("Academia de inversión", "Investing academy")}</b><br>{tr("Guías y libros de inversión en español e inglés, con prólogos gratis, y cursos paso a paso para aprender a invertir con método.", "Investing guides and books in Spanish and English, with free forewords, and step-by-step courses to learn to invest with a method.")}<br><br><a href="https://valmontco.com" style="{btn}">{tr("Ver guías y cursos", "See guides and courses")}</a></div>',
          f'<div style="{cx}"><b style="font-size:14px;color:#111111">Nexus Terminal · {tr("Análisis técnico", "Technical analysis")}</b><br>{tr("Nuestro motor analiza acciones, criptomonedas y divisas por sí solo y publica pronósticos y señales, con avisos en Telegram y un histórico público de aciertos y fallos.", "Our engine analyzes stocks, cryptocurrencies and currencies on its own and publishes forecasts and signals, with Telegram alerts and a public track record of hits and misses.")}<br><br><a href="{NEXUS}" style="{btn}">{tr("Abrir Nexus Terminal", "Open Nexus Terminal")}</a></div>'))
    a(uno(f'<div style="font-size:10px;color:#9ca3af">{tr("Webs de Community16 LLC. Contenido educativo e informativo, no es asesoramiento financiero ni garantiza resultados.", "Websites of Community16 LLC. Educational and informational content, not financial advice and no guarantee of results.")}</div>'))

    # Firma
    a(f'<tr><td style="padding:18px 22px 10px;border-top:1px solid #e5e7eb"><div style="font-weight:bold;font-size:14px;color:#111827">Equity Intrinsic</div>'
      f'<div style="font-size:12px;color:{SUAVE}">Community16 LLC · New Mexico, {tr("EE. UU.", "USA")}</div>'
      f'<div style="font-size:12px"><a href="{SITE}" style="color:#1a56db">equityintrinsic.com</a> · <a href="mailto:contacto@equityintrinsic.com" style="color:#1a56db">contacto@equityintrinsic.com</a></div>'
      f'<div style="font-size:11px;color:#9ca3af;margin-top:10px;line-height:16px">{tr("Información con fines educativos, no es asesoramiento financiero. Invertir conlleva riesgo de perder dinero.", "Information for educational purposes, not financial advice. Investing involves the risk of losing money.")} '
      f'{tr("Recibes este correo porque te suscribiste en", "You are receiving this email because you subscribed at")} <a href="{SITE}" style="color:#9ca3af">equityintrinsic.com</a>. <a href="{{{{ unsubscribe }}}}" style="color:#9ca3af">{tr("Darte de baja", "Unsubscribe")}</a> · <a href="{SITE}{tr("privacidad.html", "privacy.html")}" style="color:#9ca3af">{tr("Privacidad", "Privacy")}</a></div></td></tr>')
    a('</table></td></tr></table></body></html>')

    T = [f"EQUITY INTRINSIC · {tr('Resumen diario', 'Daily summary')} {fecha(TODAY)}", ""]
    T.append(tr("MERCADO", "MARKET"))
    T += [f"  {EN_NAMES.get(n, n) if LG == 'en' else n}: {num(c)} ({ch:+.2f}%)" for n, c, ch in idx + mat]
    T += ["", f"{tr('OPORTUNIDADES DE COMPRA', 'BUY OPPORTUNITIES')} ({len(ops)})"]
    T += [f"  {t}: {tr('precio','price')} {dinero(c)} → {tr('valor','value')} {dinero(iv)} · {tr('margen','margin')} {pc(mg)}" for _, mg, t, iv, c, it in top] or [tr("  Hoy no hay oportunidades con margen suficiente.", "  Today there are no opportunities with a sufficient margin.")]
    T += ["", f"{tr('Análisis completo', 'Full analysis')}: {SITE}", "", "Equity Intrinsic · Community16 LLC · contacto@equityintrinsic.com",
          tr("Información educativa, no asesoramiento financiero. Invertir conlleva riesgo.", "Educational information, not financial advice. Investing involves risk.")]
    return "".join(H), "\n".join(T), len(ops)


def enviar(asunto, cuerpo, lst, nombre):
    import urllib.request
    key = os.environ.get("BREVO_API_KEY")
    if not (key and lst):
        print(f"[{nombre}] Sin servicio de correo o sin lista configurada: solo vista previa, no se envía nada.")
        return
    hdr = {"api-key": key, "content-type": "application/json", "accept": "application/json"}
    camp = {"name": f"Resumen {nombre} {TODAY}", "subject": asunto, "htmlContent": cuerpo,
            "sender": {"name": "Equity Intrinsic", "email": os.environ.get("MAIL_FROM", "contacto@equityintrinsic.com")},
            "recipients": {"listIds": [int(lst)]}}
    r = urllib.request.urlopen(urllib.request.Request("https://api.brevo.com/v3/emailCampaigns", json.dumps(camp).encode(), hdr, method="POST"), timeout=60)
    cid = json.loads(r.read())["id"]
    urllib.request.urlopen(urllib.request.Request(f"https://api.brevo.com/v3/emailCampaigns/{cid}/sendNow", b"", hdr, method="POST"), timeout=60)
    print(f"[{nombre}] Correo enviado (campaña {cid}).")


def main():
    global LG, SITE
    fallo = False
    for lg, lst, suf in (("es", os.environ.get("BREVO_LIST_ID"), ""), ("en", os.environ.get("BREVO_LIST_ID_EN"), "-en")):
        LG, SITE = lg, SITE0 + ("en/" if lg == "en" else "")
        try:
            h, t, n = build()
            (DATA / f"correo{suf}.html").write_text(h, encoding="utf-8")
            (DATA / f"correo{suf}.txt").write_text(t, encoding="utf-8")
            print(f"[{lg}] Correo preparado: {n} oportunidades.")
            asunto = (f"Equity Intrinsic · resumen {fecha(TODAY)}: {n} oportunidades" if lg == "es"
                      else f"Equity Intrinsic · {fecha(TODAY)} summary: {n} {'opportunity' if n == 1 else 'opportunities'}")
            enviar(asunto, h, lst, lg)
        except Exception as ex:  # un idioma que falla no impide el otro
            print(f"[{lg}] ERROR: {ex}")
            fallo = True
    if fallo:
        sys.exit(1)


if __name__ == "__main__":
    main()
