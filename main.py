import pandas as pd
from extractor_links import extraer_links_fincaraiz
from extractor_detalles import procesar_lista_links

def main():
    print("="*60)
    print("Iniciando Pipeline de Extracción de Datos - GeoVivienda")
    print("="*60)
    
    # 1. Parámetros de búsqueda para la recolección de URLs
    # Puedes modificar estos parámetros libremente según la búsqueda que requieras.
    links_obtenidos = extraer_links_fincaraiz(
        paginas_a_extraer=2,                  # Cantidad de páginas de resultados a scrapear
        operacion="venta",                    
        tipos_inmueble=["apartamento", "casa"], 
        ubicacion="bogota/bogota-dc",
        habitaciones="2-o-mas",     
        banos="2-o-mas",                    
        con_balcon=True,            
        con_ascensor=True,          
        extras=[],                            # Ej: ["gimnasio", "zona-bbq"]
        # parqueaderos=1,             
        estado="usados",                      # "todos", "nuevos", "usados", etc.
        precio_min=250000000,       
        precio_max=350000000,       
        antiguedad="de-1-a-8-anios",          
        estratos=[3]             
    )
    
    if not links_obtenidos:
        print("\nNo se encontraron URLs con los parámetros dados. Abortando proceso.")
        return
        
    print(f"\nFase 1 completada: {len(links_obtenidos)} URLs de inmuebles identificadas.")
    print("="*60)
    
    # 2. Extracción profunda de detalles por cada URL
    # Convertimos el `set` que nos retorna extractor_links a `list` 
    lista_links = list(links_obtenidos)
    
    # Configurar de salida
    archivo_csv = "dataset_fincaraiz.csv"
    
    # Llamamos a extraer los detalles y exportar
    df_propiedades = procesar_lista_links(lista_links, archivo_salida=archivo_csv)
    
    print("="*60)
    if not df_propiedades.empty:
        print(f"¡Pipeline finalizado con éxito! {len(df_propiedades)} inmuebles guardados.")
        print(f"Archivo resultante: {archivo_csv}")
    else:
        print("Hubo un problema al procesar los detalles. Revisa los mensajes de error.")

if __name__ == "__main__":
    main()
