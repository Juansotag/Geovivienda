import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEO_DIR  = os.path.join(BASE_DIR, 'static', 'geo')

CRS_METRICO = 'EPSG:3116'
CRS_WGS84   = 'EPSG:4326'


def _cargar_capas():
    sitp     = gpd.read_file(os.path.join(GEO_DIR, 'estaciones_sitp.geojson')).to_crs(CRS_METRICO)
    tm       = gpd.read_file(os.path.join(GEO_DIR, 'estaciones_tm.geojson')).to_crs(CRS_METRICO)
    ciclo    = gpd.read_file(os.path.join(GEO_DIR, 'cliclorutas.geojson')).to_crs(CRS_METRICO)
    estratos = gpd.read_file(os.path.join(GEO_DIR, 'estratos.geojson')).to_crs(CRS_METRICO)

    col_estrato = next((c for c in estratos.columns if c.lower() == 'estrato'), None)
    if col_estrato:
        estratos[col_estrato] = pd.to_numeric(estratos[col_estrato], errors='coerce')
        estratos = estratos.dropna(subset=[col_estrato])

    return sitp, tm, ciclo, estratos, col_estrato


def _calcular_distancias(gdf, sitp, tm, ciclo):
    def min_dist(point, ref):
        return ref.distance(point).min()

    gdf['dist_sitp']  = gdf.geometry.apply(lambda x: min_dist(x, sitp))
    gdf['dist_tm']    = gdf.geometry.apply(lambda x: min_dist(x, tm))
    gdf['dist_ciclo'] = gdf.geometry.apply(lambda x: min_dist(x, ciclo))
    return gdf


def _calcular_estrato_promedio(gdf, estratos, col_estrato):
    """
    Calcula el estrato promedio ponderado por area dentro de un radio de 200m.
    Solo se consideran poligonos con estrato 1-6 (zonas residenciales).
    El denominador es unicamente la suma de las areas estratificadas.
    """
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
    sitp, tm, ciclo, estratos, col_estrato = _cargar_capas()

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
