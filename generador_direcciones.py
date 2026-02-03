"""
GENERADOR DE DIRECCIONES
=========================
Genera direcciones de carga y descarga automáticamente
basándose en el cliente, lugar de carga y lugar de entrega.

Las direcciones se almacenan en la BD del bot, NO en el Excel de la empresa.
Así la empresa sigue con su Excel original sin columnas extra.

Uso:
    from generador_direcciones import GeneradorDirecciones
    
    generador = GeneradorDirecciones(db_path)
    generador.actualizar_direcciones()
"""

import sqlite3
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# BASE DE DATOS DE DIRECCIONES CONOCIDAS
# ============================================================

# Direcciones de CARGA (por CLIENTE + LUGAR)
DIRECCIONES_CARGA = {
    # HERO
    ("HERO", "CALAHORRA"): "Pol. Ind. de Tejerías, Calle A, 26500 Calahorra, La Rioja",
    ("HERO", "AZAGRA"): "Pol. Ind. de Azagra, Ctra. Estación s/n, 31560 Azagra, Navarra",
    
    # CAMPOFRIO
    ("CAMPOFRIO", "SAN ADRIAN"): "Pol. Ind. San Adrián, Calle del Ebro s/n, 31570 San Adrián, Navarra",
    ("CAMPOFRIO", "TUDELA"): "Pol. Ind. Las Labradas, 31500 Tudela, Navarra",
    
    # GRUPO AN
    ("GRUPO AN", "MELIDA"): "Pol. Ind. de Mélida, Ctra. Caparroso km 2, 31132 Mélida, Navarra",
    ("GRUPO AN", "MÉLIDA"): "Pol. Ind. de Mélida, Ctra. Caparroso km 2, 31132 Mélida, Navarra",
    ("GRUPO AN", "TUDELA"): "Ctra. Zaragoza km 5, 31500 Tudela, Navarra",
    
    # CONGELADOS NAVARRA
    ("CONGELADOS NAVARRA", "TUDELA"): "Pol. Ind. Ciudad Agroalimentaria, 31500 Tudela, Navarra",
    ("CONGELADOS NAVARRA", "PAMPLONA"): "Pol. Ind. Landaben, 31012 Pamplona, Navarra",
    
    # UVESCO
    ("UVESCO", "IRUN"): "Pol. Ind. Ventas, 20305 Irún, Guipúzcoa",
    ("UVESCO", "PAMPLONA"): "Pol. Ind. Mutilva, 31192 Mutilva, Navarra",
    
    # MERCADONA
    ("MERCADONA", "ZARAGOZA"): "Plataforma Logística Plaza, 50197 Zaragoza",
    ("MERCADONA", "BARCELONA"): "ZAL Port, 08039 Barcelona",
    
    # Genéricos por lugar
    ("", "CALAHORRA"): "Pol. Ind. de Tejerías, 26500 Calahorra, La Rioja",
    ("", "SAN ADRIAN"): "Pol. Ind. San Adrián, 31570 San Adrián, Navarra",
    ("", "TUDELA"): "Pol. Ind. Las Labradas, 31500 Tudela, Navarra",
    ("", "MELIDA"): "Pol. Ind. de Mélida, 31132 Mélida, Navarra",
    ("", "MÉLIDA"): "Pol. Ind. de Mélida, 31132 Mélida, Navarra",
}

# Direcciones de DESCARGA (solo por LUGAR DE ENTREGA)
DIRECCIONES_DESCARGA = {
    # Madrid y alrededores
    "TORREJON DE ARDOZ": "Centro Logístico, Pol. Ind. Casablanca, 28850 Torrejón de Ardoz, Madrid",
    "MADRID": "Mercamadrid, 28053 Madrid",
    "GETAFE": "Pol. Ind. Los Ángeles, 28906 Getafe, Madrid",
    
    # Cataluña
    "VIC (BARCELONA)": "Pol. Ind. Malloles, 08500 Vic, Barcelona",
    "VIC": "Pol. Ind. Malloles, 08500 Vic, Barcelona",
    "BARCELONA": "Mercabarna, 08040 Barcelona",
    
    # Murcia
    "ALCANTARILLA": "Pol. Ind. Oeste, 30820 Alcantarilla, Murcia",
    "MURCIA": "Pol. Ind. Oeste, 30169 Murcia",
    "ARCHENA": "Pol. Ind. El Saladar, 30600 Archena, Murcia",
    
    # Extremadura
    "MERIDA": "Pol. Ind. El Prado, Av. Constitución s/n, 06800 Mérida, Badajoz",
    "MÉRIDA": "Pol. Ind. El Prado, Av. Constitución s/n, 06800 Mérida, Badajoz",
    "BADAJOZ": "Pol. Ind. El Nevero, 06006 Badajoz",
    
    # Aragón
    "ZARAGOZA": "Plataforma Logística Plaza, 50197 Zaragoza",
    
    # País Vasco
    "BILBAO": "Mercabilbao, 48970 Basauri, Vizcaya",
    "IRUN": "Pol. Ind. Ventas, 20305 Irún, Guipúzcoa",
    
    # Navarra
    "PAMPLONA": "Pol. Ind. Landaben, 31012 Pamplona, Navarra",
    "TUDELA": "Pol. Ind. Las Labradas, 31500 Tudela, Navarra",
    
    # La Rioja
    "LOGROÑO": "Pol. Ind. El Sequero, 26150 Agoncillo, La Rioja",
    "CALAHORRA": "Pol. Ind. de Tejerías, 26500 Calahorra, La Rioja",
}


class GeneradorDirecciones:
    """
    Genera y actualiza direcciones de carga/descarga en la BD.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._asegurar_columnas()
        logger.info("[DIRECCIONES] Generador inicializado")
    
    def _asegurar_columnas(self):
        """Asegura que existan las columnas de direcciones en la BD"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Añadir columnas si no existen
            try:
                cursor.execute("ALTER TABLE viajes_empresa ADD COLUMN direccion_carga TEXT")
                logger.info("[DIRECCIONES] Columna direccion_carga añadida")
            except sqlite3.OperationalError:
                pass  # Ya existe
            
            try:
                cursor.execute("ALTER TABLE viajes_empresa ADD COLUMN direccion_descarga TEXT")
                logger.info("[DIRECCIONES] Columna direccion_descarga añadida")
            except sqlite3.OperationalError:
                pass  # Ya existe
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"[DIRECCIONES] Error asegurando columnas: {e}")
    
    def obtener_direccion_carga(self, cliente: str, lugar_carga: str) -> str:
        """
        Obtiene la dirección de carga basándose en cliente + lugar.
        
        Args:
            cliente: Nombre del cliente (ej: "HERO")
            lugar_carga: Lugar de carga (ej: "CALAHORRA")
        
        Returns:
            Dirección completa o lugar_carga si no se encuentra
        """
        if not lugar_carga:
            return ""
        
        cliente = (cliente or "").upper().strip()
        lugar = lugar_carga.upper().strip()
        
        # Buscar por cliente + lugar
        direccion = DIRECCIONES_CARGA.get((cliente, lugar))
        if direccion:
            return direccion
        
        # Buscar solo por lugar
        direccion = DIRECCIONES_CARGA.get(("", lugar))
        if direccion:
            return direccion
        
        # Si no se encuentra, devolver el lugar
        return lugar_carga
    
    def obtener_direccion_descarga(self, lugar_entrega: str) -> str:
        """
        Obtiene la dirección de descarga basándose en el lugar de entrega.
        
        Args:
            lugar_entrega: Lugar de entrega (ej: "MERIDA")
        
        Returns:
            Dirección completa o lugar_entrega si no se encuentra
        """
        if not lugar_entrega:
            return ""
        
        lugar = lugar_entrega.upper().strip()
        
        # Buscar dirección
        direccion = DIRECCIONES_DESCARGA.get(lugar)
        if direccion:
            return direccion
        
        # Si no se encuentra, devolver el lugar
        return lugar_entrega
    
    def actualizar_direcciones(self) -> Dict:
        """
        Actualiza las direcciones de todos los viajes en la BD.
        
        Returns:
            Dict con resultado de la actualización
        """
        actualizados = 0
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Obtener todos los viajes
            cursor.execute("""
                SELECT id, cliente, lugar_carga, lugar_entrega, 
                       direccion_carga, direccion_descarga
                FROM viajes_empresa
            """)
            
            viajes = cursor.fetchall()
            
            for viaje in viajes:
                viaje_id = viaje['id']
                cliente = viaje['cliente'] or ""
                lugar_carga = viaje['lugar_carga'] or ""
                lugar_entrega = viaje['lugar_entrega'] or ""
                
                # Generar direcciones
                nueva_dir_carga = self.obtener_direccion_carga(cliente, lugar_carga)
                nueva_dir_descarga = self.obtener_direccion_descarga(lugar_entrega)
                
                # Actualizar si hay cambios
                if nueva_dir_carga or nueva_dir_descarga:
                    cursor.execute("""
                        UPDATE viajes_empresa 
                        SET direccion_carga = ?, direccion_descarga = ?
                        WHERE id = ?
                    """, (nueva_dir_carga, nueva_dir_descarga, viaje_id))
                    actualizados += 1
            
            conn.commit()
            conn.close()
            
            logger.info(f"[DIRECCIONES] {actualizados} viajes actualizados con direcciones")
            
            return {
                "exito": True,
                "actualizados": actualizados
            }
            
        except Exception as e:
            logger.error(f"[DIRECCIONES] Error actualizando direcciones: {e}")
            return {
                "exito": False,
                "error": str(e)
            }
    
    def añadir_direccion_carga(self, cliente: str, lugar: str, direccion: str):
        """Añade una nueva dirección de carga al diccionario"""
        DIRECCIONES_CARGA[(cliente.upper(), lugar.upper())] = direccion
        logger.info(f"[DIRECCIONES] Añadida: {cliente} + {lugar} → {direccion[:30]}...")
    
    def añadir_direccion_descarga(self, lugar: str, direccion: str):
        """Añade una nueva dirección de descarga al diccionario"""
        DIRECCIONES_DESCARGA[lugar.upper()] = direccion
        logger.info(f"[DIRECCIONES] Añadida: {lugar} → {direccion[:30]}...")


# ============================================================
# FUNCIÓN DE CONVENIENCIA
# ============================================================

def sincronizar_direcciones(db_path: str) -> Dict:
    """
    Función de conveniencia para sincronizar direcciones.
    
    Args:
        db_path: Ruta a la base de datos
    
    Returns:
        Dict con resultado
    """
    generador = GeneradorDirecciones(db_path)
    return generador.actualizar_direcciones()


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("="*60)
    print("TEST GENERADOR DE DIRECCIONES")
    print("="*60)
    
    gen = GeneradorDirecciones("test.db")
    
    # Test direcciones de carga
    print("\nDirecciones de CARGA:")
    print(f"   HERO + CALAHORRA: {gen.obtener_direccion_carga('HERO', 'CALAHORRA')}")
    print(f"   GRUPO AN + MELIDA: {gen.obtener_direccion_carga('GRUPO AN', 'MELIDA')}")
    print(f"   DESCONOCIDO + TUDELA: {gen.obtener_direccion_carga('DESCONOCIDO', 'TUDELA')}")
    
    # Test direcciones de descarga
    print("\nDirecciones de DESCARGA:")
    print(f"   MERIDA: {gen.obtener_direccion_descarga('MERIDA')}")
    print(f"   TORREJON DE ARDOZ: {gen.obtener_direccion_descarga('TORREJON DE ARDOZ')}")
    print(f"   DESCONOCIDO: {gen.obtener_direccion_descarga('DESCONOCIDO')}")
