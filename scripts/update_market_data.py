import os
import json
import requests

def fetch_market_data():
    api_key = os.environ.get("POLYGON_KEY")
    if not api_key:
        raise ValueError("No se ha encontrado la clave POLYGON_KEY en los secretos.")

    # Lista de símbolos de ejemplo que puedes adaptar o ampliar
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    market_data = {}

    for ticker in symbols:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={api_key}"
        response = requests.get(url)
        
        if response.status_code != 200:
            raise Exception(f"Error al conectar con Polygon para {ticker}: {response.status_code}")
            
        data = response.json()
        
        if "results" not in data or not data["results"]:
            raise ValueError(f"Polygon no ha devuelto datos válidos para el ticker {ticker}: {data}")
            
        market_data[ticker] = data["results"][0]

    # Crear la carpeta data si no existe
    os.makedirs("data", exist_ok=True)
    
    file_path = "data/market-data.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(market_data, f, indent=4)
        
    print(f"Datos guardados correctamente en {file_path}")

if __name__ == "__main__":
    fetch_market_data()
