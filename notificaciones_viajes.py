"""
NOTIFICACIONES DE VIAJES
=========================
Detecta viajes nuevos y notifica automáticamente al conductor.

Uso:
    from notificaciones_viajes import NotificadorViajes
    
    notificador = NotificadorViajes(db_path, bot)
    await notificador.verificar_y_notificar()
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class NotificadorViajes:
    """
    Detecta y notifica viajes nuevos a los conductores.
    """
    
    def __init__(self, db_path: str, bot=None):
        """
        Args:
            db_path: Ruta a la base de datos SQLite
            bot: Bot de Telegram (para enviar mensajes)
        """
        self.db_path = db_path
        self.bot = bot
        
        # Almacena IDs de viajes ya notificados (conductor|cliente|carga|descarga)
        self._viajes_notificados: Set[str] = set()
        
        # Cargar viajes existentes al iniciar (para no notificar los viejos)
        self._cargar_viajes_existentes()
        
        logger.info("[NOTIFICADOR] Inicializado")
    
    def _cargar_viajes_existentes(self):
        """Carga los viajes existentes para no notificar los viejos al arrancar"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT conductor_asignado, cliente, lugar_carga, lugar_entrega 
                FROM viajes_empresa 
                WHERE conductor_asignado IS NOT NULL AND conductor_asignado != ''
            """)
            
            for row in cursor.fetchall():
                viaje_id = self._generar_viaje_id(dict(row))
                self._viajes_notificados.add(viaje_id)
            
            conn.close()
            logger.info(f"[NOTIFICADOR] {len(self._viajes_notificados)} viajes existentes cargados")
            
        except Exception as e:
            logger.error(f"[NOTIFICADOR] Error cargando viajes: {e}")
    
    def _generar_viaje_id(self, viaje: Dict) -> str:
        """Genera un ID único para un viaje"""
        conductor = (viaje.get('conductor_asignado') or '').strip().upper()
        cliente = (viaje.get('cliente') or '').strip().upper()
        carga = (viaje.get('lugar_carga') or '').strip().upper()
        descarga = (viaje.get('lugar_entrega') or '').strip().upper()
        return f"{conductor}|{cliente}|{carga}|{descarga}"
    
    def _obtener_telegram_id(self, nombre_conductor: str) -> Optional[int]:
        """Obtiene el telegram_id de un conductor por su nombre"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT telegram_id FROM conductores_empresa WHERE nombre LIKE ?",
                (f"%{nombre_conductor}%",)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row['telegram_id']:
                return row['telegram_id']
            return None
            
        except Exception as e:
            logger.error(f"[NOTIFICADOR] Error buscando telegram_id: {e}")
            return None
    
    def _generar_mensaje_viaje(self, viaje: Dict) -> str:
        """Genera el mensaje de notificación para un viaje nuevo"""
        cliente = viaje.get('cliente', 'N/A')
        mercancia = viaje.get('mercancia', 'N/A')
        lugar_carga = viaje.get('lugar_carga', '?')
        lugar_entrega = viaje.get('lugar_entrega', '?')
        km = viaje.get('km', 0) or 0
        intercambio = viaje.get('intercambio', '')
        
        mensaje = "🚛 NUEVO VIAJE ASIGNADO\n\n"
        mensaje += f"📦 {cliente} - {mercancia}\n"
        mensaje += f"📍 {lugar_carga} → {lugar_entrega}\n"
        mensaje += f"📏 {km} km\n"
        
        # Mostrar si hay intercambio de palés
        if intercambio and str(intercambio).upper().strip() == 'SI':
            mensaje += f"🔄 Intercambio de palés\n"
        
        mensaje += "\nPulsa \"🚛 Mis viajes\" para ver detalles"
        
        return mensaje
    
    def detectar_viajes_nuevos(self) -> List[Dict]:
        """
        Detecta viajes nuevos comparando con los ya notificados.
        
        Returns:
            Lista de viajes nuevos
        """
        viajes_nuevos = []
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM viajes_empresa 
                WHERE conductor_asignado IS NOT NULL AND conductor_asignado != ''
            """)
            
            for row in cursor.fetchall():
                viaje = dict(row)
                viaje_id = self._generar_viaje_id(viaje)
                
                if viaje_id not in self._viajes_notificados:
                    viajes_nuevos.append(viaje)
                    # Marcar como notificado
                    self._viajes_notificados.add(viaje_id)
                    logger.info(f"[NOTIFICADOR] Nuevo viaje detectado: {viaje_id}")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"[NOTIFICADOR] Error detectando viajes: {e}")
        
        return viajes_nuevos
    
    async def notificar_viaje(self, viaje: Dict) -> bool:
        """
        Envía notificación de un viaje al conductor.
        
        Args:
            viaje: Datos del viaje
        
        Returns:
            True si se envió correctamente
        """
        if not self.bot:
            logger.warning("[NOTIFICADOR] Bot no configurado")
            return False
        
        conductor = viaje.get('conductor_asignado', '')
        telegram_id = self._obtener_telegram_id(conductor)
        
        if not telegram_id:
            logger.warning(f"[NOTIFICADOR] Conductor {conductor} sin telegram_id")
            return False
        
        mensaje = self._generar_mensaje_viaje(viaje)
        
        try:
            await self.bot.send_message(chat_id=telegram_id, text=mensaje)
            logger.info(f"[NOTIFICADOR] Notificación enviada a {conductor} ({telegram_id})")
            return True
        except Exception as e:
            logger.error(f"[NOTIFICADOR] Error enviando notificación: {e}")
            return False
    
    async def verificar_y_notificar(self) -> Dict:
        """
        Función principal: detecta viajes nuevos y notifica a los conductores.
        
        Returns:
            Dict con resultado
        """
        viajes_nuevos = self.detectar_viajes_nuevos()
        
        if not viajes_nuevos:
            return {
                "viajes_nuevos": 0,
                "notificaciones_enviadas": 0
            }
        
        notificaciones_enviadas = 0
        
        for viaje in viajes_nuevos:
            if await self.notificar_viaje(viaje):
                notificaciones_enviadas += 1
        
        logger.info(f"[NOTIFICADOR] {len(viajes_nuevos)} viajes nuevos, {notificaciones_enviadas} notificaciones enviadas")
        
        return {
            "viajes_nuevos": len(viajes_nuevos),
            "notificaciones_enviadas": notificaciones_enviadas
        }


# Variable global para el notificador
notificador_viajes = None


def inicializar_notificador(db_path: str, bot=None) -> NotificadorViajes:
    """Inicializa el notificador global"""
    global notificador_viajes
    notificador_viajes = NotificadorViajes(db_path, bot)
    return notificador_viajes


def obtener_notificador() -> Optional[NotificadorViajes]:
    """Obtiene el notificador global"""
    return notificador_viajes
