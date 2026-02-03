"""
INSTALADOR DE MEJORAS v2.0
==========================
Ejecuta este script para instalar todas las mejoras automáticamente.

Uso:
    python instalar_mejoras.py

Hace:
1. Crea las nuevas tablas en la BD
2. Crea directorios necesarios
3. Verifica dependencias
4. Hace un backup de seguridad
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path


def print_header():
    print("="*60)
    print("🚀 INSTALADOR DE MEJORAS BOT TRANSPORTE v2.0")
    print("="*60)
    print()


def backup_bd(db_path: str) -> bool:
    """Hace backup de la BD antes de modificarla."""
    if not os.path.exists(db_path):
        print(f"⚠️ Base de datos no encontrada: {db_path}")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    
    try:
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup creado: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Error creando backup: {e}")
        return False


def crear_tablas(db_path: str) -> bool:
    """Crea las nuevas tablas en la BD."""
    sql_script = """
-- TABLA: Rutas frecuentes
CREATE TABLE IF NOT EXISTS rutas_frecuentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origen TEXT NOT NULL,
    destino TEXT NOT NULL,
    km_estimados INTEGER DEFAULT 0,
    tiempo_estimado TEXT DEFAULT '',
    veces_realizada INTEGER DEFAULT 1,
    ultimo_viaje DATE,
    km_total_acumulado INTEGER DEFAULT 0,
    consumo_promedio REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(origen, destino)
);

-- TABLA: Gastos de viajes
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    viaje_id INTEGER,
    conductor TEXT,
    categoria TEXT NOT NULL,
    importe REAL NOT NULL,
    descripcion TEXT,
    fecha DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- TABLA: Historial de backups
CREATE TABLE IF NOT EXISTS backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archivo TEXT,
    tamaño_kb INTEGER,
    destino TEXT,
    estado TEXT DEFAULT 'OK'
);

-- TABLA: Logs de errores críticos
CREATE TABLE IF NOT EXISTS logs_criticos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modulo TEXT,
    nivel TEXT,
    mensaje TEXT,
    notificado INTEGER DEFAULT 0
);

-- TABLA: Informes generados
CREATE TABLE IF NOT EXISTS informes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT,
    fecha_inicio DATE,
    fecha_fin DATE,
    datos_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ÍNDICES
CREATE INDEX IF NOT EXISTS idx_rutas_origen ON rutas_frecuentes(origen);
CREATE INDEX IF NOT EXISTS idx_rutas_destino ON rutas_frecuentes(destino);
CREATE INDEX IF NOT EXISTS idx_gastos_viaje ON gastos(viaje_id);
CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);

-- DATOS INICIALES
INSERT OR IGNORE INTO rutas_frecuentes (origen, destino, km_estimados, tiempo_estimado, veces_realizada) VALUES
('AZAGRA', 'MADRID', 320, '3h 30min', 0),
('AZAGRA', 'BARCELONA', 350, '3h 45min', 0),
('AZAGRA', 'ZARAGOZA', 120, '1h 20min', 0),
('MELIDA', 'MADRID', 330, '3h 40min', 0),
('MELIDA', 'BARCELONA', 340, '3h 40min', 0),
('MELIDA', 'BADAJOZ', 580, '6h 00min', 0),
('TUDELA', 'MADRID', 310, '3h 20min', 0),
('PAMPLONA', 'MADRID', 400, '4h 15min', 0),
('PERALTA', 'MERCAMADRID', 330, '3h 35min', 0),
('CALAHORRA', 'MADRID', 290, '3h 10min', 0),
('LOGROÑO', 'MADRID', 330, '3h 30min', 0);
"""
    
    try:
        conn = sqlite3.connect(db_path)
        conn.executescript(sql_script)
        conn.commit()
        conn.close()
        print("✅ Tablas creadas correctamente")
        return True
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")
        return False


def crear_directorios() -> bool:
    """Crea los directorios necesarios."""
    directorios = ['logs', 'backups']
    
    for d in directorios:
        try:
            Path(d).mkdir(parents=True, exist_ok=True)
            print(f"✅ Directorio '{d}/' creado/verificado")
        except Exception as e:
            print(f"❌ Error creando directorio {d}: {e}")
            return False
    
    return True


def verificar_dependencias() -> bool:
    """Verifica que las dependencias estén instaladas."""
    dependencias = [
        ('python-telegram-bot', 'telegram'),
        ('python-dotenv', 'dotenv'),
        ('requests', 'requests'),
    ]
    
    faltantes = []
    
    for nombre, modulo in dependencias:
        try:
            __import__(modulo)
            print(f"✅ {nombre} instalado")
        except ImportError:
            faltantes.append(nombre)
            print(f"❌ {nombre} NO instalado")
    
    if faltantes:
        print(f"\n⚠️ Instala las dependencias faltantes:")
        print(f"   pip install {' '.join(faltantes)}")
        return False
    
    return True


def verificar_archivos() -> bool:
    """Verifica que los archivos nuevos estén presentes."""
    archivos = [
        'informes.py',
        'logging_config.py',
        'backup_automatico.py'
    ]
    
    todos_presentes = True
    
    for archivo in archivos:
        if os.path.exists(archivo):
            print(f"✅ {archivo} encontrado")
        else:
            print(f"⚠️ {archivo} NO encontrado - cópialo al directorio del bot")
            todos_presentes = False
    
    return todos_presentes


def actualizar_env() -> bool:
    """Sugiere variables para añadir al .env"""
    nuevas_vars = """
# Añadir al .env si no existen:

# Backups
BACKUP_DIR=backups
MAX_BACKUPS=7

# Logs
LOG_DIR=logs
LOG_LEVEL=INFO

# Alertas email (opcional)
ALERT_EMAIL_ENABLED=false
"""
    
    print("\n📝 Variables sugeridas para .env:")
    print(nuevas_vars)
    return True


def main():
    print_header()
    
    # Buscar base de datos
    db_path = os.getenv("DB_PATH", "viajes.db")
    
    if not os.path.exists(db_path):
        # Buscar en ubicaciones comunes
        posibles = ['viajes.db', '../viajes.db', 'data/viajes.db']
        for p in posibles:
            if os.path.exists(p):
                db_path = p
                break
    
    print(f"📁 Base de datos: {db_path}\n")
    
    # 1. Backup
    print("📦 PASO 1: Backup de seguridad")
    print("-" * 40)
    if os.path.exists(db_path):
        backup_bd(db_path)
    else:
        print("⚠️ No se encontró la BD, se creará nueva")
    
    # 2. Crear tablas
    print("\n📊 PASO 2: Crear nuevas tablas")
    print("-" * 40)
    crear_tablas(db_path)
    
    # 3. Directorios
    print("\n📁 PASO 3: Crear directorios")
    print("-" * 40)
    crear_directorios()
    
    # 4. Dependencias
    print("\n📦 PASO 4: Verificar dependencias")
    print("-" * 40)
    verificar_dependencias()
    
    # 5. Archivos
    print("\n📄 PASO 5: Verificar archivos nuevos")
    print("-" * 40)
    verificar_archivos()
    
    # 6. Variables de entorno
    print("\n⚙️ PASO 6: Variables de entorno")
    print("-" * 40)
    actualizar_env()
    
    # Resumen
    print("\n" + "="*60)
    print("✅ INSTALACIÓN COMPLETADA")
    print("="*60)
    print("""
PRÓXIMOS PASOS:

1. Copia los archivos nuevos al directorio del bot:
   - informes.py
   - logging_config.py
   - backup_automatico.py

2. Actualiza bot_transporte.py siguiendo GUIA_INTEGRACION.py

3. Actualiza teclados.py con los nuevos botones

4. Actualiza .env con las nuevas variables

5. Reinicia el bot

📖 Ver GUIA_INTEGRACION.py para instrucciones detalladas
""")


if __name__ == "__main__":
    main()
