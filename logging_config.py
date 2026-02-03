"""
SISTEMA DE LOGS MEJORADO v1.0
=============================
Logging profesional para el bot de transporte.

Características:
- Archivo rotativo (nuevo archivo cada día o al llegar a 5MB)
- Niveles por módulo
- Alertas por email en errores críticos
- Formato estructurado para análisis

Uso:
    from logging_config import setup_logging, get_logger
    
    # Al inicio del bot
    setup_logging()
    
    # En cada módulo
    logger = get_logger(__name__)
    logger.info("Mensaje informativo")
    logger.error("Error que se enviará por email")
"""

import os
import sys
import logging
import smtplib
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import sqlite3

load_dotenv()


# ============================================================
# CONFIGURACIÓN
# ============================================================

# Directorio de logs
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE = os.getenv("LOG_FILE", "bot_transporte.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Rotación
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_LOG_FILES = 30  # Mantener 30 archivos

# Email para alertas críticas
ALERT_EMAIL_ENABLED = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
ALERT_EMAIL_SMTP = os.getenv("EMAIL_SMTP", "smtp.gmail.com")
ALERT_EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
ALERT_EMAIL_USER = os.getenv("EMAIL_USER", "")
ALERT_EMAIL_PASS = os.getenv("EMAIL_PASS", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

# Base de datos para logs críticos
DB_PATH = os.getenv("DB_PATH", "viajes.db")

# Niveles por módulo (personalizable)
MODULE_LEVELS = {
    "bot_transporte": "INFO",
    "apis_externas": "INFO",
    "asignador_viajes": "INFO",
    "inteligencia_dual": "DEBUG",
    "httpx": "WARNING",
    "telegram": "WARNING",
    "urllib3": "WARNING",
}


# ============================================================
# HANDLER PERSONALIZADO PARA ALERTAS
# ============================================================

class EmailAlertHandler(logging.Handler):
    """Handler que envía emails en errores críticos."""
    
    def __init__(self, level=logging.ERROR):
        super().__init__(level)
        self.last_alert = {}
        self.cooldown = 300  # 5 minutos entre alertas del mismo tipo
    
    def emit(self, record):
        if not ALERT_EMAIL_ENABLED:
            return
        
        if not all([ALERT_EMAIL_USER, ALERT_EMAIL_PASS, ALERT_EMAIL_TO]):
            return
        
        # Evitar spam: cooldown por mensaje
        msg_key = f"{record.name}:{record.getMessage()[:50]}"
        now = datetime.now().timestamp()
        
        if msg_key in self.last_alert:
            if now - self.last_alert[msg_key] < self.cooldown:
                return
        
        self.last_alert[msg_key] = now
        
        try:
            self._send_alert(record)
        except:
            pass  # No queremos que falle el logging por el email
    
    def _send_alert(self, record):
        """Envía el email de alerta."""
        msg = MIMEMultipart()
        msg['From'] = ALERT_EMAIL_USER
        msg['To'] = ALERT_EMAIL_TO
        msg['Subject'] = f"🚨 ALERTA BOT TRANSPORTE - {record.levelname}"
        
        body = f"""
⚠️ ALERTA DEL BOT DE TRANSPORTE

📅 Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
🔴 Nivel: {record.levelname}
📦 Módulo: {record.name}
📍 Ubicación: {record.pathname}:{record.lineno}

📝 Mensaje:
{record.getMessage()}

{'='*50}
Traceback:
{record.exc_text if record.exc_text else 'N/A'}
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(ALERT_EMAIL_SMTP, ALERT_EMAIL_PORT)
        server.starttls()
        server.login(ALERT_EMAIL_USER, ALERT_EMAIL_PASS)
        server.send_message(msg)
        server.quit()


class DatabaseLogHandler(logging.Handler):
    """Handler que guarda errores críticos en la base de datos."""
    
    def __init__(self, level=logging.ERROR):
        super().__init__(level)
    
    def emit(self, record):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO logs_criticos (modulo, nivel, mensaje)
                VALUES (?, ?, ?)
            """, (record.name, record.levelname, record.getMessage()))
            
            conn.commit()
            conn.close()
        except:
            pass  # La tabla puede no existir


# ============================================================
# FORMATEADORES
# ============================================================

class ColoredFormatter(logging.Formatter):
    """Formateador con colores para consola."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Verde
        'WARNING': '\033[33m',   # Amarillo
        'ERROR': '\033[31m',     # Rojo
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Añadir color al nivel
        record.levelname = f"{color}{record.levelname}{reset}"
        
        return super().format(record)


# ============================================================
# SETUP PRINCIPAL
# ============================================================

def setup_logging(level: str = None, log_file: str = None):
    """
    Configura el sistema de logging completo.
    
    Args:
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Ruta al archivo de log (opcional)
    """
    # Crear directorio de logs
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    
    # Determinar nivel
    log_level = getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO)
    
    # Archivo de log
    log_path = os.path.join(LOG_DIR, log_file or LOG_FILE)
    
    # Configurar logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capturar todo, filtrar por handler
    
    # Limpiar handlers existentes
    root_logger.handlers.clear()
    
    # ========== HANDLER: Consola ==========
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Formato con colores para consola
    console_format = ColoredFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # ========== HANDLER: Archivo (rotativo por tamaño) ==========
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_SIZE,
        backupCount=MAX_LOG_FILES,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)  # Guardar todo en archivo
    
    file_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)
    
    # ========== HANDLER: Archivo diario ==========
    daily_log_path = os.path.join(LOG_DIR, "bot_diario.log")
    daily_handler = TimedRotatingFileHandler(
        daily_log_path,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    daily_handler.setLevel(logging.INFO)
    daily_handler.setFormatter(file_format)
    daily_handler.suffix = "%Y-%m-%d"
    root_logger.addHandler(daily_handler)
    
    # ========== HANDLER: Alertas por email ==========
    if ALERT_EMAIL_ENABLED:
        email_handler = EmailAlertHandler(level=logging.ERROR)
        email_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s\n%(message)s'
        )
        email_handler.setFormatter(email_format)
        root_logger.addHandler(email_handler)
    
    # ========== HANDLER: Base de datos ==========
    db_handler = DatabaseLogHandler(level=logging.ERROR)
    root_logger.addHandler(db_handler)
    
    # ========== Configurar niveles por módulo ==========
    for module_name, module_level in MODULE_LEVELS.items():
        module_logger = logging.getLogger(module_name)
        module_logger.setLevel(getattr(logging, module_level.upper()))
    
    # Log de inicio
    root_logger.info("="*50)
    root_logger.info("🚀 Sistema de logging iniciado")
    root_logger.info(f"   Nivel: {LOG_LEVEL}")
    root_logger.info(f"   Archivo: {log_path}")
    root_logger.info(f"   Alertas email: {'Sí' if ALERT_EMAIL_ENABLED else 'No'}")
    root_logger.info("="*50)


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger configurado para un módulo.
    
    Args:
        name: Nombre del módulo (típicamente __name__)
    
    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    
    # Aplicar nivel específico si está configurado
    if name in MODULE_LEVELS:
        logger.setLevel(getattr(logging, MODULE_LEVELS[name].upper()))
    
    return logger


# ============================================================
# FUNCIONES DE UTILIDAD
# ============================================================

def log_viaje(viaje_id: int, accion: str, detalles: str = ""):
    """Log específico para acciones de viajes."""
    logger = get_logger("viajes")
    logger.info(f"[VIAJE #{viaje_id}] {accion} - {detalles}")


def log_conductor(conductor: str, accion: str, detalles: str = ""):
    """Log específico para acciones de conductores."""
    logger = get_logger("conductores")
    logger.info(f"[{conductor}] {accion} - {detalles}")


def log_api(api_name: str, status: str, tiempo_ms: int = 0):
    """Log específico para llamadas a APIs."""
    logger = get_logger("apis")
    logger.info(f"[API:{api_name}] {status} ({tiempo_ms}ms)")


def log_error_critico(modulo: str, error: Exception, contexto: str = ""):
    """Log de error crítico con toda la información."""
    logger = get_logger(modulo)
    logger.critical(
        f"❌ ERROR CRÍTICO\n"
        f"   Módulo: {modulo}\n"
        f"   Error: {type(error).__name__}: {str(error)}\n"
        f"   Contexto: {contexto}",
        exc_info=True
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    print("🧪 Test del sistema de logging\n")
    
    # Configurar
    setup_logging(level="DEBUG")
    
    # Obtener logger
    logger = get_logger("test")
    
    # Probar niveles
    logger.debug("Este es un mensaje DEBUG")
    logger.info("Este es un mensaje INFO")
    logger.warning("Este es un mensaje WARNING")
    logger.error("Este es un mensaje ERROR")
    
    # Probar funciones específicas
    log_viaje(123, "ASIGNADO", "Conductor: ALEJANDRO")
    log_conductor("ALEJANDRO", "LOGIN", "Telegram ID: 12345")
    log_api("GASOLINERAS", "OK", 234)
    
    print("\n✅ Test completado. Revisa la carpeta 'logs/'")
