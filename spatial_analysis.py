import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEO_DIR  = os.path.join(BASE_DIR, 'static', 'geo')

CRS_METRICO = 'EPSG:3116'
CRS_WGS84   = 'EPSG:4326'


import h3

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

    if os.path.exists(poi_path):
        pois_gdf = gpd.read_file(poi_path).to_crs(CRS_METRICO)
        pois_d1_ara = pois_gdf[pois_gdf['subcategoria'].isin(['hard_discount_d1', 'hard_discount_ara'])]
        pois_malls = pois_gdf[pois_gdf['categoria'] == 'centro_comercial']
        pois_salud = pois_gdf[pois_gdf['categoria'] == 'salud']
        pois_educacion = pois_gdf[pois_gdf['categoria'] == 'educacion']

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

    return (
        sitp, tm, ciclo, estratos, col_estrato, localidades, upzs, metro, municipios,
        upz_a_localidad, pois_d1_ara, pois_malls, pois_salud, pois_educacion
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


def upz_a_localidad_map() -> dict:
    capas_res = _capas()
    return capas_res[9]


def enriquecer_inmueble(lat: float, lon: float) -> dict:
    (
        sitp, tm, ciclo, estratos, col_estrato, localidades, upzs, metro, municipios, _,
        pois_d1_ara, pois_malls, pois_salud, pois_educacion
    ) = _capas()

    punto = gpd.GeoSeries([Point(lon, lat)], crs=CRS_WGS84).to_crs(CRS_METRICO).iloc[0]

    dist_sitp = sitp.distance(punto).min()
    dist_tm = tm.distance(punto).min()
    dist_ciclo = ciclo.distance(punto).min()
    dist_metro = metro.distance(punto).min()

    dist_d1_ara = pois_d1_ara.distance(punto).min() if pois_d1_ara is not None and not pois_d1_ara.empty else None
    dist_centro_comercial = pois_malls.distance(punto).min() if pois_malls is not None and not pois_malls.empty else None
    dist_hospital = pois_salud.distance(punto).min() if pois_salud is not None and not pois_salud.empty else None
    dist_colegio = pois_educacion.distance(punto).min() if pois_educacion is not None and not pois_educacion.empty else None

    # H3 Cell Index (Resolucion 8)
    h3_index = h3.latlng_to_cell(lat, lon, 8)

    # Point-in-polygon para localidad, UPZ y municipio
    loc_match = localidades[localidades.contains(punto)]
    localidad = str(loc_match.iloc[0]['LOCNOMBRE']).strip() if not loc_match.empty else None

    upz_match = upzs[upzs.contains(punto)]
    upz = str(upz_match.iloc[0]['NOMBRE']).strip() if not upz_match.empty else None

    mpio_match = municipios[municipios.contains(punto)]
    municipio = str(mpio_match.iloc[0]['MPIO_CNMBR']).strip().title() if not mpio_match.empty else None

    buffer_geom = punto.buffer(200)
    buffer_gdf = gpd.GeoDataFrame({'geometry': [buffer_geom]}, crs=CRS_METRICO)
    interseccion = gpd.overlay(estratos, buffer_gdf, how='intersection')
    if col_estrato and not interseccion.empty:
        interseccion = interseccion[interseccion[col_estrato].isin([1, 2, 3, 4, 5, 6])]

    estrato_promedio = None
    if not interseccion.empty:
        interseccion = interseccion.copy()
        interseccion['area'] = interseccion.geometry.area
        total = interseccion['area'].sum()
        if total > 0:
            estrato_promedio = float(round((interseccion[col_estrato] * interseccion['area']).sum() / total, 2))

    return {
        "dist_sitp": float(round(dist_sitp, 1)),
        "dist_tm": float(round(dist_tm, 1)),
        "dist_ciclo": float(round(dist_ciclo, 1)),
        "dist_metro": float(round(dist_metro, 1)),
        "dist_d1_ara": float(round(dist_d1_ara, 1)) if dist_d1_ara is not None else None,
        "dist_centro_comercial": float(round(dist_centro_comercial, 1)) if dist_centro_comercial is not None else None,
        "dist_hospital": float(round(dist_hospital, 1)) if dist_hospital is not None else None,
        "dist_colegio": float(round(dist_colegio, 1)) if dist_colegio is not None else None,
        "h3_index": h3_index,
        "estrato_promedio_200m": estrato_promedio,
        "localidad": localidad,
        "upz": upz,
        "municipio": municipio,
    }


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
