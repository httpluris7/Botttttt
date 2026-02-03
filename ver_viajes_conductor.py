"""
VER VIAJES POR CONDUCTOR
=========================
Muestra los viajes asignados a un conductor.
Solo datos objetivos, sin juicios de valor.

USO:
    python ver_viajes_conductor.py
    python ver_viajes_conductor.py "ALEJANDRO DOMINGUEZ"
    python ver_viajes_conductor.py --todos
"""

import sqlite3
import sys
import math

# Configuración
DB_PATH = "logistica.db"

# Coordenadas para calcular distancias
COORDENADAS = {
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
    "HUESCA": (42.1401, -0.4089),
    "TERUEL": (40.3456, -1.1065),
    "GUADALAJARA": (40.6337, -3.1667),
    "TOLEDO": (39.8628, -4.0273),
    "CIUDAD REAL": (38.9848, -3.9274),
    "ALBACETE": (38.9943, -1.8585),
    "SALAMANCA": (40.9701, -5.6635),
    "SEGOVIA": (40.9429, -4.1088),
    "SORIA": (41.7636, -2.4649),
    "PALENCIA": (42.0096, -4.5288),
    "ZAMORA": (41.5034, -5.7467),
    "CACERES": (39.4753, -6.3724),
    "HUELVA": (37.2571, -6.9497),
    "CADIZ": (36.5271, -6.2886),
    "JAEN": (37.7796, -3.7849),
    "ALMERIA": (36.8340, -2.4637),
    "LODOSA": (42.4333, -2.0833),
    "MENDAVIA": (42.4333, -2.2000),
    "PERALTA": (42.3333, -1.8000),
    "AUTOL": (42.2167, -2.0000),
    "QUEL": (42.2333, -2.0500),
}

def calcular_distancia(lat1, lon1, lat2, lon2):
    """Calcula distancia en km"""
    if not all([lat1, lon1, lat2, lon2]):
        return None
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def obtener_coords(lugar):
    """Obtiene coordenadas de un lugar"""
    if not lugar:
        return None, None
    lugar_upper = lugar.upper().strip()
    
    if lugar_upper in COORDENADAS:
        return COORDENADAS[lugar_upper]
    
    for nombre, coords in COORDENADAS.items():
        if nombre in lugar_upper or lugar_upper in nombre:
            return coords
    
    return None, None

def mostrar_viajes_conductor(nombre_conductor):
    """Muestra los viajes de un conductor"""
    
    print(f"\n{'='*60}")
    print(f"📋 VIAJES DE: {nombre_conductor}")
    print(f"{'='*60}\n")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, cliente, lugar_carga, lugar_entrega, mercancia, km, precio, estado
        FROM viajes_empresa 
        WHERE conductor_asignado = ?
        ORDER BY id
    """, (nombre_conductor,))
    
    viajes = cursor.fetchall()
    conn.close()
    
    if not viajes:
        print("❌ No hay viajes asignados a este conductor")
        return
    
    print(f"Total viajes: {len(viajes)}\n")
    
    ultima_descarga = None
    km_viajes = 0
    km_desplazamientos = 0
    
    for i, v in enumerate(viajes, 1):
        lugar_carga = v['lugar_carga'] or '?'
        lugar_entrega = v['lugar_entrega'] or '?'
        km = v['km'] or 0
        cliente = v['cliente'] or '?'
        mercancia = v['mercancia'] or ''
        
        km_viajes += km
        
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"VIAJE {i} | {cliente}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # Desplazamiento desde viaje anterior
        if ultima_descarga:
            lat1, lon1 = obtener_coords(ultima_descarga)
            lat2, lon2 = obtener_coords(lugar_carga)
            
            if lat1 and lat2:
                dist = calcular_distancia(lat1, lon1, lat2, lon2)
                km_desplazamientos += dist
                print(f"🚛 Desplazamiento: {ultima_descarga} → {lugar_carga} ({dist:.0f} km)")
        
        print(f"📥 Carga:    {lugar_carga}")
        print(f"📤 Descarga: {lugar_entrega}")
        print(f"📏 Viaje:    {km} km")
        
        if mercancia:
            print(f"📦 Mercancía: {mercancia}")
        
        print()
        ultima_descarga = lugar_entrega
    
    # Resumen
    print(f"{'='*60}")
    print(f"📊 RESUMEN")
    print(f"{'='*60}")
    print(f"   Viajes:              {len(viajes)}")
    print(f"   Km en viajes:        {km_viajes} km")
    print(f"   Km desplazamientos:  {km_desplazamientos:.0f} km")
    print(f"   ─────────────────────────────")
    print(f"   TOTAL:               {km_viajes + km_desplazamientos:.0f} km")
    
    # Ruta visual
    print(f"\n🗺️ RUTA:")
    ruta = []
    for v in viajes:
        if v['lugar_carga'] and v['lugar_carga'] not in ruta:
            ruta.append(v['lugar_carga'])
        if v['lugar_entrega']:
            ruta.append(v['lugar_entrega'])
    
    print(f"   {' → '.join(ruta)}")
    print()


def listar_conductores_con_viajes():
    """Lista todos los conductores que tienen viajes asignados"""
    
    print(f"\n{'='*60}")
    print(f"👥 CONDUCTORES CON VIAJES ASIGNADOS")
    print(f"{'='*60}\n")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT conductor_asignado, COUNT(*) as num_viajes, SUM(km) as km_total
        FROM viajes_empresa 
        WHERE conductor_asignado IS NOT NULL AND conductor_asignado != ''
        GROUP BY conductor_asignado
        ORDER BY num_viajes DESC
    """)
    
    conductores = cursor.fetchall()
    conn.close()
    
    if not conductores:
        print("❌ No hay viajes asignados")
        return
    
    print(f"{'CONDUCTOR':<30} {'VIAJES':<10} {'KM':<10}")
    print("-" * 50)
    
    for c in conductores:
        nombre = c[0]
        num = c[1]
        km = c[2] or 0
        print(f"{nombre:<30} {num:<10} {km:<10}")
    
    print(f"\n💡 Uso: python ver_viajes_conductor.py \"NOMBRE\"")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--todos" or sys.argv[1] == "-t":
            listar_conductores_con_viajes()
        else:
            nombre = " ".join(sys.argv[1:])
            mostrar_viajes_conductor(nombre)
    else:
        listar_conductores_con_viajes()
        
        print(f"\nEscribe nombre del conductor (o ENTER para salir):")
        nombre = input("> ").strip()
        
        if nombre:
            mostrar_viajes_conductor(nombre)
