#!/usr/bin/env python3
"""Equity Intelligence: mercado amplio (miles de acciones de EE. UU.).
  python scripts/broad.py weekly  -> calcula valoraciones de todas las empresas (lento, 1 vez por semana)
  python scripts/broad.py daily   -> actualiza precios de todas con UNA consulta y avisa de oportunidades"""
import json, os, re, sys, time, urllib.error
from datetime import date, timedelta
from statistics import mean, median, pstdev
from mensajes import build_broad
from engine import (get, annual, dcf, clamp, fundamentals, verdict, rank, spread, finalize, base_checks, get_sic, eps_growth, is_finance_sic, is_investment_company, normalize_facts, hist_series, pick, TERMINAL, DISCOUNT, telegram, prices_polygon, downsample,
                    DATA, FUND, HIST, TODAY, POLY, SEC_UA, YIELD_AAA, read_universe)

MODELS = DATA / "models.json"


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def grouped():
    """Precios de TODAS las acciones de EE. UU. en una consulta (último día cerrado con datos).
    El plan gratuito no da el día en curso, así que se empieza por ayer y se retrocede."""
    denied = 0
    for back in range(1, 9):
        day = (date.today() - timedelta(days=back)).isoformat()
        url = f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{day}?adjusted=true&apiKey={POLY}"
        for intento in range(2):
            try:
                res = json.loads(get(url, timeout=90)).get("results") or []
                if res:
                    print(f"Datos de todo el mercado del día {day}: {len(res)} valores.")
                    return day, {r["T"]: r for r in res}
                print(f"{day}: sin datos (fin de semana o festivo).")
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and intento == 0:
                    time.sleep(65)
                    continue
                print(f"{day}: Polygon respondió {e.code}.")
                if e.code in (401, 403):
                    denied += 1
                break
        time.sleep(12.5)
    if denied >= 8:
        print("Tu plan de Polygon no permite la consulta de todo el mercado. Se omite el mercado amplio.")
    return None, {}


def is_cyclical(v):
    """Cíclica = beneficios que suben y bajan de forma repetida.
    Un bache antiguo seguido de una recuperación sostenida (p. ej. Alcon) no cuenta."""
    w = v[-8:]
    nonpos8 = sum(1 for x in w if x <= 0)
    nonpos5 = sum(1 for x in v[-5:] if x <= 0)
    drops = sum(1 for a, c in zip(w, w[1:]) if a > 0 and c < a * 0.75)
    cv = pstdev(w) / max(abs(mean(w)), 1e-9)
    return len(v) >= 5 and (nonpos8 >= 3 or (nonpos5 >= 1 and drops >= 1) or (cv > .35 and drops >= 2))


def bank_sic(sic):
    return 6000 <= sic <= 6199 or 6300 <= sic <= 6411


def bank_models(facts):
    """Bancos y aseguradoras: valor contable justificado por su rentabilidad (ROE) y número de Graham."""
    eps, f1 = annual(facts, ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"], "USD/shares")
    ni, _ = annual(facts, ["NetIncomeLoss"], "USD")
    shs, _ = annual(facts, ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"], "shares")
    eq = hist_series(facts, ["StockholdersEquity"], False)
    pref = hist_series(facts, ["PreferredStockValue"], False)
    if len(eps) < 3 or not eq:
        return None
    ends = list(eps)
    roes = []
    for e in ends[-5:]:
        q = pick(eq, e)
        if q is not None and e in ni and q - (pick(pref, e) or 0) > 0:
            roes.append(ni[e] / (q - (pick(pref, e) or 0)))
    if len(roes) < 3:
        return None
    roe = clamp(median(roes), 0.0, 0.25)
    k = ends[-1]
    q, s = pick(eq, k), shs.get(k)
    if q is None or not s:
        return None
    bvps = (q - (pick(pref, k) or 0)) / s
    if bvps <= 0 or roe <= TERMINAL:
        return None
    m = {"pb": bvps * (roe - TERMINAL) / (DISCOUNT - TERMINAL)}
    eps_use = mean(eps[x] for x in ends[-3:])
    if eps_use > 0:
        m["gnum"] = (22.5 * eps_use * bvps) ** 0.5
    while len(m) >= 2 and max(m.values()) > 3 * min(m.values()):
        m.pop(max(m, key=m.get))
    if len(m) < 2:
        return None
    rev = date.fromisoformat(f1 or TODAY) + timedelta(days=91)
    while rev <= date.today():
        rev += timedelta(days=91)
    return {"kind": "banco", "cyclical": False, "horizon": "largo", "review": rev.isoformat(),
            "review_reason": "próximos resultados trimestrales (fecha estimada)",
            "ratios": {"ROE medio (5 años)": f"{roe * 100:.1f} %", "Valor contable por acción": f"${bvps:.2f}"},
            "eps": round(eps[k], 2), "sh": round(s),
            "chk": [{"t": a, "x": c} for a, c in base_checks(eps, ni, shs)],
            **{a: round(c, 2) for a, c in m.items()}}


def basic_models(facts):
    eps, f1 = annual(facts, ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"], "USD/shares")
    cfo, f2 = annual(facts, ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], "USD")
    cap, _ = annual(facts, ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], "USD")
    ni, _ = annual(facts, ["NetIncomeLoss"], "USD")
    shs, _ = annual(facts, ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"], "shares")
    if len(eps) < 3:
        eps = {k: ni[k] / shs[k] for k in ni if shs.get(k)}
    if len(eps) < 3 or not cfo:
        return None
    ends = list(eps)
    v = [eps[k] for k in ends]
    cyc = is_cyclical(v)
    e_use = mean(v[-7:]) if cyc else v[-1]
    cagr = eps_growth(v)
    g = .03 if cyc else clamp(cagr, 0.0, 0.12)
    m = {}
    if e_use > 0:
        m["graham"] = e_use * (8.5 + 2 * g * 100) * 4.4 / YIELD_AAA
    k = ends[-1]
    shares = shs.get(k) or (ni[k] / eps[k] if k in ni and eps[k] > 0 else None)
    fcf = [cfo[x] - abs(cap.get(x, 0)) for x in list(cfo)[-(7 if cyc else 3):]]
    if shares and shares > 0 and fcf and mean(fcf) > 0:
        m["dcf"] = dcf(mean(fcf) / shares, g)
    m = {a: b for a, b in m.items() if b > 0}
    while len(m) >= 2 and max(m.values()) > 3 * min(m.values()):
        m.pop(max(m, key=m.get))
    if len(m) < 2:
        return None
    rev = date.fromisoformat(max(f1, f2) or TODAY) + timedelta(days=91)
    while rev <= date.today():
        rev += timedelta(days=91)
    stable = all(x > 0 for x in v[-5:]) and cagr >= .05
    res = {"cyclical": cyc, "horizon": "largo" if stable and not cyc else "medio", "review": rev.isoformat(),
            "review_reason": "próximos resultados trimestrales (fecha estimada)",
            "ratios": {"Crecimiento beneficio (5 años)": f"{cagr * 100:.1f} %"},
            **{a: round(b, 2) for a, b in m.items()}}
    chk = base_checks(eps, ni, shs)
    if shares and shares > 0:
        res["sh"] = round(shares)
    res["chk"] = [{"t": a, "x": c} for a, c in chk]
    res["eps"] = round(v[-1], 2)
    return res


def weekly():
    day, bars = grouped()
    if not bars:
        sys.exit("No se pudo obtener la lista de acciones. Fin.")
    ex = get("https://www.sec.gov/files/company_tickers_exchange.json", {"User-Agent": SEC_UA})
    rows = json.loads(ex)["data"]
    skip = re.compile(r"\b(ETF|FUND|TRUST|ETN|NOTES|ACQUISITION|WARRANT|BDC)\b", re.I)
    core = {u["t"] for u in read_universe()}
    cands = []
    for cik, name, tk, exch in rows:
        b = bars.get(tk)
        if exch not in ("Nasdaq", "NYSE") or not b or tk in core or skip.search(name) or not re.fullmatch(r"[A-Z]{1,5}", tk):
            continue
        if b["c"] >= 3 and b["v"] >= 150000:
            cands.append((b["c"] * b["v"], tk, cik, name))
    cands.sort(reverse=True)
    cands = cands[:4500]
    print(f"Empresas a analizar: {len(cands)}")
    FUND.mkdir(exist_ok=True)
    items, ok, fails, seguidos = {}, 0, {}, 0
    for i, (_, tk, cik, name) in enumerate(cands):
        facts, frenado = None, False
        for intento in range(3):  # la SEC pide ir despacio: si nos frena (403/429) esperamos y reintentamos
            try:
                facts = json.loads(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json", {"User-Agent": SEC_UA}, 90))["facts"]
                break
            except urllib.error.HTTPError as e:
                fails[e.code] = fails.get(e.code, 0) + 1
                if e.code == 404:  # esa empresa no tiene cuentas en formato estándar
                    break
                frenado = frenado or e.code in (403, 429)
                time.sleep(60 if e.code in (403, 429) else 5)
            except Exception as e:
                fails[type(e).__name__] = fails.get(type(e).__name__, 0) + 1
                time.sleep(5)
        time.sleep(0.15)
        seguidos = seguidos + 1 if (facts is None and frenado) else 0
        if seguidos >= 8:
            sys.exit(f"La SEC nos está frenando (8 empresas seguidas rechazadas). Se detiene sin guardar. Incidencias: {fails}")
        if facts is None:
            continue
        try:
            sic = get_sic(cik)
            if sic is None:
                continue  # sin poder confirmar el sector, mejor no valorarla esta semana
            if is_investment_company(facts):
                items[tk] = {"type": "ACCIONES", "name": name.title(), "kind": "financiera"}
                continue
            if is_finance_sic(sic):
                bm = bank_models(facts) if bank_sic(sic) else None
                if bm:
                    items[tk] = {"type": "ACCIONES", "name": name.title(), **bm}
                    ok += 1
                else:
                    items[tk] = {"type": "ACCIONES", "name": name.title(), "kind": "financiera"}
                continue
            facts = normalize_facts(facts)
            m = basic_models(facts)
            if m:
                fd = fundamentals(facts)
                if fd:
                    (FUND / f"{tk}.json").write_text(json.dumps(fd, ensure_ascii=False), encoding="utf-8")
                    m["health"] = fd["health"]
                items[tk] = {"type": "ACCIONES", "name": name.title(), **m}
                ok += 1
        except Exception as e:
            print(f"{tk}: error ({e})")
        if i % 200 == 0:
            print(f"  {i}/{len(cands)} revisadas, {ok} valoradas, incidencias de la SEC: {fails or 'ninguna'}")
        time.sleep(0.12)
    prev = len(load(MODELS, {"items": {}})["items"])
    print(f"Incidencias de la SEC en total: {fails or 'ninguna'}")
    if len(items) < 500 or (prev >= 500 and len(items) < prev * 0.5):
        sys.exit(f"Resultado sospechosamente pequeño ({len(items)} empresas; la vez anterior {prev}). No se guarda para no perder las valoraciones buenas.")
    MODELS.write_text(json.dumps({"updated": TODAY, "items": items}, ensure_ascii=False), encoding="utf-8")
    print(f"Listo: {ok} empresas valoradas de {len(cands)}.")


def daily():
    mods = load(MODELS, {"items": {}})["items"]
    if not mods:
        print("Aún no hay valoraciones del mercado amplio (ejecuta primero la tarea semanal).")
        return
    day, bars = grouped()
    if not bars:
        return
    mp, vp, sp = DATA / "market-data.json", DATA / "valuations.json", DATA / "signals.json"
    market, vals = load(mp, {}), load(vp, {"items": {}})
    core = set(vals["items"])
    buys = []
    for t, m in mods.items():
        b = bars.get(t)
        if not b or t in core:
            continue
        market[t] = {"c": round(b["c"], 2), "o": round(b["o"], 2), "h": round(b["h"], 2), "l": round(b["l"], 2), "v": int(b["v"]), "type": "ACCIONES"}
        item = {k: v for k, v in m.items() if k != "chk"}
        vals["items"][t] = item
        nums = [m[k] for k in ("dcf", "graham", "pb", "gnum") if k in m]
        if not nums:
            continue
        iv = sum(nums) / len(nums)
        mg = (iv - b["c"]) / iv * 100
        fiab, warns, n = finalize(m, b["c"], mg)
        item.update(fiab=fiab, checks=warns, nchk=n)
        if verdict(mg, m.get("health"), fiab) == "COMPRAR":
            buys.append((mg, t, iv, item))
    mp.write_text(json.dumps(market), encoding="utf-8")
    vp.write_text(json.dumps({**vals, "updated": vals.get("updated", TODAY)}, ensure_ascii=False), encoding="utf-8")
    buys.sort(key=lambda x: rank(x[0], x[3].get("health"), x[3].get("cyclical"), spread(x[3]), x[3].get("fiab")), reverse=True)
    # histórico para el gráfico de las mejores oportunidades
    HIST.mkdir(exist_ok=True)
    made = 0
    for mg, t, iv, m in buys[:30]:
        f = HIST / f"{t}.json"
        if f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
            continue
        try:
            rows = prices_polygon(t)
            if len(rows) > 30:
                f.write_text(json.dumps(downsample(rows)), encoding="utf-8")
                made += 1
        except Exception as e:
            print(f"{t}: sin histórico ({e})")
        time.sleep(12.5)
    # gráficos de las empresas más grandes que aún no tienen (20 por ejecución)
    big = sorted((t for t in mods if t in market and mods[t].get("sh") and t not in core),
                 key=lambda t: -market[t]["c"] * mods[t]["sh"])
    extra = 0
    for t in big:
        if extra >= 20:
            break
        f = HIST / f"{t}.json"
        if f.exists():
            continue
        try:
            rows = prices_polygon(t)
            if len(rows) > 30:
                f.write_text(json.dumps(downsample(rows)), encoding="utf-8")
                extra += 1
        except Exception as e:
            print(f"{t}: sin histórico ({e})")
        time.sleep(12.5)
    made += extra
    # señales y aviso
    sig = load(sp, [])
    recent = {s["ticker"] for s in sig if s["date"] >= (date.today() - timedelta(days=90)).isoformat()}
    spy = market.get("SPY", {}).get("c")
    new = []
    for mg, t, iv, m in buys[:25]:  # en el historial solo se registran las 25 mejores señales del día
        if t not in recent:
            row = {"date": TODAY, "ticker": t, "verdict": "COMPRAR", "price": market[t]["c"]}
            if spy:
                row["spy"] = spy
            sig.append(row)
            new.append(t)
    sp.write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(mods) < 500:
        telegram(f"⚠️ <b>Aviso técnico · mercado amplio</b>\nLa valoración semanal solo tiene {len(mods)} empresas (debería tener miles). "
                 f"No se envía el resumen del mercado amplio hasta repetirla (Actions → Valoración semanal → Run workflow).")
    else:
        telegram(build_broad(buys, new, len(mods), market, sig, TODAY))
    print(f"Mercado amplio listo: {len(buys)} oportunidades, {made} gráficos nuevos.")


if __name__ == "__main__":
    {"weekly": weekly, "daily": daily}.get(sys.argv[1] if len(sys.argv) > 1 else "", daily)()
