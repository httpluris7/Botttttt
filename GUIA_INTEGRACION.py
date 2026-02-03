# ============================================================
# GUÍA DE INTEGRACIÓN v2.0
# Nuevas funcionalidades: Informes, Backups, Logs mejorados
# ============================================================

"""
ARCHIVOS INCLUIDOS:
1. actualizar_bd_v2.sql  - Nuevas tablas para la BD
2. backup_automatico.py  - Sistema de backups
3. logging_config.py     - Logs mejorados
4. informes.py          - Informes y estadísticas
5. ejemplo.env          - Variables de entorno nuevas

PASOS DE INSTALACIÓN:
"""

# ============================================================
# PASO 1: ACTUALIZAR BASE DE DATOS
# ============================================================
"""
Ejecutar en terminal:

    sqlite3 viajes.db < actualizar_bd_v2.sql

O desde Python:

    import sqlite3
    conn = sqlite3.connect('viajes.db')
    with open('actualizar_bd_v2.sql', 'r') as f:
        conn.executescript(f.read())
    conn.close()
"""


# ============================================================
# PASO 2: AÑADIR AL INICIO DE bot_transporte.py
# ============================================================

# Añadir estos imports al principio del archivo:
IMPORTS_NUEVOS = """
# Nuevos imports v2.0
from logging_config import setup_logging, get_logger
from informes import (
    generar_informe_semanal,
    generar_analisis_rentabilidad,
    generar_estadisticas_conductor,
    generar_resumen_rapido
)
"""

# Cambiar el inicio del logging (buscar donde se configura logging):
SETUP_LOGGING = """
# Configurar sistema de logs mejorado
setup_logging()
logger = get_logger(__name__)
"""


# ============================================================
# PASO 3: AÑADIR NUEVOS BOTONES AL ADMIN (teclados.py)
# ============================================================

BOTONES_ADMIN_NUEVO = """
BOTONES_ADMIN = [
    ["🤖 Asignar viajes", "📦 Todos los viajes"],
    ["👥 Conductores", "🗺️ Estado de la flota"],
    ["📋 Consultar rutas", "📊 Estadísticas"],
    ["📈 Informe semanal", "💰 Rentabilidad"],  # NUEVO
    ["🔄 Sincronizar", "🛠️ Gestiones"]
]
"""

# Añadir al diccionario ACCIONES:
ACCIONES_NUEVAS = """
    "📈 informe semanal": "informe_semanal",
    "💰 rentabilidad": "rentabilidad",
"""


# ============================================================
# PASO 4: AÑADIR HANDLERS EN bot_transporte.py
# ============================================================

# Buscar la función mensaje_texto() y añadir estos casos:

HANDLERS_NUEVOS = '''
# En la función mensaje_texto(), añadir estos elif:

elif accion == "informe_semanal":
    return await cmd_informe_semanal(update, context)

elif accion == "rentabilidad":
    return await cmd_rentabilidad(update, context)
'''


# ============================================================
# PASO 5: AÑADIR FUNCIONES DE COMANDOS
# ============================================================

# Añadir estas funciones antes de main():

FUNCIONES_COMANDOS = '''
# ============================================================
# COMANDOS DE INFORMES
# ============================================================

async def cmd_informe_semanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera y envía el informe semanal."""
    if not es_admin(update.effective_chat.id):
        await update.message.reply_text("⛔ Solo para administradores")
        return
    
    await update.message.reply_text("📊 Generando informe semanal...")
    
    try:
        informe = await generar_informe_semanal(DB_PATH)
        await update.message.reply_text(informe)
    except Exception as e:
        logger.error(f"Error informe semanal: {e}")
        await update.message.reply_text("❌ Error generando informe")


async def cmd_rentabilidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra análisis de rentabilidad por rutas."""
    if not es_admin(update.effective_chat.id):
        await update.message.reply_text("⛔ Solo para administradores")
        return
    
    await update.message.reply_text("💰 Analizando rentabilidad...")
    
    try:
        analisis = await generar_analisis_rentabilidad(DB_PATH)
        await update.message.reply_text(analisis)
    except Exception as e:
        logger.error(f"Error análisis rentabilidad: {e}")
        await update.message.reply_text("❌ Error en análisis")


async def cmd_estadisticas_conductor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas de un conductor específico."""
    # Obtener nombre del conductor del contexto o mensaje
    conductor = context.user_data.get('conductor_actual', '')
    
    if not conductor:
        # Si es conductor, mostrar sus propias estadísticas
        chat_id = update.effective_chat.id
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM conductores WHERE telegram_id = ?", (chat_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            conductor = row[0]
        else:
            await update.message.reply_text("❌ No se pudo identificar el conductor")
            return
    
    try:
        stats = await generar_estadisticas_conductor(conductor, DB_PATH)
        await update.message.reply_text(stats)
    except Exception as e:
        logger.error(f"Error estadísticas: {e}")
        await update.message.reply_text("❌ Error generando estadísticas")
'''


# ============================================================
# PASO 6: PROGRAMAR BACKUPS AUTOMÁTICOS
# ============================================================

"""
WINDOWS (Programador de tareas):
1. Abrir "Programador de tareas"
2. Crear tarea básica
3. Nombre: "Backup Bot Transporte"
4. Desencadenador: Diariamente a las 02:00
5. Acción: Iniciar programa
   - Programa: python
   - Argumentos: backup_automatico.py --email
   - Iniciar en: C:\\ruta\\al\\bot

LINUX (Cron):
1. Editar crontab: crontab -e
2. Añadir línea:
   0 2 * * * cd /ruta/al/bot && python backup_automatico.py --email

Para probar manualmente:
    python backup_automatico.py
    python backup_automatico.py --email
    python backup_automatico.py --all
"""


# ============================================================
# PASO 7: CONFIGURAR VARIABLES DE ENTORNO
# ============================================================

"""
Añadir a tu archivo .env:

# Backups
BACKUP_DIR=backups
MAX_BACKUPS=7

# Logs
LOG_DIR=logs
LOG_LEVEL=INFO

# Alertas por email (opcional pero recomendado)
ALERT_EMAIL_ENABLED=true
EMAIL_SMTP=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=tu_email@gmail.com
EMAIL_PASS=tu_app_password_de_google
EMAIL_DESTINO=admin@empresa.com
"""


# ============================================================
# RESUMEN DE ARCHIVOS
# ============================================================

"""
📁 ESTRUCTURA FINAL:

bot_transporte/
├── bot_transporte.py      # Bot principal (modificar)
├── teclados.py            # Teclados (modificar)
├── apis_externas.py       # APIs externas
├── asignador_viajes.py    # Asignador inteligente
├── inteligencia_dual.py   # IA del bot
├── informes.py            # NUEVO - Sistema de informes
├── logging_config.py      # NUEVO - Logs mejorados
├── backup_automatico.py   # NUEVO - Backups
├── viajes.db              # Base de datos
├── .env                   # Variables de entorno
├── logs/                  # NUEVO - Directorio de logs
│   ├── bot_transporte.log
│   └── bot_diario.log
└── backups/               # NUEVO - Directorio de backups
    └── viajes_backup_YYYYMMDD.db
"""


# ============================================================
# TEST RÁPIDO
# ============================================================

if __name__ == "__main__":
    print("🧪 Verificando instalación...\n")
    
    # Verificar imports
    try:
        from informes import InformesBot
        print("✅ informes.py OK")
    except ImportError as e:
        print(f"❌ informes.py: {e}")
    
    try:
        from logging_config import setup_logging
        print("✅ logging_config.py OK")
    except ImportError as e:
        print(f"❌ logging_config.py: {e}")
    
    # Verificar BD
    import os
    import sqlite3
    
    db_path = os.getenv("DB_PATH", "viajes.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar tablas nuevas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tablas = [row[0] for row in cursor.fetchall()]
        
        tablas_nuevas = ['rutas_frecuentes', 'gastos', 'backups', 'logs_criticos', 'informes']
        for tabla in tablas_nuevas:
            if tabla in tablas:
                print(f"✅ Tabla {tabla} existe")
            else:
                print(f"⚠️ Tabla {tabla} NO existe - ejecutar actualizar_bd_v2.sql")
        
        conn.close()
    else:
        print(f"⚠️ No se encuentra {db_path}")
    
    print("\n✅ Verificación completada")
