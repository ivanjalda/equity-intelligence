#!/usr/bin/env python3
"""Equity Intelligence: grandes fondos (informes 13F de la SEC).
Descarga el último informe y el anterior de cada gestor, compara posiciones y genera data/13f.json."""
import difflib, json, re, sys, time
import xml.etree.ElementTree as ET
from collections import Counter
from engine import get, DATA, TODAY, SEC_UA

# (CIK, palabra que debe aparecer en el nombre oficial de la SEC, gestor). Si el nombre no coincide, se omite.
MANAGERS = [
    (1067983, "BERKSHIRE", "Warren Buffett"), (1336528, "PERSHING", "Bill Ackman"),
    (1350694, "BRIDGEWATER", "Ray Dalio"), (1649339, "SCION", "Michael Burry"),
    (1029160, "SOROS", "George Soros"), (1536411, "DUQUESNE", "Stanley Druckenmiller"),
    (1656456, "APPALOOSA", "David Tepper"), (1040273, "THIRD POINT", "Dan Loeb"),
    (1167483, "TIGER GLOBAL", "Chase Coleman"), (1079114, "GREENLIGHT", "David Einhorn"),
    (1061768, "BAUPOST", "Seth Klarman"), (921669, "ICAHN", "Carl Icahn"),
    (1056831, "FAIRHOLME", "Bruce Berkowitz"), (1061165, "LONE PINE", "Stephen Mandel"),
    (1103804, "VIKING", "Andreas Halvorsen"), (1135730, "COATUE", "Philippe Laffont"),
    (783412, "DAILY JOURNAL", "Daily Journal Corp."), (1709323, "HIMALAYA", "Li Lu"),
    (1549575, "DALAL", "Mohnish Pabrai"), (1112520, "AKRE", "Chuck Akre"),
    (1345471, "TRIAN", "Nelson Peltz"), (1105510, "VALUEACT", "ValueAct"),
    (1791786, "ELLIOTT", "Paul Singer"), (200217, "DODGE", "Dodge & Cox"),
    (1037389, "RENAISSANCE", "Jim Simons (Renaissance)"), (1603466, "POINT72", "Steve Cohen"),
]
H = {"User-Agent": SEC_UA}
STOP = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LP", "LLC", "HOLDINGS", "HLDGS", "GROUP",
        "THE", "OF", "AND", "NEW", "DEL", "COM", "CL", "CLASS", "A", "B", "C", "SHS", "ORD", "ADR", "SPONSORED", "N", "V",
        "SA", "NV", "AG", "SE", "DE", "ETF", "CAP", "STK"}


def norm(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", s.upper().replace("&", " AND "))
    return " ".join(w for w in s.split() if w not in STOP)


def sec_get(url):
    time.sleep(0.15)
    return get(url, H, 60)


def filings(cik):
    d = json.loads(sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    r = d["filings"]["recent"]
    rows = sorted({(r["reportDate"][i], r["filingDate"][i], r["accessionNumber"][i])
                   for i, f in enumerate(r["form"]) if f == "13F-HR"}, reverse=True)
    seen, out = set(), []
    for row in rows:
        if row[0] not in seen:
            seen.add(row[0])
            out.append(row)
    return d["name"], out[:2]


def positions(cik, acc, period):
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
    items = json.loads(sec_get(base + "/index.json"))["directory"]["item"]
    xmls = [x for x in items if x["name"].lower().endswith(".xml") and "primary_doc" not in x["name"].lower()]
    if not xmls:
        raise ValueError("no hay tabla de posiciones")
    xmls.sort(key=lambda x: int(x.get("size") or 0), reverse=True)
    root = ET.fromstring(sec_get(f"{base}/{xmls[0]['name']}"))
    mult = 1 if period >= "2022-12-31" else 1000  # desde 2023 el valor se informa en dólares
    pos = {}
    for it in root.iter():
        if it.tag.split("}")[-1] != "infoTable":
            continue
        d = {c.tag.split("}")[-1]: c for c in it}
        if "putCall" in d:
            continue  # opciones fuera
        sh = d.get("shrsOrPrnAmt")
        sd = {c.tag.split("}")[-1]: (c.text or "") for c in sh} if sh is not None else {}
        if sd.get("sshPrnamtType", "SH") != "SH":
            continue
        p = pos.setdefault((d["cusip"].text or "").strip(), {"name": (d["nameOfIssuer"].text or "").strip(), "value": 0.0, "shares": 0.0})
        p["value"] += float(d["value"].text) * mult
        p["shares"] += float(sd.get("sshPrnamt") or 0)
    return pos


def ticker_tools():
    market = json.loads((DATA / "market-data.json").read_text(encoding="utf-8")) if (DATA / "market-data.json").exists() else {}
    names = {}
    for v in json.loads(get("https://www.sec.gov/files/company_tickers.json", H)).values():
        names.setdefault(norm(v["title"]), []).append(v["ticker"].upper())

    def dv(t):
        m = market.get(t)
        return m["c"] * m["v"] if m else 0
    best = {k: max(v, key=lambda t: (t in market, dv(t), -len(t))) for k, v in names.items()}
    keys = list(best)

    def to_ticker(name):
        k = norm(name)
        if k in best:
            return best[k]
        m = difflib.get_close_matches(k, keys, n=1, cutoff=0.92)
        return best[m[0]] if m else None
    return to_ticker


def build(cik, expect, who, to_ticker):
    name, fl = filings(cik)
    if expect not in name.upper():
        print(f"  {cik}: el nombre oficial es '{name}', no coincide con '{expect}'. Se omite.")
        return None
    if not fl:
        print(f"  {name}: sin informes 13F recientes.")
        return None
    period, filed, acc = fl[0]
    cur = positions(cik, acc, period)
    prev = positions(cik, fl[1][2], fl[1][0]) if len(fl) > 1 else {}
    total = sum(p["value"] for p in cur.values())
    if total <= 0:
        return None
    out = []
    for cusip, p in sorted(cur.items(), key=lambda kv: -kv[1]["value"])[:30]:
        pv = prev.get(cusip)
        delta = None
        if not prev:
            action = "igual"
        elif not pv:
            action = "nuevo"
        else:
            delta = (p["shares"] / pv["shares"] - 1) * 100 if pv["shares"] else None
            action = "igual" if delta is None or abs(delta) < 1 else ("compra" if delta > 0 else "venta")
        out.append({"ticker": to_ticker(p["name"]), "name": p["name"].title(), "pct": round(p["value"] / total * 100, 2),
                    "value": round(p["value"]), "action": action, "delta": None if delta is None else round(delta)})
    sold = [{"ticker": to_ticker(pv["name"]), "name": pv["name"].title(), "value": round(pv["value"])}
            for c, pv in sorted(prev.items(), key=lambda kv: -kv[1]["value"]) if c not in cur][:8]
    print(f"  {name}: {len(cur)} posiciones, {sum(1 for x in out if x['ticker']) }/{len(out)} con ticker, informe {period}.")
    return {"id": cik, "name": name.title(), "who": who, "period": period, "filed": filed,
            "value": round(total), "count": len(cur), "positions": out, "sold": sold}


def ranking(mans, pick, n=12):
    c, names = Counter(), {}
    for m in mans:
        seen = set()
        for p in pick(m):
            k = p["ticker"] or p["name"]
            names[k] = p
            if k not in seen:
                seen.add(k)
                c[k] += 1
    return [{"ticker": names[k]["ticker"], "name": names[k]["name"], "funds": n_} for k, n_ in
            sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def main():
    to_ticker = ticker_tools()
    mans = []
    for cik, expect, who in MANAGERS:
        try:
            m = build(cik, expect, who, to_ticker)
            if m:
                mans.append(m)
        except Exception as e:
            print(f"  {cik} ({who}): error ({e})")
    if not mans:
        sys.exit("No se pudo leer ningún informe 13F. No se modifica nada.")
    per = Counter(m["period"] for m in mans).most_common(1)[0][0]
    y, mth = int(per[:4]), int(per[5:7])
    data = {
        "updated": TODAY, "quarter": f"{y}-T{(mth - 1) // 3 + 1}", "filed": max(m["filed"] for m in mans), "total": len(mans),
        "top": ranking(mans, lambda m: m["positions"][:15]),
        "buys": ranking(mans, lambda m: [p for p in m["positions"] if p["action"] == "nuevo" or (p["delta"] or 0) >= 20]),
        "sells": ranking(mans, lambda m: [p for p in m["positions"] if p["action"] == "venta" and (p["delta"] or 0) <= -20] + m["sold"]),
        "managers": mans,
    }
    (DATA / "13f.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"Listo: {len(mans)} gestores de {len(MANAGERS)}.")


if __name__ == "__main__":
    main()
