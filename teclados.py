"""
TECLADOS - BOTONES RÁPIDOS v2.2
================================
Teclados con botones para conductores y admins.

Cambios v2.2:
- Añadido botón "🔄 Modificar viaje en ruta" para admin

Cambios v2.1:
- Añadido botón "📋 Consultar rutas" para admin
- Eliminado botón Clima

Uso:
    from teclados import teclado_conductor, teclado_admin, obtener_teclado
"""

from telegram import ReplyKeyboardMarkup, KeyboardButton


# ============================================================
# TECLADO CONDUCTOR
# ============================================================

BOTONES_CONDUCTOR = [
    ["🚛 Mis viajes", "🚚 Mi camión"],
    ["⛽ Gasolineras", "📍 Mi ubicación"],
    ["📝 Registros", "📊 Resumen"]
]

teclado_conductor = ReplyKeyboardMarkup(
    BOTONES_CONDUCTOR,
    resize_keyboard=True,
    one_time_keyboard=False
)


# ============================================================
# TECLADO ADMIN (con Modificar viaje en ruta)
# ============================================================

BOTONES_ADMIN = [
    ["🤖 Asignar viajes", "📦 Todos los viajes"],
    ["👥 Conductores", "🗺️ Estado de la flota"],
    ["📋 Consultar rutas", "📊 Estadísticas"],
    ["📈 Informe semanal", "💰 Rentabilidad"],
    ["🔄 Modificar viaje en ruta"],  # NUEVO
    ["🔄 Sincronizar", "🛠️ Gestiones"]
]

teclado_admin = ReplyKeyboardMarkup(
    BOTONES_ADMIN,
    resize_keyboard=True,
    one_time_keyboard=False
)


# ============================================================
# TECLADO NO VINCULADO
# ============================================================

BOTONES_NO_VINCULADO = [
    ["🔗 Vincularme"]
]

teclado_no_vinculado = ReplyKeyboardMarkup(
    BOTONES_NO_VINCULADO,
    resize_keyboard=True,
    one_time_keyboard=False
)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def obtener_teclado(es_admin: bool = False, esta_vinculado: bool = True):
    """Devuelve el teclado apropiado según el perfil."""
    if not esta_vinculado:
        return teclado_no_vinculado
    
    if es_admin:
        return teclado_admin
    
    return teclado_conductor


# ============================================================
# MAPEO BOTÓN → ACCIÓN
# ============================================================

MAPEO_BOTONES = {
    # Conductor
    "🚛 Mis viajes": "mis_viajes",
    "⛽ Gasolineras": "gasolineras",
    "📍 Mi ubicación": "mi_ubicacion",
    "🚚 Mi camión": "mi_camion",
    "📝 Registros": "registros",  # NUEVO
    "📊 Resumen": "resumen",
    
    # Admin
    "🤖 Asignar viajes": "asignar",
    "👥 Conductores": "conductores",
    "📦 Todos los viajes": "todos_viajes",
    "🗺️ Estado de la flota": "estado_flota",
    "📋 Consultar rutas": "consultar_rutas",
    "📊 Estadísticas": "estadisticas",
    "📈 Informe semanal": "informe_semanal",
    "💰 Rentabilidad": "rentabilidad",
    "🔄 Sincronizar": "sync",
    "🛠️ Gestiones": "gestiones",
    "🔄 Modificar viaje en ruta": "modificar_viaje_ruta",  # NUEVO
    
    # No vinculado
    "🔗 Vincularme": "vincular",
}


def es_boton(texto: str) -> bool:
    """Verifica si el texto es un botón conocido"""
    return texto in MAPEO_BOTONES


def obtener_accion_boton(texto: str) -> str:
    """Devuelve la acción asociada a un botón"""
    return MAPEO_BOTONES.get(texto, "")
