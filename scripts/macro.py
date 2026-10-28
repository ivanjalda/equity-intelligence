#!/usr/bin/env python3
"""Equity Intelligence: bonos, materias primas e índices con datos reales.
 - Bonos: rentabilidad actual frente a los últimos 10 años (Reserva Federal, FRED).
 - Materias primas: precio ajustado a inflación frente a su historia.
 - Índices (S&P 500, Nasdaq 100, small caps): valor intrínseco agregado de nuestras empresas valoradas."""
import bisect, csv, io, json
from datetime import date, timedelta
from statistics import mean, median
from engine import get, DATA, HIST, TODAY, SEC_UA, telegram, verdict

SRC = "Datos: Reserva Federal de EE. UU. (FRED) y precios de mercado. Información, no asesoramiento financiero."
BONDS = {  # ticker: (serie FRED, descripción, tipo, ¿plazo largo?)
    "TLT": ("DGS20", "bonos del Tesoro a 20 años", "yield", True),
    "IEF": ("DGS10", "bonos del Tesoro a 10 años", "yield", True),
    "SHY": ("DGS2", "bonos del Tesoro a 2 años", "yield", False),
    "GOVT": ("DGS10", "bonos del Tesoro (referencia: 10 años)", "yield", True),
    "BND": ("DGS10", "bonos de EE. UU. (referencia: Tesoro a 10 años)", "yield", True),
    "AGG": ("DGS10", "bonos de EE. UU. (referencia: Tesoro a 10 años)", "yield", True),
    "BIL": ("DGS3MO", "letras del Tesoro a 3 meses", "yield", False),
    "SHV": ("DGS3MO", "letras del Tesoro a 3 meses", "yield", False),
    "TIP": ("DFII10", "bonos del Tesoro ligados a la inflación", "yield", True),
    "TIPX": ("DFII10", "bonos del Tesoro ligados a la inflación", "yield", True),
    "LQD": ("BAMLC0A0CM", "bonos de empresas de alta calidad", "spread", True),
    "VCIT": ("BAMLC0A0CM", "bonos de empresas de alta calidad", "spread", True),
    "VCSH": ("BAMLC0A0CM", "bonos de empresas de alta calidad", "spread", False),
    "HYG": ("BAMLH0A0HYM2", "bonos de empresas de alto riesgo", "spread", False),
    "EMB": ("BAMLEMCBPIOAS", "bonos de empresas de países emergentes", "spread", False),
}
COMMS = {  # ticker: (fuente, descripción, ¿fondo de futuros?)
    "GLD": ("etf", "oro", False), "IAU": ("etf", "oro", False), "SLV": ("etf", "plata", False),
    "PPLT": ("etf", "platino", False), "PALL": ("etf", "paladio", False),
    "USO": ("DCOILWTICO", "petróleo (WTI)", True), "BNO": ("DCOILWTICO", "petróleo (referencia WTI)", True),
    "UNG": ("DHHNGSP", "gas natural", True), "CPER": ("PCOPPUSDM", "cobre", True),
    "DBC": ("PALLFNFINDEXM", "índice global de materias primas", True), "USCI": ("PALLFNFINDEXM", "índice global de materias primas", True),
    "DBA": ("PFOODINDEXM", "índice global de alimentos", True), "WEAT": ("PFOODINDEXM", "índice global de alimentos", True),
    "CORN": ("PFOODINDEXM", "índice global de alimentos", True),
}
EQ = {"SPY": ("top500", "500 mayores empresas"), "VOO": ("top500", "500 mayores empresas"), "IVV": ("top500", "500 mayores empresas"),
      "VTI": ("top500", "500 mayores empresas"), "QQQ": ("nasdaq", "100 mayores empresas del Nasdaq"),
      "IWM": ("small", "empresas pequeñas (puestos 1.001 a 3.000 por tamaño)")}


def load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def f2(x, n=2):
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(vals, x):
    return 100.0 * sum(1 for v in vals if v <= x) / len(vals)


def fred(sid, since="2000-01-01"):
    txt = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={since}", timeout=60)
    out = []
    for r in list(csv.reader(io.StringIO(txt)))[1:]:
        try:
            out.append((r[0], float(r[1])))
        except (ValueError, IndexError):
            pass
    return out


def tone(v):
    return "ok" if v == "COMPRAR" else "warn" if v == "ESPERAR" else "bad"


def bond(t, F):
    sid, desc, kind, long_ = BONDS[t]
    s = F(sid)
    cut = (date.today() - timedelta(days=3650)).isoformat()
    w = [v for d, v in s if d >= cut]
    if len(w) < 500:
        raise ValueError("pocos datos")
    now, avg, p = s[-1][1], mean(w), pct(w, s[-1][1])
    v = "COMPRAR" if p >= 75 else ("CARO" if p <= (30 if kind == "yield" else 25) else "ESPERAR")
    label = "Rendimiento" if kind == "yield" else "Diferencial sobre el Tesoro"
    pts = [{"t": tone(v), "x": f"{label} actual: {f2(now)} %. Media de los últimos 10 años: {f2(avg)} %. Hoy está más alto que el {p:.0f} % de los días de esa década."}]
    if kind == "spread":
        pts.append({"t": "warn", "x": "El diferencial es el extra que pagan estos bonos sobre el Tesoro. Cuanto más alto, más barato está el bono, pero también más riesgo ven los inversores."})
    elif sid != "DFII10":
        real = F("DFII10")[-1][1]
        pts.append({"t": "ok" if real >= 1.5 else "warn" if real >= .5 else "bad", "x": f"Descontando la inflación esperada, el Tesoro a 10 años rinde un {f2(real)} % real."})
    if long_:
        pts.append({"t": "warn", "x": "Si los tipos de interés suben, el precio de este fondo baja, y más cuanto más largo es el plazo."})
    return {"verdict": v, "rank": round(25 + (p - 75) * .4, 1) if v == "COMPRAR" else 0, "method": "Bonos: se compara su rentabilidad actual con la de los últimos 10 años",
            "summary": f"{desc[0].upper() + desc[1:]}: {label.lower()} del {f2(now)} %, en el percentil {p:.0f} de la última década.",
            "points": pts, "metrics": [{"k": label + " hoy", "v": f"{f2(now)} %"}, {"k": "Media 10 años", "v": f"{f2(avg)} %"}, {"k": "Percentil (10 años)", "v": f"{p:.0f} de 100"}],
            "source": SRC}


def commodity(t, F, cpi):
    src, desc, fut = COMMS[t]
    if src == "etf":
        series = [(d, v) for d, v in json.loads((HIST / f"{t}.json").read_text(encoding="utf-8"))]
    else:
        series = F(src)
    series = [(d, v) for d, v in series if v > 0]
    if len(series) < 60:
        raise ValueError("pocos datos")
    cd, cv = [d for d, _ in cpi], [x for _, x in cpi]
    real = [v * cv[-1] / cv[max(bisect.bisect_right(cd, d[:10]) - 1, 0)] for d, v in series]
    now, med = real[-1], median(real)
    p, ratio = pct(real, now), now / median(real)
    years = (date.fromisoformat(series[-1][0][:10]) - date.fromisoformat(series[0][0][:10])).days / 365
    v = "COMPRAR" if p <= 25 else ("CARO" if p >= 75 else "ESPERAR")
    pts = [{"t": tone(v), "x": f"Su precio, ajustado a la inflación, está en el percentil {p:.0f} de los últimos {years:.0f} años (0 = el más barato)."},
           {"t": "warn", "x": f"Es un {abs(ratio - 1) * 100:.0f} % {'superior' if ratio > 1 else 'inferior'} a su mediana histórica ajustada a inflación."},
           {"t": "warn", "x": "Las materias primas no generan beneficios: este análisis mide si el precio es alto o bajo frente a su historia, no un valor basado en flujos de caja. Un precio bajo puede seguir bajando."}]
    if fut:
        pts.append({"t": "warn", "x": "El fondo invierte en contratos de futuros y puede rendir distinto del precio de referencia por el coste de renovarlos."})
    return {"verdict": v, "rank": round(25 + (25 - p) * .4, 1) if v == "COMPRAR" else 0,
            "method": "Materias primas: precio ajustado a inflación frente a su propia historia",
            "summary": f"Precio real del {desc} en el percentil {p:.0f} de su historia ({years:.0f} años).",
            "points": pts, "metrics": [{"k": "Precio real vs. mediana", "v": f"{(ratio - 1) * 100:+.0f} %"}, {"k": "Percentil", "v": f"{p:.0f} de 100"}, {"k": "Años analizados", "v": f"{years:.0f}"}],
            "source": SRC}


def universe(market, vals, ex):
    rows = {}
    for t, v in vals["items"].items():
        m = market.get(t)
        if not m or not v.get("sh") or v.get("kind") or v.get("type", "ACCIONES") != "ACCIONES":
            continue
        nums = [v[k] for k in ("dcf", "graham", "multiples") if isinstance(v.get(k), (int, float)) and v[k] > 0]
        if len(nums) < 2:
            continue
        iv, pr = mean(nums), m["c"]
        r = {"t": t, "cap": pr * v["sh"], "ratio": iv / pr, "ex": ex.get(t.replace(".", "-"), ""), "dv": pr * m["v"],
             "mg": (iv - pr) / iv * 100, "health": v.get("health")}
        k = v.get("name") or t
        if k not in rows or r["dv"] > rows[k]["dv"]:
            rows[k] = r
    return sorted(rows.values(), key=lambda x: -x["cap"])


def equity(group, label):
    if len(group) < 50:
        raise ValueError("pocas empresas valoradas")
    R = sum(g["cap"] * min(g["ratio"], 3) for g in group) / sum(g["cap"] for g in group)
    mg = (R - 1) / R * 100
    v = "COMPRAR" if mg >= 15 else ("ESPERAR" if mg >= 0 else "CARO")
    buy = 100 * sum(1 for g in group if verdict(g["mg"], g["health"]) == "COMPRAR") / len(group)
    cheap = 100 * sum(1 for g in group if g["mg"] > 0) / len(group)
    pts = [{"t": tone(v), "x": f"Las {len(group)} {label}, ponderadas por tamaño, cotizan un {abs(mg):.0f} % {'por debajo' if mg >= 0 else 'por encima'} de su valor intrínseco."},
           {"t": "ok" if buy >= 15 else "warn", "x": f"El {buy:.0f} % de ellas sale como COMPRAR y el {cheap:.0f} % cotiza por debajo de su valor."},
           {"t": "warn", "x": "Se calcula con nuestro propio universo de empresas valorables: no incluye bancos ni aseguradoras (necesitan otro método) y no usa la lista oficial del índice."}]
    return {"verdict": v, "rank": round(25 + min(mg, 30) / 3, 1) if v == "COMPRAR" else 0,
            "method": "Índice: valor intrínseco agregado de sus mayores empresas valoradas",
            "summary": f"Sus mayores empresas cotizan un {abs(mg):.0f} % {'por debajo' if mg >= 0 else 'por encima'} de su valor intrínseco agregado.",
            "points": pts, "metrics": [{"k": "Margen agregado", "v": f"{f2(mg, 1)} %"}, {"k": "Empresas en COMPRAR", "v": f"{buy:.0f} %"}, {"k": "Empresas analizadas", "v": str(len(group))}],
            "source": "Datos: SEC (cuentas oficiales) y precios de mercado. Información, no asesoramiento financiero."}


def main():
    mp, vp, sp = DATA / "market-data.json", DATA / "valuations.json", DATA / "signals.json"
    market, vals = load(mp, {}), load(vp, {"items": {}})
    cache = {}

    def F(sid, since="2000-01-01"):
        if (sid, since) not in cache:
            cache[(sid, since)] = fred(sid, since)
        return cache[(sid, since)]
    out = {}
    for t in BONDS:
        if t in market:
            try:
                out[t] = bond(t, F)
            except Exception as e:
                print(f"{t}: sin valorar ({e})")
    try:
        cpi = F("CPIAUCSL", "1995-01-01")
        for t in COMMS:
            if t in market:
                try:
                    out[t] = commodity(t, F, cpi)
                except Exception as e:
                    print(f"{t}: sin valorar ({e})")
    except Exception as e:
        print(f"Inflación (IPC) no disponible: {e}")
    try:
        ex = {r[2].upper(): r[3] for r in json.loads(get("https://www.sec.gov/files/company_tickers_exchange.json", {"User-Agent": SEC_UA}))["data"]}
        uni = universe(market, vals, ex)
        groups = {"top500": uni[:500], "nasdaq": [g for g in uni if g["ex"] == "Nasdaq"][:100], "small": uni[1000:3000]}
        for t, (g, label) in EQ.items():
            if t in market:
                try:
                    out[t] = equity(groups[g], label)
                except Exception as e:
                    print(f"{t}: sin valorar ({e})")
    except Exception as e:
        print(f"Índices: no se pudo calcular ({e})")
    if not out:
        print("No se valoró ningún activo.")
        return
    for t, a in out.items():
        vals["items"].setdefault(t, {"type": market[t].get("type", "ETFS")})["assess"] = a
    vp.write_text(json.dumps(vals, ensure_ascii=False), encoding="utf-8")
    sig = load(sp, [])
    recent = {s["ticker"] for s in sig if s["date"] >= (date.today() - timedelta(days=90)).isoformat()}
    spy, new = market.get("SPY", {}).get("c"), []
    buys = sorted([(a["rank"], t, a) for t, a in out.items() if a["verdict"] == "COMPRAR"], reverse=True)
    for _, t, a in buys:
        if t not in recent:
            row = {"date": TODAY, "ticker": t, "verdict": "COMPRAR", "price": market[t]["c"]}
            if spy:
                row["spy"] = spy
            sig.append(row)
            new.append(t)
    sp.write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Listo: {len(out)} activos valorados, {len(buys)} en COMPRAR.")
    if buys:
        lines = [f"Bonos, índices y materias primas · {TODAY}", ""]
        for _, t, a in buys:
            lines.append(f"{t}{' (nuevo)' if t in new else ''}: {a['summary']}")
        lines += ["", "Información, no asesoramiento financiero."]
        telegram("\n".join(lines))


if __name__ == "__main__":
    main()
