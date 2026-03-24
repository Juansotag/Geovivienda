import sys
from extractor_detalles import configurar_driver
import re
import json

print('Iniciando navegador...')
driver = configurar_driver()
driver.get('https://www.fincaraiz.com.co/apartamento-en-venta-en-la-felicidad-bogota/192736494')
import time
time.sleep(5)
html = driver.page_source
driver.quit()
print('Navegador cerrado. HTML obtenido:', len(html), 'bytes')

# 1. Buscando __NEXT_DATA__
match_next = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
if match_next:
    print("ENCONTRADO: script __NEXT_DATA__")
    try:
        data = json.loads(match_next.group(1))
        with open('next_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print("Datos guardados en next_data.json para inspección.")
    except Exception as e:
        print("Error parseando JSON:", e)
else:
    print("NO SE ENCONTRÓ __NEXT_DATA__")

# 2. Buscando cualquier indicio de latitud/longitud
print("\nBuscando rastros textuales de lat/lng...")
matches = re.finditer(r'.{0,40}(?:lat|lng|latitude|longitude|latitud|longitud)[\"\'\s:=]+([-0-9.]+).{0,40}', html, re.IGNORECASE)
found = set()
for m in matches:
    found.add(m.group(0).strip())

for f in found:
    print("->", f)
