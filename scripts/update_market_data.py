import os
import json
import time
import requests

API_KEY = os.environ.get("POLYGON_KEY")

if not API_KEY:
    raise ValueError("La variable POLYGON_KEY no está configurada en los Secrets.")

# Catálogo global ampliado: EE.UU., Europa, España, Japón, Alemania, ETFs, Bonos y Commodities
TICKERS = [
    # --- Grandes Tecnológicas y EE.UU. ---
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AMD", "INTC",
    "NKE", "WMT", "DIS", "JNJ", "V", "MA", "KO", "PEP", "PG", "COST", "UNH", "BRK.B",
    
    # --- Índices y ETFs Globales ---
    "SPY", "QQQ", "DIA", "IWM",  # EE.UU.
    "VGK", "EZU",                 # Europa / Eurozone
    "EWJ",                        # Japón
    "EWG",                        # Alemania
    "EWP",                        # España
    
    # --- Materias Primas (Commodities) ---
    "GLD", "SLV", "USO", "UNG", "DBC",
    
    # --- Bonos / Renta Fija ---
    "TLT", "IEF", "SHY", "BND"
]

market_data = {}

print(f"Descargando datos oficiales de cierre para {len(TICKERS)} activos globales...")

for ticker in TICKERS:
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("status") == "OK" and data.get("resultsCount", 0) > 0:
            res = data["results"][0]
            market_data[ticker] = {
                "c": res.get("c"),  # Cierre
                "o": res.get("o"),  # Apertura
                "h": res.get("h"),  # Máximo
                "l": res.get("l"),  # Mínimo
                "v": res.get("v"),  # Volumen
                "t": res.get("t")   # Timestamp
            }
            print(f"✔ {ticker}: Cierre ${res.get('c')}")
        else:
            print(f"⚠ Sin datos para {ticker}")
    except Exception as e:
        print(f"❌ Error en {ticker}: {e}")
    
    # Pausa de 12 segundos para respetar el límite del plan gratuito de Polygon
    time.sleep(12)

os.makedirs("data", exist_ok=True)
with open("data/market-data.json", "w", encoding="utf-8") as f:
    json.dump(market_data, f, indent=2)

print("¡Archivo data/market-data.json actualizado con el catálogo global!")
