"""
APIS EXTERNAS v3.0
==================
Integra APIs de:
- Gasolineras (Ministerio España - GRATIS)
- Tráfico (TomTom)
- Clima (OpenWeatherMap)

IMPORTANTE: Usa TLS 1.2 forzado para compatibilidad con API del Ministerio
"""

import logging
import math
import requests
from requests.adapters import HTTPAdapter
from typing import Optional, List
from datetime import datetime
 
logger = logging.getLogger(__name__)


# ============================================================
# ADAPTADOR TLS PARA COMPATIBILIDAD
# ============================================================

class TLSAdapter(HTTPAdapter):
    """Adaptador que fuerza TLS 1.2 para conexiones problemáticas"""
    def init_poolmanager(self, *args, **kwargs):
        import ssl
        from urllib3.util.ssl_ import create_urllib3_context
        ctx = create_urllib3_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


def get_session():
    """Crea una sesión con TLS configurado"""
    session = requests.Session()
    session.mount('https://', TLSAdapter())
    return session


# ============================================================
# FUNCIONES DE UTILIDAD
# ============================================================

def calcular_distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia en km entre dos puntos usando Haversine"""
    if not all([lat1, lon1, lat2, lon2]):
        return 9999
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ============================================================
# COORDENADAS DE PROVINCIAS
# ============================================================

PROVINCIAS_POR_LUGAR = {
    # Navarra
    "AZAGRA": "Navarra", "TUDELA": "Navarra", "PAMPLONA": "Navarra",
    "MELIDA": "Navarra", "MÉLIDA": "Navarra", "PERALTA": "Navarra",
    "ESTELLA": "Navarra", "TAFALLA": "Navarra", "SAN ADRIAN": "Navarra",
    "LODOSA": "Navarra", "MENDAVIA": "Navarra", "CORELLA": "Navarra",
    
    # La Rioja
    "CALAHORRA": "La Rioja", "LOGROÑO": "La Rioja", "ALFARO": "La Rioja",
    "ARNEDO": "La Rioja", "AUTOL": "La Rioja", "HARO": "La Rioja",
    
    # Aragón
    "ZARAGOZA": "Zaragoza", "HUESCA": "Huesca", "TERUEL": "Teruel",
    
    # Cataluña
    "BARCELONA": "Barcelona", "LLEIDA": "Lleida", "TARRAGONA": "Tarragona",
    "GIRONA": "Girona", "VIC": "Barcelona",
    
    # Madrid
    "MADRID": "Madrid", "MERCAMADRID": "Madrid", "GETAFE": "Madrid",
    "ALCALA DE HENARES": "Madrid", "TORREJON": "Madrid",
    
    # País Vasco
    "BILBAO": "Bizkaia", "VITORIA": "Álava", "SAN SEBASTIAN": "Gipuzkoa",
    "DONOSTIA": "Gipuzkoa", "IRUN": "Gipuzkoa",
    
    # Cantabria / Asturias
    "SANTANDER": "Cantabria", "OVIEDO": "Asturias", "GIJON": "Asturias",
    "GIJÓN": "Asturias",
    
    # Galicia
    "VIGO": "Pontevedra", "CORUÑA": "A Coruña", "A CORUÑA": "A Coruña",
    "SANTIAGO": "A Coruña", "OURENSE": "Ourense", "LUGO": "Lugo",
    
    # Valencia / Murcia
    "VALENCIA": "Valencia", "ALICANTE": "Alicante", "MURCIA": "Murcia",
    "CASTELLON": "Castellón", "CARTAGENA": "Murcia",
    
    # Andalucía
    "SEVILLA": "Sevilla", "MALAGA": "Málaga", "GRANADA": "Granada",
    "CORDOBA": "Córdoba", "CADIZ": "Cádiz", "ALMERIA": "Almería",
    "JAEN": "Jaén", "HUELVA": "Huelva", "JEREZ": "Cádiz",
    
    # Extremadura
    "MERIDA": "Badajoz", "MÉRIDA": "Badajoz", "BADAJOZ": "Badajoz",
    "CACERES": "Cáceres", "PLASENCIA": "Cáceres",
    
    # Castilla y León
    "VALLADOLID": "Valladolid", "BURGOS": "Burgos", "SALAMANCA": "Salamanca",
    "LEON": "León", "PALENCIA": "Palencia", "ZAMORA": "Zamora",
    "SEGOVIA": "Segovia", "SORIA": "Soria", "AVILA": "Ávila",
    
    # Castilla-La Mancha
    "ALBACETE": "Albacete", "CIUDAD REAL": "Ciudad Real", "TOLEDO": "Toledo",
    "CUENCA": "Cuenca", "GUADALAJARA": "Guadalajara",
}


def obtener_provincia(lugar: str) -> str:
    """Obtiene la provincia de un lugar"""
    if not lugar:
        return "Navarra"
    lugar_upper = lugar.upper().strip()
    
    if lugar_upper in PROVINCIAS_POR_LUGAR:
        return PROVINCIAS_POR_LUGAR[lugar_upper]
    
    for nombre, prov in PROVINCIAS_POR_LUGAR.items():
        if nombre in lugar_upper or lugar_upper in nombre:
            return prov
    
    return "Navarra"


def obtener_provincias_ruta(origen: str, destino: str) -> List[str]:
    """Obtiene las provincias que atraviesa una ruta."""
    prov_origen = obtener_provincia(origen)
    prov_destino = obtener_provincia(destino)
    
    provincias = [prov_origen]
    
    RUTAS_INTERMEDIAS = {
        ("Navarra", "Madrid"): ["Soria", "Guadalajara"],
        ("Navarra", "Badajoz"): ["Soria", "Madrid", "Toledo", "Ciudad Real"],
        ("Navarra", "Sevilla"): ["Soria", "Madrid", "Córdoba"],
        ("Navarra", "Málaga"): ["Soria", "Madrid", "Jaén"],
        ("Navarra", "Barcelona"): ["Zaragoza", "Lleida"],
        ("Navarra", "Valencia"): ["Zaragoza", "Teruel"],
        ("Navarra", "A Coruña"): ["Burgos", "León", "Lugo"],
        ("Navarra", "Pontevedra"): ["Burgos", "León", "Ourense"],
        ("Navarra", "Asturias"): ["Burgos", "Cantabria"],
        ("Navarra", "Cantabria"): ["Burgos"],
        ("La Rioja", "Madrid"): ["Soria", "Guadalajara"],
        ("La Rioja", "Barcelona"): ["Zaragoza", "Lleida"],
        ("La Rioja", "Badajoz"): ["Soria", "Madrid", "Toledo", "Ciudad Real"],
    }
    
    clave = (prov_origen, prov_destino)
    if clave in RUTAS_INTERMEDIAS:
        provincias.extend(RUTAS_INTERMEDIAS[clave])
    
    if prov_destino not in provincias:
        provincias.append(prov_destino)
    
    return provincias


# ============================================================
# CLIMA
# ============================================================

async def obtener_clima(ciudad: str, api_key: str = "") -> str:
    """Obtiene el clima de una ciudad usando OpenWeatherMap"""
    if not api_key:
        return (
            "⚠️ API de clima no configurada.\n\n"
            "Para activarla:\n"
            "1. Regístrate en openweathermap.org\n"
            "2. Copia tu API Key\n"
            "3. Añade al .env: OPENWEATHER_API_KEY=tu_key"
        )
    
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": f"{ciudad},ES",
            "appid": api_key,
            "units": "metric",
            "lang": "es"
        }
        
        response = requests.get(url, params=params, timeout=10, verify=False)
        data = response.json()
        
        if response.status_code == 200:
            temp = data["main"]["temp"]
            sensacion = data["main"]["feels_like"]
            desc = data["weather"][0]["description"]
            humedad = data["main"]["humidity"]
            viento = data["wind"]["speed"]
            viento_kmh = round(viento * 3.6, 1)
            
            codigo = data["weather"][0]["id"]
            if codigo >= 200 and codigo < 300:
                emoji = "⛈️"
            elif codigo >= 300 and codigo < 600:
                emoji = "🌧️"
            elif codigo >= 600 and codigo < 700:
                emoji = "❄️"
            elif codigo >= 700 and codigo < 800:
                emoji = "🌫️"
            elif codigo == 800:
                emoji = "☀️"
            else:
                emoji = "☁️"
            
            return (
                f"{emoji} CLIMA EN {ciudad.upper()}\n\n"
                f"🌡️ Temperatura: {temp}°C\n"
                f"🤔 Sensación: {sensacion}°C\n"
                f"☁️ {desc.capitalize()}\n"
                f"💧 Humedad: {humedad}%\n"
                f"💨 Viento: {viento_kmh} km/h"
            )
        else:
            return f"❌ No encontré el clima de {ciudad}"
            
    except Exception as e:
        logger.error(f"Error clima: {e}")
        return "❌ Error al consultar el clima"


# ============================================================
# GASOLINERAS - CON TLS 1.2 FORZADO
# ============================================================

def _esta_abierta(horario: str) -> bool:
    """Verifica si la gasolinera está abierta ahora."""
    if not horario:
        return True
    
    horario_upper = horario.upper()
    if "24H" in horario_upper or "24 H" in horario_upper:
        return True
    
    ahora = datetime.now()
    hora_actual = ahora.hour
    
    try:
        import re
        patron = r'(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})'
        matches = re.findall(patron, horario)
        
        if matches:
            for match in matches:
                hora_apertura = int(match[0])
                hora_cierre = int(match[2])
                
                if hora_cierre < hora_apertura:
                    if hora_actual >= hora_apertura or hora_actual < hora_cierre:
                        return True
                else:
                    if hora_apertura <= hora_actual < hora_cierre:
                        return True
            return False
        return True
    except:
        return True


async def obtener_gasolineras(
    provincia: str, 
    lat_usuario: float = None, 
    lon_usuario: float = None,
    lugar_destino: str = None,
    mostrar_ruta: bool = False
) -> str:
    """
    Obtiene gasolineras cercanas usando API del Ministerio.
    
    v3.0:
    - Usa TLS 1.2 forzado (soluciona ConnectionResetError)
    - Ordenadas por CERCANÍA
    - SIN mostrar precio
    """
    
    def generar_link_maps(lat, lon, nombre):
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    
    def generar_link_waze(lat, lon):
        return f"https://waze.com/ul?ll={lat},{lon}&navigate=yes"
    
    try:
        # Determinar provincias a buscar
        provincias_buscar = [provincia] if provincia else ["Navarra"]
        
        if lugar_destino and mostrar_ruta and provincia:
            provincias_buscar = obtener_provincias_ruta(provincia, lugar_destino)
            logger.info(f"[GASOLINERAS] Buscando en ruta: {' → '.join(provincias_buscar)}")
        
        # API del Ministerio con TLS 1.2 forzado
        url = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
        }
        
        logger.info(f"[GASOLINERAS] Conectando a API del Ministerio (TLS 1.2)...")
        
        # USAR SESIÓN CON TLS CONFIGURADO
        session = get_session()
        response = session.get(url, timeout=30, headers=headers, verify=False)
        
        logger.info(f"[GASOLINERAS] Respuesta API: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"[GASOLINERAS] Error HTTP: {response.status_code}")
            return f"❌ Error al consultar gasolineras (HTTP {response.status_code})"
        
        data = response.json()
        estaciones = data.get("ListaEESSPrecio", [])
        logger.info(f"[GASOLINERAS] Total estaciones en España: {len(estaciones)}")
        
        if not estaciones:
            return "❌ No se obtuvieron datos de gasolineras"
        
        # Mapeo de nombres de provincias
        mapeo_provincias = {
            "NAVARRA": "NAVARRA", "LA RIOJA": "RIOJA (LA)", "RIOJA": "RIOJA (LA)",
            "MADRID": "MADRID", "BARCELONA": "BARCELONA", "ZARAGOZA": "ZARAGOZA",
            "MURCIA": "MURCIA", "BADAJOZ": "BADAJOZ", "VALENCIA": "VALENCIA/VALÈNCIA",
            "ALICANTE": "ALICANTE", "SEVILLA": "SEVILLA", "MÁLAGA": "MÁLAGA",
            "MALAGA": "MÁLAGA", "BIZKAIA": "BIZKAIA", "BILBAO": "BIZKAIA",
            "GIPUZKOA": "GIPUZKOA", "ÁLAVA": "ARABA/ÁLAVA", "ALAVA": "ARABA/ÁLAVA",
            "A CORUÑA": "CORUÑA (A)", "CORUÑA": "CORUÑA (A)",
            "PONTEVEDRA": "PONTEVEDRA", "OURENSE": "OURENSE", "LUGO": "LUGO",
            "ASTURIAS": "ASTURIAS", "CANTABRIA": "CANTABRIA",
            "LEÓN": "LEÓN", "LEON": "LEÓN", "BURGOS": "BURGOS",
            "VALLADOLID": "VALLADOLID", "SALAMANCA": "SALAMANCA",
            "SORIA": "SORIA", "GUADALAJARA": "GUADALAJARA",
            "TOLEDO": "TOLEDO", "CIUDAD REAL": "CIUDAD REAL",
            "CÓRDOBA": "CÓRDOBA", "CORDOBA": "CÓRDOBA",
            "JAÉN": "JAÉN", "JAEN": "JAÉN",
            "GRANADA": "GRANADA", "ALMERÍA": "ALMERÍA", "ALMERIA": "ALMERÍA",
            "CÁDIZ": "CÁDIZ", "CADIZ": "CÁDIZ", "HUELVA": "HUELVA",
            "CÁCERES": "CÁCERES", "CACERES": "CÁCERES",
            "LLEIDA": "LLEIDA", "TARRAGONA": "TARRAGONA", "GIRONA": "GIRONA",
            "TERUEL": "TERUEL", "HUESCA": "HUESCA",
            "CASTELLÓN": "CASTELLÓN/CASTELLÓ", "CASTELLON": "CASTELLÓN/CASTELLÓ",
        }
        
        estaciones_filtradas = []
        
        for prov in provincias_buscar:
            prov_upper = prov.upper().strip()
            prov_buscar = mapeo_provincias.get(prov_upper, prov_upper)
            
            count_prov = 0
            for e in estaciones:
                prov_estacion = e.get("Provincia", "").upper()
                
                # Coincidencia más flexible
                if prov_buscar in prov_estacion or prov_upper in prov_estacion:
                    lat_str = e.get("Latitud", "").replace(",", ".")
                    lon_str = e.get("Longitud (WGS84)", "").replace(",", ".")
                    horario = e.get("Horario", "")
                    
                    # Filtrar solo abiertas si hay info de horario
                    if horario and not _esta_abierta(horario):
                        continue
                    
                    if lat_str and lon_str:
                        try:
                            lat = float(lat_str)
                            lon = float(lon_str)
                            
                            # Calcular distancia
                            distancia = 9999
                            if lat_usuario and lon_usuario:
                                distancia = calcular_distancia_km(lat_usuario, lon_usuario, lat, lon)
                            
                            es_24h = "24H" in horario.upper() if horario else False
                            
                            estaciones_filtradas.append({
                                "direccion": e.get("Dirección", "")[:50],
                                "localidad": e.get("Localidad", ""),
                                "provincia": e.get("Provincia", ""),
                                "rotulo": e.get("Rótulo", ""),
                                "es_24h": es_24h,
                                "lat": lat,
                                "lon": lon,
                                "distancia": distancia
                            })
                            count_prov += 1
                        except ValueError:
                            continue
            
            logger.info(f"[GASOLINERAS] {prov}: {count_prov} estaciones encontradas")
        
        # Eliminar duplicados
        vistos = set()
        estaciones_unicas = []
        for e in estaciones_filtradas:
            clave = (round(e['lat'], 4), round(e['lon'], 4))
            if clave not in vistos:
                vistos.add(clave)
                estaciones_unicas.append(e)
        
        logger.info(f"[GASOLINERAS] Total únicas: {len(estaciones_unicas)}")
        
        # Ordenar por cercanía
        estaciones_unicas.sort(key=lambda x: x["distancia"])
        
        # Título
        if mostrar_ruta and lugar_destino:
            titulo = f"⛽ GASOLINERAS EN TU RUTA\n   📍 {provincia} → {lugar_destino}"
        else:
            titulo = f"⛽ GASOLINERAS CERCANAS ({provincia.upper() if provincia else 'NAVARRA'})"
        
        if estaciones_unicas:
            resultado = f"{titulo}\n"
            resultado += f"   📏 Ordenadas por cercanía\n"
            resultado += f"   🟢 Abiertas ahora\n\n"
            
            for i, e in enumerate(estaciones_unicas[:6], 1):
                # Distancia
                if e.get('distancia') and e['distancia'] < 9999:
                    dist_txt = f"📏 {e['distancia']:.1f} km"
                else:
                    dist_txt = ""
                
                # 24H
                h24 = " 🕐24H" if e.get('es_24h') else ""
                
                resultado += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                resultado += f"{i}. 🏪 {e['rotulo']}{h24}\n"
                if dist_txt:
                    resultado += f"   {dist_txt}\n"
                resultado += f"   📍 {e['localidad']}\n"
                resultado += f"   {e['direccion']}\n"
                
                link_maps = generar_link_maps(e['lat'], e['lon'], e['rotulo'])
                link_waze = generar_link_waze(e['lat'], e['lon'])
                
                resultado += f"   🗺️ Maps: {link_maps}\n"
                resultado += f"   🚗 Waze: {link_waze}\n\n"
            
            return resultado
        else:
            return f"❌ No encontré gasolineras en {provincia or 'la zona'}"
            
    except requests.exceptions.Timeout:
        logger.error("[GASOLINERAS] Timeout al conectar con la API")
        return "❌ Timeout al consultar gasolineras. Intenta de nuevo."
    except requests.exceptions.ConnectionError as ce:
        logger.error(f"[GASOLINERAS] Error de conexión: {ce}")
        return "❌ Error de conexión. Verifica tu internet."
    except Exception as e:
        logger.error(f"[GASOLINERAS] Error: {type(e).__name__}: {e}")
        return f"❌ Error al consultar gasolineras: {type(e).__name__}"


# ============================================================
# ALIAS PARA COMPATIBILIDAD
# ============================================================

async def obtener_gasolineras_en_ruta(origen: str, destino: str, lat: float = None, lon: float = None) -> str:
    """Alias para compatibilidad con inteligencia_dual.py"""
    provincia_origen = obtener_provincia(origen)
    return await obtener_gasolineras(
        provincia=provincia_origen,
        lat_usuario=lat,
        lon_usuario=lon,
        lugar_destino=destino,
        mostrar_ruta=True
    )


# ============================================================
# TRÁFICO
# ============================================================

async def obtener_trafico(zona: str, api_key: str = "") -> str:
    """Obtiene información de tráfico usando TomTom API"""
    if not api_key:
        return (
            f"🚗 TRÁFICO EN {zona.upper()}\n\n"
            "⚠️ API de tráfico no configurada.\n\n"
            "📻 Consulta:\n"
            "• DGT: dgt.es/el-trafico\n"
            "• Radio Nacional: informativos de tráfico"
        )
    
    coordenadas = {
        "MADRID": (40.4168, -3.7038),
        "BARCELONA": (41.3851, 2.1734),
        "ZARAGOZA": (41.6488, -0.8891),
        "PAMPLONA": (42.8125, -1.6458),
        "LOGROÑO": (42.4650, -2.4456),
        "BILBAO": (43.2630, -2.9350),
        "VALENCIA": (39.4699, -0.3763),
        "SEVILLA": (37.3891, -5.9845),
    }
    
    zona_upper = zona.upper()
    
    if zona_upper not in coordenadas:
        return f"❌ No tengo datos de tráfico para {zona}"
    
    lat, lon = coordenadas[zona_upper]
    
    try:
        url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        params = {"key": api_key, "point": f"{lat},{lon}"}
        
        response = requests.get(url, params=params, timeout=10, verify=False)
        data = response.json()
        
        if response.status_code == 200:
            flow = data.get("flowSegmentData", {})
            velocidad_actual = flow.get("currentSpeed", 0)
            velocidad_libre = flow.get("freeFlowSpeed", 0)
            confianza = flow.get("confidence", 0)
            
            if velocidad_libre > 0:
                ratio = velocidad_actual / velocidad_libre
                if ratio >= 0.9:
                    estado = "🟢 FLUIDO"
                elif ratio >= 0.7:
                    estado = "🟡 DENSO"
                elif ratio >= 0.5:
                    estado = "🟠 LENTO"
                else:
                    estado = "🔴 MUY LENTO"
            else:
                estado = "⚪ Sin datos"
            
            return (
                f"🚗 TRÁFICO EN {zona.upper()}\n\n"
                f"{estado}\n\n"
                f"🏎️ Velocidad actual: {velocidad_actual} km/h\n"
                f"🚀 Velocidad libre: {velocidad_libre} km/h\n"
                f"📊 Fiabilidad: {confianza:.0%}"
            )
        else:
            return f"❌ Error al consultar tráfico de {zona}"
            
    except Exception as e:
        logger.error(f"Error tráfico: {e}")
        return "❌ Error al consultar tráfico"


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("="*50)
        print("TEST APIs EXTERNAS (TLS 1.2)")
        print("="*50)
        
        print("\n⛽ GASOLINERAS:")
        resultado = await obtener_gasolineras("Navarra")
        print(resultado)
    
    asyncio.run(test())
