"""
BOT DE TELEGRAM - TRANSPORTE v2.2
==================================
Bot único con 2 PERFILES:

👔 ADMIN/RESPONSABLE:
   - Ve todos los conductores
   - Ve todos los viajes
   - Ve posición de toda la flota
   - Puede asignar viajes
   - Vehículos cercanos a puntos
   - Estadísticas
   - 📋 Consultar rutas de conductores

🚛 CAMIONERO:
   - Solo ve SUS datos
   - Su vehículo
   - Sus viajes
   - Su posición
   - Gasolineras

El perfil se detecta automáticamente por TELEGRAM_ID en .env

CAMBIOS v2.2:
- Lector automático de emails de viajes
- Notifica a admins cuando llega viaje por email
- Integración completa con Drive
"""

import urllib.parse
import random
from datetime import datetime, timedelta
import os
import sqlite3
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from teclados import obtener_teclado, es_boton, obtener_accion_boton, teclado_admin, teclado_viajes, teclado_flota, teclado_informes
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv

# Módulos del sistema
from separador_excel_empresa import SeparadorExcelEmpresa
from movildata_api import MovildataAPI
from apis_externas import obtener_gasolineras, obtener_trafico
from inteligencia_dual import InteligenciaDual

# Lector de emails de viajes
from lector_emails_viajes import LectorEmailsViajes, crear_job_lector_emails
from monitor_retrasos import MonitorRetrasos
# Google Drive
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pickle
import re
import io
from extractor_telefonos import sincronizar_telefonos
from generador_direcciones import sincronizar_direcciones
from notificaciones_viajes import inicializar_notificador, obtener_notificador
from asignador_viajes import inicializar_asignador, obtener_asignador
from asignacion_manual import AsignacionManual
from gestiones_manager import GestionesManager
from modificador_viajes_ruta import ModificadorViajesRuta
from registros_conductor import crear_registros_conductor
from incidencias_conductor import crear_incidencias_conductor
from cierre_dia import crear_cierre_dia
from cierre_dia_handler import crear_cierre_handler
from conductores_panel import crear_conductores_panel

gestiones_manager = None
modificador_ruta = None
cierre_dia_handler = None

EQUIVALENCIAS_DISTANCIA = [
    (500, "Pamplona - Madrid"),
    (1000, "Pamplona - Barcelona ida y vuelta"),
    (1500, "Pamplona - París"),
    (2000, "Pamplona - Berlín"),
    (2500, "Pamplona - Roma"),
    (3000, "Pamplona - Londres ida y vuelta"),
    (4000, "Pamplona - Estocolmo"),
    (5000, "Pamplona - Moscú"),
    (6000, "Atravesar España 6 veces"),
    (8000, "Pamplona - Dubái"),
    (10000, "Dar la vuelta a España 5 veces"),
    (15000, "Cruzar Europa de punta a punta 3 veces"),
    (20000, "Media vuelta al mundo"),
]

# ============================================================
# COORDENADAS PARA CALCULAR DISTANCIAS EN RUTAS
# ============================================================

COORDENADAS_RUTAS = {
    "AZAGRA": (42.3167, -1.8833),
    "MELIDA": (42.3833, -1.5500),
    "MÉLIDA": (42.3833, -1.5500),
    "TUDELA": (42.0617, -1.6067),
    "PAMPLONA": (42.8125, -1.6458),
    "SAN ADRIAN": (42.3417, -1.9333),
    "CALAHORRA": (42.3050, -1.9653),
    "LOGROÑO": (42.4650, -2.4456),
    "ALFARO": (42.1833, -1.7500),
    "ARNEDO": (42.2167, -2.1000),
    "AUTOL": (42.2167, -2.0000),
    "QUEL": (42.2333, -2.0500),
    "LODOSA": (42.4333, -2.0833),
    "MENDAVIA": (42.4333, -2.2000),
    "PERALTA": (42.3333, -1.8000),
    "ZARAGOZA": (41.6488, -0.8891),
    "BARCELONA": (41.3851, 2.1734),
    "MADRID": (40.4168, -3.7038),
    "MERCAMADRID": (40.3833, -3.6500),
    "VALENCIA": (39.4699, -0.3763),
    "BILBAO": (43.2630, -2.9350),
    "VITORIA": (42.8467, -2.6728),
    "SANTANDER": (43.4623, -3.8100),
    "OVIEDO": (43.3614, -5.8494),
    "GIJON": (43.5453, -5.6615),
    "SEVILLA": (37.3891, -5.9845),
    "MALAGA": (36.7213, -4.4214),
    "MERIDA": (38.9161, -6.3436),
    "MÉRIDA": (38.9161, -6.3436),
    "BADAJOZ": (38.8794, -6.9706),
    "VALLADOLID": (41.6523, -4.7245),
    "BURGOS": (42.3439, -3.6969),
    "LEON": (42.5987, -5.5671),
    "VIGO": (42.2314, -8.7124),
    "CORUÑA": (43.3713, -8.3960),
    "MURCIA": (37.9922, -1.1307),
    "ALICANTE": (38.3452, -0.4815),
    "GRANADA": (37.1773, -3.5986),
    "CORDOBA": (37.8882, -4.7794),
    "LLEIDA": (41.6176, 0.6200),
    "TARRAGONA": (41.1189, 1.2445),
    "GUADALAJARA": (40.6337, -3.1667),
    "TOLEDO": (39.8628, -4.0273),
    "SALAMANCA": (40.9701, -5.6635),
    "SORIA": (41.7636, -2.4649),
}


def _calcular_distancia_rutas(lat1, lon1, lat2, lon2):
    """Calcula distancia en km entre dos puntos"""
    import math
    if not all([lat1, lon1, lat2, lon2]):
        return None
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def _obtener_coords_rutas(lugar):
    """Obtiene coordenadas de un lugar"""
    if not lugar:
        return None, None
    lugar_upper = lugar.upper().strip()
    
    if lugar_upper in COORDENADAS_RUTAS:
        return COORDENADAS_RUTAS[lugar_upper]
    
    for nombre, coords in COORDENADAS_RUTAS.items():
        if nombre in lugar_upper or lugar_upper in nombre:
            return coords
    
    return None, None

def obtener_equivalencia_km(km: int) -> str:
    """Devuelve una equivalencia divertida para los km recorridos"""
    equivalencia = "tu primer viaje 🚀"
    for limite, texto in EQUIVALENCIAS_DISTANCIA:
        if km >= limite:
            equivalencia = texto
    return equivalencia


async def resumen_conductor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resumen personalizado para el conductor"""
    user = update.effective_user
    conductor = db.obtener_conductor(user.id)
    
    if not conductor:
        await update.message.reply_text("👋 ¡Hola! Para empezar, pulsa el botón de abajo 👇", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚀 Comenzar")]], resize_keyboard=True, one_time_keyboard=True))
        return
    
    nombre = conductor.get('nombre', 'N/A')
    tractora = conductor.get('tractora', 'N/A')
    
    # Obtener viajes del conductor
    viajes = db.obtener_viajes_conductor(nombre)
    
    # ══════════════════════════════════════
    # DATOS DE HOY
    # ══════════════════════════════════════
    viajes_hoy = len(viajes)
    km_pendientes = sum(v.get('km', 0) or 0 for v in viajes)
    
    # Tiempo estimado (75 km/h promedio + 30min por parada)
    if km_pendientes > 0:
        horas_conduccion = km_pendientes / 75
        horas_paradas = viajes_hoy * 0.5  # 30min por carga/descarga
        tiempo_total = horas_conduccion + horas_paradas
        horas = int(tiempo_total)
        minutos = int((tiempo_total - horas) * 60)
        tiempo_estimado = f"{horas}h {minutos}min"
    else:
        tiempo_estimado = "0h"
    
    # ══════════════════════════════════════
    # DATOS DEL MES (simulados por ahora)
    # Cuando tengas histórico real, se calculará de la BD
    # ══════════════════════════════════════
    import random
    
    # Por ahora simulamos, luego usaremos datos reales del histórico
    km_mes = km_pendientes * random.randint(8, 15)  # Simular mes
    entregas_mes = viajes_hoy * random.randint(10, 20)  # Simular mes
    puntualidad = random.randint(92, 99)  # Simular puntualidad
    
    # Si no hay viajes, poner valores base
    if km_mes == 0:
        km_mes = random.randint(5000, 12000)
    if entregas_mes == 0:
        entregas_mes = random.randint(15, 30)
    
    # ══════════════════════════════════════
    # CURIOSIDAD
    # ══════════════════════════════════════
    equivalencia = obtener_equivalencia_km(km_mes)
    
    # ══════════════════════════════════════
    # CONSTRUIR MENSAJE
    # ══════════════════════════════════════
    mensaje = f"📊 TU RESUMEN\n\n"
    mensaje += f"👤 {nombre}\n"
    mensaje += f"🚛 {tractora}\n"
    
    # HOY
    mensaje += f"\n📅 HOY:\n"
    mensaje += f"📦 Viajes: {viajes_hoy}\n"
    mensaje += f"📏 KM pendientes: {km_pendientes:,} km\n"
    mensaje += f"⏱️ Tiempo estimado: {tiempo_estimado}\n"
    
    # ESTE MES
    mensaje += f"\n📈 ESTE MES:\n"
    mensaje += f"📏 KM recorridos: {km_mes:,} km\n"
    mensaje += f"📦 Entregas completadas: {entregas_mes}\n"
    mensaje += f"🏆 Puntualidad: {puntualidad}%\n"
    
    # CURIOSIDAD
    mensaje += f"\n🎯 CURIOSIDADES:\n"
    mensaje += f"🌍 Has recorrido el equivalente a {equivalencia}"
    
    await update.message.reply_text(mensaje)

# Cargar variables de entorno
load_dotenv()

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Variables globales
separador_excel = None
movildata_api = None
drive_service = None
inteligencia = None
notificador = None
asignador = None
asignacion_manual = None


@dataclass
class Config:
    """Configuración del bot"""
    BOT_TOKEN: str
    DB_PATH: str = "logistica.db"
    EXCEL_EMPRESA: str = "PRUEBO.xlsx"
    SYNC_INTERVAL: int = 60
    ASIGNACION_AUTO: bool = False
    MONITOR_RETRASOS_ENABLED: bool = True
    MONITOR_RETRASOS_INTERVALO: int = 300  # segundos (5 min)
    # IDs de administradores (separados por coma)
    ADMIN_IDS: List[int] = None
    
    # Google Drive
    DRIVE_ENABLED: bool = False
    DRIVE_CREDENTIALS: str = "credentials.json"
    DRIVE_EXCEL_EMPRESA_ID: str = ""
    
    # APIs externas
    OPENWEATHER_API_KEY: str = ""
    TOMTOM_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    
    # Lector de emails
    EMAIL_VIAJES_ENABLED: bool = False
    EMAIL_VIAJES_USER: str = ""
    EMAIL_VIAJES_PASSWORD: str = ""
    EMAIL_VIAJES_IMAP: str = "imap.gmail.com"
    EMAIL_VIAJES_INTERVALO: int = 300

    @classmethod
    def from_env(cls) -> 'Config':
        token = os.getenv("BOT_TOKEN")
        if not token:
            raise RuntimeError("Falta BOT_TOKEN en variables de entorno.")
        
        # Parsear ADMIN_IDS
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        admin_ids = []
        if admin_ids_str:
            try:
                admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
            except ValueError:
                logger.warning("ADMIN_IDS mal formateado en .env")
        
        return cls(
            BOT_TOKEN=token,
            DB_PATH=os.getenv("DB_PATH", "logistica.db"),
            EXCEL_EMPRESA=os.getenv("EXCEL_EMPRESA", "PRUEBO.xlsx"),
            SYNC_INTERVAL=int(os.getenv("SYNC_INTERVAL", "60")),
            MONITOR_RETRASOS_ENABLED=os.getenv("MONITOR_RETRASOS_ENABLED", "true").lower() == "true",
            MONITOR_RETRASOS_INTERVALO=int(os.getenv("MONITOR_RETRASOS_INTERVALO", "300")),
            ASIGNACION_AUTO=os.getenv("ASIGNACION_AUTO", "false").lower() == "true",
            ADMIN_IDS=admin_ids,
            DRIVE_ENABLED=os.getenv("DRIVE_ENABLED", "false").lower() == "true",
            DRIVE_CREDENTIALS=os.getenv("DRIVE_CREDENTIALS", "credentials.json"),
            DRIVE_EXCEL_EMPRESA_ID=os.getenv("DRIVE_EXCEL_EMPRESA_ID", ""),
            OPENWEATHER_API_KEY=os.getenv("OPENWEATHER_API_KEY", ""),
            TOMTOM_API_KEY=os.getenv("TOMTOM_API_KEY", ""),
            OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
            EMAIL_VIAJES_ENABLED=os.getenv("EMAIL_VIAJES_ENABLED", "false").lower() == "true",
            EMAIL_VIAJES_USER=os.getenv("EMAIL_VIAJES_USER", ""),
            EMAIL_VIAJES_PASSWORD=os.getenv("EMAIL_VIAJES_PASSWORD", ""),
            EMAIL_VIAJES_IMAP=os.getenv("EMAIL_VIAJES_IMAP", "imap.gmail.com"),
            EMAIL_VIAJES_INTERVALO=int(os.getenv("EMAIL_VIAJES_INTERVALO", "300")),
        )


def es_admin(user_id: int) -> bool:
    """Verifica si el usuario es administrador"""
    return user_id in (config.ADMIN_IDS or [])


# ============================================================
# GOOGLE DRIVE
# ============================================================

SCOPES = ['https://www.googleapis.com/auth/drive']

def inicializar_drive():
    """Inicializa Google Drive"""
    global drive_service
    
    creds = None
    token_path = 'token.pickle'
    
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(config.DRIVE_CREDENTIALS):
                logger.error(f"No se encontró {config.DRIVE_CREDENTIALS}")
                return False
            
            flow = InstalledAppFlow.from_client_secrets_file(
                config.DRIVE_CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
    
    drive_service = build('drive', 'v3', credentials=creds)
    logger.info("✅ Google Drive inicializado")
    return True


def descargar_excel_desde_drive() -> bool:
    """Descarga PRUEBO.xlsx desde Drive"""
    global drive_service
    
    if not drive_service:
        if not inicializar_drive():
            return False
    
    if not config.DRIVE_EXCEL_EMPRESA_ID:
        return False
    
    try:
        request = drive_service.files().get_media(fileId=config.DRIVE_EXCEL_EMPRESA_ID)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        with open(config.EXCEL_EMPRESA, 'wb') as f:
            f.write(fh.read())
        
        logger.info(f"✅ Excel descargado: {config.EXCEL_EMPRESA}")
        return True
    except Exception as e:
        logger.error(f"Error descargando Excel: {e}")
        return False


def subir_excel_a_drive() -> bool:
    """Sube PRUEBO.xlsx a Drive (actualiza el archivo existente)"""
    global drive_service
    
    logger.info("[DRIVE] Intentando subir Excel a Drive...")
    
    if not drive_service:
        logger.info("[DRIVE] drive_service no existe, inicializando...")
        if not inicializar_drive():
            logger.error("[DRIVE] No se pudo inicializar Drive")
            return False
    
    if not config.DRIVE_EXCEL_EMPRESA_ID:
        logger.warning("[DRIVE] No hay ID de Excel en Drive configurado")
        return False
    
    if not Path(config.EXCEL_EMPRESA).exists():
        logger.warning(f"[DRIVE] No existe el archivo local: {config.EXCEL_EMPRESA}")
        return False
    
    try:
        from googleapiclient.http import MediaFileUpload
        
        logger.info(f"[DRIVE] Subiendo {config.EXCEL_EMPRESA} a Drive ID: {config.DRIVE_EXCEL_EMPRESA_ID[:10]}...")
        
        media = MediaFileUpload(
            config.EXCEL_EMPRESA,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True
        )
        
        # Actualizar el archivo existente en Drive
        drive_service.files().update(
            fileId=config.DRIVE_EXCEL_EMPRESA_ID,
            media_body=media
        ).execute()
        
        logger.info(f"[DRIVE] ✅ Excel subido exitosamente a Drive")
        return True
    except Exception as e:
        logger.error(f"[DRIVE] Error subiendo Excel a Drive: {e}")
        return False


def subir_archivo_nuevo_a_drive(ruta_archivo: str, nombre_archivo: str = None, carpeta_id: str = None) -> bool:
    """
    Sube un archivo NUEVO a Drive (no actualiza, crea nuevo).
    
    Args:
        ruta_archivo: Ruta local del archivo a subir
        nombre_archivo: Nombre para el archivo en Drive (opcional, usa el nombre del archivo)
        carpeta_id: ID de la carpeta destino en Drive (opcional, usa la misma del Excel principal)
    
    Returns:
        bool: True si se subió correctamente
    """
    global drive_service
    
    if not drive_service:
        if not inicializar_drive():
            logger.error("[DRIVE] No se pudo inicializar Drive")
            return False
    
    if not Path(ruta_archivo).exists():
        logger.warning(f"[DRIVE] No existe el archivo: {ruta_archivo}")
        return False
    
    try:
        from googleapiclient.http import MediaFileUpload
        
        if nombre_archivo is None:
            nombre_archivo = Path(ruta_archivo).name
        
        # Obtener la carpeta padre del archivo principal
        if carpeta_id is None and config.DRIVE_EXCEL_EMPRESA_ID:
            try:
                file_info = drive_service.files().get(
                    fileId=config.DRIVE_EXCEL_EMPRESA_ID,
                    fields='parents'
                ).execute()
                parents = file_info.get('parents', [])
                if parents:
                    carpeta_id = parents[0]
            except Exception as e:
                logger.warning(f"[DRIVE] No se pudo obtener carpeta padre: {e}")
        
        logger.info(f"[DRIVE] Subiendo archivo nuevo: {nombre_archivo}")
        
        # Metadata del archivo
        file_metadata = {'name': nombre_archivo}
        if carpeta_id:
            file_metadata['parents'] = [carpeta_id]
        
        media = MediaFileUpload(
            ruta_archivo,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True
        )
        
        # Crear archivo nuevo en Drive
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'
        ).execute()
        
        logger.info(f"[DRIVE] ✅ Archivo subido: {file.get('name')} (ID: {file.get('id')})")
        return True
        
    except Exception as e:
        logger.error(f"[DRIVE] Error subiendo archivo nuevo: {e}")
        return False


# ============================================================
# DATABASE MANAGER
# ============================================================

class DatabaseManager:
    """Gestiona la base de datos"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def _query(self, query: str, params: tuple = (), fetch_one: bool = False):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                if fetch_one:
                    row = cursor.fetchone()
                    return dict(row) if row else None
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error SQL: {e}")
            return None
    
    def _update(self, query: str, params: tuple = ()) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error SQL: {e}")
            return False
    
    # --- CONDUCTORES ---
    
    def obtener_conductor(self, telegram_id: int) -> Optional[Dict]:
        return self._query(
            "SELECT * FROM conductores_empresa WHERE telegram_id = ?",
            (telegram_id,), fetch_one=True
        )
    
    def buscar_conductor_por_nombre(self, nombre: str) -> Optional[Dict]:
        return self._query(
            "SELECT * FROM conductores_empresa WHERE nombre LIKE ? LIMIT 1",
            (f"%{nombre}%",), fetch_one=True
        )
    
    def vincular_conductor(self, nombre: str, telegram_id: int) -> bool:
        return self._update(
            "UPDATE conductores_empresa SET telegram_id = ? WHERE nombre LIKE ?",
            (telegram_id, f"%{nombre}%")
        )
    
    def buscar_conductor_por_telefono(self, telefono: str) -> Optional[Dict]:
        """Busca un conductor por su teléfono"""
        return self._query(
            """SELECT * FROM conductores_empresa 
               WHERE telefono = ? 
               OR telefono = ? 
               OR telefono LIKE ?
               LIMIT 1""",
            (telefono, f"34{telefono}", f"%{telefono[-9:]}"),
            fetch_one=True
        )
    
    def vincular_conductor_por_telefono(self, telefono: str, telegram_id: int) -> bool:
        """Vincula un telegram_id a un conductor por su teléfono"""
        return self._update(
            """UPDATE conductores_empresa 
               SET telegram_id = ? 
               WHERE telefono = ? 
               OR telefono = ?
               OR telefono LIKE ?""",
            (telegram_id, telefono, f"34{telefono}", f"%{telefono[-9:]}")
        )
    
    def obtener_nombres_conductores(self) -> List[str]:
        result = self._query("SELECT nombre FROM conductores_empresa")
        return [r['nombre'] for r in result] if result else []
    
    def listar_conductores(self) -> List[Dict]:
        return self._query("SELECT * FROM conductores_empresa ORDER BY nombre") or []
    
    # --- VIAJES ---
    
    def obtener_viajes_conductor(self, nombre: str) -> List[Dict]:
        return self._query(
            "SELECT * FROM viajes_empresa WHERE conductor_asignado LIKE ? ORDER BY fila_excel",
            (f"%{nombre}%",)
        ) or []
    
    def obtener_todos_viajes(self) -> List[Dict]:
        return self._query("SELECT * FROM viajes_empresa ORDER BY fila_excel") or []
    
    def obtener_viajes_pendientes(self) -> List[Dict]:
        return self._query(
            "SELECT * FROM viajes_empresa WHERE conductor_asignado IS NULL OR conductor_asignado = '' ORDER BY precio DESC"
        ) or []
    
    # --- VEHÍCULOS ---
    
    def listar_vehiculos(self) -> List[Dict]:
        return self._query("SELECT * FROM vehiculos_empresa ORDER BY tipo, matricula") or []
    
    # --- RESUMEN ---
    
    def obtener_resumen(self) -> Dict:
        conductores = self._query("SELECT COUNT(*) as n FROM conductores_empresa", fetch_one=True)
        viajes = self._query("SELECT COUNT(*) as n FROM viajes_empresa", fetch_one=True)
        vehiculos = self._query("SELECT COUNT(*) as n FROM vehiculos_empresa", fetch_one=True)
        pendientes = self._query(
            "SELECT COUNT(*) as n FROM viajes_empresa WHERE conductor_asignado IS NULL OR conductor_asignado = ''",
            fetch_one=True
        )
        
        return {
            "conductores": conductores['n'] if conductores else 0,
            "viajes": viajes['n'] if viajes else 0,
            "vehiculos": vehiculos['n'] if vehiculos else 0,
            "pendientes": pendientes['n'] if pendientes else 0
        }


db = None


# ============================================================
# HANDLERS COMUNES (ambos perfiles)
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Pide teléfono para identificar al conductor"""
    user = update.effective_user
    admin = es_admin(user.id)
    
    logger.info(f"[START] {user.id} ({user.first_name}) - Admin: {admin}")
    
    conductor = db.obtener_conductor(user.id)
    
    # Si es ADMIN y no está vinculado como conductor, darle acceso directo
    if admin and not conductor:
        mensaje = (
            f"👋 ¡Hola {user.first_name}!\n"
            f"Perfil: 👔 RESPONSABLE\n\n"
            "COMANDOS ADMIN:\n"
            "/conductores - Ver todos\n"
            "/viajes_pendientes - Sin asignar\n"
            "/estado_flota - GPS de todos\n"
            "/asignar - Asignar viajes automáticamente\n"
            "/estadisticas - KPIs\n"
            "/sync - Sincronizar Excel\n"
        )
        
        teclado = obtener_teclado(es_admin=True, esta_vinculado=True)
        await update.message.reply_text(mensaje, reply_markup=teclado)
        return
    
    if conductor:
        # Ya está vinculado, mostrar bienvenida normal
        perfil = "👔 RESPONSABLE" if admin else "🚛 CONDUCTOR"
        nombre = conductor['nombre'].split()[0]
        
        mensaje = (
            f"👋 ¡Hola {nombre}!\n"
            f"Perfil: {perfil}\n\n"
            f"🚛 Tractora: {conductor.get('tractora', 'N/A')}\n"
            f"📍 Ubicación: {conductor.get('ubicacion', 'N/A')}\n\n"
        )
        
        if admin:
            mensaje += (
                "COMANDOS ADMIN:\n"
                "/conductores - Ver todos\n"
                "/viajes_pendientes - Sin asignar\n"
                "/estado_flota - GPS de todos\n"
                "/asignar - Asignar viajes automáticamente\n"
                "/estadisticas - KPIs\n"
                "/sync - Sincronizar Excel\n\n"
            )
        
        mensaje += (
            "COMANDOS PERSONALES:\n"
            "/mi_camion - Tu vehículo\n"
            "/mis_viajes - Tus viajes\n"
            "/mi_posicion - Tu GPS\n"
            "/clima [ciudad] - Tiempo\n"
            "/gasolineras [provincia] - Gasolineras\n"
        )
        
        teclado = obtener_teclado(es_admin=admin, esta_vinculado=True)
        await update.message.reply_text(mensaje, reply_markup=teclado)
        return
    
    # NO está vinculado y NO es admin - Pedir teléfono
    keyboard = [
        [KeyboardButton("📱 Compartir mi teléfono", request_contact=True)]
    ]
    
    await update.message.reply_text(
        f"👋 ¡Hola {user.first_name}!\n\n"
        "Para identificarte, necesito tu número de teléfono.\n\n"
        "🔒 Tu número solo se usará para vincular tu cuenta.\n\n"
        "Pulsa el botón de abajo 👇",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )


async def recibir_contacto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el contacto compartido y vincula al conductor"""
    user = update.effective_user
    contact = update.message.contact
    
    if not contact:
        await update.message.reply_text("❌ No se recibió el contacto")
        return
    
    # Obtener teléfono (quitar el prefijo +34 si existe)
    telefono = contact.phone_number
    if telefono.startswith('+'):
        telefono = telefono[1:]
    if telefono.startswith('34'):
        telefono = telefono[2:]
    
    telefono = telefono.strip()
    
    logger.info(f"[CONTACTO] {user.id} compartió teléfono: {telefono}")
    
    # Buscar conductor por teléfono
    conductor = db.buscar_conductor_por_telefono(telefono)
    
    if conductor:
        # Vincular telegram_id al conductor
        db.vincular_conductor_por_telefono(telefono, user.id)
        
        admin = es_admin(user.id)
        perfil = "👔 RESPONSABLE" if admin else "🚛 CONDUCTOR"
        nombre = conductor['nombre'].split()[0]
        
        teclado = obtener_teclado(es_admin=admin, esta_vinculado=True)
        
        await update.message.reply_text(
            f"✅ ¡Bienvenido {nombre}!\n\n"
            f"Perfil: {perfil}\n"
            f"🚛 Tractora: {conductor.get('tractora', 'N/A')}\n"
            f"📦 Remolque: {conductor.get('remolque', 'N/A')}\n\n"
            "Usa los botones de abajo 👇",
            reply_markup=teclado
        )
    else:
        await update.message.reply_text(
            f"❌ No encontré ningún conductor con el teléfono {telefono}\n\n"
            "📞 Contacta con tu responsable para que te den de alta.",
            reply_markup=ReplyKeyboardRemove()
        )


async def seleccion_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Gestiona selección de nombre"""
    user = update.effective_user
    texto = update.message.text
    
    if texto == "❌ No estoy en la lista":
        await update.message.reply_text(
            "📞 Contacta con tu responsable.",
            reply_markup=ReplyKeyboardRemove()
        )
        return True
    
    conductor = db.buscar_conductor_por_nombre(texto)
    
    if conductor:
        db.vincular_conductor(texto, user.id)
        conductor = db.obtener_conductor(user.id)
        perfil = "👔 RESPONSABLE" if es_admin(user.id) else "🚛 CONDUCTOR"
        
        teclado = obtener_teclado(es_admin=es_admin(user.id), esta_vinculado=True)
        await update.message.reply_text(
            f"✅ ¡Bienvenido {conductor['nombre'].split()[0]}!\n"
            f"Perfil: {perfil}\n\n"
            f"🚛 Tractora: {conductor.get('tractora', 'N/A')}\n"
            f"📦 Remolque: {conductor.get('remolque', 'N/A')}\n\n"
            "Usa los botones de abajo 👇",
            reply_markup=teclado
        )
        return True
    
    return False


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda"""
    user = update.effective_user
    admin = es_admin(user.id)
    
    mensaje = "📋 COMANDOS DISPONIBLES\n\n"
    
    if admin:
        mensaje += (
            "👔 ADMIN/RESPONSABLE:\n"
            "/conductores - Lista de conductores\n"
            "/viajes_pendientes - Viajes sin asignar\n"
            "/todos_viajes - Todos los viajes\n"
            "/estado_flota - GPS de toda la flota\n"
            "/cercanos [ciudad] - Vehículos cercanos\n"
            "/estadisticas - Resumen y KPIs\n"
            "/sync - Sincronizar Excel\n\n"
        )
    
    mensaje += (
        "🚛 PERSONAL:\n"
        "/mi_camion - Tu vehículo\n"
        "/mis_viajes - Tus viajes\n"
        "/mi_posicion - Tu ubicación GPS\n\n"
        "🌍 INFORMACIÓN:\n"
        "/clima [ciudad] - Tiempo\n"
        "/gasolineras [provincia] - Gasolineras baratas\n"
        "/trafico [zona] - Tráfico\n\n"
        "💬 También puedes escribir directamente:\n"
        "• \"mis viajes\"\n"
        "• \"tiempo en Madrid\"\n"
        "• \"gasolineras Navarra\""
    )
    
    await update.message.reply_text(mensaje)


# ============================================================
# HANDLERS CAMIONERO (datos propios)
# ============================================================

async def mi_camion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mi vehículo asignado - CON MANEJO DE ERRORES MEJORADO"""
    user = update.effective_user
    
    try:
        conductor = db.obtener_conductor(user.id)
        
        if not conductor:
            await update.message.reply_text(
                "❌ No estás vinculado.\n\n"
                "Usa /vincular TU_NOMBRE para vincularte."
            )
            return
        
        tractora = conductor.get('tractora', 'N/A')
        nombre = conductor.get('nombre', 'N/A')
        remolque = conductor.get('remolque', 'N/A')
        ubicacion = conductor.get('ubicacion', 'N/A')
        zona = conductor.get('zona', 'N/A')
        
        mensaje = (
            f"🚛 TU CAMIÓN\n"
            f"══════════════════════════════\n"
            f"👤 {nombre}\n"
            f"🚛 Tractora: {tractora}\n"
            f"📦 Remolque: {remolque}\n"
            f"📍 Base: {ubicacion}\n"
            f"🗺️ Zona: {zona}"
        )
        
        # GPS en tiempo real
        if movildata_api and tractora and tractora != 'N/A':
            try:
                pos = movildata_api.get_last_location_plate(tractora)
                if pos:
                    motor = "🟢 Encendido" if pos.get('motor_encendido') else "🔴 Apagado"
                    velocidad = pos.get('velocidad', 0)
                    municipio = pos.get('municipio', 'Desconocido')
                    provincia = pos.get('provincia', '')
                    
                    mensaje += (
                        f"\n\n📡 GPS EN TIEMPO REAL:\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📍 {municipio}, {provincia}\n"
                        f"🏎️ {velocidad} km/h\n"
                        f"⚙️ Motor: {motor}"
                    )
                    
                    # Link a ubicación
                    lat = pos.get('latitud')
                    lon = pos.get('longitud')
                    if lat and lon:
                        mensaje += f"\n🗺️ Maps: https://www.google.com/maps?q={lat},{lon}"
                else:
                    mensaje += "\n\n📡 GPS: Sin señal"
                    
            except Exception as e:
                logger.error(f"Error GPS en mi_camion: {e}")
                mensaje += "\n\n📡 GPS: Error de conexión"
            
            # Temperatura del frigorífico
            try:
                temp_data = movildata_api.get_temperatura_vehiculo(tractora)
                if temp_data:
                    temp_actual = temp_data.get('temperatura', 0)
                    estado_temp = temp_data.get('estado', 'OK')
                    
                    if estado_temp == 'OK':
                        emoji_temp = "✅"
                    elif estado_temp == 'ALERTA':
                        emoji_temp = "⚠️"
                    else:
                        emoji_temp = "🚨"
                    
                    mensaje += (
                        f"\n\n🌡️ FRIGORÍFICO:\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{emoji_temp} Temperatura: {temp_actual}°C"
                    )
            except Exception as e:
                logger.debug(f"Sin datos de temperatura: {e}")
        
        await update.message.reply_text(mensaje)
        
    except Exception as e:
        logger.error(f"Error en mi_camion: {e}")
        await update.message.reply_text(
            "❌ Error al obtener datos del camión.\n"
            "Intenta de nuevo en unos segundos."
        )
    

def generar_link_maps(direccion: str) -> str:
    if not direccion or str(direccion).lower() in ['nan', 'none', '']:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(direccion)}"

def generar_link_waze(direccion: str) -> str:
    if not direccion or str(direccion).lower() in ['nan', 'none', '']:
        return ""
    return f"https://waze.com/ul?q={urllib.parse.quote(direccion)}&navigate=yes"

def simular_horarios(km: int, indice_viaje: int = 0) -> dict:
    ahora = datetime.now()
    minutos_hasta_carga = random.randint(60, 120) if indice_viaje == 0 else 180 + (indice_viaje * 240)
    hora_carga = ahora + timedelta(minutes=minutos_hasta_carga)
    hora_carga = hora_carga.replace(minute=(hora_carga.minute // 15) * 15, second=0)
    km = km or 200
    minutos_viaje = int((km / 75) * 60) + random.randint(20, 45)
    hora_descarga = hora_carga + timedelta(minutes=minutos_viaje)
    hora_descarga = hora_descarga.replace(minute=(hora_descarga.minute // 15) * 15, second=0)
    return {
        "fecha_carga": hora_carga.strftime("%d/%m") if hora_carga.date() > ahora.date() else "Hoy",
        "hora_carga": hora_carga.strftime("%H:%M"),
        "fecha_descarga": hora_descarga.strftime("%d/%m") if hora_descarga.date() > ahora.date() else "Hoy",
        "hora_descarga": hora_descarga.strftime("%H:%M"),
    }

async def mis_viajes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mis viajes asignados - FORMATO DETALLADO"""
    user = update.effective_user
    conductor = db.obtener_conductor(user.id)
    
    if not conductor:
        await update.message.reply_text("👋 ¡Hola! Para empezar, pulsa el botón de abajo 👇", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚀 Comenzar")]], resize_keyboard=True, one_time_keyboard=True))
        return
    
    viajes = db.obtener_viajes_conductor(conductor['nombre'])
    
    if not viajes:
        await update.message.reply_text("📦 No tienes viajes asignados.")
        return
    
    mensaje = f"🚛 TUS VIAJES ({len(viajes)})\n"
    
    for i, v in enumerate(viajes[:3]):
        cliente = v.get('cliente', 'N/A')
        mercancia = v.get('mercancia', 'N/A')
        km = v.get('km', 0) or 0
        intercambio = v.get('intercambio', '')
        observaciones = v.get('observaciones', '')
        
        lugar_carga = v.get('direccion_carga') or v.get('lugar_carga', 'Sin especificar')
        lugar_descarga = v.get('direccion_descarga') or v.get('lugar_entrega', 'Sin especificar')
        
        if str(lugar_carga).lower() in ['nan', 'none', '']:
            lugar_carga = v.get('lugar_carga', 'Sin especificar')
        if str(lugar_descarga).lower() in ['nan', 'none', '']:
            lugar_descarga = v.get('lugar_entrega', 'Sin especificar')
        
        horarios = simular_horarios(km, i)
        hay_intercambio = intercambio and str(intercambio).upper().strip() == 'SI'
        
        mensaje += f"\n{'═'*30}\n"
        mensaje += f"📋 VIAJE {i+1}\n"
        mensaje += f"{'═'*30}\n"
        mensaje += f"📦 MERCANCÍA: {mercancia}\n"
        mensaje += f"📏 {km}km"
        if hay_intercambio:
            mensaje += f" | 🔄 Intercambio de palés"
        mensaje += "\n"
        
        # CARGA
        mensaje += f"\n{'━'*30}\n"
        mensaje += f"📥 CARGA - {cliente}\n"
        mensaje += f"{'━'*30}\n"
        mensaje += f"📍 {lugar_carga}\n"
        if hay_intercambio:
            mensaje += f"🔄 Intercambio de palés\n"
        mensaje += f"📅 {horarios['fecha_carga']} a las {horarios['hora_carga']}\n"
        link_maps = generar_link_maps(lugar_carga)
        link_waze = generar_link_waze(lugar_carga)
        if link_maps:
            mensaje += f"🗺️ Maps: {link_maps}\n"
        if link_waze:
            mensaje += f"🚗 Waze: {link_waze}\n"
        
        # DESCARGA
        mensaje += f"\n{'━'*30}\n"
        mensaje += f"📤 DESCARGA\n"
        mensaje += f"{'━'*30}\n"
        mensaje += f"📍 {lugar_descarga}\n"
        mensaje += f"📅 {horarios['fecha_descarga']} a las {horarios['hora_descarga']}\n"
        link_maps = generar_link_maps(lugar_descarga)
        link_waze = generar_link_waze(lugar_descarga)
        if link_maps:
            mensaje += f"🗺️ Maps: {link_maps}\n"
        if link_waze:
            mensaje += f"🚗 Waze: {link_waze}\n"
        
        if observaciones and str(observaciones).lower() not in ['nan', 'none', '']:
            mensaje += f"\n📝 NOTAS: {observaciones}\n"
    
    if len(viajes) > 3:
        mensaje += f"\n\n📋 Tienes {len(viajes) - 3} viaje(s) más."
    
    await update.message.reply_text(mensaje)


async def mi_posicion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mi posición GPS"""
    user = update.effective_user
    conductor = db.obtener_conductor(user.id)
    
    if not conductor:
        await update.message.reply_text("👋 ¡Hola! Para empezar, pulsa el botón de abajo 👇", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚀 Comenzar")]], resize_keyboard=True, one_time_keyboard=True))
        return
    
    tractora = conductor.get('tractora')
    
    if not tractora:
        await update.message.reply_text("❌ No tienes tractora asignada")
        return
    
    if movildata_api:
        pos = movildata_api.get_last_location_plate(tractora)
        if pos:
            motor = "🟢 Encendido" if pos.get('motor_encendido') else "🔴 Apagado"
            await update.message.reply_text(
                f"📍 TU POSICIÓN\n\n"
                f"🚛 {tractora}\n"
                f"📍 {pos.get('municipio', 'N/A')}, {pos.get('provincia', 'N/A')}\n"
                f"🛣️ {pos.get('direccion', 'N/A')}\n"
                f"🏎️ {pos.get('velocidad', 0)} km/h\n"
                f"⚙️ Motor: {motor}\n"
                f"🕐 {pos.get('fecha_hora', 'N/A')}"
            )
            return
    
    await update.message.reply_text(f"📍 Base: {conductor.get('ubicacion', 'N/A')}")


# ============================================================
# HANDLERS ADMIN (solo responsables)
# ============================================================

async def conductores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista de conductores (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    lista = db.listar_conductores()
    
    if not lista:
        await update.message.reply_text("No hay conductores.")
        return
    
    mensaje = f"👥 CONDUCTORES ({len(lista)})\n\n"
    
    for c in lista:
        vinculado = "✅" if c.get('telegram_id') else "⬜"
        mensaje += (
            f"{vinculado} {c['nombre']}\n"
            f"   🚛 {c.get('tractora', 'N/A')} | 📍 {c.get('ubicacion', 'N/A')}\n"
        )
    
    await update.message.reply_text(mensaje)


async def viajes_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Viajes sin asignar (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    viajes = db.obtener_viajes_pendientes()
    
    if not viajes:
        await update.message.reply_text("✅ No hay viajes pendientes.")
        return
    
    mensaje = f"📦 VIAJES PENDIENTES ({len(viajes)})\n\n"
    
    for v in viajes[:10]:
        mensaje += (
            f"• {v.get('cliente', 'N/A')}\n"
            f"  {v.get('lugar_carga', '?')} → {v.get('lugar_entrega', '?')}\n"
            f"  {v.get('mercancia', 'N/A')} | {v.get('precio', 0)}€\n\n"
        )
    
    if len(viajes) > 10:
        mensaje += f"... y {len(viajes)-10} más"
    
    await update.message.reply_text(mensaje)


async def todos_viajes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Todos los viajes (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    viajes = db.obtener_todos_viajes()
    
    if not viajes:
        await update.message.reply_text("No hay viajes.")
        return
    
    # Dividir en mensajes de máximo 10 viajes para no superar límite de Telegram
    VIAJES_POR_MENSAJE = 15
    total = len(viajes)
    
    for i in range(0, total, VIAJES_POR_MENSAJE):
        lote = viajes[i:i+VIAJES_POR_MENSAJE]
        
        if i == 0:
            mensaje = f"📦 TODOS LOS VIAJES ({total})\n"
            mensaje += "═" * 30 + "\n\n"
        else:
            mensaje = f"📦 VIAJES (continuación {i+1}-{min(i+VIAJES_POR_MENSAJE, total)})\n"
            mensaje += "═" * 30 + "\n\n"
        
        for v in lote:
            conductor = v.get('conductor_asignado', 'SIN ASIGNAR') or 'SIN ASIGNAR'
            cliente = v.get('cliente', 'N/A')
            carga = v.get('lugar_carga', '?')
            descarga = v.get('lugar_entrega', '?')
            precio = v.get('precio', 0) or 0
            km = v.get('km', 0) or 0
            
            # Icono según estado
            if conductor == 'SIN ASIGNAR':
                icono = "⚠️"
            else:
                icono = "✅"
            
            mensaje += f"{icono} {cliente} | {conductor}\n"
            mensaje += f"   📍 {carga} → {descarga}\n"
            mensaje += f"   💰 {precio}€ | 📏 {km}km\n\n"
        
        await update.message.reply_text(mensaje)


async def estado_flota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Estado de toda la flota (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    if not movildata_api:
        await update.message.reply_text("❌ GPS no disponible")
        return
    
    estados = movildata_api.get_last_vehicles_status()
    
    mensaje = "🚛 ESTADO DE LA FLOTA\n"
    mensaje += "═" * 30 + "\n"
    mensaje += "🟢 Disponible | 🟡 Cargando/Descargando\n"
    mensaje += "🔵 En ruta | 🔴 Descanso/Otro\n"
    mensaje += "═" * 30 + "\n\n"
    
    for e in estados:
        matricula = e.get('matricula', 'N/A')
        conductor = e.get('conductor_nombre', 'N/A')
        estado = e.get('estado', 'DESCONOCIDO')
        
        # Emoji según estado
        if estado == "DISPONIBLE":
            emoji = "🟢"
        elif estado in ["CARGANDO", "DESCARGANDO"]:
            emoji = "🟡"
        elif estado == "EN_RUTA":
            emoji = "🔵"
        else:
            emoji = "🔴"
        
        mensaje += f"{emoji} {matricula} - {conductor}\n"
        
        # Obtener ubicación GPS
        pos = movildata_api.get_last_location_plate(matricula)
        if pos:
            municipio = pos.get('municipio', '?')
            provincia = pos.get('provincia', '')
            mensaje += f"   📍 {municipio}, {provincia}\n"
        
        mensaje += "\n"
    
    await update.message.reply_text(mensaje)


async def cercanos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vehículos cercanos a un punto (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /cercanos [ciudad]\nEjemplo: /cercanos Calahorra")
        return
    
    ciudad = " ".join(context.args).upper()
    
    if not movildata_api:
        await update.message.reply_text("❌ GPS no disponible")
        return
    
    # Obtener coordenadas de la ciudad
    coords = movildata_api.UBICACIONES_BASE.get(ciudad)
    
    if not coords:
        ciudades = ", ".join(list(movildata_api.UBICACIONES_BASE.keys())[:5])
        await update.message.reply_text(
            f"❌ Ciudad no encontrada: {ciudad}\n\n"
            f"Ciudades disponibles: {ciudades}..."
        )
        return
    
    cercanos = movildata_api.get_geoneearest_vehicles_to_point(coords['lat'], coords['lon'])
    
    mensaje = f"📍 VEHÍCULOS CERCANOS A {ciudad}\n\n"
    
    for i, v in enumerate(cercanos[:5], 1):
        mensaje += (
            f"{i}. {v['matricula']} - {v.get('conductor', 'N/A')}\n"
            f"   📍 {v.get('distancia_km', 0):.1f} km | {v.get('estado', 'N/A')}\n"
        )
    
    await update.message.reply_text(mensaje)


async def estadisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Estadísticas (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    resumen = db.obtener_resumen()
    
    # Calcular más datos
    viajes = db.obtener_todos_viajes()
    km_total = sum(v.get('km', 0) for v in viajes)
    facturacion = sum(v.get('precio', 0) for v in viajes)
    
    await update.message.reply_text(
        f"📊 ESTADÍSTICAS\n\n"
        f"👥 Conductores: {resumen['conductores']}\n"
        f"🚛 Vehículos: {resumen['vehiculos']}\n"
        f"📦 Viajes totales: {resumen['viajes']}\n"
        f"⏳ Pendientes: {resumen['pendientes']}\n\n"
        f"📏 KM totales: {km_total:,}\n"
        f"💰 Facturación: {facturacion:,.0f}€"
    )


async def cmd_informe_semanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera y envía el informe semanal (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    await update.message.reply_text("📊 Generando informe semanal...")
    
    try:
        from informes import InformesBot
        informes = InformesBot(DB_PATH)
        informe = informes.informe_semanal()
        await update.message.reply_text(informe)
    except Exception as e:
        logger.error(f"Error informe semanal: {e}")
        await update.message.reply_text("❌ Error generando informe. ¿Hay viajes en los últimos 7 días?")


async def cmd_rentabilidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra análisis de rentabilidad por rutas (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    await update.message.reply_text("💰 Analizando rentabilidad...")
    
    try:
        from informes import InformesBot
        informes = InformesBot(DB_PATH)
        analisis = informes.analisis_rentabilidad()
        await update.message.reply_text(analisis)
    except Exception as e:
        logger.error(f"Error análisis rentabilidad: {e}")
        await update.message.reply_text("❌ Error en análisis. ¿Hay suficientes viajes?")


async def sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sincronizar Excel (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    await update.message.reply_text("🔄 Sincronizando...")
    
    # Descargar de Drive
    if config.DRIVE_ENABLED and config.DRIVE_EXCEL_EMPRESA_ID:
        if descargar_excel_desde_drive():
            await update.message.reply_text("✅ Excel descargado de Drive")
        else:
            await update.message.reply_text("⚠️ Error descargando de Drive")
    
    # Procesar
    if separador_excel:
        resultado = separador_excel.sincronizar_desde_archivo(config.EXCEL_EMPRESA, forzar=True)
        
        if resultado.get('exito'):
            # Sincronizar teléfonos de las notas
            tel_result = sincronizar_telefonos(config.EXCEL_EMPRESA, config.DB_PATH)
            
            # Sincronizar direcciones
            dir_result = sincronizar_direcciones(config.DB_PATH)
            
            await update.message.reply_text(
                f"✅ Sincronización exitosa!\n\n"
                f"👥 Conductores: {resultado.get('conductores', 0)}\n"
                f"📦 Viajes: {resultado.get('viajes', 0)}\n"
                f"🚛 Vehículos: {resultado.get('vehiculos', 0)}\n"
                f"📱 Teléfonos: {tel_result.get('actualizados', 0)}\n"
                f"📍 Direcciones: {dir_result.get('actualizados', 0)}"
            )
        else:
            await update.message.reply_text(f"❌ Error: {resultado.get('error')}")


async def asignar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asignar viajes pendientes automáticamente (SOLO ADMIN)"""
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Comando solo para responsables.")
        return
    
    await update.message.reply_text("🤖 Analizando viajes y conductores...")
    
    asig = obtener_asignador()
    if not asig:
        await update.message.reply_text("❌ Asignador no disponible")
        return
    
    resultado = asig.asignar_viajes_pendientes()
    
    if resultado['viajes_pendientes'] == 0:
        await update.message.reply_text("✅ No hay viajes pendientes de asignar")
        return
    
    mensaje = f"🤖 ASIGNACIÓN AUTOMÁTICA\n\n"
    mensaje += f"📦 Viajes pendientes: {resultado['viajes_pendientes']}\n"
    mensaje += f"✅ Asignados: {resultado['viajes_asignados']}\n"
    mensaje += f"❌ Sin conductor: {resultado['viajes_sin_conductor']}\n"
    
    if resultado['asignaciones']:
        mensaje += f"\n{'═'*30}\n"
        mensaje += "📋 DETALLE:\n"
        for a in resultado['asignaciones']:
            mensaje += f"\n• {a['cliente']}\n"
            mensaje += f"  {a['ruta']}\n"
            mensaje += f"  → {a['conductor']} ({a['matricula']})\n"
            mensaje += f"  📍 A {a['distancia_a_carga']} km de la carga\n"
    
    await update.message.reply_text(mensaje)
    
    # Notificar a los conductores
    if resultado['viajes_asignados'] > 0:
        notif = obtener_notificador()
        if notif:
            await notif.verificar_y_notificar()
            await update.message.reply_text("📱 Conductores notificados")


# ============================================================
# CONSULTAR RUTAS (ADMIN)
# ============================================================

async def consultar_rutas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Muestra lista de conductores con viajes asignados.
    Solo para ADMIN.
    """
    user = update.effective_user
    
    if not es_admin(user.id):
        await update.message.reply_text("❌ Solo administradores pueden usar esta función.")
        return
    
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        # Obtener conductores con viajes
        cursor.execute("""
            SELECT conductor_asignado, COUNT(*) as num_viajes, SUM(km) as km_total
            FROM viajes_empresa 
            WHERE conductor_asignado IS NOT NULL AND conductor_asignado != ''
            GROUP BY conductor_asignado
            ORDER BY num_viajes DESC
            LIMIT 20
        """)
        
        conductores = cursor.fetchall()
        conn.close()
        
        if not conductores:
            await update.message.reply_text(
                "📋 CONSULTAR RUTAS\n"
                "══════════════════════════════\n\n"
                "❌ No hay viajes asignados a ningún conductor."
            )
            return
        
        # Crear botones inline
        botones = []
        for c in conductores:
            nombre = c[0]
            num = c[1]
            km = c[2] or 0
            
            # Acortar nombre si es muy largo
            nombre_corto = nombre[:20] + "..." if len(nombre) > 20 else nombre
            texto_boton = f"{nombre_corto} ({num} viajes)"
            
            # callback_data tiene límite de 64 bytes
            callback = f"rutas:{nombre[:30]}"
            
            botones.append([InlineKeyboardButton(texto_boton, callback_data=callback)])
        
        teclado = InlineKeyboardMarkup(botones)
        
        mensaje = (
            "📋 CONSULTAR RUTAS\n"
            "══════════════════════════════\n\n"
            f"👥 {len(conductores)} conductores con viajes asignados\n\n"
            "Selecciona un conductor para ver sus viajes:"
        )
        
        await update.message.reply_text(mensaje, reply_markup=teclado)
        
    except Exception as e:
        logger.error(f"Error en consultar_rutas: {e}")
        await update.message.reply_text("❌ Error al consultar rutas.")


async def callback_ver_rutas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback cuando se pulsa un conductor para ver sus rutas.
    """
    query = update.callback_query
    await query.answer()
    
    # Extraer nombre del conductor del callback_data
    data = query.data  # "rutas:NOMBRE_CONDUCTOR"
    nombre_conductor = data.replace("rutas:", "")
    
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Buscar conductor (puede ser parcial)
        cursor.execute("""
            SELECT DISTINCT conductor_asignado
            FROM viajes_empresa
            WHERE conductor_asignado LIKE ?
            LIMIT 1
        """, (f"{nombre_conductor}%",))
        
        resultado = cursor.fetchone()
        if resultado:
            nombre_conductor = resultado[0]
        
        # Obtener viajes
        cursor.execute("""
            SELECT id, cliente, lugar_carga, lugar_entrega, mercancia, km
            FROM viajes_empresa 
            WHERE conductor_asignado = ?
            ORDER BY id
        """, (nombre_conductor,))
        
        viajes = cursor.fetchall()
        conn.close()
        
        if not viajes:
            await query.edit_message_text(f"❌ No hay viajes para {nombre_conductor}")
            return
        
        # Construir mensaje
        mensaje = (
            f"📋 VIAJES DE {nombre_conductor}\n"
            f"══════════════════════════════\n\n"
            f"📦 Total: {len(viajes)} viajes\n\n"
        )
        
        ultima_descarga = None
        km_viajes = 0
        km_desplazamientos = 0
        ruta_lugares = []
        
        for i, v in enumerate(viajes, 1):
            lugar_carga = v['lugar_carga'] or '?'
            lugar_entrega = v['lugar_entrega'] or '?'
            km = v['km'] or 0
            cliente = v['cliente'] or '?'
            mercancia = v['mercancia'] or ''
            
            km_viajes += km
            
            # Guardar para ruta visual
            if lugar_carga not in ruta_lugares:
                ruta_lugares.append(lugar_carga)
            ruta_lugares.append(lugar_entrega)
            
            mensaje += f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            mensaje += f"📦 {i}. {cliente}\n"
            
            # Desplazamiento
            if ultima_descarga:
                lat1, lon1 = _obtener_coords_rutas(ultima_descarga)
                lat2, lon2 = _obtener_coords_rutas(lugar_carga)
                
                if lat1 and lat2:
                    dist = _calcular_distancia_rutas(lat1, lon1, lat2, lon2)
                    km_desplazamientos += dist
                    mensaje += f"🚛 {ultima_descarga} → {lugar_carga} ({dist:.0f}km)\n"
            
            mensaje += f"📥 {lugar_carga}\n"
            mensaje += f"📤 {lugar_entrega}\n"
            mensaje += f"📏 {km} km\n"
            
            # Tipo de mercancía
            if mercancia:
                merc_upper = mercancia.upper()
                if 'CONGEL' in merc_upper or '-18' in merc_upper:
                    mensaje += f"🥶 {mercancia[:30]}\n"
                elif 'REFRIG' in merc_upper or '+2' in merc_upper:
                    mensaje += f"❄️ {mercancia[:30]}\n"
            
            mensaje += "\n"
            ultima_descarga = lugar_entrega
        
        # Resumen
        mensaje += f"══════════════════════════════\n"
        mensaje += f"📊 RESUMEN\n"
        mensaje += f"══════════════════════════════\n"
        mensaje += f"📏 Km viajes: {km_viajes}\n"
        mensaje += f"🚛 Km desplazamientos: {km_desplazamientos:.0f}\n"
        mensaje += f"📍 TOTAL: {km_viajes + km_desplazamientos:.0f} km\n\n"
        
        # Ruta visual (simplificada si es muy larga)
        if len(ruta_lugares) > 8:
            ruta_txt = " → ".join(ruta_lugares[:4]) + " → ... → " + " → ".join(ruta_lugares[-2:])
        else:
            ruta_txt = " → ".join(ruta_lugares)
        
        mensaje += f"🗺️ {ruta_txt}"
        
        # Telegram tiene límite de 4096 caracteres
        if len(mensaje) > 4000:
            mensaje = mensaje[:3950] + "\n\n... (mensaje truncado)"
        
        # Botón para volver
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Volver a lista", callback_data="rutas:volver")]
        ])
        
        await query.edit_message_text(mensaje, reply_markup=teclado)
        
    except Exception as e:
        logger.error(f"Error en callback_ver_rutas: {e}")
        await query.edit_message_text(f"❌ Error al obtener viajes de {nombre_conductor}")


async def callback_rutas_volver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Volver a la lista de conductores"""
    query = update.callback_query
    await query.answer()
    
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT conductor_asignado, COUNT(*) as num_viajes, SUM(km) as km_total
            FROM viajes_empresa 
            WHERE conductor_asignado IS NOT NULL AND conductor_asignado != ''
            GROUP BY conductor_asignado
            ORDER BY num_viajes DESC
            LIMIT 20
        """)
        
        conductores = cursor.fetchall()
        conn.close()
        
        if not conductores:
            await query.edit_message_text("❌ No hay viajes asignados.")
            return
        
        botones = []
        for c in conductores:
            nombre = c[0]
            num = c[1]
            nombre_corto = nombre[:20] + "..." if len(nombre) > 20 else nombre
            texto_boton = f"{nombre_corto} ({num} viajes)"
            callback = f"rutas:{nombre[:30]}"
            botones.append([InlineKeyboardButton(texto_boton, callback_data=callback)])
        
        teclado = InlineKeyboardMarkup(botones)
        
        mensaje = (
            "📋 CONSULTAR RUTAS\n"
            "══════════════════════════════\n\n"
            f"👥 {len(conductores)} conductores con viajes asignados\n\n"
            "Selecciona un conductor para ver sus viajes:"
        )
        
        await query.edit_message_text(mensaje, reply_markup=teclado)
        
    except Exception as e:
        logger.error(f"Error en callback_rutas_volver: {e}")
        await query.edit_message_text("❌ Error al cargar la lista.")


async def callback_incidencia_listo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback cuando el conductor pulsa 'Listo' después de reportar incidencia"""
    query = update.callback_query
    await query.answer()
    
    from teclados import teclado_conductor
    
    await query.edit_message_text("✅ Incidencia registrada correctamente.")
    await query.message.reply_text(
        "¿Qué más necesitas?",
        reply_markup=teclado_conductor
    )


# ============================================================
# HANDLERS INFORMACIÓN (ambos)
# ============================================================

async def clima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clima"""
    ciudad = " ".join(context.args) if context.args else "Madrid"
    await update.message.reply_text(f"🔍 Consultando tiempo en {ciudad}...")
    resultado = await obtener_clima(ciudad, config.OPENWEATHER_API_KEY)
    await update.message.reply_text(resultado)


async def gasolineras(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Gasolineras MEJORADAS - busca en la ruta del conductor.
    
    Si el conductor tiene viajes asignados, busca gasolineras
    a lo largo de la ruta (provincia origen → provincias intermedias → destino)
    """
    user = update.effective_user
    conductor = db.obtener_conductor(user.id)
    
    provincia = " ".join(context.args) if context.args else None
    lat_usuario = None
    lon_usuario = None
    lugar_destino = None
    buscar_en_ruta = False
    
    if conductor:
        tractora = conductor.get('tractora')
        nombre = conductor.get('nombre', '')
        
        # Obtener GPS actual
        if movildata_api and tractora:
            pos = movildata_api.get_last_location_plate(tractora)
            if pos:
                lat_usuario = pos.get('latitud')
                lon_usuario = pos.get('longitud')
                if not provincia:
                    provincia = pos.get('provincia')
        
        # Obtener viajes asignados para buscar en ruta
        try:
            conn = sqlite3.connect(config.DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Buscar viaje actual del conductor
            cursor.execute("""
                SELECT lugar_carga, lugar_entrega 
                FROM viajes_empresa 
                WHERE conductor_asignado = ? 
                AND estado != 'completado'
                LIMIT 1
            """, (nombre,))
            
            viaje = cursor.fetchone()
            if viaje:
                lugar_destino = viaje['lugar_entrega']
                buscar_en_ruta = True
                
                # Si no tenemos provincia, usar la del lugar de carga
                if not provincia:
                    lugar_carga = viaje['lugar_carga']
                    # Mapeo básico
                    mapeo = {
                        'AZAGRA': 'Navarra', 'TUDELA': 'Navarra', 'PAMPLONA': 'Navarra',
                        'MELIDA': 'Navarra', 'MÉLIDA': 'Navarra', 'SAN ADRIAN': 'Navarra',
                        'CALAHORRA': 'La Rioja', 'LOGROÑO': 'La Rioja', 'ALFARO': 'La Rioja',
                        'ZARAGOZA': 'Zaragoza', 'MADRID': 'Madrid', 'BARCELONA': 'Barcelona',
                        'MURCIA': 'Murcia', 'BADAJOZ': 'Badajoz', 'MERIDA': 'Badajoz',
                        'SEVILLA': 'Sevilla', 'VALENCIA': 'Valencia',
                    }
                    for lugar, prov in mapeo.items():
                        if lugar in lugar_carga.upper():
                            provincia = prov
                            break
            
            conn.close()
        except Exception as e:
            logger.error(f"Error obteniendo viaje para gasolineras: {e}")
        
        # Si no hay GPS ni viaje, usar base del conductor
        if not provincia:
            ubicacion = conductor.get('ubicacion', '')
            mapeo = {
                'AZAGRA': 'Navarra', 'TUDELA': 'Navarra', 'PAMPLONA': 'Navarra',
                'CALAHORRA': 'La Rioja', 'LOGROÑO': 'La Rioja',
                'ZARAGOZA': 'Zaragoza', 'MADRID': 'Madrid',
            }
            provincia = mapeo.get(ubicacion.upper(), 'Navarra')
    
    if not provincia:
        provincia = "Navarra"
    
    # Mensaje de búsqueda
    if buscar_en_ruta and lugar_destino:
        await update.message.reply_text(f"🔍 Buscando gasolineras en tu ruta hacia {lugar_destino}...")
    else:
        await update.message.reply_text(f"🔍 Buscando gasolineras en {provincia}...")
    
    # Llamar a la API mejorada
    resultado = await obtener_gasolineras(
        provincia, 
        lat_usuario, 
        lon_usuario,
        lugar_destino=lugar_destino,
        mostrar_ruta=buscar_en_ruta
    )
    await update.message.reply_text(resultado)



async def trafico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tráfico"""
    zona = " ".join(context.args) if context.args else "Madrid"
    await update.message.reply_text(f"🔍 Consultando tráfico en {zona}...")
    resultado = await obtener_trafico(zona, config.TOMTOM_API_KEY)
    await update.message.reply_text(resultado)


# ============================================================
# HANDLER MENSAJES TEXTO
# ============================================================

async def mensaje_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensajes de texto con GPT"""
    global inteligencia
    
    user = update.effective_user
    texto = update.message.text
    admin = es_admin(user.id)
    
    logger.info(f"[MSG] {user.id} (admin={admin}): {texto}")

    if es_boton(texto):
        accion = obtener_accion_boton(texto)
        
        # Submenús admin
        if accion == "menu_viajes":
            await update.message.reply_text(
                "📦 *VIAJES Y RUTAS*\n\nSelecciona una opción:",
                parse_mode="Markdown",
                reply_markup=teclado_viajes
            )
            return
        elif accion == "menu_flota":
            await update.message.reply_text(
                "🚛 *FLOTA*\n\nSelecciona una opción:",
                parse_mode="Markdown",
                reply_markup=teclado_flota
            )
            return
        elif accion == "menu_informes":
            await update.message.reply_text(
                "📊 *INFORMES*\n\nSelecciona una opción:",
                parse_mode="Markdown",
                reply_markup=teclado_informes
            )
            return
        elif accion == "volver_menu":
            await update.message.reply_text(
                "¿Qué necesitas?",
                reply_markup=teclado_admin
            )
            return
        
        # Acciones existentes
        if accion == "mis_viajes":
            return await mis_viajes(update, context)
        elif accion == "gasolineras":
            return await gasolineras(update, context)
        elif accion == "mi_ubicacion":
            return await mi_posicion(update, context)        
        elif accion == "mi_camion":
            return await mi_camion(update, context)
        elif accion == "resumen":
            if es_admin(user.id):
                return await estadisticas(update, context)
            else:
                return await resumen_conductor(update, context)
        elif accion == "asignar":
            return await asignacion_manual.inicio(update, context)
        elif accion == "conductores":
            return await conductores(update, context)
        elif accion == "todos_viajes":
            return await todos_viajes(update, context)
        elif accion == "estado_flota":
            return await estado_flota(update, context)
        elif accion == "estadisticas":
            return await estadisticas(update, context)
        elif accion == "sync":
            return await sync(update, context)
        elif accion == "consultar_rutas":
            return await consultar_rutas(update, context)
        elif accion == "modificar_viaje_ruta":
            return await modificador_ruta.inicio(update, context)   
        elif accion == "informe_semanal":
            return await cmd_informe_semanal(update, context)
        elif accion == "rentabilidad":
            return await cmd_rentabilidad(update, context)
        elif accion == "vincular":
            await update.message.reply_text(
                "Para vincularte usa:\n/vincular TU_NOMBRE\n\nEjemplo: /vincular LUIS ARNALDO"
            )
         
        return
    
    # Botón "Comenzar" para nuevos usuarios
    if texto == "🚀 Comenzar":
        return await start(update, context)
    
    conductor = db.obtener_conductor(user.id)
    
    if not conductor:
        # Si es admin, puede usar inteligencia sin estar vinculado
        if admin and inteligencia:
            conductor = {"nombre": "Admin", "tractora": "", "remolque": "", "ubicacion": ""}
            respuesta, accion = inteligencia.responder(user.id, texto, conductor, admin)
            
            if accion:
                await update.message.reply_text(respuesta)
                if accion == 'menu_gestiones':
                    return await gestiones_manager.inicio(update, context)
                elif accion == 'añadir_conductor':
                    return await gestiones_manager.inicio_añadir_conductor(update, context)
                elif accion == 'añadir_viaje':
                    return await gestiones_manager.inicio_añadir_viaje(update, context)
                elif accion == 'modificar_conductor':
                    return await gestiones_manager.inicio_modificar_conductor(update, context)
                elif accion == 'modificar_viaje':
                    return await gestiones_manager.inicio_modificar_viaje(update, context)
                return

            teclado = obtener_teclado(es_admin=admin, esta_vinculado=True)
            await update.message.reply_text(
                respuesta, 
                parse_mode='Markdown', 
                disable_web_page_preview=True,
                reply_markup=teclado
            )
            return
        
        # Usuario normal no vinculado
        nombres = db.obtener_nombres_conductores()
        if texto in nombres or texto == "❌ No estoy en la lista":
            await seleccion_nombre(update, context)
            return
        
        await update.message.reply_text("👋 ¡Hola! Para empezar, pulsa el botón de abajo 👇", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚀 Comenzar")]], resize_keyboard=True, one_time_keyboard=True))
        return
    
    if inteligencia:
        respuesta, accion = inteligencia.responder(user.id, texto, conductor, admin)
        
        # Si detectó una intención de gestión (solo admin)
        if accion and admin:
            await update.message.reply_text(respuesta)
            
            if accion == 'menu_gestiones':
                return await gestiones_manager.inicio(update, context)
            elif accion == 'añadir_conductor':
                return await gestiones_manager.inicio_añadir_conductor(update, context)
            elif accion == 'añadir_viaje':
                return await gestiones_manager.inicio_añadir_viaje(update, context)
            elif accion == 'modificar_conductor':
                return await gestiones_manager.inicio_modificar_conductor(update, context)
            elif accion == 'modificar_viaje':
                return await gestiones_manager.inicio_modificar_viaje(update, context)
            elif accion == 'modificar_viaje_ruta':
                return await modificador_ruta.inicio(update, context)
            return
        
        # Respuesta normal CON TECLADO
        teclado = obtener_teclado(es_admin=admin, esta_vinculado=True)
        await update.message.reply_text(
            respuesta, 
            parse_mode='Markdown', 
            disable_web_page_preview=True,
            reply_markup=teclado
        )
    else:
        teclado = obtener_teclado(es_admin=admin, esta_vinculado=True)
        await update.message.reply_text("Usa /ayuda para ver comandos.", reply_markup=teclado)
    
    # Si detectó una intención de gestión (solo admin)
# ============================================================
# SYNC AUTOMÁTICA
# ============================================================

async def sync_automatica(context: ContextTypes.DEFAULT_TYPE):
    """Sincronización automática"""
    global separador_excel
    
    try:
        if config.DRIVE_ENABLED and config.DRIVE_EXCEL_EMPRESA_ID:
            descargar_excel_desde_drive()
        
        if separador_excel and Path(config.EXCEL_EMPRESA).exists():
            resultado = separador_excel.sincronizar_desde_archivo(config.EXCEL_EMPRESA)
            if resultado.get('cambios'):
                logger.info(f"[SYNC] Cambios: {resultado}")
            
            # Sincronizar teléfonos de las notas
            sincronizar_telefonos(config.EXCEL_EMPRESA, config.DB_PATH)
            
            # Sincronizar direcciones
            sincronizar_direcciones(config.DB_PATH)
            
            # Asignar viajes pendientes automáticamente
            # Asignar viajes pendientes (solo si ASIGNACION_AUTO=true en .env)
            if config.ASIGNACION_AUTO:
                asig = obtener_asignador()
                if asig:
                    resultado_asignacion = asig.asignar_viajes_pendientes()
                    if resultado_asignacion.get('viajes_asignados', 0) > 0:
                        logger.info(f"[SYNC] Viajes asignados: {resultado_asignacion['viajes_asignados']}")
            
            # Notificar viajes nuevos (después de asignar)
            notif = obtener_notificador()
            if notif:
                await notif.verificar_y_notificar()
            
    except Exception as e:
        logger.error(f"Error sync: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Errores"""
    logger.error(f"Error: {context.error}", exc_info=context.error)


# ============================================================
# MAIN
# ============================================================

def main():
    """Función principal"""
    global separador_excel, movildata_api, inteligencia, db, notificador, asignador, asignacion_manual
    
    logger.info("=" * 60)
    logger.info("BOT TRANSPORTE v2.0 - PERFILES DUAL")
    logger.info(f"Admins configurados: {config.ADMIN_IDS}")
    logger.info("=" * 60)
    
    # Base de datos
    db = DatabaseManager(config.DB_PATH)
    
    # Google Drive
    if config.DRIVE_ENABLED:
        if inicializar_drive() and config.DRIVE_EXCEL_EMPRESA_ID:
            descargar_excel_desde_drive()
    
    # Separador Excel
    separador_excel = SeparadorExcelEmpresa(config.DB_PATH)
    logger.info("✅ Separador Excel")
    
    # Sync inicial
    if Path(config.EXCEL_EMPRESA).exists():
        resultado = separador_excel.sincronizar_desde_archivo(config.EXCEL_EMPRESA, forzar=True)
        logger.info(f"✅ Sync inicial: {resultado}")
        
        # Sincronizar teléfonos de las notas
        tel_result = sincronizar_telefonos(config.EXCEL_EMPRESA, config.DB_PATH)
        logger.info(f"✅ Teléfonos sincronizados: {tel_result.get('actualizados', 0)}")
        
        # Sincronizar direcciones
        dir_result = sincronizar_direcciones(config.DB_PATH)
        logger.info(f"✅ Direcciones sincronizadas: {dir_result.get('actualizados', 0)}")
    
    # Movildata GPS
    movildata_api = MovildataAPI()
    logger.info("✅ Movildata GPS")
    
    # Asignador de viajes (con actualización de Excel y subida a Drive)
    asignador = inicializar_asignador(
        config.DB_PATH, 
        movildata_api,
        excel_path=config.EXCEL_EMPRESA,
        on_excel_updated=subir_excel_a_drive if config.DRIVE_ENABLED else None
    )
    logger.info("✅ Asignador de viajes")
    
    # Asignación manual
    asignacion_manual = AsignacionManual(
        db_path=config.DB_PATH,
        excel_path=config.EXCEL_EMPRESA,
        on_excel_updated=subir_excel_a_drive if config.DRIVE_ENABLED else None,
        admin_ids=config.ADMIN_IDS,
        movildata_api=movildata_api,
    )
    logger.info("✅ Asignación manual")
    
    # Inteligencia dual
    inteligencia = InteligenciaDual(config.DB_PATH, movildata_api)
    logger.info("✅ Inteligencia GPT")
    
    # Telegram
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()
    
    # Inicializar notificador de viajes (necesita el bot)
    notificador = inicializar_notificador(config.DB_PATH, app.bot)
    logger.info("✅ Notificador de viajes")
    
    # Comandos comunes
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("help", ayuda))
    
    # Comandos camionero
    app.add_handler(CommandHandler("mi_camion", mi_camion))
    app.add_handler(CommandHandler("mi_vehiculo", mi_camion))
    app.add_handler(CommandHandler("mis_viajes", mis_viajes))
    app.add_handler(CommandHandler("mi_posicion", mi_posicion))
    
    # Comandos admin
    app.add_handler(CommandHandler("conductores", conductores))
    app.add_handler(CommandHandler("viajes_pendientes", viajes_pendientes))
    app.add_handler(CommandHandler("todos_viajes", todos_viajes))
    app.add_handler(CommandHandler("estado_flota", estado_flota))
    app.add_handler(CommandHandler("cercanos", cercanos))
    app.add_handler(CommandHandler("estadisticas", estadisticas))
    app.add_handler(CommandHandler("sync", sync))
    app.add_handler(CommandHandler("asignar", asignar))
    
    # Comandos info
    app.add_handler(CommandHandler("gasolineras", gasolineras))
    app.add_handler(CommandHandler("trafico", trafico))
    
    # Handler para contacto compartido (teléfono)
    app.add_handler(MessageHandler(filters.CONTACT, recibir_contacto))
    
    # Handler para gestiones (camioneros y viajes)
    global gestiones_manager
    gestiones_manager = GestionesManager(config.EXCEL_EMPRESA, config.DB_PATH, es_admin, subir_excel_a_drive)
    app.add_handler(gestiones_manager.get_conversation_handler())
    # Modificador de viajes en ruta
    global modificador_ruta
    modificador_ruta = ModificadorViajesRuta(
        excel_path=config.EXCEL_EMPRESA,
        db_path=config.DB_PATH,
        es_admin_func=es_admin,
        subir_drive_func=subir_excel_a_drive,
        bot=app.bot,
        movildata_api=movildata_api
    )
    app.add_handler(modificador_ruta.get_conversation_handler())
    logger.info("✅ Gestiones manager")
    
    # Registros de conductor (llegada/salida en carga/descarga)
    registros = crear_registros_conductor(
        config.EXCEL_EMPRESA,
        config.DB_PATH,
        subir_excel_a_drive if config.DRIVE_ENABLED else None
    )
    app.add_handler(registros.get_conversation_handler())
    logger.info("✅ Registros conductor")
    
    # Incidencias de conductor
    incidencias = crear_incidencias_conductor(
        config.DB_PATH,
        app.bot,
        config.ADMIN_IDS
    )
    app.add_handler(incidencias.get_conversation_handler())
    logger.info("✅ Incidencias conductor")
    
    # Cierre de día
    global cierre_dia_handler
    cierre = crear_cierre_dia(
        config.EXCEL_EMPRESA,
        config.DB_PATH,
        subir_excel_a_drive if config.DRIVE_ENABLED else None,
        subir_archivo_nuevo_a_drive if config.DRIVE_ENABLED else None
    )
    cierre_dia_handler = crear_cierre_handler(cierre, es_admin, teclado_admin)
    app.add_handler(cierre_dia_handler.get_conversation_handler())
    logger.info("✅ Cierre de día")

    # Añadir handler en main() (después de línea 2165)
    conductores_panel = crear_conductores_panel(
        config.EXCEL_EMPRESA,
        config.DB_PATH,
        es_admin,
        subir_excel_a_drive if config.DRIVE_ENABLED else None
    )
    app.add_handler(conductores_panel.get_conversation_handler())
    logger.info("✅ Panel conductores")
    
    # Handlers para callbacks de rutas (ADMIN)
    app.add_handler(CallbackQueryHandler(callback_ver_rutas, pattern="^rutas:(?!volver)"))
    app.add_handler(CallbackQueryHandler(callback_rutas_volver, pattern="^rutas:volver$"))
    app.add_handler(CallbackQueryHandler(callback_incidencia_listo, pattern="^inc_listo$"))
    logger.info("✅ Consultar rutas")
    
    # Asignación manual de viajes
    asignacion_manual.registrar_handlers(app)
    logger.info("✅ Handlers asignación manual")
    
    # Mensajes texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_texto))
    
    # Errores
    app.add_error_handler(error_handler)
    
    # Sync automática
    if app.job_queue:
        app.job_queue.run_repeating(sync_automatica, interval=config.SYNC_INTERVAL, first=30)
    
    # Lector de emails de viajes
    if config.EMAIL_VIAJES_ENABLED and config.EMAIL_VIAJES_USER:
        lector_emails = LectorEmailsViajes(
            email_user=config.EMAIL_VIAJES_USER,
            email_password=config.EMAIL_VIAJES_PASSWORD,
            openai_api_key=config.OPENAI_API_KEY,
            excel_path=config.EXCEL_EMPRESA,
            db_path=config.DB_PATH,
            drive_service=drive_service,
            drive_excel_id=config.DRIVE_EXCEL_EMPRESA_ID,
            imap_server=config.EMAIL_VIAJES_IMAP,
            confianza_minima=70
        )
        crear_job_lector_emails(app, lector_emails, config.ADMIN_IDS, config.EMAIL_VIAJES_INTERVALO)
        logger.info("✅ Lector de emails activo")
    
    if config.MONITOR_RETRASOS_ENABLED:
        monitor_retrasos = MonitorRetrasos(
            db_path=config.DB_PATH,
            excel_path=config.EXCEL_EMPRESA,
            bot=app.bot,
            admin_ids=config.ADMIN_IDS,
        )
        app.job_queue.run_repeating(
            monitor_retrasos.verificar_retrasos,
            interval=config.MONITOR_RETRASOS_INTERVALO,
            first=120,  # esperar 2min al arrancar (dar tiempo al sync)
        )
        # Reset diario a medianoche
        app.job_queue.run_daily(
            lambda ctx: monitor_retrasos.resetear_alertas_diarias(),
            time=datetime.strptime("00:00", "%H:%M").time(),
        )
        logger.info(f"✅ Monitor retrasos activo (cada {config.MONITOR_RETRASOS_INTERVALO}s, umbral 25%)")

    logger.info("=" * 60)
    logger.info("✅ Bot activo")
    logger.info("=" * 60)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        config = Config.from_env()
        main()
    except Exception as e:
        logger.critical(f"Error: {e}", exc_info=True)
        raise
