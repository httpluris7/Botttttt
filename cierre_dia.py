"""
CIERRE DE DÍA v2.0
===================
Gestiona el cierre diario y creación del Excel del día siguiente.

ESTRUCTURA DEL EXCEL:
- Fila 1: Secciones (ZONA NORTE, FECHA, etc.)
- Fila 2: Cabeceras de columnas
- Fila 3+: Datos

COLUMNAS CONDUCTOR (1-8):
- Col 1: Número (24/45)
- Col 2: UBICACIÓN
- Col 3: H.LL (hora llegada)
- Col 4: H.SA (hora salida)
- Col 5: TRANSPORTISTA (nombre)
- Col 6: ABSENTISMO
- Col 7: TRACTORA
- Col 8: REMOLQUE

COLUMNAS VIAJE (9-28):
- Col 9: CLIENTE
- Col 10: Nº PEDIDO
- Col 11: REF. CLIENTE
- Col 12: INTERCAMBIO
- Col 13: Nº PALÉS
- Col 14: LUGAR DE CARGA
- Col 15: HORA LLEGADA (carga)
- Col 16: HORA SALIDA (carga)
- Col 17: LUGAR DE ENTREGA (descarga)
- Col 18: HORA LLEGADA (descarga)
- Col 19: HORA SALIDA (descarga) ← Determina si viaje completado
- Col 20: MERCANCIA
- Col 21: CARGADOR
- Col 22: TRANSPORTISTA (asignado)
- Col 23: PRECIO COBRO
- Col 24: KM
- Col 25-28: Otros

Proceso:
1. Analiza Excel actual
2. Crea NUEVO Excel (RUTAS_DD-MM-YYYY.xlsx)
3. Exporta conductores que terminaron (ubicación = última descarga, H.LL/H.SA = VACIO)
4. Exporta viajes pendientes (sin hora salida descarga)
5. Cambia el bot al nuevo Excel (NO sobrescribe el anterior)
"""

import os
import sys
import sqlite3
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURACIÓN DE ESTRUCTURA
# ============================================================

FILA_SECCION = 1      # Fila con ZONA NORTE, FECHA, etc.
FILA_CABECERAS = 2    # Fila con nombres de columnas
FILA_INICIO_DATOS = 3 # Primera fila de datos

# Columnas de conductores (parte izquierda)
COL_CONDUCTOR = {
    'numero': 1,          # A - 24/45
    'ubicacion': 2,       # B - UBICACIÓN
    'hora_llegada': 3,    # C - H.LL
    'hora_salida': 4,     # D - H.SA
    'nombre': 5,          # E - TRANSPORTISTA (nombre conductor)
    'absentismo': 6,      # F - ABSENTISMO
    'tractora': 7,        # G - TRACTORA
    'remolque': 8,        # H - REMOLQUE
}

# Columnas de viajes
COL_VIAJE = {
    'cliente': 9,              # I
    'num_pedido': 10,          # J
    'ref_cliente': 11,         # K
    'intercambio': 12,         # L
    'num_pales': 13,           # M
    'lugar_carga': 14,         # N
    'hora_llegada_carga': 15,  # O
    'hora_salida_carga': 16,   # P
    'lugar_descarga': 17,      # Q - LUGAR DE ENTREGA
    'hora_llegada_descarga': 18,  # R
    'hora_salida_descarga': 19,   # S ← Determina si completado
    'mercancia': 20,           # T
    'cargador': 21,            # U
    'transportista': 22,       # V - TRANSPORTISTA asignado
    'precio': 23,              # W
    'km': 24,                  # X
    'eur_km': 25,              # Y
    'pago_cargador': 26,       # Z
    'num_exp': 27,             # AA
    'observaciones': 28,       # AB
}

# Total de columnas a copiar
TOTAL_COLUMNAS = 45


@dataclass
class ConductorExportar:
    """Datos de un conductor para exportar"""
    fila_original: int
    numero: str
    nombre: str
    ubicacion: str
    tractora: str
    remolque: str
    absentismo: str


@dataclass
class ViajePendiente:
    """Datos de un viaje pendiente"""
    fila_original: int
    datos_conductor: Dict
    datos_viaje: Dict


class CierreDia:
    """Gestiona el cierre de día y creación del Excel nuevo."""
    
    def __init__(self, excel_path: str, db_path: str, 
                 directorio_excels: str = None,
                 subir_drive_func=None,
                 descargar_drive_func=None):
        self.excel_path = excel_path
        self.db_path = db_path
        self.directorio = directorio_excels or str(Path(excel_path).parent)
        self.subir_drive = subir_drive_func
        self.descargar_drive = descargar_drive_func
        
        # Archivo que guarda el Excel activo
        self.archivo_activo_path = os.path.join(self.directorio, "excel_activo.txt")
        
        logger.info("[CIERRE] Módulo de cierre de día v2.0 inicializado")
    
    # ============================================================
    # GESTIÓN DEL ARCHIVO ACTIVO
    # ============================================================
    
    def obtener_excel_activo(self) -> str:
        """Obtiene el nombre del Excel activo actual"""
        if os.path.exists(self.archivo_activo_path):
            with open(self.archivo_activo_path, 'r') as f:
                return f.read().strip()
        return os.path.basename(self.excel_path)
    
    def establecer_excel_activo(self, nombre_excel: str):
        """Establece el Excel activo"""
        with open(self.archivo_activo_path, 'w') as f:
            f.write(nombre_excel)
        logger.info(f"[CIERRE] Excel activo establecido: {nombre_excel}")
    
    def generar_nombre_excel(self, fecha: datetime = None) -> str:
        """Genera el nombre del Excel para una fecha"""
        if fecha is None:
            fecha = datetime.now()
        return f"RUTAS_{fecha.strftime('%d-%m-%Y')}.xlsx"
    
    # ============================================================
    # ANÁLISIS DEL EXCEL ACTUAL
    # ============================================================
    
    def analizar_excel_actual(self) -> Dict:
        """
        Analiza el Excel actual para identificar:
        - Conductores que terminaron (hora salida descarga registrada)
        - Viajes pendientes (sin hora salida descarga)
        """
        try:
            wb = load_workbook(self.excel_path)
            ws = wb.active
            
            conductores_terminaron = []
            conductores_con_pendiente = []
            viajes_pendientes = []
            viajes_completados = []
            conductores_vistos = set()
            
            # Recorrer filas de datos (desde fila 3)
            for fila in range(FILA_INICIO_DATOS, ws.max_row + 1):
                # Obtener datos clave
                nombre = ws.cell(row=fila, column=COL_CONDUCTOR['nombre']).value
                cliente = ws.cell(row=fila, column=COL_VIAJE['cliente']).value
                hora_salida_descarga = ws.cell(row=fila, column=COL_VIAJE['hora_salida_descarga']).value
                
                # Saltar filas vacías
                if not nombre and not cliente:
                    continue
                
                # Limpiar valores
                nombre_str = str(nombre).strip() if nombre else ''
                hora_salida_str = str(hora_salida_descarga).strip() if hora_salida_descarga else ''
                
                # Ignorar si hora_salida es "None" o vacío
                viaje_completado = bool(hora_salida_str and hora_salida_str.lower() != 'none')
                
                # Procesar conductor (si hay nombre y no lo hemos visto)
                if nombre_str and nombre_str.upper() not in conductores_vistos:
                    conductores_vistos.add(nombre_str.upper())
                    
                    conductor = ConductorExportar(
                        fila_original=fila,
                        numero=str(ws.cell(row=fila, column=COL_CONDUCTOR['numero']).value or '').strip(),
                        nombre=nombre_str,
                        ubicacion=str(ws.cell(row=fila, column=COL_CONDUCTOR['ubicacion']).value or '').strip(),
                        tractora=str(ws.cell(row=fila, column=COL_CONDUCTOR['tractora']).value or '').strip(),
                        remolque=str(ws.cell(row=fila, column=COL_CONDUCTOR['remolque']).value or '').strip(),
                        absentismo=str(ws.cell(row=fila, column=COL_CONDUCTOR['absentismo']).value or '').strip(),
                    )
                    
                    # Clasificar conductor
                    if viaje_completado:
                        # Actualizar ubicación a lugar de descarga
                        lugar_descarga = ws.cell(row=fila, column=COL_VIAJE['lugar_descarga']).value
                        if lugar_descarga:
                            conductor.ubicacion = str(lugar_descarga).strip()
                        conductores_terminaron.append(conductor)
                    elif not cliente:
                        # Sin viaje asignado = disponible
                        conductores_terminaron.append(conductor)
                    else:
                        # Tiene viaje pendiente
                        conductores_con_pendiente.append(conductor)
                
                # Procesar viaje (si hay cliente)
                if cliente:
                    # Obtener datos del conductor de esta fila
                    datos_conductor = {}
                    for campo, col in COL_CONDUCTOR.items():
                        val = ws.cell(row=fila, column=col).value
                        datos_conductor[campo] = str(val).strip() if val else ''
                    
                    # Obtener datos del viaje
                    datos_viaje = {}
                    for campo, col in COL_VIAJE.items():
                        val = ws.cell(row=fila, column=col).value
                        datos_viaje[campo] = str(val).strip() if val else ''
                    
                    viaje = ViajePendiente(
                        fila_original=fila,
                        datos_conductor=datos_conductor,
                        datos_viaje=datos_viaje
                    )
                    
                    if viaje_completado:
                        viajes_completados.append(viaje)
                    else:
                        viajes_pendientes.append(viaje)
            
            wb.close()
            
            resultado = {
                'conductores_terminaron': conductores_terminaron,
                'conductores_con_pendiente': conductores_con_pendiente,
                'viajes_pendientes': viajes_pendientes,
                'viajes_completados': viajes_completados,
                'total_conductores': len(conductores_vistos)
            }
            
            logger.info(f"[CIERRE] Análisis: {len(conductores_terminaron)} terminaron, "
                       f"{len(conductores_con_pendiente)} con pendiente, "
                       f"{len(viajes_pendientes)} viajes pendientes, "
                       f"{len(viajes_completados)} completados")
            
            return resultado
            
        except Exception as e:
            logger.error(f"[CIERRE] Error analizando Excel: {e}")
            import traceback
            traceback.print_exc()
            return {
                'conductores_terminaron': [],
                'conductores_con_pendiente': [],
                'viajes_pendientes': [],
                'viajes_completados': [],
                'total_conductores': 0,
                'error': str(e)
            }
    
    # ============================================================
    # CREAR NUEVO EXCEL
    # ============================================================
    
    def crear_excel_nuevo(self, fecha: datetime = None) -> Tuple[str, str]:
        """
        Crea el Excel del nuevo día.
        NO modifica el Excel original.
        """
        if fecha is None:
            fecha = datetime.now()
        
        nombre_nuevo = self.generar_nombre_excel(fecha)
        ruta_nueva = os.path.join(self.directorio, nombre_nuevo)
        
        try:
            # Cargar Excel actual (solo lectura)
            wb_original = load_workbook(self.excel_path)
            ws_original = wb_original.active
            
            # Crear nuevo workbook
            wb_nuevo = Workbook()
            ws_nuevo = wb_nuevo.active
            ws_nuevo.title = "Rutas"
            
            # Copiar fila 1 (secciones: ZONA NORTE, FECHA, etc.)
            for col in range(1, TOTAL_COLUMNAS + 1):
                celda_origen = ws_original.cell(row=FILA_SECCION, column=col)
                celda_destino = ws_nuevo.cell(row=FILA_SECCION, column=col)
                celda_destino.value = celda_origen.value
                # Copiar formato básico
                if celda_origen.font:
                    celda_destino.font = Font(
                        bold=celda_origen.font.bold,
                        size=celda_origen.font.size
                    )
            
            # Copiar fila 2 (cabeceras)
            for col in range(1, TOTAL_COLUMNAS + 1):
                celda_origen = ws_original.cell(row=FILA_CABECERAS, column=col)
                celda_destino = ws_nuevo.cell(row=FILA_CABECERAS, column=col)
                celda_destino.value = celda_origen.value
                if celda_origen.font:
                    celda_destino.font = Font(
                        bold=celda_origen.font.bold,
                        size=celda_origen.font.size
                    )
            
            # Copiar ancho de columnas
            for col in range(1, TOTAL_COLUMNAS + 1):
                letra = get_column_letter(col)
                if ws_original.column_dimensions[letra].width:
                    ws_nuevo.column_dimensions[letra].width = ws_original.column_dimensions[letra].width
            
            # Analizar datos
            analisis = self.analizar_excel_actual()
            conductores_terminaron = analisis['conductores_terminaron']
            viajes_pendientes = analisis['viajes_pendientes']
            
            fila_actual = FILA_INICIO_DATOS
            conductores_escritos = set()
            
            # 1. Escribir conductores que terminaron (vacíos, ubicación actualizada)
            for conductor in conductores_terminaron:
                if conductor.nombre.upper() in conductores_escritos:
                    continue
                conductores_escritos.add(conductor.nombre.upper())
                
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['numero'], value=conductor.numero)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['ubicacion'], value=conductor.ubicacion)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['hora_llegada'], value="VACIO")
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['hora_salida'], value="VACIO")
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['nombre'], value=conductor.nombre)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['absentismo'], value=conductor.absentismo)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['tractora'], value=conductor.tractora)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['remolque'], value=conductor.remolque)
                
                fila_actual += 1
            
            # 2. Escribir viajes pendientes CON sus conductores
            for viaje in viajes_pendientes:
                transportista = viaje.datos_viaje.get('transportista', '').strip()
                
                # Escribir datos del conductor
                conductor_nombre = viaje.datos_conductor.get('nombre', '').strip()
                if conductor_nombre and conductor_nombre.upper() not in conductores_escritos:
                    conductores_escritos.add(conductor_nombre.upper())
                
                # Columnas del conductor
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['numero'], 
                             value=viaje.datos_conductor.get('numero', ''))
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['ubicacion'], 
                             value=viaje.datos_conductor.get('ubicacion', ''))
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['hora_llegada'], value='')
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['hora_salida'], value='')
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['nombre'], 
                             value=viaje.datos_conductor.get('nombre', ''))
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['absentismo'], 
                             value=viaje.datos_conductor.get('absentismo', ''))
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['tractora'], 
                             value=viaje.datos_conductor.get('tractora', ''))
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['remolque'], 
                             value=viaje.datos_conductor.get('remolque', ''))
                
                # Columnas del viaje (sin horas de registro)
                for campo, col in COL_VIAJE.items():
                    valor = viaje.datos_viaje.get(campo, '')
                    # Limpiar horas de registro
                    if campo in ['hora_llegada_carga', 'hora_salida_carga', 
                                'hora_llegada_descarga', 'hora_salida_descarga']:
                        valor = ''
                    ws_nuevo.cell(row=fila_actual, column=col, value=valor)
                
                fila_actual += 1
            
            # Guardar nuevo Excel
            wb_nuevo.save(ruta_nueva)
            wb_nuevo.close()
            wb_original.close()
            
            logger.info(f"[CIERRE] ✅ Nuevo Excel creado: {nombre_nuevo}")
            logger.info(f"[CIERRE]    - {len(conductores_escritos)} conductores")
            logger.info(f"[CIERRE]    - {len(viajes_pendientes)} viajes pendientes")
            
            return nombre_nuevo, ruta_nueva
            
        except Exception as e:
            logger.error(f"[CIERRE] Error creando Excel nuevo: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    # ============================================================
    # SINCRONIZAR BD
    # ============================================================
    
    def sincronizar_bd_nuevo_excel(self, ruta_excel: str) -> Dict:
        """Sincroniza la BD con el nuevo Excel"""
        try:
            from separador_excel_empresa import SeparadorExcelEmpresa
            from extractor_telefonos import sincronizar_telefonos
            from generador_direcciones import sincronizar_direcciones
            
            separador = SeparadorExcelEmpresa(self.db_path)
            resultado = separador.sincronizar_desde_archivo(ruta_excel, forzar=True)
            
            sincronizar_telefonos(ruta_excel, self.db_path)
            sincronizar_direcciones(self.db_path)
            
            logger.info(f"[CIERRE] BD sincronizada: {resultado}")
            return resultado
            
        except Exception as e:
            logger.error(f"[CIERRE] Error sincronizando BD: {e}")
            return {'exito': False, 'error': str(e)}
    
    # ============================================================
    # EJECUTAR CIERRE
    # ============================================================
    
    def ejecutar_cierre(self, fecha_nuevo: datetime = None) -> Dict:
        """
        Ejecuta el cierre de día.
        CREA un nuevo Excel, NO modifica el anterior.
        """
        resultado = {
            'exito': False,
            'excel_anterior': os.path.basename(self.excel_path),
            'excel_nuevo': None,
            'conductores_exportados': 0,
            'viajes_pendientes': 0,
            'viajes_completados': 0,
            'bd_sincronizada': False,
            'drive_subido': False,
            'errores': []
        }
        
        try:
            logger.info("[CIERRE] ═══════════════════════════════════════")
            logger.info("[CIERRE] INICIANDO CIERRE DE DÍA")
            logger.info("[CIERRE] ═══════════════════════════════════════")
            
            # Paso 1: Analizar
            logger.info("[CIERRE] Paso 1: Analizando Excel actual...")
            analisis = self.analizar_excel_actual()
            
            if 'error' in analisis:
                resultado['errores'].append(f"Error analizando: {analisis['error']}")
                return resultado
            
            resultado['conductores_exportados'] = len(analisis['conductores_terminaron']) + len(analisis['conductores_con_pendiente'])
            resultado['viajes_pendientes'] = len(analisis['viajes_pendientes'])
            resultado['viajes_completados'] = len(analisis['viajes_completados'])
            
            # Paso 2: Crear nuevo Excel
            logger.info("[CIERRE] Paso 2: Creando nuevo Excel...")
            nombre_nuevo, ruta_nueva = self.crear_excel_nuevo(fecha_nuevo)
            resultado['excel_nuevo'] = nombre_nuevo
            
            # Paso 3: Actualizar referencia al Excel activo
            logger.info("[CIERRE] Paso 3: Actualizando referencia...")
            self.establecer_excel_activo(nombre_nuevo)
            
            # Paso 4: Sincronizar BD con el nuevo Excel
            logger.info("[CIERRE] Paso 4: Sincronizando BD...")
            sync_resultado = self.sincronizar_bd_nuevo_excel(ruta_nueva)
            resultado['bd_sincronizada'] = sync_resultado.get('exito', True) if 'error' not in sync_resultado else False
            
            # Paso 5: Subir nuevo Excel a Drive
            if self.subir_drive:
                logger.info("[CIERRE] Paso 5: Subiendo a Drive...")
                try:
                    # Subir el nuevo Excel
                    self.subir_drive()
                    resultado['drive_subido'] = True
                except Exception as e:
                    resultado['errores'].append(f"Error subiendo a Drive: {e}")
            
            resultado['exito'] = True
            
            logger.info("[CIERRE] ═══════════════════════════════════════")
            logger.info("[CIERRE] ✅ CIERRE DE DÍA COMPLETADO")
            logger.info(f"[CIERRE]    Excel anterior: {resultado['excel_anterior']} (sin modificar)")
            logger.info(f"[CIERRE]    Excel nuevo: {nombre_nuevo}")
            logger.info(f"[CIERRE]    Conductores: {resultado['conductores_exportados']}")
            logger.info(f"[CIERRE]    Viajes pendientes: {resultado['viajes_pendientes']}")
            logger.info("[CIERRE] ═══════════════════════════════════════")
            
            return resultado
            
        except Exception as e:
            logger.error(f"[CIERRE] ❌ Error en cierre: {e}")
            import traceback
            traceback.print_exc()
            resultado['errores'].append(str(e))
            return resultado
    
    # ============================================================
    # VERIFICACIONES
    # ============================================================
    
    def verificar_cierre_seguro(self) -> Dict:
        """Verifica si es seguro hacer el cierre"""
        analisis = self.analizar_excel_actual()
        
        nombre_hoy = self.generar_nombre_excel()
        ruta_hoy = os.path.join(self.directorio, nombre_hoy)
        excel_hoy_existe = os.path.exists(ruta_hoy)
        
        return {
            'seguro': not excel_hoy_existe,
            'excel_hoy_existe': excel_hoy_existe,
            'nombre_excel_hoy': nombre_hoy,
            'conductores_terminaron': len(analisis.get('conductores_terminaron', [])),
            'conductores_con_pendiente': len(analisis.get('conductores_con_pendiente', [])),
            'viajes_pendientes': len(analisis.get('viajes_pendientes', [])),
            'viajes_completados': len(analisis.get('viajes_completados', [])),
            'advertencia': f"Ya existe {nombre_hoy}" if excel_hoy_existe else None
        }
    
    def listar_excels_historicos(self, limite: int = 7) -> List[Dict]:
        """Lista los Excels históricos disponibles"""
        excels = []
        
        try:
            for archivo in os.listdir(self.directorio):
                if archivo.startswith("RUTAS_") and archivo.endswith(".xlsx"):
                    ruta = os.path.join(self.directorio, archivo)
                    fecha_mod = datetime.fromtimestamp(os.path.getmtime(ruta))
                    
                    excels.append({
                        'nombre': archivo,
                        'ruta': ruta,
                        'fecha_modificacion': fecha_mod,
                        'tamaño': os.path.getsize(ruta)
                    })
        except Exception as e:
            logger.error(f"[CIERRE] Error listando históricos: {e}")
        
        excels.sort(key=lambda x: x['fecha_modificacion'], reverse=True)
        return excels[:limite]


# ============================================================
# FUNCIÓN PARA INTEGRAR EN BOT
# ============================================================

def crear_cierre_dia(excel_path: str, db_path: str, 
                     subir_drive_func=None, descargar_drive_func=None):
    """Crea una instancia del módulo de cierre"""
    return CierreDia(
        excel_path=excel_path,
        db_path=db_path,
        subir_drive_func=subir_drive_func,
        descargar_drive_func=descargar_drive_func
    )


# ============================================================
# SCRIPT PARA CRON
# ============================================================

if __name__ == "__main__":
    import logging
    from dotenv import load_dotenv
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    load_dotenv()
    
    EXCEL_EMPRESA = os.getenv("EXCEL_EMPRESA", "PRUEBO.xlsx")
    DB_PATH = os.getenv("DB_PATH", "logistica.db")
    DRIVE_ENABLED = os.getenv("DRIVE_ENABLED", "false").lower() == "true"
    
    subir_drive = None
    if DRIVE_ENABLED:
        try:
            from sync_automatico import subir_excel_a_drive, inicializar_drive
            if inicializar_drive():
                subir_drive = subir_excel_a_drive
        except Exception as e:
            logger.warning(f"No se pudo configurar Drive: {e}")
    
    cierre = CierreDia(
        excel_path=EXCEL_EMPRESA,
        db_path=DB_PATH,
        subir_drive_func=subir_drive
    )
    
    verificacion = cierre.verificar_cierre_seguro()
    
    if not verificacion['seguro']:
        logger.warning(f"[CIERRE] ⚠️ {verificacion['advertencia']}")
        if len(sys.argv) > 1 and sys.argv[1] == "--forzar":
            logger.info("[CIERRE] Forzando cierre...")
        else:
            logger.warning("[CIERRE] Use --forzar para continuar")
            sys.exit(1)
    
    resultado = cierre.ejecutar_cierre()
    
    if resultado['exito']:
        logger.info("[CIERRE] ✅ Completado")
        sys.exit(0)
    else:
        logger.error(f"[CIERRE] ❌ Errores: {resultado['errores']}")
        sys.exit(1)
