import os
import json
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Point, Polygon
import h3
import unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEODATA_DIR = os.path.join(BASE_DIR, 'geodata', 'cali')

CRS_METRICO = 'EPSG:3116'
CRS_WGS84   = 'EPSG:4326'

EXCLUSIONES = ['FARALLONES'] # Ejemplo: excluir Parque Nacional Farallones de Cali

def normalize(text):
    if not text or pd.isna(text): return ''
    text = str(text).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def ejecutar():
    print("=== 1. Cargando capas bases (Barrios y Comunas) ===")
    barrios_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'barrios.geojson'))
    comunas_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'comunas.geojson'))
    
    print("=== 2. Cargando e integrando datos de Estratos ===")
    estratos_csv = pd.read_csv(os.path.join(GEODATA_DIR, 'estratos_por_barrio.csv'), sep=';', encoding='utf-8')
    # Renombrar columnas para facilitar merge
    estratos_csv = estratos_csv.rename(columns={'Código único': 'BarCodigo', 'Estrato moda': 'estrato_promedio_200m'})
    
    # Asegurar tipos compatibles para el merge
    barrios_gdf['BarCodigo'] = pd.to_numeric(barrios_gdf['BarCodigo'], errors='coerce')
    estratos_csv['BarCodigo'] = pd.to_numeric(estratos_csv['BarCodigo'], errors='coerce')
    
    # Merge de estratos a los polígonos de barrios
    barrios_detallados = barrios_gdf.merge(estratos_csv[['BarCodigo', 'estrato_promedio_200m']], on='BarCodigo', how='left')

    barrios_urbanos = barrios_detallados[~barrios_detallados['BarNombre'].apply(lambda n: any(e in str(n).upper() for e in EXCLUSIONES))].copy()
    loc_urbanas = comunas_gdf[~comunas_gdf['ComNombre'].apply(lambda n: any(e in str(n).upper() for e in EXCLUSIONES))].copy()
    
    # Ensure they are in WGS84 for H3 lat/lng
    if barrios_urbanos.crs != CRS_WGS84:
        barrios_urbanos = barrios_urbanos.to_crs(CRS_WGS84)
    if loc_urbanas.crs != CRS_WGS84:
        loc_urbanas = loc_urbanas.to_crs(CRS_WGS84)

    barrios_metric = barrios_urbanos.to_crs(CRS_METRICO)
    comunas_metric = loc_urbanas.to_crs(CRS_METRICO)

    print(f"Barrios Urbanos detallados a procesar: {len(barrios_urbanos)}")

    print("=== 3. Generando celdas H3 Res 9 (Micro-Urbana) ===")
    celdas_h3 = set()
    for _, row in barrios_urbanos.iterrows():
        geom = row.geometry
        if geom.geom_type == 'Polygon':
            coords = list(geom.exterior.coords)
            lat_lng = [(c[1], c[0]) for c in coords]
            poly = h3.LatLngPoly(lat_lng)
            celdas_h3.update(h3.polygon_to_cells(poly, 9))
        elif geom.geom_type == 'MultiPolygon':
            for poly_geom in geom.geoms:
                coords = list(poly_geom.exterior.coords)
                lat_lng = [(c[1], c[0]) for c in coords]
                poly = h3.LatLngPoly(lat_lng)
                celdas_h3.update(h3.polygon_to_cells(poly, 9))

    celdas_lista = list(celdas_h3)
    print(f"Total hexágonos H3 urbanos (Res 9): {len(celdas_lista)}")

    filas_base = []
    for hex_code in celdas_lista:
        lat, lng = h3.cell_to_latlng(hex_code)
        punto_wgs84 = Point(lng, lat)
        filas_base.append({"h3_index": hex_code, "lat": lat, "lng": lng, "geometry": punto_wgs84})

    gdf_h3 = gpd.GeoDataFrame(filas_base, crs=CRS_WGS84).to_crs(CRS_METRICO)

    # Spatial Join de Comuna y Barrio
    print("=== 4. Asignando variables administrativas y estrato a los hexágonos ===")
    join_loc = gpd.sjoin(gdf_h3, comunas_metric[['ComNombre', 'geometry']], how='left', predicate='within')
    gdf_h3['nivel_admin_1'] = join_loc['ComNombre'].fillna('CALI')

    join_barrio = gpd.sjoin(gdf_h3, barrios_metric[['BarNombre', 'estrato_promedio_200m', 'geometry']], how='left', predicate='within')
    gdf_h3['nivel_admin_2'] = join_barrio['BarNombre'].fillna('ZONA URBANA')
    
    # Asignar el estrato moda mapeado desde el barrio (usamos estrato_promedio_200m para mantener compatibilidad con el sistema actual)
    gdf_h3['estrato_promedio_200m'] = pd.to_numeric(join_barrio['estrato_promedio_200m'], errors='coerce')
    gdf_h3['estrato_promedio_200m'] = gdf_h3['estrato_promedio_200m'].fillna(3.0) # Fallback a estrato medio si falta data

    # Llenar distancias dummy para evitar que se rompa el frontend (mientras conseguimos los de transporte de Cali)
    gdf_h3['dist_sitp'] = 500
    gdf_h3['dist_tm'] = 1500
    gdf_h3['dist_ciclo'] = 800

    gdf_h3 = gdf_h3[~gdf_h3['nivel_admin_1'].apply(lambda n: any(e in str(n).upper() for e in EXCLUSIONES)) &
                    ~gdf_h3['nivel_admin_2'].apply(lambda n: any(e in str(n).upper() for e in EXCLUSIONES))].copy().reset_index(drop=True)

    print(f"Total hexágonos urbanos tras filtro: {len(gdf_h3)}")

    # Volver a WGS84 para exportar
    gdf_h3_export = gdf_h3.to_crs(CRS_WGS84)

    # Eliminar duplicados (sjoin a veces duplica)
    gdf_h3_export = gdf_h3_export.drop_duplicates(subset=['h3_index'])

    print("=== FINAL. Guardando GeoJSON H3 Cali ===")
    drop_cols = ['geometry']
    features = []
    for _, r in gdf_h3_export.iterrows():
        hex_code = r['h3_index']
        boundary_coords = h3.cell_to_boundary(hex_code)
        poly_coords = [[c[1], c[0]] for c in boundary_coords]
        poly_coords.append(poly_coords[0])

        props = r.drop(labels=[c for c in drop_cols if c in r.index]).to_dict()
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [poly_coords]}
        })

    output_path = os.path.join(GEODATA_DIR, 'mapa_h3_cali.geojson')
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)
    print(f"Guardado exitosamente en: {output_path}")

if __name__ == '__main__':
    ejecutar()
