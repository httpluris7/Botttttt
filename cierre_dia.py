"""
CIERRE DE DÍA v4.0
===================
Lógica correcta: Conductores y Viajes son INDEPENDIENTES.

ESTRUCTURA DEL EXCEL:
- Columnas A-H: Lista de CONDUCTORES (bloque izquierdo)
- Columnas I+: Lista de VIAJES (bloque derecho)
- Relación: columna TRANSPORTISTA (V/22) del viaje indica qué conductor lo hace

PROCESO DE CIERRE:
1. Identificar viajes COMPLETADOS (tienen hora salida descarga en col 19)
2. Para cada viaje completado, anotar el TRANSPORTISTA y su lugar de descarga
3. Copiar Excel completo
4. Viajes completados → Limpiar columnas del viaje
5. Viajes pendientes → Limpiar solo horas de registro
6. Conductores que terminaron → Ubicación = última descarga, H.LL/H.SA = "VACIO"
7. Conductores que NO terminaron → H.LL/H.SA = vacías
"""

import os
import sys
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Set

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURACIÓN DE COLUMNAS
# ============================================================

# Columnas de CONDUCTORES (bloque izquierdo)
COL_UBICACION = 2        # B
COL_H_LLEGADA = 3        # C
COL_H_SALIDA = 4         # D
COL_TRANSPORTISTA_COND = 5    # E - Nombre del conductor

# Columnas de VIAJES (bloque derecho)
COL_CLIENTE = 9                    # I
COL_LUGAR_CARGA = 14               # N
COL_HORA_LLEGADA_CARGA = 15        # O
COL_HORA_SALIDA_CARGA = 16         # P
COL_LUGAR_DESCARGA = 17            # Q
COL_HORA_LLEGADA_DESCARGA = 18     # R
COL_HORA_SALIDA_DESCARGA = 19      # S - CLAVE para saber si terminó
COL_TRANSPORTISTA_VIAJE = 22       # V - Qué conductor hace el viaje

# Rango de columnas de viaje (para limpiar)
COL_VIAJE_INICIO = 9    # I
COL_VIAJE_FIN = 28      # AB


class CierreDia:
    """Gestiona el cierre de día con lógica de bloques independientes."""
    
    def __init__(self, excel_path: str, db_path: str, 
                 directorio_excels: str = None,
                 subir_drive_func=None,
                 subir_archivo_nuevo_func=None):
        self.excel_path = excel_path
        self.db_path = db_path
        self.directorio = directorio_excels or str(Path(excel_path).parent)
        self.subir_drive = subir_drive_func
        self.subir_archivo_nuevo = subir_archivo_nuevo_func
        
        logger.info("[CIERRE] Módulo de cierre de día v4.0 inicializado")
    
    def obtener_excel_activo(self) -> str:
        return os.path.basename(self.excel_path)
    
    def generar_nombre_excel(self, fecha: datetime = None) -> str:
        if fecha is None:
            fecha = datetime.now()
        return f"RUTAS_{fecha.strftime('%d-%m-%Y')}.xlsx"
    
    def _es_fila_cabecera(self, ws, fila: int) -> bool:
        """Detecta si es una fila de cabecera/sección"""
        col1 = ws.cell(row=fila, column=1).value
        col5 = ws.cell(row=fila, column=COL_TRANSPORTISTA_COND).value
        col9 = ws.cell(row=fila, column=COL_CLIENTE).value
        
        if col1 and 'ZONA' in str(col1).upper():
            return True
        if col5 and str(col5).upper() == 'TRANSPORTISTA':
            return True
        if col9 and str(col9).upper() in ['CLIENTE', 'FECHA']:
            return True
        return False
    
    def _get_cell_value(self, ws, fila: int, columna: int) -> str:
        """Obtiene valor de celda como string limpio"""
        try:
            valor = ws.cell(row=fila, column=columna).value
            if valor is None:
                return ''
            return str(valor).strip()
        except:
            return ''
    
    def _set_cell_value(self, ws, fila: int, columna: int, valor):
        """Establece valor manejando celdas combinadas"""
        try:
            cell = ws.cell(row=fila, column=columna)
            for merged_range in ws.merged_cells.ranges:
                if cell.coordinate in merged_range:
                    return  # Es merge, no modificar
            cell.value = valor
        except:
            pass
    
    # ============================================================
    # ANÁLISIS DE VIAJES COMPLETADOS
    # ============================================================
    
    def _obtener_conductores_terminaron(self, ws) -> Dict[str, str]:
        """
        Busca viajes completados y devuelve los conductores que terminaron.
        
        Returns:
            Dict {nombre_conductor_upper: lugar_descarga}
        """
        conductores_terminaron = {}
        
        for fila in range(1, ws.max_row + 1):
            if self._es_fila_cabecera(ws, fila):
                continue
            
            # Verificar si el viaje está completado (tiene hora salida descarga)
            hora_salida = self._get_cell_value(ws, fila, COL_HORA_SALIDA_DESCARGA)
            if not hora_salida or hora_salida.upper() in ['', 'HORA SALIDA', 'VACIO']:
                continue
            
            # Viaje completado - obtener transportista y lugar descarga
            transportista = self._get_cell_value(ws, fila, COL_TRANSPORTISTA_VIAJE)
            lugar_descarga = self._get_cell_value(ws, fila, COL_LUGAR_DESCARGA)
            
            if transportista and transportista.upper() not in ['TRANSPORTISTA', '']:
                # Guardar (si ya existe, se sobrescribe - última descarga)
                conductores_terminaron[transportista.upper()] = lugar_descarga
        
        return conductores_terminaron
    
    # ============================================================
    # ANÁLISIS
    # ============================================================
    
    def analizar_excel_actual(self) -> Dict:
        """Analiza el Excel para mostrar estadísticas"""
        try:
            wb = load_workbook(self.excel_path)
            ws = wb.active
            
            viajes_pendientes = 0
            viajes_completados = 0
            conductores_total = set()
            
            # Obtener conductores que terminaron
            conductores_terminaron = self._obtener_conductores_terminaron(ws)
            
            for fila in range(1, ws.max_row + 1):
                if self._es_fila_cabecera(ws, fila):
                    continue
                
                # Contar conductor
                conductor = self._get_cell_value(ws, fila, COL_TRANSPORTISTA_COND)
                if conductor and conductor.upper() not in ['TRANSPORTISTA', '']:
                    conductores_total.add(conductor.upper())
                
                # Contar viajes
                cliente = self._get_cell_value(ws, fila, COL_CLIENTE)
                if cliente and cliente.upper() not in ['CLIENTE', '']:
                    hora_salida = self._get_cell_value(ws, fila, COL_HORA_SALIDA_DESCARGA)
                    if hora_salida and hora_salida.upper() not in ['', 'HORA SALIDA']:
                        viajes_completados += 1
                    else:
                        viajes_pendientes += 1
            
            wb.close()
            
            conductores_terminaron_count = len(conductores_terminaron)
            conductores_disponibles = len(conductores_total) - conductores_terminaron_count
            
            return {
                'conductores_terminaron': conductores_terminaron_count,
                'conductores_disponibles': max(0, conductores_disponibles),
                'viajes_pendientes': viajes_pendientes,
                'viajes_completados': viajes_completados,
            }
            
        except Exception as e:
            logger.error(f"[CIERRE] Error analizando: {e}")
            return {
                'conductores_terminaron': 0,
                'conductores_disponibles': 0,
                'viajes_pendientes': 0,
                'viajes_completados': 0,
                'error': str(e)
            }
    
    # ============================================================
    # CREAR NUEVO EXCEL
    # ============================================================
    
    def crear_excel_nuevo(self, fecha: datetime = None) -> Tuple[str, str]:
        """
        Crea nuevo Excel con la lógica de bloques independientes.
        """
        if fecha is None:
            fecha = datetime.now()
        
        nombre_nuevo = self.generar_nombre_excel(fecha)
        ruta_nueva = os.path.join(self.directorio, nombre_nuevo)
        
        try:
            # PASO 1: Copiar archivo original
            logger.info(f"[CIERRE] Copiando {self.excel_path} → {ruta_nueva}")
            shutil.copy2(self.excel_path, ruta_nueva)
            
            # PASO 2: Abrir la copia
            wb = load_workbook(ruta_nueva)
            ws = wb.active
            
            # PASO 3: Obtener conductores que terminaron (y su ubicación)
            conductores_terminaron = self._obtener_conductores_terminaron(ws)
            logger.info(f"[CIERRE] Conductores que terminaron: {len(conductores_terminaron)}")
            for nombre, ubicacion in conductores_terminaron.items():
                logger.info(f"[CIERRE]   - {nombre} → {ubicacion}")
            
            # PASO 4: Procesar cada fila
            viajes_limpiados = 0
            viajes_horas_limpiadas = 0
            conductores_actualizados = 0
            
            for fila in range(1, ws.max_row + 1):
                if self._es_fila_cabecera(ws, fila):
                    continue
                
                # === PROCESAR BLOQUE VIAJES (columnas I+) ===
                cliente = self._get_cell_value(ws, fila, COL_CLIENTE)
                if cliente and cliente.upper() not in ['CLIENTE', '']:
                    hora_salida = self._get_cell_value(ws, fila, COL_HORA_SALIDA_DESCARGA)
                    
                    if hora_salida and hora_salida.upper() not in ['', 'HORA SALIDA']:
                        # VIAJE COMPLETADO → Limpiar todas las columnas del viaje
                        for col in range(COL_VIAJE_INICIO, COL_VIAJE_FIN + 1):
                            self._set_cell_value(ws, fila, col, None)
                        viajes_limpiados += 1
                    else:
                        # VIAJE PENDIENTE → Solo limpiar horas de registro
                        self._set_cell_value(ws, fila, COL_HORA_LLEGADA_CARGA, None)
                        self._set_cell_value(ws, fila, COL_HORA_SALIDA_CARGA, None)
                        self._set_cell_value(ws, fila, COL_HORA_LLEGADA_DESCARGA, None)
                        self._set_cell_value(ws, fila, COL_HORA_SALIDA_DESCARGA, None)
                        viajes_horas_limpiadas += 1
                
                # === PROCESAR BLOQUE CONDUCTORES (columnas A-H) ===
                conductor = self._get_cell_value(ws, fila, COL_TRANSPORTISTA_COND)
                if conductor and conductor.upper() not in ['TRANSPORTISTA', '']:
                    conductor_upper = conductor.upper()
                    
                    if conductor_upper in conductores_terminaron:
                        # CONDUCTOR TERMINÓ → Actualizar ubicación + H.LL/H.SA = VACIO
                        nueva_ubicacion = conductores_terminaron[conductor_upper]
                        if nueva_ubicacion:
                            self._set_cell_value(ws, fila, COL_UBICACION, nueva_ubicacion)
                        self._set_cell_value(ws, fila, COL_H_LLEGADA, "VACIO")
                        self._set_cell_value(ws, fila, COL_H_SALIDA, "VACIO")
                        conductores_actualizados += 1
                    else:
                        # CONDUCTOR NO TERMINÓ → H.LL/H.SA vacías
                        self._set_cell_value(ws, fila, COL_H_LLEGADA, None)
                        self._set_cell_value(ws, fila, COL_H_SALIDA, None)
            
            # Guardar
            wb.save(ruta_nueva)
            wb.close()
            
            logger.info(f"[CIERRE] ✅ Excel creado: {nombre_nuevo}")
            logger.info(f"[CIERRE]    - Viajes completados limpiados: {viajes_limpiados}")
            logger.info(f"[CIERRE]    - Viajes pendientes (horas limpiadas): {viajes_horas_limpiadas}")
            logger.info(f"[CIERRE]    - Conductores actualizados (terminaron): {conductores_actualizados}")
            
            return nombre_nuevo, ruta_nueva
            
        except Exception as e:
            logger.error(f"[CIERRE] Error creando Excel: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    # ============================================================
    # EJECUTAR CIERRE
    # ============================================================
    
    def ejecutar_cierre(self, fecha_nuevo: datetime = None) -> Dict:
        """Ejecuta el cierre de día completo."""
        resultado = {
            'exito': False,
            'excel_original': os.path.basename(self.excel_path),
            'excel_nuevo': None,
            'ruta_excel_nuevo': None,
            'conductores_exportados': 0,
            'viajes_pendientes': 0,
            'viajes_completados': 0,
            'drive_subido': False,
            'errores': []
        }
        
        try:
            logger.info("[CIERRE] ═══════════════════════════════════════")
            logger.info("[CIERRE] INICIANDO CIERRE DE DÍA v4.0")
            logger.info("[CIERRE] ═══════════════════════════════════════")
            
            # Analizar
            analisis = self.analizar_excel_actual()
            if 'error' in analisis:
                resultado['errores'].append(analisis['error'])
                return resultado
            
            resultado['conductores_exportados'] = analisis['conductores_terminaron'] + analisis['conductores_disponibles']
            resultado['viajes_pendientes'] = analisis['viajes_pendientes']
            resultado['viajes_completados'] = analisis['viajes_completados']
            
            # Crear Excel nuevo
            nombre_nuevo, ruta_nueva = self.crear_excel_nuevo(fecha_nuevo)
            resultado['excel_nuevo'] = nombre_nuevo
            resultado['ruta_excel_nuevo'] = ruta_nueva
            
            # Subir a Drive
            if self.subir_archivo_nuevo:
                logger.info(f"[CIERRE] Subiendo {nombre_nuevo} a Drive...")
                try:
                    if self.subir_archivo_nuevo(ruta_nueva, nombre_nuevo):
                        resultado['drive_subido'] = True
                except Exception as e:
                    resultado['errores'].append(f"Error Drive: {e}")
            
            resultado['exito'] = True
            
            logger.info("[CIERRE] ═══════════════════════════════════════")
            logger.info("[CIERRE] ✅ CIERRE COMPLETADO")
            logger.info(f"[CIERRE]    Excel: {nombre_nuevo}")
            logger.info("[CIERRE] ═══════════════════════════════════════")
            
            return resultado
            
        except Exception as e:
            logger.error(f"[CIERRE] Error: {e}")
            resultado['errores'].append(str(e))
            return resultado
    
    # ============================================================
    # VERIFICACIONES
    # ============================================================
    
    def verificar_cierre_seguro(self) -> Dict:
        analisis = self.analizar_excel_actual()
        
        nombre_hoy = self.generar_nombre_excel()
        ruta_hoy = os.path.join(self.directorio, nombre_hoy)
        excel_hoy_existe = os.path.exists(ruta_hoy)
        
        return {
            'seguro': not excel_hoy_existe,
            'excel_hoy_existe': excel_hoy_existe,
            'nombre_excel_hoy': nombre_hoy,
            'conductores_terminaron': analisis.get('conductores_terminaron', 0),
            'conductores_disponibles': analisis.get('conductores_disponibles', 0),
            'viajes_pendientes': analisis.get('viajes_pendientes', 0),
            'viajes_completados': analisis.get('viajes_completados', 0),
            'advertencia': f"Ya existe {nombre_hoy}" if excel_hoy_existe else None
        }
    
    def listar_excels_historicos(self, limite: int = 7) -> List[Dict]:
        excels = []
        try:
            for archivo in os.listdir(self.directorio):
                if archivo.startswith("RUTAS_") and archivo.endswith(".xlsx"):
                    ruta = os.path.join(self.directorio, archivo)
                    excels.append({
                        'nombre': archivo,
                        'ruta': ruta,
                        'fecha_modificacion': datetime.fromtimestamp(os.path.getmtime(ruta)),
                        'tamaño': os.path.getsize(ruta)
                    })
        except Exception as e:
            logger.error(f"[CIERRE] Error listando: {e}")
        
        excels.sort(key=lambda x: x['fecha_modificacion'], reverse=True)
        return excels[:limite]


def crear_cierre_dia(excel_path: str, db_path: str, subir_drive_func=None, subir_archivo_nuevo_func=None):
    return CierreDia(
        excel_path=excel_path,
        db_path=db_path,
        subir_drive_func=subir_drive_func,
        subir_archivo_nuevo_func=subir_archivo_nuevo_func
    )


if __name__ == "__main__":
    from dotenv import load_dotenv
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    load_dotenv()
    
    EXCEL = os.getenv("EXCEL_EMPRESA", "PRUEBO.xlsx")
    cierre = CierreDia(EXCEL, "logistica.db")
    resultado = cierre.ejecutar_cierre()
    
    if resultado['exito']:
        print(f"✅ Creado: {resultado['excel_nuevo']}")
    else:
        print(f"❌ Error: {resultado['errores']}")
