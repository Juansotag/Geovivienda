import os
import requests
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE_DIR, "geodata", "cali", "estaciones_mio.geojson")

query = """
[out:json][timeout:25];
(
  node["network"~"MIO"]["public_transport"="station"](3.28, -76.60, 3.55, -76.45);
  way["network"~"MIO"]["public_transport"="station"](3.28, -76.60, 3.55, -76.45);
  relation["network"~"MIO"]["public_transport"="station"](3.28, -76.60, 3.55, -76.45);
);
out center;
"""

def fetch_mio_stations():
    print("Descargando estaciones del MIO desde Overpass API (Bounding Box Cali)...")
    url = "https://lz4.overpass-api.de/api/interpreter"
    response = requests.post(url, data={"data": query}, timeout=30)
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        return

    data = response.json()
    features = []
    
    for el in data.get("elements", []):
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not lat or not lon:
            continue
            
        tags = el.get("tags", {})
        nombre = tags.get("name", "Estación MIO")
        
        feature = {
            "type": "Feature",
            "properties": {
                "nombre": nombre,
                "tipo": "MIO"
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            }
        }
        features.append(feature)
        
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
        
    print(f"Descargadas {len(features)} estaciones del MIO en {OUTPUT_FILE}")
    
    # Copiar a static/geo/cali para la API
    static_dir = os.path.join(BASE_DIR, "static", "geo", "cali")
    os.makedirs(static_dir, exist_ok=True)
    static_file = os.path.join(static_dir, "estaciones_mio.geojson")
    with open(static_file, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    print(f"Copiado a {static_file}")

if __name__ == "__main__":
    fetch_mio_stations()
