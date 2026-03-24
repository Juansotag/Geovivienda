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

// ==============================
// INIT
// ==============================
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    buildTableHead();
    
    loadData();
    bindToggleGroups();
    document.getElementById("scrape-form").addEventListener("submit", triggerScrape);
});

// Layer registry for toggle control
const ESTRATO_COLOR = {
    1: '#ce1818ff', 2: '#e0631aff', 3: '#ebd515ff',
    4: '#a7db17ff', 5: '#17c29dff', 6: '#2065ccff'
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
        .then(r => r.json())
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
        .then(r => r.json())
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
        .then(r => r.json())
        .then(gj => {
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
        .then(r => r.json())
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
        .then(r => r.json())
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
        .then(r => r.json())
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

let popupNode = null;
function showFilterPopup(col, th, btn) {
    if (popupNode) { popupNode.remove(); popupNode = null; }
    
    popupNode = document.createElement('div');
    popupNode.className = 'excel-popup';
    
    // Title
    const title = document.createElement('div');
    title.innerHTML = `<b>Filtrar:</b> ${col.label}`;
    title.style.marginBottom = '10px';
    popupNode.appendChild(title);
    
    let activeF = filters[col.key] || { active: false };
    
    if (col.numeric) {
        // Min / Max
        popupNode.innerHTML += `
            <div style="margin-bottom:8px"><label>Min</label><br><input type="number" id="pf_min" value="${activeF.min!==undefined ? activeF.min : ''}"></div>
            <div style="margin-bottom:8px"><label>Max</label><br><input type="number" id="pf_max" value="${activeF.max!==undefined ? activeF.max : ''}"></div>
        `;
    } else {
        // Unique values checkboxes
        const uniqueValues = [...new Set(rawDataset.map(r => String(r[col.key]||'')))].sort();
        const listDiv = document.createElement('div');
        listDiv.style.maxHeight = '150px';
        listDiv.style.overflowY = 'auto';
        listDiv.style.marginBottom = '10px';
        
        uniqueValues.forEach(val => {
            const vStr = val || '(Vacío)';
            const checked = !activeF.active || (activeF.values && activeF.values.has(val));
            listDiv.innerHTML += `<div style="margin-bottom:4px"><label><input type="checkbox" class="pf_chk" value="${val}" ${checked ? 'checked' : ''}> ${vStr.length>30?vStr.slice(0,30)+'...':vStr}</label></div>`;
        });
        popupNode.appendChild(listDiv);
    }
    
    const applyBtn = document.createElement('button');
    applyBtn.innerText = 'Aplicar';
    applyBtn.style.marginRight = '10px';
    applyBtn.onclick = () => {
        if (col.numeric) {
            const mi = document.getElementById('pf_min').value;
            const ma = document.getElementById('pf_max').value;
            if(mi==='' && ma==='') {
                filters[col.key] = { active: false };
                btn.style.color = '';
            } else {
                filters[col.key] = { active:true, type:'numeric', min:mi, max:ma };
                btn.style.color = 'var(--primary)';
            }
        } else {
            const chks = [...popupNode.querySelectorAll('.pf_chk')];
            const selected = new Set(chks.filter(c => c.checked).map(c => c.value));
            if(selected.size === chks.length) {
                filters[col.key] = { active: false };
                btn.style.color = '';
            } else {
                filters[col.key] = { active:true, type:'string', values: selected };
                btn.style.color = 'var(--primary)';
            }
        }
        applyFiltersAndSort();
        popupNode.remove();
        popupNode = null;
    };
    
    const clearBtn = document.createElement('button');
    clearBtn.innerText = 'Limpiar';
    clearBtn.onclick = () => {
        filters[col.key] = { active: false };
        btn.style.color = '';
        applyFiltersAndSort();
        popupNode.remove();
        popupNode = null;
    };
    
    popupNode.appendChild(applyBtn);
    popupNode.appendChild(clearBtn);
    
    // Position
    const rect = th.getBoundingClientRect();
    popupNode.style.top = (rect.bottom + window.scrollY) + 'px';
    popupNode.style.left = rect.left + 'px';
    
    document.body.appendChild(popupNode);
    
    // close on outside click
    setTimeout(() => {
        document.addEventListener('click', function closeP(e){
            if(popupNode && !popupNode.contains(e.target) && e.target !== btn) {
                popupNode.remove();
                popupNode=null;
                document.removeEventListener('click', closeP);
            }
        });
    }, 100);
}

function buildTableHead() {
    const tr = document.querySelector('#table-head tr');
    tr.innerHTML = '';
    COLUMNS.forEach(col => {
        const th = document.createElement('th');
        const span = document.createElement('span');
        span.textContent = col.label;
        if (col.sortable) {
            span.classList.add('sortable');
            span.dataset.key = col.key;
            span.addEventListener('click', () => handleSort(col.key, span));
        }
        th.appendChild(span);
        
        if (col.filterable) {
            const btn = document.createElement('i');
            btn.innerHTML = ' &#9084;'; // Funnel symbol
            btn.style.cursor = 'pointer';
            btn.style.marginLeft = '8px';
            btn.onclick = (e) => { e.stopPropagation(); showFilterPopup(col, th, btn); };
            th.appendChild(btn);
        }
        tr.appendChild(th);
    });
}


// ==============================
// TOGGLE GROUPS
// ==============================
function bindToggleGroups() {
    // Multi-select: estrato, comodidades
    ['estrato-group', 'comodidades-group'].forEach(id => {
        document.getElementById(id).querySelectorAll('.toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => btn.classList.toggle('active'));
        });
    });
    // Single-select: cuartos, banos, parqueaderos
    ['cuartos-group', 'banos-group', 'parq-group'].forEach(id => {
        document.getElementById(id).querySelectorAll('.toggle-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById(id).querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
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
            rawDataset = data.map(enrichRow);
            applyFiltersAndSort();
        });
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

    return row;
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
    document.querySelectorAll('#table-head th span').forEach(el => el.classList.remove('asc', 'desc'));
    th.classList.add(sortDir);
    applyFiltersAndSort();
}

function applyFiltersAndSort() {
    let result = [...rawDataset];

    // Filter
    Object.entries(filters).forEach(([colKey, fVal]) => {
        if (!fVal || !fVal.active) return;
        result = result.filter(row => {
            let cell = row[colKey];
            if (fVal.type === 'numeric') {
                let v = parseNum(cell);
                if (fVal.min !== '' && v < parseFloat(fVal.min)) return false;
                if (fVal.max !== '' && v > parseFloat(fVal.max)) return false;
                return true;
            } else {
                if (cell === null || cell === undefined) cell = '';
                return Array.from(fVal.values).length === 0 || fVal.values.has(String(cell));
            }
        });
    });

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
    tbody.innerHTML = '';

    const prices = viewDataset.map(d => parseNum(d.Precio_Venta)).filter(p => p > 0);
    const minP = Math.min(...prices), maxP = Math.max(...prices);
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
    return parseFloat(String(val).replace(/\./g, '').replace(',', '.')) || 0;
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
    const cuartosVal = getActiveVal('cuartos-group');
    const banosVal = getActiveVal('banos-group');
    const parqVal = getActiveVal('parq-group');

    const payload = {
        ubicacion: document.getElementById('ubicacion').value,
        operacion: document.getElementById('operacion').value,
        tipo: document.getElementById('tipo').value,
        estado: document.getElementById('estado').value,
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
