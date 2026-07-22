import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import os
import json
import math

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEO_DIR  = os.path.join(BASE_DIR, 'static', 'geo')

CRS_METRICO = 'EPSG:3116'
CRS_WGS84   = 'EPSG:4326'


import h3


def _limpiar_h3_row(row_dict: dict) -> dict:
    """Convierte valores numpy a tipos Python nativos para que json.dumps()
    funcione al guardar h3_data como JSONB en la DB.
    - numpy.floating  → float (NaN → None)
    - numpy.integer   → int
    - numpy.bool_     → bool
    - str/None        → sin cambio
    """
    out = {}
    for k, v in row_dict.items():
        if isinstance(v, np.floating):
            out[k] = None if math.isnan(float(v)) else float(v)
        elif isinstance(v, np.integer):
            out[k] = int(v)
        elif isinstance(v, np.bool_):
            out[k] = bool(v)
        elif isinstance(v, float):
            out[k] = None if math.isnan(v) else v
        else:
            out[k] = v
    return out


def _cargar_capas():
    sitp        = gpd.read_file(os.path.join(GEO_DIR, 'estaciones_sitp.geojson')).to_crs(CRS_METRICO)
    tm          = gpd.read_file(os.path.join(GEO_DIR, 'estaciones_tm.geojson')).to_crs(CRS_METRICO)
    ciclo       = gpd.read_file(os.path.join(GEO_DIR, 'cliclorutas.geojson')).to_crs(CRS_METRICO)
    estratos    = gpd.read_file(os.path.join(GEO_DIR, 'estratos.geojson')).to_crs(CRS_METRICO)
    localidades = gpd.read_file(os.path.join(GEO_DIR, 'localidad.geojson')).to_crs(CRS_METRICO)
    upzs        = gpd.read_file(os.path.join(GEO_DIR, 'upz.geojson')).to_crs(CRS_METRICO)
    metro       = gpd.read_file(os.path.join(GEO_DIR, 'estaciones_metro.geojson')).to_crs(CRS_METRICO)
    municipios  = gpd.read_file(os.path.join(GEO_DIR, 'municipios_cundinamarca.geojson')).to_crs(CRS_METRICO)

    # Capas POIs
    poi_path = os.path.join(BASE_DIR, 'geodata', 'entorno', 'poi', 'pois_bogota_completo.geojson')
    pois_d1_ara = None
    pois_malls = None
    pois_salud = None
    pois_educacion = None
    pois_parques = None

    if os.path.exists(poi_path):
        pois_gdf = gpd.read_file(poi_path).to_crs(CRS_METRICO)
        pois_d1_ara = pois_gdf[pois_gdf['subcategoria'].isin(['hard_discount_d1', 'hard_discount_ara'])]
        pois_malls = pois_gdf[pois_gdf['categoria'] == 'centro_comercial']
        pois_salud = pois_gdf[pois_gdf['categoria'] == 'salud']
        pois_educacion = pois_gdf[pois_gdf['categoria'] == 'educacion']

    # Capas de parques y transporte extendido para POIs cercanos
    parques_path = os.path.join(BASE_DIR, 'geodata', 'entorno', 'ambiente', 'parques.geojson')
    if os.path.exists(parques_path):
        try:
            pois_parques = gpd.read_file(parques_path)
            # pois_parques.crs puede ser None si el archivo no tiene CRS declarado;
            # str(None).upper() devolvería 'NONE', no 'None' — y el .upper() sobre
            # el objeto None lanzaría AttributeError. Se verifica is None primero.
            crs_val = pois_parques.crs
            if crs_val is None or str(crs_val).upper() == 'EPSG:6247':
                pois_parques = pois_parques.set_crs('EPSG:6247', allow_override=True).to_crs(CRS_METRICO)
            else:
                pois_parques = pois_parques.to_crs(CRS_METRICO)
        except Exception:
            pois_parques = None

    col_estrato = next((c for c in estratos.columns if c.lower() == 'estrato'), None)
    if col_estrato:
        estratos[col_estrato] = pd.to_numeric(estratos[col_estrato], errors='coerce')
        estratos = estratos.dropna(subset=[col_estrato])

    upz_a_localidad = {}
    for _, upz_row in upzs.iterrows():
        centroide = upz_row.geometry.centroid
        loc_match = localidades[localidades.contains(centroide)]
        if not loc_match.empty:
            upz_a_localidad[str(upz_row['NOMBRE']).strip()] = str(loc_match.iloc[0]['LOCNOMBRE']).strip()

    # Cargar GeoJSON H3 Res 9 maestro en memoria, indexado por h3_index
    h3_lookup = {}
    h3_geojson_path = os.path.join(BASE_DIR, 'geodata', 'mapa_h3_bogota.geojson')
    if os.path.exists(h3_geojson_path):
        try:
            h3_gdf = gpd.read_file(h3_geojson_path)
            # Excluir columna geometry para el snapshot
            prop_cols = [c for c in h3_gdf.columns if c != 'geometry']
            for _, row in h3_gdf.iterrows():
                idx = str(row.get('h3_index', ''))
                if idx:
                    h3_lookup[idx] = _limpiar_h3_row({c: row[c] for c in prop_cols})
            print(f"[spatial_analysis] GeoJSON H3 cargado: {len(h3_lookup)} hexágonos en memoria")
        except Exception as e:
            print(f"[spatial_analysis] Advertencia: no se pudo cargar el GeoJSON H3: {e}")

    return (
        sitp, tm, ciclo, estratos, col_estrato, localidades, upzs, metro, municipios,
        upz_a_localidad, pois_d1_ara, pois_malls, pois_salud, pois_educacion,
        pois_parques, h3_lookup
    )


def _calcular_distancias(gdf, sitp, tm, ciclo):
    def min_dist(point, ref):
        return ref.distance(point).min()

    gdf['dist_sitp']  = gdf.geometry.apply(lambda x: min_dist(x, sitp))
    gdf['dist_tm']    = gdf.geometry.apply(lambda x: min_dist(x, tm))
    gdf['dist_ciclo'] = gdf.geometry.apply(lambda x: min_dist(x, ciclo))
    return gdf


def _calcular_estrato_promedio(gdf, estratos, col_estrato):
    resultados = []

    for _, row in gdf.iterrows():
        buffer_gdf   = gpd.GeoDataFrame({'geometry': [row.geometry.buffer(200)]}, crs=CRS_METRICO)
        interseccion = gpd.overlay(estratos, buffer_gdf, how='intersection')

        if not interseccion.empty:
            interseccion = interseccion[interseccion[col_estrato].isin([1, 2, 3, 4, 5, 6])]

        if not interseccion.empty:
            interseccion = interseccion.copy()
            interseccion['area'] = interseccion.geometry.area
            total = interseccion['area'].sum()
            if total > 0:
                avg = (interseccion[col_estrato] * interseccion['area']).sum() / total
                resultados.append(round(avg, 2))
                continue

        resultados.append(None)

    gdf['estrato_promedio_200m'] = resultados
    return gdf


_CAPAS_CACHE = None


def _capas():
    global _CAPAS_CACHE
    if _CAPAS_CACHE is None:
        _CAPAS_CACHE = _cargar_capas()
    return _CAPAS_CACHE


# Pre-cargar las capas geográficas al importar el módulo (no de forma lazy).
# _cargar_capas() tarda 5-30s en el primer call (carga GeoJSON H3 de Bogotá
# completo + GeoPandas de varias capas). Si se hace lazy en el primer request
# de un usuario, ese request experimenta esa latencia sin motivo.
# Con Flask (debug=False) el import se ejecuta al arrancar el proceso.
try:
    _capas()
except Exception as _e:
    print(f"[spatial_analysis] Advertencia: no se pudieron precargar capas geográficas: {_e}")
    print("[spatial_analysis] Las capas se cargarán en el primer request que las necesite.")


def upz_a_localidad_map() -> dict:
    capas_res = _capas()
    return capas_res[9]


def _top_pois_cercanos(capa_gdf, punto_metrico, nombre_col, radio_m=700, max_n=3):
    """Retorna hasta max_n POIs más cercanos dentro de radio_m metros.
    Devuelve lista de dicts {nombre, distancia_m}."""
    if capa_gdf is None or capa_gdf.empty:
        return []
    try:
        dists = capa_gdf.distance(punto_metrico)
        cercanos = dists[dists <= radio_m].nsmallest(max_n)
        resultado = []
        for idx, dist in cercanos.items():
            nombre = None
            for col in [nombre_col, 'nombre', 'NOMBRE', 'name', 'Name']:
                val = capa_gdf.loc[idx].get(col) if col else None
                if val and str(val).strip() and str(val).strip().lower() not in ('none', 'nan', ''):
                    nombre = str(val).strip()
                    break
            if not nombre:
                nombre = "Sin nombre"
            resultado.append({"nombre": nombre, "distancia_m": round(float(dist))})
        return resultado
    except Exception:
        return []


def pois_cercanos(lat: float, lon: float, radio_m: int = 700) -> dict:
    """Calcula los POIs más cercanos al punto (lat, lon) por categoría.
    Retorna dict {categoria: [{nombre, distancia_m}]} con hasta 4 POIs por categoría."""
    (
        sitp, tm, ciclo, estratos, col_estrato, localidades, upzs, metro, municipios, _,
        pois_d1_ara, pois_malls, pois_salud, pois_educacion,
        pois_parques, h3_lookup
    ) = _capas()

    punto = gpd.GeoSeries([Point(lon, lat)], crs=CRS_WGS84).to_crs(CRS_METRICO).iloc[0]

    resultado = {}

    # Transporte — TM/Cable/Metro
    tm_cercanos = _top_pois_cercanos(tm, punto, 'nombre', radio_m, 3)
    metro_cercanos = _top_pois_cercanos(metro, punto, 'nombre', radio_m, 2)
    sitp_cercanos = _top_pois_cercanos(sitp, punto, 'nombre', radio_m, 3)
    resultado['Transporte BRT / Cable'] = tm_cercanos
    resultado['Transporte Metro'] = metro_cercanos
    resultado['Transporte SITP'] = sitp_cercanos

    # Comercio
    resultado['Hard Discount (D1/Ara)'] = _top_pois_cercanos(pois_d1_ara, punto, 'nombre', radio_m, 3)
    resultado['Centros Comerciales'] = _top_pois_cercanos(pois_malls, punto, 'nombre', radio_m, 3)

    # Salud
    resultado['Salud'] = _top_pois_cercanos(pois_salud, punto, 'nombre', radio_m, 3)

    # Educación
    resultado['Educacion'] = _top_pois_cercanos(pois_educacion, punto, 'nombre', radio_m, 3)

    # Parques
    resultado['Parques'] = _top_pois_cercanos(pois_parques, punto, 'nombre', radio_m * 1.5, 3)

    # Filtrar categorías vacías
    return {k: v for k, v in resultado.items() if v}


def enriquecer_inmueble(lat: float, lon: float) -> dict:
    """
    Enriquece un punto geográfico con datos del hexágono H3 y contexto espacial.

    FAST PATH (~1ms): si el punto cae en un hexágono del GeoJSON maestro, todos
    los valores (distancias, estrato, localidad, UPZ) se leen directamente del
    h3_lookup en memoria — sin GeoPandas, sin .distance().min(), sin overlays.
    El error máximo es la mitad del diámetro del hexágono res-9 (~87m), aceptable
    para el scoring geoespacial.

    FALLBACK (~5s): si el punto no está cubierto por el H3 (municipios de
    Cundinamarca fuera de Bogotá urbana), se calculan los valores con GeoPandas
    — más lento pero correcto para cualquier coordenada.
    """
    (
        sitp, tm, ciclo, estratos, col_estrato, localidades, upzs, metro, municipios, _,
        pois_d1_ara, pois_malls, pois_salud, pois_educacion,
        pois_parques, h3_lookup
    ) = _capas()

    h3_index = h3.latlng_to_cell(lat, lon, 9)
    h3_data  = h3_lookup.get(h3_index)

    if h3_data:
        # ── FAST PATH ────────────────────────────────────────────────────────
        # Todas las distancias y atributos del sector vienen del hexágono
        # precomputado. Las columnas val_* contienen metros reales al POI más
        # cercano para el centroide del hexágono.
        # Mapeo explícito de nombre en GeoJSON → nombre usado internamente:
        #   val_dist_brt  → dist_tm  (BRT = Bus Rapid Transit = TransMilenio)
        return {
            "h3_index":             h3_index,
            "h3_data":              h3_data,
            "dist_sitp":            h3_data.get("val_dist_sitp"),
            "dist_tm":              h3_data.get("val_dist_brt"),
            "dist_ciclo":           h3_data.get("val_dist_ciclo"),
            "dist_metro":           h3_data.get("val_dist_metro"),
            "dist_d1_ara":          h3_data.get("val_dist_d1_ara"),
            "dist_centro_comercial":h3_data.get("val_dist_centro_comercial"),
            "dist_hospital":        h3_data.get("val_dist_hospital"),
            "dist_colegio":         h3_data.get("val_dist_colegio"),
            "estrato_promedio_200m":h3_data.get("estrato_promedio_200m"),
            "localidad":            h3_data.get("localidad"),
            "upz":                  h3_data.get("upz"),
            # Si el H3 no tiene campo 'municipio' (solo cubre Bogotá urbana),
            # el municipio es Bogotá D.C. por definición de cobertura.
            "municipio":            h3_data.get("municipio") or "Bogotá D.C.",
        }

    # ── FALLBACK: fuera de la cobertura del H3 ───────────────────────────────
    # Inmuebles en Chía, La Calera u otros municipios de Cundinamarca donde el
    # GeoJSON maestro no tiene hexágonos. Se calculan los valores directamente.
    punto = gpd.GeoSeries([Point(lon, lat)], crs=CRS_WGS84).to_crs(CRS_METRICO).iloc[0]

    dist_sitp  = float(round(sitp.distance(punto).min(), 1))
    dist_tm    = float(round(tm.distance(punto).min(), 1))
    dist_ciclo = float(round(ciclo.distance(punto).min(), 1))
    dist_metro = float(round(metro.distance(punto).min(), 1))

    dist_d1_ara           = float(round(pois_d1_ara.distance(punto).min(), 1)) if pois_d1_ara is not None and not pois_d1_ara.empty else None
    dist_centro_comercial = float(round(pois_malls.distance(punto).min(), 1)) if pois_malls is not None and not pois_malls.empty else None
    dist_hospital         = float(round(pois_salud.distance(punto).min(), 1)) if pois_salud is not None and not pois_salud.empty else None
    dist_colegio          = float(round(pois_educacion.distance(punto).min(), 1)) if pois_educacion is not None and not pois_educacion.empty else None

    loc_match  = localidades[localidades.contains(punto)]
    localidad  = str(loc_match.iloc[0]['LOCNOMBRE']).strip() if not loc_match.empty else None

    upz_match  = upzs[upzs.contains(punto)]
    upz        = str(upz_match.iloc[0]['NOMBRE']).strip() if not upz_match.empty else None

    mpio_match = municipios[municipios.contains(punto)]
    municipio  = str(mpio_match.iloc[0]['MPIO_CNMBR']).strip().title() if not mpio_match.empty else None

    buffer_geom  = punto.buffer(200)
    buffer_gdf   = gpd.GeoDataFrame({'geometry': [buffer_geom]}, crs=CRS_METRICO)
    interseccion = gpd.overlay(estratos, buffer_gdf, how='intersection')
    if col_estrato and not interseccion.empty:
        interseccion = interseccion[interseccion[col_estrato].isin([1, 2, 3, 4, 5, 6])]

    estrato_promedio = None
    if not interseccion.empty:
        interseccion = interseccion.copy()
        interseccion['area'] = interseccion.geometry.area
        total = interseccion['area'].sum()
        if total > 0:
            estrato_promedio = float(round(
                (interseccion[col_estrato] * interseccion['area']).sum() / total, 2
            ))

    return {
        "h3_index":             h3_index,
        "h3_data":              None,
        "dist_sitp":            dist_sitp,
        "dist_tm":              dist_tm,
        "dist_ciclo":           dist_ciclo,
        "dist_metro":           dist_metro,
        "dist_d1_ara":          dist_d1_ara,
        "dist_centro_comercial":dist_centro_comercial,
        "dist_hospital":        dist_hospital,
        "dist_colegio":         dist_colegio,
        "estrato_promedio_200m":estrato_promedio,
        "localidad":            localidad,
        "upz":                  upz,
        "municipio":            municipio,
    }


def verificar_ubicacion_rapida(lat: float, lon: float) -> dict:
    """Verifica la ubicación de un punto usando solo H3 lookup + point-in-polygon
    para UPZ y municipio. NO calcula distancias a capas de transporte/comercio.

    ~1-5ms vs ~5s de enriquecer_inmueble completo.

    Se usa como pre-filtro en busqueda.py para descartar anuncios fuera de las
    UPZ o municipios pedidos ANTES de gastar tiempo en el enriquecimiento completo.

    Retorna: {"upz": str|None, "municipio": str|None, "localidad": str|None, "h3_index": str|None}
    """
    try:
        (
            _sitp, _tm, _ciclo, _estratos, _col_estrato, localidades, upzs, _metro, municipios, _,
            _pois_d1_ara, _pois_malls, _pois_salud, _pois_educacion,
            _pois_parques, h3_lookup
        ) = _capas()

        punto = gpd.GeoSeries([Point(lon, lat)], crs=CRS_WGS84).to_crs(CRS_METRICO).iloc[0]

        # H3 lookup (O(1), instantáneo)
        h3_index = h3.latlng_to_cell(lat, lon, 9)
        h3_data = h3_lookup.get(h3_index, {})

        # Si el H3 lookup ya tiene upz/municipio guardados, usarlos directamente
        upz = h3_data.get("upz") if h3_data else None
        municipio_from_h3 = h3_data.get("municipio") if h3_data else None

        # Fallback: point-in-polygon solo si el H3 no tiene datos (solo para zonas no cubiertas)
        if not upz:
            upz_match = upzs[upzs.contains(punto)]
            upz = str(upz_match.iloc[0]['NOMBRE']).strip() if not upz_match.empty else None

        loc_match = localidades[localidades.contains(punto)]
        localidad = str(loc_match.iloc[0]['LOCNOMBRE']).strip() if not loc_match.empty else None

        if not municipio_from_h3:
            mpio_match = municipios[municipios.contains(punto)]
            municipio_from_h3 = str(mpio_match.iloc[0]['MPIO_CNMBR']).strip().title() if not mpio_match.empty else None

        return {
            "upz": upz,
            "localidad": localidad,
            "municipio": municipio_from_h3,
            "h3_index": h3_index,
        }
    except Exception as e:
        print(f"[verificar_ubicacion_rapida] Error: {e}")
        return {"upz": None, "localidad": None, "municipio": None, "h3_index": None}




def run_analysis(input_csv, output_csv, log_callback=print):
    """
    Punto de entrada reutilizable para el analisis espacial.
    Puede llamarse desde app.py despues del scraping o ejecutarse manualmente.
    """
    if not os.path.exists(input_csv):
        log_callback(f'Error: no se encuentra {input_csv}', 'error')
        return False

    log_callback('Analisis espacial: leyendo dataset...', 'info')
    df = pd.read_csv(input_csv, sep=';', decimal=',', encoding='utf-8-sig')
    df = df.dropna(subset=['Latitud', 'Longitud'])

    geometry = [Point(xy) for xy in zip(df['Longitud'], df['Latitud'])]
    gdf = gpd.GeoDataFrame(df, crs=CRS_WGS84, geometry=geometry).to_crs(CRS_METRICO)

    log_callback('Analisis espacial: cargando capas geograficas...', 'info')
    sitp, tm, ciclo, estratos, col_estrato, *_ = _cargar_capas()

    log_callback('Analisis espacial: calculando distancias a transporte...', 'info')
    gdf = _calcular_distancias(gdf, sitp, tm, ciclo)

    log_callback('Analisis espacial: calculando estrato ponderado (200m)...', 'info')
    gdf = _calcular_estrato_promedio(gdf, estratos, col_estrato)

    final_df = pd.DataFrame(gdf.drop(columns=['geometry']))
    final_df.to_csv(output_csv, sep=';', decimal=',', encoding='utf-8-sig', index=False)

    log_callback(f'Analisis espacial completado. Dataset enriquecido guardado.', 'ok')
    return True


if __name__ == '__main__':
    input_path  = os.path.join(BASE_DIR, 'dataset_fincaraiz.csv')
    output_path = os.path.join(BASE_DIR, 'dataset_enriquecido.csv')
    run_analysis(input_path, output_path)
