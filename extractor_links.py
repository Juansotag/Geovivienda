import sys
import subprocess

# Módulo de funciones para extración de links
from selenium import webdriver  
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re

def construir_url_fincaraiz(operacion, tipos_inmueble, ubicacion="bogota/bogota-dc", 
                            habitaciones=None, banos=None, con_balcon=False, con_ascensor=False, 
                            extras=None, parqueaderos=None, estado=None, precio_min=None, 
                            precio_max=None, antiguedad=None, estratos=None):
    """
    Función interna que construye la URL de búsqueda.
    (Ver la documentación de `extraer_links_fincaraiz` para el detalle de todas las opciones y parámetros).
    """
    # Mapeo de términos singulares proporcionados por el usuario a la sintaxis plural (y guiones) de FincaRaíz
    mapa_plurales = {
        'casa': 'casas',
        'apartamento': 'apartamentos',
        'apartaestudio': 'apartaestudios',
        'cabaña': 'cabanas',
        'casa campestre': 'casas-campestres',
        'casa lote': 'casas-lote',
        'finca': 'fincas',
        'habitacion': 'habitaciones',
        'lote': 'lotes',
        'bodega': 'bodegas',
        'consultorio': 'consultorios',
        'local': 'locales',
        'oficina': 'oficinas',
        'parqueadero': 'parqueaderos',
        'edificio': 'edificios'
    }
    
    # Estandarizar operación
    operacion = operacion.lower().strip()
    if operacion not in ['venta', 'arriendo', 'proyectos']:
        operacion = 'arriendo' # Default por seguridad
        
    # Estandarizar y pluralizar los tipos de inmueble
    tipos_url = []
    for tipo in tipos_inmueble:
        tipo_limpio = tipo.lower().strip()
        # Buscar en el mapa, y si por error pasan algo no mapeado, usarlo tal cual reemplazando espacios por guiones
        tipos_url.append(mapa_plurales.get(tipo_limpio, tipo_limpio.replace(' ', '-')))
        
    # Unir con "-y-" como requiere FincaRaíz
    segmento_inmuebles = "-y-".join(tipos_url)
    
    # Si la lista estaba vacía por error, poner un genérico
    if not segmento_inmuebles:
        segmento_inmuebles = "casas-y-apartamentos"
        
    url_base = f"https://www.fincaraiz.com.co/{operacion}/{segmento_inmuebles}/{ubicacion}"
    
    # -----------------------------
    # Agregar variables de Ruta (Patrones jerárquicos)
    # -----------------------------
    path_extras = ""
    
    if habitaciones is not None:
        hab_str = str(habitaciones)
        if "habitaciones" not in hab_str:
            hab_str += "-habitaciones"
        path_extras += f"/{hab_str}"
        
    if banos is not None:
        banos_str = str(banos)
        if "banos" not in banos_str and "baños" not in banos_str:
            banos_str += "-banos"
        # Limpiar por si escriben "baños" con eñe
        banos_str = banos_str.replace("baños", "banos")
        path_extras += f"/{banos_str}"
        
    # Variables de extras/amenidades (FincaRaíz las encadena con '-y-')
    segmento_extras = []
    if con_balcon:
        segmento_extras.append("con-balcon")
    if con_ascensor:
        segmento_extras.append("con-ascensor")
        
    if extras:
        for ex in extras:
            ex_str = ex.lower().strip().replace(" ", "-")
            # Si el usuario no le puso "con-" se lo agregamos para ajustarse a FincaRaiz
            if not ex_str.startswith("con-") and not ex_str.startswith("sin-"):
                ex_str = f"con-{ex_str}"
            segmento_extras.append(ex_str)
            
    if segmento_extras:
        path_extras += f"/{'-y-'.join(segmento_extras)}"
        
    if parqueaderos is not None:
        parq_str = str(parqueaderos).strip()
        if "parqueadero" not in parq_str:
            parq_str = f"{parq_str}-parqueadero" if parq_str == "1" else f"{parq_str}-parqueaderos"
        path_extras += f"/{parq_str}"
        
    if estado and estado.lower() != "todos": # Ej: usados, nuevos, sobre-planos, en-construccion
        path_extras += f"/{estado.lower().strip()}"
        
    if precio_min is not None:
        path_extras += f"/desde-{int(precio_min)}"
        
    if precio_max is not None:
        path_extras += f"/hasta-{int(precio_max)}"
        
    if antiguedad and antiguedad.lower() != "todos" and antiguedad.lower() != "todas":
        # Por si el usuario mete acentos o eñes, las URLs de FincaRaiz suelen usar 'anios' o no lo requieren literal
        # Ej esperado: menor-a-1-anio, de-1-a-8-anios, de-9-a-15-anios, de-16-a-30-anios, mas-de-30-anios
        antiguedad_str = antiguedad.lower().strip().replace('años', 'anios').replace('año', 'anio')
        path_extras += f"/{antiguedad_str}"
        
    url_completa = url_base + path_extras
    
    # -----------------------------
    # Agregar variables de Query (?var=val)
    # -----------------------------
    query_params = ["IDmoneda=4"] # Fijo para representar pesos colombianos
    
    if estratos:
        for estrato in estratos:
            query_params.append(f"stratum[]={estrato}")
            
    if query_params:
        url_completa += "?" + "&".join(query_params)
        
    return url_completa

def configurar_driver():
    """
    Configura y retorna el driver de Selenium con opciones básicas.
    """
    opts = Options()
    opts.add_argument("--start-maximized")
    # Si en el futuro no quieres ver el navegador abriéndose, descomenta la siguiente línea:
    # opts.add_argument("--headless")
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )
    return driver

def extraer_links_fincaraiz(paginas_a_extraer=2, operacion="venta", tipos_inmueble=["casa", "apartamento"], 
                            ubicacion="bogota/bogota-dc", habitaciones=None, banos=None, 
                            con_balcon=False, con_ascensor=False, extras=None, 
                            parqueaderos=None, estado=None, precio_min=None, 
                            precio_max=None, antiguedad=None, estratos=None):
    """
    Extrae los enlaces de inmuebles validos de Finca Raíz iterando página por página automáticamente.
    
    === PARÁMETROS BÁSICOS ===
    :param paginas_a_extraer: (int) Número de páginas a scrapear para la búsqueda (Ej: 2, 10).
    :param operacion: (str) El tipo de negocio. Opciones: "venta", "arriendo", "proyectos".
    :param tipos_inmueble: (list) Lista de strings. Opciones válidas: "casa", "apartamento", "apartaestudio", 
                           "cabaña", "casa campestre", "casa lote", "finca", "habitacion", "lote", "bodega", 
                           "consultorio", "local", "oficina", "parqueadero", "edificio".
    :param ubicacion: (str) Estructura de la web "municipio/zona" o "municipio". Ej: "bogota/bogota-dc".
    
    === PARÁMETROS OPCIONALES DEL INMUEBLE ===
    :param habitaciones: (int/str) Ej: 2, u opciones textuales como: "1-o-mas", "2-o-mas", "3-o-mas".
    :param banos: (int/str) Ej: 2, u opciones textuales como: "1-o-mas", "2-o-mas", "3-o-mas".
    :param con_balcon: (bool) True para exigir balcón.
    :param con_ascensor: (bool) True para exigir ascensor.
    :param extras: (list) Lista de strings con otros extras textuales. Ej: ["gimnasio", "zona-bbq"]. El 
                   código les añadirá el prefijo "con-" automáticamente si es necesario.
    :param parqueaderos: (int) Número de parqueaderos deseado. Ej: 1, 2.
    
    === PARÁMETROS OPCIONALES FINANCIEROS Y DE ESTADO ===
    :param estado: (str) Opciones válidas: "todos", "sobre-planos", "en-construccion", "nuevos", "usados".
    :param precio_min: (int) Precio mínimo deseado en COP. Ej: 300000000.
    :param precio_max: (int) Precio máximo deseado en COP. Ej: 500000000.
    :param antiguedad: (str) Opciones textuales válidas: "todos", "menor-a-1-anio", "de-1-a-8-anios", 
                       "de-9-a-15-anios", "de-16-a-30-anios", "mas-de-30-anios".
    :param estratos: (list) Lista de estratos numéricos aceptados. Ej: [2, 3, 4].
    
    :return: (list) Lista de strings correspondientes a los links únicos encontrados de todas las páginas visitadas.
    """
    url_base = construir_url_fincaraiz(
        operacion=operacion,
        tipos_inmueble=tipos_inmueble,
        ubicacion=ubicacion,
        habitaciones=habitaciones,
        banos=banos,
        con_balcon=con_balcon,
        con_ascensor=con_ascensor,
        extras=extras,
        parqueaderos=parqueaderos,
        estado=estado,
        precio_min=precio_min,
        precio_max=precio_max,
        antiguedad=antiguedad,
        estratos=estratos
    )
    print(f"URL Base generada internamente: {url_base}")

    driver = configurar_driver()
    links_dataset = set()
    
    try:
        for j in range(1, paginas_a_extraer + 1):
            print(f"\n--- Procesando página {j} ---")
            
            # 1. Navegar gestionando la paginación mediante la URL en vez de clics
            # Esto evita que el DOM colapse o se desincronice (común después de la página 3 en SPAs)
            if j == 1:
                url_actual = url_base
            else:
                # En FincaRaiz el formato correcto de paginación es /paginaX ANTES de los query params
                if "?" in url_base:
                    base_path, query_str = url_base.split("?", 1)
                    url_actual = f"{base_path.rstrip('/')}/pagina{j}?{query_str}"
                else:
                    url_actual = f"{url_base.rstrip('/')}/pagina{j}"
                
            driver.get(url_actual)
            
            # 2. Breve pausa antes de empezar a scrollear
            time.sleep(2)
            
            # 3. Hacer scroll progresivo como el que tenías originalmente
            # FincaRaíz usa lazy loading muy agresivo que se rompe si saltas directo al final
            intentos_scroll = 30
            step_scroll = 300
            for i in range(intentos_scroll):
                driver.execute_script(f"window.scrollBy(0, {step_scroll});")
                time.sleep(0.1) # Pequeña pausa para que renderice
            
            # Dar un tiempo extra final
            time.sleep(1)
            
            # 4. Buscamos TODOS los enlaces 'a' que tengan un 'href'
            elementos_a = driver.find_elements(By.TAG_NAME, "a")
            
            anuncios_encontrados = 0
            for elemento in elementos_a:
                try:
                    link = elemento.get_attribute("href")
                    if not link:
                        continue
                        
                    # Los verdaderos anuncios de Finca Raiz siempre terminan en el ID de la propiedad
                    # Ejemplo: /apartamento-en-arriendo-en-el-chico-bogota/193363100
                    # Filtramos si el último segmento de la URL es un número grande (ID)
                    partes_url = link.rstrip('/').split('/')
                    if partes_url and partes_url[-1].isdigit() and len(partes_url[-1]) > 5:
                        
                        # Evitamos basura o links de agencias
                        if any(x in link for x in ["facebook.com", "twitter.com", "whatsapp.com", "/inmobiliarias/"]):
                            continue
                            
                        # Si es un link válido de anuncio
                        if link not in links_dataset:
                            links_dataset.add(link)
                            anuncios_encontrados += 1
                            print(f"Propiedad encontrada: {link}")
                except Exception as e:
                    pass
            
            print(f"Anuncios únicos encontrados en página {j}: {anuncios_encontrados}")
            print(f"Total acumulado: {len(links_dataset)}")
            
            # Pausa breve por cortesía al servidor y evitar bloqueos
            time.sleep(3)
            
    except Exception as e:
        print(f"Error general durante el scraping: {e}")
    finally:
        print(f"\nExtracción finalizada. Total de links recolectados: {len(links_dataset)}")
        driver.quit()
        
    return list(links_dataset)


