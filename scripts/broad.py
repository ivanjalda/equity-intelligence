#!/usr/bin/env python3
"""Equity Intelligence: mercado amplio (miles de acciones de EE. UU.).
  python scripts/broad.py weekly  -> calcula valoraciones de todas las empresas (lento, 1 vez por semana)
  python scripts/broad.py daily   -> actualiza precios de todas con UNA consulta y avisa de oportunidades"""
import json, os, re, sys, time, urllib.error
from datetime import date, timedelta
from statistics import mean, pstdev
from engine import (get, annual, dcf, clamp, fundamentals, verdict, rank, is_financial, telegram, prices_polygon, downsample,
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
    cyc = len(v) >= 6 and (min(v[-8:]) <= 0 or pstdev(v[-8:]) / max(abs(mean(v[-8:])), 1e-9) > .5)
    e_use = mean(v[-7:]) if cyc else v[-1]
    win = v[-6:]
    cagr = (win[-1] / win[0]) ** (1 / (len(win) - 1)) - 1 if len(win) > 2 and win[0] > 0 and win[-1] > 0 else 0.0
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
    return {"cyclical": cyc, "horizon": "largo" if stable and not cyc else "medio", "review": rev.isoformat(),
            "review_reason": "próximos resultados trimestrales (fecha estimada)",
            "ratios": {"Crecimiento beneficio (5 años)": f"{cagr * 100:.1f} %"},
            **{a: round(b, 2) for a, b in m.items()}}


def weekly():
    day, bars = grouped()
    if not bars:
        sys.exit("No se pudo obtener la lista de acciones. Fin.")
    ex = get("https://www.sec.gov/files/company_tickers_exchange.json", {"User-Agent": SEC_UA})
    rows = json.loads(ex)["data"]
    skip = re.compile(r"\b(ETF|FUND|TRUST|ETN|NOTES|ACQUISITION|WARRANT)\b", re.I)
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
    items, ok = {}, 0
    for i, (_, tk, cik, name) in enumerate(cands):
        try:
            facts = json.loads(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json", {"User-Agent": SEC_UA}, 90))["facts"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(30)
            continue
        except Exception:
            continue
        try:
            if is_financial(facts):
                items[tk] = {"type": "ACCIONES", "name": name.title(), "kind": "financiera"}
                continue
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
            print(f"  {i}/{len(cands)} revisadas, {ok} valoradas")
        time.sleep(0.12)
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
        vals["items"][t] = dict(m)
        nums = [m[k] for k in ("dcf", "graham") if k in m]
        if not nums:
            continue
        iv = sum(nums) / len(nums)
        mg = (iv - b["c"]) / iv * 100
        if verdict(mg, m.get("health")) == "COMPRAR":
            buys.append((mg, t, iv, m))
    mp.write_text(json.dumps(market), encoding="utf-8")
    vp.write_text(json.dumps({**vals, "updated": vals.get("updated", TODAY)}, ensure_ascii=False), encoding="utf-8")
    buys.sort(key=lambda x: rank(x[0], x[3].get("health"), x[3].get("cyclical")), reverse=True)
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
    lines = [f"Mercado amplio · {TODAY}", f"{len(buys)} oportunidades entre {len(mods)} acciones analizadas.", ""]
    for mg, t, iv, m in buys[:15]:
        lines.append(f"{t}{' (nueva)' if t in new else ''}: ${market[t]['c']} · valor ${iv:.2f} · margen {mg:.0f} % · salud {str(m.get('health', '—')).lower()}")
    if len(buys) > 15:
        lines.append(f"…y {len(buys) - 15} más en la web.")
    lines += ["", "Información, no asesoramiento financiero."]
    telegram("\n".join(lines))
    print(f"Mercado amplio listo: {len(buys)} oportunidades, {made} gráficos nuevos.")


if __name__ == "__main__":
    {"weekly": weekly, "daily": daily}.get(sys.argv[1] if len(sys.argv) > 1 else "", daily)()
