"""
EXTRACTOR DE TELÉFONOS DE EXCEL
================================
Extrae los teléfonos de las notas/comentarios del Excel de la empresa
y los asocia a cada conductor.

Uso:
    from extractor_telefonos import extraer_telefonos_excel, actualizar_telefonos_bd
    
    telefonos = extraer_telefonos_excel("PRUEBO.xlsx")
    actualizar_telefonos_bd(db_path, telefonos)
"""

import openpyxl
import re
import sqlite3
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def extraer_telefonos_excel(archivo_excel: str) -> Dict[str, str]:
    """
    Extrae teléfonos de las notas del Excel.
    
    Las notas están en la columna TRANSPORTISTA (columna 5)
    con formato: "Tel. empresa: 611213412"
    
    Args:
        archivo_excel: Ruta al archivo Excel
    
    Returns:
        Dict {nombre_conductor: telefono}
    """
    conductores_telefonos = {}
    
    if not Path(archivo_excel).exists():
        logger.error(f"[TELEFONOS] Archivo no encontrado: {archivo_excel}")
        return conductores_telefonos
    
    try:
        wb = openpyxl.load_workbook(archivo_excel)
        ws = wb.active
        
        # Buscar en columna 5 (TRANSPORTISTA)
        for row in range(3, 100):  # Empezar desde fila 3 (datos)
            cell = ws.cell(row=row, column=5)
            nombre = cell.value
            
            if not nombre:
                continue
            
            nombre_str = str(nombre).strip().upper()
            
            # Ignorar headers
            if nombre_str in ['TRANSPORTISTA', 'NAN', '', 'NONE']:
                continue
            
            if cell.comment:
                nota = cell.comment.text
                telefono = _extraer_telefono_de_nota(nota)
                
                if telefono:
                    conductores_telefonos[nombre_str] = telefono
                    logger.debug(f"[TELEFONOS] {nombre_str} → {telefono}")
        
        wb.close()
        logger.info(f"[TELEFONOS] Extraídos {len(conductores_telefonos)} teléfonos")
        
    except Exception as e:
        logger.error(f"[TELEFONOS] Error leyendo Excel: {e}")
    
    return conductores_telefonos


def _extraer_telefono_de_nota(nota: str) -> Optional[str]:
    """
    Extrae el teléfono de una nota.
    
    Busca patrones como:
    - "Tel. empresa: 611213412"
    - "Tel: 611213412"
    - "Teléfono: 611213412"
    - O cualquier número de 9 dígitos que empiece por 6 o 7
    """
    if not nota:
        return None
    
    # Patrón 1: "Tel. empresa: NUMERO" o "Tel: NUMERO"
    patron1 = r'Tel[éefonoempresa.\s]*[:\s]*(\d{9})'
    match = re.search(patron1, nota, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Patrón 2: Cualquier móvil español (empieza por 6 o 7)
    patron2 = r'\b([67]\d{8})\b'
    match = re.search(patron2, nota)
    if match:
        return match.group(1)
    
    return None


def actualizar_telefonos_bd(db_path: str, telefonos: Dict[str, str]) -> int:
    """
    Actualiza los teléfonos en la base de datos.
    
    Args:
        db_path: Ruta a la base de datos SQLite
        telefonos: Dict {nombre_conductor: telefono}
    
    Returns:
        Número de registros actualizados
    """
    if not telefonos:
        return 0
    
    actualizados = 0
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        for nombre, telefono in telefonos.items():
            # Actualizar conductor que coincida con el nombre
            cursor.execute("""
                UPDATE conductores_empresa 
                SET telefono = ? 
                WHERE UPPER(nombre) LIKE ?
            """, (telefono, f"%{nombre}%"))
            
            if cursor.rowcount > 0:
                actualizados += cursor.rowcount
                logger.debug(f"[TELEFONOS] Actualizado {nombre} → {telefono}")
        
        conn.commit()
        conn.close()
        
        logger.info(f"[TELEFONOS] {actualizados} conductores actualizados con teléfono")
        
    except Exception as e:
        logger.error(f"[TELEFONOS] Error actualizando BD: {e}")
    
    return actualizados


def sincronizar_telefonos(archivo_excel: str, db_path: str) -> Dict:
    """
    Función principal: extrae teléfonos del Excel y actualiza la BD.
    
    Args:
        archivo_excel: Ruta al Excel de la empresa
        db_path: Ruta a la base de datos
    
    Returns:
        Dict con resultado de la sincronización
    """
    logger.info("[TELEFONOS] Iniciando sincronización de teléfonos...")
    
    # Extraer teléfonos
    telefonos = extraer_telefonos_excel(archivo_excel)
    
    if not telefonos:
        return {
            "exito": False,
            "mensaje": "No se encontraron teléfonos en las notas",
            "telefonos_encontrados": 0,
            "actualizados": 0
        }
    
    # Actualizar BD
    actualizados = actualizar_telefonos_bd(db_path, telefonos)
    
    return {
        "exito": True,
        "mensaje": f"Sincronización completada",
        "telefonos_encontrados": len(telefonos),
        "actualizados": actualizados,
        "detalle": telefonos
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("="*60)
    print("TEST EXTRACTOR DE TELÉFONOS")
    print("="*60)
    
    telefonos = extraer_telefonos_excel("PRUEBO.xlsx")
    
    print(f"\nTeléfonos encontrados: {len(telefonos)}")
    for nombre, tel in telefonos.items():
        print(f"   {nombre}: {tel}")
