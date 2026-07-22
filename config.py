"""
Configuracion central de Geovivienda.

Los nombres de modelos Claude estan definidos aqui como constantes para que
una sola edicion actualice todo el proyecto. Antes estaban hardcodeados en
3 archivos distintos (busqueda.py, scoring.py, reportes.py) con valores
inconsistentes entre si.
"""

# --- Modelos Anthropic Claude ------------------------------------------------

# Modelo principal: razonamiento complejo, scoring cualitativo, normalizacion
# de comodidades, generacion de reportes.
CLAUDE_SMART = "claude-sonnet-4-5"

# Modelo ultrarapido: solicitud de pesos LLM (~300ms, max_tokens=250).
# Usa el mismo que CLAUDE_SMART por ahora; cambiar aqui si se migra a Haiku.
CLAUDE_FAST = "claude-sonnet-4-5"

# --- Limites de tokens por tarea ---------------------------------------------

MAX_TOKENS_SCORING = 4000
MAX_TOKENS_PESOS   = 250
MAX_TOKENS_REPORTE = 1600

# --- Integraciones externas --------------------------------------------------
import os
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")