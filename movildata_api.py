"""
SIMULADOR DE API MOVILDATA v3.0
================================
Simula todos los endpoints de Movildata con datos del JSON simulado.
Genera automáticamente conductores, vehículos y disponibilidad.

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
# UBICACIONES BASE
# ============================================================

UBICACIONES_BASE = {
    "AZAGRA": {"lat": 42.3167, "lon": -1.8833, "provincia": "Navarra"},
    "TUDELA": {"lat": 42.0617, "lon": -1.6067, "provincia": "Navarra"},
    "CALAHORRA": {"lat": 42.3050, "lon": -1.9653, "provincia": "La Rioja"},
    "SAN ADRIAN": {"lat": 42.3417, "lon": -1.9333, "provincia": "Navarra"},
    "LOGROÑO": {"lat": 42.4650, "lon": -2.4456, "provincia": "La Rioja"},
    "PAMPLONA": {"lat": 42.8125, "lon": -1.6458, "provincia": "Navarra"},
    "ALFARO": {"lat": 42.1833, "lon": -1.7500, "provincia": "La Rioja"},
    "ARNEDO": {"lat": 42.2167, "lon": -2.1000, "provincia": "La Rioja"},
    "ESTELLA": {"lat": 42.6667, "lon": -2.0333, "provincia": "Navarra"},
    "TAFALLA": {"lat": 42.5167, "lon": -1.6667, "provincia": "Navarra"},
    "ZARAGOZA": {"lat": 41.6488, "lon": -0.8891, "provincia": "Zaragoza"},
    "PERALTA": {"lat": 42.3333, "lon": -1.8000, "provincia": "Navarra"},
}


# ============================================================
# CLASE PRINCIPAL: SIMULADOR MOVILDATA
# ============================================================

class MovildataAPI:
    
    def __init__(self, api_key: str = None, api_url: str = None):
        self.api_key = api_key or MOVILDATA_API_KEY
        self.api_url = api_url or MOVILDATA_API_URL
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
            logger.info("[MOVILDATA] Usando simulador con datos ficticios")
            self._init_simulated_data()
    
    def _cargar_json_simulado(self) -> List[dict]:
        """Carga datos de api_gps_simulada.json si existe"""
        if Path(API_GPS_SIMULADA_FILE).exists():
            try:
                with open(API_GPS_SIMULADA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    vehiculos = data.get('vehiculos', [])
                    logger.info(f"[MOVILDATA] ✅ Cargados {len(vehiculos)} vehículos de {API_GPS_SIMULADA_FILE}")
                    return vehiculos
            except Exception as e:
                logger.warning(f"[MOVILDATA] Error cargando JSON: {e}")
        return []
    
    def _init_simulated_data(self):
        """Inicializa datos simulados desde el JSON"""
        vehiculos_json = self._cargar_json_simulado()
        
        if vehiculos_json:
            self._init_desde_json(vehiculos_json)
        else:
            logger.warning("[MOVILDATA] No hay JSON, usando datos mínimos")
            self._init_datos_minimos()
        
        logger.info(f"[MOVILDATA] Inicializados: {len(self._posiciones)} posiciones, {len(self._conductores)} conductores, {len(self._disponibilidad)} disponibilidades")
    
    def _init_desde_json(self, vehiculos_json: List[dict]):
        """Inicializa todos los datos desde el JSON simulado"""
        
        for idx, v in enumerate(vehiculos_json):
            matricula = v.get('matricula', '')
            conductor_nombre = v.get('conductor', '')
            telefono = v.get('telefono', '')
            ubicacion = v.get('ubicacion', {})
            estado_str = v.get('estado', 'disponible')
            
            if not matricula:
                continue
            
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
            vehiculo = Vehiculo(
                id=idx + 1,
                matricula=matricula,
                tipo="TRACTORA",
                marca=random.choice(["VOLVO", "SCANIA", "MERCEDES", "DAF", "MAN", "IVECO"]),
                modelo=random.choice(["FH500", "R450", "ACTROS", "XF480", "TGX", "S-WAY"]),
                conductor_asignado=conductor_nombre,
                remolque_asignado=v.get('remolque', f"R{random.randint(1000,9999)}BBB"),
                tipo_remolque="FRIGORIFICO",
                capacidad_kg=24000
            )
            self._vehiculos.append(vehiculo)
            
            # 3. CREAR POSICIÓN GPS
            lat = ubicacion.get('lat', 42.3)
            lon = ubicacion.get('lon', -1.9)
            
            # Mapear estado
            estado_map = {
                'disponible': 'DISPONIBLE',
                'en_ruta': 'EN_RUTA',
                'cargando': 'CARGANDO',
                'descargando': 'DESCARGANDO',
                'descanso': 'DESCANSO'
            }
            estado = estado_map.get(estado_str, 'DISPONIBLE')
            
            self._posiciones[matricula] = PosicionGPS(
                matricula=matricula,
                latitud=lat,
                longitud=lon,
                velocidad=v.get('velocidad', 0),
                rumbo=random.randint(0, 359),
                fecha_hora=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                direccion=ubicacion.get('direccion', ''),
                municipio=ubicacion.get('ciudad', ''),
                provincia=ubicacion.get('provincia', ''),
                motor_encendido=estado in ['EN_RUTA', 'CARGANDO']
            )
            
            # 4. CREAR ESTADO VEHÍCULO
            self._estados[matricula] = EstadoVehiculo(
                matricula=matricula,
                estado=estado,
                desde=(datetime.now() - timedelta(hours=random.randint(0, 4))).strftime("%Y-%m-%d %H:%M:%S"),
                conductor_nif=nif,
                conductor_nombre=conductor_nombre,
                temperatura=v.get('temperatura', round(random.uniform(-22, 5), 1))
            )
            
            # 5. CREAR DISPONIBILIDAD (tacógrafo simulado)
            self._generar_disponibilidad(nif, conductor_nombre, estado)
    
    def _generar_disponibilidad(self, nif: str, nombre: str, estado_vehiculo: str):
        """Genera datos de disponibilidad realistas para un conductor"""
        
        # Simular horas conducidas según estado
        if estado_vehiculo == 'DESCANSO':
            horas_hoy = 0
            estado = 0  # Descanso
        elif estado_vehiculo == 'DISPONIBLE':
            horas_hoy = round(random.uniform(0, 4), 1)
            estado = 1  # Disponible
        elif estado_vehiculo == 'CARGANDO':
            horas_hoy = round(random.uniform(2, 6), 1)
            estado = 2  # Trabajo
        else:  # EN_RUTA
            horas_hoy = round(random.uniform(4, 8), 1)
            estado = 3  # Conducción
        
        horas_semana = round(random.uniform(20, 45), 1)
        
        estados_texto = {0: "DESCANSO", 1: "DISPONIBLE", 2: "TRABAJO", 3: "CONDUCCION"}
        
        horas_restantes_hoy = max(0, 9 - horas_hoy)
        horas_restantes_semana = max(0, 56 - horas_semana)
        
        # Calcular tiempo hasta descanso obligatorio
        if horas_hoy >= 4.5:
            minutos_hasta_descanso = 0  # Ya debería descansar
        else:
            minutos_hasta_descanso = int((4.5 - (horas_hoy % 4.5)) * 60)
        
        ahora = datetime.now()
        
        self._disponibilidad[nif] = DisponibilidadConductor(
            nif=nif,
            nombre=nombre,
            id_tarjeta=f"E{random.randint(100000000000, 999999999999)}",
            estado=estado,
            estado_texto=estados_texto[estado],
            horas_conducidas_hoy=horas_hoy,
            horas_restantes_hoy=horas_restantes_hoy,
            horas_conducidas_semana=horas_semana,
            horas_restantes_semana=horas_restantes_semana,
            inicio_proximo_descanso_diario=(ahora + timedelta(hours=horas_restantes_hoy)).strftime("%Y-%m-%d %H:%M"),
            fin_proximo_descanso_diario=(ahora + timedelta(hours=horas_restantes_hoy + 11)).strftime("%Y-%m-%d %H:%M"),
            inicio_proximo_descanso_semanal=(ahora + timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d"),
            horas_proximo_descanso_semanal=45.0 if random.random() > 0.5 else 24.0,
            minutos_hasta_descanso=minutos_hasta_descanso,
            necesita_descanso_pronto=minutos_hasta_descanso < 60 or horas_restantes_hoy < 1,
            ultima_actualizacion=ahora.strftime("%Y-%m-%d %H:%M:%S")
        )
    
    def _init_datos_minimos(self):
        """Datos mínimos si no hay JSON"""
        # Solo 4 conductores de prueba
        datos_minimos = [
            ("4885NFF", "LUIS ARNALDO", "666111001", "AZAGRA"),
            ("5113NSC", "JUAN JOSE", "666111002", "SAN ADRIAN"),
            ("8521LCC", "PEDRO LUIS", "666111003", "CALAHORRA"),
            ("8895NFN", "MIGUEL ANGEL", "666111004", "TUDELA"),
        ]
        
        vehiculos_json = []
        for matricula, nombre, tel, ciudad in datos_minimos:
            ubi = UBICACIONES_BASE.get(ciudad, {"lat": 42.3, "lon": -1.9, "provincia": "Navarra"})
            vehiculos_json.append({
                "matricula": matricula,
                "conductor": nombre,
                "telefono": tel,
                "ubicacion": {
                    "lat": ubi["lat"],
                    "lon": ubi["lon"],
                    "ciudad": ciudad,
                    "provincia": ubi["provincia"]
                },
                "estado": "disponible"
            })
        
        self._init_desde_json(vehiculos_json)
    
    def _actualizar_posiciones_simuladas(self):
        """Simula pequeños movimientos en las posiciones"""
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

def inicializar_movildata(api_key: str = None, api_url: str = None) -> MovildataAPI:
    global _instancia_api
    _instancia_api = MovildataAPI(api_key, api_url)
    return _instancia_api

def obtener_movildata() -> Optional[MovildataAPI]:
    return _instancia_api
