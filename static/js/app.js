// --- Cancelar busqueda en curso ---
async function cancelarBusqueda(busquedaId, boton) {
  if (!confirm('¿Detener esta búsqueda? Los inmuebles ya procesados se conservan, pero no se seguirán agregando más.')) return;
  boton.disabled = true;
  boton.textContent = 'Deteniendo...';
  const resp = await fetch(`/api/busquedas/${busquedaId}/cancelar`, { method: 'POST' });
  const data = await resp.json();
  if (data.status === 'ok') {
    window.location.reload();
  } else {
    boton.disabled = false;
    boton.textContent = 'Detener';
    alert(data.message || 'No se pudo cancelar la búsqueda.');
  }
}

// --- Reportes ---
async function generarReporte(clienteId, anuncioId, boton, busquedaId) {
  boton.disabled = true;
  boton.textContent = 'Generando...';
  const resp = await fetch('/api/reportes/generar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cliente_id: clienteId, anuncio_id: anuncioId, busqueda_id: busquedaId || null }),
  });
  const data = await resp.json();
  if (data.reporte_id) {
    window.location.reload();
  } else {
    boton.disabled = false;
    boton.textContent = 'Reintentar';
  }
}

// --- Edicion de inmueble: recalcular score / buscar administracion ---
async function recalcularScore(anuncioId, boton) {
  boton.disabled = true;
  const original = boton.innerHTML;
  boton.innerHTML = 'Recalculando...';
  const resultado = document.getElementById('recalcular-resultado');
  try {
    const resp = await fetch(`/inmuebles/${anuncioId}/recalcular-score`, { method: 'POST' });
    const data = await resp.json();
    if (data.status === 'ok') {
      resultado.textContent = `Score actualizado en ${data.actualizados} de ${data.total} búsqueda(s).`;
    } else {
      resultado.textContent = data.message || 'No se pudo recalcular el score.';
    }
  } finally {
    boton.disabled = false;
    boton.innerHTML = original;
    if (window.lucide) lucide.createIcons();
  }
}

async function buscarAdministracion(anuncioId, boton) {
  boton.disabled = true;
  const original = boton.innerHTML;
  boton.innerHTML = 'Buscando...';
  const resp = await fetch(`/inmuebles/${anuncioId}/buscar-administracion`, { method: 'POST' });
  const data = await resp.json();
  if (data.status === 'ok') {
    document.getElementById('administracion').value = data.administracion;
    boton.remove();
  } else {
    alert(data.message || 'No se pudo encontrar la administración en el anuncio original.');
    boton.disabled = false;
    boton.innerHTML = original;
    if (window.lucide) lucide.createIcons();
  }
}

async function generarReportePorUrl(clienteId) {
  const url = document.getElementById('url-manual').value.trim();
  const resultado = document.getElementById('resultado-manual');
  if (!url) return;
  resultado.textContent = 'Buscando y generando reporte...';
  const resp = await fetch('/api/reportes/generar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cliente_id: clienteId, url }),
  });
  const data = await resp.json();
  if (data.reporte_id) {
    resultado.innerHTML = `<a href="/reportes/${data.reporte_id}/pdf" class="btn btn-secondary btn-sm">Descargar PDF</a>`;
  } else {
    resultado.textContent = data.message || 'No se pudo generar el reporte.';
  }
}
