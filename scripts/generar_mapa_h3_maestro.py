import os
import json
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Point, Polygon
import h3
import unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEODATA_DIR = os.path.join(BASE_DIR, 'geodata')
STATIC_GEO_DIR = os.path.join(BASE_DIR, 'static', 'geo')

CRS_METRICO = 'EPSG:3116'
CRS_WGS84   = 'EPSG:4326'

EXCLUSIONES = ['UPR ZONA NORTE', 'UPR RÍO TUNJUELO', 'UPR RÍO SUMAPAZ', 'UPR RÍO BLANCO', 'SUMAPAZ', 'SUMAPÁZ']

def normalize(text):
    if not text or pd.isna(text): return ''
    text = str(text).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def cargar_layer_fix(path, native_crs=None):
    if not os.path.exists(path):
        return None
    try:
        gdf = gpd.read_file(path)
        if gdf.empty:
            return None
        gdf['geometry'] = gdf.geometry.map(lambda g: shapely.force_2d(g) if g else None)
        if native_crs:
            gdf = gdf.set_crs(native_crs, allow_override=True).to_crs(CRS_METRICO)
        else:
            if gdf.crs is None:
                gdf = gdf.set_crs(CRS_WGS84)
            gdf = gdf.to_crs(CRS_METRICO)
        return gdf
    except Exception as e:
        print(f"Nota: No se pudo cargar {path}: {e}")
        return None

def ejecutar():
    print("=== 1. Cargando capa detallada de UPZs urbanas (geodata/upz.geojson) ===")
    upz_detalladas = gpd.read_file(os.path.join(GEODATA_DIR, 'upz.geojson'))
    localidades_gdf = gpd.read_file(os.path.join(STATIC_GEO_DIR, 'localidad.geojson'))

    upz_urbanas = upz_detalladas[~upz_detalladas['NOMBRE'].apply(lambda n: any(e in str(n).upper() for e in EXCLUSIONES))].copy()
    loc_urbanas = localidades_gdf[~localidades_gdf['LOCNOMBRE'].apply(lambda n: any(e in str(n).upper() for e in EXCLUSIONES))].copy()

    upzs_metric = upz_urbanas.to_crs(CRS_METRICO)
    localidades_metric = loc_urbanas.to_crs(CRS_METRICO)

    print(f"UPZs Urbanas detalladas a procesar: {len(upz_urbanas)}")

    print("=== 2. Generando celdas H3 Res 9 (Micro-Urbana) ===")
    celdas_h3 = set()
    for _, row in upz_urbanas.iterrows():
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

    # Spatial Join de Localidad y UPZ
    join_loc = gpd.sjoin(gdf_h3, localidades_metric[['LOCNOMBRE', 'geometry']], how='left', predicate='within')
    gdf_h3['localidad'] = join_loc['LOCNOMBRE'].fillna('BOGOTÁ')

    join_upz = gpd.sjoin(gdf_h3, upzs_metric[['NOMBRE', 'geometry']], how='left', predicate='within')
    gdf_h3['upz'] = join_upz['NOMBRE'].fillna('ZONA URBANA')

    gdf_h3 = gdf_h3[~gdf_h3['localidad'].apply(lambda n: any(e in str(n).upper() for e in EXCLUSIONES)) &
                    ~gdf_h3['upz'].apply(lambda n: any(e in str(n).upper() for e in EXCLUSIONES))].copy().reset_index(drop=True)

    print(f"Total hexágonos urbanos tras filtro: {len(gdf_h3)}")

    print("=== 3. Cargar Hurtos 100% (Sin Huecos) ===")
    df_hurto = pd.read_csv(os.path.join(GEODATA_DIR, 'seguridad', 'crimen', 'hurto.csv'), sep=';', encoding='utf-8-sig')
    df_hurto['Casos'] = pd.to_numeric(df_hurto['Casos'], errors='coerce').fillna(0)
    ag_hurto = df_hurto.groupby(['UPZ', 'Hecho'])['Casos'].sum().unstack(fill_value=0)

    hurto_upz_norm = {normalize(u): u for u in ag_hurto.index}
    
    def get_hurto_stats(upz_name):
        norm = normalize(upz_name)
        if norm in hurto_upz_norm:
            real_u = hurto_upz_norm[norm]
            row = ag_hurto.loc[real_u]
            total = float(row.sum())
            personas = float(row.get('Hurto a personas', 0))
            comercios = float(row.get('Hurto a comercios', 0))
            residencias = float(row.get('Hurtos a residencias', 0))
            vehiculos = float(row.get('Hurto a automotores', 0) + row.get('Hurto a motocicletas', 0))
            return total, personas, comercios, residencias, vehiculos
        return 0.0, 0.0, 0.0, 0.0, 0.0

    stats_h = [get_hurto_stats(u) for u in gdf_h3['upz']]
    gdf_h3['val_hurtos_upz'] = [s[0] for s in stats_h]
    gdf_h3['val_hurtos_personas'] = [s[1] for s in stats_h]
    gdf_h3['val_hurtos_comercios'] = [s[2] for s in stats_h]
    gdf_h3['val_hurtos_residencias'] = [s[3] for s in stats_h]
    gdf_h3['val_hurtos_vehiculos'] = [s[4] for s in stats_h]

    # Cargar Siniestros Viales
    print("=== 4. Cargar Siniestros Viales (Puntos) ===")
    sin_path = os.path.join(GEODATA_DIR, 'seguridad', 'crimen', 'siniestros.csv')
    siniestros_gdf = None
    siniestros_graves_gdf = None
    if os.path.exists(sin_path):
        df_sin = pd.read_csv(sin_path)
        df_sin['LATITUD'] = pd.to_numeric(df_sin['LATITUD'], errors='coerce')
        df_sin['LONGITUD'] = pd.to_numeric(df_sin['LONGITUD'], errors='coerce')
        df_sin = df_sin.dropna(subset=['LATITUD', 'LONGITUD'])
        
        geometry_sin = [Point(xy) for xy in zip(df_sin['LONGITUD'], df_sin['LATITUD'])]
        siniestros_gdf = gpd.GeoDataFrame(df_sin, geometry=geometry_sin, crs=CRS_WGS84).to_crs(CRS_METRICO)
        
        df_graves = df_sin[df_sin['GRAVEDAD'].astype(str).str.upper().str.contains('HERIDO|MUERTO|GRAVE')]
        geometry_graves = [Point(xy) for xy in zip(df_graves['LONGITUD'], df_graves['LATITUD'])]
        siniestros_graves_gdf = gpd.GeoDataFrame(df_graves, geometry=geometry_graves, crs=CRS_WGS84).to_crs(CRS_METRICO)

    print("=== 5. Cargando y Unificando Capas Vectoriales Completa ===")
    poi_path = os.path.join(GEODATA_DIR, 'entorno', 'poi', 'pois_bogota_completo.geojson')
    pois_gdf = cargar_layer_fix(poi_path)
    
    pois_d1 = pois_gdf[pois_gdf['subcategoria'].isin(['hard_discount_d1', 'hard_discount_ara'])] if pois_gdf is not None else None
    pois_malls = pois_gdf[pois_gdf['categoria'] == 'centro_comercial'] if pois_gdf is not None else None
    pois_salud = pois_gdf[pois_gdf['categoria'] == 'salud'] if pois_gdf is not None else None
    pois_colegios = pois_gdf[pois_gdf['categoria'] == 'educacion'] if pois_gdf is not None else None
    pois_premium = pois_gdf[pois_gdf['subcategoria'].isin(['supermercado_premium', 'supermercado_exito', 'supermercado_carulla', 'supermercado_olimpica'])] if pois_gdf is not None else None

    # Unificar TransMilenio BRT + TransMiCable
    brt_layer = cargar_layer_fix(os.path.join(GEODATA_DIR, 'transporte', 'brt.geojson'))
    cable_layer = cargar_layer_fix(os.path.join(GEODATA_DIR, 'transporte', 'cable.geojson'))
    
    if brt_layer is not None and cable_layer is not None:
        brt_unificado = pd.concat([brt_layer[['geometry']], cable_layer[['geometry']]], ignore_index=True)
    elif brt_layer is not None:
        brt_unificado = brt_layer[['geometry']]
    else:
        brt_unificado = cable_layer[['geometry']] if cable_layer is not None else None

    bus_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'transporte', 'bus.geojson'))
    metro_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'transporte', 'ferreo.geojson'), native_crs='EPSG:6247')
    
    # Ciclorrutas ampliadas
    c1 = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'ciclovia.geojson'))
    c2 = cargar_layer_fix(os.path.join(STATIC_GEO_DIR, 'cicloalameda.geojson'))
    c3 = cargar_layer_fix(os.path.join(STATIC_GEO_DIR, 'cliclorutas.geojson'))
    c_list = [c for c in [c1, c2, c3] if c is not None and not c.empty]
    ciclo_gdf = pd.concat(c_list, ignore_index=True) if c_list else None

    cai_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'centro_atencion_inmediata.geojson'))
    est_policia_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'estacion_policia.geojson'))
    
    # Equipamiento Justicia (URI + Inspecciones + Salas)
    j1 = cargar_layer_fix(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'inspeccion_policia.geojson'))
    j2 = cargar_layer_fix(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'sala_de_atencion.geojson'))
    j3 = cargar_layer_fix(os.path.join(GEODATA_DIR, 'seguridad', 'policia', 'unidad_reaccion_inmediata.geojson'))
    j_list = [j for j in [j1, j2, j3] if j is not None and not j.empty]
    justicia_gdf = pd.concat(j_list, ignore_index=True) if j_list else None

    # Recreación y Deportes (Gimnasios + Mobiliario Deportivo + Parques Infantiles)
    d1_g = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'servicios_publicos', 'gimnasio.geojson'))
    d2_g = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'servicios_publicos', 'mobiliariodeportivo.geojson'))
    d3_g = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'servicios_publicos', 'parque_infantil.geojson'))
    dep_list = [d for d in [d1_g, d2_g, d3_g] if d is not None and not d.empty]
    deporte_gdf = pd.concat(dep_list, ignore_index=True) if dep_list else None

    parques_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'parques.geojson'), native_crs='EPSG:6247')
    basuras_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'servicios_publicos', 'puntos_criticos_arrojo_clandestino_residuos.geojson'))
    arboles_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'arbolado_urbano.geojson'))

    # Capas Ambientales
    pm25_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'pm25_promedio_anual_2024.geojson'))
    temp_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'temperatura_promedio_2024.geojson'))
    prec_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'ambiente', 'precipitacion_acumulada_2024.geojson'))

    # Catastro y Uso
    estratos_gdf = cargar_layer_fix(os.path.join(STATIC_GEO_DIR, 'estratos.geojson'))
    avaluo_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'uso', 'avaluo_catastral_medio.geojson'))
    uso_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'entorno', 'uso', 'uso_suelo_manzana.geojson'))
    area_act_gdf = cargar_layer_fix(os.path.join(GEODATA_DIR, 'areaactividad', 'AreaActividad.shp'))

    print("=== 6. Calculando Distancias Mínimas (sjoin_nearest) ===")
    def calc_dist(gdf_p, layer, col):
        if layer is None or layer.empty:
            gdf_p[col] = 9999.0
            return
        res = gpd.sjoin_nearest(gdf_p[['h3_index', 'geometry']], layer[['geometry']], distance_col=col, how='left')
        m = res.groupby('h3_index')[col].min().reset_index()
        gdf_p[col] = gdf_p['h3_index'].map(m.set_index('h3_index')[col]).round(1).fillna(9999.0)

    calc_dist(gdf_h3, brt_unificado, 'val_dist_brt')
    calc_dist(gdf_h3, bus_gdf, 'val_dist_sitp')
    calc_dist(gdf_h3, metro_gdf, 'val_dist_metro')
    calc_dist(gdf_h3, ciclo_gdf, 'val_dist_ciclo')
    calc_dist(gdf_h3, cai_gdf, 'val_dist_cai')
    calc_dist(gdf_h3, est_policia_gdf, 'val_dist_est_policia')
    calc_dist(gdf_h3, justicia_gdf, 'val_dist_equipamiento_justicia')
    calc_dist(gdf_h3, pois_d1, 'val_dist_d1_ara')
    calc_dist(gdf_h3, pois_malls, 'val_dist_centro_comercial')
    calc_dist(gdf_h3, pois_salud, 'val_dist_hospital')
    calc_dist(gdf_h3, pois_colegios, 'val_dist_colegio')
    calc_dist(gdf_h3, pois_premium, 'val_dist_supermercado_premium')
    calc_dist(gdf_h3, parques_gdf, 'val_dist_parque')
    calc_dist(gdf_h3, deporte_gdf, 'val_dist_recreacion_deporte')
    calc_dist(gdf_h3, basuras_gdf, 'val_dist_basura')

    print("=== 7. Calculando Conteos y Buffers (500m y 300m) ===")
    gdf_h3['buffer_500'] = gdf_h3.geometry.buffer(500)
    gdf_h3['buffer_300'] = gdf_h3.geometry.buffer(300)

    def calc_conteo(gdf_p, layer, buffer_col, target_col):
        if layer is None or layer.empty:
            gdf_p[target_col] = 0
            return
        b_gdf = gpd.GeoDataFrame(gdf_p[['h3_index']], geometry=gdf_p[buffer_col], crs=CRS_METRICO)
        joined = gpd.sjoin(b_gdf, layer[['geometry']], how='inner', predicate='intersects')
        counts = joined.groupby('h3_index').size()
        gdf_p[target_col] = gdf_p['h3_index'].map(counts).fillna(0).astype(int)

    calc_conteo(gdf_h3, brt_unificado, 'buffer_500', 'val_brt_500m')
    calc_conteo(gdf_h3, bus_gdf, 'buffer_300', 'val_sitp_300m')
    calc_conteo(gdf_h3, pois_d1, 'buffer_500', 'val_conteo_hard_discount_500m')
    calc_conteo(gdf_h3, pois_salud, 'buffer_500', 'val_hospitales_500m')
    calc_conteo(gdf_h3, pois_colegios, 'buffer_500', 'val_colegios_500m')
    calc_conteo(gdf_h3, basuras_gdf, 'buffer_300', 'val_basuras_300m')
    calc_conteo(gdf_h3, arboles_gdf, 'buffer_300', 'val_arboles_300m')
    calc_conteo(gdf_h3, siniestros_gdf, 'buffer_300', 'val_siniestros_viales_300m')
    calc_conteo(gdf_h3, siniestros_graves_gdf, 'buffer_500', 'val_siniestros_graves_500m')

    # Imputación de PM2.5, Temperatura y Precipitación
    print("=== 8. Imputando Capas Ambientales (PM2.5, Temperatura, Precipitación) ===")
    def imputar_poligono_val(gdf_p, layer, target_col, src_val_col, default_val):
        if layer is None or layer.empty or src_val_col not in layer.columns:
            gdf_p[target_col] = default_val
            return
        layer[src_val_col] = pd.to_numeric(layer[src_val_col], errors='coerce')
        joined = gpd.sjoin(gdf_p[['h3_index', 'geometry']], layer[[src_val_col, 'geometry']], how='left', predicate='within')
        m = joined.groupby('h3_index')[src_val_col].mean().round(2)
        gdf_p[target_col] = gdf_p['h3_index'].map(m).fillna(default_val)

    imputar_poligono_val(gdf_h3, pm25_gdf, 'val_pm25', 'conc_pm25', 15.0)
    imputar_poligono_val(gdf_h3, temp_gdf, 'val_temperatura', 'temperatur', 14.5)
    imputar_poligono_val(gdf_h3, prec_gdf, 'val_precipitacion', 'precip_per', 800.0)

    # Imputación de Estrato, Avalúo Catastral y Uso
    print("=== 9. Imputando Estrato, Avalúo Catastral y Uso de Suelo ===")
    if estratos_gdf is not None and not estratos_gdf.empty:
        col_e = next((c for c in estratos_gdf.columns if c.lower() == 'estrato'), None)
        if col_e:
            estratos_gdf[col_e] = pd.to_numeric(estratos_gdf[col_e], errors='coerce')
            j_est = gpd.sjoin(gdf_h3[['h3_index', 'geometry']], estratos_gdf[[col_e, 'geometry']], how='left', predicate='intersects')
            m_est = j_est.groupby('h3_index')[col_e].mean().round(2)
            gdf_h3['estrato_promedio_200m'] = gdf_h3['h3_index'].map(m_est).fillna(3.0)

    if avaluo_gdf is not None and not avaluo_gdf.empty:
        col_av = next((c for c in avaluo_gdf.columns if 'av_cat' in c.lower()), None)
        if col_av:
            avaluo_gdf[col_av] = pd.to_numeric(avaluo_gdf[col_av], errors='coerce')
            j_av = gpd.sjoin(gdf_h3[['h3_index', 'geometry']], avaluo_gdf[[col_av, 'geometry']], how='left', predicate='intersects')
            m_av = j_av.groupby('h3_index')[col_av].mean().round(1)
            gdf_h3['val_avaluo_catastral_m2'] = gdf_h3['h3_index'].map(m_av).fillna(3500000.0)
    else:
        gdf_h3['val_avaluo_catastral_m2'] = 3500000.0

    if uso_gdf is not None and not uso_gdf.empty and 'grupousoec' in uso_gdf.columns:
        j_uso = gpd.sjoin(gdf_h3[['h3_index', 'geometry']], uso_gdf[['grupousoec', 'geometry']], how='left', predicate='within')
        m_uso = j_uso.groupby('h3_index')['grupousoec'].first()
        gdf_h3['uso_suelo_predominante'] = gdf_h3['h3_index'].map(m_uso).fillna('RESIDENCIAL').str.capitalize()
    else:
        gdf_h3['uso_suelo_predominante'] = 'Residencial'

    if area_act_gdf is not None and not area_act_gdf.empty:
        col_pot = next((c for c in area_act_gdf.columns if 'pot' in c.lower() or 'nombre' in c.lower()), None)
        if col_pot:
            j_pot = gpd.sjoin(gdf_h3[['h3_index', 'geometry']], area_act_gdf[[col_pot, 'geometry']], how='left', predicate='within')
            m_pot = j_pot.groupby('h3_index')[col_pot].first()
            gdf_h3['area_actividad_pot'] = gdf_h3['h3_index'].map(m_pot).fillna('Residencial')

    print("=== 10. Calculando Rankings Percentiles (0.00 a 1.00) sobre 100% de las variables ===")
    cols_distancia = ["val_dist_brt", "val_dist_sitp", "val_dist_metro", "val_dist_ciclo", "val_dist_cai", "val_dist_est_policia", "val_dist_equipamiento_justicia", "val_dist_d1_ara", "val_dist_centro_comercial", "val_dist_hospital", "val_dist_colegio", "val_dist_supermercado_premium", "val_dist_parque", "val_dist_recreacion_deporte"]
    for col in cols_distancia:
        rank_col = col.replace("val_", "rank_")
        gdf_h3[rank_col] = (1.0 - gdf_h3[col].rank(pct=True, ascending=True)).round(4)

    # Penalizaciones (Menor delincuencia/accidentalidad/PM2.5 = Mayor ranking)
    cols_penalizaciones = ["val_dist_basura", "val_hurtos_upz", "val_hurtos_personas", "val_hurtos_comercios", "val_hurtos_residencias", "val_hurtos_vehiculos", "val_basuras_300m", "val_siniestros_viales_300m", "val_siniestros_graves_500m", "val_pm25"]
    for col in cols_penalizaciones:
        rank_col = col.replace("val_", "rank_")
        if col == "val_dist_basura":
            gdf_h3[rank_col] = gdf_h3[col].rank(pct=True, ascending=True).round(4)
        else:
            gdf_h3[rank_col] = (1.0 - gdf_h3[col].rank(pct=True, ascending=True)).round(4)

    cols_conteo = ["val_brt_500m", "val_sitp_300m", "val_conteo_hard_discount_500m", "val_hospitales_500m", "val_colegios_500m", "val_arboles_300m", "val_avaluo_catastral_m2", "val_temperatura", "val_precipitacion"]
    for col in cols_conteo:
        rank_col = col.replace("val_", "rank_")
        gdf_h3[rank_col] = gdf_h3[col].rank(pct=True, ascending=True).round(4)

    gdf_h3['rank_estrato'] = gdf_h3['estrato_promedio_200m'].rank(pct=True, ascending=True).round(4)

    # SCORE GLOBAL SINTÉTICO REPONDERADO MAESTRO
    gdf_h3['score_h3_global'] = (
        gdf_h3['rank_hurtos_upz'] * 0.25 +                  # 25% Poca Criminalidad / Seguridad
        gdf_h3['rank_estrato'] * 0.20 +                     # 20% Estratos Altos
        gdf_h3['rank_dist_parque'] * 0.15 +                 # 15% Parques Cerca
        gdf_h3['rank_dist_d1_ara'] * 0.05 +
        gdf_h3['rank_dist_centro_comercial'] * 0.05 +
        gdf_h3['rank_dist_supermercado_premium'] * 0.05 +   # 15% Comercio Completo (D1 + Mall + Premium)
        gdf_h3['rank_dist_brt'] * 0.10 +                    # 10% Transporte (BRT + Cable)
        gdf_h3['rank_arboles_300m'] * 0.10                  # 10% Árboles
    ).round(4)

    print("=== 11. Exportando GeoJSON Maestro Definitivo ===")
    drop_cols = ['geometry', 'buffer_500', 'buffer_300']
    features = []
    for _, r in gdf_h3.iterrows():
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

    out_path = os.path.join(GEODATA_DIR, 'mapa_h3_bogota.geojson')
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, indent=2)

    print(f"¡PROCESAMIENTO ABSOLUTAMENTE COMPLETO! mapa_h3_bogota.geojson sobrescrito con {len(features)} hexágonos urbanos Res 9 y 100% de variables de geodata/.")

if __name__ == "__main__":
    ejecutar()
