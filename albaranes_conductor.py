"""
ALBARANES DE CONDUCTOR v1.1
============================
Permite a los conductores subir fotos de albaranes a Google Drive.

CAMBIOS v1.1:
- Máximo 3 fotos por viaje/día (sin mensaje al usuario)
- Mensajes simplificados para el conductor
- Sin información técnica visible

Estructura en Drive:
📁 Albaranes/
  📁 2026-02-12/
    📄 143022_JESUS-LA-PERLA_CONSUM_BILBAO-ALBACETE.jpg
  📁 2026-02-13/
    📄 ...

Flujo con viaje activo:
1. Conductor pulsa "📸 Registrar albarán"
2. Envía foto
3. Se sube automáticamente con datos del viaje

Flujo sin viaje activo:
1. Conductor pulsa "📸 Registrar albarán"
2. Bot pregunta: "¿Para qué cliente?"
3. Bot pregunta: "¿Ruta? (ej: BILBAO-MADRID)"
4. Envía foto
5. Se sube con esos datos
"""

import sqlite3
import logging
import os
import re
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
ALB_CONFIRMAR = 300      # Confirmar que tiene viaje activo
ALB_CLIENTE = 301        # Pedir cliente (si no tiene viaje)
ALB_RUTA = 302           # Pedir ruta (si no tiene viaje)
ALB_FOTO = 303           # Esperando foto
ALB_CONFIRMAR_SUBIDA = 304  # Confirmar subida exitosa


class AlbaranesConductor:
    """
    Gestiona la subida de fotos de albaranes a Google Drive.
    """
    
    def __init__(self, db_path: str, drive_service=None, 
                 carpeta_albaranes_id: str = None,
                 teclado_conductor=None):
        self.db_path = db_path
        self.drive_service = drive_service
        self.carpeta_albaranes_id = carpeta_albaranes_id
        self.teclado_conductor = teclado_conductor
        self._cache_carpetas = {}  # Cache de IDs de carpetas por fecha
        logger.info("[ALBARANES] Módulo de albaranes v1.1 inicializado")
    
    def set_drive_service(self, drive_service):
        """Permite establecer drive_service después de init"""
        self.drive_service = drive_service
    
    def set_carpeta_albaranes(self, carpeta_id: str):
        """Establece la carpeta raíz de albaranes en Drive"""
        self.carpeta_albaranes_id = carpeta_id
    
    def get_conversation_handler(self):
        """Devuelve el ConversationHandler para albaranes"""
        return ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^📸 Registrar albarán$"), self.inicio),
                CallbackQueryHandler(self.inicio_callback, pattern="^alb_inicio$"),
            ],
            states={
                ALB_CONFIRMAR: [
                    CallbackQueryHandler(self.pedir_foto, pattern="^alb_foto$"),
                    CallbackQueryHandler(self.cancelar_callback, pattern="^alb_cancelar$"),
                ],
                ALB_CLIENTE: [
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.recibir_cliente),
                ],
                ALB_RUTA: [
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.volver_cliente),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.recibir_ruta),
                ],
                ALB_FOTO: [
                    MessageHandler(filters.PHOTO, self.recibir_foto),
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                    CallbackQueryHandler(self.cancelar_callback, pattern="^alb_cancelar$"),
                ],
            },
            fallbacks=[
                CommandHandler("cancelar", self.cancelar),
                MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                CallbackQueryHandler(self.cancelar_callback, pattern="^alb_cancelar$"),
            ],
            name="albaranes",
            persistent=False,
        )
    
    # ============================================================
    # FUNCIONES DE BASE DE DATOS
    # ============================================================
    
    def _obtener_conductor(self, telegram_id: int) -> Optional[Dict]:
        """Obtiene datos del conductor por telegram_id"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT nombre, tractora, telefono, ubicacion
                FROM conductores_empresa 
                WHERE telegram_id = ?
            """, (telegram_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[ALBARANES] Error obteniendo conductor: {e}")
            return None
    
    def _obtener_viaje_activo(self, nombre_conductor: str) -> Optional[Dict]:
        """Obtiene el viaje activo del conductor"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, cliente, lugar_carga, lugar_entrega, mercancia, estado, fila_excel
                FROM viajes_empresa 
                WHERE conductor_asignado LIKE ?
                AND estado IN ('pendiente', 'en_ruta', 'asignado')
                ORDER BY id DESC
                LIMIT 1
            """, (f"%{nombre_conductor}%",))
            
            row = cursor.fetchone()
            conn.close()
            
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[ALBARANES] Error obteniendo viaje: {e}")
            return None
    
    # ============================================================
    # FUNCIONES DE GOOGLE DRIVE
    # ============================================================
    
    def _obtener_o_crear_carpeta(self, nombre_carpeta: str, padre_id: str = None) -> Optional[str]:
        """
        Obtiene el ID de una carpeta o la crea si no existe.
        Usa caché para evitar consultas repetidas.
        """
        cache_key = f"{padre_id}_{nombre_carpeta}"
        if cache_key in self._cache_carpetas:
            return self._cache_carpetas[cache_key]
        
        if not self.drive_service:
            logger.error("[ALBARANES] Drive no inicializado")
            return None
        
        try:
            # Buscar carpeta existente
            query = f"name = '{nombre_carpeta}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            if padre_id:
                query += f" and '{padre_id}' in parents"
            
            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                carpeta_id = files[0]['id']
                self._cache_carpetas[cache_key] = carpeta_id
                return carpeta_id
            
            # Crear carpeta nueva
            file_metadata = {
                'name': nombre_carpeta,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if padre_id:
                file_metadata['parents'] = [padre_id]
            
            folder = self.drive_service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            carpeta_id = folder.get('id')
            self._cache_carpetas[cache_key] = carpeta_id
            logger.info(f"[ALBARANES] Carpeta creada: {nombre_carpeta} ({carpeta_id})")
            return carpeta_id
            
        except Exception as e:
            logger.error(f"[ALBARANES] Error con carpeta {nombre_carpeta}: {e}")
            return None
    
    def _contar_fotos_viaje(self, carpeta_fecha: str, patron_nombre: str) -> int:
        """
        Cuenta cuántas fotos ya existen de este viaje en el día.
        patron_nombre: parte del nombre sin hora (CONDUCTOR_CLIENTE_RUTA)
        """
        if not self.drive_service:
            return 0
        
        try:
            # Obtener carpeta Albaranes
            carpeta_albaranes = self._obtener_o_crear_carpeta(
                "Albaranes", 
                self.carpeta_albaranes_id
            )
            if not carpeta_albaranes:
                return 0
            
            # Obtener carpeta del día
            carpeta_dia = self._obtener_o_crear_carpeta(
                carpeta_fecha, 
                carpeta_albaranes
            )
            if not carpeta_dia:
                return 0
            
            # Buscar archivos que contengan el patrón
            query = f"'{carpeta_dia}' in parents and name contains '{patron_nombre}' and trashed = false"
            
            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=10
            ).execute()
            
            return len(results.get('files', []))
            
        except Exception as e:
            logger.error(f"[ALBARANES] Error contando fotos: {e}")
            return 0
    
    def _subir_foto_a_drive(self, ruta_local: str, nombre_archivo: str, 
                            carpeta_fecha: str) -> bool:
        """
        Sube una foto a Drive en la estructura:
        Albaranes/YYYY-MM-DD/nombre_archivo.jpg
        """
        if not self.drive_service:
            logger.error("[ALBARANES] Drive no inicializado")
            return False
        
        try:
            # Obtener o crear carpeta "Albaranes"
            carpeta_albaranes = self._obtener_o_crear_carpeta(
                "Albaranes", 
                self.carpeta_albaranes_id
            )
            if not carpeta_albaranes:
                logger.error("[ALBARANES] No se pudo crear carpeta Albaranes")
                return False
            
            # Obtener o crear carpeta del día
            carpeta_dia = self._obtener_o_crear_carpeta(
                carpeta_fecha, 
                carpeta_albaranes
            )
            if not carpeta_dia:
                logger.error(f"[ALBARANES] No se pudo crear carpeta {carpeta_fecha}")
                return False
            
            # Subir foto
            from googleapiclient.http import MediaFileUpload
            
            file_metadata = {
                'name': nombre_archivo,
                'parents': [carpeta_dia]
            }
            
            media = MediaFileUpload(
                ruta_local,
                mimetype='image/jpeg',
                resumable=True
            )
            
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name'
            ).execute()
            
            logger.info(f"[ALBARANES] ✅ Foto subida: {file.get('name')}")
            return True
            
        except Exception as e:
            logger.error(f"[ALBARANES] Error subiendo foto: {e}")
            return False
    
    # ============================================================
    # HANDLERS DE CONVERSACIÓN
    # ============================================================
    
    async def inicio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia el proceso de registro de albarán"""
        user = update.effective_user
        
        # Verificar que es un conductor vinculado
        conductor = self._obtener_conductor(user.id)
        if not conductor:
            await update.message.reply_text(
                "❌ No estás vinculado como conductor.\n"
                "Usa /vincular para vincularte primero.",
                reply_markup=self.teclado_conductor
            )
            return ConversationHandler.END
        
        context.user_data['conductor'] = conductor
        
        # Verificar si tiene viaje activo
        viaje = self._obtener_viaje_activo(conductor['nombre'])
        
        if viaje:
            # Tiene viaje activo → pedir foto directamente
            context.user_data['viaje'] = viaje
            context.user_data['cliente'] = viaje.get('cliente', 'DESCONOCIDO')
            
            origen = viaje.get('lugar_carga', '?')
            destino = viaje.get('lugar_entrega', '?')
            context.user_data['ruta'] = f"{origen}-{destino}"
            
            keyboard = [
                [InlineKeyboardButton("📸 Enviar foto", callback_data="alb_foto")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="alb_cancelar")]
            ]
            
            await update.message.reply_text(
                f"📸 *REGISTRAR ALBARÁN*\n\n"
                f"📦 Viaje detectado:\n"
                f"• Cliente: *{viaje.get('cliente', '?')}*\n"
                f"• Ruta: *{origen} → {destino}*\n\n"
                f"¿Quieres subir un albarán para este viaje?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ALB_CONFIRMAR
        else:
            # Sin viaje activo → pedir datos manualmente
            context.user_data['viaje'] = None
            
            from telegram import ReplyKeyboardMarkup
            keyboard = [["❌ Cancelar"]]
            
            await update.message.reply_text(
                "📸 *REGISTRAR ALBARÁN*\n\n"
                "No tienes un viaje activo asignado.\n\n"
                "¿Para qué *cliente* es este albarán?",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return ALB_CLIENTE
    
    async def inicio_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicio desde callback (botón inline)"""
        query = update.callback_query
        await query.answer()
        
        # Simular mensaje para reusar lógica
        update.message = query.message
        return await self.inicio(update, context)
    
    async def recibir_cliente(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recibe el nombre del cliente"""
        cliente = update.message.text.strip().upper()
        
        if len(cliente) < 2:
            await update.message.reply_text("⚠️ Nombre de cliente muy corto. Inténtalo de nuevo:")
            return ALB_CLIENTE
        
        context.user_data['cliente'] = cliente
        
        from telegram import ReplyKeyboardMarkup
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            f"✅ Cliente: *{cliente}*\n\n"
            f"Ahora escribe la *ruta* (origen-destino):\n"
            f"Ejemplo: BILBAO-MADRID",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return ALB_RUTA
    
    async def recibir_ruta(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recibe la ruta del viaje"""
        ruta = update.message.text.strip().upper()
        
        # Normalizar ruta (quitar espacios, reemplazar → por -)
        ruta = re.sub(r'\s*[→>]\s*', '-', ruta)
        ruta = re.sub(r'\s+', '-', ruta)
        
        if len(ruta) < 3 or '-' not in ruta:
            await update.message.reply_text(
                "⚠️ Formato de ruta incorrecto.\n"
                "Usa el formato: ORIGEN-DESTINO\n"
                "Ejemplo: BILBAO-MADRID"
            )
            return ALB_RUTA
        
        context.user_data['ruta'] = ruta
        
        keyboard = [
            [InlineKeyboardButton("📸 Enviar foto", callback_data="alb_foto")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="alb_cancelar")]
        ]
        
        cliente = context.user_data.get('cliente', '?')
        
        await update.message.reply_text(
            f"✅ *DATOS DEL ALBARÁN*\n\n"
            f"• Cliente: *{cliente}*\n"
            f"• Ruta: *{ruta}*\n\n"
            f"Ahora envía la foto del albarán 📸",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ALB_FOTO
    
    async def pedir_foto(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pide al conductor que envíe la foto"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("❌ Cancelar", callback_data="alb_cancelar")]
        ]
        
        await query.edit_message_text(
            "📸 *ENVÍA LA FOTO DEL ALBARÁN*\n\n"
            "Haz una foto clara del albarán y envíala aquí.\n\n"
            "_Asegúrate de que se vean bien todos los datos._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ALB_FOTO
    
    async def recibir_foto(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recibe y procesa la foto del albarán"""
        # Obtener la foto con mayor resolución
        foto = update.message.photo[-1]
        
        conductor = context.user_data.get('conductor', {})
        cliente = context.user_data.get('cliente', 'DESCONOCIDO')
        ruta = context.user_data.get('ruta', 'SIN-RUTA')
        
        # Generar nombre del archivo
        ahora = datetime.now()
        fecha_carpeta = ahora.strftime("%Y-%m-%d")
        hora = ahora.strftime("%H%M%S")
        
        nombre_conductor = conductor.get('nombre', 'CONDUCTOR')
        nombre_conductor = re.sub(r'\s+', '-', nombre_conductor.upper())
        cliente_norm = re.sub(r'\s+', '-', cliente.upper())
        ruta_norm = re.sub(r'\s+', '-', ruta.upper())
        
        # Patrón para buscar fotos existentes (sin la hora)
        patron_viaje = f"{nombre_conductor}_{cliente_norm}_{ruta_norm}"
        
        # Verificar límite de 3 fotos por viaje
        fotos_existentes = self._contar_fotos_viaje(fecha_carpeta, patron_viaje)
        if fotos_existentes >= 3:
            await update.message.reply_text(
                "✅ Ya has registrado el albarán de este viaje.",
                reply_markup=self.teclado_conductor
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        nombre_archivo = f"{hora}_{patron_viaje}.jpg"
        
        # Descargar foto temporalmente
        ruta_temp = f"/tmp/{nombre_archivo}"
        
        try:
            archivo = await foto.get_file()
            await archivo.download_to_drive(ruta_temp)
            
            # Subir a Drive (sin mensaje al usuario)
            exito = self._subir_foto_a_drive(ruta_temp, nombre_archivo, fecha_carpeta)
            
            # Eliminar archivo temporal
            if os.path.exists(ruta_temp):
                os.remove(ruta_temp)
            
            if exito:
                await update.message.reply_text(
                    "✅ Albarán registrado correctamente.",
                    reply_markup=self.teclado_conductor
                )
            else:
                await update.message.reply_text(
                    "❌ Error al guardar el albarán. Inténtalo de nuevo.",
                    reply_markup=self.teclado_conductor
                )
            
        except Exception as e:
            logger.error(f"[ALBARANES] Error procesando foto: {e}")
            await update.message.reply_text(
                "❌ Error al procesar la foto. Inténtalo de nuevo.",
                reply_markup=self.teclado_conductor
            )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def volver_cliente(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a pedir el cliente"""
        from telegram import ReplyKeyboardMarkup
        keyboard = [["❌ Cancelar"]]
        
        await update.message.reply_text(
            "¿Para qué *cliente* es este albarán?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return ALB_CLIENTE
    
    async def cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela el proceso"""
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Registro de albarán cancelado.",
            reply_markup=self.teclado_conductor
        )
        return ConversationHandler.END
    
    async def cancelar_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela desde callback"""
        query = update.callback_query
        await query.answer()
        context.user_data.clear()
        
        await query.edit_message_text("❌ Registro de albarán cancelado.")
        await query.message.reply_text(
            "¿Qué más necesitas?",
            reply_markup=self.teclado_conductor
        )
        return ConversationHandler.END


# ============================================================
# FUNCIÓN PARA INTEGRAR EN BOT
# ============================================================

def crear_albaranes_conductor(db_path: str, drive_service=None,
                               carpeta_albaranes_id: str = None,
                               teclado_conductor=None):
    """
    Crea el gestor de albaranes.
    
    Uso en bot_transporte.py:
    
        from albaranes_conductor import crear_albaranes_conductor
        
        # En main():
        albaranes = crear_albaranes_conductor(
            config.DB_PATH,
            drive_service,
            config.DRIVE_CARPETA_ALBARANES_ID,  # Opcional
            teclado_conductor
        )
        app.add_handler(albaranes.get_conversation_handler())
    """
    return AlbaranesConductor(
        db_path=db_path,
        drive_service=drive_service,
        carpeta_albaranes_id=carpeta_albaranes_id,
        teclado_conductor=teclado_conductor
    )
