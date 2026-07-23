"""
Genera el mapeo UPZ pre-2023 (116) → UPL post-2023 (33)
mediante point-in-polygon: centroide de cada UPZ contra los polígonos UPL.

Salida: services/upz_upl_mapping.py  con el dict UPZ_A_UPL
"""
import os, json, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import geopandas as gpd
    from shapely.geometry import shape, mapping
except ImportError:
    sys.exit("Instala geopandas: pip install geopandas")

# Cargar capas
upz_path = os.path.join(BASE, "geodata", "upz.geojson")
upl_path = os.path.join(BASE, "static", "geo", "upz.geojson")

print("Cargando UPZ pre-2023 (116)...")
upz_gdf = gpd.read_file(upz_path).to_crs("EPSG:4326")

print("Cargando UPL post-2023 (33)...")
upl_gdf = gpd.read_file(upl_path).to_crs("EPSG:4326")

print(f"UPZs: {len(upz_gdf)}  |  UPLs: {len(upl_gdf)}")

# Para cada UPZ, calcular centroide y ver en qué UPL cae
mapeo = {}   # UPZ_NOMBRE → UPL_NOMBRE
sin_match = []

for _, upz_row in upz_gdf.iterrows():
    nombre_upz = str(upz_row["NOMBRE"]).strip().upper()
    centroide = upz_row.geometry.centroid

    # point-in-polygon contra UPLs
    hits = upl_gdf[upl_gdf.geometry.contains(centroide)]
    if not hits.empty:
        nombre_upl = str(hits.iloc[0]["NOMBRE"]).strip()
        mapeo[nombre_upz] = nombre_upl
    else:
        # Fallback: UPL más cercana por distancia (bordes/enclaves)
        upl_metric = upl_gdf.to_crs("EPSG:3116")
        centroide_metric = gpd.GeoSeries([centroide], crs="EPSG:4326").to_crs("EPSG:3116").iloc[0]
        upl_metric["_dist"] = upl_metric.geometry.distance(centroide_metric)
        nearest = upl_metric.nsmallest(1, "_dist").index[0]
        nombre_upl = str(upl_gdf.loc[nearest, "NOMBRE"]).strip()
        mapeo[nombre_upz] = nombre_upl
        sin_match.append(nombre_upz)
        print(f"  [FALLBACK distancia] {nombre_upz} -> {nombre_upl}")

print(f"\n=== Mapeo generado: {len(mapeo)} UPZs ===")
for upz, upl in sorted(mapeo.items()):
    print(f"  {upz:40s} -> {upl}")

if sin_match:
    print(f"\n[INFO] {len(sin_match)} UPZs fuera de polígono, asignadas por distancia: {sin_match}")

# Guardar como módulo Python
out_path = os.path.join(BASE, "services", "upz_upl_mapping.py")
lines = [
    '"""',
    'Mapeo automático UPZ pre-2023 (116) → UPL post-2023 (33).',
    'Generado por scripts/generar_mapeo_upz_upl.py',
    '"""',
    '',
    '# Clave: nombre UPZ pre-2023 en MAYÚSCULAS (como aparece en el H3 maestro)',
    '# Valor: nombre UPL post-2023 (como aparece en el formulario de búsqueda)',
    'UPZ_A_UPL: dict[str, str] = {',
]
for upz, upl in sorted(mapeo.items()):
    lines.append(f'    {repr(upz)}: {repr(upl)},')
lines += ['}', '']

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\nGuardado en: {out_path}")
