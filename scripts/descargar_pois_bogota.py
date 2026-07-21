import os
import json
import time
import requests

BBOX = "4.4,-74.3,4.9,-73.9"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter"
]

HEADERS = {
    "User-Agent": "GeoviviendaApp/1.0 (contact@geovivienda.local)",
    "Accept": "application/json"
}

def hacer_consulta_overpass(query):
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"Enviando consulta a {endpoint}...")
            response = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=90)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error {response.status_code} desde {endpoint}")
        except Exception as e:
            print(f"Excepción conectando a {endpoint}: {e}")
        time.sleep(2)
    return None

def extraer_coordenada_elemento(elem):
    if elem.get("type") == "node":
        return elem.get("lat"), elem.get("lon")
    elif elem.get("center"):
        return elem["center"].get("lat"), elem["center"].get("lon")
    return None, None

def descargar_y_clasificar_pois():
    query = f"""
    [out:json][timeout:90];
    (
      // Centros Comerciales
      nwr["shop"="mall"]({BBOX});
      
      // Supermercados y Hard Discount
      nwr["shop"="supermarket"]({BBOX});
      nwr["shop"="convenience"]({BBOX});
      nwr["brand"~"D1|Ara|Carulla|Olímpica|Olimpica|Éxito|Exito|Jumbo|Colsubsidio|Metro|Zapatoca", i]({BBOX});
      nwr["name"~"D1|Ara|Carulla|Olímpica|Olimpica|Éxito|Exito|Jumbo|Colsubsidio|Metro|Zapatoca", i]({BBOX});
      
      // Salud
      nwr["amenity"="hospital"]({BBOX});
      nwr["amenity"="clinic"]({BBOX});
      nwr["amenity"="health_post"]({BBOX});
      
      // Educación
      nwr["amenity"="school"]({BBOX});
      nwr["amenity"="college"]({BBOX});
      nwr["amenity"="university"]({BBOX});
    );
    out center tags;
    """
    
    data = hacer_consulta_overpass(query)
    if not data or "elements" not in data:
        print("No se recibieron datos de Overpass API.")
        return

    elementos = data["elements"]
    print(f"Total elementos recibidos de OpenStreetMap: {len(elementos)}")

    features_centros_comerciales = []
    features_supermercados = []
    features_salud = []
    features_educacion = []

    for elem in elementos:
        lat, lon = extraer_coordenada_elemento(elem)
        if not lat or not lon:
            continue
        
        tags = elem.get("tags", {})
        nombre = tags.get("name") or tags.get("brand") or "Sin Nombre"
        shop = tags.get("shop", "")
        amenity = tags.get("amenity", "")
        brand = (tags.get("brand") or "").lower()
        nombre_lower = nombre.lower()

        props = {
            "id": elem.get("id"),
            "nombre": nombre,
            "categoria": "",
            "subcategoria": "",
            "tags": tags
        }

        # Clasificación por categoría
        if shop == "mall" or "centro comercial" in nombre_lower:
            props["categoria"] = "centro_comercial"
            features_centros_comerciales.append({
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [lon, lat]}
            })

        elif shop in ["supermarket", "convenience"] or any(k in nombre_lower or k in brand for k in ["d1", "ara", "carulla", "olimpica", "olímpica", "exito", "éxito", "jumbo", "colsubsidio"]):
            props["categoria"] = "supermercado"
            if "d1" in nombre_lower or "d1" in brand:
                props["subcategoria"] = "hard_discount_d1"
            elif "ara" in nombre_lower or "ara" in brand:
                props["subcategoria"] = "hard_discount_ara"
            elif "carulla" in nombre_lower or "carulla" in brand:
                props["subcategoria"] = "supermercado_premium"
            else:
                props["subcategoria"] = "supermercado_general"
            
            features_supermercados.append({
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [lon, lat]}
            })

        elif amenity in ["hospital", "clinic", "health_post"] or "hospital" in nombre_lower or "clínica" in nombre_lower:
            props["categoria"] = "salud"
            props["subcategoria"] = amenity or "salud"
            features_salud.append({
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [lon, lat]}
            })

        elif amenity in ["school", "college", "university", "kindergarten"]:
            props["categoria"] = "educacion"
            props["subcategoria"] = amenity or "educacion"
            features_educacion.append({
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [lon, lat]}
            })

    output_dir = os.path.join("geodata", "entorno", "poi")
    os.makedirs(output_dir, exist_ok=True)

    archivos = [
        ("centros_comerciales.geojson", features_centros_comerciales),
        ("supermercados_hard_discount.geojson", features_supermercados),
        ("salud_hospitales.geojson", features_salud),
        ("educacion_colegios.geojson", features_educacion),
    ]

    for fname, feats in archivos:
        path = os.path.join(output_dir, fname)
        fc = {"type": "FeatureCollection", "features": feats}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False, indent=2)
        print(f"Guardado {fname} con {len(feats)} registros en {path}")

    # Guardar GeoJSON unificado de todos los POIs
    todos_feats = features_centros_comerciales + features_supermercados + features_salud + features_educacion
    path_todos = os.path.join(output_dir, "pois_bogota_completo.geojson")
    with open(path_todos, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": todos_feats}, f, ensure_ascii=False, indent=2)
    print(f"Guardado unificado pois_bogota_completo.geojson con {len(todos_feats)} POIs en total.")

if __name__ == "__main__":
    descargar_y_clasificar_pois()
