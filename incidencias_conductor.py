"""
INCIDENCIAS DE CONDUCTOR v1.0
==============================
Permite a los conductores reportar incidencias que se notifican al admin.

Tipos de incidencia:
- 🔧 Avería
- ⏰ Retraso
- 🚨 Accidente
- 📦 Problema con carga
- ❓ Otro

Flujo:
1. Conductor pulsa "⚠️ Incidencia"
2. Selecciona tipo de incidencia
3. Escribe descripción (opcional)
4. Confirma
5. Admin recibe notificación inmediata
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, Optional, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

logger = logging.getLogger(__name__)

# ============================================================
# ESTADOS DEL CONVERSATION HANDLER
# ============================================================
INC_TIPO = 300
INC_DESCRIPCION = 301
INC_CONFIRMAR = 302
INC_LLAMAR = 303  # Después de confirmar, muestra botón de llamar

# ============================================================
# TIPOS DE INCIDENCIA
# ============================================================
TIPOS_INCIDENCIA = {
    'averia': ('🔧', 'Avería mecánica'),
    'retraso': ('⏰', 'Retraso'),
    'accidente': ('🚨', 'Accidente'),
    'carga': ('📦', 'Problema con carga'),
    'otro': ('❓', 'Otro'),
}

# ============================================================
# SUPERVISORES POR ZONA
# ============================================================
SUPERVISORES_ZONA = {
    'ZONA NORTE': {'nombre': 'Cris', 'telefono': '693404714'},
    'ZONA CORTOS NORTE': {'nombre': 'Pedro', 'telefono': '623456789'},
    'ZONA RESTO NACIONAL': {'nombre': 'María', 'telefono': '634567890'},
    'ZONA MURCIA': {'nombre': 'Luis', 'telefono': '645678901'},
}

# Supervisor por defecto si no se encuentra la zona
SUPERVISOR_DEFAULT = {'nombre': 'Cris', 'telefono': '693404714'}

# ============================================================
# SUPERVISORES POR ZONA
# ============================================================
SUPERVISORES_ZONA = {
    'ZONA NORTE': {'nombre': 'Cris', 'telefono': '693404714'},
    'ZONA CORTOS NORTE': {'nombre': 'Pedro', 'telefono': '623456789'},
    'ZONA RESTO NACIONAL': {'nombre': 'María', 'telefono': '634567890'},
    'ZONA MURCIA': {'nombre': 'Luis', 'telefono': '645678901'},
}


class IncidenciasConductor:
    """
    Gestiona el reporte de incidencias de conductores.
    """
    
    def __init__(self, db_path: str, bot=None, admin_ids: List[int] = None):
        """
        Args:
            db_path: Ruta a la base de datos
            bot: Bot de Telegram para enviar notificaciones
            admin_ids: Lista de IDs de admins a notificar
        """
        self.db_path = db_path
        self.bot = bot
        self.admin_ids = admin_ids or []
        logger.info("[INCIDENCIAS] Módulo de incidencias v1.0 inicializado")
    
    def get_conversation_handler(self):
        """Devuelve el ConversationHandler para incidencias"""
        return ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^⚠️ Incidencia$"), self.inicio),
            ],
            states={
                INC_TIPO: [
                    CallbackQueryHandler(self.seleccionar_tipo, pattern="^inc_tipo_"),
                    CallbackQueryHandler(self.cancelar_callback, pattern="^inc_cancelar$"),
                ],
                INC_DESCRIPCION: [
                    MessageHandler(filters.Regex("^⏭️ Omitir$"), self.omitir_descripcion),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.guardar_descripcion),
                ],
                INC_CONFIRMAR: [
                    CallbackQueryHandler(self.confirmar_incidencia, pattern="^inc_confirmar$"),
                    CallbackQueryHandler(self.cancelar_callback, pattern="^inc_cancelar$"),
                ],
                INC_LLAMAR: [
                    CallbackQueryHandler(self.finalizar, pattern="^inc_listo$"),
                ],
            },
            fallbacks=[
                CommandHandler("cancelar", self.cancelar),
                MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
            ],
        )
    
    # ============================================================
    # OBTENER DATOS DEL CONDUCTOR
    # ============================================================
    
    def _obtener_conductor(self, telegram_id: int) -> Optional[Dict]:
        """Obtiene datos del conductor"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM conductores_empresa 
                WHERE telegram_id = ?
            """, (telegram_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
            
        except Exception as e:
            logger.error(f"[INCIDENCIAS] Error obteniendo conductor: {e}")
            return None
    
    def _obtener_viaje_activo(self, nombre_conductor: str) -> Optional[Dict]:
        """Obtiene el viaje activo del conductor"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM viajes_empresa 
                WHERE conductor_asignado LIKE ? 
                AND estado IN ('pendiente', 'en_ruta', 'asignado')
                ORDER BY id DESC
                LIMIT 1
            """, (f"%{nombre_conductor}%",))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
            
        except Exception as e:
            logger.error(f"[INCIDENCIAS] Error obteniendo viaje: {e}")
            return None
    
    def _obtener_supervisor(self, zona: str) -> Dict:
        """Obtiene el supervisor correspondiente a una zona"""
        if not zona:
            return SUPERVISOR_DEFAULT
        
        zona_upper = zona.strip().upper()
        
        # Buscar coincidencia exacta o parcial
        for zona_key, supervisor in SUPERVISORES_ZONA.items():
            if zona_key in zona_upper or zona_upper in zona_key:
                return supervisor
        
        return SUPERVISOR_DEFAULT
    
    # ============================================================
    # GUARDAR INCIDENCIA EN BD
    # ============================================================
    
    def _guardar_incidencia(self, conductor: Dict, tipo: str, descripcion: str, viaje: Dict = None) -> bool:
        """Guarda la incidencia en la BD"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Crear tabla si no existe
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS incidencias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    conductor TEXT,
                    telegram_id INTEGER,
                    tipo TEXT,
                    descripcion TEXT,
                    viaje_id INTEGER,
                    cliente TEXT,
                    ruta TEXT,
                    estado TEXT DEFAULT 'pendiente'
                )
            """)
            
            viaje_id = viaje.get('id') if viaje else None
            cliente = viaje.get('cliente', '') if viaje else ''
            ruta = f"{viaje.get('lugar_carga', '')} → {viaje.get('lugar_entrega', '')}" if viaje else ''
            
            cursor.execute("""
                INSERT INTO incidencias (conductor, telegram_id, tipo, descripcion, viaje_id, cliente, ruta)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                conductor.get('nombre', ''),
                conductor.get('telegram_id'),
                tipo,
                descripcion,
                viaje_id,
                cliente,
                ruta
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"[INCIDENCIAS] Incidencia guardada: {conductor.get('nombre')} - {tipo}")
            return True
            
        except Exception as e:
            logger.error(f"[INCIDENCIAS] Error guardando incidencia: {e}")
            return False
    
    # ============================================================
    # NOTIFICAR A ADMINS
    # ============================================================
    
    async def _notificar_admins(self, conductor: Dict, tipo: str, descripcion: str, viaje: Dict = None):
        """Notifica a todos los admins sobre la incidencia"""
        if not self.bot or not self.admin_ids:
            logger.warning("[INCIDENCIAS] Bot o admin_ids no configurados")
            return
        
        emoji, tipo_texto = TIPOS_INCIDENCIA.get(tipo, ('⚠️', tipo))
        hora = datetime.now().strftime("%H:%M")
        
        mensaje = f"🚨 *INCIDENCIA REPORTADA*\n\n"
        mensaje += f"👤 *{conductor.get('nombre', 'N/A')}*\n"
        mensaje += f"🚛 {conductor.get('tractora', 'N/A')}\n"
        mensaje += f"⏰ {hora}\n\n"
        mensaje += f"{emoji} *Tipo:* {tipo_texto}\n"
        
        if descripcion:
            mensaje += f"📝 *Detalle:* {descripcion}\n"
        
        if viaje:
            mensaje += f"\n{'─'*20}\n"
            mensaje += f"📦 *Viaje activo:*\n"
            mensaje += f"🏢 {viaje.get('cliente', 'N/A')}\n"
            mensaje += f"📍 {viaje.get('lugar_carga', '?')} → {viaje.get('lugar_entrega', '?')}\n"
        
        # Botón para llamar al conductor
        telefono = conductor.get('telefono', '')
        if telefono:
            mensaje += f"\n📞 Teléfono: {telefono}"
        
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=mensaje,
                    parse_mode="Markdown"
                )
                logger.info(f"[INCIDENCIAS] Admin {admin_id} notificado")
            except Exception as e:
                logger.error(f"[INCIDENCIAS] Error notificando admin {admin_id}: {e}")
    
    # ============================================================
    # HANDLERS DEL CONVERSATION
    # ============================================================
    
    async def inicio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia el flujo de reporte de incidencia"""
        telegram_id = update.effective_user.id
        
        conductor = self._obtener_conductor(telegram_id)
        
        if not conductor:
            from teclados import teclado_conductor
            await update.message.reply_text(
                "❌ No estás vinculado como conductor.\n"
                "Usa /vincular TU_NOMBRE para vincularte.",
                reply_markup=teclado_conductor
            )
            return ConversationHandler.END
        
        context.user_data['conductor'] = conductor
        
        # Obtener viaje activo (si tiene)
        viaje = self._obtener_viaje_activo(conductor.get('nombre', ''))
        if viaje:
            context.user_data['viaje'] = viaje
        
        texto = (
            f"⚠️ *REPORTAR INCIDENCIA*\n\n"
            f"👤 {conductor.get('nombre', 'N/A')}\n"
        )
        
        if viaje:
            texto += f"📦 Viaje: {viaje.get('cliente', 'N/A')}\n"
            texto += f"📍 {viaje.get('lugar_carga', '?')} → {viaje.get('lugar_entrega', '?')}\n"
        
        texto += "\n¿Qué tipo de incidencia quieres reportar?"
        
        keyboard = [
            [
                InlineKeyboardButton("🔧 Avería", callback_data="inc_tipo_averia"),
                InlineKeyboardButton("⏰ Retraso", callback_data="inc_tipo_retraso"),
            ],
            [
                InlineKeyboardButton("🚨 Accidente", callback_data="inc_tipo_accidente"),
                InlineKeyboardButton("📦 Problema carga", callback_data="inc_tipo_carga"),
            ],
            [
                InlineKeyboardButton("❓ Otro", callback_data="inc_tipo_otro"),
            ],
            [
                InlineKeyboardButton("❌ Cancelar", callback_data="inc_cancelar"),
            ]
        ]
        
        await update.message.reply_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return INC_TIPO
    
    async def seleccionar_tipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cuando selecciona tipo de incidencia"""
        query = update.callback_query
        await query.answer()
        
        tipo = query.data.replace("inc_tipo_", "")
        context.user_data['tipo_incidencia'] = tipo
        
        emoji, tipo_texto = TIPOS_INCIDENCIA.get(tipo, ('⚠️', tipo))
        
        from telegram import ReplyKeyboardMarkup
        
        await query.edit_message_text(
            f"{emoji} *{tipo_texto.upper()}*\n\n"
            f"Escribe una descripción breve de lo ocurrido.\n\n"
            f"_O pulsa ⏭️ Omitir si no quieres añadir detalles._",
            parse_mode="Markdown"
        )
        
        # Teclado con opción de omitir
        teclado_descripcion = ReplyKeyboardMarkup(
            [["⏭️ Omitir"], ["❌ Cancelar"]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await query.message.reply_text(
            "Escribe la descripción:",
            reply_markup=teclado_descripcion
        )
        
        return INC_DESCRIPCION
    
    async def guardar_descripcion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda la descripción y pide confirmación"""
        descripcion = update.message.text
        context.user_data['descripcion'] = descripcion
        
        return await self._mostrar_confirmacion(update, context)
    
    async def omitir_descripcion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Omite la descripción"""
        context.user_data['descripcion'] = ''
        
        return await self._mostrar_confirmacion(update, context)
    
    async def _mostrar_confirmacion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra resumen y pide confirmación"""
        conductor = context.user_data.get('conductor', {})
        viaje = context.user_data.get('viaje')
        tipo = context.user_data.get('tipo_incidencia', 'otro')
        descripcion = context.user_data.get('descripcion', '')
        
        emoji, tipo_texto = TIPOS_INCIDENCIA.get(tipo, ('⚠️', tipo))
        
        texto = (
            f"📋 *CONFIRMAR INCIDENCIA*\n\n"
            f"👤 {conductor.get('nombre', 'N/A')}\n"
            f"{emoji} *{tipo_texto}*\n"
        )
        
        if descripcion:
            texto += f"📝 {descripcion}\n"
        
        if viaje:
            texto += f"\n📦 Viaje: {viaje.get('cliente', 'N/A')}\n"
        
        texto += "\n¿Confirmar reporte?"
        
        keyboard = [
            [InlineKeyboardButton("✅ Confirmar", callback_data="inc_confirmar")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="inc_cancelar")]
        ]
        
        await update.message.reply_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return INC_CONFIRMAR
    
    async def confirmar_incidencia(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirma y envía la incidencia"""
        query = update.callback_query
        await query.answer()
        
        conductor = context.user_data.get('conductor', {})
        viaje = context.user_data.get('viaje')
        tipo = context.user_data.get('tipo_incidencia', 'otro')
        descripcion = context.user_data.get('descripcion', '')
        
        # Guardar en BD
        self._guardar_incidencia(conductor, tipo, descripcion, viaje)
        
        # Notificar admins
        await self._notificar_admins(conductor, tipo, descripcion, viaje)
        
        emoji, tipo_texto = TIPOS_INCIDENCIA.get(tipo, ('⚠️', tipo))
        
        # Detectar zona y supervisor
        zona = self._detectar_zona_conductor(conductor, viaje)
        supervisor = SUPERVISORES_ZONA.get(zona)
        
        texto = (
            f"✅ *INCIDENCIA REPORTADA*\n\n"
            f"{emoji} {tipo_texto}\n\n"
            f"Los responsables han sido notificados.\n"
        )
        
        if supervisor:
            texto += f"\n📍 Zona: *{zona}*"
            texto += f"\n📞 Supervisor: *{supervisor['nombre']}*"
        
        # Crear botón de llamada
        keyboard = []
        if supervisor:
            keyboard.append([
                InlineKeyboardButton(
                    f"📞 Llamar a {supervisor['nombre']}", 
                    url=f"tel:{supervisor['telefono']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("✅ Listo", callback_data="inc_listo")])
        
        await query.edit_message_text(
            texto, 
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # No limpiar context.user_data aquí, se limpia en finalizar
        return INC_LLAMAR
    
    async def finalizar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Finaliza el reporte después de mostrar botón de llamar"""
        query = update.callback_query
        await query.answer()
        
        from teclados import teclado_conductor
        
        await query.edit_message_text(
            "✅ Incidencia gestionada.\n\n¿Qué más necesitas?"
        )
        
        await query.message.reply_text(
            "Usa el menú:",
            reply_markup=teclado_conductor
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    def _detectar_zona_conductor(self, conductor: Dict, viaje: Dict = None) -> str:
        """Detecta la zona del conductor"""
        # Primero intentar desde el conductor
        zona = conductor.get('zona', '')
        if zona:
            # Normalizar zona
            zona_upper = zona.strip().upper()
            for zona_key in SUPERVISORES_ZONA.keys():
                if zona_key in zona_upper or zona_upper in zona_key:
                    return zona_key
        
        # Si no, intentar desde el viaje
        if viaje:
            zona_viaje = viaje.get('zona', '')
            if zona_viaje:
                zona_upper = zona_viaje.strip().upper()
                for zona_key in SUPERVISORES_ZONA.keys():
                    if zona_key in zona_upper or zona_upper in zona_key:
                        return zona_key
        
        # Por defecto, ZONA NORTE
        return 'ZONA NORTE'
    
    async def cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela el reporte (mensaje)"""
        context.user_data.clear()
        
        from teclados import teclado_conductor
        
        await update.message.reply_text(
            "❌ Reporte cancelado.",
            reply_markup=teclado_conductor
        )
        
        return ConversationHandler.END
    
    async def cancelar_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela el reporte (callback)"""
        query = update.callback_query
        await query.answer()
        
        context.user_data.clear()
        
        from teclados import teclado_conductor
        
        await query.edit_message_text("❌ Reporte cancelado.")
        await query.message.reply_text(
            "¿Qué más necesitas?",
            reply_markup=teclado_conductor
        )
        
        return ConversationHandler.END


# ============================================================
# FUNCIÓN PARA INTEGRAR EN BOT_TRANSPORTE.PY
# ============================================================

def crear_incidencias_conductor(db_path: str, bot=None, admin_ids: List[int] = None):
    """
    Crea una instancia del módulo de incidencias.
    
    Uso en bot_transporte.py:
    
        from incidencias_conductor import crear_incidencias_conductor
        
        # En main():
        incidencias = crear_incidencias_conductor(
            config.DB_PATH,
            app.bot,
            config.ADMIN_IDS  # Lista de IDs de admins
        )
        app.add_handler(incidencias.get_conversation_handler())
    """
    return IncidenciasConductor(
        db_path=db_path,
        bot=bot,
        admin_ids=admin_ids
    )
