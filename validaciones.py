"""
VALIDACIONES v2.0
==================
Módulo de validación y NORMALIZACIÓN de datos para el bot de transporte.
Valida y formatea todos los campos antes de guardar en Excel/BD.

Características:
- Valida formato correcto
- Normaliza datos (mayúsculas, formato precio, corrección ciudades)
- Mensajes de error claros en español

Uso:
    from validaciones import validar_telefono, validar_matricula, normalizar_ciudad, etc.
    
    resultado = validar_telefono("666111222")
    if resultado['valido']:
        telefono_limpio = resultado['valor']
    else:
        mensaje_error = resultado['error']
"""

import re
import logging
from typing import Dict, Optional, Union
from difflib import get_close_matches

logger = logging.getLogger(__name__)


# ============================================================
# DICCIONARIO DE CIUDADES CONOCIDAS (para normalizar)
# ============================================================

CIUDADES_CONOCIDAS = {
    # Navarra
    "AZAGRA": "AZAGRA", "TUDELA": "TUDELA", "PAMPLONA": "PAMPLONA",
    "MELIDA": "MÉLIDA", "MÉLIDA": "MÉLIDA", "PERALTA": "PERALTA",
    "ESTELLA": "ESTELLA", "TAFALLA": "TAFALLA", "SAN ADRIAN": "SAN ADRIÁN",
    "SAN ADRIÁN": "SAN ADRIÁN", "LODOSA": "LODOSA", "MENDAVIA": "MENDAVIA",
    "CORELLA": "CORELLA", "CINTRUENIGO": "CINTRUÉNIGO", "CINTRUÉNIGO": "CINTRUÉNIGO",
    "CARCASTILLO": "CARCASTILLO", "VILLAFRANCA": "VILLAFRANCA",
    
    # La Rioja
    "CALAHORRA": "CALAHORRA", "LOGROÑO": "LOGROÑO", "LOGRONO": "LOGROÑO",
    "ALFARO": "ALFARO", "ARNEDO": "ARNEDO", "AUTOL": "AUTOL",
    "HARO": "HARO", "NAJERA": "NÁJERA", "NÁJERA": "NÁJERA",
    "QUEL": "QUEL", "RINCON DE SOTO": "RINCÓN DE SOTO",
    
    # Aragón
    "ZARAGOZA": "ZARAGOZA", "HUESCA": "HUESCA", "TERUEL": "TERUEL",
    "CALATAYUD": "CALATAYUD", "EJEA": "EJEA DE LOS CABALLEROS",
    
    # Cataluña
    "BARCELONA": "BARCELONA", "BARCELONE": "BARCELONA", "BARNA": "BARCELONA",
    "LLEIDA": "LLEIDA", "LERIDA": "LLEIDA", "TARRAGONA": "TARRAGONA",
    "GIRONA": "GIRONA", "GERONA": "GIRONA", "VIC": "VIC",
    "SABADELL": "SABADELL", "TERRASSA": "TERRASSA", "MATARO": "MATARÓ",
    "MATARÓ": "MATARÓ", "REUS": "REUS", "FIGUERES": "FIGUERES",
    "MANRESA": "MANRESA", "GRANOLLERS": "GRANOLLERS",
    
    # Madrid
    "MADRID": "MADRID", "MADRI": "MADRID", "MERCAMADRID": "MERCAMADRID",
    "GETAFE": "GETAFE", "ALCALA": "ALCALÁ DE HENARES", "ALCALÁ": "ALCALÁ DE HENARES",
    "TORREJON": "TORREJÓN DE ARDOZ", "TORREJÓN": "TORREJÓN DE ARDOZ",
    "MOSTOLES": "MÓSTOLES", "MÓSTOLES": "MÓSTOLES", "LEGANES": "LEGANÉS",
    "LEGANÉS": "LEGANÉS", "FUENLABRADA": "FUENLABRADA", "ALCORCON": "ALCORCÓN",
    "ALCORCÓN": "ALCORCÓN", "COSLADA": "COSLADA", "SAN FERNANDO": "SAN FERNANDO DE HENARES",
    
    # País Vasco
    "BILBAO": "BILBAO", "BILBO": "BILBAO", "VITORIA": "VITORIA-GASTEIZ",
    "VITORIA-GASTEIZ": "VITORIA-GASTEIZ", "SAN SEBASTIAN": "SAN SEBASTIÁN",
    "SAN SEBASTIÁN": "SAN SEBASTIÁN", "DONOSTIA": "SAN SEBASTIÁN",
    "IRUN": "IRÚN", "IRÚN": "IRÚN", "EIBAR": "EIBAR", "DURANGO": "DURANGO",
    "BARAKALDO": "BARAKALDO", "GETXO": "GETXO", "PORTUGALETE": "PORTUGALETE",
    
    # Cantabria / Asturias / Galicia
    "SANTANDER": "SANTANDER", "OVIEDO": "OVIEDO", "GIJON": "GIJÓN",
    "GIJÓN": "GIJÓN", "AVILES": "AVILÉS", "AVILÉS": "AVILÉS",
    "VIGO": "VIGO", "CORUÑA": "A CORUÑA", "A CORUÑA": "A CORUÑA",
    "LA CORUÑA": "A CORUÑA", "SANTIAGO": "SANTIAGO DE COMPOSTELA",
    "OURENSE": "OURENSE", "ORENSE": "OURENSE", "LUGO": "LUGO",
    "PONTEVEDRA": "PONTEVEDRA", "FERROL": "FERROL",
    
    # Castilla y León
    "VALLADOLID": "VALLADOLID", "BURGOS": "BURGOS", "SALAMANCA": "SALAMANCA",
    "LEON": "LEÓN", "LEÓN": "LEÓN", "PALENCIA": "PALENCIA",
    "ZAMORA": "ZAMORA", "SORIA": "SORIA", "SEGOVIA": "SEGOVIA",
    "AVILA": "ÁVILA", "ÁVILA": "ÁVILA", "PONFERRADA": "PONFERRADA",
    
    # Castilla-La Mancha
    "TOLEDO": "TOLEDO", "ALBACETE": "ALBACETE", "CIUDAD REAL": "CIUDAD REAL",
    "GUADALAJARA": "GUADALAJARA", "CUENCA": "CUENCA", "TALAVERA": "TALAVERA DE LA REINA",
    "PUERTOLLANO": "PUERTOLLANO", "TOMELLOSO": "TOMELLOSO",
    
    # Valencia / Murcia
    "VALENCIA": "VALENCIA", "ALICANTE": "ALICANTE", "CASTELLON": "CASTELLÓN",
    "CASTELLÓN": "CASTELLÓN", "ELCHE": "ELCHE", "TORREVIEJA": "TORREVIEJA",
    "ORIHUELA": "ORIHUELA", "BENIDORM": "BENIDORM", "GANDIA": "GANDÍA",
    "GANDÍA": "GANDÍA", "ALZIRA": "ALZIRA", "SAGUNTO": "SAGUNTO",
    "MURCIA": "MURCIA", "CARTAGENA": "CARTAGENA", "LORCA": "LORCA",
    "MOLINA": "MOLINA DE SEGURA", "ALCANTARILLA": "ALCANTARILLA",
    "CIEZA": "CIEZA", "YECLA": "YECLA", "JUMILLA": "JUMILLA",
    
    # Andalucía
    "SEVILLA": "SEVILLA", "MALAGA": "MÁLAGA", "MÁLAGA": "MÁLAGA",
    "GRANADA": "GRANADA", "CORDOBA": "CÓRDOBA", "CÓRDOBA": "CÓRDOBA",
    "ALMERIA": "ALMERÍA", "ALMERÍA": "ALMERÍA", "JAEN": "JAÉN", "JAÉN": "JAÉN",
    "CADIZ": "CÁDIZ", "CÁDIZ": "CÁDIZ", "HUELVA": "HUELVA",
    "JEREZ": "JEREZ DE LA FRONTERA", "MARBELLA": "MARBELLA",
    "ALGECIRAS": "ALGECIRAS", "LINARES": "LINARES", "MOTRIL": "MOTRIL",
    "ROQUETAS": "ROQUETAS DE MAR", "DOS HERMANAS": "DOS HERMANAS",
    "ALCALA DE GUADAIRA": "ALCALÁ DE GUADAÍRA",
    
    # Extremadura
    "BADAJOZ": "BADAJOZ", "CACERES": "CÁCERES", "CÁCERES": "CÁCERES",
    "MERIDA": "MÉRIDA", "MÉRIDA": "MÉRIDA", "PLASENCIA": "PLASENCIA",
    "DON BENITO": "DON BENITO", "ALMENDRALEJO": "ALMENDRALEJO",
    
    # Baleares / Canarias
    "PALMA": "PALMA DE MALLORCA", "PALMA DE MALLORCA": "PALMA DE MALLORCA",
    "IBIZA": "IBIZA", "MAHON": "MAHÓN", "MAHÓN": "MAHÓN",
    "LAS PALMAS": "LAS PALMAS DE GRAN CANARIA", "TENERIFE": "SANTA CRUZ DE TENERIFE",
    "SANTA CRUZ": "SANTA CRUZ DE TENERIFE",
    
    # Otros
    "JIJON": "GIJÓN", "JIJÓN": "GIJÓN",  # Error común
}

# Crear lista de ciudades para búsqueda fuzzy
LISTA_CIUDADES = list(set(CIUDADES_CONOCIDAS.values()))


def normalizar_ciudad(ciudad: str) -> str:
    """
    Normaliza el nombre de una ciudad.
    - Corrige errores tipográficos comunes
    - Pone mayúsculas
    - Añade tildes correctas
    
    Args:
        ciudad: Nombre de la ciudad (puede tener errores)
    
    Returns:
        Nombre normalizado de la ciudad
    """
    if not ciudad:
        return ""
    
    # Limpiar y poner en mayúsculas
    limpio = ciudad.upper().strip()
    limpio = ' '.join(limpio.split())  # Quitar espacios extra
    
    # Buscar en diccionario exacto
    if limpio in CIUDADES_CONOCIDAS:
        return CIUDADES_CONOCIDAS[limpio]
    
    # Buscar coincidencia aproximada (fuzzy)
    matches = get_close_matches(limpio, LISTA_CIUDADES, n=1, cutoff=0.8)
    if matches:
        logger.info(f"[NORMALIZAR] Ciudad '{ciudad}' normalizada a '{matches[0]}'")
        return matches[0]
    
    # Si no encuentra, devolver en mayúsculas
    return limpio


def formatear_precio(precio: float) -> str:
    """
    Formatea un precio para el Excel.
    
    Args:
        precio: Valor numérico (ej: 956.0)
    
    Returns:
        String formateado (ej: "956.00€")
    """
    if precio is None:
        return "0.00€"
    
    try:
        valor = float(precio)
        return f"{valor:.2f}€"
    except (ValueError, TypeError):
        return f"{precio}€"


def formatear_km(km: int) -> str:
    """
    Formatea los km para el Excel.
    
    Args:
        km: Valor numérico (ej: 500)
    
    Returns:
        String formateado (ej: "500")
    """
    if km is None:
        return "0"
    
    try:
        return str(int(km))
    except (ValueError, TypeError):
        return str(km)


# ============================================================
# CONFIGURACIÓN DE LÍMITES
# ============================================================

LIMITES = {
    'precio_min': 0,
    'precio_max': 15000,      # Máximo 15.000€ por viaje
    'km_min': 1,
    'km_max': 3500,           # Máximo 3.500 km (España-Europa)
    'nombre_min': 3,
    'nombre_max': 50,
    'lugar_min': 2,
    'lugar_max': 100,
    'cliente_min': 2,
    'cliente_max': 50,
    'mercancia_min': 2,
    'mercancia_max': 100,
    'observaciones_max': 500,
}


# ============================================================
# VALIDACIÓN DE TELÉFONO
# ============================================================

def validar_telefono(telefono: str) -> Dict:
    """
    Valida un número de teléfono español.
    
    Formatos aceptados:
    - 666111222
    - 666 111 222
    - +34 666111222
    - 0034 666111222
    
    Returns:
        {'valido': True, 'valor': '666111222'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not telefono:
        return {'valido': False, 'error': '❌ El teléfono no puede estar vacío'}
    
    # Limpiar: quitar espacios, guiones, paréntesis, prefijos
    limpio = telefono.strip()
    limpio = re.sub(r'[\s\-\(\)\.]', '', limpio)  # Quitar espacios, guiones, etc.
    limpio = re.sub(r'^(\+34|0034|34)', '', limpio)  # Quitar prefijo España
    
    # Verificar que solo tiene números
    if not limpio.isdigit():
        return {
            'valido': False, 
            'error': '❌ El teléfono solo puede contener números\n_Ejemplo: 666111222_'
        }
    
    # Verificar longitud
    if len(limpio) != 9:
        return {
            'valido': False, 
            'error': f'❌ El teléfono debe tener 9 dígitos (tienes {len(limpio)})\n_Ejemplo: 666111222_'
        }
    
    # Verificar que empieza por 6, 7, 8 o 9
    if limpio[0] not in '6789':
        return {
            'valido': False, 
            'error': '❌ El teléfono debe empezar por 6, 7, 8 o 9\n_Ejemplo: 666111222_'
        }
    
    logger.info(f"[VALIDACION] Teléfono válido: {limpio}")
    return {'valido': True, 'valor': limpio}


# ============================================================
# VALIDACIÓN DE MATRÍCULA TRACTORA
# ============================================================

def validar_matricula_tractora(matricula: str) -> Dict:
    """
    Valida una matrícula de tractora española.
    
    Formatos aceptados:
    - 1234ABC (nuevo formato)
    - 1234 ABC
    - AB1234CD (formato antiguo)
    - E-1234-ABC (con guiones)
    
    Returns:
        {'valido': True, 'valor': '1234ABC'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not matricula:
        return {'valido': False, 'error': '❌ La matrícula no puede estar vacía'}
    
    # Limpiar: mayúsculas, quitar espacios y guiones
    limpio = matricula.upper().strip()
    limpio = re.sub(r'[\s\-]', '', limpio)
    
    # Quitar prefijo E de España si lo tiene
    limpio = re.sub(r'^E', '', limpio)
    
    # Verificar longitud mínima
    if len(limpio) < 6:
        return {
            'valido': False, 
            'error': '❌ Matrícula demasiado corta\n_Ejemplo: 1234ABC_'
        }
    
    if len(limpio) > 10:
        return {
            'valido': False, 
            'error': '❌ Matrícula demasiado larga\n_Ejemplo: 1234ABC_'
        }
    
    # Verificar que tiene letras y números
    tiene_letras = bool(re.search(r'[A-Z]', limpio))
    tiene_numeros = bool(re.search(r'\d', limpio))
    
    if not tiene_letras or not tiene_numeros:
        return {
            'valido': False, 
            'error': '❌ La matrícula debe tener letras y números\n_Ejemplo: 1234ABC_'
        }
    
    # Patrón nuevo formato español: 4 números + 3 letras (sin vocales)
    patron_nuevo = r'^\d{4}[BCDFGHJKLMNPRSTVWXYZ]{3}$'
    
    # Patrón antiguo: letras + números + letras
    patron_antiguo = r'^[A-Z]{1,2}\d{4}[A-Z]{1,2}$'
    
    # Patrón genérico (más permisivo para matrículas extranjeras)
    patron_generico = r'^[A-Z0-9]{6,10}$'
    
    if re.match(patron_nuevo, limpio) or re.match(patron_antiguo, limpio) or re.match(patron_generico, limpio):
        logger.info(f"[VALIDACION] Matrícula tractora válida: {limpio}")
        return {'valido': True, 'valor': limpio}
    
    return {
        'valido': False, 
        'error': '❌ Formato de matrícula no válido\n_Ejemplo: 1234ABC_'
    }


# ============================================================
# VALIDACIÓN DE MATRÍCULA REMOLQUE
# ============================================================

def validar_matricula_remolque(matricula: str) -> Dict:
    """
    Valida una matrícula de remolque española.
    
    Formatos aceptados:
    - R1234ABC
    - R-1234-ABC
    - 1234ABC (sin R)
    
    Returns:
        {'valido': True, 'valor': 'R1234ABC'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not matricula:
        return {'valido': False, 'error': '❌ La matrícula no puede estar vacía'}
    
    # Limpiar: mayúsculas, quitar espacios y guiones
    limpio = matricula.upper().strip()
    limpio = re.sub(r'[\s\-]', '', limpio)
    
    # Quitar R inicial si existe para validar el resto
    sin_r = limpio[1:] if limpio.startswith('R') else limpio
    
    # Verificar longitud mínima
    if len(sin_r) < 6:
        return {
            'valido': False, 
            'error': '❌ Matrícula demasiado corta\n_Ejemplo: R1234ABC_'
        }
    
    if len(sin_r) > 10:
        return {
            'valido': False, 
            'error': '❌ Matrícula demasiado larga\n_Ejemplo: R1234ABC_'
        }
    
    # Verificar que tiene letras y números
    tiene_letras = bool(re.search(r'[A-Z]', sin_r))
    tiene_numeros = bool(re.search(r'\d', sin_r))
    
    if not tiene_letras or not tiene_numeros:
        return {
            'valido': False, 
            'error': '❌ La matrícula debe tener letras y números\n_Ejemplo: R1234ABC_'
        }
    
    # Añadir R si no la tiene
    if not limpio.startswith('R'):
        limpio = 'R' + limpio
    
    logger.info(f"[VALIDACION] Matrícula remolque válida: {limpio}")
    return {'valido': True, 'valor': limpio}


# ============================================================
# VALIDACIÓN DE PRECIO
# ============================================================

def validar_precio(precio: str) -> Dict:
    """
    Valida un precio de viaje.
    
    Formatos aceptados:
    - 1500
    - 1500.50
    - 1.500,50 (formato español)
    - 1500€
    - 1500 euros
    
    Returns:
        {'valido': True, 'valor': 1500.50} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not precio:
        return {'valido': False, 'error': '❌ El precio no puede estar vacío'}
    
    # Limpiar: quitar espacios, símbolo €, palabra euros
    limpio = str(precio).strip().lower()
    limpio = re.sub(r'[€euros\s]', '', limpio)
    
    # Convertir formato español (1.500,50) a formato estándar (1500.50)
    if ',' in limpio and '.' in limpio:
        # Formato 1.500,50 -> quitar puntos de miles, cambiar coma por punto
        limpio = limpio.replace('.', '').replace(',', '.')
    elif ',' in limpio:
        # Formato 1500,50 -> cambiar coma por punto
        limpio = limpio.replace(',', '.')
    
    try:
        valor = float(limpio)
    except ValueError:
        return {
            'valido': False, 
            'error': '❌ El precio debe ser un número\n_Ejemplo: 1500 o 1500.50_'
        }
    
    # Verificar que no es negativo
    if valor < LIMITES['precio_min']:
        return {
            'valido': False, 
            'error': '❌ El precio no puede ser negativo'
        }
    
    # Verificar máximo razonable
    if valor > LIMITES['precio_max']:
        return {
            'valido': False, 
            'error': f'⚠️ ¿Seguro? El precio parece muy alto ({valor}€)\n_Máximo permitido: {LIMITES["precio_max"]}€_'
        }
    
    # Redondear a 2 decimales
    valor = round(valor, 2)
    
    # Devolver valor numérico Y formateado para Excel
    valor_formateado = formatear_precio(valor)
    
    logger.info(f"[VALIDACION] Precio válido: {valor_formateado}")
    return {
        'valido': True, 
        'valor': valor,  # Valor numérico para BD
        'valor_excel': valor_formateado  # Valor formateado para Excel
    }


# ============================================================
# VALIDACIÓN DE KILÓMETROS
# ============================================================

def validar_km(km: str) -> Dict:
    """
    Valida los kilómetros de un viaje.
    
    Formatos aceptados:
    - 500
    - 500 km
    - 500km
    
    Returns:
        {'valido': True, 'valor': 500} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not km:
        return {'valido': False, 'error': '❌ Los km no pueden estar vacíos'}
    
    # Limpiar: quitar espacios y "km"
    limpio = str(km).strip().lower()
    limpio = re.sub(r'[km\s]', '', limpio)
    
    # Convertir coma a punto por si acaso
    limpio = limpio.replace(',', '.')
    
    try:
        valor = float(limpio)
        valor = int(round(valor))  # Redondear a entero
    except ValueError:
        return {
            'valido': False, 
            'error': '❌ Los km deben ser un número\n_Ejemplo: 500_'
        }
    
    # Verificar mínimo
    if valor < LIMITES['km_min']:
        return {
            'valido': False, 
            'error': f'❌ Los km deben ser al menos {LIMITES["km_min"]}'
        }
    
    # Verificar máximo razonable
    if valor > LIMITES['km_max']:
        return {
            'valido': False, 
            'error': f'⚠️ ¿Seguro? {valor} km parece demasiado\n_Máximo permitido: {LIMITES["km_max"]} km_'
        }
    
    logger.info(f"[VALIDACION] Km válidos: {valor}")
    return {'valido': True, 'valor': valor}


# ============================================================
# VALIDACIÓN DE NOMBRE
# ============================================================

def validar_nombre(nombre: str) -> Dict:
    """
    Valida un nombre de conductor.
    
    Reglas:
    - Mínimo 3 caracteres
    - Solo letras, espacios y algunos caracteres especiales (ñ, acentos)
    - No solo números
    
    Returns:
        {'valido': True, 'valor': 'JUAN PÉREZ'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not nombre:
        return {'valido': False, 'error': '❌ El nombre no puede estar vacío'}
    
    # Limpiar espacios extra
    limpio = ' '.join(nombre.strip().split())
    
    # Verificar longitud mínima
    if len(limpio) < LIMITES['nombre_min']:
        return {
            'valido': False, 
            'error': f'❌ El nombre debe tener al menos {LIMITES["nombre_min"]} caracteres'
        }
    
    # Verificar longitud máxima
    if len(limpio) > LIMITES['nombre_max']:
        return {
            'valido': False, 
            'error': f'❌ El nombre es demasiado largo (máx {LIMITES["nombre_max"]} caracteres)'
        }
    
    # Verificar que no es solo números
    if limpio.replace(' ', '').isdigit():
        return {
            'valido': False, 
            'error': '❌ El nombre no puede ser solo números\n_Ejemplo: JUAN PÉREZ_'
        }
    
    # Verificar caracteres válidos (letras, espacios, acentos, ñ)
    patron = r'^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s]+$'
    if not re.match(patron, limpio):
        return {
            'valido': False, 
            'error': '❌ El nombre solo puede contener letras\n_Ejemplo: JUAN PÉREZ_'
        }
    
    # Convertir a mayúsculas
    limpio = limpio.upper()
    
    logger.info(f"[VALIDACION] Nombre válido: {limpio}")
    return {'valido': True, 'valor': limpio}


# ============================================================
# VALIDACIÓN DE LUGAR (CARGA/DESCARGA)
# ============================================================

def validar_lugar(lugar: str, tipo: str = "lugar") -> Dict:
    """
    Valida un lugar de carga o descarga.
    
    Reglas:
    - Mínimo 2 caracteres
    - No solo números
    - Puede contener letras, números, espacios, paréntesis
    
    Args:
        lugar: El lugar a validar
        tipo: "carga" o "descarga" para mensajes personalizados
    
    Returns:
        {'valido': True, 'valor': 'BARCELONA'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not lugar:
        return {'valido': False, 'error': f'❌ El lugar de {tipo} no puede estar vacío'}
    
    # Limpiar espacios extra
    limpio = ' '.join(lugar.strip().split())
    
    # Verificar longitud mínima
    if len(limpio) < LIMITES['lugar_min']:
        return {
            'valido': False, 
            'error': f'❌ El lugar de {tipo} debe tener al menos {LIMITES["lugar_min"]} caracteres'
        }
    
    # Verificar longitud máxima
    if len(limpio) > LIMITES['lugar_max']:
        return {
            'valido': False, 
            'error': f'❌ El lugar de {tipo} es demasiado largo'
        }
    
    # Verificar que no es solo números
    if limpio.replace(' ', '').isdigit():
        return {
            'valido': False, 
            'error': f'❌ El lugar de {tipo} no puede ser solo números\n_Ejemplo: BARCELONA_'
        }
    
    # NORMALIZAR CIUDAD (corregir errores, añadir tildes)
    limpio = normalizar_ciudad(limpio)
    
    logger.info(f"[VALIDACION] Lugar de {tipo} válido: {limpio}")
    return {'valido': True, 'valor': limpio}


def validar_lugar_carga(lugar: str) -> Dict:
    """Valida lugar de carga"""
    return validar_lugar(lugar, "carga")


def validar_lugar_descarga(lugar: str) -> Dict:
    """Valida lugar de descarga"""
    return validar_lugar(lugar, "descarga")


# ============================================================
# VALIDACIÓN DE CLIENTE
# ============================================================

def validar_cliente(cliente: str) -> Dict:
    """
    Valida un nombre de cliente.
    
    Reglas:
    - Mínimo 2 caracteres
    - Puede contener letras, números, espacios
    
    Returns:
        {'valido': True, 'valor': 'MERCADONA'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not cliente:
        return {'valido': False, 'error': '❌ El cliente no puede estar vacío'}
    
    # Limpiar espacios extra
    limpio = ' '.join(cliente.strip().split())
    
    # Verificar longitud mínima
    if len(limpio) < LIMITES['cliente_min']:
        return {
            'valido': False, 
            'error': f'❌ El cliente debe tener al menos {LIMITES["cliente_min"]} caracteres'
        }
    
    # Verificar longitud máxima
    if len(limpio) > LIMITES['cliente_max']:
        return {
            'valido': False, 
            'error': f'❌ El nombre del cliente es demasiado largo'
        }
    
    # Convertir a mayúsculas
    limpio = limpio.upper()
    
    logger.info(f"[VALIDACION] Cliente válido: {limpio}")
    return {'valido': True, 'valor': limpio}


# ============================================================
# VALIDACIÓN DE MERCANCÍA
# ============================================================

def validar_mercancia(mercancia: str) -> Dict:
    """
    Valida el tipo de mercancía.
    
    Reglas:
    - Mínimo 2 caracteres
    - Puede contener letras, números, espacios
    
    Returns:
        {'valido': True, 'valor': 'PALETS FRUTA'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not mercancia:
        return {'valido': False, 'error': '❌ La mercancía no puede estar vacía'}
    
    # Limpiar espacios extra
    limpio = ' '.join(mercancia.strip().split())
    
    # Verificar longitud mínima
    if len(limpio) < LIMITES['mercancia_min']:
        return {
            'valido': False, 
            'error': f'❌ La mercancía debe tener al menos {LIMITES["mercancia_min"]} caracteres'
        }
    
    # Verificar longitud máxima
    if len(limpio) > LIMITES['mercancia_max']:
        return {
            'valido': False, 
            'error': '❌ La descripción de mercancía es demasiado larga'
        }
    
    # Convertir a mayúsculas
    limpio = limpio.upper()
    
    logger.info(f"[VALIDACION] Mercancía válida: {limpio}")
    return {'valido': True, 'valor': limpio}


# ============================================================
# VALIDACIÓN DE OBSERVACIONES
# ============================================================

def validar_observaciones(obs: str) -> Dict:
    """
    Valida las observaciones (campo opcional).
    
    Reglas:
    - Puede estar vacío
    - Máximo 500 caracteres
    
    Returns:
        {'valido': True, 'valor': 'texto limpio'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not obs:
        return {'valido': True, 'valor': ''}
    
    # Limpiar espacios extra
    limpio = ' '.join(obs.strip().split())
    
    # Verificar longitud máxima
    if len(limpio) > LIMITES['observaciones_max']:
        return {
            'valido': False, 
            'error': f'❌ Las observaciones son demasiado largas (máx {LIMITES["observaciones_max"]} caracteres)'
        }
    
    logger.info(f"[VALIDACION] Observaciones válidas: {limpio[:50]}...")
    return {'valido': True, 'valor': limpio}


# ============================================================
# VALIDACIÓN DE ZONA
# ============================================================

ZONAS_VALIDAS = [
    "ZONA NORTE", "ZONA SUR", "ZONA ESTE", "ZONA OESTE", "ZONA CENTRO",
    "NORTE", "SUR", "ESTE", "OESTE", "CENTRO"
]

def validar_zona(zona: str) -> Dict:
    """
    Valida una zona.
    
    Returns:
        {'valido': True, 'valor': 'ZONA NORTE'} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if not zona:
        return {'valido': False, 'error': '❌ La zona no puede estar vacía'}
    
    limpio = zona.upper().strip()
    
    # Añadir "ZONA " si no lo tiene
    if limpio in ["NORTE", "SUR", "ESTE", "OESTE", "CENTRO"]:
        limpio = f"ZONA {limpio}"
    
    if limpio not in ZONAS_VALIDAS:
        return {
            'valido': False, 
            'error': '❌ Zona no válida\n_Opciones: NORTE, SUR, ESTE, OESTE, CENTRO_'
        }
    
    logger.info(f"[VALIDACION] Zona válida: {limpio}")
    return {'valido': True, 'valor': limpio}


# ============================================================
# VALIDACIÓN DE FILA EXCEL (CRÍTICO)
# ============================================================

def validar_fila_excel(fila: int, max_fila: int = 10000) -> Dict:
    """
    Valida que una fila de Excel es válida.
    
    Args:
        fila: Número de fila
        max_fila: Máxima fila permitida
    
    Returns:
        {'valido': True, 'valor': 5} o
        {'valido': False, 'error': 'mensaje de error'}
    """
    if fila is None:
        return {
            'valido': False, 
            'error': '❌ Error interno: fila_excel es None'
        }
    
    try:
        fila = int(fila)
    except (ValueError, TypeError):
        return {
            'valido': False, 
            'error': f'❌ Error interno: fila_excel no es un número ({fila})'
        }
    
    if fila < 1:
        return {
            'valido': False, 
            'error': f'❌ Error interno: fila_excel inválida ({fila})'
        }
    
    if fila > max_fila:
        return {
            'valido': False, 
            'error': f'❌ Error interno: fila_excel fuera de rango ({fila})'
        }
    
    return {'valido': True, 'valor': fila}


# ============================================================
# FUNCIÓN HELPER PARA VALIDAR MÚLTIPLES CAMPOS
# ============================================================

def validar_campos(datos: Dict, campos_requeridos: Dict) -> Dict:
    """
    Valida múltiples campos a la vez.
    
    Args:
        datos: Dict con los datos a validar {'telefono': '666...', 'nombre': 'Juan'}
        campos_requeridos: Dict con campo -> función validadora
            {'telefono': validar_telefono, 'nombre': validar_nombre}
    
    Returns:
        {
            'valido': True/False,
            'valores': {'telefono': '666111222', 'nombre': 'JUAN'},
            'errores': ['Error en teléfono: ...']
        }
    """
    valores = {}
    errores = []
    
    for campo, validador in campos_requeridos.items():
        valor_raw = datos.get(campo, '')
        resultado = validador(valor_raw)
        
        if resultado['valido']:
            valores[campo] = resultado['valor']
        else:
            errores.append(f"*{campo}*: {resultado['error']}")
    
    return {
        'valido': len(errores) == 0,
        'valores': valores,
        'errores': errores
    }


# ============================================================
# TESTS
# ============================================================

if __name__ == "__main__":
    print("=== TESTS DE VALIDACIÓN Y NORMALIZACIÓN ===\n")
    
    # Test teléfono
    print("📱 TELÉFONOS:")
    tests_tel = ["666111222", "+34 666 111 222", "123456789", "66611122", "abcdefghi"]
    for t in tests_tel:
        r = validar_telefono(t)
        estado = "✅" if r['valido'] else "❌"
        print(f"  {estado} '{t}' -> {r}")
    
    print("\n🚛 MATRÍCULAS TRACTORA:")
    tests_mat = ["1234ABC", "1234 ABC", "AB1234CD", "123", "ABCDEFGH"]
    for t in tests_mat:
        r = validar_matricula_tractora(t)
        estado = "✅" if r['valido'] else "❌"
        print(f"  {estado} '{t}' -> {r}")
    
    print("\n💰 PRECIOS (con formato Excel):")
    tests_precio = ["1500", "1.500,50", "1500€", "956", "-100", "20000"]
    for t in tests_precio:
        r = validar_precio(t)
        estado = "✅" if r['valido'] else "❌"
        if r['valido']:
            print(f"  {estado} '{t}' -> {r['valor']} (Excel: {r['valor_excel']})")
        else:
            print(f"  {estado} '{t}' -> {r['error']}")
    
    print("\n📏 KILÓMETROS:")
    tests_km = ["500", "500 km", "0", "5000"]
    for t in tests_km:
        r = validar_km(t)
        estado = "✅" if r['valido'] else "❌"
        print(f"  {estado} '{t}' -> {r}")
    
    print("\n👤 NOMBRES:")
    tests_nom = ["Juan Pérez", "J", "12345", "LUIS GARCÍA LÓPEZ"]
    for t in tests_nom:
        r = validar_nombre(t)
        estado = "✅" if r['valido'] else "❌"
        print(f"  {estado} '{t}' -> {r}")
    
    print("\n🏙️ NORMALIZACIÓN DE CIUDADES:")
    tests_ciudades = [
        "barcelone",      # Error tipográfico
        "BARCELONE",      # Error en mayúsculas
        "barcelona",      # Minúsculas
        "barna",          # Abreviatura
        "madri",          # Incompleto
        "gijon",          # Sin tilde
        "GIJÓN",          # Con tilde
        "logroño",        # Sin tilde
        "vitoria",        # Sin guión
        "san sebastian",  # Sin tilde
        "murcia",         # Normal
        "DESCONOCIDA",    # Ciudad no en diccionario
    ]
    for t in tests_ciudades:
        normalizado = normalizar_ciudad(t)
        cambio = "→" if t.upper() != normalizado else "="
        print(f"  '{t}' {cambio} '{normalizado}'")
    
    print("\n📍 LUGARES DE CARGA/DESCARGA:")
    tests_lugares = ["barcelone", "madri", "gijon", "123", ""]
    for t in tests_lugares:
        r = validar_lugar_carga(t)
        estado = "✅" if r['valido'] else "❌"
        if r['valido']:
            print(f"  {estado} '{t}' -> '{r['valor']}'")
        else:
            print(f"  {estado} '{t}' -> {r['error'][:50]}...")
    
    print("\n✅ Tests completados")
