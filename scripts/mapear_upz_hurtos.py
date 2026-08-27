import pandas as pd
import geopandas as gpd
import unicodedata
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_GEO_DIR = os.path.join(BASE_DIR, 'static', 'geo', 'bogota')
GEODATA_DIR = os.path.join(BASE_DIR, 'geodata', 'bogota')

def normalize(text):
    if not text or pd.isna(text): return ''
    text = str(text).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

upzs_geo = gpd.read_file(os.path.join(STATIC_GEO_DIR, 'upz.geojson'))
df_hurto = pd.read_csv(os.path.join(GEODATA_DIR, 'seguridad', 'crimen', 'hurto.csv'), sep=';', encoding='utf-8-sig')

geo_names = upzs_geo['NOMBRE'].dropna().unique().tolist()
hurto_upzs = df_hurto['UPZ'].dropna().unique().tolist()
hurto_norm_map = {normalize(u): u for u in hurto_upzs}

print(f"Total UPZs en static/geo/upz.geojson: {len(geo_names)}")
print(f"Total UPZs en hurto.csv: {len(hurto_upzs)}")

manual_alias = {
    "USAQUEN": "USAQUEN",
    "LOS CEDROS": "CEDROS",
    "TOBERON": "TOBERIN",
    "RINCON DE SUBA": "EL RINCON",
    "USME - ENTRENUBES": "PARQUE ENTRENUBES",
    "CERROS ORIENTALES": "SAN ISIDRO - PATIOS",
    "CUENCA DEL TUNJUELO": "TUNJUELITO",
    "SAN CRISTOBAL": "SAN CRISTOBAL NORTE",
    "ARBORIZADORA": "ARBORIZADORA",
    "BRITALIA": "BRITALIA",
    "PORVENIR": "EL PORVENIR",
}

mapped_dict = {}
for name in geo_names:
    norm = normalize(name)
    if norm in hurto_norm_map:
        mapped_dict[name] = hurto_norm_map[norm]
        print(f"EXACT MATCH: '{name}' -> '{hurto_norm_map[norm]}'")
    elif norm in manual_alias and normalize(manual_alias[norm]) in hurto_norm_map:
        real_csv = hurto_norm_map[normalize(manual_alias[norm])]
        mapped_dict[name] = real_csv
        print(f"ALIAS MATCH: '{name}' -> '{real_csv}'")
    else:
        # Fuzzy / substring match
        candidates = [h for h in hurto_upzs if normalize(h) in norm or norm in normalize(h)]
        if candidates:
            mapped_dict[name] = candidates[0]
            print(f"FUZZY MATCH: '{name}' -> '{candidates[0]}'")
        else:
            print(f"!!! HOLE DETECTED: '{name}' HAS NO MATCH IN HURTO.CSV !!!")

print("\n--- RESUMEN DE COBERTURA ---")
print(f"Total Mapeadas: {len(mapped_dict)} / {len(geo_names)}")
