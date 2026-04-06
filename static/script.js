// ==============================
// COLUMNS DEFINITION
// ==============================
const COLUMNS = [
    { key: '_del', label: '', sortable: false, filterable: false },
    { key: 'Precio_Venta', label: 'Precio', sortable: true, filterable: true, numeric: true },
    { key: '_precio_m2', label: '$/m2', sortable: true, filterable: true, numeric: true },
    { key: 'Tipo_Inmueble', label: 'Tipo', sortable: true, filterable: true },
    { key: 'Ubicacion', label: 'Barrio', sortable: true, filterable: true },
    { key: 'Estrato', label: 'Estrato', sortable: true, filterable: true, numeric: true },
    { key: 'Area_Metros', label: 'Area Total', sortable: true, filterable: true, numeric: true },
    { key: 'Area_Construida', label: 'A. Const.', sortable: true, filterable: true, numeric: true },
    { key: 'Area_Privada', label: 'A. Priv.', sortable: true, filterable: true, numeric: true },
    { key: 'Habitaciones', label: 'Cuartos', sortable: true, filterable: true, numeric: true },
    { key: 'Banos', label: 'Banos', sortable: true, filterable: true, numeric: true },
    { key: 'Parqueaderos', label: 'Parq.', sortable: true, filterable: true, numeric: true },
    { key: 'Administracion', label: 'Admin.', sortable: true, filterable: true, numeric: true },
    { key: 'Comodidades', label: 'Comodidades', sortable: false, filterable: true },
    { key: '_dist_tm', label: 'Dist. TM (m)', sortable: true, filterable: true, numeric: true },
    { key: '_url', label: 'Enlace', sortable: false, filterable: false },
];

// ==============================
// STATE
// ==============================
let map, markerGroup;
let rawDataset = [];        // from server
let viewDataset = [];       // after sort+filter
let sortCol = null;
let sortDir = 'asc';
let filters = {};
let tmStationsArr = []; // To calculate distances later

// ==============================
// INIT
// ==============================
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    buildTableHead();
    loadData();
    bindToggleGroups();
    bindFilterPanel();
    document.getElementById("scrape-form").addEventListener("submit", triggerScrape);
});

// ==============================
// TAB SWITCHING
// ==============================
function switchTab(tab) {
    ['filter', 'scrape'].forEach(t => {
        document.getElementById(`tab-btn-${t}`).classList.toggle('active', t === tab);
        document.getElementById(`tab-panel-${t}`).classList.toggle('active', t === tab);
    });
}

// Layer registry for toggle control
const ESTRATO_COLOR = {
    1: '#7b2d8b', 2: '#3a6fd8', 3: '#2eaa62',
    4: '#d4a800', 5: '#e07b00', 6: '#cc2020'
};

const LAYERS = {
    estratos: { label: 'Estratos', color: '#d4a800', layer: null, visible: false },
    sitp: { label: 'SITP', color: '#2255cc', layer: null, visible: false },
    tm: { label: 'TM', color: '#cc2222', layer: null, visible: false },
    metro: { label: 'Metro', color: '#ff8800', layer: null, visible: false },
    cable: { label: 'Cable', color: '#dd1144', layer: null, visible: false },
    ciclorutas: { label: 'Ciclorutas', color: '#e8e8e8', layer: null, visible: false },
};

function initMap() {
    map = L.map('map').setView([4.6097, -74.0817], 11);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CartoDB', maxZoom: 19
    }).addTo(map);

    // Helper: load a layer but only add it to map if visible:true
    function maybeAdd(key) {
        if (LAYERS[key].visible) map.addLayer(LAYERS[key].layer);
    }

    // ---- Estratos (polígonos coloreados por ESTRATO) ----
    fetch('/api/geo/estratos.geojson')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(gj => {
            LAYERS.estratos.layer = L.geoJSON(gj, {
                style: f => {
                    const e = f.properties && (f.properties.ESTRATO || f.properties.estrato);
                    return { color: 'transparent', fillColor: ESTRATO_COLOR[e] || '#555', fillOpacity: 0.35, weight: 0 };
                }
            });
            maybeAdd('estratos');
        }).catch(() => { });

    // ---- SITP (azul rey, radio 3) ----
    fetch('/api/geo/estaciones_sitp.geojson')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(gj => {
            LAYERS.sitp.layer = L.geoJSON(gj, {
                pointToLayer: (f, latlng) => L.circleMarker(latlng, {
                    radius: 3, fillColor: '#2255cc', color: '#2255cc', weight: 0, fillOpacity: 0.7
                }),
                onEachFeature: (f, l) => {
                    const n = f.properties && (f.properties.nombre || f.properties.nom_est);
                    if (n) l.bindTooltip(n, { sticky: true });
                }
            });
            maybeAdd('sitp');
        }).catch(() => { });

    // ---- TM (rojo oscuro, radio 5) ----
    fetch('/api/geo/estaciones_tm.geojson')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(gj => {
            // Save stations for distance calculation
            tmStationsArr = gj.features.map(f => ({
                lat: f.geometry.coordinates[1],
                lng: f.geometry.coordinates[0]
            }));

            // Force recalculation of distances in dataset if already loaded
            if (rawDataset.length > 0) {
                rawDataset = rawDataset.map(enrichRow);
                applyFiltersAndSort();
            }

            LAYERS.tm.layer = L.geoJSON(gj, {
                pointToLayer: (f, latlng) => L.circleMarker(latlng, {
                    radius: 5, fillColor: '#cc2222', color: '#cc2222', weight: 0, fillOpacity: 0.9
                }),
                onEachFeature: (f, l) => {
                    if (f.properties && f.properties.nom_est)
                        l.bindTooltip(f.properties.nom_est, { sticky: true });
                }
            });
            maybeAdd('tm');
        }).catch(() => { });

    // ---- Metro (naranja, centroide de MultiPolygon) ----
    fetch('/api/geo/estaciones_metro.geojson')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(gj => {
            const markers = L.layerGroup();
            gj.features.forEach(f => {
                const geom = f.geometry;
                if (!geom) return;
                let lats = [], lngs = [];
                const rings = geom.type === 'MultiPolygon' ? geom.coordinates.flat(1) : geom.coordinates;
                rings.forEach(ring => ring.forEach(([lng, lat]) => { lngs.push(lng); lats.push(lat); }));
                if (!lats.length) return;
                const centLat = lats.reduce((a, b) => a + b, 0) / lats.length;
                const centLng = lngs.reduce((a, b) => a + b, 0) / lngs.length;
                const m = L.circleMarker([centLat, centLng], {
                    radius: 7, fillColor: '#ff8800', color: '#ff8800', weight: 0, fillOpacity: 0.95
                });
                const n = f.properties && (f.properties.NOMBRE || f.properties.nombre);
                if (n) m.bindTooltip(n, { sticky: true });
                markers.addLayer(m);
            });
            LAYERS.metro.layer = markers;
            maybeAdd('metro');
        }).catch(() => { });

    // ---- Cable (rojo claro, radio 6) ----
    fetch('/api/geo/estaciones_cable.geojson')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(gj => {
            LAYERS.cable.layer = L.geoJSON(gj, {
                pointToLayer: (f, latlng) => L.circleMarker(latlng, {
                    radius: 6, fillColor: '#dd1144', color: '#dd1144', weight: 0, fillOpacity: 0.95
                }),
                onEachFeature: (f, l) => {
                    if (f.properties && f.properties.nom_est)
                        l.bindTooltip(f.properties.nom_est, { sticky: true });
                }
            });
            maybeAdd('cable');
        }).catch(() => { });

    // ---- Ciclorutas (blanco, línea fina, sin tooltip) ----
    fetch('/api/geo/cliclorutas.geojson')
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(gj => {
            LAYERS.ciclorutas.layer = L.geoJSON(gj, {
                style: { color: '#e8e8e8', weight: 1.2, opacity: 0.55 }
            });
            maybeAdd('ciclorutas');
        }).catch(() => { });

    // markerGroup al final → inmuebles siempre encima
    markerGroup = L.layerGroup().addTo(map);

    // ---- Legend Control para Estratos ----
    estratoLegend = L.control({ position: 'bottomleft' });
    estratoLegend.onAdd = function () {
        const div = L.DomUtil.create('div', 'info legend estrato-legend');
        div.innerHTML = '<h4>Estratos</h4>';
        for (let i = 1; i <= 6; i++) {
            div.innerHTML += `
                <div class="legend-row">
                    <i style="background:${ESTRATO_COLOR[i]}"></i> Estrato ${i}
                </div>`;
        }
        return div;
    };
    // No añadimos la leyenda todavía porque la capa arranca apagada

    buildLayerToggle();
}

let estratoLegend; // variable global para la leyenda

// ---- Panel flotante de capas (todos apagados por defecto) ----
function buildLayerToggle() {
    const ctrl = document.createElement('div');
    ctrl.id = 'layer-ctrl';
    ctrl.innerHTML = '<div class="lc-title">Capas</div>';
    Object.entries(LAYERS).forEach(([key, cfg]) => {
        const row = document.createElement('label');
        row.className = 'lc-row';
        row.innerHTML = `
            <input type="checkbox" ${cfg.visible ? 'checked' : ''} onchange="toggleLayer('${key}', this.checked)">
            <span class="lc-dot" style="background:${cfg.color}"></span>
            ${cfg.label}`;
        ctrl.appendChild(row);
    });
    document.querySelector('.map-wrapper').appendChild(ctrl);
}

function toggleLayer(key, visible) {
    const cfg = LAYERS[key];
    if (!cfg || !cfg.layer) return;

    if (visible) {
        map.addLayer(cfg.layer);
        if (key === 'estratos') estratoLegend.addTo(map);
    } else {
        map.removeLayer(cfg.layer);
        if (key === 'estratos') estratoLegend.remove();
    }
}

// ==============================
// TABLE HEAD (dynamic)
// ==============================
function buildTableHead() {
    const tr = document.querySelector('#table-head tr');
    tr.innerHTML = '';
    COLUMNS.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col.label;
        if (col.sortable) {
            th.classList.add('sortable');
            th.dataset.key = col.key;
            th.addEventListener('click', () => handleSort(col.key, th));
        }
        tr.appendChild(th);
    });
}

// ==============================
// FILTER PANEL BINDING
// ==============================
function bindFilterPanel() {
    // Text / numeric inputs
    ['f-ubicacion', 'f-precio-min', 'f-precio-max', 'f-area-min', 'f-comodidades'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', applyFiltersAndSort);
    });
    // Multi-select: estrato, estado, tipo
    ['f-estrato-group', 'f-estado-group', 'f-tipo-group'].forEach(id => {
        const grp = document.getElementById(id);
        if (!grp) return;
        grp.querySelectorAll('.toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                btn.classList.toggle('active');
                applyFiltersAndSort();
            });
        });
    });
    // Single-select: habitaciones, banos
    ['f-habitaciones-group', 'f-banos-group'].forEach(id => {
        const grp = document.getElementById(id);
        if (!grp) return;
        grp.querySelectorAll('.toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                grp.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                applyFiltersAndSort();
            });
        });
    });
}

function clearFilters() {
    ['f-ubicacion', 'f-precio-min', 'f-precio-max', 'f-area-min', 'f-comodidades'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    ['f-estrato-group', 'f-estado-group', 'f-tipo-group'].forEach(id => {
        const grp = document.getElementById(id);
        if (grp) grp.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    });
    ['f-habitaciones-group', 'f-banos-group'].forEach(id => {
        const grp = document.getElementById(id);
        if (!grp) return;
        const btns = grp.querySelectorAll('.toggle-btn');
        btns.forEach(b => b.classList.remove('active'));
        if (btns[0]) btns[0].classList.add('active');
    });
    applyFiltersAndSort();
}

function getFilterPanelValues() {
    const get = id => document.getElementById(id);
    const val = id => (get(id) ? get(id).value : '');
    const ubicacion  = val('f-ubicacion').trim().toLowerCase();
    const precioMin  = parseNum(val('f-precio-min'));
    const precioMax  = parseNum(val('f-precio-max'));
    const areaMin    = parseNum(val('f-area-min'));
    const comodidades = val('f-comodidades').trim().toLowerCase();
    const estratos   = [...document.querySelectorAll('#f-estrato-group .toggle-btn.active')].map(b => b.dataset.val);
    const estados    = [...document.querySelectorAll('#f-estado-group .toggle-btn.active')].map(b => b.dataset.val);
    const tipos      = [...document.querySelectorAll('#f-tipo-group .toggle-btn.active')].map(b => b.dataset.val);
    const habMinVal   = (document.querySelector('#f-habitaciones-group .toggle-btn.active') || {}).dataset?.val || '0';
    const banosMinVal = (document.querySelector('#f-banos-group .toggle-btn.active') || {}).dataset?.val || '0';
    return { ubicacion, precioMin, precioMax, areaMin, comodidades, estratos, estados, tipos, habMin: parseInt(habMinVal), banosMin: parseInt(banosMinVal) };
}

// ==============================
// TOGGLE GROUPS
// ==============================
function bindToggleGroups() {
    // Multi-select: estrato, comodidades, estado, tipo (scrape panel)
    ['estrato-group', 'comodidades-group', 'estado-group', 'tipo-group'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.querySelectorAll('.toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => btn.classList.toggle('active'));
        });
    });
    // Single-select: cuartos, banos, parqueaderos (scrape panel)
    ['cuartos-group', 'banos-group', 'parq-group'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.querySelectorAll('.toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                el.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    });
}

function getActiveVal(groupId) {
    const a = document.querySelector(`#${groupId} .toggle-btn.active`);
    return a ? a.dataset.val : null;
}

function getActiveVals(groupId) {
    return [...document.querySelectorAll(`#${groupId} .toggle-btn.active`)].map(b => b.dataset.val);
}

// ==============================
// LOAD DATA
// ==============================
function loadData() {
    fetch('/api/data')
        .then(r => r.json())
        .then(data => {
            console.log("Cargando", data.length, "registros");
            rawDataset = data.map(enrichRow);
            applyFiltersAndSort();
        })
        .catch(err => console.error("Error cargando tabla:", err));
}

// Fill gaps: area fields, precio_m2
function enrichRow(row) {
    let total = parseNum(row.Area_Metros);
    let construida = parseNum(row.Area_Construida);
    let privada = parseNum(row.Area_Privada);

    // Fill gaps between area fields
    if (!construida && privada) construida = privada;
    if (!privada && construida) privada = construida;
    if (!total && construida) total = construida;
    if (!total && privada) total = privada;

    row.Area_Metros = total || row.Area_Metros;
    row.Area_Construida = construida || row.Area_Construida;
    row.Area_Privada = privada || row.Area_Privada;

    // Precio / m2
    const precio = parseNum(row.Precio_Venta);
    row._precio_m2 = (precio > 0 && total > 0) ? Math.round(precio / total) : null;

    // Distancia a TM mas cercano
    if (tmStationsArr.length > 0 && row.Latitud && row.Longitud) {
        let minDist = Infinity;
        const rLat = parseFloat(String(row.Latitud).replace(',', '.'));
        const rLng = parseFloat(String(row.Longitud).replace(',', '.'));
        
        for (const st of tmStationsArr) {
            const d = haversineDistance(rLat, rLng, st.lat, st.lng);
            if (d < minDist) minDist = d;
        }
        row._dist_tm = Math.round(minDist);
    } else {
        row._dist_tm = null;
    }

    return row;
}

function haversineDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000; // Earth radius in meters
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

// ==============================
// SORT & FILTER
// ==============================
function handleSort(key, th) {
    if (sortCol === key) {
        sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        sortCol = key;
        sortDir = 'asc';
    }
    // Update th classes
    document.querySelectorAll('#table-head th').forEach(el => el.classList.remove('asc', 'desc'));
    th.classList.add(sortDir);
    applyFiltersAndSort();
}

function applyFiltersAndSort() {
    let result = [...rawDataset];
    const f = getFilterPanelValues();

    // Ubicacion text
    if (f.ubicacion) {
        result = result.filter(r => String(r.Ubicacion || '').toLowerCase().includes(f.ubicacion));
    }
    // Precio min
    if (f.precioMin > 0) {
        result = result.filter(r => parseNum(r.Precio_Venta) >= f.precioMin);
    }
    // Precio max
    if (f.precioMax > 0) {
        result = result.filter(r => parseNum(r.Precio_Venta) <= f.precioMax);
    }
    // Area min
    if (f.areaMin > 0) {
        result = result.filter(r => parseNum(r.Area_Metros) >= f.areaMin);
    }
    // Estratos (multi-select — if none selected, show all)
    if (f.estratos.length > 0) {
        result = result.filter(r => f.estratos.includes(String(r.Estrato)));
    }
    // Habitaciones min
    if (f.habMin > 0) {
        result = result.filter(r => parseNum(r.Habitaciones) >= f.habMin);
    }
    // Banos min
    if (f.banosMin > 0) {
        result = result.filter(r => parseNum(r.Banos) >= f.banosMin);
    }
    // Comodidades free text
    if (f.comodidades) {
        result = result.filter(r => String(r.Comodidades || '').toLowerCase().includes(f.comodidades));
    }
    // Estado (multi)
    if (f.estados.length > 0) {
        result = result.filter(r => f.estados.some(ev => String(r.Estado || '').toLowerCase().includes(ev)));
    }
    // Tipo (multi)
    if (f.tipos.length > 0) {
        result = result.filter(r => f.tipos.some(tv => String(r.Tipo_Inmueble || '').toLowerCase().includes(tv)));
    }

    // Sort
    if (sortCol) {
        const col = COLUMNS.find(c => c.key === sortCol);
        result.sort((a, b) => {
            let av = a[sortCol], bv = b[sortCol];
            if (col && col.numeric) { av = parseNum(av); bv = parseNum(bv); }
            else { av = String(av || '').toLowerCase(); bv = String(bv || '').toLowerCase(); }
            if (av < bv) return sortDir === 'asc' ? -1 : 1;
            if (av > bv) return sortDir === 'asc' ? 1 : -1;
            return 0;
        });
    }

    viewDataset = result;
    renderAll();
}

// ==============================
// RENDER
// ==============================
function getGradientColor(price, minP, maxP) {
    if (minP === maxP) return 'hsl(210, 80%, 55%)';
    const t = Math.max(0, Math.min(1, (price - minP) / (maxP - minP)));
    return `hsl(${220 - t * 220}, 82%, 55%)`;
}

const copFmt = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });

function renderAll() {
    markerGroup.clearLayers();
    const tbody = document.getElementById('table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    const prices = viewDataset.map(d => parseNum(d.Precio_Venta)).filter(p => p > 0);
    const minP = prices.length > 0 ? Math.min(...prices) : 0;
    const maxP = prices.length > 0 ? Math.max(...prices) : 0;
    const bounds = [];

    viewDataset.forEach((row, idx) => {
        const price = parseNum(row.Precio_Venta);
        const priceStr = price > 0 ? copFmt.format(price) : 'Sin precio';
        const pM2 = row._precio_m2 ? copFmt.format(row._precio_m2) : '--';
        const lat = parseFloat(String(row.Latitud).replace(',', '.'));
        const lng = parseFloat(String(row.Longitud).replace(',', '.'));
        const color = price > 0 ? getGradientColor(price, minP, maxP) : '#555e75';

        // Map marker
        if (!isNaN(lat) && !isNaN(lng)) {
            bounds.push([lat, lng]);
            const marker = L.circleMarker([lat, lng], {
                radius: 7, fillColor: color, color: '#fff', weight: 1.5,
                opacity: 1, fillOpacity: 0.9
            });
            marker.bindPopup(`
                <div class="popup-price">${priceStr}</div>
                <div class="popup-row"><b>Barrio:</b> ${row.Ubicacion || '--'}</div>
                <div class="popup-row"><b>Area:</b> ${row.Area_Metros || '--'} m2 | <b>$/m2:</b> ${pM2}</div>
                <div class="popup-row"><b>Cuartos:</b> ${row.Habitaciones || '--'} | <b>Banos:</b> ${row.Banos || '--'}</div>
                <div class="popup-row"><b>Comodidades:</b> ${row.Comodidades || '--'}</div>
                <a class="popup-link" href="${row.URL}" target="_blank">Ver en FincaRaiz</a>
            `);
            marker.on('mouseover', function () { this.openPopup(); });
            marker.on('click', () => highlightRow(idx));
            markerGroup.addLayer(marker);
        }

        // Admin display
        const adminVal = parseNum(row.Administracion);
        const adminCell = adminVal > 0
            ? copFmt.format(adminVal)
            : `<span class="admin-included">Incluido en el precio</span>`;

        // Table row
        const tr = document.createElement('tr');
        tr.id = `row-${idx}`;
        const distStr = row._dist_tm !== null ? `${row._dist_tm} m` : '--';
        tr.innerHTML = `
            <td><button class="del-row-btn" title="Eliminar" onclick="deleteRow(event,'${row.URL}')">&#10005;</button></td>
            <td class="price-cell">${priceStr}</td>
            <td class="price-m2">${pM2}</td>
            <td>${row.Tipo_Inmueble || '--'}</td>
            <td>${row.Ubicacion || '--'}</td>
            <td>${row.Estrato || '--'}</td>
            <td>${row.Area_Metros || '--'}</td>
            <td>${row.Area_Construida || '--'}</td>
            <td>${row.Area_Privada || '--'}</td>
            <td>${row.Habitaciones || '--'}</td>
            <td>${row.Banos || '--'}</td>
            <td>${row.Parqueaderos || '--'}</td>
            <td>${adminCell}</td>
            <td title="${row.Comodidades || ''}">${truncate(row.Comodidades, 30)}</td>
            <td class="dist-tm-cell">${distStr}</td>
            <td><a class="link-out" href="${row.URL}" target="_blank">Ver</a></td>
        `;
        tr.addEventListener('click', (e) => {
            if (e.target.classList.contains('del-row-btn')) return;
            if (!isNaN(lat) && !isNaN(lng)) map.flyTo([lat, lng], 16, { duration: 1 });
            highlightRow(idx);
        });
        tbody.appendChild(tr);
    });

    document.getElementById("prop-count").innerText = `${viewDataset.length} registros`;
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [40, 40] });
}

// ==============================
// UTILS
// ==============================
function parseNum(val) {
    if (val === null || val === undefined || val === '') return 0;
    if (typeof val === 'number') return val;
    let s = String(val);
    // Si ya es un float nativo con punto y sin comas (ej: 3.5 desde pandas)
    if (s.includes('.') && !s.includes(',')) return parseFloat(s) || 0;
    // Si tiene comas (formato latino), quitamos los puntos de miles y cambiamos coma por punto
    return parseFloat(s.replace(/\./g, '').replace(',', '.')) || 0;
}

function truncate(str, n) {
    if (!str) return '--';
    return str.length > n ? str.slice(0, n) + '...' : str;
}

function highlightRow(idx) {
    document.querySelectorAll('#table-body tr').forEach(r => r.classList.remove('selected-row'));
    const tr = document.getElementById(`row-${idx}`);
    if (tr) { tr.classList.add('selected-row'); tr.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
}

// ==============================
// DELETE
// ==============================
function deleteRow(e, url) {
    e.stopPropagation();
    fetch('/api/delete_row', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
    }).then(() => loadData());
}

function clearAllData() {
    if (!confirm('Eliminar toda la base de datos? Esta accion no se puede deshacer.')) return;
    fetch('/api/clear', { method: 'POST' })
        .then(() => { rawDataset = []; viewDataset = []; renderAll(); appendLog('Base de datos vaciada.', 'warn'); });
}

// ==============================
// SCRAPE (background + polling)
// ==============================
let pollInterval = null;
let logCursor = 0;

function triggerScrape(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-scrape');
    btn.disabled = true;
    logCursor = 0;

    const numInmuebles = parseInt(document.getElementById('num_inmuebles').value) || 21;
    const paginas = Math.ceil(numInmuebles / 21);

    appendLog(`Objetivo: ${numInmuebles} inmuebles -> ${paginas} paginas`, 'info');

    const comodidades = getActiveVals('comodidades-group');
    const estratos = getActiveVals('estrato-group');
    const tipos = getActiveVals('tipo-group');
    const estados = getActiveVals('estado-group');
    const cuartosVal = getActiveVal('cuartos-group');
    const banosVal = getActiveVal('banos-group');
    const parqVal = getActiveVal('parq-group');

    const payload = {
        ubicacion: document.getElementById('ubicacion').value,
        operacion: document.getElementById('operacion').value,
        tipos,
        estados,
        precio_min: document.getElementById('precio_min').value,
        precio_max: document.getElementById('precio_max').value,
        estratos,
        habitaciones: cuartosVal ? `${cuartosVal}-o-mas` : '1-o-mas',
        banos: banosVal ? `${banosVal}-o-mas` : '1-o-mas',
        parqueaderos: parqVal && parqVal !== '0' ? parseInt(parqVal) : null,
        comodidades,
        paginas
    };

    fetch('/api/scrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'started') {
                appendLog('Rastreo iniciado. Aguarda los resultados...', 'info');
                startPolling();
            } else if (data.status === 'warning') {
                appendLog(data.message, 'warn');
                btn.disabled = false;
            } else {
                appendLog(data.message || 'Error desconocido.', 'error');
                btn.disabled = false;
            }
        })
        .catch(err => { btn.disabled = false; appendLog('Error: ' + err, 'error'); });
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => {
        fetch(`/api/status?since=${logCursor}`)
            .then(r => r.json())
            .then(data => {
                // Replay new server-side logs into the console
                data.logs.forEach(entry => appendLog(entry.msg, entry.level));
                logCursor = data.total_logs;

                if (data.status === 'done' || data.status === 'error') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    document.getElementById('btn-scrape').disabled = false;
                    if (data.status === 'done') loadData();
                }
            })
            .catch(() => { }); // ignore transient network hiccups
    }, 2000);
}

// ==============================
// LOG
// ==============================
function appendLog(msg, type = '') {
    const con = document.getElementById('log-console');
    const line = document.createElement('div');
    line.className = `log-line ${type}`;
    const ts = new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    line.textContent = `[${ts}] ${msg}`;
    con.appendChild(line);
    con.scrollTop = con.scrollHeight;
}

function parseNum(v) {
    if (v === undefined || v === null || v === "") return 0;
    // Format: 480.000.000,0 or 480000000,0
    let s = String(v).trim();
    // Remove dots (thousands) and replace comma with dot
    s = s.replace(/\./g, "").replace(",", ".");
    return parseFloat(s) || 0;
}
