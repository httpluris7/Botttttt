"""
DIAGNÓSTICO DE ASIGNACIÓN DE VIAJES v2
=======================================
Usa logistica.db (la DB correcta del bot)

USO:
    python diagnostico_asignacion.py
"""

import sqlite3
import json
import math
from pathlib import Path

# Configuración
DB_PATH = "logistica.db"
GPS_JSON = "api_gps_simulada.json"

# Colores para terminal
class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(texto):
    print(f"\n{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{texto}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")

def print_ok(texto):
    print(f"{C.GREEN}✅ {texto}{C.RESET}")

def print_warn(texto):
    print(f"{C.YELLOW}⚠️  {texto}{C.RESET}")

def print_error(texto):
    print(f"{C.RED}❌ {texto}{C.RESET}")

def print_info(texto):
    print(f"{C.BLUE}ℹ️  {texto}{C.RESET}")

def distancia_km(lat1, lon1, lat2, lon2):
    """Calcula distancia en km entre dos puntos"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# Coordenadas de lugares de carga
COORDS_CARGA = {
    "CALAHORRA": (42.305, -1.965),
    "TUDELA": (42.062, -1.607),
    "AZAGRA": (42.317, -1.883),
    "SAN ADRIAN": (42.342, -1.933),
    "ALFARO": (42.183, -1.750),
    "ARNEDO": (42.217, -2.100),
    "PERALTA": (42.333, -1.800),
    "MENDAVIA": (42.433, -2.200),
    "LODOSA": (42.433, -2.083),
    "AUTOL": (42.217, -2.000),
    "QUEL": (42.233, -2.050),
    "PAMPLONA": (42.817, -1.650),
    "LOGROÑO": (42.467, -2.450),
}

# ============================================================
# 1. VERIFICAR ARCHIVOS
# ============================================================

print_header("1. VERIFICANDO ARCHIVOS")

if Path(DB_PATH).exists():
    size = Path(DB_PATH).stat().st_size
    print_ok(f"{DB_PATH} ({size:,} bytes)")
else:
    print_error(f"{DB_PATH} NO ENCONTRADO")

if Path(GPS_JSON).exists():
    print_ok(f"{GPS_JSON}")
else:
    print_error(f"{GPS_JSON} NO ENCONTRADO")
    print_warn("Ejecuta: python sincronizar_gps_simulado.py")

# ============================================================
# 2. ANALIZAR BASE DE DATOS
# ============================================================

print_header("2. ANALIZANDO BASE DE DATOS")

n_con_tractora = 0

try:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Conductores
    cursor.execute("SELECT COUNT(*) as n FROM conductores_empresa")
    n_conductores = cursor.fetchone()['n']
    print_info(f"Conductores totales: {n_conductores}")
    
    # Conductores con tractora
    cursor.execute("SELECT COUNT(*) as n FROM conductores_empresa WHERE tractora IS NOT NULL AND tractora != ''")
    n_con_tractora = cursor.fetchone()['n']
    print_info(f"Conductores con tractora: {n_con_tractora}")
    
    # Viajes totales
    cursor.execute("SELECT COUNT(*) as n FROM viajes_empresa")
    n_viajes = cursor.fetchone()['n']
    print_info(f"Viajes totales: {n_viajes}")
    
    # Viajes pendientes
    cursor.execute("""
        SELECT COUNT(*) as n FROM viajes_empresa 
        WHERE (conductor_asignado IS NULL OR conductor_asignado = '')
    """)
    n_pendientes = cursor.fetchone()['n']
    print_info(f"Viajes PENDIENTES: {n_pendientes}")
    
    # Viajes asignados
    n_asignados = n_viajes - n_pendientes
    print_info(f"Viajes ASIGNADOS: {n_asignados}")
    
    conn.close()
except Exception as e:
    print_error(f"Error con DB: {e}")

# ============================================================
# 3. ANALIZAR GPS SIMULADO
# ============================================================

print_header("3. ANALIZANDO GPS SIMULADO")

gps_por_matricula = {}

try:
    if Path(GPS_JSON).exists():
        with open(GPS_JSON, "r", encoding="utf-8") as f:
            gps_data = json.load(f)
        
        vehiculos = gps_data.get("vehiculos", [])
        print_info(f"Vehículos en JSON: {len(vehiculos)}")
        
        # Indexar por matrícula
        for v in vehiculos:
            gps_por_matricula[v.get("matricula", "")] = v
        
        # Contar por estado
        estados = {}
        for v in vehiculos:
            estado = v.get("estado", "desconocido")
            estados[estado] = estados.get(estado, 0) + 1
        
        print_info("Estados:")
        for estado, count in estados.items():
            emoji = "🟢" if estado == "disponible" else "🟡" if estado == "cargando" else "🔵"
            print(f"      {emoji} {estado}: {count}")
    else:
        print_error("api_gps_simulada.json no existe")
except Exception as e:
    print_error(f"Error leyendo JSON: {e}")

# ============================================================
# 4. CRUZAR DATOS: CONDUCTORES DB vs GPS
# ============================================================

print_header("4. CRUZANDO CONDUCTORES DB vs GPS")

coinciden = 0

try:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT nombre, tractora, telefono 
        FROM conductores_empresa 
        WHERE tractora IS NOT NULL AND tractora != ''
    """)
    conductores_db = cursor.fetchall()
    
    no_coinciden = []
    
    for c in conductores_db:
        matricula = c['tractora']
        if matricula in gps_por_matricula:
            coinciden += 1
        else:
            no_coinciden.append((c['nombre'], matricula))
    
    if coinciden > 0:
        print_ok(f"{coinciden} conductores tienen GPS simulado")
    
    if no_coinciden:
        print_warn(f"{len(no_coinciden)} conductores SIN GPS:")
        for nombre, mat in no_coinciden[:5]:
            print(f"      - {nombre} ({mat})")
        if len(no_coinciden) > 5:
            print(f"      ... y {len(no_coinciden) - 5} más")
        print_warn("Ejecuta: python sincronizar_gps_simulado.py")
    
    conn.close()
except Exception as e:
    print_error(f"Error cruzando datos: {e}")

# ============================================================
# 5. SIMULAR ASIGNACIÓN DE UN VIAJE
# ============================================================

print_header("5. SIMULACIÓN DE ASIGNACIÓN")

try:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Obtener un viaje pendiente
    cursor.execute("""
        SELECT * FROM viajes_empresa 
        WHERE (conductor_asignado IS NULL OR conductor_asignado = '')
        AND lugar_carga IS NOT NULL
        LIMIT 1
    """)
    viaje = cursor.fetchone()
    
    if viaje:
        print_info(f"Viaje pendiente de ejemplo:")
        print(f"      Cliente: {viaje['cliente']}")
        print(f"      Ruta: {viaje['lugar_carga']} → {viaje['lugar_entrega']}")
        print(f"      KM: {viaje['km']}")
        print(f"      Precio: {viaje['precio']}€")
        print(f"      Mercancía: {viaje['mercancia']}")
        
        lugar_carga = (viaje['lugar_carga'] or "").upper()
        
        # Obtener coordenadas del lugar de carga
        lat_carga, lon_carga = COORDS_CARGA.get(lugar_carga, (42.3, -1.9))
        print_info(f"Coordenadas carga: {lat_carga}, {lon_carga}")
        
        # Buscar conductores con GPS disponible
        cursor.execute("""
            SELECT nombre, tractora, telefono 
            FROM conductores_empresa 
            WHERE tractora IS NOT NULL AND tractora != ''
        """)
        conductores = cursor.fetchall()
        
        candidatos = []
        for c in conductores:
            matricula = c['tractora']
            if matricula in gps_por_matricula:
                gps = gps_por_matricula[matricula]
                if gps.get('estado') == 'disponible':
                    ubi = gps.get('ubicacion', {})
                    lat = ubi.get('lat', 0)
                    lon = ubi.get('lon', 0)
                    dist = distancia_km(lat_carga, lon_carga, lat, lon)
                    
                    candidatos.append({
                        'nombre': c['nombre'],
                        'matricula': matricula,
                        'ciudad': ubi.get('ciudad', '?'),
                        'distancia': round(dist, 1),
                        'estado': gps.get('estado')
                    })
        
        # Ordenar por distancia
        candidatos.sort(key=lambda x: x['distancia'])
        
        if candidatos:
            print_ok(f"\n{len(candidatos)} conductores DISPONIBLES con GPS:")
            print(f"\n{'CONDUCTOR':<25} {'MATRÍCULA':<12} {'CIUDAD':<15} {'DISTANCIA':<10}")
            print("-" * 65)
            for c in candidatos[:10]:
                print(f"{c['nombre']:<25} {c['matricula']:<12} {c['ciudad']:<15} {c['distancia']:.1f} km")
            
            mejor = candidatos[0]
            print(f"\n{C.GREEN}{C.BOLD}🏆 MEJOR CANDIDATO:{C.RESET}")
            print(f"   {C.GREEN}{mejor['nombre']} ({mejor['matricula']}){C.RESET}")
            print(f"   {C.GREEN}📍 En {mejor['ciudad']} a {mejor['distancia']} km del punto de carga{C.RESET}")
        else:
            print_warn("No hay conductores DISPONIBLES con GPS")
            print_info("Puede que todos estén en_ruta o cargando")
    else:
        print_info("No hay viajes pendientes")
    
    conn.close()
except Exception as e:
    print_error(f"Error en simulación: {e}")
    import traceback
    traceback.print_exc()

# ============================================================
# 6. VERIFICAR LÓGICA DE FILTRADO
# ============================================================

print_header("6. VERIFICACIÓN DE CRITERIOS DE ASIGNACIÓN")

print("""
La lógica de asignación verifica:

1. ✅ ESTADO del conductor:
   - Solo asigna a: DISPONIBLE, EN_RUTA
   - NO asigna a: DESCANSO, AVERIA, OTROS_TRABAJOS

2. ✅ HORAS DISPONIBLES (tacógrafo):
   - Horas restantes hoy >= horas viaje + 1h margen
   - Horas restantes semana >= horas viaje + 1h margen

3. ✅ TIPO DE REMOLQUE:
   - Si mercancía es REFRIGERADO/CONGELADO → necesita FRIGORIFICO

4. ✅ DISTANCIA al punto de carga:
   - Ordena candidatos por cercanía
   - Asigna al más cercano

5. ✅ EVITA DOBLE ASIGNACIÓN:
   - Un conductor solo recibe 1 viaje por ronda
""")

# ============================================================
# 7. RESUMEN Y PRÓXIMOS PASOS
# ============================================================

print_header("7. PRÓXIMOS PASOS")

if not gps_por_matricula:
    print(f"""
{C.YELLOW}⚠️  El GPS simulado está vacío o no coincide con la DB{C.RESET}

SOLUCIÓN:
1. Ejecuta: {C.CYAN}python sincronizar_gps_simulado.py{C.RESET}
2. Reinicia el bot
3. En Telegram pulsa: 🤖 Asignar viajes
""")
elif coinciden < n_con_tractora:
    print(f"""
{C.YELLOW}⚠️  Solo {coinciden}/{n_con_tractora} conductores tienen GPS{C.RESET}

SOLUCIÓN:
1. Ejecuta: {C.CYAN}python sincronizar_gps_simulado.py{C.RESET}
2. Reinicia el bot
""")
else:
    print(f"""
{C.GREEN}✅ Sistema configurado correctamente{C.RESET}

Para probar la asignación:
1. En Telegram pulsa: 🤖 Asignar viajes
2. Observa qué viajes se asignan y a quién
3. Verifica que asigne al conductor más cercano
""")
