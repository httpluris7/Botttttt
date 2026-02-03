"""
DIAGNÓSTICO DE TACÓGRAFO Y DISPONIBILIDAD
==========================================
Verifica que los datos de horas se están usando correctamente.

USO:
    python diagnostico_tacografo.py
"""

import sqlite3
import json
from pathlib import Path

# Configuración
DB_PATH = "logistica.db"
GPS_JSON = "api_gps_simulada.json"

class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(texto):
    print(f"\n{C.BOLD}{C.CYAN}{'='*70}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{texto}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'='*70}{C.RESET}")

# ============================================================
# 1. CARGAR DATOS
# ============================================================

print_header("1. CARGANDO DATOS")

# Cargar JSON
gps_data = {}
if Path(GPS_JSON).exists():
    with open(GPS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for v in data.get('vehiculos', []):
            gps_data[v.get('matricula', '')] = v
    print(f"{C.GREEN}✅ Cargados {len(gps_data)} vehículos del JSON{C.RESET}")
else:
    print(f"{C.RED}❌ No existe {GPS_JSON}{C.RESET}")

# Cargar conductores de DB
conductores_db = []
if Path(DB_PATH).exists():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT nombre, tractora, telefono FROM conductores_empresa WHERE tractora IS NOT NULL AND tractora != ''")
    conductores_db = cursor.fetchall()
    conn.close()
    print(f"{C.GREEN}✅ Cargados {len(conductores_db)} conductores de la DB{C.RESET}")
else:
    print(f"{C.RED}❌ No existe {DB_PATH}{C.RESET}")

# ============================================================
# 2. SIMULAR DISPONIBILIDAD (como hace movildata_api.py)
# ============================================================

print_header("2. SIMULACIÓN DE DISPONIBILIDAD")

import random

def simular_disponibilidad(estado_vehiculo):
    """Simula datos de tacógrafo según estado"""
    if estado_vehiculo == 'descanso':
        horas_hoy = 0
    elif estado_vehiculo == 'disponible':
        horas_hoy = round(random.uniform(0, 4), 1)
    elif estado_vehiculo == 'cargando':
        horas_hoy = round(random.uniform(2, 6), 1)
    else:  # en_ruta
        horas_hoy = round(random.uniform(4, 8), 1)
    
    horas_semana = round(random.uniform(20, 45), 1)
    horas_restantes_hoy = max(0, 9 - horas_hoy)
    horas_restantes_semana = max(0, 56 - horas_semana)
    
    return {
        'horas_hoy': horas_hoy,
        'horas_restantes_hoy': horas_restantes_hoy,
        'horas_semana': horas_semana,
        'horas_restantes_semana': horas_restantes_semana,
        'puede_conducir_4h': horas_restantes_hoy >= 4,
        'puede_conducir_8h': horas_restantes_hoy >= 8,
    }

print(f"\n{'CONDUCTOR':<25} {'MATRÍCULA':<12} {'ESTADO':<12} {'H.HOY':<8} {'H.REST':<8} {'PUEDE 4h':<10}")
print("-" * 85)

conductores_validos = 0
conductores_sin_horas = 0

for c in conductores_db[:20]:  # Primeros 20
    matricula = c['tractora']
    nombre = c['nombre']
    
    if matricula in gps_data:
        gps = gps_data[matricula]
        estado = gps.get('estado', 'disponible')
        disp = simular_disponibilidad(estado)
        
        puede = "✅ Sí" if disp['puede_conducir_4h'] else "❌ No"
        color = C.GREEN if disp['puede_conducir_4h'] else C.RED
        
        print(f"{nombre:<25} {matricula:<12} {estado:<12} {disp['horas_hoy']:<8.1f} {disp['horas_restantes_hoy']:<8.1f} {color}{puede}{C.RESET}")
        
        if disp['puede_conducir_4h']:
            conductores_validos += 1
        else:
            conductores_sin_horas += 1
    else:
        print(f"{nombre:<25} {matricula:<12} {C.YELLOW}SIN GPS{C.RESET}")

# ============================================================
# 3. RESUMEN
# ============================================================

print_header("3. RESUMEN DE DISPONIBILIDAD")

print(f"""
📊 ESTADÍSTICAS:

   Total conductores con tractora: {len(conductores_db)}
   Conductores con GPS simulado:   {len(gps_data)}
   
   ✅ Pueden conducir (>4h):       ~{conductores_validos}
   ❌ Sin horas suficientes:       ~{conductores_sin_horas}

📋 CRITERIOS DE ASIGNACIÓN:

   1. Estado != DESCANSO, AVERIA
   2. Horas restantes HOY >= horas viaje + 1h margen
   3. Horas restantes SEMANA >= horas viaje + 1h margen
   4. Tipo remolque correcto (si necesita frío)
   5. Ordenar por distancia al punto de carga
""")

# ============================================================
# 4. EJEMPLO DE ASIGNACIÓN
# ============================================================

print_header("4. EJEMPLO: ¿QUIÉN PUEDE HACER UN VIAJE DE 4 HORAS?")

print(f"\n🚛 Viaje de ejemplo: CALAHORRA → MADRID (320 km, ~4h)")
print(f"📋 Requisitos: 4h conducción + 1h margen = 5h mínimo\n")

candidatos = []
for c in conductores_db:
    matricula = c['tractora']
    nombre = c['nombre']
    
    if matricula in gps_data:
        gps = gps_data[matricula]
        estado = gps.get('estado', 'disponible')
        
        # Solo disponibles o cargando
        if estado in ['disponible', 'cargando']:
            disp = simular_disponibilidad(estado)
            
            # Verificar horas
            if disp['horas_restantes_hoy'] >= 5:
                candidatos.append({
                    'nombre': nombre,
                    'matricula': matricula,
                    'estado': estado,
                    'horas_rest': disp['horas_restantes_hoy'],
                    'ciudad': gps.get('ubicacion', {}).get('ciudad', '?')
                })

# Ordenar por horas restantes (más horas = mejor)
candidatos.sort(key=lambda x: -x['horas_rest'])

print(f"✅ {len(candidatos)} conductores PUEDEN hacer este viaje:\n")
print(f"{'CONDUCTOR':<25} {'MATRÍCULA':<12} {'CIUDAD':<15} {'H.REST':<8} {'ESTADO':<12}")
print("-" * 75)

for c in candidatos[:10]:
    print(f"{c['nombre']:<25} {c['matricula']:<12} {c['ciudad']:<15} {c['horas_rest']:<8.1f} {c['estado']:<12}")

if len(candidatos) > 10:
    print(f"... y {len(candidatos) - 10} más")

print(f"\n{C.GREEN}{C.BOLD}🏆 MEJOR CANDIDATO (más horas disponibles):{C.RESET}")
if candidatos:
    mejor = candidatos[0]
    print(f"   {C.GREEN}{mejor['nombre']} ({mejor['matricula']}){C.RESET}")
    print(f"   {C.GREEN}📍 En {mejor['ciudad']} con {mejor['horas_rest']:.1f}h disponibles{C.RESET}")
