"""
GENERADOR DE GPS SIMULADO - SINCRONIZADO CON DB
=================================================
Lee los conductores REALES de logistica.db y genera
api_gps_simulada.json con sus MISMAS matrículas.

USO:
    python sincronizar_gps_simulado.py
"""

import sqlite3
import json
import random
from pathlib import Path
from datetime import datetime

# Configuración
DB_PATH = "logistica.db"
OUTPUT_JSON = "api_gps_simulada.json"

# Ubicaciones base ZONA NORTE con coordenadas
UBICACIONES = {
    "AZAGRA": {"lat": 42.3167, "lon": -1.8833, "provincia": "Navarra"},
    "TUDELA": {"lat": 42.0667, "lon": -1.6000, "provincia": "Navarra"},
    "CALAHORRA": {"lat": 42.3000, "lon": -1.9667, "provincia": "La Rioja"},
    "SAN ADRIAN": {"lat": 42.3333, "lon": -1.9333, "provincia": "Navarra"},
    "LOGROÑO": {"lat": 42.4667, "lon": -2.4500, "provincia": "La Rioja"},
    "PAMPLONA": {"lat": 42.8167, "lon": -1.6500, "provincia": "Navarra"},
    "ALFARO": {"lat": 42.1833, "lon": -1.7500, "provincia": "La Rioja"},
    "ARNEDO": {"lat": 42.2167, "lon": -2.1000, "provincia": "La Rioja"},
    "ESTELLA": {"lat": 42.6667, "lon": -2.0333, "provincia": "Navarra"},
    "TAFALLA": {"lat": 42.5167, "lon": -1.6667, "provincia": "Navarra"},
    "ZARAGOZA": {"lat": 41.6488, "lon": -0.8891, "provincia": "Zaragoza"},
    "PERALTA": {"lat": 42.3333, "lon": -1.8000, "provincia": "Navarra"},
    "MENDAVIA": {"lat": 42.4333, "lon": -2.2000, "provincia": "Navarra"},
    "LODOSA": {"lat": 42.4333, "lon": -2.0833, "provincia": "Navarra"},
}

def main():
    print("=" * 60)
    print("🔄 SINCRONIZANDO GPS SIMULADO CON DB REAL")
    print("=" * 60)
    
    # 1. Verificar que existe la DB
    if not Path(DB_PATH).exists():
        print(f"❌ No se encuentra {DB_PATH}")
        return
    
    # 2. Leer conductores de la DB
    print(f"\n📖 Leyendo conductores de {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT nombre, tractora, telefono, remolque 
        FROM conductores_empresa 
        WHERE tractora IS NOT NULL AND tractora != ''
    """)
    
    conductores = cursor.fetchall()
    conn.close()
    
    print(f"   ✅ {len(conductores)} conductores con tractora encontrados")
    
    if not conductores:
        print("❌ No hay conductores con tractora en la DB")
        return
    
    # 3. Generar datos GPS para cada conductor
    print(f"\n🛰️ Generando datos GPS simulados...")
    
    vehiculos = []
    ubicaciones_list = list(UBICACIONES.keys())
    
    for c in conductores:
        nombre = c['nombre'] or "DESCONOCIDO"
        matricula = c['tractora'] or ""
        telefono = c['telefono'] or ""
        remolque = c['remolque'] or ""
        
        if not matricula:
            continue
        
        # Ubicación aleatoria
        ubicacion_nombre = random.choice(ubicaciones_list)
        ubicacion = UBICACIONES[ubicacion_nombre]
        
        # Variación en coordenadas
        lat = ubicacion["lat"] + random.uniform(-0.03, 0.03)
        lon = ubicacion["lon"] + random.uniform(-0.03, 0.03)
        
        # Estado: 60% disponible, 25% en_ruta, 15% cargando
        rand = random.random()
        if rand < 0.60:
            estado = "disponible"
            velocidad = 0
        elif rand < 0.85:
            estado = "en_ruta"
            velocidad = random.randint(60, 90)
        else:
            estado = "cargando"
            velocidad = 0
        
        vehiculo = {
            "matricula": matricula,
            "remolque": remolque,
            "conductor": nombre,
            "telefono": telefono,
            "ubicacion": {
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "ciudad": ubicacion_nombre,
                "provincia": ubicacion["provincia"],
                "direccion": f"Polígono Industrial, {ubicacion_nombre}"
            },
            "estado": estado,
            "velocidad": velocidad,
            "temperatura": round(random.uniform(-22, 5), 1),
            "combustible_pct": random.randint(30, 100)
        }
        vehiculos.append(vehiculo)
    
    # 4. Guardar JSON
    api_data = {
        "timestamp": datetime.now().isoformat(),
        "total": len(vehiculos),
        "vehiculos": vehiculos
    }
    
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(api_data, f, indent=2, ensure_ascii=False)
    
    print(f"   ✅ {len(vehiculos)} vehículos guardados en {OUTPUT_JSON}")
    
    # 5. Mostrar resumen
    print(f"\n📊 RESUMEN:")
    print(f"   - Vehículos totales: {len(vehiculos)}")
    
    estados = {}
    for v in vehiculos:
        e = v['estado']
        estados[e] = estados.get(e, 0) + 1
    
    for estado, count in estados.items():
        print(f"   - {estado}: {count}")
    
    print(f"\n📋 PRIMEROS 10 VEHÍCULOS:")
    print(f"{'MATRÍCULA':<12} {'CONDUCTOR':<25} {'CIUDAD':<15} {'ESTADO':<12}")
    print("-" * 65)
    for v in vehiculos[:10]:
        print(f"{v['matricula']:<12} {v['conductor']:<25} {v['ubicacion']['ciudad']:<15} {v['estado']:<12}")
    
    print(f"\n✅ COMPLETADO")
    print(f"\n🔄 Ahora reinicia el bot para que cargue el nuevo JSON")

if __name__ == "__main__":
    main()
