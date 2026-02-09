#!/usr/bin/env python3
"""
SINCRONIZACIÓN AUTOMÁTICA
==========================
Descarga Excel de Drive y sincroniza con la BD.
Ejecutar con cron cada 5 minutos.

Uso:
    python3 sync_automatico.py

Cron (cada 5 minutos):
    */5 * * * * cd /root/bot-transporte/Botttttt && /root/bot-transporte/venv/bin/python3 sync_automatico.py >> /var/log/sync_transporte.log 2>&1
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

# Configuración
EXCEL_EMPRESA = os.getenv("EXCEL_EMPRESA", "PRUEBO.xlsx")
DB_PATH = os.getenv("DB_PATH", "logistica.db")
DRIVE_ENABLED = os.getenv("DRIVE_ENABLED", "false").lower() == "true"
DRIVE_CREDENTIALS = os.getenv("DRIVE_CREDENTIALS", "credentials.json")
DRIVE_EXCEL_EMPRESA_ID = os.getenv("DRIVE_EXCEL_EMPRESA_ID", "")

# Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive']
drive_service = None


def inicializar_drive():
    """Inicializa conexión con Google Drive"""
    global drive_service
    
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import pickle
        
        creds = None
        
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(DRIVE_CREDENTIALS):
                    logger.error(f"No se encontró {DRIVE_CREDENTIALS}")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(DRIVE_CREDENTIALS, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        drive_service = build('drive', 'v3', credentials=creds)
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando Drive: {e}")
        return False


def descargar_excel_desde_drive() -> bool:
    """Descarga PRUEBO.xlsx desde Drive"""
    global drive_service
    
    if not drive_service:
        if not inicializar_drive():
            return False
    
    if not DRIVE_EXCEL_EMPRESA_ID:
        logger.warning("No hay ID de Excel en Drive configurado")
        return False
    
    try:
        from googleapiclient.http import MediaIoBaseDownload
        import io
        
        request = drive_service.files().get_media(fileId=DRIVE_EXCEL_EMPRESA_ID)
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        with open(EXCEL_EMPRESA, 'wb') as f:
            f.write(fh.getvalue())
        
        logger.info(f"✅ Excel descargado: {EXCEL_EMPRESA}")
        return True
        
    except Exception as e:
        logger.error(f"Error descargando Excel: {e}")
        return False


def sincronizar_bd() -> dict:
    """Sincroniza Excel con la BD"""
    try:
        from separador_excel_empresa import SeparadorExcelEmpresa
        from extractor_telefonos import sincronizar_telefonos
        from generador_direcciones import sincronizar_direcciones
        
        separador = SeparadorExcelEmpresa(DB_PATH)
        resultado = separador.sincronizar_desde_archivo(EXCEL_EMPRESA, forzar=False)
        
        if resultado.get('cambios'):
            # Sincronizar teléfonos y direcciones si hubo cambios
            sincronizar_telefonos(EXCEL_EMPRESA, DB_PATH)
            sincronizar_direcciones(DB_PATH)
            logger.info(f"✅ BD sincronizada: {resultado}")
        else:
            logger.debug("Sin cambios en el Excel")
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error sincronizando BD: {e}")
        return {"exito": False, "error": str(e)}


def main():
    """Función principal"""
    logger.info("="*50)
    logger.info(f"🔄 Sync automático - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Paso 1: Descargar Excel de Drive (si está habilitado)
    if DRIVE_ENABLED and DRIVE_EXCEL_EMPRESA_ID:
        if not descargar_excel_desde_drive():
            logger.warning("No se pudo descargar Excel de Drive, usando local")
    
    # Paso 2: Verificar que existe el Excel
    if not Path(EXCEL_EMPRESA).exists():
        logger.error(f"Excel no encontrado: {EXCEL_EMPRESA}")
        sys.exit(1)
    
    # Paso 3: Sincronizar con BD
    resultado = sincronizar_bd()
    
    if resultado.get('exito'):
        if resultado.get('cambios'):
            logger.info(f"✅ Sync completado: {resultado.get('conductores', 0)} conductores, "
                       f"{resultado.get('viajes', 0)} viajes")
        else:
            logger.debug("✅ Sin cambios")
    else:
        logger.error(f"❌ Error en sync: {resultado.get('error', 'desconocido')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
