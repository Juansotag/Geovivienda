import os
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
import h3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEODATA_DIR = os.path.join(BASE_DIR, 'geodata')
STATIC_GEO_DIR = os.path.join(BASE_DIR, 'static', 'geo')

CRS_METRICO = 'EPSG:3116'
CRS_WGS84   = 'EPSG:4326'

EXCLUSIONES = [
    'SUMAPAZ', 'SUMAPÁZ', 'SUMAPAZ', 'RÍO TUNJUELO', 'RIO TUNJUELO',
    'CUENCA DEL TUNJUELO', 'RÍO BLANCO', 'RIO BLANCO', 'UPR',
    'UPR ZONA NORTE', 'UPR RÍO TUNJUELO', 'UPR RÍO SUMAPAZ', 'UPR RÍO BLANCO'
]

def es_rural(nombre):
    if not nombre:
        return False
    nom = str(nombre).upper().strip()
    return any(e in nom for e in EXCLUSIONES)

def ejecutar():
    print("=== 1. Cargando capas oficiales de UPZs urbanas ===")
    upzs_gdf = gpd.read_file(os.path.join(STATIC_GEO_DIR, 'upz.geojson'))
    localidades_gdf = gpd.read_file(os.path.join(STATIC_GEO_DIR, 'localidad.geojson'))

    upzs_urbanas = upzs_gdf[~upzs_gdf['NOMBRE'].apply(es_rural)].copy()
    localidades_urbanas = localidades_gdf[~localidades_gdf['LOCNOMBRE'].apply(es_rural)].copy()

    upzs_metric = upzs_urbanas.to_crs(CRS_METRICO)
    localidades_metric = localidades_urbanas.to_crs(CRS_METRICO)

    print("=== 2. Generando malla H3 Res 9 (excluyendo zonas rurales) ===")
    celdas_h3 = set()
    for _, row in upzs_urbanas.iterrows():
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

    # Crear GeoDataFrame base de puntos H3
    filas_base = []
    for hex_code in celdas_lista:
        lat, lng = h3.cell_to_latlng(hex_code)
        punto_wgs84 = Point(lng, lat)
        filas_base.append({
            "h3_index": hex_code,
            "lat": lat,
            "lng": lng,
            "geometry": punto_wgs84
        })

    gdf_h3 = gpd.GeoDataFrame(filas_base, crs=CRS_WGS84).to_crs(CRS_METRICO)

    # Point-in-polygon para localidad y UPZ urbana
    print("=== 3. Asignando Localidad y UPZ por centroide H3 ===")
    join_loc = gpd.sjoin(gdf_h3, localidades_metric[['LOCNOMBRE', 'geometry']], how='left', predicate='within')
    gdf_h3['localidad'] = join_loc['LOCNOMBRE'].fillna('BOGOTÁ')

    join_upz = gpd.sjoin(gdf_h3, upzs_metric[['NOMBRE', 'geometry']], how='left', predicate='within')
    gdf_h3['upz'] = join_upz['NOMBRE'].fillna('ZONA URBANA')

    # Filtrar cualquier celda que accidentalmente haya caído en Sumapaz o UPRs
    gdf_h3 = gdf_h3[~gdf_h3['localidad'].apply(es_rural) & ~gdf_h3['upz'].apply(es_rural)].copy()
    gdf_h3 = gdf_h3.reset_index(drop=True)
    print(f"Total hexágonos verdaderamente urbanos tras filtro: {len(gdf_h3)}")

    # --- Cargar capas de entorno y POIs ---
    print("=== 4. Calculando distancias vectoriales ultrarrápidas (sjoin_nearest) ===")
    poi_path = os.path.join(GEODATA_DIR, 'entorno', 'poi', 'pois_bogota_completo.geojson')
    pois_gdf = gpd.read_file(poi_path).to_crs(CRS_METRICO) if os.path.exists(poi_path) else None

    pois_d1 = pois_gdf[pois_gdf['subcategoria'].isin(['hard_discount_d1', 'hard_discount_ara'])] if pois_gdf is not None else None
    pois_malls = pois_gdf[pois_gdf['categoria'] == 'centro_comercial'] if pois_gdf is not None else None
    pois_salud = pois_gdf[pois_gdf['categoria'] == 'salud'] if pois_gdf is not None else None
    pois_colegios = pois_gdf[pois_gdf['categoria'] == 'educacion'] if pois_gdf is not None else None

    def calc_dist_nearest(gdf_puntos, layer_gdf, col_name):
        if layer_gdf is None or layer_gdf.empty:
            gdf_puntos[col_name] = 9999.0
            return
        res = gpd.sjoin_nearest(gdf_puntos[['h3_index', 'geometry']], layer_gdf[['geometry']], distance_col=col_name, how='left')
        res_first = res.groupby('h3_index')[col_name].min().reset_index()
        gdf_puntos[col_name] = gdf_puntos['h3_index'].map(res_first.set_index('h3_index')[col_name]).round(1).fillna(9999.0)

    brt_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'transporte', 'brt.geojson')).to_crs(CRS_METRICO) if os.path.exists(os.path.join(GEODATA_DIR, 'transporte', 'brt.geojson')) else None
    bus_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'transporte', 'bus.geojson')).to_crs(CRS_METRICO) if os.path.exists(os.path.join(GEODATA_DIR, 'transporte', 'bus.geojson')) else None
    metro_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'transporte', 'ferreo.geojson')).to_crs(CRS_METRICO) if os.path.exists(os.path.join(GEODATA_DIR, 'transporte', 'ferreo.geojson')) else None
    ciclo_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'ciclovia.geojson')).to_crs(CRS_METRICO) if os.path.exists(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'ciclovia.geojson')) else None
    cai_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'centro_atencion_inmediata.geojson')).to_crs(CRS_METRICO) if os.path.exists(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'centro_atencion_inmediata.geojson')) else None
    est_policia_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'estacion_policia.geojson')).to_crs(CRS_METRICO) if os.path.exists(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'estacion_policia.geojson')) else None
    parques_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'parques.geojson')).to_crs(CRS_METRICO) if os.path.exists(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'parques.geojson')) else None
    basuras_gdf = gpd.read_file(os.path.join(GEODATA_DIR, 'entorno', 'servicios_publicos', 'puntos_criticos_arrojo_clandestino_residuos.geojson')).to_crs(CRS_METRICO) if os.path.exists(os.path.join(GEODATA_DIR, 'entorno', 'servicios_publicos', 'puntos_criticos_arrojo_clandestino_residuos.geojson')) else None

    calc_dist_nearest(gdf_h3, brt_gdf, 'val_dist_brt')
    calc_dist_nearest(gdf_h3, bus_gdf, 'val_dist_sitp')
    calc_dist_nearest(gdf_h3, metro_gdf, 'val_dist_metro')
    calc_dist_nearest(gdf_h3, ciclo_gdf, 'val_dist_ciclo')
    calc_dist_nearest(gdf_h3, cai_gdf, 'val_dist_cai')
    calc_dist_nearest(gdf_h3, est_policia_gdf, 'val_dist_est_policia')
    calc_dist_nearest(gdf_h3, pois_d1, 'val_dist_d1_ara')
    calc_dist_nearest(gdf_h3, pois_malls, 'val_dist_centro_comercial')
    calc_dist_nearest(gdf_h3, pois_salud, 'val_dist_hospital')
    calc_dist_nearest(gdf_h3, pois_colegios, 'val_dist_colegio')
    calc_dist_nearest(gdf_h3, parques_gdf, 'val_dist_parque')
    calc_dist_nearest(gdf_h3, basuras_gdf, 'val_dist_basura')

    # Hurtos UPZ
    hurto_csv = os.path.join(GEODATA_DIR, 'seguridad', 'crimen', 'hurto.csv')
    hurtos_por_upz = {}
    if os.path.exists(hurto_csv):
        try:
            df_h = pd.read_csv(hurto_csv, sep=';', encoding='utf-8-sig')
            if 'UPZ' in df_h.columns and 'Casos' in df_h.columns:
                df_h['Casos'] = pd.to_numeric(df_h['Casos'], errors='coerce').fillna(0)
                ag = df_h.groupby('UPZ')['Casos'].sum().to_dict()
                hurtos_por_upz = {str(k).strip().upper(): float(v) for k, v in ag.items()}
        except Exception as e:
            print(f"Error procesando hurto.csv: {e}")

    gdf_h3['val_hurtos_upz'] = gdf_h3['upz'].apply(lambda u: hurtos_por_upz.get(str(u).upper(), 0.0))

    print("=== 5. Calculando Rankings Percentiles (0.00 a 1.00) sobre área urbana ===")
    cols_distancia = ["val_dist_brt", "val_dist_sitp", "val_dist_metro", "val_dist_ciclo", "val_dist_cai", "val_dist_est_policia", "val_dist_d1_ara", "val_dist_centro_comercial", "val_dist_hospital", "val_dist_colegio", "val_dist_parque"]
    for col in cols_distancia:
        rank_col = col.replace("val_", "rank_")
        gdf_h3[rank_col] = (1.0 - gdf_h3[col].rank(pct=True, ascending=True)).round(4)

    cols_penalizaciones = ["val_dist_basura", "val_hurtos_upz"]
    for col in cols_penalizaciones:
        rank_col = col.replace("val_", "rank_")
        if col == "val_dist_basura":
            gdf_h3[rank_col] = gdf_h3[col].rank(pct=True, ascending=True).round(4)
        else:
            gdf_h3[rank_col] = (1.0 - gdf_h3[col].rank(pct=True, ascending=True)).round(4)

    gdf_h3['score_h3_global'] = (
        gdf_h3['rank_dist_d1_ara'] * 0.20 +
        gdf_h3['rank_dist_centro_comercial'] * 0.15 +
        gdf_h3['rank_dist_hospital'] * 0.10 +
        gdf_h3['rank_dist_colegio'] * 0.10 +
        gdf_h3['rank_dist_brt'] * 0.15 +
        gdf_h3['rank_dist_ciclo'] * 0.10 +
        gdf_h3['rank_hurtos_upz'] * 0.10 +
        gdf_h3['rank_dist_parque'] * 0.10
    ).round(4)

    print("=== 6. Escribiendo GeoJSON final a geodata/mapa_h3_bogota.geojson ===")
    features_geojson = []
    for _, r in gdf_h3.iterrows():
        hex_code = r['h3_index']
        boundary_coords = h3.cell_to_boundary(hex_code)
        poly_coords = [[c[1], c[0]] for c in boundary_coords]
        poly_coords.append(poly_coords[0])

        props = r.drop(['geometry']).to_dict()
        features_geojson.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [poly_coords]}
        })

    out_path = os.path.join(GEODATA_DIR, 'mapa_h3_bogota.geojson')
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features_geojson}, f, ensure_ascii=False, indent=2)

    print(f"¡ÉXITO TOTAL! mapa_h3_bogota.geojson SOBRESCRITO con {len(features_geojson)} hexágonos urbanos Res 9.")

if __name__ == "__main__":
    ejecutar()
