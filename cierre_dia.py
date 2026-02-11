"""
CIERRE DE DÍA v1.0
===================
Gestiona el cierre diario y creación del Excel del día siguiente.

Proceso:
1. Identifica conductores que terminaron (tienen hora salida descarga)
2. Identifica viajes pendientes (sin hora salida descarga)
3. Crea nuevo Excel del día
4. Exporta conductores con ubicación actualizada (H.LL/H.SA = VACIO)
5. Exporta viajes pendientes
6. Cambia el bot al nuevo Excel
7. Sube a Drive

Uso manual (bot):
    from cierre_dia import CierreDia
    cierre = CierreDia(config)
    resultado = await cierre.ejecutar_cierre()

Uso automático (cron):
    python3 cierre_dia.py
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
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURACIÓN DE COLUMNAS
# ============================================================

# Columnas de conductores (parte izquierda del Excel)
COL_CONDUCTOR = {
    'nombre': 1,          # A
    'ubicacion': 2,       # B
    'hora_llegada': 3,    # C (H.LL)
    'hora_salida': 4,     # D (H.SA)
    'tractora': 5,        # E
    'remolque': 6,        # F
    'zona': 7,            # G
    'telefono': 8,        # H
}

# Columnas de viajes
COL_VIAJE = {
    'zona': 9,            # I
    'cliente': 10,        # J
    'num_pedido': 11,     # K
    'ref_cliente': 12,    # L
    'intercambio': 13,    # M
    'lugar_carga': 14,    # N
    'hora_llegada_carga': 15,    # O
    'hora_salida_carga': 16,     # P
    'lugar_descarga': 17,        # Q
    'hora_llegada_descarga': 18, # R
    'hora_salida_descarga': 19,  # S
    'mercancia': 20,      # T
    'km': 21,             # U
    'transportista': 22,  # V
    'precio': 23,         # W
    'observaciones': 24,  # X
}

# Fila donde empiezan los datos (1 = cabecera)
FILA_INICIO_DATOS = 2


@dataclass
class ConductorParaExportar:
    """Datos de un conductor para exportar al nuevo día"""
    fila_original: int
    nombre: str
    ubicacion: str  # Será la última descarga
    tractora: str
    remolque: str
    zona: str
    telefono: str


@dataclass
class ViajePendiente:
    """Datos de un viaje pendiente para exportar al nuevo día"""
    fila_original: int
    datos: Dict  # Todos los datos del viaje


class CierreDia:
    """
    Gestiona el cierre de día y creación del Excel nuevo.
    """
    
    def __init__(self, excel_path: str, db_path: str, 
                 directorio_excels: str = None,
                 subir_drive_func=None,
                 descargar_drive_func=None):
        """
        Args:
            excel_path: Ruta al Excel actual
            db_path: Ruta a la base de datos
            directorio_excels: Directorio donde guardar los Excels (default: mismo que excel_path)
            subir_drive_func: Función para subir a Drive
            descargar_drive_func: Función para descargar de Drive
        """
        self.excel_path = excel_path
        self.db_path = db_path
        self.directorio = directorio_excels or str(Path(excel_path).parent)
        self.subir_drive = subir_drive_func
        self.descargar_drive = descargar_drive_func
        
        # Archivo que guarda el Excel activo
        self.archivo_activo_path = os.path.join(self.directorio, "excel_activo.txt")
        
        logger.info("[CIERRE] Módulo de cierre de día v1.0 inicializado")
    
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
        - Conductores que terminaron (hora salida descarga registrada O sin viaje asignado)
        - Conductores con viajes pendientes (tienen viaje sin hora salida descarga)
        - Viajes pendientes (sin hora salida descarga)
        
        Returns:
            Dict con listas de conductores y viajes
        """
        try:
            wb = load_workbook(self.excel_path)
            ws = wb.active
            
            conductores_terminaron = []      # Terminaron viaje o están vacíos
            conductores_con_pendiente = []   # Tienen viaje pendiente
            viajes_pendientes = []
            viajes_completados = []
            
            conductores_vistos = set()  # Para evitar duplicados
            
            # Recorrer filas de datos
            for fila in range(FILA_INICIO_DATOS, ws.max_row + 1):
                # Verificar si hay datos en la fila
                nombre = ws.cell(row=fila, column=COL_CONDUCTOR['nombre']).value
                cliente = ws.cell(row=fila, column=COL_VIAJE['cliente']).value
                
                if not nombre and not cliente:
                    continue  # Fila vacía
                
                # Obtener hora salida descarga
                hora_salida_descarga = ws.cell(row=fila, column=COL_VIAJE['hora_salida_descarga']).value
                hora_salida_descarga_str = str(hora_salida_descarga).strip() if hora_salida_descarga else ''
                
                # Procesar conductor (si hay nombre y no lo hemos visto)
                if nombre:
                    nombre_str = str(nombre).strip()
                    
                    if nombre_str not in conductores_vistos:
                        conductores_vistos.add(nombre_str)
                        
                        conductor = ConductorParaExportar(
                            fila_original=fila,
                            nombre=nombre_str,
                            ubicacion=str(ws.cell(row=fila, column=COL_CONDUCTOR['ubicacion']).value or '').strip(),
                            tractora=str(ws.cell(row=fila, column=COL_CONDUCTOR['tractora']).value or '').strip(),
                            remolque=str(ws.cell(row=fila, column=COL_CONDUCTOR['remolque']).value or '').strip(),
                            zona=str(ws.cell(row=fila, column=COL_CONDUCTOR['zona']).value or '').strip(),
                            telefono=str(ws.cell(row=fila, column=COL_CONDUCTOR['telefono']).value or '').strip(),
                        )
                        
                        # Caso 1: Tiene viaje completado (hora salida descarga registrada)
                        if cliente and hora_salida_descarga_str:
                            # Actualizar ubicación a lugar de descarga
                            lugar_descarga = ws.cell(row=fila, column=COL_VIAJE['lugar_descarga']).value
                            if lugar_descarga:
                                conductor.ubicacion = str(lugar_descarga).strip()
                            conductores_terminaron.append(conductor)
                        
                        # Caso 2: No tiene viaje o viaje vacío → disponible
                        elif not cliente:
                            conductores_terminaron.append(conductor)
                        
                        # Caso 3: Tiene viaje pendiente
                        else:
                            conductores_con_pendiente.append(conductor)
                
                # Procesar viaje (si hay cliente)
                if cliente:
                    viaje_datos = {}
                    for campo, columna in COL_VIAJE.items():
                        valor = ws.cell(row=fila, column=columna).value
                        viaje_datos[campo] = str(valor).strip() if valor else ''
                    
                    viaje = ViajePendiente(
                        fila_original=fila,
                        datos=viaje_datos
                    )
                    
                    # Clasificar viaje
                    if hora_salida_descarga_str:
                        viajes_completados.append(viaje)
                    else:
                        viajes_pendientes.append(viaje)
            
            wb.close()
            
            resultado = {
                'conductores_terminaron': conductores_terminaron,
                'conductores_con_pendiente': conductores_con_pendiente,
                'viajes_pendientes': viajes_pendientes,
                'viajes_completados': viajes_completados,
                'total_filas': ws.max_row - FILA_INICIO_DATOS + 1
            }
            
            logger.info(f"[CIERRE] Análisis: {len(conductores_terminaron)} terminaron/disponibles, "
                       f"{len(conductores_con_pendiente)} con viaje pendiente, "
                       f"{len(viajes_pendientes)} viajes pendientes, "
                       f"{len(viajes_completados)} viajes completados")
            
            return resultado
            
        except Exception as e:
            logger.error(f"[CIERRE] Error analizando Excel: {e}")
            return {
                'conductores_terminaron': [],
                'conductores_con_pendiente': [],
                'viajes_pendientes': [],
                'viajes_completados': [],
                'total_filas': 0,
                'error': str(e)
            }
    
    # ============================================================
    # CREAR NUEVO EXCEL
    # ============================================================
    
    def crear_excel_nuevo(self, fecha: datetime = None) -> Tuple[str, str]:
        """
        Crea el Excel del nuevo día.
        
        Args:
            fecha: Fecha para el nuevo Excel (default: hoy)
        
        Returns:
            Tuple (nombre_archivo, ruta_completa)
        """
        if fecha is None:
            fecha = datetime.now()
        
        nombre_nuevo = self.generar_nombre_excel(fecha)
        ruta_nueva = os.path.join(self.directorio, nombre_nuevo)
        
        try:
            # Cargar Excel actual como plantilla
            wb = load_workbook(self.excel_path)
            ws = wb.active
            
            # Obtener cabeceras (fila 1)
            cabeceras = []
            for col in range(1, ws.max_column + 1):
                cabeceras.append(ws.cell(row=1, column=col).value)
            
            # Analizar datos actuales
            analisis = self.analizar_excel_actual()
            conductores_terminaron = analisis['conductores_terminaron']
            conductores_con_pendiente = analisis.get('conductores_con_pendiente', [])
            viajes_pendientes = analisis['viajes_pendientes']
            
            # Crear nuevo workbook
            wb_nuevo = Workbook()
            ws_nuevo = wb_nuevo.active
            ws_nuevo.title = "Rutas"
            
            # Copiar cabeceras
            for col, cabecera in enumerate(cabeceras, 1):
                ws_nuevo.cell(row=1, column=col, value=cabecera)
            
            # Copiar formato de cabeceras (ancho de columnas)
            for col in range(1, len(cabeceras) + 1):
                letra = get_column_letter(col)
                if ws.column_dimensions[letra].width:
                    ws_nuevo.column_dimensions[letra].width = ws.column_dimensions[letra].width
            
            fila_actual = FILA_INICIO_DATOS
            conductores_escritos = set()  # Para evitar duplicados
            
            # 1. Escribir conductores que terminaron (ubicación actualizada, H.LL/H.SA = VACIO)
            for conductor in conductores_terminaron:
                if conductor.nombre.upper() in conductores_escritos:
                    continue
                conductores_escritos.add(conductor.nombre.upper())
                
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['nombre'], value=conductor.nombre)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['ubicacion'], value=conductor.ubicacion)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['hora_llegada'], value="VACIO")
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['hora_salida'], value="VACIO")
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['tractora'], value=conductor.tractora)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['remolque'], value=conductor.remolque)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['zona'], value=conductor.zona)
                ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['telefono'], value=conductor.telefono)
                fila_actual += 1
            
            # 2. Escribir viajes pendientes CON sus conductores
            for viaje in viajes_pendientes:
                transportista = viaje.datos.get('transportista', '').strip()
                
                # Buscar datos del conductor en el Excel original (si tiene transportista)
                if transportista and transportista.upper() not in conductores_escritos:
                    for fila in range(FILA_INICIO_DATOS, ws.max_row + 1):
                        nombre = ws.cell(row=fila, column=COL_CONDUCTOR['nombre']).value
                        if nombre and str(nombre).strip().upper() == transportista.upper():
                            conductores_escritos.add(transportista.upper())
                            
                            ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['nombre'], 
                                         value=str(nombre).strip())
                            ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['ubicacion'], 
                                         value=str(ws.cell(row=fila, column=COL_CONDUCTOR['ubicacion']).value or '').strip())
                            ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['hora_llegada'], value="")
                            ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['hora_salida'], value="")
                            ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['tractora'], 
                                         value=str(ws.cell(row=fila, column=COL_CONDUCTOR['tractora']).value or '').strip())
                            ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['remolque'], 
                                         value=str(ws.cell(row=fila, column=COL_CONDUCTOR['remolque']).value or '').strip())
                            ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['zona'], 
                                         value=str(ws.cell(row=fila, column=COL_CONDUCTOR['zona']).value or '').strip())
                            ws_nuevo.cell(row=fila_actual, column=COL_CONDUCTOR['telefono'], 
                                         value=str(ws.cell(row=fila, column=COL_CONDUCTOR['telefono']).value or '').strip())
                            break
                
                # Escribir datos del viaje (sin horas de registro)
                for campo, columna in COL_VIAJE.items():
                    valor = viaje.datos.get(campo, '')
                    # Limpiar horas de registro para el nuevo día
                    if campo in ['hora_llegada_carga', 'hora_salida_carga', 
                                'hora_llegada_descarga', 'hora_salida_descarga']:
                        valor = ''
                    ws_nuevo.cell(row=fila_actual, column=columna, value=valor)
                
                fila_actual += 1
            
            # Guardar nuevo Excel
            wb_nuevo.save(ruta_nueva)
            wb_nuevo.close()
            wb.close()
            
            logger.info(f"[CIERRE] ✅ Nuevo Excel creado: {nombre_nuevo}")
            logger.info(f"[CIERRE]    - {len(conductores_escritos)} conductores exportados")
            logger.info(f"[CIERRE]    - {len(viajes_pendientes)} viajes pendientes exportados")
            
            return nombre_nuevo, ruta_nueva
            
        except Exception as e:
            logger.error(f"[CIERRE] Error creando Excel nuevo: {e}")
            raise
    
    # ============================================================
    # SINCRONIZAR BD CON NUEVO EXCEL
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
    # EJECUTAR CIERRE COMPLETO
    # ============================================================
    
    def ejecutar_cierre(self, fecha_nuevo: datetime = None) -> Dict:
        """
        Ejecuta el cierre de día completo.
        
        Args:
            fecha_nuevo: Fecha para el nuevo Excel (default: hoy)
        
        Returns:
            Dict con resultado del cierre
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
            
            # Paso 1: Analizar Excel actual
            logger.info("[CIERRE] Paso 1: Analizando Excel actual...")
            analisis = self.analizar_excel_actual()
            
            if 'error' in analisis:
                resultado['errores'].append(f"Error analizando: {analisis['error']}")
                return resultado
            
            resultado['conductores_exportados'] = len(analisis['conductores_terminaron'])
            resultado['viajes_pendientes'] = len(analisis['viajes_pendientes'])
            resultado['viajes_completados'] = len(analisis['viajes_completados'])
            
            # Paso 2: Crear nuevo Excel
            logger.info("[CIERRE] Paso 2: Creando nuevo Excel...")
            nombre_nuevo, ruta_nueva = self.crear_excel_nuevo(fecha_nuevo)
            resultado['excel_nuevo'] = nombre_nuevo
            
            # Paso 3: Renombrar Excel actual a histórico (si no tiene fecha en el nombre)
            excel_actual_nombre = os.path.basename(self.excel_path)
            if not excel_actual_nombre.startswith("RUTAS_"):
                # Renombrar a RUTAS_<fecha_ayer>.xlsx
                fecha_ayer = datetime.now() - timedelta(days=1)
                nombre_historico = self.generar_nombre_excel(fecha_ayer)
                ruta_historico = os.path.join(self.directorio, nombre_historico)
                
                if not os.path.exists(ruta_historico):
                    shutil.copy2(self.excel_path, ruta_historico)
                    logger.info(f"[CIERRE] Excel anterior guardado como: {nombre_historico}")
            
            # Paso 4: Copiar nuevo Excel a ruta activa
            logger.info("[CIERRE] Paso 4: Activando nuevo Excel...")
            shutil.copy2(ruta_nueva, self.excel_path)
            
            # Paso 5: Actualizar archivo de Excel activo
            self.establecer_excel_activo(nombre_nuevo)
            
            # Paso 6: Sincronizar BD
            logger.info("[CIERRE] Paso 5: Sincronizando BD...")
            sync_resultado = self.sincronizar_bd_nuevo_excel(self.excel_path)
            resultado['bd_sincronizada'] = sync_resultado.get('exito', False)
            
            # Paso 7: Subir a Drive
            if self.subir_drive:
                logger.info("[CIERRE] Paso 6: Subiendo a Drive...")
                try:
                    self.subir_drive()
                    resultado['drive_subido'] = True
                except Exception as e:
                    resultado['errores'].append(f"Error subiendo a Drive: {e}")
            
            resultado['exito'] = True
            
            logger.info("[CIERRE] ═══════════════════════════════════════")
            logger.info("[CIERRE] ✅ CIERRE DE DÍA COMPLETADO")
            logger.info(f"[CIERRE]    Excel nuevo: {nombre_nuevo}")
            logger.info(f"[CIERRE]    Conductores: {resultado['conductores_exportados']}")
            logger.info(f"[CIERRE]    Viajes pendientes: {resultado['viajes_pendientes']}")
            logger.info("[CIERRE] ═══════════════════════════════════════")
            
            return resultado
            
        except Exception as e:
            logger.error(f"[CIERRE] ❌ Error en cierre: {e}")
            resultado['errores'].append(str(e))
            return resultado
    
    # ============================================================
    # VERIFICAR SI ES SEGURO CERRAR
    # ============================================================
    
    def verificar_cierre_seguro(self) -> Dict:
        """
        Verifica si es seguro hacer el cierre.
        
        Returns:
            Dict con info de seguridad
        """
        analisis = self.analizar_excel_actual()
        
        # Verificar si ya existe Excel del día
        nombre_hoy = self.generar_nombre_excel()
        ruta_hoy = os.path.join(self.directorio, nombre_hoy)
        excel_hoy_existe = os.path.exists(ruta_hoy)
        
        return {
            'seguro': not excel_hoy_existe,
            'excel_hoy_existe': excel_hoy_existe,
            'nombre_excel_hoy': nombre_hoy,
            'conductores_terminaron': len(analisis.get('conductores_terminaron', [])),
            'viajes_pendientes': len(analisis.get('viajes_pendientes', [])),
            'viajes_completados': len(analisis.get('viajes_completados', [])),
            'advertencia': "Ya existe el Excel del día de hoy" if excel_hoy_existe else None
        }
    
    # ============================================================
    # OBTENER EXCELS HISTÓRICOS
    # ============================================================
    
    def listar_excels_historicos(self, limite: int = 7) -> List[Dict]:
        """Lista los Excels históricos disponibles"""
        excels = []
        
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
        
        # Ordenar por fecha descendente
        excels.sort(key=lambda x: x['fecha_modificacion'], reverse=True)
        
        return excels[:limite]


# ============================================================
# FUNCIÓN PARA INTEGRAR EN BOT
# ============================================================

def crear_cierre_dia(excel_path: str, db_path: str, 
                     subir_drive_func=None, descargar_drive_func=None):
    """
    Crea una instancia del módulo de cierre de día.
    
    Uso en bot_transporte.py:
    
        from cierre_dia import crear_cierre_dia
        
        cierre = crear_cierre_dia(
            config.EXCEL_EMPRESA,
            config.DB_PATH,
            subir_excel_a_drive,
            descargar_excel_desde_drive
        )
    """
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
    """
    Uso con cron:
    0 8 * * * cd /root/bot-transporte/Botttttt && /root/bot-transporte/venv/bin/python3 cierre_dia.py >> /var/log/cierre_dia.log 2>&1
    """
    import logging
    from dotenv import load_dotenv
    
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Cargar variables de entorno
    load_dotenv()
    
    EXCEL_EMPRESA = os.getenv("EXCEL_EMPRESA", "PRUEBO.xlsx")
    DB_PATH = os.getenv("DB_PATH", "logistica.db")
    DRIVE_ENABLED = os.getenv("DRIVE_ENABLED", "false").lower() == "true"
    
    # Función para subir a Drive
    subir_drive = None
    if DRIVE_ENABLED:
        try:
            from sync_automatico import subir_excel_a_drive, inicializar_drive
            if inicializar_drive():
                subir_drive = subir_excel_a_drive
        except Exception as e:
            logger.warning(f"No se pudo configurar Drive: {e}")
    
    # Ejecutar cierre
    cierre = CierreDia(
        excel_path=EXCEL_EMPRESA,
        db_path=DB_PATH,
        subir_drive_func=subir_drive
    )
    
    # Verificar si es seguro
    verificacion = cierre.verificar_cierre_seguro()
    
    if not verificacion['seguro']:
        logger.warning(f"[CIERRE] ⚠️ {verificacion['advertencia']}")
        logger.warning("[CIERRE] Cierre automático cancelado. Use --forzar para ignorar.")
        
        if len(sys.argv) > 1 and sys.argv[1] == "--forzar":
            logger.info("[CIERRE] Forzando cierre...")
        else:
            sys.exit(1)
    
    # Ejecutar
    resultado = cierre.ejecutar_cierre()
    
    if resultado['exito']:
        logger.info("[CIERRE] ✅ Cierre automático completado exitosamente")
        sys.exit(0)
    else:
        logger.error(f"[CIERRE] ❌ Errores: {resultado['errores']}")
        sys.exit(1)
