"""
INFORMES Y ESTADÍSTICAS v1.0
============================
Generador de informes automáticos para el bot de transporte.

Informes disponibles:
- Resumen semanal
- Resumen mensual
- Estadísticas por conductor
- Análisis de rentabilidad por ruta
- Top rutas frecuentes

Uso:
    from informes import InformesBot
    
    informes = InformesBot("viajes.db")
    
    # Generar informe semanal
    texto = informes.informe_semanal()
    
    # Análisis de rentabilidad
    texto = informes.analisis_rentabilidad()
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class EstadisticasConductor:
    """Estadísticas de un conductor."""
    nombre: str
    viajes: int
    km_totales: int
    horas_estimadas: float
    ciudades_visitadas: List[str]


@dataclass
class EstadisticasRuta:
    """Estadísticas de una ruta."""
    origen: str
    destino: str
    veces_realizada: int
    km_promedio: int
    tiempo_promedio: str
    ultimo_viaje: str


class InformesBot:
    """Generador de informes para el bot de transporte."""
    
    # Consumo medio diesel camión (L/100km)
    CONSUMO_MEDIO = 33.0
    
    # Precio medio diesel (€/L) - actualizar según mercado
    PRECIO_DIESEL = 1.45
    
    def __init__(self, db_path: str = "viajes.db"):
        """Inicializa el generador de informes."""
        self.db_path = db_path
    
    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene conexión a la base de datos."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # ============================================================
    # INFORME SEMANAL
    # ============================================================
    
    def informe_semanal(self, fecha_inicio: datetime = None) -> str:
        """
        Genera el informe semanal de actividad.
        
        Args:
            fecha_inicio: Fecha de inicio de la semana (default: hace 7 días)
        
        Returns:
            Texto formateado del informe
        """
        if not fecha_inicio:
            fecha_inicio = datetime.now() - timedelta(days=7)
        
        fecha_fin = fecha_inicio + timedelta(days=7)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Total viajes completados
            cursor.execute("""
                SELECT COUNT(*) as total,
                       SUM(COALESCE(km, 0)) as km_totales
                FROM viajes 
                WHERE fecha_carga >= ? AND fecha_carga <= ?
                AND estado IN ('COMPLETADO', 'ENTREGADO', 'ASIGNADO')
            """, (fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d')))
            
            row = cursor.fetchone()
            total_viajes = row['total'] or 0
            km_totales = row['km_totales'] or 0
            
            # Consumo y coste estimado
            consumo_litros = (km_totales * self.CONSUMO_MEDIO) / 100
            coste_combustible = consumo_litros * self.PRECIO_DIESEL
            
            # Top conductores
            cursor.execute("""
                SELECT conductor, 
                       COUNT(*) as viajes,
                       SUM(COALESCE(km, 0)) as km
                FROM viajes 
                WHERE fecha_carga >= ? AND fecha_carga <= ?
                AND conductor IS NOT NULL AND conductor != ''
                GROUP BY conductor
                ORDER BY viajes DESC
                LIMIT 5
            """, (fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d')))
            
            top_conductores = cursor.fetchall()
            
            # Rutas más frecuentes
            cursor.execute("""
                SELECT lugar_carga as origen, lugar_descarga as destino,
                       COUNT(*) as veces
                FROM viajes 
                WHERE fecha_carga >= ? AND fecha_carga <= ?
                GROUP BY lugar_carga, lugar_descarga
                ORDER BY veces DESC
                LIMIT 5
            """, (fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d')))
            
            top_rutas = cursor.fetchall()
            
            # Viajes por tipo de mercancía
            cursor.execute("""
                SELECT tipo_viaje,
                       COUNT(*) as total
                FROM viajes 
                WHERE fecha_carga >= ? AND fecha_carga <= ?
                GROUP BY tipo_viaje
            """, (fecha_inicio.strftime('%Y-%m-%d'), fecha_fin.strftime('%Y-%m-%d')))
            
            por_tipo = cursor.fetchall()
            
            conn.close()
            
            # Construir informe
            informe = f"""
📊 RESUMEN SEMANAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 {fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}

🚛 Viajes completados: {total_viajes}
📏 Kilómetros totales: {km_totales:,} km
⛽ Consumo estimado: {consumo_litros:,.0f} L
💰 Coste combustible: ~{coste_combustible:,.0f}€

🏆 TOP CONDUCTORES:
"""
            
            for i, c in enumerate(top_conductores, 1):
                informe += f"   {i}. {c['conductor']} - {c['viajes']} viajes, {c['km']:,} km\n"
            
            if not top_conductores:
                informe += "   (Sin datos)\n"
            
            informe += "\n🗺️ RUTAS MÁS FRECUENTES:\n"
            
            for i, r in enumerate(top_rutas, 1):
                informe += f"   {i}. {r['origen']} → {r['destino']} ({r['veces']}x)\n"
            
            if not top_rutas:
                informe += "   (Sin datos)\n"
            
            informe += "\n📦 POR TIPO DE MERCANCÍA:\n"
            
            emojis_tipo = {
                'CONGELADO': '🥶',
                'REFRIGERADO': '❄️',
                'SECO': '📦',
                'MIXTO': '🔄'
            }
            
            for t in por_tipo:
                emoji = emojis_tipo.get(t['tipo_viaje'], '📦')
                informe += f"   {emoji} {t['tipo_viaje']}: {t['total']} viajes\n"
            
            # Guardar informe en BD
            self._guardar_informe("SEMANAL", fecha_inicio, fecha_fin, {
                'viajes': total_viajes,
                'km': km_totales,
                'consumo': consumo_litros,
                'coste': coste_combustible
            })
            
            return informe.strip()
            
        except Exception as e:
            logger.error(f"Error generando informe semanal: {e}")
            return "❌ Error generando informe semanal"
    
    # ============================================================
    # ANÁLISIS DE RENTABILIDAD
    # ============================================================
    
    def analisis_rentabilidad(self, dias: int = 30) -> str:
        """
        Analiza la rentabilidad por ruta.
        
        Args:
            dias: Número de días a analizar
        
        Returns:
            Texto formateado del análisis
        """
        fecha_inicio = datetime.now() - timedelta(days=dias)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Rutas con más viajes y sus km
            cursor.execute("""
                SELECT 
                    lugar_carga as origen,
                    lugar_descarga as destino,
                    COUNT(*) as frecuencia,
                    AVG(COALESCE(km, 0)) as km_promedio,
                    SUM(COALESCE(km, 0)) as km_totales
                FROM viajes 
                WHERE fecha_carga >= ?
                AND km > 0
                GROUP BY lugar_carga, lugar_descarga
                HAVING COUNT(*) >= 2
                ORDER BY frecuencia DESC, km_totales DESC
                LIMIT 10
            """, (fecha_inicio.strftime('%Y-%m-%d'),))
            
            rutas = cursor.fetchall()
            
            conn.close()
            
            if not rutas:
                return "📈 No hay suficientes datos para análisis de rentabilidad"
            
            informe = f"""
📈 ANÁLISIS DE RUTAS (últimos {dias} días)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🗺️ RUTAS MÁS FRECUENTES:

"""
            
            for i, r in enumerate(rutas, 1):
                km_prom = r['km_promedio'] or 0
                frecuencia = r['frecuencia']
                km_totales = r['km_totales'] or 0
                
                # Calcular coste estimado por viaje
                coste_viaje = (km_prom * self.CONSUMO_MEDIO / 100) * self.PRECIO_DIESEL
                
                # Calcular €/km (asumiendo tarifa media de 1.5€/km)
                tarifa_estimada = 1.5
                ingresos_viaje = km_prom * tarifa_estimada
                margen = ingresos_viaje - coste_viaje
                
                informe += f"""
{i}. {r['origen']} → {r['destino']}
   📊 Frecuencia: {frecuencia}/mes
   📏 Km promedio: {km_prom:.0f} km
   ⛽ Coste fuel: ~{coste_viaje:.0f}€/viaje
   💰 Margen est.: ~{margen:.0f}€/viaje
"""
            
            informe += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 RECOMENDACIONES:

• Priorizar rutas con mayor frecuencia
• Optimizar cargas de retorno
• Revisar rutas con bajo margen
"""
            
            return informe.strip()
            
        except Exception as e:
            logger.error(f"Error en análisis rentabilidad: {e}")
            return "❌ Error en análisis de rentabilidad"
    
    # ============================================================
    # ESTADÍSTICAS POR CONDUCTOR
    # ============================================================
    
    def estadisticas_conductor(self, conductor: str, dias: int = 30) -> str:
        """
        Genera estadísticas detalladas de un conductor.
        
        Args:
            conductor: Nombre del conductor
            dias: Período a analizar
        
        Returns:
            Texto formateado
        """
        fecha_inicio = datetime.now() - timedelta(days=dias)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Estadísticas generales
            cursor.execute("""
                SELECT 
                    COUNT(*) as viajes,
                    SUM(COALESCE(km, 0)) as km_totales,
                    AVG(COALESCE(km, 0)) as km_promedio,
                    COUNT(DISTINCT lugar_descarga) as destinos
                FROM viajes 
                WHERE conductor LIKE ?
                AND fecha_carga >= ?
            """, (f"%{conductor}%", fecha_inicio.strftime('%Y-%m-%d')))
            
            stats = cursor.fetchone()
            
            # Destinos frecuentes
            cursor.execute("""
                SELECT lugar_descarga, COUNT(*) as veces
                FROM viajes 
                WHERE conductor LIKE ?
                AND fecha_carga >= ?
                GROUP BY lugar_descarga
                ORDER BY veces DESC
                LIMIT 5
            """, (f"%{conductor}%", fecha_inicio.strftime('%Y-%m-%d')))
            
            destinos = cursor.fetchall()
            
            # Tipo de mercancía
            cursor.execute("""
                SELECT tipo_viaje, COUNT(*) as total
                FROM viajes 
                WHERE conductor LIKE ?
                AND fecha_carga >= ?
                GROUP BY tipo_viaje
            """, (f"%{conductor}%", fecha_inicio.strftime('%Y-%m-%d')))
            
            tipos = cursor.fetchall()
            
            conn.close()
            
            if not stats or stats['viajes'] == 0:
                return f"📊 No hay viajes de {conductor} en los últimos {dias} días"
            
            viajes = stats['viajes']
            km_totales = stats['km_totales'] or 0
            km_promedio = stats['km_promedio'] or 0
            
            informe = f"""
👤 ESTADÍSTICAS: {conductor.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Últimos {dias} días

🚛 Viajes realizados: {viajes}
📏 Kilómetros totales: {km_totales:,} km
📊 Promedio por viaje: {km_promedio:.0f} km
🗺️ Destinos diferentes: {stats['destinos']}

📍 DESTINOS FRECUENTES:
"""
            
            for d in destinos:
                informe += f"   • {d['lugar_descarga']} ({d['veces']}x)\n"
            
            informe += "\n📦 POR TIPO:\n"
            
            for t in tipos:
                informe += f"   • {t['tipo_viaje']}: {t['total']} viajes\n"
            
            return informe.strip()
            
        except Exception as e:
            logger.error(f"Error estadísticas conductor: {e}")
            return "❌ Error generando estadísticas"
    
    # ============================================================
    # ACTUALIZAR RUTAS FRECUENTES
    # ============================================================
    
    def actualizar_rutas_frecuentes(self):
        """
        Actualiza la tabla de rutas frecuentes basándose en los viajes.
        Llamar periódicamente (ej: cada noche).
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Obtener rutas de los viajes
            cursor.execute("""
                SELECT 
                    lugar_carga as origen,
                    lugar_descarga as destino,
                    COUNT(*) as veces,
                    AVG(COALESCE(km, 0)) as km_promedio,
                    MAX(fecha_carga) as ultimo
                FROM viajes 
                WHERE lugar_carga IS NOT NULL 
                AND lugar_descarga IS NOT NULL
                AND km > 0
                GROUP BY lugar_carga, lugar_descarga
            """)
            
            rutas = cursor.fetchall()
            
            for r in rutas:
                # Insertar o actualizar
                cursor.execute("""
                    INSERT INTO rutas_frecuentes (origen, destino, km_estimados, veces_realizada, ultimo_viaje)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(origen, destino) DO UPDATE SET
                        km_estimados = ?,
                        veces_realizada = veces_realizada + ?,
                        ultimo_viaje = ?,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    r['origen'], r['destino'], int(r['km_promedio']), r['veces'], r['ultimo'],
                    int(r['km_promedio']), r['veces'], r['ultimo']
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Actualizadas {len(rutas)} rutas frecuentes")
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando rutas: {e}")
            return False
    
    # ============================================================
    # UTILIDADES
    # ============================================================
    
    def _guardar_informe(self, tipo: str, fecha_inicio: datetime, fecha_fin: datetime, datos: dict):
        """Guarda el informe en la base de datos."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO informes (tipo, fecha_inicio, fecha_fin, datos_json)
                VALUES (?, ?, ?, ?)
            """, (
                tipo,
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d'),
                json.dumps(datos)
            ))
            
            conn.commit()
            conn.close()
        except:
            pass  # La tabla puede no existir
    
    def resumen_rapido(self) -> str:
        """
        Genera un resumen rápido del estado actual.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Viajes de hoy
            hoy = datetime.now().strftime('%Y-%m-%d')
            
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM viajes WHERE fecha_carga = ?
            """, (hoy,))
            viajes_hoy = cursor.fetchone()['total']
            
            # Viajes pendientes
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM viajes WHERE estado = 'PENDIENTE'
            """)
            pendientes = cursor.fetchone()['total']
            
            # Conductores activos
            cursor.execute("""
                SELECT COUNT(DISTINCT conductor) as total
                FROM viajes 
                WHERE fecha_carga >= date('now', '-7 days')
                AND conductor IS NOT NULL
            """)
            conductores_activos = cursor.fetchone()['total']
            
            conn.close()
            
            return f"""
📊 RESUMEN RÁPIDO

📅 Viajes hoy: {viajes_hoy}
⏳ Pendientes asignar: {pendientes}
👥 Conductores activos (7d): {conductores_activos}
"""
            
        except Exception as e:
            logger.error(f"Error resumen rápido: {e}")
            return "❌ Error generando resumen"


# ============================================================
# FUNCIONES PARA INTEGRAR EN EL BOT
# ============================================================

async def generar_informe_semanal(db_path: str = "viajes.db") -> str:
    """Función async para usar desde el bot."""
    informes = InformesBot(db_path)
    return informes.informe_semanal()


async def generar_analisis_rentabilidad(db_path: str = "viajes.db") -> str:
    """Función async para usar desde el bot."""
    informes = InformesBot(db_path)
    return informes.analisis_rentabilidad()


async def generar_estadisticas_conductor(conductor: str, db_path: str = "viajes.db") -> str:
    """Función async para usar desde el bot."""
    informes = InformesBot(db_path)
    return informes.estadisticas_conductor(conductor)


async def generar_resumen_rapido(db_path: str = "viajes.db") -> str:
    """Función async para usar desde el bot."""
    informes = InformesBot(db_path)
    return informes.resumen_rapido()


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    print("🧪 Test del sistema de informes\n")
    
    # Crear instancia
    informes = InformesBot("viajes.db")
    
    # Generar informes
    print("="*50)
    print("INFORME SEMANAL:")
    print("="*50)
    print(informes.informe_semanal())
    
    print("\n" + "="*50)
    print("ANÁLISIS DE RENTABILIDAD:")
    print("="*50)
    print(informes.analisis_rentabilidad())
    
    print("\n" + "="*50)
    print("RESUMEN RÁPIDO:")
    print("="*50)
    print(informes.resumen_rapido())
