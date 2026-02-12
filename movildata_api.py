"""
SIMULADOR DE API MOVILDATA v3.1
================================
Simula todos los endpoints de Movildata.

CAMBIOS v3.1:
- Las coordenadas se obtienen de la ubicación del conductor en la BD
- Ya no depende del JSON para las posiciones
- UBICACIONES_BASE ampliado con más ciudades

Endpoints simulados:
- Users_GetLastLocations (posición GPS de todos los vehículos)
- Users_GetLastLocationPlate (posición por matrícula)
- Users_GetGeonearestVehiclesToPoint (vehículos más cercanos a un punto)
- Users_GetVehiculos (lista de vehículos)
- Users_GetDisponibilidadConductor (disponibilidad y tacógrafo)
- Drivers_getDrivers (lista de conductores)
- Users_GetTemperatureData (temperatura remolques frío)
- AutoStatus_GetLastVehiclesStatusList (estado de vehículos)
"""

import random
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import math
import logging

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURACIÓN
# ============================================================
USE_REAL_API = False
MOVILDATA_API_URL = "https://api.movildata.com/api/"
MOVILDATA_API_KEY = ""
API_GPS_SIMULADA_FILE = "api_gps_simulada.json"
DB_PATH = "logistica.db"  # Ruta a la BD


# ============================================================
# MODELOS DE DATOS
# ============================================================

@dataclass
class Conductor:
    id: int
    nif: str
    nombre: str
    apellidos: str
    telefono: str
    email: str
    activo: bool = True
    grupo: str = "ZONA NORTE"
    
@dataclass 
class Vehiculo:
    id: int
    matricula: str
    tipo: str
    marca: str
    modelo: str
    conductor_asignado: Optional[str] = None
    remolque_asignado: Optional[str] = None
    tipo_remolque: str = "FRIGORIFICO"
    capacidad_kg: int = 24000

@dataclass
class PosicionGPS:
    matricula: str
    latitud: float
    longitud: float
    velocidad: int
    rumbo: int
    fecha_hora: str
    direccion: str
    municipio: str
    provincia: str
    motor_encendido: bool

@dataclass
class EstadoVehiculo:
    matricula: str
    estado: str
    desde: str
    conductor_nif: Optional[str] = None
    conductor_nombre: Optional[str] = None
    temperatura: Optional[float] = None

@dataclass
class DisponibilidadConductor:
    nif: str
    nombre: str
    id_tarjeta: str
    estado: int  # 0=Descanso, 1=Disponible, 2=Trabajo, 3=Conducción
    estado_texto: str
    horas_conducidas_hoy: float
    horas_restantes_hoy: float
    horas_conducidas_semana: float
    horas_restantes_semana: float
    inicio_proximo_descanso_diario: str
    fin_proximo_descanso_diario: str
    inicio_proximo_descanso_semanal: str
    horas_proximo_descanso_semanal: float
    minutos_hasta_descanso: int
    necesita_descanso_pronto: bool
    ultima_actualizacion: str


# ============================================================
# UBICACIONES BASE - AMPLIADO v3.1
# ============================================================

UBICACIONES_BASE = {
    # Navarra
    "AZAGRA": {"lat": 42.3167, "lon": -1.8833, "provincia": "Navarra"},
    "TUDELA": {"lat": 42.0617, "lon": -1.6067, "provincia": "Navarra"},
    "SAN ADRIAN": {"lat": 42.3417, "lon": -1.9333, "provincia": "Navarra"},
    "PAMPLONA": {"lat": 42.8125, "lon": -1.6458, "provincia": "Navarra"},
    "ESTELLA": {"lat": 42.6667, "lon": -2.0333, "provincia": "Navarra"},
    "TAFALLA": {"lat": 42.5167, "lon": -1.6667, "provincia": "Navarra"},
    "PERALTA": {"lat": 42.3333, "lon": -1.8000, "provincia": "Navarra"},
    "MELIDA": {"lat": 42.3833, "lon": -1.5500, "provincia": "Navarra"},
    "MÉLIDA": {"lat": 42.3833, "lon": -1.5500, "provincia": "Navarra"},
    "LODOSA": {"lat": 42.4333, "lon": -2.0833, "provincia": "Navarra"},
    "MENDAVIA": {"lat": 42.4333, "lon": -2.2000, "provincia": "Navarra"},
    
    # La Rioja
    "CALAHORRA": {"lat": 42.3050, "lon": -1.9653, "provincia": "La Rioja"},
    "LOGROÑO": {"lat": 42.4650, "lon": -2.4456, "provincia": "La Rioja"},
    "ALFARO": {"lat": 42.1833, "lon": -1.7500, "provincia": "La Rioja"},
    "ARNEDO": {"lat": 42.2167, "lon": -2.1000, "provincia": "La Rioja"},
    "AUTOL": {"lat": 42.2167, "lon": -2.0000, "provincia": "La Rioja"},
    "QUEL": {"lat": 42.2333, "lon": -2.0500, "provincia": "La Rioja"},
    "HARO": {"lat": 42.5833, "lon": -2.8500, "provincia": "La Rioja"},
    
    # Aragón
    "ZARAGOZA": {"lat": 41.6488, "lon": -0.8891, "provincia": "Zaragoza"},
    "HUESCA": {"lat": 42.1401, "lon": -0.4089, "provincia": "Huesca"},
    "TERUEL": {"lat": 40.3456, "lon": -1.1065, "provincia": "Teruel"},
    
    # Cataluña
    "BARCELONA": {"lat": 41.3851, "lon": 2.1734, "provincia": "Barcelona"},
    "LLEIDA": {"lat": 41.6176, "lon": 0.6200, "provincia": "Lleida"},
    "TARRAGONA": {"lat": 41.1189, "lon": 1.2445, "provincia": "Tarragona"},
    "GIRONA": {"lat": 41.9794, "lon": 2.8214, "provincia": "Girona"},
    
    # País Vasco
    "BILBAO": {"lat": 43.2630, "lon": -2.9350, "provincia": "Vizcaya"},
    "VITORIA": {"lat": 42.8467, "lon": -2.6728, "provincia": "Álava"},
    "SAN SEBASTIAN": {"lat": 43.3183, "lon": -1.9812, "provincia": "Guipúzcoa"},
    "DONOSTIA": {"lat": 43.3183, "lon": -1.9812, "provincia": "Guipúzcoa"},
    
    # Madrid
    "MADRID": {"lat": 40.4168, "lon": -3.7038, "provincia": "Madrid"},
    "MERCAMADRID": {"lat": 40.3833, "lon": -3.6500, "provincia": "Madrid"},
    "GETAFE": {"lat": 40.3088, "lon": -3.7328, "provincia": "Madrid"},
    "ALCALA": {"lat": 40.4818, "lon": -3.3635, "provincia": "Madrid"},
    
    # Comunidad Valenciana
    "VALENCIA": {"lat": 39.4699, "lon": -0.3763, "provincia": "Valencia"},
    "ALICANTE": {"lat": 38.3452, "lon": -0.4815, "provincia": "Alicante"},
    "CASTELLON": {"lat": 39.9864, "lon": -0.0513, "provincia": "Castellón"},
    
    # Murcia
    "MURCIA": {"lat": 37.9922, "lon": -1.1307, "provincia": "Murcia"},
    "CARTAGENA": {"lat": 37.6257, "lon": -0.9966, "provincia": "Murcia"},
    
    # Andalucía
    "SEVILLA": {"lat": 37.3891, "lon": -5.9845, "provincia": "Sevilla"},
    "MALAGA": {"lat": 36.7213, "lon": -4.4214, "provincia": "Málaga"},
    "GRANADA": {"lat": 37.1773, "lon": -3.5986, "provincia": "Granada"},
    "CORDOBA": {"lat": 37.8882, "lon": -4.7794, "provincia": "Córdoba"},
    "ALMERIA": {"lat": 36.8340, "lon": -2.4637, "provincia": "Almería"},
    "CADIZ": {"lat": 36.5271, "lon": -6.2886, "provincia": "Cádiz"},
    "HUELVA": {"lat": 37.2614, "lon": -6.9447, "provincia": "Huelva"},
    "JAEN": {"lat": 37.7796, "lon": -3.7849, "provincia": "Jaén"},
    
    # Extremadura
    "MERIDA": {"lat": 38.9161, "lon": -6.3436, "provincia": "Badajoz"},
    "MÉRIDA": {"lat": 38.9161, "lon": -6.3436, "provincia": "Badajoz"},
    "BADAJOZ": {"lat": 38.8794, "lon": -6.9706, "provincia": "Badajoz"},
    "CACERES": {"lat": 39.4753, "lon": -6.3724, "provincia": "Cáceres"},
    
    # Castilla y León
    "VALLADOLID": {"lat": 41.6523, "lon": -4.7245, "provincia": "Valladolid"},
    "BURGOS": {"lat": 42.3439, "lon": -3.6969, "provincia": "Burgos"},
    "LEON": {"lat": 42.5987, "lon": -5.5671, "provincia": "León"},
    "SALAMANCA": {"lat": 40.9701, "lon": -5.6635, "provincia": "Salamanca"},
    "SORIA": {"lat": 41.7636, "lon": -2.4649, "provincia": "Soria"},
    "SEGOVIA": {"lat": 40.9429, "lon": -4.1088, "provincia": "Segovia"},
    "AVILA": {"lat": 40.6566, "lon": -4.6818, "provincia": "Ávila"},
    "PALENCIA": {"lat": 42.0096, "lon": -4.5288, "provincia": "Palencia"},
    "ZAMORA": {"lat": 41.5034, "lon": -5.7467, "provincia": "Zamora"},
    
    # Castilla-La Mancha
    "TOLEDO": {"lat": 39.8628, "lon": -4.0273, "provincia": "Toledo"},
    "GUADALAJARA": {"lat": 40.6337, "lon": -3.1667, "provincia": "Guadalajara"},
    "CIUDAD REAL": {"lat": 38.9848, "lon": -3.9274, "provincia": "Ciudad Real"},
    "ALBACETE": {"lat": 38.9943, "lon": -1.8585, "provincia": "Albacete"},
    "CUENCA": {"lat": 40.0704, "lon": -2.1374, "provincia": "Cuenca"},
    
    # Galicia
    "VIGO": {"lat": 42.2314, "lon": -8.7124, "provincia": "Pontevedra"},
    "CORUÑA": {"lat": 43.3713, "lon": -8.3960, "provincia": "A Coruña"},
    "A CORUÑA": {"lat": 43.3713, "lon": -8.3960, "provincia": "A Coruña"},
    "SANTIAGO": {"lat": 42.8782, "lon": -8.5448, "provincia": "A Coruña"},
    "LUGO": {"lat": 43.0097, "lon": -7.5567, "provincia": "Lugo"},
    "OURENSE": {"lat": 42.3358, "lon": -7.8639, "provincia": "Ourense"},
    "PONTEVEDRA": {"lat": 42.4310, "lon": -8.6444, "provincia": "Pontevedra"},
    
    # Cantabria
    "SANTANDER": {"lat": 43.4623, "lon": -3.8100, "provincia": "Cantabria"},
    
    # Asturias
    "OVIEDO": {"lat": 43.3614, "lon": -5.8494, "provincia": "Asturias"},
    "GIJON": {"lat": 43.5453, "lon": -5.6615, "provincia": "Asturias"},
    
    # Baleares
    "PALMA": {"lat": 39.5696, "lon": 2.6502, "provincia": "Baleares"},
    
    # Canarias
    "LAS PALMAS": {"lat": 28.1235, "lon": -15.4363, "provincia": "Las Palmas"},
    "TENERIFE": {"lat": 28.4636, "lon": -16.2518, "provincia": "Santa Cruz de Tenerife"},
}


# ============================================================
# CLASE PRINCIPAL: SIMULADOR MOVILDATA
# ============================================================

class MovildataAPI:
    
    def __init__(self, api_key: str = None, api_url: str = None, db_path: str = None):
        self.api_key = api_key or MOVILDATA_API_KEY
        self.api_url = api_url or MOVILDATA_API_URL
        self.db_path = db_path or DB_PATH
        self.use_real = USE_REAL_API
        
        # Datos internos
        self._posiciones: Dict[str, PosicionGPS] = {}
        self._estados: Dict[str, EstadoVehiculo] = {}
        self._disponibilidad: Dict[str, DisponibilidadConductor] = {}
        self._conductores: List[Conductor] = []
        self._vehiculos: List[Vehiculo] = []
        
        if self.use_real:
            logger.info(f"[MOVILDATA] Conectando a API real: {self.api_url}")
        else:
            logger.info("[MOVILDATA] Usando simulador v3.1 (coordenadas desde BD)")
            self._init_simulated_data()
    
    def _obtener_coordenadas_ubicacion(self, ubicacion: str) -> tuple:
        """
        Obtiene coordenadas de una ubicación.
        Busca en UBICACIONES_BASE. Si no encuentra, devuelve coords por defecto.
        """
        if not ubicacion:
            return 42.3167, -1.8833  # Por defecto AZAGRA
        
        ubicacion_upper = ubicacion.upper().strip()
        
        # Buscar exacto
        if ubicacion_upper in UBICACIONES_BASE:
            ubi = UBICACIONES_BASE[ubicacion_upper]
            return ubi["lat"], ubi["lon"]
        
        # Buscar parcial
        for nombre, datos in UBICACIONES_BASE.items():
            if nombre in ubicacion_upper or ubicacion_upper in nombre:
                return datos["lat"], datos["lon"]
        
        # No encontrado - devolver coords por defecto con pequeña variación
        logger.warning(f"[MOVILDATA] Ubicación no encontrada: {ubicacion}, usando coords por defecto")
        return 42.3167 + random.uniform(-0.1, 0.1), -1.8833 + random.uniform(-0.1, 0.1)
    
    def _obtener_provincia_ubicacion(self, ubicacion: str) -> str:
        """Obtiene la provincia de una ubicación"""
        if not ubicacion:
            return "Navarra"
        
        ubicacion_upper = ubicacion.upper().strip()
        
        if ubicacion_upper in UBICACIONES_BASE:
            return UBICACIONES_BASE[ubicacion_upper].get("provincia", "Desconocida")
        
        for nombre, datos in UBICACIONES_BASE.items():
            if nombre in ubicacion_upper or ubicacion_upper in nombre:
                return datos.get("provincia", "Desconocida")
        
        return "Desconocida"
    
    def _cargar_conductores_bd(self) -> List[dict]:
        """Carga conductores desde la BD con su ubicación actual"""
        conductores = []
        try:
            if not Path(self.db_path).exists():
                logger.warning(f"[MOVILDATA] BD no encontrada: {self.db_path}")
                return []
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT nombre, tractora, remolque, telefono, ubicacion, absentismo
                FROM conductores_empresa
                WHERE absentismo IS NULL OR absentismo = '' OR absentismo NOT IN ('BAJA', 'VACACIONES')
            """)
            
            for row in cursor.fetchall():
                conductores.append({
                    'nombre': row['nombre'],
                    'matricula': row['tractora'],
                    'remolque': row['remolque'],
                    'telefono': row['telefono'] or '',
                    'ubicacion': row['ubicacion'] or 'AZAGRA',
                })
            
            conn.close()
            logger.info(f"[MOVILDATA] ✅ Cargados {len(conductores)} conductores de BD")
            
        except Exception as e:
            logger.error(f"[MOVILDATA] Error cargando conductores de BD: {e}")
        
        return conductores
    
    def _cargar_json_simulado(self) -> List[dict]:
        """Carga datos de api_gps_simulada.json si existe (fallback)"""
        if Path(API_GPS_SIMULADA_FILE).exists():
            try:
                with open(API_GPS_SIMULADA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    vehiculos = data.get('vehiculos', [])
                    logger.info(f"[MOVILDATA] Cargados {len(vehiculos)} vehículos de JSON (fallback)")
                    return vehiculos
            except Exception as e:
                logger.warning(f"[MOVILDATA] Error cargando JSON: {e}")
        return []
    
    def _init_simulated_data(self):
        """Inicializa datos simulados desde la BD (o JSON como fallback)"""
        # Intentar cargar desde BD primero
        conductores_bd = self._cargar_conductores_bd()
        
        if conductores_bd:
            self._init_desde_bd(conductores_bd)
        else:
            # Fallback al JSON
            vehiculos_json = self._cargar_json_simulado()
            if vehiculos_json:
                self._init_desde_json(vehiculos_json)
            else:
                logger.warning("[MOVILDATA] No hay datos, usando mínimos")
                self._init_datos_minimos()
        
        logger.info(f"[MOVILDATA] Inicializados: {len(self._posiciones)} posiciones, "
                   f"{len(self._conductores)} conductores")
    
    def _init_desde_bd(self, conductores_bd: List[dict]):
        """Inicializa datos desde los conductores de la BD"""
        ahora = datetime.now()
        
        for idx, c in enumerate(conductores_bd):
            nombre = c.get('nombre', '')
            matricula = c.get('matricula', '')
            remolque = c.get('remolque', '')
            telefono = c.get('telefono', '')
            ubicacion = c.get('ubicacion', 'AZAGRA')
            
            if not matricula or not nombre:
                continue
            
            # Obtener coordenadas de la ubicación
            lat, lon = self._obtener_coordenadas_ubicacion(ubicacion)
            provincia = self._obtener_provincia_ubicacion(ubicacion)
            
            # 1. CREAR CONDUCTOR
            nif = f"SIM{idx:05d}X"
            partes_nombre = nombre.split(' ', 1)
            nombre_pila = partes_nombre[0] if partes_nombre else nombre
            apellidos = partes_nombre[1] if len(partes_nombre) > 1 else ""
            
            conductor = Conductor(
                id=idx + 1,
                nif=nif,
                nombre=nombre_pila,
                apellidos=apellidos,
                telefono=telefono,
                email=f"{nombre_pila.lower()}@empresa.com",
                activo=True,
                grupo="ZONA NORTE"
            )
            self._conductores.append(conductor)
            
            # 2. CREAR VEHÍCULO
            vehiculo = Vehiculo(
                id=idx + 1,
                matricula=matricula,
                tipo="TRAILER",
                marca="VOLVO",
                modelo="FH500",
                conductor_asignado=nombre,
                remolque_asignado=remolque,
                tipo_remolque="FRIGORIFICO",
                capacidad_kg=24000
            )
            self._vehiculos.append(vehiculo)
            
            # 3. CREAR POSICIÓN GPS (desde ubicación de BD)
            posicion = PosicionGPS(
                matricula=matricula,
                latitud=lat,
                longitud=lon,
                velocidad=0,
                rumbo=random.randint(0, 359),
                fecha_hora=ahora.strftime("%Y-%m-%d %H:%M:%S"),
                direccion=f"Calle Principal, {ubicacion}",
                municipio=ubicacion,
                provincia=provincia,
                motor_encendido=False
            )
            self._posiciones[matricula] = posicion
            
            # 4. CREAR ESTADO VEHÍCULO
            estado = EstadoVehiculo(
                matricula=matricula,
                estado="DISPONIBLE",
                desde=ahora.strftime("%Y-%m-%d %H:%M:%S"),
                conductor_nif=nif,
                conductor_nombre=nombre,
                temperatura=random.uniform(-20, -18) if remolque else None
            )
            self._estados[matricula] = estado
            
            # 5. CREAR DISPONIBILIDAD
            disponibilidad = self._generar_disponibilidad(nif, nombre, ahora)
            self._disponibilidad[nif] = disponibilidad
    
    def _init_desde_json(self, vehiculos_json: List[dict]):
        """Inicializa todos los datos desde el JSON simulado (fallback)"""
        ahora = datetime.now()
        
        for idx, v in enumerate(vehiculos_json):
            matricula = v.get('matricula', '')
            conductor_nombre = v.get('conductor', '')
            telefono = v.get('telefono', '')
            ubicacion = v.get('ubicacion', {})
            estado_str = v.get('estado', 'disponible')
            
            if not matricula:
                continue
            
            # Obtener coordenadas del JSON o calcular desde ciudad
            if isinstance(ubicacion, dict):
                lat = ubicacion.get('lat', 42.3167)
                lon = ubicacion.get('lon', -1.8833)
                ciudad = ubicacion.get('ciudad', 'AZAGRA')
                provincia = ubicacion.get('provincia', 'Navarra')
            else:
                ciudad = str(ubicacion) if ubicacion else 'AZAGRA'
                lat, lon = self._obtener_coordenadas_ubicacion(ciudad)
                provincia = self._obtener_provincia_ubicacion(ciudad)
            
            # 1. CREAR CONDUCTOR
            nif = f"SIM{idx:05d}X"
            partes_nombre = conductor_nombre.split(' ', 1)
            nombre = partes_nombre[0] if partes_nombre else conductor_nombre
            apellidos = partes_nombre[1] if len(partes_nombre) > 1 else ""
            
            conductor = Conductor(
                id=idx + 1,
                nif=nif,
                nombre=nombre,
                apellidos=apellidos,
                telefono=telefono,
                email=f"{nombre.lower()}.{apellidos.lower().replace(' ', '.')}@empresa.com" if apellidos else f"{nombre.lower()}@empresa.com",
                activo=True,
                grupo="ZONA NORTE"
            )
            self._conductores.append(conductor)
            
            # 2. CREAR VEHÍCULO
            remolque = v.get('remolque', f"R-{matricula[-4:]}")
            vehiculo = Vehiculo(
                id=idx + 1,
                matricula=matricula,
                tipo="TRAILER",
                marca=random.choice(["VOLVO", "SCANIA", "MAN", "MERCEDES", "DAF"]),
                modelo=random.choice(["FH500", "R450", "TGX", "ACTROS", "XF"]),
                conductor_asignado=conductor_nombre,
                remolque_asignado=remolque,
                tipo_remolque="FRIGORIFICO",
                capacidad_kg=24000
            )
            self._vehiculos.append(vehiculo)
            
            # 3. CREAR POSICIÓN GPS
            posicion = PosicionGPS(
                matricula=matricula,
                latitud=lat,
                longitud=lon,
                velocidad=random.randint(0, 90) if estado_str == "en_ruta" else 0,
                rumbo=random.randint(0, 359),
                fecha_hora=ahora.strftime("%Y-%m-%d %H:%M:%S"),
                direccion=f"Calle Principal, {ciudad}",
                municipio=ciudad,
                provincia=provincia,
                motor_encendido=estado_str == "en_ruta"
            )
            self._posiciones[matricula] = posicion
            
            # 4. CREAR ESTADO VEHÍCULO
            estado_map = {
                "disponible": "DISPONIBLE",
                "en_ruta": "EN_RUTA",
                "descansando": "DESCANSO",
                "cargando": "CARGANDO",
                "descargando": "DESCARGANDO"
            }
            estado = EstadoVehiculo(
                matricula=matricula,
                estado=estado_map.get(estado_str, "DISPONIBLE"),
                desde=ahora.strftime("%Y-%m-%d %H:%M:%S"),
                conductor_nif=nif,
                conductor_nombre=conductor_nombre,
                temperatura=random.uniform(-20, -18)
            )
            self._estados[matricula] = estado
            
            # 5. CREAR DISPONIBILIDAD
            disponibilidad = self._generar_disponibilidad(nif, conductor_nombre, ahora)
            self._disponibilidad[nif] = disponibilidad
    
    def _generar_disponibilidad(self, nif: str, nombre: str, ahora: datetime) -> DisponibilidadConductor:
        """Genera datos de disponibilidad simulados"""
        horas_conducidas_hoy = random.uniform(0, 7)
        horas_restantes_hoy = max(0, 9 - horas_conducidas_hoy)
        horas_conducidas_semana = horas_conducidas_hoy + random.uniform(10, 40)
        horas_restantes_semana = max(0, 56 - horas_conducidas_semana)
        
        estado = random.choice([0, 1, 2, 3])
        estados_texto = {0: "Descanso", 1: "Disponible", 2: "Trabajo", 3: "Conducción"}
        
        minutos_hasta_descanso = int((horas_restantes_hoy * 60) + random.randint(-30, 30))
        minutos_hasta_descanso = max(0, minutos_hasta_descanso)
        
        return DisponibilidadConductor(
            nif=nif,
            nombre=nombre,
            id_tarjeta=f"E{random.randint(10000000, 99999999)}",
            estado=estado,
            estado_texto=estados_texto.get(estado, "Desconocido"),
            horas_conducidas_hoy=round(horas_conducidas_hoy, 1),
            horas_restantes_hoy=round(horas_restantes_hoy, 1),
            horas_conducidas_semana=round(horas_conducidas_semana, 1),
            horas_restantes_semana=round(horas_restantes_semana, 1),
            inicio_proximo_descanso_diario=(ahora + timedelta(hours=horas_restantes_hoy)).strftime("%Y-%m-%d %H:%M"),
            fin_proximo_descanso_diario=(ahora + timedelta(hours=horas_restantes_hoy + 11)).strftime("%Y-%m-%d %H:%M"),
            inicio_proximo_descanso_semanal=(ahora + timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d"),
            horas_proximo_descanso_semanal=45.0,
            minutos_hasta_descanso=minutos_hasta_descanso,
            necesita_descanso_pronto=minutos_hasta_descanso < 60 or horas_restantes_hoy < 1,
            ultima_actualizacion=ahora.strftime("%Y-%m-%d %H:%M:%S")
        )
    
    def _init_datos_minimos(self):
        """Datos mínimos si no hay BD ni JSON"""
        datos_minimos = [
            ("4885NFF", "LUIS ARNALDO", "666111001", "AZAGRA"),
            ("5113NSC", "JUAN JOSE", "666111002", "SAN ADRIAN"),
            ("8521LCC", "PEDRO LUIS", "666111003", "CALAHORRA"),
            ("8895NFN", "MIGUEL ANGEL", "666111004", "TUDELA"),
        ]
        
        conductores_bd = []
        for matricula, nombre, tel, ciudad in datos_minimos:
            conductores_bd.append({
                'nombre': nombre,
                'matricula': matricula,
                'remolque': f"R-{matricula[-4:]}",
                'telefono': tel,
                'ubicacion': ciudad,
            })
        
        self._init_desde_bd(conductores_bd)
    
    def refrescar_posiciones_desde_bd(self):
        """
        Refresca las posiciones de los conductores desde la BD.
        Llamar este método para actualizar las coordenadas cuando cambie la ubicación.
        """
        try:
            conductores_bd = self._cargar_conductores_bd()
            
            for c in conductores_bd:
                matricula = c.get('matricula', '')
                ubicacion = c.get('ubicacion', '')
                
                if matricula and matricula in self._posiciones:
                    lat, lon = self._obtener_coordenadas_ubicacion(ubicacion)
                    provincia = self._obtener_provincia_ubicacion(ubicacion)
                    
                    pos = self._posiciones[matricula]
                    pos.latitud = lat
                    pos.longitud = lon
                    pos.municipio = ubicacion
                    pos.provincia = provincia
                    pos.fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            logger.info("[MOVILDATA] ✅ Posiciones refrescadas desde BD")
            
        except Exception as e:
            logger.error(f"[MOVILDATA] Error refrescando posiciones: {e}")
    
    def _actualizar_posiciones_simuladas(self):
        """Simula pequeños movimientos en las posiciones"""
        # Primero refrescar desde BD para tener ubicaciones actuales
        self.refrescar_posiciones_desde_bd()
        
        for matricula, pos in self._posiciones.items():
            estado = self._estados.get(matricula)
            if estado and estado.estado == "EN_RUTA":
                # Mover ligeramente el vehículo
                pos.latitud += random.uniform(-0.01, 0.01)
                pos.longitud += random.uniform(-0.01, 0.01)
                pos.velocidad = random.randint(60, 90)
            else:
                pos.velocidad = 0
            pos.fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _calcular_distancia_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calcula distancia entre dos puntos usando fórmula de Haversine"""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    # ============================================================
    # ENDPOINTS GPS
    # ============================================================
    
    def get_last_locations(self) -> List[Dict]:
        """Obtiene última posición de todos los vehículos"""
        if self.use_real:
            pass  # Llamar API real
        self._actualizar_posiciones_simuladas()
        return [asdict(p) for p in self._posiciones.values()]
    
    def get_last_location_plate(self, matricula: str) -> Optional[Dict]:
        """Obtiene última posición de un vehículo por matrícula"""
        if self.use_real:
            pass
        self._actualizar_posiciones_simuladas()
        pos = self._posiciones.get(matricula)
        return asdict(pos) if pos else None
    
    def get_geoneearest_vehicles_to_point(self, lat: float, lon: float, max_results: int = 5) -> List[Dict]:
        """Obtiene vehículos más cercanos a un punto"""
        if self.use_real:
            pass
        
        self._actualizar_posiciones_simuladas()
        
        vehiculos_con_distancia = []
        for matricula, pos in self._posiciones.items():
            distancia = self._calcular_distancia_km(lat, lon, pos.latitud, pos.longitud)
            estado = self._estados.get(matricula)
            vehiculo = next((v for v in self._vehiculos if v.matricula == matricula), None)
            
            vehiculos_con_distancia.append({
                "matricula": matricula,
                "latitud": pos.latitud,
                "longitud": pos.longitud,
                "distancia_km": round(distancia, 2),
                "velocidad": pos.velocidad,
                "motor_encendido": pos.motor_encendido,
                "estado": estado.estado if estado else "DESCONOCIDO",
                "conductor": estado.conductor_nombre if estado else None,
                "tipo_remolque": vehiculo.tipo_remolque if vehiculo else "FRIGORIFICO"
            })
        
        vehiculos_con_distancia.sort(key=lambda x: x["distancia_km"])
        return vehiculos_con_distancia[:max_results]
    
    # ============================================================
    # ENDPOINTS VEHÍCULOS
    # ============================================================
    
    def get_vehiculos(self) -> List[Dict]:
        """Lista todos los vehículos"""
        return [asdict(v) for v in self._vehiculos]
    
    def get_last_vehicles_status(self) -> List[Dict]:
        """Estado de todos los vehículos"""
        return [asdict(e) for e in self._estados.values()]
    
    def get_vehicle_status(self, matricula: str) -> Optional[Dict]:
        """Estado de un vehículo específico"""
        estado = self._estados.get(matricula)
        return asdict(estado) if estado else None
    
    # ============================================================
    # ENDPOINTS CONDUCTORES
    # ============================================================
    
    def get_drivers(self) -> List[Dict]:
        """Lista todos los conductores"""
        return [asdict(c) for c in self._conductores]
    
    def get_driver_by_nif(self, nif: str) -> Optional[Dict]:
        """Obtiene conductor por NIF"""
        conductor = next((c for c in self._conductores if c.nif == nif), None)
        return asdict(conductor) if conductor else None
    
    def get_disponibilidad_conductor(self, nif: str = None, matricula: str = None) -> Optional[Dict]:
        """Obtiene disponibilidad de un conductor"""
        if matricula and not nif:
            # Buscar NIF por matrícula
            estado = self._estados.get(matricula)
            if estado:
                nif = estado.conductor_nif
        
        if nif:
            disp = self._disponibilidad.get(nif)
            return asdict(disp) if disp else None
        return None
    
    def get_disponibilidad_por_nombre(self, nombre: str) -> Optional[Dict]:
        """Obtiene disponibilidad buscando por nombre"""
        nombre_upper = nombre.upper()
        for nif, disp in self._disponibilidad.items():
            if nombre_upper in disp.nombre.upper():
                return asdict(disp)
        return None
    
    # ============================================================
    # ENDPOINTS TEMPERATURA
    # ============================================================
    
    def get_temperatura_vehiculo(self, matricula: str) -> Optional[Dict]:
        """Temperatura del remolque frigorífico"""
        estado = self._estados.get(matricula)
        if estado and estado.temperatura is not None:
            return {
                "matricula": matricula,
                "temperatura": estado.temperatura,
                "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "estado": "OK" if -25 <= estado.temperatura <= 8 else "ALERTA"
            }
        return None
    
    # ============================================================
    # MÉTODOS DE UTILIDAD
    # ============================================================
    
    def resumen_flota(self) -> Dict:
        """Resumen del estado de la flota"""
        estados_count = {}
        for estado in self._estados.values():
            e = estado.estado
            estados_count[e] = estados_count.get(e, 0) + 1
        
        return {
            "total_vehiculos": len(self._vehiculos),
            "total_conductores": len(self._conductores),
            "estados": estados_count,
            "timestamp": datetime.now().isoformat()
        }


# ============================================================
# FUNCIONES DE INICIALIZACIÓN GLOBAL
# ============================================================

_instancia_api = None

def inicializar_movildata(api_key: str = None, api_url: str = None, db_path: str = None) -> MovildataAPI:
    global _instancia_api
    _instancia_api = MovildataAPI(api_key, api_url, db_path)
    return _instancia_api

def obtener_movildata() -> Optional[MovildataAPI]:
    return _instancia_api
