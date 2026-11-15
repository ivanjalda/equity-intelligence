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
NEXUS = os.environ.get("NEXUS_URL", "https://nexusterminalalerts.com")
METODOS = ("dcf", "graham", "multiples", "pb", "gnum")


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


def oportunidades(vals, market):
    out = []
    for t, it in (vals.get("items") or {}).items():
        c = (market.get(t) or {}).get("c")
        nums = [it[k] for k in METODOS if isinstance(it.get(k), (int, float)) and it[k] > 0]
        if not c or not nums or it.get("type", "ACCIONES") != "ACCIONES":
            continue
        iv = sum(nums) / len(nums)
        mg = (iv - c) / iv * 100
        if verdict(mg, it.get("health"), it.get("fiab")) == "COMPRAR":
            out.append((rank(mg, it.get("health"), it.get("cyclical"), spread(it), it.get("fiab")), mg, t, iv, c, it))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def indices(market):
    r = []
    for t, n in IDX:
        m = market.get(t) or {}
        if m.get("c") and m.get("p"):
            r.append((n, m["c"], (m["c"] / m["p"] - 1) * 100))
    return r


def build():
    market = load("market-data.json", {})
    vals = load("valuations.json", {"items": {}})
    _todas = (load("news.json", {}) or {}).get("items", [])
    news = [x for x in _todas if x.get("l") == "es" and x.get("t")][:5]
    if len(news) < 3:
        news = (news + [x for x in _todas if x.get("l") != "es" and x.get("t")])[:5]
    ins = (load("insiders.json", {}) or {}).get("items", [])
    ops = oportunidades(vals, market)
    idx = indices(market)
    top = ops[:5]
    # compras de directivos más recientes (solo compras)
    compras = [x for x in ins if str(x.get("k", "")).upper().startswith(("P", "C", "BUY", "COMPRA"))][:4]

    verde, rojo, oro = "#0b8043", "#c5221f", "#b8860b"
    H = []
    a = H.append
    a(f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Equity Intrinsic · {fecha(TODAY)}</title></head>')
    a('<body style="margin:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#1f2937">')
    a('<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:16px 8px">')
    a('<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fff;border-radius:10px;overflow:hidden">')
    a(f'<tr><td style="background:#000;text-align:center;padding:0"><a href="{SITE}"><img src="{SITE}logo-email.jpg" width="300" alt="Equity Intrinsic" style="display:block;margin:0 auto;max-width:100%;height:auto"></a></td></tr>')
    a(f'<tr><td style="padding:20px 24px 4px"><div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:1px">Resumen diario · {fecha(TODAY)}</div></td></tr>')
    if idx:
        a('<tr><td style="padding:8px 24px"><div style="font-weight:bold;font-size:16px;margin-bottom:6px">Mercado hoy</div><table role="presentation" width="100%" cellpadding="0" cellspacing="0">')
        for n, c, ch in idx:
            col = verde if ch >= 0 else rojo
            a(f'<tr><td style="padding:4px 0;font-size:14px">{e(n)}</td><td align="right" style="font-size:14px">{num(c)}</td><td align="right" style="width:80px;font-size:14px;font-weight:bold;color:{col}">{"+" if ch >= 0 else ""}{num(ch)} %</td></tr>')
        a('</table><div style="font-size:11px;color:#6b7280;margin-top:4px">Referencia: fondos que replican cada índice, al último cierre.</div></td></tr>')
    a(f'<tr><td style="padding:14px 24px 4px"><div style="font-weight:bold;font-size:16px">Oportunidades de compra ({len(ops)})</div><div style="font-size:12px;color:#6b7280">Precio por debajo de su valor intrínseco con margen de seguridad de al menos 25 %.</div></td></tr>')
    if top:
        for _, mg, t, iv, c, it in top:
            extra = " · ".join(x for x in [f"plazo {it['horizon']}" if it.get("horizon") else "", f"salud {str(it['health']).lower()}" if it.get("health") else "", f"fiabilidad {it['fiab']}" if it.get("fiab") else ""] if x)
            a(f'<tr><td style="padding:6px 24px"><a href="{SITE}#/ficha/{e(t)}" style="text-decoration:none;color:inherit"><div style="border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px"><span style="font-weight:bold;font-size:15px">{e(it.get("name") or t)}</span> <span style="color:#6b7280;font-size:12px">{e(t)}</span><br><span style="font-size:13px">Precio ${num(c)} → valor intrínseco ${num(iv)}</span> <span style="color:{verde};font-weight:bold;font-size:13px">· margen {mg:.0f} %</span><br><span style="font-size:11px;color:#6b7280">{e(extra)}</span></div></a></td></tr>')
    else:
        a('<tr><td style="padding:6px 24px;font-size:14px">Hoy no hay oportunidades con margen de seguridad suficiente. Esperar también es una decisión.</td></tr>')
    if compras:
        a('<tr><td style="padding:14px 24px 4px"><div style="font-weight:bold;font-size:16px">Directivos que compran con su dinero</div></td></tr>')
        for x in compras:
            quien = " · ".join(z for z in [(x.get("w") or "").strip(), (x.get("r") or "").strip()] if z)
            a(f'<tr><td style="padding:3px 24px;font-size:13px"><b>{e(x.get("t",""))}</b> · {e(x.get("n",""))}{(" — " + e(quien)) if quien else ""} · {fecha(x.get("d", TODAY))}</td></tr>')
    if news:
        a('<tr><td style="padding:14px 24px 4px"><div style="font-weight:bold;font-size:16px">Noticias</div></td></tr>')
        for n in news:
            a(f'<tr><td style="padding:3px 24px;font-size:13px"><a href="{e(n.get("u","#"))}" style="color:#1a56db;text-decoration:none">{e(n.get("t",""))}</a> <span style="color:#6b7280;font-size:11px">· {e(n.get("s",""))}</span></td></tr>')
    a(f'<tr><td align="center" style="padding:18px 24px"><a href="{SITE}" style="background:{oro};color:#fff;text-decoration:none;padding:12px 26px;border-radius:6px;font-weight:bold;font-size:14px;display:inline-block">Ver el análisis completo</a></td></tr>')
    # Publicidad propia
    a('<tr><td style="padding:6px 24px 0"><div style="font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:1px">Publicidad</div></td></tr>')
    btn = 'display:inline-block;background:#d4a72c;color:#111111;text-decoration:none;font-weight:bold;font-size:12px;padding:7px 14px;border-radius:5px'
    caja = 'border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;font-size:12px;line-height:18px;color:#374151'
    a('<tr><td style="padding:4px 24px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
      f'<td width="50%" valign="top" style="padding-right:6px"><div style="{caja}"><b style="font-size:13px;color:#111111">Valmont &amp; Co. · Academia de inversión</b><br>Guías y libros de inversión en español e inglés, con prólogos gratis, y cursos paso a paso.<br><br><a href="https://valmontco.com" style="{btn}">Ver guías y cursos</a></div></td>'
      f'<td width="50%" valign="top" style="padding-left:6px"><div style="{caja}"><b style="font-size:13px;color:#111111">Nexus Terminal · Análisis técnico</b><br>Nuestro motor analiza acciones, criptomonedas y divisas, y publica pronósticos y señales, con avisos en Telegram.<br><br><a href="{NEXUS}" style="{btn}">Abrir Nexus Terminal</a></div></td>'
      '</tr></table></td></tr>')
    a('<tr><td style="padding:4px 24px 0;font-size:10px;color:#9ca3af">Webs de Community16 LLC. Contenido educativo e informativo, no es asesoramiento financiero ni garantiza resultados.</td></tr>')
    # Firma
    a('<tr><td style="padding:20px 24px 8px;border-top:1px solid #e5e7eb;margin-top:12px">'
      f'<div style="font-weight:bold;font-size:14px">Equity Intrinsic</div>'
      '<div style="font-size:12px;color:#6b7280">Community16 LLC · New Mexico, EE. UU.</div>'
      f'<div style="font-size:12px"><a href="{SITE}" style="color:#1a56db">equityintrinsic.com</a> · <a href="mailto:contacto@equityintrinsic.com" style="color:#1a56db">contacto@equityintrinsic.com</a></div></td></tr>')
    a('<tr><td style="padding:8px 24px 20px;font-size:11px;color:#9ca3af;line-height:1.5">Información con fines educativos, no es asesoramiento financiero. Invertir conlleva riesgo de perder dinero. '
      f'Recibes este correo porque te suscribiste en equityintrinsic.com. <a href="{{{{ unsubscribe }}}}" style="color:#9ca3af">Darte de baja</a> · <a href="{SITE}privacidad.html" style="color:#9ca3af">Privacidad</a></td></tr>')
    a('</table></td></tr></table></body></html>')

    T = [f"EQUITY INTRINSIC · Resumen diario {fecha(TODAY)}", ""]
    if idx:
        T.append("MERCADO HOY")
        T += [f"  {n}: {num(c)} ({'+' if ch >= 0 else ''}{num(ch)} %)" for n, c, ch in idx]
        T.append("")
    T.append(f"OPORTUNIDADES DE COMPRA ({len(ops)})")
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
