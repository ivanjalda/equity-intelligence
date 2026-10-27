import os
import json
import time
import requests

# 1. Obtener la API key almacenada en los Secrets de GitHub
API_KEY = os.environ.get("POLYGON_KEY")

if not API_KEY:
    raise ValueError("La variable POLYGON_KEY no está configurada en los Secrets.")

# 2. Lista completa de activos
TICKERS = [
    # Grandes empresas (Acciones)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "BRK.B", "JNJ", "V", "MA", "KO", "PEP", "PG", "COST", "UNH",
    
    # Índices Bursátiles (ETFs)
    "SPY", "QQQ", "DIA", "IWM",
    
    # Materias Primas
    "GLD", "SLV", "USO", "DBC",
    
    # Bonos y Renta Fija
    "TLT", "IEF", "SHY"
]

market_data = {}

print(f"Descargando datos oficiales de cierre para {len(TICKERS)} activos (con pausa para respetar el plan gratuito)...")

for ticker in TICKERS:
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("status") == "OK" and data.get("resultsCount", 0) > 0:
            res = data["results"][0]
            market_data[ticker] = {
                "c": res.get("c"),  # Precio Cierre
                "o": res.get("o"),  # Precio Apertura
                "h": res.get("h"),  # Máximo
                "l": res.get("l"),  # Mínimo
                "v": res.get("v"),  # Volumen
                "t": res.get("t")   # Timestamp Unix
            }
            print(f"✔ {ticker}: Cierre ${res.get('c')}")
        else:
            print(f"⚠ No se obtuvieron datos para {ticker} (Respuesta: {data.get('status')})")
    except Exception as e:
        print(f"❌ Error al consultar {ticker}: {e}")
    
    # Pausa de 12 segundos entre peticiones para cumplir estrictamente
    # el límite gratuito de Polygon (máx 5 peticiones por minuto)
    time.sleep(12)

# 3. Guardar el resultado en la carpeta data/market-data.json
os.makedirs("data", exist_ok=True)
with open("data/market-data.json", "w", encoding="utf-8") as f:
    json.dump(market_data, f, indent=2)

print("¡Archivo data/market-data.json actualizado con éxito!")
