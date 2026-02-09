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
# TECLADO ADMIN (Simplificado con submenús)
# ============================================================

BOTONES_ADMIN = [
    ["📦 Viajes y rutas"],
    ["🚛 Flota"],
    ["📊 Informes"],
    ["🛠️ Gestiones"]
]

teclado_admin = ReplyKeyboardMarkup(
    BOTONES_ADMIN,
    resize_keyboard=True,
    one_time_keyboard=False
)

# Submenú: Viajes y rutas
BOTONES_VIAJES = [
    ["📦 Todos los viajes", "📋 Consultar rutas"],
    ["🤖 Asignar viajes", "🔄 Modificar viaje en ruta"],
    ["⬅️ Volver al menú"]
]

teclado_viajes = ReplyKeyboardMarkup(
    BOTONES_VIAJES,
    resize_keyboard=True,
    one_time_keyboard=False
)

# Submenú: Flota
BOTONES_FLOTA = [
    ["👥 Conductores", "🗺️ Estado de la flota"],
    ["⬅️ Volver al menú"]
]

teclado_flota = ReplyKeyboardMarkup(
    BOTONES_FLOTA,
    resize_keyboard=True,
    one_time_keyboard=False
)

# Submenú: Informes
BOTONES_INFORMES = [
    ["📊 Estadísticas", "📈 Informe semanal"],
    ["💰 Rentabilidad"],
    ["⬅️ Volver al menú"]
]

teclado_informes = ReplyKeyboardMarkup(
    BOTONES_INFORMES,
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
    "📝 Registros": "registros",
    "📊 Resumen": "resumen",
    
    # Admin - Menú principal
    "📦 Viajes y rutas": "menu_viajes",
    "🚛 Flota": "menu_flota",
    "📊 Informes": "menu_informes",
    "🛠️ Gestiones": "gestiones",
    "⬅️ Volver al menú": "volver_menu",
    
    # Admin - Submenú Viajes
    "📦 Todos los viajes": "todos_viajes",
    "📋 Consultar rutas": "consultar_rutas",
    "🤖 Asignar viajes": "asignar",
    "🔄 Modificar viaje en ruta": "modificar_viaje_ruta",
    
    # Admin - Submenú Flota
    "👥 Conductores": "conductores",
    "🗺️ Estado de la flota": "estado_flota",
    
    # Admin - Submenú Informes
    "📊 Estadísticas": "estadisticas",
    "📈 Informe semanal": "informe_semanal",
    "💰 Rentabilidad": "rentabilidad",
    
    # No vinculado
    "🔗 Vincularme": "vincular",
}


def es_boton(texto: str) -> bool:
    """Verifica si el texto es un botón conocido"""
    return texto in MAPEO_BOTONES


def obtener_accion_boton(texto: str) -> str:
    """Devuelve la acción asociada a un botón"""
    return MAPEO_BOTONES.get(texto, "")
