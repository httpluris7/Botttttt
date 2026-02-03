"""
BACKUP AUTOMÁTICO v1.0
======================
Sistema de copias de seguridad para la base de datos del bot.

Opciones:
- Backup local con rotación (mantiene últimos 7 días)
- Envío por email
- Subida a Google Drive (requiere configuración)

Uso:
    python backup_automatico.py              # Backup local
    python backup_automatico.py --email      # Backup + envío email
    python backup_automatico.py --drive      # Backup + Google Drive
    python backup_automatico.py --all        # Todo

Programar en Windows (Task Scheduler) o Linux (cron):
    # Cada día a las 02:00
    0 2 * * * cd /ruta/bot && python backup_automatico.py --email
"""

import os
import sys
import shutil
import sqlite3
import smtplib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIGURACIÓN
# ============================================================

# Rutas
DB_PATH = os.getenv("DB_PATH", "viajes.db")
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "7"))  # Días a mantener

# Email (configurar en .env)
EMAIL_SMTP = os.getenv("EMAIL_SMTP", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")  # App password para Gmail
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO", "")

# Google Drive (requiere google-api-python-client)
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# FUNCIONES DE BACKUP
# ============================================================

def crear_backup_local() -> str:
    """
    Crea una copia de seguridad local de la base de datos.
    Retorna la ruta del archivo creado.
    """
    # Crear directorio si no existe
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    
    # Nombre del archivo con fecha y hora
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"viajes_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    # Verificar que existe la BD original
    if not os.path.exists(DB_PATH):
        logger.error(f"❌ No se encuentra la base de datos: {DB_PATH}")
        return None
    
    try:
        # Usar backup de SQLite para consistencia
        conn_origen = sqlite3.connect(DB_PATH)
        conn_backup = sqlite3.connect(backup_path)
        
        conn_origen.backup(conn_backup)
        
        conn_backup.close()
        conn_origen.close()
        
        # Obtener tamaño
        size_kb = os.path.getsize(backup_path) // 1024
        
        logger.info(f"✅ Backup creado: {backup_path} ({size_kb} KB)")
        
        # Registrar en BD
        registrar_backup(backup_filename, size_kb, "LOCAL")
        
        return backup_path
        
    except Exception as e:
        logger.error(f"❌ Error creando backup: {e}")
        return None


def limpiar_backups_antiguos():
    """Elimina backups más antiguos que MAX_BACKUPS días."""
    if not os.path.exists(BACKUP_DIR):
        return
    
    fecha_limite = datetime.now() - timedelta(days=MAX_BACKUPS)
    eliminados = 0
    
    for archivo in os.listdir(BACKUP_DIR):
        if archivo.startswith("viajes_backup_") and archivo.endswith(".db"):
            ruta = os.path.join(BACKUP_DIR, archivo)
            fecha_archivo = datetime.fromtimestamp(os.path.getmtime(ruta))
            
            if fecha_archivo < fecha_limite:
                os.remove(ruta)
                eliminados += 1
                logger.info(f"🗑️ Eliminado backup antiguo: {archivo}")
    
    if eliminados > 0:
        logger.info(f"🧹 Limpieza: {eliminados} backups antiguos eliminados")


def enviar_por_email(backup_path: str) -> bool:
    """Envía el backup por email."""
    if not all([EMAIL_USER, EMAIL_PASS, EMAIL_DESTINO]):
        logger.warning("⚠️ Email no configurado. Añade EMAIL_USER, EMAIL_PASS, EMAIL_DESTINO al .env")
        return False
    
    try:
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_DESTINO
        msg['Subject'] = f"🗄️ Backup Bot Transporte - {datetime.now().strftime('%Y-%m-%d')}"
        
        # Cuerpo del mensaje
        body = f"""
Backup automático del bot de transporte.

📅 Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}
📁 Archivo: {os.path.basename(backup_path)}
📊 Tamaño: {os.path.getsize(backup_path) // 1024} KB

Este es un mensaje automático.
        """
        msg.attach(MIMEText(body, 'plain'))
        
        # Adjuntar archivo
        with open(backup_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={os.path.basename(backup_path)}'
            )
            msg.attach(part)
        
        # Enviar
        server = smtplib.SMTP(EMAIL_SMTP, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"✅ Backup enviado por email a {EMAIL_DESTINO}")
        registrar_backup(os.path.basename(backup_path), 0, "EMAIL")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error enviando email: {e}")
        return False


def subir_a_drive(backup_path: str) -> bool:
    """Sube el backup a Google Drive."""
    if not DRIVE_FOLDER_ID:
        logger.warning("⚠️ Google Drive no configurado. Añade DRIVE_FOLDER_ID al .env")
        return False
    
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        import pickle
        
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        creds = None
        
        # Cargar credenciales guardadas
        if os.path.exists('token_drive.pickle'):
            with open('token_drive.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        # Si no hay credenciales válidas, autenticar
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials_drive.json'):
                    logger.error("❌ Falta credentials_drive.json para Google Drive")
                    return False
                flow = InstalledAppFlow.from_client_secrets_file('credentials_drive.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token_drive.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        # Subir archivo
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': os.path.basename(backup_path),
            'parents': [DRIVE_FOLDER_ID]
        }
        media = MediaFileUpload(backup_path, mimetype='application/x-sqlite3')
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        logger.info(f"✅ Backup subido a Google Drive (ID: {file.get('id')})")
        registrar_backup(os.path.basename(backup_path), 0, "DRIVE")
        return True
        
    except ImportError:
        logger.error("❌ Instala google-api-python-client: pip install google-api-python-client google-auth-oauthlib")
        return False
    except Exception as e:
        logger.error(f"❌ Error subiendo a Drive: {e}")
        return False


def registrar_backup(archivo: str, tamaño_kb: int, destino: str):
    """Registra el backup en la base de datos."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO backups (archivo, tamaño_kb, destino, estado)
            VALUES (?, ?, ?, 'OK')
        """, (archivo, tamaño_kb, destino))
        
        conn.commit()
        conn.close()
    except:
        pass  # La tabla puede no existir aún


def verificar_integridad(backup_path: str) -> bool:
    """Verifica que el backup es válido."""
    try:
        conn = sqlite3.connect(backup_path)
        cursor = conn.cursor()
        
        # Verificar tablas principales
        cursor.execute("SELECT COUNT(*) FROM viajes")
        viajes = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM conductores")
        conductores = cursor.fetchone()[0]
        
        conn.close()
        
        logger.info(f"✅ Backup verificado: {viajes} viajes, {conductores} conductores")
        return True
        
    except Exception as e:
        logger.error(f"❌ Backup corrupto: {e}")
        return False


# ============================================================
# MAIN
# ============================================================

def main():
    """Ejecuta el proceso de backup."""
    print("="*50)
    print("🗄️ BACKUP AUTOMÁTICO - Bot Transporte")
    print("="*50)
    
    # Parsear argumentos
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    enviar_email = '--email' in args or '--all' in args
    subir_drive = '--drive' in args or '--all' in args
    
    # 1. Crear backup local
    print("\n📦 Creando backup local...")
    backup_path = crear_backup_local()
    
    if not backup_path:
        print("❌ Error creando backup. Abortando.")
        sys.exit(1)
    
    # 2. Verificar integridad
    print("\n🔍 Verificando integridad...")
    if not verificar_integridad(backup_path):
        print("⚠️ Advertencia: El backup puede estar corrupto")
    
    # 3. Limpiar backups antiguos
    print("\n🧹 Limpiando backups antiguos...")
    limpiar_backups_antiguos()
    
    # 4. Enviar por email (opcional)
    if enviar_email:
        print("\n📧 Enviando por email...")
        enviar_por_email(backup_path)
    
    # 5. Subir a Drive (opcional)
    if subir_drive:
        print("\n☁️ Subiendo a Google Drive...")
        subir_a_drive(backup_path)
    
    print("\n" + "="*50)
    print("✅ BACKUP COMPLETADO")
    print("="*50)


if __name__ == "__main__":
    main()
