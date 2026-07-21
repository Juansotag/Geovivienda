"""
Genera static/data/h3_distribuciones.json:
Para cada variable val_* y rank_*, guarda el array de valores de los 3766 hexágonos
urbanos. Se usa en el frontend para dibujar histogramas SVG en el perfil del inmueble
sin tener que enviar el GeoJSON completo de 8MB al cliente.
"""
import json
import os
import geopandas as gpd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H3_PATH = os.path.join(BASE_DIR, 'geodata', 'mapa_h3_bogota.geojson')
OUT_PATH = os.path.join(BASE_DIR, 'static', 'data', 'h3_distribuciones.json')

print(f"Leyendo {H3_PATH} ...")
gdf = gpd.read_file(H3_PATH)
print(f"  {len(gdf)} hexágonos, {len(gdf.columns)} columnas")

# Columnas numéricas a exportar (val_* y rank_* y estrato y score)
skip = {'geometry', 'h3_index', 'lat', 'lng', 'localidad', 'upz',
        'uso_suelo_predominante', 'area_actividad_pot'}
num_cols = [c for c in gdf.columns if c not in skip]

distribuciones = {}
for col in num_cols:
    serie = gdf[col].dropna()
    if serie.empty:
        continue
    try:
        vals = serie.astype(float).tolist()
        distribuciones[col] = {
            "valores": [round(v, 4) for v in vals],
            "min": round(float(serie.min()), 4),
            "max": round(float(serie.max()), 4),
            "p25": round(float(np.percentile(vals, 25)), 4),
            "p50": round(float(np.percentile(vals, 50)), 4),
            "p75": round(float(np.percentile(vals, 75)), 4),
            "n": len(vals),
        }
    except Exception as e:
        print(f"  Advertencia: no se pudo procesar {col}: {e}")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(distribuciones, f, ensure_ascii=False, separators=(',', ':'))

size_kb = os.path.getsize(OUT_PATH) / 1024
print(f"\nGuardado {OUT_PATH}")
print(f"  {len(distribuciones)} variables exportadas, {size_kb:.0f} KB")
