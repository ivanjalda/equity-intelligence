import os
import json
import requests

# 1. Obtener la API key almacenada en los Secrets de GitHub
API_KEY = os.environ.get("POLYGON_KEY")

if not API_KEY:
    raise ValueError("La variable POLYGON_KEY no está configurada en los Secrets.")

# 2. Lista ampliada de activos representativos del mercado global:
# - Megacaps / Tech: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
# - Valor / Calidad: BRK.B, JNJ, V, MA, KO, PEP, PG, COST, UNH
# - Índices globales (ETFs): SPY (S&P 500), QQQ (Nasdaq 100), DIA (Dow Jones), IWM (Russell 2000)
# - Materias Primas (ETFs): GLD (Oro), SLV (Plata), USO (Petróleo), DBC (Commodities globales)
# - Bonos / Renta Fija (ETFs): TLT (Tesoro EE.UU. 20+ años), IEF (Tesoro EE.UU. 7-10 años), SHY (Tesoro a corto plazo)
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

print(f"Descargando datos oficiales de cierre para {len(TICKERS)} activos...")

for ticker in TICKERS:
    # Consulta a la API oficial de Polygon (End of Day Previous Close)
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
            print(f"⚠ No se obtuvieron datos para {ticker}")
    except Exception as e:
        print(f"❌ Error al consultar {ticker}: {e}")

# 3. Guardar el resultado en la carpeta data/market-data.json
os.makedirs("data", exist_ok=True)
with open("data/market-data.json", "w", encoding="utf-8") as f:
    json.dump(market_data, f, indent=2)

print("¡Archivo data/market-data.json actualizado con éxito!")
