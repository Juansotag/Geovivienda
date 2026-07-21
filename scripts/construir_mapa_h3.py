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

# Exclusiones de zonas rurales / páramos para evitar sesgos
EXCLUSIONES_RURALES_PATTERNS = ['SUMAP', 'TUNJUELO', 'RIO BLANCO', 'RÍO BLANCO']

def es_zona_rural(nombre):
    if not nombre:
        return False
    nombre_upper = str(nombre).upper()
    return any(p in nombre_upper for p in EXCLUSIONES_RURALES_PATTERNS)

def construir_malla_h3(resolucion=9):
    print(f"=== 1. Cargando capa oficial de UPZs (static/geo/upz.geojson) ===")
    path_upz_oficial = os.path.join(STATIC_GEO_DIR, 'upz.geojson')
    path_loc_oficial = os.path.join(STATIC_GEO_DIR, 'localidad.geojson')

    upzs_gdf = gpd.read_file(path_upz_oficial)
    localidades_gdf = gpd.read_file(path_loc_oficial)

    # Filtrar UPZs urbanas excluyendo páramo y zonas rurales
    upzs_urbanas = upzs_gdf[~upzs_gdf['NOMBRE'].apply(es_zona_rural)].copy()
    localidades_urbanas = localidades_gdf[~localidades_gdf['LOCNOMBRE'].apply(es_zona_rural)].copy()

    upzs_metric = upzs_urbanas.to_crs(CRS_METRICO)
    localidades_metric = localidades_urbanas.to_crs(CRS_METRICO)

    print(f"=== 2. Generando celdas H3 (Resolución {resolucion} - Micro-Urbana) ===")
    celdas_h3 = set()
    for _, row in upzs_urbanas.iterrows():
        geom = row.geometry
        if geom.geom_type == 'Polygon':
            coords = list(geom.exterior.coords)
            lat_lng = [(c[1], c[0]) for c in coords]
            poly = h3.LatLngPoly(lat_lng)
            celdas_h3.update(h3.polygon_to_cells(poly, resolucion))
        elif geom.geom_type == 'MultiPolygon':
            for poly_geom in geom.geoms:
                coords = list(poly_geom.exterior.coords)
                lat_lng = [(c[1], c[0]) for c in coords]
                poly = h3.LatLngPoly(lat_lng)
                celdas_h3.update(h3.polygon_to_cells(poly, resolucion))

    celdas_lista = list(celdas_h3)
    print(f"Total celdas H3 urbanas generadas en Bogotá (Res {resolucion}): {len(celdas_lista)}")

    print("=== 3. Cargando capas de Transporte, Seguridad, POIs, Ambiente y Catastro ===")
    # --- POIs ---
    poi_path = os.path.join(GEODATA_DIR, 'entorno', 'poi', 'pois_bogota_completo.geojson')
    pois_gdf = gpd.read_file(poi_path).to_crs(CRS_METRICO) if os.path.exists(poi_path) else None

    pois_d1 = pois_gdf[pois_gdf['subcategoria'].isin(['hard_discount_d1', 'hard_discount_ara'])] if pois_gdf is not None else None
    pois_malls = pois_gdf[pois_gdf['categoria'] == 'centro_comercial'] if pois_gdf is not None else None
    pois_salud = pois_gdf[pois_gdf['categoria'] == 'salud'] if pois_gdf is not None else None
    pois_colegios = pois_gdf[pois_gdf['categoria'] == 'educacion'] if pois_gdf is not None else None

    # --- Transporte ---
    brt_path = os.path.join(GEODATA_DIR, 'transporte', 'brt.geojson')
    bus_path = os.path.join(GEODATA_DIR, 'transporte', 'bus.geojson')
    metro_path = os.path.join(GEODATA_DIR, 'transporte', 'ferreo.geojson')
    cable_path = os.path.join(GEODATA_DIR, 'transporte', 'cable.geojson')
    ciclo_path = os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'ciclovia.geojson')

    brt_gdf = gpd.read_file(brt_path).to_crs(CRS_METRICO) if os.path.exists(brt_path) else None
    bus_gdf = gpd.read_file(bus_path).to_crs(CRS_METRICO) if os.path.exists(bus_path) else None
    metro_gdf = gpd.read_file(metro_path).to_crs(CRS_METRICO) if os.path.exists(metro_path) else None
    cable_gdf = gpd.read_file(cable_path).to_crs(CRS_METRICO) if os.path.exists(cable_path) else None
    ciclo_gdf = gpd.read_file(ciclo_path).to_crs(CRS_METRICO) if os.path.exists(ciclo_path) else None

    # --- Seguridad & Policía ---
    cai_path = os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'centro_atencion_inmediata.geojson')
    est_policia_path = os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'estacion_policia.geojson')
    cai_gdf = gpd.read_file(cai_path).to_crs(CRS_METRICO) if os.path.exists(cai_path) else None
    est_policia_gdf = gpd.read_file(est_policia_path).to_crs(CRS_METRICO) if os.path.exists(est_policia_path) else None

    # Hurtos por UPZ
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

    # Siniestros Viales
    siniestros_csv = os.path.join(GEODATA_DIR, 'seguridad', 'crimen', 'siniestros.csv')
    siniestros_gdf = None
    if os.path.exists(siniestros_csv):
        try:
            df_sin = pd.read_csv(siniestros_csv, sep=';', nrows=10000, encoding='utf-8-sig')
            if 'LONGITUD' in df_sin.columns and 'LATITUD' in df_sin.columns:
                df_sin = df_sin.dropna(subset=['LONGITUD', 'LATITUD'])
                geoms = [Point(xy) for xy in zip(df_sin['LONGITUD'], df_sin['LATITUD'])]
                siniestros_gdf = gpd.GeoDataFrame(df_sin, crs=CRS_WGS84, geometry=geoms).to_crs(CRS_METRICO)
        except Exception as e:
            print(f"Error cargando siniestros.csv: {e}")

    # --- Ambiente & Servicios ---
    parques_path = os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'parques.geojson')
    basuras_path = os.path.join(GEODATA_DIR, 'entorno', 'servicios_publicos', 'puntos_criticos_arrojo_clandestino_residuos.geojson')
    parques_gdf = gpd.read_file(parques_path).to_crs(CRS_METRICO) if os.path.exists(parques_path) else None
    basuras_gdf = gpd.read_file(basuras_path).to_crs(CRS_METRICO) if os.path.exists(basuras_path) else None

    # --- Catastro & Uso ---
    uso_path = os.path.join(GEODATA_DIR, 'entorno', 'uso', 'uso_suelo_manzana.geojson')
    uso_gdf = gpd.read_file(uso_path).to_crs(CRS_METRICO) if os.path.exists(uso_path) else None

    print("=== 4. Calculando métricas espaciales urbanas para cada celda H3 ===")
    filas = []

    for i, hex_code in enumerate(celdas_lista):
        lat, lng = h3.cell_to_latlng(hex_code)
        punto_wgs84 = Point(lng, lat)
        punto_metric = gpd.GeoSeries([punto_wgs84], crs=CRS_WGS84).to_crs(CRS_METRICO).iloc[0]

        # Boundaries & Geometría H3
        boundary_coords = h3.cell_to_boundary(hex_code)
        poly_coords_wgs84 = [(c[1], c[0]) for c in boundary_coords]
        poly_h3 = Polygon(poly_coords_wgs84)
        poly_h3_metric = gpd.GeoSeries([poly_h3], crs=CRS_WGS84).to_crs(CRS_METRICO).iloc[0]

        # Point-in-polygon para localidad y UPZ urbana
        loc_match = localidades_metric[localidades_metric.contains(punto_metric)]
        localidad = str(loc_match.iloc[0]['LOCNOMBRE']).strip() if not loc_match.empty else "BOGOTÁ"

        upz_match = upzs_metric[upzs_metric.contains(punto_metric)]
        upz = str(upz_match.iloc[0]['NOMBRE']).strip() if not upz_match.empty else "ZONA URBANA"

        # Omitir si cae accidentalmente en Sumapaz o rural
        if es_zona_rural(localidad) or es_zona_rural(upz):
            continue

        # --- Distancias (en metros) ---
        dist_brt = float(round(brt_gdf.distance(punto_metric).min(), 1)) if brt_gdf is not None and not brt_gdf.empty else 9999.0
        dist_sitp = float(round(bus_gdf.distance(punto_metric).min(), 1)) if bus_gdf is not None and not bus_gdf.empty else 9999.0
        dist_metro = float(round(metro_gdf.distance(punto_metric).min(), 1)) if metro_gdf is not None and not metro_gdf.empty else 9999.0
        dist_cable = float(round(cable_gdf.distance(punto_metric).min(), 1)) if cable_gdf is not None and not cable_gdf.empty else 9999.0
        dist_ciclo = float(round(ciclo_gdf.distance(punto_metric).min(), 1)) if ciclo_gdf is not None and not ciclo_gdf.empty else 9999.0

        dist_cai = float(round(cai_gdf.distance(punto_metric).min(), 1)) if cai_gdf is not None and not cai_gdf.empty else 9999.0
        dist_est_policia = float(round(est_policia_gdf.distance(punto_metric).min(), 1)) if est_policia_gdf is not None and not est_policia_gdf.empty else 9999.0

        dist_d1_ara = float(round(pois_d1.distance(punto_metric).min(), 1)) if pois_d1 is not None and not pois_d1.empty else 9999.0
        dist_mall = float(round(pois_malls.distance(punto_metric).min(), 1)) if pois_malls is not None and not pois_malls.empty else 9999.0
        dist_salud = float(round(pois_salud.distance(punto_metric).min(), 1)) if pois_salud is not None and not pois_salud.empty else 9999.0
        dist_colegio = float(round(pois_colegios.distance(punto_metric).min(), 1)) if pois_colegios is not None and not pois_colegios.empty else 9999.0

        dist_parque = float(round(parques_gdf.distance(punto_metric).min(), 1)) if parques_gdf is not None and not parques_gdf.empty else 9999.0
        dist_basura = float(round(basuras_gdf.distance(punto_metric).min(), 1)) if basuras_gdf is not None and not basuras_gdf.empty else 9999.0

        # --- Conteos ---
        conteo_d1_500m = int((pois_d1.distance(punto_metric) <= 500).sum()) if pois_d1 is not None and not pois_d1.empty else 0
        conteo_salud_500m = int((pois_salud.distance(punto_metric) <= 500).sum()) if pois_salud is not None and not pois_salud.empty else 0
        conteo_colegios_500m = int((pois_colegios.distance(punto_metric) <= 500).sum()) if pois_colegios is not None and not pois_colegios.empty else 0
        conteo_siniestros_300m = int((siniestros_gdf.distance(punto_metric) <= 300).sum()) if siniestros_gdf is not None and not siniestros_gdf.empty else 0
        conteo_basuras_300m = int((basuras_gdf.distance(punto_metric) <= 300).sum()) if basuras_gdf is not None and not basuras_gdf.empty else 0

        # Hurtos UPZ
        hurtos_upz = hurtos_por_upz.get(upz.upper(), 0.0)

        # % de Parque
        pct_parque = 0.0
        if parques_gdf is not None and not parques_gdf.empty:
            inter = parques_gdf.intersection(poly_h3_metric)
            area_inter = inter.area.sum()
            area_hex = poly_h3_metric.area
            pct_parque = float(round((area_inter / area_hex) * 100, 2)) if area_hex > 0 else 0.0

        # Uso Suelo Predominante
        uso_pred = "Residencial"
        if uso_gdf is not None and not uso_gdf.empty:
            match_uso = uso_gdf[uso_gdf.contains(punto_metric)]
            if not match_uso.empty and 'grupousoec' in match_uso.columns:
                uso_pred = str(match_uso.iloc[0]['grupousoec']).strip().capitalize()

        filas.append({
            "h3_index": hex_code,
            "lat": lat,
            "lng": lng,
            "localidad": localidad,
            "upz": upz,
            # Valores en Bruto
            "val_dist_brt": dist_brt,
            "val_dist_sitp": dist_sitp,
            "val_dist_metro": dist_metro,
            "val_dist_cable": dist_cable,
            "val_dist_ciclo": dist_ciclo,
            "val_dist_cai": dist_cai,
            "val_dist_est_policia": dist_est_policia,
            "val_dist_d1_ara": dist_d1_ara,
            "val_dist_centro_comercial": dist_mall,
            "val_dist_hospital": dist_salud,
            "val_dist_colegio": dist_colegio,
            "val_dist_parque": dist_parque,
            "val_dist_basura": dist_basura,
            "val_conteo_d1_500m": conteo_d1_500m,
            "val_conteo_salud_500m": conteo_salud_500m,
            "val_conteo_colegios_500m": conteo_colegios_500m,
            "val_siniestros_300m": conteo_siniestros_300m,
            "val_basuras_300m": conteo_basuras_300m,
            "val_hurtos_upz": hurtos_upz,
            "val_pct_parque": pct_parque,
            "uso_suelo_predominante": uso_pred
        })

        if (i + 1) % 1000 == 0 or (i + 1) == len(celdas_lista):
            print(f"Procesadas {i+1}/{len(celdas_lista)} celdas H3 urbanas...")

    df_h3 = pd.DataFrame(filas)

    print("=== 5. Calculando Rankings en Percentil (0.00 a 1.00) sobre el casco urbano ===")
    
    # Inverso: Menor distancia = Mejor posición (Rank alto)
    cols_distancia_positiva = [
        "val_dist_brt", "val_dist_sitp", "val_dist_metro", "val_dist_cable", "val_dist_ciclo",
        "val_dist_cai", "val_dist_est_policia", "val_dist_d1_ara", "val_dist_centro_comercial",
        "val_dist_hospital", "val_dist_colegio", "val_dist_parque"
    ]
    for col in cols_distancia_positiva:
        rank_col = col.replace("val_", "rank_")
        df_h3[rank_col] = (1.0 - df_h3[col].rank(pct=True, ascending=True)).round(4)

    # Inverso Penalizaciones: Menor delincuencia / basuras = Mejor posición (Rank alto)
    cols_penalizaciones = ["val_dist_basura", "val_siniestros_300m", "val_basuras_300m", "val_hurtos_upz"]
    for col in cols_penalizaciones:
        rank_col = col.replace("val_", "rank_")
        if col == "val_dist_basura":
            df_h3[rank_col] = df_h3[col].rank(pct=True, ascending=True).round(4)
        else:
            df_h3[rank_col] = (1.0 - df_h3[col].rank(pct=True, ascending=True)).round(4)

    # Directo: Mayor conteo / área verde = Mejor posición (Rank alto)
    cols_conteo_positivo = [
        "val_conteo_d1_500m", "val_conteo_salud_500m", "val_conteo_colegios_500m", "val_pct_parque"
    ]
    for col in cols_conteo_positivo:
        rank_col = col.replace("val_", "rank_")
        df_h3[rank_col] = df_h3[col].rank(pct=True, ascending=True).round(4)

    # --- Score Sintético de Entorno H3 ---
    df_h3['score_h3_global'] = (
        df_h3['rank_dist_d1_ara'] * 0.15 +
        df_h3['rank_dist_centro_comercial'] * 0.10 +
        df_h3['rank_dist_hospital'] * 0.10 +
        df_h3['rank_dist_colegio'] * 0.10 +
        df_h3['rank_dist_brt'] * 0.15 +
        df_h3['rank_dist_ciclo'] * 0.10 +
        df_h3['rank_hurtos_upz'] * 0.15 +
        df_h3['rank_dist_parque'] * 0.15
    ).round(4)

    print("=== 6. Generando GeoJSON final con Geometrías H3 (Res 9 Urbana) ===")
    features_geojson = []
    for _, r in df_h3.iterrows():
        hex_code = r['h3_index']
        boundary_coords = h3.cell_to_boundary(hex_code)
        poly_coords = [[c[1], c[0]] for c in boundary_coords]
        poly_coords.append(poly_coords[0])

        props = r.to_dict()
        features_geojson.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [poly_coords]}
        })

    out_path = os.path.join(GEODATA_DIR, 'mapa_h3_bogota.geojson')
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features_geojson}, f, ensure_ascii=False, indent=2)

    print(f"¡Mapa H3 urbano Res {resolucion} completado exitosamente! Guardado en {out_path} con {len(features_geojson)} hexágonos.")
    return df_h3

if __name__ == "__main__":
    construir_malla_h3(resolucion=9)
