import json
import os
import geopandas as gpd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON_PATH = os.path.join(BASE_DIR, 'geodata', 'mapa_h3_bogota.geojson')
HTML_OUTPUT_PATH = os.path.join(BASE_DIR, 'mapa_h3_interactivo.html')

def generar():
    if not os.path.exists(GEOJSON_PATH):
        print("Error: No existe geodata/mapa_h3_bogota.geojson")
        return

    with open(GEOJSON_PATH, encoding='utf-8') as f:
        data_json = json.load(f)

    # Coordenadas centro de Bogotá
    gdf = gpd.read_file(GEOJSON_PATH)
    lat_center = round(float(gdf['lat'].mean()), 4)
    lng_center = round(float(gdf['lng'].mean()), 4)

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Geovivienda - Mapa H3 Interactivo Maestro</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body, html {{ width: 100%; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; overflow: hidden; }}
        #map {{ width: 100%; height: 100vh; background: #eef2f6; }}
        
        .control-panel {{
            position: absolute;
            top: 15px;
            right: 15px;
            z-index: 1000;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(8px);
            padding: 16px;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            width: 320px;
            border: 1px solid #e0e0e0;
        }}
        .control-panel h3 {{
            font-size: 15px;
            font-weight: 700;
            color: #1a202c;
            margin-bottom: 4px;
        }}
        .control-panel p {{
            font-size: 12px;
            color: #718096;
            margin-bottom: 12px;
        }}
        .control-panel label {{
            display: block;
            font-size: 11px;
            font-weight: 600;
            color: #4a5568;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }}
        .control-panel select {{
            width: 100%;
            padding: 8px 10px;
            font-size: 13px;
            border-radius: 6px;
            border: 1px solid #cbd5e0;
            background: #ffffff;
            color: #2d3748;
            outline: none;
            cursor: pointer;
        }}
        .control-panel select:focus {{
            border-color: #3182ce;
            box-shadow: 0 0 0 2px rgba(49, 130, 206, 0.2);
        }}
        .legend {{
            margin-top: 14px;
            padding-top: 12px;
            border-top: 1px solid #edf2f7;
        }}
        .legend-title {{
            font-size: 11px;
            font-weight: 600;
            color: #4a5568;
            margin-bottom: 6px;
        }}
        .legend-bar {{
            height: 10px;
            border-radius: 5px;
            background: linear-gradient(to right, #440154, #3b528b, #21908d, #5dc963, #fde725);
            margin-bottom: 4px;
        }}
        .legend-labels {{
            display: flex;
            justify-content: space-between;
            font-size: 10px;
            color: #718096;
        }}
        
        .info-panel {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            z-index: 1000;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(8px);
            padding: 12px 16px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            font-size: 12px;
            color: #2d3748;
            border: 1px solid #e2e8f0;
            max-width: 300px;
        }}
        .info-panel strong {{ color: #1a202c; }}
        
        .leaflet-popup-content-wrapper {{
            border-radius: 8px;
            padding: 4px;
        }}
        .popup-table {{
            width: 100%;
            font-size: 11px;
            border-collapse: collapse;
        }}
        .popup-table td {{
            padding: 4px 6px;
            border-bottom: 1px solid #edf2f7;
        }}
        .popup-table tr:last-child td {{ border-bottom: none; }}
        .popup-table td.prop-name {{ font-weight: 600; color: #4a5568; }}
        .popup-table td.prop-val {{ text-align: right; color: #2b6cb0; font-weight: 700; }}
    </style>
</head>
<body>

    <div id="map"></div>

    <div class="control-panel">
        <h3>Geovivienda H3 (Res 9)</h3>
        <p>Malla urbana de 3,766 hexágonos</p>

        <label for="layerSelect">Seleccionar Capa / Variable</label>
        <select id="layerSelect">
            <option value="score_h3_global" selected>Score H3 Global (Sintético Maestro)</option>
            <option value="rank_hurtos_upz">Seguridad: Poca Criminalidad (Ranking UPZ)</option>
            <option value="val_hurtos_upz">Seguridad: Casos de Hurtos Totales (UPZ)</option>
            <option value="rank_estrato">Estrato Socioeconómico (Ranking 200m)</option>
            <option value="estrato_promedio_200m">Estrato Promedio (Valor 1 a 6)</option>
            <option value="rank_dist_parque">Parques: Proximidad (Ranking)</option>
            <option value="val_dist_parque">Parques: Distancia Mínima (Metros)</option>
            <option value="rank_dist_brt">Transporte: TransMilenio + Cable (Ranking)</option>
            <option value="val_dist_brt">Transporte: Distancia a BRT/Cable (Metros)</option>
            <option value="rank_dist_metro">Metro: Proximidad a Línea (Ranking)</option>
            <option value="val_dist_metro">Metro: Distancia a Línea (Metros)</option>
            <option value="rank_dist_d1_ara">Comercio: Proximidad D1 / Ara (Ranking)</option>
            <option value="val_dist_d1_ara">Comercio: Distancia a D1 / Ara (Metros)</option>
            <option value="rank_dist_centro_comercial">Comercio: Centros Comerciales (Ranking)</option>
            <option value="rank_dist_supermercado_premium">Comercio: Supermercados Premium (Ranking)</option>
            <option value="rank_arboles_300m">Entorno: Cobertura de Árboles (Ranking 300m)</option>
            <option value="val_arboles_300m">Entorno: Conteo de Árboles (300m)</option>
            <option value="rank_pm25">Calidad del Aire: Bajo PM2.5 (Ranking)</option>
            <option value="val_pm25">Calidad del Aire: PM2.5 (ug/m3)</option>
            <option value="rank_avaluo_catastral_m2">Catastro: Avalúo por m2 (Ranking)</option>
            <option value="val_avaluo_catastral_m2">Catastro: Avalúo por m2 (COP)</option>
        </select>

        <div class="legend">
            <div class="legend-title" id="legendTitle">Valor del Indicador</div>
            <div class="legend-bar"></div>
            <div class="legend-labels">
                <span id="legendMin">Bajo (0.0)</span>
                <span id="legendMax">Alto (1.0)</span>
            </div>
        </div>
    </div>

    <div class="info-panel" id="infoPanel">
        Pase el cursor sobre un hexágono para ver detalles.
    </div>

    <script type="application/json" id="geo-data">
    {json.dumps(data_json, ensure_ascii=False)}
    </script>

    <script>
        const rawData = JSON.parse(document.getElementById('geo-data').textContent);

        const map = L.map('map', {{
            center: [{lat_center}, {lng_center}],
            zoom: 12,
            zoomControl: true
        }});

        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; OpenStreetMap',
            subdomains: 'abcd',
            maxZoom: 19
        }}).addTo(map);

        let geojsonLayer = null;
        let selectedVar = 'score_h3_global';

        // Escala de Colores Viridis
        function getViridisColor(val, min, max) {{
            if (val === null || val === undefined || isNaN(val)) return '#cbd5e0';
            let norm = (val - min) / (max - min || 1);
            norm = Math.max(0, Math.min(1, norm));

            const viridisColors = [
                [68, 1, 84],     // 0.0 - Purpura
                [59, 82, 139],   // 0.25 - Azul
                [33, 144, 141],  // 0.50 - Turquesa
                [93, 201, 99],   // 0.75 - Verde
                [253, 231, 37]   // 1.0 - Amarillo
            ];

            let idx = norm * (viridisColors.length - 1);
            let i = Math.floor(idx);
            let f = idx - i;

            if (i >= viridisColors.length - 1) return `rgb(${{viridisColors[viridisColors.length - 1].join(',')}})`;

            let r = Math.round(viridisColors[i][0] + f * (viridisColors[i+1][0] - viridisColors[i][0]));
            let g = Math.round(viridisColors[i][1] + f * (viridisColors[i+1][1] - viridisColors[i][1]));
            let b = Math.round(viridisColors[i][2] + f * (viridisColors[i+1][2] - viridisColors[i][2]));

            return `rgb(${{r}}, ${{g}}, ${{b}})`;
        }}

        function getMinMax(varName) {{
            let min = Infinity, max = -Infinity;
            rawData.features.forEach(f => {{
                let val = f.properties[varName];
                if (val !== null && val !== undefined && !isNaN(val)) {{
                    if (val < min) min = val;
                    if (val > max) max = val;
                }}
            }});
            if (min === Infinity) min = 0;
            if (max === -Infinity) max = 1;
            return {{ min, max }};
        }}

        function formatVal(val, varName) {{
            if (val === null || val === undefined) return 'N/A';
            if (typeof val === 'number') {{
                if (varName.startsWith('rank_') || varName.startsWith('score_')) {{
                    return val.toFixed(4);
                }}
                if (varName.startsWith('val_dist_')) {{
                    return val.toFixed(1) + ' m';
                }}
                if (varName === 'val_avaluo_catastral_m2') {{
                    return '$ ' + Math.round(val).toLocaleString('es-CO') + ' /m2';
                }}
                return Number.isInteger(val) ? val.toLocaleString('es-CO') : val.toFixed(2);
            }}
            return val;
        }}

        function updateLayer() {{
            selectedVar = document.getElementById('layerSelect').value;
            const {{ min, max }} = getMinMax(selectedVar);

            document.getElementById('legendTitle').textContent = selectedVar;
            document.getElementById('legendMin').textContent = formatVal(min, selectedVar);
            document.getElementById('legendMax').textContent = formatVal(max, selectedVar);

            if (geojsonLayer) {{
                map.removeLayer(geojsonLayer);
            }}

            geojsonLayer = L.geoJSON(rawData, {{
                style: function(feature) {{
                    let val = feature.properties[selectedVar];
                    return {{
                        fillColor: getViridisColor(val, min, max),
                        weight: 0.5,
                        opacity: 0.4,
                        color: '#ffffff',
                        fillOpacity: 0.7
                    }};
                }},
                onEachFeature: function(feature, layer) {{
                    layer.on({{
                        mouseover: function(e) {{
                            let l = e.target;
                            l.setStyle({{ weight: 2, color: '#1a202c', fillOpacity: 0.95 }});
                            l.bringToFront();

                            let props = feature.properties;
                            let valStr = formatVal(props[selectedVar], selectedVar);
                            document.getElementById('infoPanel').innerHTML = `
                                <strong>UPZ:</strong> ${{props.upz || 'N/A'}} (${{props.localidad || 'BOGOTÁ'}})<br>
                                <strong>Hexágono H3:</strong> <code>${{props.h3_index}}</code><br>
                                <strong>${{selectedVar}}:</strong> <span style="color:#2b6cb0; font-weight:bold;">${{valStr}}</span><br>
                                <strong>Score H3 Global:</strong> ${{props.score_h3_global || 'N/A'}}
                            `;
                        }},
                        mouseout: function(e) {{
                            geojsonLayer.resetStyle(e.target);
                        }},
                        click: function(e) {{
                            let p = feature.properties;
                            let content = `
                                <div style="font-family:sans-serif; min-width: 220px;">
                                    <h4 style="margin:0 0 6px 0; font-size:13px; color:#1a202c;">UPZ ${{p.upz}}</h4>
                                    <p style="margin:0 0 8px 0; font-size:11px; color:#718096;">Localidad: ${{p.localidad}} | Res 9</p>
                                    <table class="popup-table">
                                        <tr><td class="prop-name">Score H3 Global</td><td class="prop-val">${{p.score_h3_global}}</td></tr>
                                        <tr><td class="prop-name">Hurtos UPZ (Casos)</td><td class="prop-val">${{p.val_hurtos_upz}}</td></tr>
                                        <tr><td class="prop-name">Rank Seguridad UPZ</td><td class="prop-val">${{p.rank_hurtos_upz}}</td></tr>
                                        <tr><td class="prop-name">Estrato Promedio</td><td class="prop-val">${{p.estrato_promedio_200m}}</td></tr>
                                        <tr><td class="prop-name">Distancia a Parque</td><td class="prop-val">${{formatVal(p.val_dist_parque, 'val_dist_parque')}}</td></tr>
                                        <tr><td class="prop-name">Distancia a BRT/Cable</td><td class="prop-val">${{formatVal(p.val_dist_brt, 'val_dist_brt')}}</td></tr>
                                        <tr><td class="prop-name">Distancia a Metro</td><td class="prop-val">${{formatVal(p.val_dist_metro, 'val_dist_metro')}}</td></tr>
                                        <tr><td class="prop-name">Distancia a D1/Ara</td><td class="prop-val">${{formatVal(p.val_dist_d1_ara, 'val_dist_d1_ara')}}</td></tr>
                                        <tr><td class="prop-name">Árboles a 300m</td><td class="prop-val">${{p.val_arboles_300m}}</td></tr>
                                        <tr><td class="prop-name">PM2.5 Anual</td><td class="prop-val">${{p.val_pm25}} ug/m3</td></tr>
                                    </table>
                                </div>
                            `;
                            layer.bindPopup(content).openPopup();
                        }}
                    }});
                }}
            }}).addTo(map);
        }}

        document.getElementById('layerSelect').addEventListener('change', updateLayer);
        updateLayer();
    </script>
</body>
</html>
"""

    with open(HTML_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print("¡HTML INTERACTIVO LIMPIO CREADO EXITOSAMENTE! mapa_h3_interactivo.html")

if __name__ == "__main__":
    generar()
