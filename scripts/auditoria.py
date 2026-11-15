# -*- coding: utf-8 -*-
"""Revisión automática de Equity Intelligence.
Vuelve a calcular y comprueba los datos publicados: fórmulas, coherencia de las cuentas, frescura de los datos y rangos
razonables. Escribe data/auditoria.json (la web muestra el resultado) y termina con error si algo no cuadra,
para que GitHub avise por correo."""
import json, re, sys, math
from datetime import date, datetime
from pathlib import Path
from statistics import mean

DATA = Path("data")
TERMINAL, YIELD_AAA = 0.025, 5.0
fallos, avisos, total = [], [], 0


def check(ok, msg, grave=True):
    global total
    total += 1
    if not ok:
        (fallos if grave else avisos).append(msg)


def dcf(fcfps, g, r):
    v, f = 0.0, fcfps
    for y in range(1, 11):
        f *= 1 + (g if y <= 5 else g / 2)
        v += f / (1 + r) ** y
    return v + f * (1 + TERMINAL) / (r - TERMINAL) / (1 + r) ** 10


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception as e:
        return None


def close(a, b, tol):
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)


def autotest():
    """Números conocidos: si el código de las fórmulas cambia por error, esto lo detecta."""
    check(close(2.10 * 8.5 * 4.4 / YIELD_AAA, 15.708, 0.001), "Fórmula de Graham: resultado inesperado en el caso de prueba")
    check(close(dcf(1.0, 0.0, 0.10), 8.6, 0.30) and dcf(1.0, 0.0, 0.10) < dcf(1.0, 0.05, 0.10) and dcf(1.0, 0.05, 0.12) < dcf(1.0, 0.05, 0.10),
          "DCF: no se comporta como debe (más crecimiento = más valor; más tasa = menos valor)")



def fecha(x):
    try:
        return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def web_completa(today):
    """Todo lo demás de la web: páginas, enlaces, datos de cada sección y frescura."""
    root = Path(".")
    # 1) páginas obligatorias y enlaces internos
    paginas = ["index.html", "aprender.html", "como-funciona.html", "privacidad.html", "cookies.html", "aviso-legal.html", "riesgo.html"]
    ids = {}
    for pg in paginas:
        f = root / pg
        check(f.exists() and f.stat().st_size > 2000, f"Falta la página {pg} o está vacía")
        if f.exists():
            ids[pg] = set(re.findall(r'\bid="([^"]+)"', f.read_text(encoding="utf-8")))
    for pg in paginas:
        f = root / pg
        if not f.exists():
            continue
        h = f.read_text(encoding="utf-8")
        for href in set(re.findall(r'(?:href|src)="([^"#:?]+)?(#[^"]*)?"', h)):
            dest, anc = href
            if any(c in (dest or '') + (anc or '') for c in "${}'+"):
                continue   # enlace construido por el código al ejecutarse
            if dest and not dest.startswith(("http", "mailto", "javascript", "data")):
                check((root / dest).exists(), f"{pg}: enlace o archivo que no existe: {dest}")
            if anc and len(anc) > 1:
                objetivo = dest or pg
                if objetivo in ids:
                    check(anc[1:] in ids[objetivo], f"{pg}: el enlace {objetivo}{anc} apunta a un apartado que no existe")
        check("temaActual" in h and "tema.js" in h, f"{pg}: falta el selector de tema") if pg == "index.html" else None
        if pg != "index.html":
            check("Información, no asesoramiento" in h or "no es asesoramiento" in h.lower() or "asesoramiento" in h.lower(), f"{pg}: falta el aviso legal de no asesoramiento", grave=False)
    # el código de la ficha enlaza a apartados de Aprender: todos deben existir
    idx = (root / "index.html").read_text(encoding="utf-8") if (root / "index.html").exists() else ""
    for a in set(re.findall(r'aprender\.html#([A-Za-z0-9_-]+)', idx)):
        if a.endswith("-"):
            continue   # parte construida por el código
        check(a in ids.get("aprender.html", set()), f"index.html enlaza a aprender.html#{a}, que no existe")
    # 2) cada archivo de datos se lee y está al día
    for nombre, campo, max_dias in (("news.json", "updated", 3), ("13f.json", "updated", 120), ("insiders.json", "updated", 6),
                                      ("market-data.json", None, None), ("signals.json", None, None), ("models.json", "updated", 10)):
        d = load(DATA / nombre)
        check(d is not None, f"No se puede leer data/{nombre}")
        if d is not None and campo:
            fd = fecha(d.get(campo))
            check(fd is not None, f"data/{nombre}: fecha ilegible")
            if fd and max_dias:
                check((today - fd).days <= max_dias, f"data/{nombre} tiene {(today - fd).days} días de antigüedad (máximo {max_dias})", grave=(nombre != "13f.json"))
    N = load(DATA / "news.json") or {}
    for it in N.get("items", [])[:60]:
        check(str(it.get("u", "")).startswith("https://") and it.get("t") and it.get("s"), f"Noticia sin enlace https, título o medio: {str(it.get('t'))[:50]}", grave=False)
    F = load(DATA / "13f.json") or {}
    for m in F.get("managers", []):
        check(m.get("value", 0) > 0 and m.get("positions"), f"13F de {m.get('name')}: sin valor o sin posiciones", grave=False)
    M = load(DATA / "market-data.json") or {}
    check(len(M) > 100, f"market-data.json tiene muy pocos valores ({len(M)})")
    malos = [t for t, x in M.items() if not isinstance(x, dict) or not (x.get("c") or 0) > 0]
    check(len(malos) <= 0.02 * max(len(M), 1), f"{len(malos)} valores sin precio válido en market-data.json: {malos[:5]}")
    # 3) históricos de precios de las acciones valoradas del motor diario
    V = load(DATA / "valuations.json") or {"items": {}}
    sin_hist, viejos = [], []
    for t, it in V["items"].items():
        if it.get("type", "ACCIONES") != "ACCIONES" or not (it.get("dcf") or it.get("graham")):
            continue
        h = load(DATA / "history" / f"{t}.json")
        if h is None:
            if t in M:
                sin_hist.append(t)
            continue
        if h:
            fd = fecha(h[-1][0])
            if fd and (today - fd).days > 12:
                viejos.append(t)
            check(all(isinstance(r[1], (int, float)) and r[1] > 0 for r in h[-30:]), f"{t}: histórico con precios no válidos")
    check(len(viejos) <= 5, f"{len(viejos)} históricos de precios con más de 12 días sin actualizar: {viejos[:5]}", grave=False)
    check(len(sin_hist) <= 0.5 * max(len(V['items']), 1), f"Faltan históricos de precios de {len(sin_hist)} acciones", grave=False)
    # 4) una acción valorada debe tener precio actual
    sin_precio = [t for t, it in V["items"].items() if (it.get("dcf") or it.get("graham")) and t not in M]
    check(len(sin_precio) <= 0.05 * max(len(V["items"]), 1), f"{len(sin_precio)} acciones valoradas sin precio actual: {sin_precio[:5]}", grave=False)


def main():
    autotest()
    today = date.today()
    V = load(DATA / "valuations.json")
    M = load(DATA / "market-data.json") or {}
    check(bool(V and V.get("items")), "No se pudo leer valuations.json")
    if V:
        upd = datetime.strptime(V["updated"], "%Y-%m-%d").date()
        edad = (today - upd).days
        check(edad <= 5, f"Las valoraciones tienen {edad} días de antigüedad (máximo 5)")
        n_items = 0
        for t, it in V["items"].items():
            if it.get("type", "ACCIONES") != "ACCIONES":
                continue
            ms = [it[k] for k in ("dcf", "graham", "multiples") if isinstance(it.get(k), (int, float))]
            if len(ms) < 2:
                continue
            n_items += 1
            iv = mean(ms)
            check(all(x > 0 for x in ms), f"{t}: algún método de valoración es cero o negativo")
            check(max(ms) <= 3 * min(ms) + 1e-6, f"{t}: los métodos difieren más de 3 veces y no se descartó ninguno")
            r, g, b = it.get("r"), it.get("g"), it.get("beta")
            if r is not None:
                check(0.07 <= r <= 0.13, f"{t}: tasa de descuento fuera de rango ({r})")
            if g is not None:
                check(0 <= g <= 0.15, f"{t}: crecimiento fuera de rango ({g})")
            if b is not None:
                check(0.5 <= b <= 1.8, f"{t}: beta fuera de rango ({b})")
            if it.get("dcf") and it.get("fcfps") and g is not None and r:
                check(close(dcf(it["fcfps"], g, r), it["dcf"], 0.01), f"{t}: el DCF publicado no coincide con el recalculado ({it['dcf']} frente a {dcf(it['fcfps'], g, r):.2f})")
            if not it.get("cyclical") and it.get("graham") and it.get("eps") and g is not None and it["eps"] > 0:
                check(close(it["eps"] * (8.5 + 2 * g * 100) * 4.4 / YIELD_AAA, it["graham"], 0.01), f"{t}: Graham publicado no coincide con el recalculado")
            e = it.get("esc")
            if e:
                check(len(e) == 3 and e[0] <= e[1] + 0.01 <= e[2] + 0.02, f"{t}: escenarios desordenados {e}")
                check(close(e[1], iv, 0.03), f"{t}: el escenario base ({e[1]}) no coincide con el valor intrínseco ({iv:.2f})")
            p = (M.get(t) or {}).get("c")
            if p:
                check(p > 0 and iv / p < 20 and p / iv < 20, f"{t}: precio ({p}) y valor ({iv:.2f}) difieren más de 20 veces: dato sospechoso", grave=False)
        check(n_items > 20, f"Muy pocas acciones valoradas ({n_items})")

    # cuentas oficiales
    nf = 0
    for f in sorted((DATA / "fundamentals").glob("*.json")):
        d = load(f)
        st = d and d.get("st")
        if not st:
            continue
        nf += 1
        t = f.stem
        y, e = st.get("y", []), st.get("e", [])
        check(len(y) == len(e) and len(y) >= 3, f"{t}: años de las cuentas incoherentes")
        if e:
            try:
                meses = (today - datetime.strptime(e[-1], "%Y-%m-%d").date()).days / 30
                check(meses <= 20, f"{t}: las últimas cuentas son de hace {meses:.0f} meses", grave=False)
            except ValueError:
                check(False, f"{t}: fecha de cuentas ilegible")
        src = st.get("src")
        if src and e:
            check(src.get("end") == e[-1], f"{t}: el informe enlazado (ejercicio {src.get('end')}) no es el último de la tabla ({e[-1]})")
        n = len(y)
        B, I = st.get("bs", {}), st.get("is", {})
        at, pt, eq = B.get("Activos totales"), B.get("Pasivos totales"), B.get("Patrimonio total") or B.get("Patrimonio neto")
        if at and pt and eq and not B.get("Intereses minoritarios") and not B.get("Patrimonio total"):
            for i in range(n):
                if None not in (at[i], pt[i], eq[i]) and at[i] > 0:
                    check(close(at[i], pt[i] + eq[i], 0.03), f"{t} {y[i]}: activos ({at[i]}) ≠ pasivos + patrimonio ({pt[i] + eq[i]:.0f})", grave=False)
        ing, cv, bb = I.get("Ingresos"), I.get("Coste de ventas"), I.get("Beneficio bruto")
        if ing and cv and bb:
            for i in range(n):
                if None not in (ing[i], cv[i], bb[i]) and ing[i] > 0:
                    check(close(ing[i] - cv[i], bb[i], 0.02), f"{t} {y[i]}: ingresos − coste ≠ beneficio bruto", grave=False)
    check(nf > 0, "No hay cuentas oficiales publicadas")

    # directivos
    ins = load(DATA / "insiders.json")
    if ins and ins.get("items"):
        check(ins.get("ver") == 2, "insiders.json tiene un formato antiguo")
        raros = [x for x in ins["items"] if x.get("px", 0) > 20000 and not str(x.get("t", "")).startswith("BRK")]
        check(len(raros) <= 0.02 * len(ins["items"]), f"Demasiadas operaciones de directivos con precio absurdo ({len(raros)})", grave=False)

    web_completa(today)
    res = {"fecha": today.isoformat(), "ok": not fallos, "comprobaciones": total, "fallos": fallos[:50], "avisos": avisos[:50],
           "n_fallos": len(fallos), "n_avisos": len(avisos)}
    (DATA / "auditoria.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print(f"Revisión: {total} comprobaciones, {len(fallos)} fallos, {len(avisos)} avisos.")
    for m in fallos[:40]:
        print("FALLO:", m)
    for m in avisos[:15]:
        print("aviso:", m)
    return 0 if not fallos else 1


if __name__ == "__main__":
    sys.exit(main())
