"""
TECLADOS - BOTONES RÁPIDOS v2.4
================================
Teclados con botones para conductores y admins.

Cambios v2.4:
- Añadido "📸 Registrar albarán" para conductores

Cambios v2.3:
- Eliminado "✏️ Modificar camionero" (fusionado en panel Conductores)
- Eliminado "🗺️ Estado de la flota" (fusionado en panel Conductores)

Cambios v2.2:
- Añadido botón "🔄 Modificar viaje en ruta" para admin
"""

from telegram import ReplyKeyboardMarkup, KeyboardButton


# ============================================================
# TECLADO CONDUCTOR
# ============================================================

BOTONES_CONDUCTOR = [
    ["🚛 Mis viajes", "🚚 Mi camión"],
    ["⛽ Gasolineras", "📍 Mi ubicación"],
    ["📝 Registros", "📸 Registrar albarán"],
    ["⚠️ Incidencia", "📊 Resumen"]
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
    ["📦 Viajes y rutas", "🚛 Flota"],
    ["📊 Informes", "🔄 Sincronizar"],
    ["📅 Cierre de día"]
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
    ["➕ Añadir viaje", "✏️ Modificar viaje"],
    ["⬅️ Volver al menú"]
]

teclado_viajes = ReplyKeyboardMarkup(
    BOTONES_VIAJES,
    resize_keyboard=True,
    one_time_keyboard=False
)

# Submenú: Flota (SIMPLIFICADO - v2.3)
BOTONES_FLOTA = [
    ["👥 Conductores"],
    ["➕ Añadir camionero"],
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
    ["💰 Rentabilidad", "📊 Dashboard"],
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
    "📸 Registrar albarán": "albaran",
    "⚠️ Incidencia": "incidencia",
    "📊 Resumen": "resumen",
    
    # Admin - Menú principal
    "📦 Viajes y rutas": "menu_viajes",
    "🚛 Flota": "menu_flota",
    "📊 Informes": "menu_informes",
    "🔄 Sincronizar": "sincronizar",
    "📅 Cierre de día": "cierre_dia",
    "⬅️ Volver al menú": "volver_menu",
    
    
    # Admin - Submenú Viajes
    "📦 Todos los viajes": "todos_viajes",
    "📋 Consultar rutas": "consultar_rutas",
    "🤖 Asignar viajes": "asignar",
    "🔄 Modificar viaje en ruta": "modificar_viaje_ruta",
    "➕ Añadir viaje": "añadir_viaje",
    "✏️ Modificar viaje": "modificar_viaje",
    
    # Admin - Submenú Flota (SIMPLIFICADO)
    "👥 Conductores": "conductores",
    "➕ Añadir camionero": "añadir_camionero",
    
    # Admin - Submenú Informes
    "📊 Estadísticas": "estadisticas",
    "📈 Informe semanal": "informe_semanal",
    "💰 Rentabilidad": "rentabilidad",
    "📊 Dashboard": "dashboard",
    
    # No vinculado
    "🔗 Vincularme": "vincular",
}


def es_boton(texto: str) -> bool:
    """Verifica si el texto es un botón conocido"""
    return texto in MAPEO_BOTONES


def obtener_accion_boton(texto: str) -> str:
    """Devuelve la acción asociada a un botón"""
    return MAPEO_BOTONES.get(texto, "")
