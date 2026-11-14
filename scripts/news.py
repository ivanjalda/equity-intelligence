#!/usr/bin/env python3
"""Noticias de mercado: lee los titulares públicos (RSS) de noticias-fuentes.txt y guarda data/news.json.
Solo guarda titular, fuente, fecha y enlace. No copia artículos ni imágenes. Solo librería estándar."""
import json, re, html, sys, os, urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "news.json"
UA = os.environ.get("SEC_USER_AGENT", "EquityIntelligence community16jalda@gmail.com")
NOW = datetime.now(timezone.utc)
MAX_PER_FEED, MAX_AGE_DAYS, MAX_TOTAL = 12, 3, 80


def local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def clean(t):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()[:200]


def read_feed(lang, name, url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
    root = ET.fromstring(urllib.request.urlopen(req, timeout=30).read())
    out = []
    for it in root.iter():
        if local(it.tag) not in ("item", "entry"):
            continue
        f = {}
        img = None
        for ch in it:
            k = local(ch.tag)
            if k == "link":
                f["link"] = ch.get("href") or (ch.text or "").strip()
            elif k in ("title", "pubdate", "updated", "published", "date"):
                f.setdefault(k, ch.text or "")
            if k in ("content", "thumbnail", "enclosure", "image") and not img:
                u, ty = ch.get("url") or "", (ch.get("type") or ch.get("medium") or "").lower()
                if u and (k == "thumbnail" or "image" in ty or re.search(r"\.(jpe?g|png|webp)(\?|$)", u, re.I)):
                    img = u
            if k in ("description", "encoded", "summary", "content") and not img and ch.text:
                m = re.search(r"<img[^>]+src=[\"']([^\"']+)", ch.text, re.I)
                if m:
                    img = html.unescape(m.group(1))
        t, u = clean(f.get("title")), (f.get("link") or "").strip()
        d = parse_date(f.get("pubdate") or f.get("published") or f.get("updated") or f.get("date"))
        if len(t) < 15 or not re.match(r"https?://", u):
            continue
        if d and (NOW - d > timedelta(days=MAX_AGE_DAYS) or d > NOW + timedelta(hours=1)):
            continue
        if img and (not img.startswith("https://") or re.search(r"pixel|1x1|spacer|feedburner|doubleclick", img, re.I)):
            img = None
        out.append({"t": t, "u": u, "s": name, "l": lang, "d": d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None, "i": img})
        if len(out) >= MAX_PER_FEED:
            break
    return out


def main():
    feeds = []
    for line in (ROOT / "noticias-fuentes.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line.count("|") >= 2:
            feeds.append(tuple(x.strip() for x in line.split("|", 2)))
    new, ok, fail = {}, 0, []
    for lang, name, url in feeds:
        try:
            items = read_feed(lang, name, url)
            ok += 1
            print(f"OK   {name}: {len(items)} titulares")
            for x in items:
                new[x["u"]] = x
        except Exception as e:
            fail.append(name)
            print(f"FALLA {name}: {e}")
    if not new:
        print("No se obtuvo ningún titular. No se modifica nada.")
        sys.exit(0)
    old = []
    try:
        old = json.loads(OUT.read_text(encoding="utf-8")).get("items", [])
    except Exception:
        pass
    for x in old:  # conserva titulares recientes de fuentes que hoy no respondieron
        if x["u"] not in new and x.get("s") in fail and x.get("d") and NOW - parse_date(x["d"]) < timedelta(days=MAX_AGE_DAYS):
            new[x["u"]] = x
    items = sorted(new.values(), key=lambda x: x["d"] or "", reverse=True)[:MAX_TOTAL]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items}, ensure_ascii=False), encoding="utf-8")
    print(f"Guardados {len(items)} titulares ({ok} fuentes bien, {len(fail)} con fallo: {', '.join(fail) or 'ninguna'})")


main()
