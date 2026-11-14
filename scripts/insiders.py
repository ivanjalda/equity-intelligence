#!/usr/bin/env python3
"""Equity Intelligence: compras y ventas de directivos (formulario 4 de la SEC).
Lee el índice diario de EDGAR, descarga cada formulario 4 y guarda en data/insiders.json las
compras y ventas en mercado abierto (códigos P y S) de al menos 50.000 $. Conserva 45 días."""
import json, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import xml.etree.ElementTree as ET
from engine import get, DATA, SEC_UA

H = {"User-Agent": SEC_UA}
MIN_USD = 50000
KEEP_DAYS = 45
BACK_DAYS = 8           # en la primera vuelta mira los últimos días hábiles
MAX_PER_RUN = 30000
BUDGET = 55 * 60        # segundos: pasado este tiempo se guarda lo leído y se sigue en la próxima ejecución
OUT = DATA / "insiders.json"


_lock = threading.Lock()
_next = [0.0]


def sec(url):
    """Pide a la SEC como máximo ~8 veces por segundo en total (el límite es 10)."""
    with _lock:
        t = max(time.time(), _next[0])
        _next[0] = t + 0.125
    time.sleep(max(0, t - time.time()))
    return get(url, H, 60)


def quarter(d):
    return f"{d.year}/QTR{(d.month - 1) // 3 + 1}"


def day_filings(d):
    """Devuelve {accesión: ruta} de los formularios 4 presentados ese día (índice diario)."""
    url = f"https://www.sec.gov/Archives/edgar/daily-index/{quarter(d)}/form.{d.strftime('%Y%m%d')}.idx"
    try:
        txt = sec(url)
    except Exception as e:
        print(f"  {d}: sin índice ({e}).")
        return {}
    out = {}
    for line in txt.splitlines():
        if not line.startswith("4 ") and not line.startswith("4/A"):
            continue
        m = re.search(r"(edgar/data/\d+/(\d{10}-\d{2}-\d{6})\.txt)\s*$", line)
        if m and line.startswith("4 "):
            out[m.group(2)] = m.group(1)
    return out


def txt_of(node, path):
    el = node.find(path)
    return (el.text or "").strip() if el is not None and el.text else ""


def parse(raw):
    """Extrae las operaciones P/S de un formulario 4. Devuelve lista de dicts."""
    m = re.search(r"<ownershipDocument>.*?</ownershipDocument>", raw, re.S)
    if not m:
        return []
    root = ET.fromstring(m.group(0))
    tick = txt_of(root, "issuer/issuerTradingSymbol").upper()
    name = txt_of(root, "issuer/issuerName")
    owners = root.findall("reportingOwner")
    who = txt_of(owners[0], "reportingOwnerId/rptOwnerName") if owners else ""
    rel = owners[0].find("reportingOwnerRelationship") if owners else None
    role = ""
    if rel is not None:
        if txt_of(rel, "officerTitle"):
            role = txt_of(rel, "officerTitle")
        elif txt_of(rel, "isDirector") in ("1", "true"):
            role = "Consejero"
        elif txt_of(rel, "isTenPercentOwner") in ("1", "true"):
            role = "Accionista >10 %"
    res = []
    for tr in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = txt_of(tr, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        try:
            sh = float(txt_of(tr, "transactionAmounts/transactionShares/value"))
            px = float(txt_of(tr, "transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        if px <= 0 or sh <= 0 or sh * px < MIN_USD or not tick:
            continue
        res.append({"t": tick, "n": name, "w": who.title() if who.isupper() else who, "r": role, "k": code,
                    "d": txt_of(tr, "transactionDate/value")[:10], "sh": round(sh), "px": round(px, 2), "v": round(sh * px)})
    return res


def main():
    old = {"items": [], "seen": []}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass
    seen = set(old.get("seen", []))
    items = list(old.get("items", []))
    today = date.today()
    t0 = time.time()
    days = []
    d = today
    while len(days) < BACK_DAYS:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    nuevos = fallos = 0
    todo = []
    for d in sorted(days, reverse=True):          # primero lo más reciente
        fl = day_filings(d)
        pend = [(a, p) for a, p in fl.items() if a not in seen]
        print(f"{d}: {len(fl)} formularios 4, {len(pend)} nuevos.", flush=True)
        todo.extend(pend)

    def work(ap):
        acc, path = ap
        if time.time() - t0 > BUDGET:
            return None
        try:
            return acc, parse(sec("https://www.sec.gov/Archives/" + path))
        except Exception:
            return acc, False

    with ThreadPoolExecutor(8) as ex:
        for r in ex.map(work, todo[:MAX_PER_RUN]):
            if r is None:
                continue
            acc, res = r
            if res is False:
                fallos += 1
                continue
            items.extend(res)
            seen.add(acc)
            nuevos += 1
            if nuevos % 1000 == 0:
                print(f"  {nuevos} leídos, {len(items)} operaciones...", flush=True)
    if len(todo) > nuevos + fallos:
        print(f"Quedan {len(todo) - nuevos - fallos} por leer; se harán en la próxima ejecución.", flush=True)
    limite = (today - timedelta(days=KEEP_DAYS)).isoformat()
    items = [x for x in items if x["d"] >= limite]
    uniq = {(x["t"], x["w"], x["d"], x["k"], x["sh"], x["px"]): x for x in items}
    items = sorted(uniq.values(), key=lambda x: (x["d"], x["v"]), reverse=True)
    keep_seen = sorted(seen)[-20000:]
    if not items and not old.get("items") and nuevos == 0:
        print("No se pudo leer ningún formulario. No se guarda nada.")
        sys.exit(0)
    DATA.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"updated": today.isoformat(), "items": items, "seen": keep_seen}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Listo: {nuevos} formularios leídos ({fallos} con error), {len(items)} operaciones guardadas.")


if __name__ == "__main__":
    main()
