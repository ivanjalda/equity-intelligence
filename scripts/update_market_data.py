```python
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TICKERS = ["MSFT", "AAPL", "NVDA", "AMZN", "KO", "JNJ"]

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "market-data.json"


def fetch_json(url):
    request = Request(
        url,
        headers={"User-Agent": "EquityIntelligence/1.0"}
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(
            f"Error HTTP {exc.code} al consultar Polygon."
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            "No se pudo conectar con Polygon."
        ) from exc


def main():
    api_key = os.environ.get("POLYGON_KEY")

    if not api_key:
        sys.exit(
            "ERROR: falta el secreto POLYGON_KEY en GitHub."
        )

    today = datetime.now(timezone.utc).date()
    results = {}

    for ticker in TICKERS:
        # Se consulta la última sesión disponible de los últimos
        # diez días naturales para cubrir fines de semana y festivos.
        from_date = today.fromordinal(today.toordinal() - 10)

        params = urlencode({
            "adjusted": "true",
            "sort": "desc",
            "limit": 1,
            "apiKey": api_key,
        })

        url = (
            "https://api.polygon.io/v2/aggs/ticker/"
            f"{ticker}/range/1/day/"
            f"{from_date.isoformat()}/{today.isoformat()}?"
            f"{params}"
        )

        payload = fetch_json(url)
        rows = payload.get("results") or []

        if not rows:
            print(f"AVISO: Polygon no devolvió datos para {ticker}.")
            results[ticker] = {
                "ticker": ticker,
                "status": "no_data",
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }
            continue

        bar = rows[0]

        results[ticker] = {
            "ticker": ticker,
            "date": datetime.fromtimestamp(
                bar["t"] / 1000, timezone.utc
            ).date().isoformat(),
            "open": bar.get("o"),
            "high": bar.get("h"),
            "low": bar.get("l"),
            "close": bar.get("c"),
            "volume": bar.get("v"),
            "status": "ok",
        }

        print(f"OK: {ticker} actualizado.")
        time.sleep(0.15)

    if not any(item["status"] == "ok" for item in results.values()):
        sys.exit("ERROR: no se obtuvieron datos válidos.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    document = {
        "provider": "Polygon",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "market_data": results,
    }

    OUTPUT.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Archivo generado correctamente: {OUTPUT}")


if __name__ == "__main__":
    main()
```
