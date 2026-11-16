#!/usr/bin/env python3
"""Equity Intrinsic: resumen diario por correo. Solo datos reales de data/*.json; nada inventado.
Genera data/correo.html y data/correo.txt. Si hay servicio de correo configurado (BREVO_API_KEY y BREVO_LIST_ID), lo envía.
Sin esas claves solo genera la vista previa (no envía nada)."""
import html, json, os, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from engine import verdict, rank, spread  # mismas reglas que la web y Telegram

DATA = Path(os.environ.get("DATA_DIR", "data"))
SITE = os.environ.get("SITE_URL", "https://equityintrinsic.com/").rstrip("/") + "/"
TODAY = date.today().isoformat()
IDX = [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DIA", "Dow Jones"), ("IWM", "Russell 2000")]
MAT = [("GLD", "Oro"), ("SLV", "Plata"), ("USO", "Petróleo"), ("UNG", "Gas natural"), ("CPER", "Cobre")]
BON = [("TLT", "Bonos EE. UU. largo plazo"), ("IEF", "Bonos EE. UU. medio plazo"), ("SHY", "Bonos EE. UU. corto plazo"), ("LQD", "Deuda de empresas sólidas"), ("HYG", "Deuda de empresas de más riesgo")]
NEXUS = os.environ.get("NEXUS_URL", "https://nexusterminalalerts.com")
METODOS = ("dcf", "graham", "multiples", "pb", "gnum")
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
    return f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def fecha(iso):
    a, m, d = str(iso)[:10].split("-")
    return f"{d}/{m}/{a}"


def pct(ch):
    col = VERDE if ch >= 0 else ROJO
    return f'<span style="font-weight:bold;color:{col}">{"+" if ch >= 0 else ""}{num(ch)} %</span>'


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
    a(f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Equity Intrinsic · {fecha(TODAY)}</title>'
      '<style>@media only screen and (max-width:680px){td.col{display:block!important;width:100%!important;padding:0 0 10px 0!important}td.tile{display:inline-block!important;width:46%!important}}</style></head>')
    a('<body style="margin:0;padding:0;background:#f7f8fa;font-family:Arial,Helvetica,sans-serif;color:#1f2937">')
    a('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%"><tr><td align="center" style="padding:0">')
    a('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background:#f7f8fa">')

    # Cabecera
    a(f'<tr><td style="background:#0b0f19;padding:16px 22px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
      f'<td width="84" valign="middle"><a href="{SITE}"><img src="{SITE}logo-email.jpg" width="76" alt="Equity Intrinsic" style="display:block;border:0;border-radius:6px"></a></td>'
      f'<td valign="middle" style="padding-left:14px"><div style="font-size:22px;font-weight:bold;color:#d4a72c;letter-spacing:.5px">Equity Intrinsic</div>'
      f'<div style="font-size:12px;color:#9ca3af;margin-top:2px">Resumen diario · {fecha(TODAY)} · precios al cierre de mercado</div></td>'
      f'<td align="right" valign="middle"><a href="{SITE}" style="background:#d4a72c;color:#111;text-decoration:none;font-weight:bold;font-size:13px;padding:9px 16px;border-radius:6px;display:inline-block">Abrir la web</a></td></tr></table></td></tr>')

    # Cifras del día
    if cuenta["total"]:
        def tile(t, v, col=TXT):
            return (f'<td class="tile" width="25%" valign="top" style="padding:0 4px"><div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:10px 6px;text-align:center">'
                    f'<div style="font-size:11px;color:{SUAVE}">{t}</div><div style="font-size:24px;font-weight:bold;color:{col}">{v}</div></div></td>')
        a('<tr><td style="padding:12px 10px 4px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
          + tile("Acciones valoradas", f"{cuenta['total']:,}".replace(",", "."))
          + tile("Oportunidades de compra", cuenta["COMPRAR"], VERDE)
          + tile("Mejor esperar", cuenta["ESPERAR"])
          + tile("Caras ahora", cuenta["CARO"], ROJO) + '</tr></table></td></tr>')

    # Mercado
    idx, mat, bon = cambios(market, IDX), cambios(market, MAT), cambios(market, BON)
    sub, baj = movers(market, vals)
    f = lambda L: [(e(n), f'{num(c)} &nbsp; {pct(ch)}') for n, c, ch in L]
    a(dos(caja("Índices", filas(f(idx), "Sin datos hoy."), "Referencia: fondos que replican cada índice, al último cierre."),
          caja("Materias primas", filas(f(mat), "Sin datos hoy."), "Fondos que replican cada materia prima.")))
    g = lambda L: [(f'<b>{e(t)}</b> <span style="color:{SUAVE};font-size:11px">{e(n[:26])}</span>', f'${num(c)} &nbsp; {pct(ch)}') for t, n, c, ch in L]
    a(dos(caja("Más suben hoy", filas(g(sub), "Sin datos hoy."), "Entre las acciones de nuestra lista principal."),
          caja("Más bajan hoy", filas(g(baj), "Hoy no hay caídas destacadas."), "Entre las acciones de nuestra lista principal.")))
    a(dos(caja("Bonos y deuda", filas(f(bon), "Sin datos hoy."), "Fondos que replican cada tipo de bono. Si suben los tipos de interés, su precio baja."),
          caja("Conceptos del día", "".join(f'<div style="margin-bottom:10px"><b style="font-size:13px;color:#111111">{e(TIPS[(date.today().toordinal() + k) % len(TIPS)][0])}</b><div style="font-size:13px;line-height:19px;color:{TXT}">{e(TIPS[(date.today().toordinal() + k) % len(TIPS)][1])}</div></div>' for k in (0, 1))
               + f'<div><a href="{SITE}" style="color:{ORO};font-size:12px;font-weight:bold;text-decoration:none">Cómo funciona todo →</a></div>')))

    # Oportunidades
    a(uno(f'<div style="font-weight:bold;font-size:17px;color:#111827;padding:6px 0 0">Oportunidades de compra ({len(ops)})</div>'
          f'<div style="font-size:12px;color:{SUAVE};margin-bottom:2px">Precio por debajo de su valor intrínseco con margen de seguridad de al menos 25 %. Ordenadas por nuestro motor.</div>'))
    top = ops[:8]
    if top:
        def card(x):
            _, mg, t, iv, c, it = x
            extra = " · ".join(z for z in [it.get("horizon") and f"plazo {str(it['horizon']).lower()}", it.get("health") and f"salud {str(it['health']).lower()}", it.get("fiab") and f"fiabilidad {it['fiab']}"] if z)
            return (f'<a href="{SITE}#/ficha/{e(t)}" style="text-decoration:none;color:inherit"><div style="border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px;background:#fff;margin-bottom:8px">'
                    f'<span style="font-weight:bold;font-size:14px;color:#111827">{e(it.get("name") or t)}</span> <span style="color:{SUAVE};font-size:12px">{e(t)}</span><br>'
                    f'<span style="font-size:13px">Precio ${num(c)} → valor intrínseco ${num(iv)}</span> <span style="color:{VERDE};font-weight:bold;font-size:13px">· margen {mg:.0f} %</span><br>'
                    f'<span style="font-size:11px;color:{SUAVE}">{e(extra)}</span></div></a>')
        izq = "".join(card(x) for x in top[0::2])
        der = "".join(card(x) for x in top[1::2])
        a(dos(izq, der))
    else:
        a(uno(f'<div style="font-size:14px;padding:4px 0">Hoy no hay oportunidades con margen de seguridad suficiente. Esperar también es una decisión.</div>'))

    # Señales nuevas + directivos
    recientes = []
    if isinstance(sig, list) and sig:
        comp = [s for s in sig if s.get("verdict") == "COMPRAR"]
        comp.sort(key=lambda s: str(s.get("date", "")), reverse=True)
        recientes = comp[:5]
    sf = [(f'<b>{e(s.get("ticker",""))}</b> <span style="color:{SUAVE};font-size:11px">{e((items.get(s.get("ticker","")) or {}).get("name","")[:24])}</span><br><span style="font-size:11px;color:{SUAVE}">Señal de compra · {fecha(s.get("date", TODAY))}</span>', f'${num(s["price"])}' if isinstance(s.get("price"), (int, float)) else "") for s in recientes]
    titulo_sig = "Señales de compra más recientes"
    compras = [x for x in ins if str(x.get("k", "")).upper().startswith(("P", "C", "BUY", "COMPRA"))][:5]
    cf = []
    for x in compras:
        quien = " · ".join(z for z in [(x.get("w") or "").strip(), (x.get("r") or "").strip()] if z)
        imp = f'${num(x["v"], 0)}' if isinstance(x.get("v"), (int, float)) else ""
        cf.append((f'<b>{e(x.get("t",""))}</b> <span style="color:{SUAVE};font-size:11px">{e((x.get("n") or "")[:30])}</span><br><span style="font-size:11px;color:{SUAVE}">{e(quien)} · {fecha(x.get("d", TODAY))}</span>', imp))
    a(dos(caja(titulo_sig, filas(sf, "Sin señales nuevas de compra."), "Cada señal queda con su fecha y su resultado real en el historial de la web."),
          caja("Directivos que compran con su dinero", filas(cf, "Sin compras destacadas en los últimos días."), "Operaciones de al menos 50.000 $ en el mercado (formulario 4 de la SEC).")))

    # Grandes fondos
    if f13.get("buys") or f13.get("sells"):
        fb = [(fondo(x), f'{x.get("funds","")} fondos') for x in (f13.get("buys") or [])[:6]]
        fs = [(fondo(x), f'{x.get("funds","")} fondos') for x in (f13.get("sells") or [])[:6]]
        nota = f"Informes 13F de {e(f13.get('quarter',''))} (presentados hasta 45 días después del trimestre). Sirven para ver tendencias, no para copiar operaciones."
        a(dos(caja("Grandes fondos: lo que más compran", filas(fb, "Sin datos."), nota), caja("Grandes fondos: lo que más venden", filas(fs, "Sin datos."), nota)))

    # Noticias
    def noticias(L):
        return "".join(
            f'<div style="padding:6px 0;border-bottom:1px solid #f0f1f3"><a href="{e(n.get("u","#"))}" style="color:#1a56db;text-decoration:none;font-size:13px;line-height:18px">{e(n.get("t",""))}</a>'
            f'<div style="font-size:11px;color:{SUAVE}">{e(n.get("s",""))}</div></div>' for n in L) or f'<div style="font-size:13px;color:{SUAVE}">Sin noticias hoy.</div>'
    es_ = [x for x in todas if x.get("l") == "es" and x.get("t")][:6]
    en_ = [x for x in todas if x.get("l") != "es" and x.get("t")][:6]
    a(dos(caja("Noticias de mercado", noticias(es_)), caja("Mercados de EE. UU. (titulares en inglés)", noticias(en_))))

    # CTA
    a(f'<tr><td align="center" style="padding:14px 14px 6px"><a href="{SITE}" style="background:#b8860b;color:#fff;text-decoration:none;padding:13px 30px;border-radius:6px;font-weight:bold;font-size:15px;display:inline-block">Ver el análisis completo en la web</a></td></tr>')

    # Publicidad propia
    btn = 'display:inline-block;background:#d4a72c;color:#111111;text-decoration:none;font-weight:bold;font-size:12px;padding:8px 16px;border-radius:5px'
    cx = 'border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;font-size:12px;line-height:18px;color:#374151;background:#fff'
    a(uno(f'<div style="font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px">Publicidad</div>'))
    a(dos(f'<div style="{cx}"><b style="font-size:14px;color:#111111">Valmont &amp; Co. · Academia de inversión</b><br>Guías y libros de inversión en español e inglés, con prólogos gratis, y cursos paso a paso para aprender a invertir con método.<br><br><a href="https://valmontco.com" style="{btn}">Ver guías y cursos</a></div>',
          f'<div style="{cx}"><b style="font-size:14px;color:#111111">Nexus Terminal · Análisis técnico</b><br>Nuestro motor analiza acciones, criptomonedas y divisas por sí solo y publica pronósticos y señales, con avisos en Telegram y un histórico público de aciertos y fallos.<br><br><a href="{NEXUS}" style="{btn}">Abrir Nexus Terminal</a></div>'))
    a(uno(f'<div style="font-size:10px;color:#9ca3af">Webs de Community16 LLC. Contenido educativo e informativo, no es asesoramiento financiero ni garantiza resultados.</div>'))

    # Firma
    a(f'<tr><td style="padding:18px 22px 10px;border-top:1px solid #e5e7eb"><div style="font-weight:bold;font-size:14px;color:#111827">Equity Intrinsic</div>'
      f'<div style="font-size:12px;color:{SUAVE}">Community16 LLC · New Mexico, EE. UU.</div>'
      f'<div style="font-size:12px"><a href="{SITE}" style="color:#1a56db">equityintrinsic.com</a> · <a href="mailto:contacto@equityintrinsic.com" style="color:#1a56db">contacto@equityintrinsic.com</a></div>'
      f'<div style="font-size:11px;color:#9ca3af;margin-top:10px;line-height:16px">Información con fines educativos, no es asesoramiento financiero. Invertir conlleva riesgo de perder dinero. '
      f'Recibes este correo porque te suscribiste en <a href="{SITE}" style="color:#9ca3af">equityintrinsic.com</a>. <a href="{{{{ unsubscribe }}}}" style="color:#9ca3af">Darte de baja</a> · <a href="{SITE}privacidad.html" style="color:#9ca3af">Privacidad</a></div></td></tr>')
    a('</table></td></tr></table></body></html>')

    T = [f"EQUITY INTRINSIC · Resumen diario {fecha(TODAY)}", ""]
    T.append("MERCADO")
    T += [f"  {n}: {num(c)} ({ch:+.2f} %)" for n, c, ch in idx + mat]
    T += ["", f"OPORTUNIDADES DE COMPRA ({len(ops)})"]
    T += [f"  {t}: precio ${num(c)} → valor ${num(iv)} · margen {mg:.0f} %" for _, mg, t, iv, c, it in top] or ["  Hoy no hay oportunidades con margen suficiente."]
    T += ["", f"Análisis completo: {SITE}", "", "Equity Intrinsic · Community16 LLC · contacto@equityintrinsic.com",
          "Información educativa, no asesoramiento financiero. Invertir conlleva riesgo."]
    return "".join(H), "\n".join(T), len(ops)


def enviar(asunto, cuerpo):
    import urllib.request
    key, lst = os.environ.get("BREVO_API_KEY"), os.environ.get("BREVO_LIST_ID")
    if not (key and lst):
        print("Sin servicio de correo configurado: solo vista previa, no se envía nada.")
        return
    cuerpo = cuerpo.replace("{{ unsubscribe }}", "{{ unsubscribe }}")
    hdr = {"api-key": key, "content-type": "application/json", "accept": "application/json"}
    camp = {"name": f"Resumen {TODAY}", "subject": asunto, "htmlContent": cuerpo,
            "sender": {"name": "Equity Intrinsic", "email": os.environ.get("MAIL_FROM", "contacto@equityintrinsic.com")},
            "recipients": {"listIds": [int(lst)]}}
    r = urllib.request.urlopen(urllib.request.Request("https://api.brevo.com/v3/emailCampaigns", json.dumps(camp).encode(), hdr, method="POST"), timeout=60)
    cid = json.loads(r.read())["id"]
    urllib.request.urlopen(urllib.request.Request(f"https://api.brevo.com/v3/emailCampaigns/{cid}/sendNow", b"", hdr, method="POST"), timeout=60)
    print(f"Correo enviado (campaña {cid}).")


def main():
    h, t, n = build()
    (DATA / "correo.html").write_text(h, encoding="utf-8")
    (DATA / "correo.txt").write_text(t, encoding="utf-8")
    print(f"Correo preparado: {n} oportunidades.")
    enviar(f"Equity Intrinsic · resumen {fecha(TODAY)}: {n} oportunidades", h)


if __name__ == "__main__":
    main()
