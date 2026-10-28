#!/usr/bin/env python3
"""Equity Intelligence: motor diario.
Descarga precios, calcula el valor intrínseco con 3 métodos (DCF, Graham,
múltiplos históricos) usando datos oficiales de la SEC, registra señales y
avisa por Telegram. Solo usa la librería estándar de Python."""
import json, os, sys, time, csv, io, bisect, urllib.request, urllib.parse, urllib.error
from datetime import date, timedelta
from pathlib import Path
from statistics import median, mean

DATA = Path("data")
HIST = DATA / "history"
FUND = DATA / "fundamentals"
TODAY = date.today().isoformat()
POLY = os.environ.get("POLYGON_KEY")
SEC_UA = os.environ.get("SEC_USER_AGENT", "EquityIntelligence contacto@ejemplo.com")
YIELD_AAA = 5.0      # rendimiento de bonos AAA usado en la fórmula de Graham (%)
DISCOUNT = 0.10      # tasa de descuento del DCF
TERMINAL = 0.025     # crecimiento a perpetuidad del DCF
MIN_MARGIN = 25.0    # margen de seguridad mínimo para COMPRAR (%)


def verdict(mg, health=None):
    """Regla común: margen de seguridad entre 25 % y 70 % y salud financiera no frágil."""
    if mg is None:
        return None
    if MIN_MARGIN <= mg <= 70 and health != "Frágil":
        return "COMPRAR"
    return "ESPERAR" if mg >= 0 else "CARO"


def get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def read_universe():
    out = []
    for line in Path("tickers.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        p = line.upper().split()
        tipo = next((x for x in p[1:] if x in ("ACCIONES", "ETFS", "COMMODITIES", "BONOS")), "ACCIONES")
        out.append({"t": p[0], "type": tipo, "cyc": "CICLICA" in p[1:]})
    return out


# ---------- PRECIOS ----------
def prices_yahoo(t):
    s = t.replace(".", "-")
    d = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=10y&interval=1d"))
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(r["timestamp"]):
        if q["close"][i] is None:
            continue
        rows.append((date.fromtimestamp(ts).isoformat(), q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i] or 0))
    return rows


def prices_stooq(t):
    s = t.lower().replace(".", "-") + ".us"
    rows = []
    for r in csv.DictReader(io.StringIO(get(f"https://stooq.com/q/d/l/?s={s}&i=d"))):
        rows.append((r["Date"], float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]), float(r.get("Volume") or 0)))
    return rows[-2600:]


def prices_polygon(t):
    """Precios de Polygon (plan gratuito: 2 años de histórico, 5 consultas/minuto)."""
    start = (date.today() - timedelta(days=730)).isoformat()
    url = (f"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/day/{start}/{TODAY}"
           f"?adjusted=true&sort=asc&limit=50000&apiKey={POLY}")
    for intento in range(2):
        try:
            d = json.loads(get(url))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento == 0:
                time.sleep(65)
                continue
            raise
    return [(date.fromtimestamp(r["t"] / 1000).isoformat(), r["o"], r["h"], r["l"], r["c"], r.get("v", 0))
            for r in (d.get("results") or [])]


def prices(t):
    """Devuelve (corto, largo): corto = Polygon (precio oficial); largo = histórico de 10 años si hay fuente."""
    short, long_ = None, None
    if POLY:
        try:
            short = prices_polygon(t)
        except Exception as e:
            print(f"  {t}: Polygon falló ({e})")
        time.sleep(12.5)  # respeta el límite del plan gratuito
    for fn in (prices_yahoo, prices_stooq):
        try:
            rows = fn(t)
            if len(rows) > 30:
                long_ = rows
                break
        except Exception as e:
            print(f"  {t}: {fn.__name__} sin histórico largo ({e})")
    if not short or len(short) < 30:
        short = long_
    if not short:
        return None
    long_ = long_ or short
    if long_ is not short:  # Polygon manda en los últimos 2 años; la otra fuente solo aporta lo anterior
        long_ = [r for r in long_ if r[0] < short[0][0]] + short
    return short, long_


def downsample(rows):
    cut = (date.today() - timedelta(days=730)).isoformat()
    old = [r for r in rows if r[0] < cut][::5]
    return [[r[0], round(r[4], 2)] for r in old + [r for r in rows if r[0] >= cut]]


# ---------- SEC ----------
def annual(facts, names, unit):
    out, last = {}, ""
    for n in names:
        for r in facts.get("us-gaap", {}).get(n, {}).get("units", {}).get(unit, []):
            last = max(last, r.get("filed", ""))
            if "start" not in r:
                continue
            days = (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days
            if not 340 <= days <= 380:
                continue
            if r["end"] not in out or r["filed"] > out[r["end"]][1]:
                out[r["end"]] = (r["val"], r["filed"])
        if out:
            break
    return {k: v[0] for k, v in sorted(out.items())}, last


def clamp(x, a, b):
    return max(a, min(b, x))


def dcf(fcfps, g):
    v, f = 0.0, fcfps
    for y in range(1, 11):
        f *= 1 + (g if y <= 5 else g / 2)
        v += f / (1 + DISCOUNT) ** y
    return v + f * (1 + TERMINAL) / (DISCOUNT - TERMINAL) / (1 + DISCOUNT) ** 10


def value_stock(t, cyc, facts, hist, price):
    eps, f1 = annual(facts, ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"], "USD/shares")
    cfo, f2 = annual(facts, ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], "USD")
    cap, _ = annual(facts, ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], "USD")
    ni, _ = annual(facts, ["NetIncomeLoss"], "USD")
    if len(eps) < 3:  # algunas empresas (p. ej. Visa) no publican el beneficio por acción total
        shs, _ = annual(facts, ["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares")
        eps = {k: ni[k] / shs[k] for k in ni if shs.get(k)}
    if len(eps) < 3 or not cfo:
        return f"pocos datos oficiales (beneficio {len(eps)} años, flujo de caja {len(cfo)} años)"
    ends = list(eps)
    e_last = eps[ends[-1]]
    n_norm = 7 if cyc else 3
    e_use = mean(eps[k] for k in ends[-n_norm:]) if cyc else e_last
    # crecimiento del beneficio (5 años), acotado
    win = [eps[k] for k in ends[-6:]]
    cagr = (win[-1] / win[0]) ** (1 / (len(win) - 1)) - 1 if win[0] > 0 and win[-1] > 0 and len(win) > 2 else 0.0
    g = 0.03 if cyc else clamp(cagr, 0.0, 0.12)
    models = {}
    # Graham
    if e_use > 0:
        models["graham"] = e_use * (8.5 + 2 * g * 100) * 4.4 / YIELD_AAA
    # DCF (flujo de caja libre por acción, media de varios años)
    k = ends[-1]
    sh, _ = annual(facts, ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"], "shares")
    shares = sh.get(k) or (ni[k] / eps[k] if k in ni and eps[k] > 0 else None)
    fcf = [cfo[x] - abs(cap.get(x, 0)) for x in list(cfo)[-(7 if cyc else 3):]]
    fcfps = None
    if shares and shares > 0 and fcf and mean(fcf) > 0:
        fcfps = mean(fcf) / shares
        models["dcf"] = dcf(fcfps, g)
    # Múltiplos: PER mediano histórico x beneficio
    dates = [h[0] for h in hist]
    pes = []
    for e in ends:
        i = bisect.bisect_right(dates, e) - 1
        if i >= 0 and eps[e] > 0:
            pes.append(hist[i][4] / eps[e])
    if len(pes) >= 4 and e_use > 0:
        models["multiples"] = clamp(median(pes), 8, 30) * e_use
    models = {m: v for m, v in models.items() if v > 0}
    if len(models) < 2:
        return f"menos de 2 métodos válidos (hay: {', '.join(models) or 'ninguno'})"
    while len(models) >= 2 and max(models.values()) > 3 * min(models.values()):
        models.pop(max(models, key=models.get))  # descartamos el más optimista
    if len(models) < 2:
        return "los métodos discrepan demasiado entre sí"
    vals = list(models.values())
    iv = mean(vals)
    mg = (iv - price) / iv * 100
    # plazo (mezcla interna de fundamental y técnico)
    stable = all(eps[x] > 0 for x in ends[-5:]) and cagr >= 0.05
    hz = "medio" if cyc else ("largo" if stable else "medio")
    c200 = mean(h[4] for h in hist[-200:])
    if mg >= MIN_MARGIN and price < 0.9 * c200:
        hz = "corto"
    rev = date.fromisoformat(max(f1, f2) or TODAY) + timedelta(days=91)
    while rev <= date.today():
        rev += timedelta(days=91)
    ratios = {"PER": f"{price / e_last:.1f}x" if e_last > 0 else "—",
              "Crecimiento beneficio (5 años)": f"{cagr * 100:.1f} %",
              "Rentab. flujo de caja libre": f"{fcfps / price * 100:.1f} %" if fcfps else "—"}
    item = {"cyclical": cyc, "horizon": hz, "review": rev.isoformat(),
            "review_reason": "próximos resultados trimestrales (fecha estimada)", "ratios": ratios}
    for key in ("dcf", "graham", "multiples"):
        if key in models and models[key] > 0:
            item[key] = round(models[key], 2)
    return item, iv, mg



# ---------- CUENTAS DE LA EMPRESA (5 años) ----------
BAL = {"Activos totales": ["Assets"], "Activo corriente": ["AssetsCurrent"], "Pasivos totales": ["Liabilities"],
       "Pasivo corriente": ["LiabilitiesCurrent"],
       "Patrimonio neto": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
       "Caja": ["CashAndCashEquivalentsAtCarryingValue"], "Deuda a largo plazo": ["LongTermDebtNoncurrent", "LongTermDebt"]}
FLOW = {"Ingresos": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "Beneficio neto": ["NetIncomeLoss"]}
HINTS = {"Ingresos": "Lo que vende al año.",
         "Beneficio neto": "Lo que gana al año después de pagar todos sus gastos.",
         "Flujo de caja libre": "Dinero real que le sobra tras invertir en su negocio.",
         "Caja": "Dinero disponible ahora mismo.",
         "Activos totales": "Todo lo que posee la empresa.",
         "Activo corriente": "Lo que puede convertir en dinero en menos de un año.",
         "Pasivos totales": "Todo lo que debe.",
         "Pasivo corriente": "Lo que tiene que pagar en menos de un año.",
         "Deuda a largo plazo": "Préstamos que vencen dentro de más de un año.",
         "Patrimonio neto": "Lo que quedaría para los accionistas si pagara todas sus deudas."}


def hist_series(facts, names, flow):
    out = {}
    for n in names:
        tmp = {}
        for r in facts.get("us-gaap", {}).get(n, {}).get("units", {}).get("USD", []):
            if flow:
                if "start" not in r or not 340 <= (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days <= 380:
                    continue
            elif "start" in r or r.get("fp") != "FY":
                continue
            if r["end"] not in tmp or r["filed"] > tmp[r["end"]][1]:
                tmp[r["end"]] = (r["val"], r["filed"])
        for k, v in tmp.items():
            out.setdefault(k, v[0])
    return dict(sorted(out.items()))


def pick(dic, end):
    e = date.fromisoformat(end)
    for k in dic:
        if abs((date.fromisoformat(k) - e).days) <= 10:
            return dic[k]
    return None


def judge(s):
    L, acc = [], [0, 0]

    def add(t, x):
        L.append({"t": t, "x": x})
        acc[0] += {"ok": 2, "warn": 1, "bad": 0}[t]
        acc[1] += 2

    def vals(k):
        return [x for x in s.get(k, []) if x is not None]

    ac, pc = vals("Activo corriente"), vals("Pasivo corriente")
    if ac and pc and pc[-1] > 0:
        r = ac[-1] / pc[-1]
        if r >= 1.5:
            add("ok", f"Puede pagar sus deudas a corto plazo con holgura: tiene ${r:.1f} por cada $1 que debe a menos de un año.")
        elif r >= .8:
            add("warn", f"Liquidez justa: tiene ${r:.2f} por cada $1 que debe a menos de un año.")
        else:
            add("bad", "Liquidez débil: lo que debe a menos de un año supera lo que puede convertir en dinero en ese plazo.")
    a, p = vals("Activos totales"), vals("Pasivos totales")
    if a and p and a[-1] > 0:
        r = p[-1] / a[-1]
        add("ok" if r <= .5 else "warn" if r <= .75 else "bad", f"Sus deudas equivalen al {r * 100:.0f} % de todo lo que posee.")
    v = vals("Ingresos")
    if len(v) >= 3 and v[0] > 0 and v[-1] > 0:
        g = (v[-1] / v[0]) ** (1 / (len(v) - 1)) - 1
        if g >= .05:
            add("ok", f"Vende cada vez más: las ventas crecen un {g * 100:.0f} % al año.")
        elif g >= 0:
            add("warn", f"Las ventas apenas crecen ({g * 100:.1f} % al año).")
        else:
            add("bad", f"Las ventas están cayendo ({abs(g) * 100:.1f} % al año).")
    n = vals("Beneficio neto")
    if n:
        if n[-1] <= 0:
            add("bad", "Ahora mismo pierde dinero.")
        elif len(n) > 1 and n[0] > 0 and n[-1] < n[0]:
            add("warn", f"Gana dinero, pero menos que hace {len(n) - 1} años.")
        else:
            add("ok", "Gana dinero y sus beneficios no han bajado.")
    f = vals("Flujo de caja libre")
    if f and n:
        if f[-1] > 0 and n[-1] > 0 and f[-1] >= .8 * n[-1]:
            add("ok", "Sus beneficios se convierten en dinero real en la caja.")
        elif f[-1] > 0:
            add("warn", "Genera caja, aunque menos de lo que gana sobre el papel.")
        else:
            add("bad", "Gasta más dinero del que genera.")
    e = vals("Patrimonio neto")
    if len(e) >= 3 and e[0] > 0:
        add("ok" if e[-1] > e[0] else "warn",
            "Su patrimonio crece: la empresa vale más para sus accionistas." if e[-1] > e[0]
            else "Su patrimonio ha bajado en estos años" + (" (algo habitual en empresas rentables que recompran muchas acciones)." if n and n[-1] > 0 else "."))
    if not acc[1]:
        return {"insights": L, "health": "Sin datos"}
    q = acc[0] / acc[1]
    return {"insights": L, "health": "Sólida" if q >= .75 else "Aceptable" if q >= .5 else "Frágil"}


def fundamentals(facts):
    raw = {k: hist_series(facts, v, k in FLOW) for k, v in {**BAL, **FLOW}.items()}
    cfo = hist_series(facts, ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], True)
    cap = hist_series(facts, ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], True)
    raw["Flujo de caja libre"] = {k: cfo[k] - abs(pick(cap, k) or 0) for k in cfo}
    if not raw["Pasivos totales"]:
        tot = hist_series(facts, ["LiabilitiesAndStockholdersEquity"], False)
        raw["Pasivos totales"] = {k: tot[k] - pick(raw["Patrimonio neto"], k) for k in tot if pick(raw["Patrimonio neto"], k) is not None}
    base = raw["Activos totales"] or raw["Ingresos"]
    if len(base) < 3:
        return None
    ends = list(base)[-5:]
    series = {}
    for k in HINTS:
        vals = [pick(raw[k], e) for e in ends]
        if any(x is not None for x in vals):
            series[k] = [None if x is None else round(x / 1e6) for x in vals]
    return {"years": [e[:4] for e in ends], "series": series, "hints": {k: HINTS[k] for k in series}, **judge(series)}


# ---------- TELEGRAM ----------
def telegram(text):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("Telegram no configurado: se omite el aviso.")
        return
    body = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=body), timeout=30)


def main():
    DATA.mkdir(exist_ok=True)
    HIST.mkdir(exist_ok=True)
    FUND.mkdir(exist_ok=True)
    uni = read_universe()
    cik = {}
    try:
        for v in json.loads(get("https://www.sec.gov/files/company_tickers.json", {"User-Agent": SEC_UA})).values():
            cik[v["ticker"].upper()] = (v["cik_str"], v["title"])
    except Exception as e:
        print("No se pudo leer la lista de empresas de la SEC:", e)

    market, items, hists = {}, {}, {}
    for u in uni:
        t = u["t"]
        got = prices(t)
        if not got:
            print(f"{t}: sin precios, se omite")
            continue
        rows, long_rows = got
        last = rows[-1]
        market[t] = {"c": round(last[4], 2), "o": round(last[1], 2), "h": round(last[2], 2), "l": round(last[3], 2), "v": int(last[5]), "type": u["type"]}
        hists[t] = downsample(long_rows)
        entry = {"type": u["type"], "name": cik.get(t.replace(".", "-"), (0, t))[1].title()}
        items[t] = entry
        if u["type"] == "ACCIONES" and t.replace(".", "-") in cik:
            try:
                n = cik[t.replace(".", "-")][0]
                facts = json.loads(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(n):010d}.json", {"User-Agent": SEC_UA}, 60))["facts"]
                try:
                    fd = fundamentals(facts)
                    if fd:
                        (FUND / f"{t}.json").write_text(json.dumps(fd, ensure_ascii=False), encoding="utf-8")
                        entry["health"] = fd["health"]
                except Exception as e:
                    print(f"{t}: error en cuentas ({e})")
                res = value_stock(t, u["cyc"], facts, long_rows, last[4])
                time.sleep(0.2)
                if isinstance(res, tuple):
                    item, iv, mg = res
                    entry.update(item)
                    entry["_iv"], entry["_mg"] = iv, mg
                else:
                    print(f"{t}: sin valorar ({res})")
            except Exception as e:
                print(f"{t}: error de valoración ({e})")

    if not market:
        print("No se obtuvo ningún precio. No se modifica nada.")
        sys.exit(1)

    (DATA / "market-data.json").write_text(json.dumps(market), encoding="utf-8")
    for t, h in hists.items():
        (HIST / f"{t}.json").write_text(json.dumps(h), encoding="utf-8")

    buys = []
    for t, e in items.items():
        iv, mg = e.pop("_iv", None), e.pop("_mg", None)
        if iv is not None and verdict(mg, e.get("health")) == "COMPRAR":
            buys.append((mg, t, e, iv))
    buys.sort(reverse=True)
    (DATA / "valuations.json").write_text(json.dumps({"updated": TODAY, "items": items}, ensure_ascii=False), encoding="utf-8")

    # Historial de señales: solo se añaden filas nuevas, nunca se editan
    sp = DATA / "signals.json"
    sig = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else []
    recent = {s["ticker"] for s in sig if s["date"] >= (date.today() - timedelta(days=90)).isoformat()}
    spy = market.get("SPY", {}).get("c")
    new = []
    for mg, t, e, iv in buys:
        if t not in recent:
            row = {"date": TODAY, "ticker": t, "verdict": "COMPRAR", "price": market[t]["c"]}
            if spy:
                row["spy"] = spy
            sig.append(row)
            new.append(t)
    sp.write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")

    # Aviso diario
    if buys:
        lines = [f"Lista principal · {TODAY}", ""]
        for mg, t, e, iv in buys[:15]:
            lines.append(f"{t}{' (nueva)' if t in new else ''}: ${market[t]['c']} · valor ${iv:.2f} · margen {mg:.0f} % · plazo {e['horizon']}{' · cíclica' if e['cyclical'] else ''}")
        lines += ["", "Información, no asesoramiento financiero."]
    else:
        lines = [f"Lista principal · {TODAY}", "", "Hoy no hay oportunidades con margen de seguridad suficiente."]
    telegram("\n".join(lines))
    print(f"Listo: {len(market)} activos, {len(buys)} oportunidades.")


if __name__ == "__main__":
    main()
