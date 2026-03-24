import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import subprocess
import sys
import re
import os

# Módulo de funciones para extraer detalles de FincaRaíz

def configurar_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.page_load_strategy = 'eager' # No esperar a que carguen imágenes y CSS
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(15) # Máximo 15 segundos de espera por página
    return driver

def extraer_detalles_inmueble(html_source, url_referencia=""):
    """
    Recibe el código HTML crudo y extrae las variables del inmueble mediante selectores CSS.
    """
    soup = BeautifulSoup(html_source, "html.parser")
    detalles = {
        "URL": url_referencia,
        "Precio_Venta": None,
        "Administracion": None,
        "Habitaciones": None,
        "Banos": None,
        "Area_Metros": None,
        "Ubicacion": None,
        "Tipo_Inmueble": None,
        "Estado": None,
        "Antiguedad": None,
        "Parqueaderos": None,
        "Area_Construida": None,
        "Area_Privada": None,
        "Estrato": None,
        "Piso_Nro": None,
        "Cantidad_Pisos": None,
        "Comodidades": "",
        "Descripcion": None,
        "Codigo_FincaRaiz": None,
        "Latitud": "",
        "Longitud": ""
    }
    
    def limpiar_entero(texto):
        if not texto: return None
        if "incluid" in str(texto).lower(): return 0
        nums = re.sub(r'[^\d]', '', str(texto))
        return int(nums) if nums else None

    def limpiar_decimal(texto):
        if not texto: return None
        # Mantiene números y comas/puntos
        match = re.search(r'[\d,.]+', str(texto))
        if match:
            # Reemplazar siempre comas por puntos para que Python lo acepte como float
            num_str = match.group(0).replace(',', '.')
            partes = num_str.split('.')
            if len(partes) > 2:
                # Si hay multiples puntos, unimos todos menos el último (ej 1.200.50 -> 1200.50)
                num_str = ''.join(partes[:-1]) + '.' + partes[-1]
            try:
                val = float(num_str)
                return int(val) if val.is_integer() else val
            except ValueError:
                return num_str
        return None
    
    # 1. PRECIO VENTA
    precio_tag = soup.find("p", class_="main-price")
    if precio_tag:
        detalles["Precio_Venta"] = limpiar_entero(precio_tag.text)
        
    # 2. ADMINISTRACION
    admin_tag = soup.find("span", class_="commonExpenses")
    if admin_tag:
        detalles["Administracion"] = limpiar_entero(admin_tag.text)
        
    # 3. TÍTULO / HABITACIONES / BAÑOS / AREA BASE (Tarjetas de resumen top)
    tags_resumen = soup.find_all("div", class_="typology-item-container")
    for t in tags_resumen:
        texto = t.text.lower()
        if "hab" in texto:
            detalles["Habitaciones"] = limpiar_entero(t.text)
        elif "baño" in texto or "bano" in texto:
            detalles["Banos"] = limpiar_entero(t.text)
        elif "m²" in texto or "m2" in texto:
            detalles["Area_Metros"] = limpiar_decimal(t.text)
            
    # 4. UBICACIÓN
    loc_tag = soup.find("span", class_="property-location-tag")
    if loc_tag:
        ps = loc_tag.find_all("p")
        detalles["Ubicacion"] = " | ".join([p.text.strip() for p in ps])
        
    # 5. DETALLES DE LA PROPIEDAD (Mesa de especificaciones inferior)
    hoja_tecnica = soup.find("div", class_="technical-sheet")
    if hoja_tecnica:
        filas = hoja_tecnica.find_all("div", class_="ant-row")
        for fila in filas:
            cols = fila.find_all("div", class_="ant-col")
            if len(cols) >= 3:
                llave = cols[0].text.replace("•", "").strip()
                valor = cols[-1].text.strip()
                
                llave_lower = llave.lower()
                if "tipo de inmueble" in llave_lower: detalles["Tipo_Inmueble"] = valor
                elif "estado" in llave_lower: detalles["Estado"] = valor
                elif "antigüedad" in llave_lower: detalles["Antiguedad"] = valor
                elif "parqueaderos" in llave_lower: detalles["Parqueaderos"] = limpiar_entero(valor)
                elif "área construida" in llave_lower or "area construida" in llave_lower: detalles["Area_Construida"] = limpiar_decimal(valor)
                elif "área privada" in llave_lower or "area privada" in llave_lower: detalles["Area_Privada"] = limpiar_decimal(valor)
                elif "estrato" in llave_lower: detalles["Estrato"] = limpiar_entero(valor)
                elif "piso n°" in llave_lower or "piso n" in llave_lower: detalles["Piso_Nro"] = limpiar_entero(valor)
                elif "cantidad de pisos" in llave_lower: detalles["Cantidad_Pisos"] = limpiar_entero(valor)

    # Validaciones cruzadas para Habitaciones/Baños si no se hallaron arriba
    if detalles["Banos"] is None and hoja_tecnica:
        for fila in filas:
            cols = fila.find_all("div", class_="ant-col")
            if len(cols) >= 3 and "baños" in cols[0].text.lower(): detalles["Banos"] = limpiar_entero(cols[-1].text)
    if detalles["Habitaciones"] is None and hoja_tecnica:
        for fila in filas:
            cols = fila.find_all("div", class_="ant-col")
            if len(cols) >= 3 and "habitaciones" in cols[0].text.lower(): detalles["Habitaciones"] = limpiar_entero(cols[-1].text)
            
    # 6. COMODIDADES (Servicios adicionales unidos por coma)
    fac_div = soup.find("div", class_="property-facilities")
    if fac_div:
        items = fac_div.find_all("span", class_="ant-typography")
        comodidades = [i.text.strip() for i in items if "•" not in i.text and i.text.strip()]
        detalles["Comodidades"] = ", ".join(comodidades)
            
    # 7. DESCRIPCIÓN 
    desc_tag = soup.find("div", class_="property-description")
    if desc_tag:
        detalles["Descripcion"] = desc_tag.text.strip()
        
    # 8. CÓDIGO FINCARAÍZ
    codigo_tags = soup.find_all("span")
    for st in codigo_tags:
        if "Código Fincaraíz:" in st.text:
            detalles["Codigo_FincaRaiz"] = st.text.replace("Código Fincaraíz:", "").strip()
            break
            
    # 9. LATITUD Y LONGITUD (Geoespacial desde JSON-LD en el DOM)
    try:
        lat_match = re.search(r'["\']?latitude["\']?\s*:\s*([-0-9.]+)', html_source, re.IGNORECASE)
        lon_match = re.search(r'["\']?longitude["\']?\s*:\s*([-0-9.]+)', html_source, re.IGNORECASE)
        
        if lat_match:
            detalles["Latitud"] = float(lat_match.group(1))
        if lon_match:
            detalles["Longitud"] = float(lon_match.group(1))
    except Exception as e:
        print(f"Error extrayendo lat/long para {url_referencia}: {e}")
            
    return detalles

def procesar_lista_links(lista_urls, archivo_salida="datos_propiedades.csv"):
    """
    Controlador principal: itera sobre una lista de URLs, scrapea y exporta
    los resultados concatenándolos a un CSV existente y evitando duplicados.
    """
    columnas_ordenadas = [
        "URL", "Codigo_FincaRaiz", "Tipo_Inmueble", "Estado", "Precio_Venta", "Administracion", 
        "Ubicacion", "Estrato", "Area_Metros", "Area_Construida", "Area_Privada", 
        "Habitaciones", "Banos", "Parqueaderos", "Antiguedad", "Piso_Nro", 
        "Cantidad_Pisos", "Comodidades", "Descripcion", "Latitud", "Longitud"
    ]
    
    # 1. Cargar archivo existente si lo hay para evitar duplicados
    urls_existentes = set()
    df_existente = None
    if os.path.exists(archivo_salida):
        try:
            df_existente = pd.read_csv(archivo_salida, sep=";", decimal=",", encoding="utf-8-sig")
            if "URL" in df_existente.columns:
                urls_existentes = set(df_existente["URL"].dropna().tolist())
                print(f"Archivo previo detectado con {len(urls_existentes)} propiedades guardadas.")
        except Exception as e:
            print(f"No se pudo cargar el archivo existente: {e}")
            
    # 2. Filtrar los enlaces que ya fueron procesados previamente
    urls_a_procesar = [url for url in lista_urls if url not in urls_existentes]
    
    if not urls_a_procesar:
        print("La lista de URLs nuevas está vacía o ya fueron procesadas íntegramente. Abortando extracción.")
        return df_existente if df_existente is not None else pd.DataFrame(columns=columnas_ordenadas)
        
    print(f"\nIniciando extracción detallada de {len(urls_a_procesar)} nuevas propiedades...\n")
    driver = configurar_driver()
    datos = []
    
    try:
        total = len(urls_a_procesar)
        for i, url in enumerate(urls_a_procesar, 1):
            print(f"[{i}/{total}] Procesando: {url}")
            try:
                try:
                    driver.get("about:blank") # Limpiar DOM para evitar heredar datos si falla la red
                    driver.get(url)
                except TimeoutException:
                    print(f"  Página {url} tardó mucho, intentando parsear lo que cargó...")
                    
                # Espera asíncrona extra para asegurar la renderización JS (React/Next)
                time.sleep(3.5) 
                
                html = driver.page_source
                detalle = extraer_detalles_inmueble(html, url)
                datos.append(detalle)
                
            except Exception as e_url:
                print(f"  Error al procesar la URL {url}: {e_url}")
                
            # Retraso amigable antispam
            time.sleep(1.5)
            
    except Exception as e_general:
        print(f"Error crítico en el módulo de extracción: {e_general}")
    finally:
        driver.quit()
        print("\nExtracción finalizada. Cerrando instancia de Chrome.")
        
    df_nuevos = pd.DataFrame(datos)
    
    # Consolidar los datos extraídos
    if not df_nuevos.empty:
        # Asegurar de tener solo columas requeridas
        columnas_finales = [c for c in columnas_ordenadas if c in df_nuevos.columns]
        df_nuevos = df_nuevos[columnas_finales]
        
        # Concatenar con los previamente guardados si existen
        if df_existente is not None and not df_existente.empty:
            df_final = pd.concat([df_existente, df_nuevos], ignore_index=True)
        else:
            df_final = df_nuevos
            
        # Forzar el casting a tipos numéricos, si no, pandas asume strings/objects y omite decimal=","
        cols_numericas = ["Precio_Venta", "Administracion", "Estrato", "Area_Metros", 
                          "Area_Construida", "Area_Privada", "Habitaciones", "Banos", 
                          "Parqueaderos", "Piso_Nro", "Cantidad_Pisos", "Latitud", "Longitud"]
        for col in cols_numericas:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors="coerce")
                
        # Guardar en CSV con formato regional para Excel en Español (punto y coma, decimal en coma)
        df_final.to_csv(archivo_salida, index=False, encoding="utf-8-sig", sep=";", decimal=",")
        print(f"Datos registrados exitosamente a -> {archivo_salida} (Total en base: {len(df_final)})")
        return df_final
    else:
        print("No se logró extraer información nueva.")
        return df_existente if df_existente is not None else pd.DataFrame(columns=columnas_ordenadas)


