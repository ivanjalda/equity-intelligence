# -*- coding: utf-8 -*-
"""Prueba de acierto de Equity Intelligence.
Para cada fecha del pasado (cada trimestre desde 2018) recalcula el valor intrínseco de cada acción del motor diario usando
SOLO los datos que existían ese día (cuentas presentadas a la SEC hasta esa fecha y precios hasta esa fecha), y mira qué hizo
el precio en los 12 meses siguientes frente al índice S&P 500 (SPY).
Resultado: data/prueba.json y una tabla en el registro."""
import copy, json, sys, time, statistics as st
from datetime import date, timedelta
from pathlib import Path

import engine

DATA = Path("data")
FIX_RATE = engine.DISCOUNT          # tasa fija 10 %: no tenemos el bono ni la beta de aquellos años
engine.rate_for = lambda t: (FIX_RATE, None)
HORIZ = 365


def facts_asof(facts, asof):
    out = {}
    for tax, tags in facts.items():
        out[tax] = {}
        for tag, v in tags.items():
            units = {u: [r for r in rows if r.get("filed", "9999") <= asof] for u, rows in v.get("units", {}).items()}
            if any(units.values()):
                out[tax][tag] = {"units": units}
    return out


def price_at(rows, day, after=False):
    """Primer cierre en o después de 'day' (after) o último en o antes."""
    if after:
        for r in rows:
            if r[0] >= day:
                return r[0], r[4]
        return None
    best = None
    for r in rows:
        if r[0] <= day:
            best = r
        else:
            break
    return (best[0], best[4]) if best else None


def fechas(desde, hasta):
    y, m = desde
    while date(y, m, 1) <= hasta:
        yield date(y, m, 1)
        m += 3
        if m > 12:
            m, y = m - 12, y + 1


def observaciones(t, cyc, facts, rows, spy_rows, hoy=None, desde=(2018, 1)):
    hoy = hoy or date.today()
    obs = []
    for d in fechas(desde, hoy - timedelta(days=HORIZ + 7)):
        asof = d.isoformat()
        p0 = price_at(rows, asof)
        if not p0:
            continue
        hist = [r for r in rows if r[0] <= p0[0]]
        if len(hist) < 400:
            continue
        res = engine.value_stock(t, cyc, facts_asof(facts, asof), hist, p0[1])
        if not isinstance(res, tuple):
            continue
        _, iv, mg = res
        fin = (d + timedelta(days=HORIZ)).isoformat()
        p1 = price_at(rows, fin, after=True)
        s0, s1 = price_at(spy_rows, p0[0]), price_at(spy_rows, fin, after=True)
        if not (p1 and s0 and s1):
            continue
        r_acc, r_spy = p1[1] / p0[1] - 1, s1[1] / s0[1] - 1
        obs.append({"t": t, "d": asof, "mg": round(mg, 1), "iv": round(iv, 2), "p": round(p0[1], 2), "ret": round(r_acc, 4), "spy": round(r_spy, 4)})
    return obs


def grupo(o):
    if o["mg"] >= 25:
        return "Oportunidad (margen ≥ 25 %)"
    if o["mg"] >= 0:
        return "Esperar (margen 0–25 %)"
    return "Cara (margen < 0)"


def resumen(obs):
    out = []
    for g in ("Oportunidad (margen ≥ 25 %)", "Esperar (margen 0–25 %)", "Cara (margen < 0)", "Todas"):
        L = [o for o in obs if g == "Todas" or grupo(o) == g]
        if not L:
            out.append({"g": g, "n": 0})
            continue
        ex = [o["ret"] - o["spy"] for o in L]
        out.append({"g": g, "n": len(L), "ret_medio": round(st.mean(o["ret"] for o in L) * 100, 1),
                    "ret_mediana": round(st.median(o["ret"] for o in L) * 100, 1),
                    "spy_medio": round(st.mean(o["spy"] for o in L) * 100, 1),
                    "exceso_medio": round(st.mean(ex) * 100, 1),
                    "ganan_al_indice": round(sum(1 for x in ex if x > 0) / len(L) * 100)})
    return out


def main():
    uni = [u for u in engine.read_universe() if u["type"] == "ACCIONES"]
    cik = {}
    for v in json.loads(engine.get("https://www.sec.gov/files/company_tickers.json", {"User-Agent": engine.SEC_UA})).values():
        cik[v["ticker"].upper()] = v["cik_str"]
    spy = engine.prices("SPY")
    if not spy:
        sys.exit("No se pudo obtener el índice de comparación (SPY).")
    spy_rows = spy[1]
    obs = []
    for u in uni:
        t = u["t"]
        n = cik.get(t.replace(".", "-"))
        got = engine.prices(t)
        if not n or not got:
            continue
        try:
            facts = json.loads(engine.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(n):010d}.json", {"User-Agent": engine.SEC_UA}, 60))["facts"]
            facts = engine.normalize_facts(facts)
            o = observaciones(t, u["cyc"], facts, got[1], spy_rows)
            obs += o
            print(f"{t}: {len(o)} observaciones")
        except Exception as e:
            print(f"{t}: error ({e})")
        time.sleep(0.2)
    res = resumen(obs)
    nota = ("Prueba con las acciones del motor diario de hoy (sesgo de supervivencia: incluye empresas que han salido bien parada), "
            "tasa de descuento fija del 10 %, sin dividendos y con ventanas de 12 meses que se solapan. Sirve para comparar grupos entre sí, no para prometer rentabilidades.")
    DATA.mkdir(exist_ok=True)
    (DATA / "prueba.json").write_text(json.dumps({"fecha": date.today().isoformat(), "horizonte_meses": 12, "resumen": res, "nota": nota,
                                                  "n_empresas": len({o["t"] for o in obs})}, ensure_ascii=False), encoding="utf-8")
    print("\nRESULTADO (12 meses después):")
    for r in res:
        if r["n"]:
            print(f"  {r['g']}: {r['n']} casos · acción {r['ret_medio']} % · índice {r['spy_medio']} % · exceso {r['exceso_medio']} puntos · ganan al índice {r['ganan_al_indice']} %")
    print(nota)


if __name__ == "__main__":
    main()
