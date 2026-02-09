"""
REGISTROS DE CONDUCTOR v1.0
============================
Permite a los conductores registrar horas de llegada/salida
en puntos de carga y descarga.

Flujo:
1. Conductor pulsa "📝 Registros"
2. Selecciona "📥 Carga" o "📤 Descarga"
3. Selecciona "🚛 Llegada" o "🏁 Salida"
4. Se registra la hora actual en el Excel y se sube a Drive

Columnas Excel:
- Col O (15): HORA LLEGADA carga
- Col P (16): HORA SALIDA carga
- Col R (18): HORA LLEGADA descarga
- Col S (19): HORA SALIDA descarga
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

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
REG_TIPO = 200          # Seleccionar Carga o Descarga
REG_ACCION = 201        # Seleccionar Llegada o Salida
REG_CONFIRMAR = 202     # Confirmar registro

# ============================================================
# COLUMNAS EXCEL (índices openpyxl, 1-indexed)
# ============================================================
COLUMNAS_EXCEL = {
    'carga_llegada': 15,      # Col O
    'carga_salida': 16,       # Col P
    'descarga_llegada': 18,   # Col R
    'descarga_salida': 19,    # Col S
}


class RegistrosConductor:
    """
    Gestiona los registros de llegada/salida de conductores.
    """
    
    def __init__(self, excel_path: str, db_path: str, subir_drive_func=None):
        self.excel_path = excel_path
        self.db_path = db_path
        self.subir_drive = subir_drive_func
        logger.info("[REGISTROS] Módulo de registros v1.0 inicializado")
    
    def get_conversation_handler(self):
        """Devuelve el ConversationHandler para registros"""
        return ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^📝 Registros$"), self.inicio),
            ],
            states={
                REG_TIPO: [
                    CallbackQueryHandler(self.seleccionar_tipo, pattern="^reg_tipo_"),
                    CallbackQueryHandler(self.cancelar_callback, pattern="^reg_cancelar$"),
                ],
                REG_ACCION: [
                    CallbackQueryHandler(self.seleccionar_accion, pattern="^reg_accion_"),
                    CallbackQueryHandler(self.volver_tipo, pattern="^reg_volver_tipo$"),
                    CallbackQueryHandler(self.cancelar_callback, pattern="^reg_cancelar$"),
                ],
                REG_CONFIRMAR: [
                    CallbackQueryHandler(self.confirmar_registro, pattern="^reg_confirmar_"),
                    CallbackQueryHandler(self.volver_accion, pattern="^reg_volver_accion$"),
                    CallbackQueryHandler(self.cancelar_callback, pattern="^reg_cancelar$"),
                ],
            },
            fallbacks=[
                CommandHandler("cancelar", self.cancelar),
                MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
            ],
        )
    
    # ============================================================
    # OBTENER VIAJE ACTIVO DEL CONDUCTOR
    # ============================================================
    
    def _obtener_viaje_conductor(self, telegram_id: int) -> Optional[Dict]:
        """Obtiene el viaje activo del conductor"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Primero obtener el nombre del conductor
            cursor.execute("""
                SELECT nombre FROM conductores_empresa 
                WHERE telegram_id = ?
            """, (telegram_id,))
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return None
            
            nombre = row['nombre']
            
            # Buscar viaje activo
            cursor.execute("""
                SELECT * FROM viajes_empresa 
                WHERE conductor_asignado LIKE ? 
                AND estado IN ('pendiente', 'en_ruta', 'asignado')
                ORDER BY id DESC
                LIMIT 1
            """, (f"%{nombre}%",))
            
            viaje = cursor.fetchone()
            conn.close()
            
            if viaje:
                return dict(viaje)
            return None
            
        except Exception as e:
            logger.error(f"[REGISTROS] Error obteniendo viaje: {e}")
            return None
    
    # ============================================================
    # ACTUALIZAR EXCEL
    # ============================================================
    
    def _actualizar_hora_excel(self, fila_excel: int, tipo: str, accion: str) -> bool:
        """
        Actualiza la hora en el Excel.
        
        Args:
            fila_excel: Fila del viaje (0-indexed de la BD)
            tipo: 'carga' o 'descarga'
            accion: 'llegada' o 'salida'
        """
        try:
            from openpyxl import load_workbook
            
            if not Path(self.excel_path).exists():
                logger.error(f"[REGISTROS] Excel no encontrado: {self.excel_path}")
                return False
            
            # Determinar columna
            clave = f"{tipo}_{accion}"
            columna = COLUMNAS_EXCEL.get(clave)
            
            if not columna:
                logger.error(f"[REGISTROS] Columna no encontrada para: {clave}")
                return False
            
            # Hora actual
            hora_actual = datetime.now().strftime("%H:%M")
            
            # Cargar Excel
            wb = load_workbook(self.excel_path)
            ws = wb.active
            
            # fila_excel es 0-indexed, openpyxl es 1-indexed
            fila_openpyxl = fila_excel + 1
            
            if fila_openpyxl > ws.max_row:
                logger.error(f"[REGISTROS] Fila {fila_openpyxl} fuera de rango")
                return False
            
            # Escribir hora
            celda = ws.cell(row=fila_openpyxl, column=columna)
            valor_anterior = celda.value
            celda.value = hora_actual
            
            wb.save(self.excel_path)
            wb.close()
            
            logger.info(f"[REGISTROS] ✅ Excel actualizado: Fila {fila_openpyxl}, "
                       f"Col {columna} ({clave}) = '{hora_actual}' (antes: '{valor_anterior}')")
            
            # Subir a Drive
            if self.subir_drive:
                try:
                    self.subir_drive()
                    logger.info("[REGISTROS] ✅ Subido a Drive")
                except Exception as e:
                    logger.error(f"[REGISTROS] Error subiendo a Drive: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"[REGISTROS] Error actualizando Excel: {e}")
            return False
    
    # ============================================================
    # HANDLERS DEL CONVERSATION
    # ============================================================
    
    async def inicio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia el flujo de registros"""
        telegram_id = update.effective_user.id
        
        # Verificar que tiene viaje activo
        viaje = self._obtener_viaje_conductor(telegram_id)
        
        if not viaje:
            from teclados import teclado_conductor
            await update.message.reply_text(
                "❌ No tienes ningún viaje asignado actualmente.\n\n"
                "Cuando tengas un viaje, podrás registrar tus llegadas y salidas.",
                reply_markup=teclado_conductor
            )
            return ConversationHandler.END
        
        # Guardar viaje en contexto
        context.user_data['viaje'] = viaje
        
        # Mostrar info del viaje
        lugar_carga = viaje.get('lugar_carga', 'N/A')
        lugar_descarga = viaje.get('lugar_entrega', viaje.get('lugar_descarga', 'N/A'))
        cliente = viaje.get('cliente', 'N/A')
        
        texto = (
            f"📝 *REGISTRAR HORA*\n\n"
            f"🏢 Cliente: *{cliente}*\n"
            f"📥 Carga: {lugar_carga}\n"
            f"📤 Descarga: {lugar_descarga}\n\n"
            f"¿Qué quieres registrar?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📥 Carga", callback_data="reg_tipo_carga"),
                InlineKeyboardButton("📤 Descarga", callback_data="reg_tipo_descarga"),
            ],
            [InlineKeyboardButton("❌ Cancelar", callback_data="reg_cancelar")]
        ]
        
        await update.message.reply_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return REG_TIPO
    
    async def seleccionar_tipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cuando selecciona Carga o Descarga"""
        query = update.callback_query
        await query.answer()
        
        tipo = query.data.replace("reg_tipo_", "")
        context.user_data['tipo_registro'] = tipo
        
        viaje = context.user_data.get('viaje', {})
        
        if tipo == 'carga':
            lugar = viaje.get('lugar_carga', 'N/A')
            emoji = "📥"
        else:
            lugar = viaje.get('lugar_entrega', viaje.get('lugar_descarga', 'N/A'))
            emoji = "📤"
        
        texto = (
            f"{emoji} *{tipo.upper()}*\n\n"
            f"📍 Lugar: *{lugar}*\n\n"
            f"¿Qué momento quieres registrar?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🚛 Llegada", callback_data="reg_accion_llegada"),
                InlineKeyboardButton("🏁 Salida", callback_data="reg_accion_salida"),
            ],
            [
                InlineKeyboardButton("⬅️ Volver", callback_data="reg_volver_tipo"),
                InlineKeyboardButton("❌ Cancelar", callback_data="reg_cancelar"),
            ]
        ]
        
        await query.edit_message_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return REG_ACCION
    
    async def seleccionar_accion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cuando selecciona Llegada o Salida"""
        query = update.callback_query
        await query.answer()
        
        accion = query.data.replace("reg_accion_", "")
        context.user_data['accion_registro'] = accion
        
        tipo = context.user_data.get('tipo_registro', 'carga')
        viaje = context.user_data.get('viaje', {})
        hora_actual = datetime.now().strftime("%H:%M")
        
        if tipo == 'carga':
            lugar = viaje.get('lugar_carga', 'N/A')
            emoji_tipo = "📥"
        else:
            lugar = viaje.get('lugar_entrega', viaje.get('lugar_descarga', 'N/A'))
            emoji_tipo = "📤"
        
        emoji_accion = "🚛" if accion == 'llegada' else "🏁"
        
        texto = (
            f"⏰ *CONFIRMAR REGISTRO*\n\n"
            f"{emoji_tipo} {tipo.capitalize()}: *{lugar}*\n"
            f"{emoji_accion} Acción: *{accion.upper()}*\n"
            f"🕐 Hora: *{hora_actual}*\n\n"
            f"¿Confirmar registro?"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"✅ Registrar {accion}", callback_data=f"reg_confirmar_si")],
            [
                InlineKeyboardButton("⬅️ Volver", callback_data="reg_volver_accion"),
                InlineKeyboardButton("❌ Cancelar", callback_data="reg_cancelar"),
            ]
        ]
        
        await query.edit_message_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return REG_CONFIRMAR
    
    async def confirmar_registro(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirma y guarda el registro"""
        query = update.callback_query
        await query.answer()
        
        tipo = context.user_data.get('tipo_registro', 'carga')
        accion = context.user_data.get('accion_registro', 'llegada')
        viaje = context.user_data.get('viaje', {})
        fila_excel = viaje.get('fila_excel')
        
        hora_actual = datetime.now().strftime("%H:%M")
        
        if not fila_excel:
            await query.edit_message_text(
                "❌ Error: No se encontró la fila del viaje en el Excel.\n"
                "Contacta con el administrador."
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        # Actualizar Excel
        exito = self._actualizar_hora_excel(fila_excel, tipo, accion)
        
        if tipo == 'carga':
            lugar = viaje.get('lugar_carga', 'N/A')
            emoji_tipo = "📥"
        else:
            lugar = viaje.get('lugar_entrega', viaje.get('lugar_descarga', 'N/A'))
            emoji_tipo = "📤"
        
        emoji_accion = "🚛" if accion == 'llegada' else "🏁"
        
        if exito:
            texto = (
                f"✅ *REGISTRO GUARDADO*\n\n"
                f"{emoji_tipo} {tipo.capitalize()}: *{lugar}*\n"
                f"{emoji_accion} {accion.capitalize()}: *{hora_actual}*\n\n"
                f"☁️ _Sincronizado con Drive_"
            )
        else:
            texto = (
                f"⚠️ *ERROR AL GUARDAR*\n\n"
                f"No se pudo registrar la hora.\n"
                f"Inténtalo de nuevo o contacta con el administrador."
            )
        
        from teclados import teclado_conductor
        
        await query.edit_message_text(texto, parse_mode="Markdown")
        await query.message.reply_text(
            "¿Qué más necesitas?",
            reply_markup=teclado_conductor
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # ============================================================
    # NAVEGACIÓN
    # ============================================================
    
    async def volver_tipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a selección de tipo"""
        query = update.callback_query
        await query.answer()
        
        viaje = context.user_data.get('viaje', {})
        lugar_carga = viaje.get('lugar_carga', 'N/A')
        lugar_descarga = viaje.get('lugar_entrega', viaje.get('lugar_descarga', 'N/A'))
        cliente = viaje.get('cliente', 'N/A')
        
        texto = (
            f"📝 *REGISTRAR HORA*\n\n"
            f"🏢 Cliente: *{cliente}*\n"
            f"📥 Carga: {lugar_carga}\n"
            f"📤 Descarga: {lugar_descarga}\n\n"
            f"¿Qué quieres registrar?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📥 Carga", callback_data="reg_tipo_carga"),
                InlineKeyboardButton("📤 Descarga", callback_data="reg_tipo_descarga"),
            ],
            [InlineKeyboardButton("❌ Cancelar", callback_data="reg_cancelar")]
        ]
        
        await query.edit_message_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return REG_TIPO
    
    async def volver_accion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a selección de acción"""
        query = update.callback_query
        await query.answer()
        
        tipo = context.user_data.get('tipo_registro', 'carga')
        viaje = context.user_data.get('viaje', {})
        
        if tipo == 'carga':
            lugar = viaje.get('lugar_carga', 'N/A')
            emoji = "📥"
        else:
            lugar = viaje.get('lugar_entrega', viaje.get('lugar_descarga', 'N/A'))
            emoji = "📤"
        
        texto = (
            f"{emoji} *{tipo.upper()}*\n\n"
            f"📍 Lugar: *{lugar}*\n\n"
            f"¿Qué momento quieres registrar?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🚛 Llegada", callback_data="reg_accion_llegada"),
                InlineKeyboardButton("🏁 Salida", callback_data="reg_accion_salida"),
            ],
            [
                InlineKeyboardButton("⬅️ Volver", callback_data="reg_volver_tipo"),
                InlineKeyboardButton("❌ Cancelar", callback_data="reg_cancelar"),
            ]
        ]
        
        await query.edit_message_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return REG_ACCION
    
    async def cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela el registro (mensaje)"""
        context.user_data.clear()
        
        from teclados import teclado_conductor
        
        await update.message.reply_text(
            "❌ Registro cancelado.",
            reply_markup=teclado_conductor
        )
        
        return ConversationHandler.END
    
    async def cancelar_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela el registro (callback)"""
        query = update.callback_query
        await query.answer()
        
        context.user_data.clear()
        
        from teclados import teclado_conductor
        
        await query.edit_message_text("❌ Registro cancelado.")
        await query.message.reply_text(
            "¿Qué más necesitas?",
            reply_markup=teclado_conductor
        )
        
        return ConversationHandler.END


# ============================================================
# FUNCIÓN PARA INTEGRAR EN BOT_TRANSPORTE.PY
# ============================================================

def crear_registros_conductor(excel_path: str, db_path: str, subir_drive_func=None):
    """
    Crea una instancia del módulo de registros.
    
    Uso en bot_transporte.py:
    
        from registros_conductor import crear_registros_conductor
        
        # En main():
        registros = crear_registros_conductor(
            config.EXCEL_EMPRESA,
            config.DB_PATH,
            subir_excel_a_drive if config.DRIVE_ENABLED else None
        )
        app.add_handler(registros.get_conversation_handler())
    """
    return RegistrosConductor(
        excel_path=excel_path,
        db_path=db_path,
        subir_drive_func=subir_drive_func
    )
