"""
MODIFICAR VIAJES EN RUTA
=========================
Sistema para que los admins modifiquen viajes de conductores en ruta.

Flujo:
1. Admin selecciona "Modificar viaje en ruta"
2. Selecciona zona
3. Ve lista de conductores EN RUTA con: nombre, teléfono, ruta, cliente
4. Selecciona conductor
5. Ve detalles del viaje y puede modificar campos
6. Confirma cambios
7. Se actualiza Excel + Drive + notifica al conductor

Version 1.0
"""

import sqlite3
import logging
import openpyxl
from openpyxl.comments import Comment
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
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
MOD_RUTA_ZONA = 100
MOD_RUTA_CONDUCTOR = 101
MOD_RUTA_DETALLE = 102
MOD_RUTA_CAMPO = 103
MOD_RUTA_VALOR = 104
MOD_RUTA_CONFIRMAR = 105

# Zonas disponibles
ZONAS = ["ZONA NORTE", "ZONA SUR", "ZONA ESTE", "ZONA OESTE", "ZONA CENTRO"]


class ModificadorViajesRuta:
    """
    Gestiona la modificación de viajes de conductores en ruta.
    Incluye notificaciones y sincronización con Drive.
    """
    
    def __init__(self, excel_path: str, db_path: str, es_admin_func, 
                 subir_drive_func=None, bot=None, movildata_api=None):
        """
        Args:
            excel_path: Ruta al Excel PRUEBO.xlsx
            db_path: Ruta a la BD SQLite
            es_admin_func: Función para verificar si es admin
            subir_drive_func: Función para subir Excel a Drive
            bot: Instancia del bot para notificaciones
            movildata_api: API de GPS para saber estados
        """
        self.excel_path = excel_path
        self.db_path = db_path
        self.es_admin = es_admin_func
        self.subir_drive = subir_drive_func
        self.bot = bot
        self.movildata = movildata_api
        
        # Campos modificables del viaje
        self.campos_viaje = {
            '1': ('lugar_carga', '📍 Lugar de Carga'),
            '2': ('lugar_entrega', '📍 Lugar de Descarga'),
            '3': ('mercancia', '📦 Mercancía'),
            '4': ('observaciones', '📝 Observaciones'),
            '5': ('hora_carga', '⏰ Hora de Carga'),
            '6': ('hora_descarga', '⏰ Hora de Descarga'),
            '7': ('cliente', '🏢 Cliente'),
            '8': ('precio', '💰 Precio'),
            '9': ('km', '📏 Kilómetros'),
        }
        
        logger.info("[MOD_RUTA] Modificador de viajes en ruta inicializado")
    
    def get_conversation_handler(self):
        """Devuelve el ConversationHandler para modificar viajes en ruta"""
        return ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^🔄 Modificar viaje en ruta$"), self.inicio),
                CommandHandler("modificar_ruta", self.inicio),
            ],
            states={
                MOD_RUTA_ZONA: [
                    CallbackQueryHandler(self.seleccionar_zona, pattern="^zona_"),
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                ],
                MOD_RUTA_CONDUCTOR: [
                    CallbackQueryHandler(self.seleccionar_conductor, pattern="^conductor_"),
                    CallbackQueryHandler(self.volver_zonas, pattern="^volver_zonas$"),
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                ],
                MOD_RUTA_DETALLE: [
                    CallbackQueryHandler(self.seleccionar_campo, pattern="^campo_"),
                    CallbackQueryHandler(self.llamar_conductor, pattern="^llamar_"),
                    CallbackQueryHandler(self.volver_conductores, pattern="^volver_conductores$"),
                    CallbackQueryHandler(self.confirmar_cambios, pattern="^confirmar_si$"),
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                ],
                MOD_RUTA_VALOR: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.volver_detalle),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.guardar_valor),
                ],
                MOD_RUTA_CONFIRMAR: [
                    CallbackQueryHandler(self.confirmar_cambios, pattern="^confirmar_si$"),
                    CallbackQueryHandler(self.volver_detalle, pattern="^confirmar_no$"),
                ],
            },
            fallbacks=[
                CommandHandler("cancelar", self.cancelar),
                MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
            ],
        )
    # ============================================================
    # FUNCIONES DE BASE DE DATOS
    # ============================================================
    
    def _query(self, query: str, params: tuple = (), fetch_one: bool = False):
        """Ejecuta una consulta SQL"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                if fetch_one:
                    row = cursor.fetchone()
                    return dict(row) if row else None
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"[MOD_RUTA] Error SQL: {e}")
            return None
    
    def _obtener_conductores_en_ruta(self, zona: str = None) -> List[Dict]:
        """
        Obtiene conductores que están EN RUTA (con viaje activo).
        
        Returns:
            Lista de conductores con sus datos y viaje actual
        """
        query = """
            SELECT DISTINCT 
                c.nombre,
                c.telefono,
                c.tractora,
                c.remolque,
                c.zona,
                c.telegram_id,
                v.id as viaje_id,
                v.cliente,
                v.lugar_carga,
                v.lugar_entrega,
                v.mercancia,
                v.precio,
                v.km,
                v.observaciones,
                v.fila_excel,
                v.estado
            FROM conductores_empresa c
            INNER JOIN viajes_empresa v ON v.conductor_asignado LIKE '%' || c.nombre || '%'
            WHERE v.estado IN ('pendiente', 'en_ruta', 'asignado')
        """
        
        params = ()
        if zona:
            query += " AND (c.zona LIKE ? OR v.zona LIKE ?)"
            params = (f"%{zona}%", f"%{zona}%")
        
        query += " ORDER BY c.nombre"
        
        conductores = self._query(query, params)
        
        # Añadir estado GPS si está disponible
        if self.movildata and conductores:
            for c in conductores:
                if c.get('tractora'):
                    try:
                        estado = self.movildata.get_estado_vehiculo(c['tractora'])
                        if estado:
                            c['estado_gps'] = estado.get('estado', 'desconocido')
                            c['velocidad'] = estado.get('velocidad', 0)
                    except:
                        pass
        
        return conductores or []
    
    def _obtener_telegram_id_conductor(self, nombre: str) -> Optional[int]:
        """Obtiene el telegram_id de un conductor"""
        result = self._query(
            "SELECT telegram_id FROM conductores_empresa WHERE nombre LIKE ?",
            (f"%{nombre}%",),
            fetch_one=True
        )
        return result.get('telegram_id') if result else None
    
    # ============================================================
    # FUNCIONES DE EXCEL
    # ============================================================
    
    def _detectar_formato_columna(self, ws, columna: int) -> dict:
        """
        Detecta el formato de una columna basándose en las primeras 5 filas de datos.
        Incluye: number_format, font (negrita), tipo de dato
        """
        formato = {
            'number_format': 'General',
            'bold': False,
            'font_name': None,
            'font_size': None,
            'tipo_valor': 'str'  # 'int', 'float', 'str'
        }
        
        # Revisar filas 3 a 7 (primeras 5 filas de datos)
        for fila in range(3, 8):
            celda = ws.cell(row=fila, column=columna)
            valor = celda.value
            
            if valor is not None:
                # Copiar formato de número
                if celda.number_format:
                    formato['number_format'] = celda.number_format
                
                # Copiar fuente (negrita, nombre, tamaño)
                if celda.font:
                    formato['bold'] = celda.font.bold or False
                    formato['font_name'] = celda.font.name
                    formato['font_size'] = celda.font.size
                
                # Detectar tipo de valor
                if isinstance(valor, int):
                    formato['tipo_valor'] = 'int'
                elif isinstance(valor, float):
                    formato['tipo_valor'] = 'float'
                else:
                    formato['tipo_valor'] = 'str'
                
                break  # Con el primer valor válido es suficiente
        
        return formato

    def _aplicar_formato(self, valor, campo: str, formato: dict):
        """
        Convierte el valor al tipo correcto (número o texto).
        NO añade € ni formato - eso lo hace Excel con number_format.
        """
        # Campos numéricos (precio, km)
        if campo in ['precio', 'km']:
            try:
                # Limpiar valor
                valor_limpio = str(valor).replace('€', '').replace(' ', '').replace(',', '.').replace('km', '').replace('KM', '')
                
                if formato['tipo_valor'] == 'int':
                    return int(float(valor_limpio))
                elif formato['tipo_valor'] == 'float':
                    return float(valor_limpio)
                else:
                    return float(valor_limpio)
            except:
                return valor
        
        # Campos de texto (lugares, cliente, mercancía)
        elif campo in ['lugar_carga', 'lugar_entrega', 'cliente', 'mercancia']:
            return str(valor).strip().upper()
        
        # Otros campos
        else:
            return valor

    def _actualizar_excel(self, fila: int, campo: str, valor) -> bool:
        """
        Actualiza un campo en el Excel COPIANDO EL FORMATO de las primeras filas.
        
        Args:
            fila: Número de fila en el Excel
            campo: Nombre del campo a actualizar
            valor: Nuevo valor
        
        Returns:
            True si se actualizó correctamente
        """
        from openpyxl.styles import Font
        from copy import copy
        
        # Mapeo de campos a columnas del Excel
        COLUMNAS_EXCEL = {
            'lugar_carga': 14,
            'lugar_entrega': 17,
            'mercancia': 20,
            'precio': 23,
            'km': 24,
            'observaciones': 28,
            'cliente': 9,
            'hora_carga': 3,
            'hora_descarga': 4,
        }
        
        columna = COLUMNAS_EXCEL.get(campo)
        if not columna:
            logger.error(f"[MOD_RUTA] Campo no encontrado: {campo}")
            return False
        
        try:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb.active
            
            # Corregir desfase: la BD guarda fila-1
            fila_real = fila + 1
            
            # DETECTAR FORMATO de las primeras filas
            formato = self._detectar_formato_columna(ws, columna)
            logger.info(f"[MOD_RUTA] Formato detectado: {formato}")
            
            # CONVERTIR VALOR al tipo correcto
            valor_convertido = self._aplicar_formato(valor, campo, formato)
            logger.info(f"[MOD_RUTA] Valor: {valor} -> Convertido: {valor_convertido} (tipo: {type(valor_convertido).__name__})")
            
            # Guardar valor anterior para el log
            celda = ws.cell(row=fila_real, column=columna)
            valor_anterior = celda.value
            
            # ACTUALIZAR VALOR
            celda.value = valor_convertido
            
            # COPIAR FORMATO DE NÚMERO (esto hace que se vea "500.00 €")
            celda.number_format = formato['number_format']
            
            # COPIAR FUENTE (negrita, etc.)
            celda.font = Font(
                bold=formato['bold'],
                name=formato['font_name'] or 'Calibri',
                size=formato['font_size'] or 11
            )
            
            # Añadir comentario con timestamp
            comentario = f"Modificado: {datetime.now().strftime('%d/%m/%Y %H:%M')}\nAnterior: {valor_anterior}"
            celda.comment = Comment(comentario, "Bot")
            
            wb.save(self.excel_path)
            wb.close()
            
            logger.info(f"[MOD_RUTA] Excel actualizado: fila {fila_real}, {campo} = {valor_convertido}")
            return True
            
        except Exception as e:
            logger.error(f"[MOD_RUTA] Error actualizando Excel: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _actualizar_bd(self, viaje_id: int, campo: str, valor) -> bool:
        """Actualiza un campo en la BD"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE viajes_empresa SET {campo} = ? WHERE id = ?",
                    (valor, viaje_id)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[MOD_RUTA] Error actualizando BD: {e}")
            return False
    
    def _sync_to_drive(self) -> bool:
        """Sincroniza el Excel con Google Drive"""
        logger.info(f"[MOD_RUTA] Intentando sincronizar con Drive...")
        logger.info(f"[MOD_RUTA] subir_drive existe: {self.subir_drive is not None}")
        
        if self.subir_drive:
            try:
                logger.info("[MOD_RUTA] Llamando a subir_drive()...")
                result = self.subir_drive()
                logger.info(f"[MOD_RUTA] Resultado subir_drive: {result}")
                if result:
                    logger.info("[MOD_RUTA] ✅ Excel sincronizado con Drive")
                else:
                    logger.error("[MOD_RUTA] ❌ subir_drive devolvió False")
                return result
            except Exception as e:
                logger.error(f"[MOD_RUTA] Error sincronizando: {e}")
                return False
        else:
            logger.warning("[MOD_RUTA] ⚠️ subir_drive es None, no se sincroniza")
        return True
    
    # ============================================================
    # NOTIFICACIONES
    # ============================================================
    
    async def _notificar_conductor(self, telegram_id: int, mensaje: str) -> bool:
        """Envía notificación al conductor"""
        if not self.bot or not telegram_id:
            return False
        
        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=mensaje,
                parse_mode='Markdown'
            )
            logger.info(f"[MOD_RUTA] Notificación enviada a {telegram_id}")
            return True
        except Exception as e:
            logger.error(f"[MOD_RUTA] Error enviando notificación: {e}")
            return False
    
    def _generar_mensaje_modificacion(self, conductor: str, cambios: Dict) -> str:
        """Genera el mensaje de notificación para el conductor"""
        mensaje = f"⚠️ *CAMBIO EN TU VIAJE*\n\n"
        mensaje += f"👤 Conductor: {conductor}\n"
        mensaje += f"📅 Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        mensaje += "📝 *Cambios realizados:*\n"
        
        for campo, valores in cambios.items():
            nombre_campo = self.campos_viaje.get(campo, (campo, campo))[1]
            mensaje += f"\n{nombre_campo}:\n"
            mensaje += f"   ❌ Antes: {valores['anterior']}\n"
            mensaje += f"   ✅ Ahora: {valores['nuevo']}\n"
        
        mensaje += "\n_Contacta con oficina si tienes dudas._"
        return mensaje
    
    # ============================================================
    # HANDLERS DEL CONVERSATION
    # ============================================================
    
    async def inicio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicio: muestra selección de zonas"""
        user = update.effective_user
        
        if not self.es_admin(user.id):
            await update.message.reply_text("❌ Solo administradores pueden acceder.")
            return ConversationHandler.END
        
        context.user_data.clear()
        
        # Crear botones de zonas
        keyboard = []
        for zona in ZONAS:
            keyboard.append([InlineKeyboardButton(zona, callback_data=f"zona_{zona}")])
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
        
        await update.message.reply_text(
            "🔄 *MODIFICAR VIAJE EN RUTA*\n\n"
            "Selecciona la zona:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MOD_RUTA_ZONA
    
    async def seleccionar_zona(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler cuando admin selecciona una zona"""
        query = update.callback_query
        await query.answer()
        
        zona = query.data.replace("zona_", "")
        context.user_data['zona_seleccionada'] = zona
        
        # Obtener conductores en ruta de esa zona
        conductores = self._obtener_conductores_en_ruta(zona)
        
        if not conductores:
            await query.edit_message_text(
                f"❌ No hay conductores en ruta en {zona}.\n\n"
                "Selecciona otra zona:",
                reply_markup=self._get_keyboard_zonas()
            )
            return MOD_RUTA_ZONA
        
        context.user_data['conductores'] = conductores
        
        # Mostrar lista de conductores
        texto = f"🚛 *CONDUCTORES EN RUTA - {zona}*\n\n"
        keyboard = []
        
        for i, c in enumerate(conductores):
            nombre = c.get('nombre', 'N/A')
            telefono = c.get('telefono', 'Sin teléfono')
            cliente = c.get('cliente', 'N/A')
            carga = c.get('lugar_carga', '?')
            descarga = c.get('lugar_entrega', '?')
            estado_gps = c.get('estado_gps', '')
            
            # Emoji según estado
            estado_emoji = "🟢" if estado_gps == 'en_ruta' else "🔵"
            
            texto += f"{estado_emoji} *{nombre}*\n"
            texto += f"   📞 {telefono}\n"
            texto += f"   🚛 {carga} → {descarga}\n"
            texto += f"   🏢 {cliente}\n\n"
            
            # Botón con nombre resumido
            nombre_corto = nombre.split()[0] if nombre else f"Conductor {i+1}"
            keyboard.append([
                InlineKeyboardButton(
                    f"{estado_emoji} {nombre_corto} - {carga}→{descarga}",
                    callback_data=f"conductor_{i}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="volver_zonas")])
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
        
        await query.edit_message_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MOD_RUTA_CONDUCTOR
    
    async def seleccionar_conductor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler cuando admin selecciona un conductor"""
        query = update.callback_query
        await query.answer()
        
        indice = int(query.data.replace("conductor_", ""))
        conductores = context.user_data.get('conductores', [])
        
        if indice >= len(conductores):
            await query.edit_message_text("❌ Error: conductor no encontrado.")
            return ConversationHandler.END
        
        conductor = conductores[indice]
        context.user_data['conductor_seleccionado'] = conductor
        context.user_data['cambios_pendientes'] = {}
        
        # Mostrar detalle del viaje
        texto = self._formatear_detalle_viaje(conductor)
        keyboard = self._get_keyboard_campos(conductor)
        
        await query.edit_message_text(
            texto,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return MOD_RUTA_DETALLE
    
    def _formatear_detalle_viaje(self, conductor: Dict) -> str:
        """Formatea los detalles del viaje para mostrar"""
        cambios = getattr(self, '_cambios_temp', {})
        
        texto = "📋 *DETALLE DEL VIAJE*\n"
        texto += "═" * 25 + "\n\n"
        
        texto += f"👤 *Conductor:* {conductor.get('nombre', 'N/A')}\n"
        texto += f"📞 *Teléfono:* {conductor.get('telefono', 'Sin teléfono')}\n"
        texto += f"🚛 *Tractora:* {conductor.get('tractora', 'N/A')}\n\n"
        
        texto += "─" * 25 + "\n"
        texto += "*VIAJE ACTUAL*\n"
        texto += "─" * 25 + "\n\n"
        
        texto += f"🏢 *Cliente:* {conductor.get('cliente', 'N/A')}\n"
        texto += f"📦 *Mercancía:* {conductor.get('mercancia', 'N/A')}\n\n"
        
        texto += f"📍 *Carga:* {conductor.get('lugar_carga', 'N/A')}\n"
        texto += f"📍 *Descarga:* {conductor.get('lugar_entrega', 'N/A')}\n\n"
        
        texto += f"📏 *Km:* {conductor.get('km', 'N/A')}\n"
        texto += f"💰 *Precio:* {conductor.get('precio', 'N/A')}€\n"
        
        if conductor.get('observaciones'):
            texto += f"\n📝 *Obs:* {conductor.get('observaciones', '')[:100]}\n"
        
        # Mostrar cambios pendientes
        cambios_pendientes = getattr(context, 'user_data', {}).get('cambios_pendientes', {}) if hasattr(self, 'context') else {}
        if cambios_pendientes:
            texto += "\n" + "═" * 25 + "\n"
            texto += "⚠️ *CAMBIOS PENDIENTES:*\n"
            for campo, valores in cambios_pendientes.items():
                nombre = self.campos_viaje.get(campo, (campo, campo))[1]
                texto += f"• {nombre}: {valores['nuevo']}\n"
        
        texto += "\n_Selecciona un campo para modificar:_"
        return texto
    
    def _get_keyboard_campos(self, conductor: Dict) -> InlineKeyboardMarkup:
        """Genera el teclado con campos modificables"""
        keyboard = [
            [
                InlineKeyboardButton("📍 Lugar Carga", callback_data="campo_1"),
                InlineKeyboardButton("📍 Lugar Descarga", callback_data="campo_2"),
            ],
            [
                InlineKeyboardButton("📦 Mercancía", callback_data="campo_3"),
                InlineKeyboardButton("📝 Observaciones", callback_data="campo_4"),
            ],
            [
                InlineKeyboardButton("🏢 Cliente", callback_data="campo_7"),
                InlineKeyboardButton("💰 Precio", callback_data="campo_8"),
            ],
            [
                InlineKeyboardButton("📏 Km", callback_data="campo_9"),
            ],
            [
                InlineKeyboardButton(
                    f"📞 Llamar ({conductor.get('telefono', 'N/A')})",
                    callback_data=f"llamar_{conductor.get('telefono', '')}"
                ),
            ],
        ]
        
        # Si hay cambios pendientes, añadir botón de confirmar
        keyboard.append([
            InlineKeyboardButton("✅ Confirmar cambios", callback_data="confirmar_si"),
            InlineKeyboardButton("⬅️ Volver", callback_data="volver_conductores"),
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    def _get_keyboard_zonas(self) -> InlineKeyboardMarkup:
        """Genera el teclado de zonas"""
        keyboard = []
        for zona in ZONAS:
            keyboard.append([InlineKeyboardButton(zona, callback_data=f"zona_{zona}")])
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
        return InlineKeyboardMarkup(keyboard)
    
    async def seleccionar_campo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler cuando admin selecciona un campo para modificar"""
        query = update.callback_query
        await query.answer()
        
        num_campo = query.data.replace("campo_", "")
        campo_info = self.campos_viaje.get(num_campo)
        
        if not campo_info:
            await query.answer("Campo no válido", show_alert=True)
            return MOD_RUTA_DETALLE
        
        campo_key, campo_nombre = campo_info
        context.user_data['campo_editando'] = num_campo
        context.user_data['campo_key'] = campo_key
        context.user_data['campo_nombre'] = campo_nombre
        
        conductor = context.user_data.get('conductor_seleccionado', {})
        valor_actual = conductor.get(campo_key, 'N/A')
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await query.message.reply_text(
            f"✏️ *MODIFICAR {campo_nombre.upper()}*\n\n"
            f"Valor actual: `{valor_actual}`\n\n"
            "Escribe el nuevo valor:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MOD_RUTA_VALOR
    
    async def guardar_valor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda el nuevo valor del campo"""
        nuevo_valor = update.message.text.strip()
        
        campo_key = context.user_data.get('campo_key')
        campo_nombre = context.user_data.get('campo_nombre')
        conductor = context.user_data.get('conductor_seleccionado', {})
        valor_anterior = conductor.get(campo_key, '')
        
        # Guardar en cambios pendientes
        if 'cambios_pendientes' not in context.user_data:
            context.user_data['cambios_pendientes'] = {}
        
        context.user_data['cambios_pendientes'][campo_key] = {
            'anterior': valor_anterior,
            'nuevo': nuevo_valor,
            'nombre': campo_nombre
        }
        
        # Actualizar también en el conductor para mostrar
        conductor[campo_key] = nuevo_valor
        
        await update.message.reply_text(
            f"✅ {campo_nombre} actualizado a: `{nuevo_valor}`\n\n"
            "Puedes modificar más campos o confirmar los cambios.",
            parse_mode="Markdown"
        )
        
        # Mostrar detalle actualizado
        texto = self._formatear_detalle_viaje_con_cambios(conductor, context.user_data.get('cambios_pendientes', {}))
        keyboard = self._get_keyboard_campos(conductor)
        
        await update.message.reply_text(
            texto,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return MOD_RUTA_DETALLE
    
    def _formatear_detalle_viaje_con_cambios(self, conductor: Dict, cambios: Dict) -> str:
        """Formatea los detalles del viaje incluyendo cambios pendientes"""
        texto = "📋 *DETALLE DEL VIAJE*\n"
        texto += "═" * 25 + "\n\n"
        
        texto += f"👤 *Conductor:* {conductor.get('nombre', 'N/A')}\n"
        texto += f"📞 *Teléfono:* {conductor.get('telefono', 'Sin teléfono')}\n"
        texto += f"🚛 *Tractora:* {conductor.get('tractora', 'N/A')}\n\n"
        
        texto += "─" * 25 + "\n"
        texto += "*VIAJE ACTUAL*\n"
        texto += "─" * 25 + "\n\n"
        
        texto += f"🏢 *Cliente:* {conductor.get('cliente', 'N/A')}\n"
        texto += f"📦 *Mercancía:* {conductor.get('mercancia', 'N/A')}\n\n"
        
        texto += f"📍 *Carga:* {conductor.get('lugar_carga', 'N/A')}\n"
        texto += f"📍 *Descarga:* {conductor.get('lugar_entrega', 'N/A')}\n\n"
        
        texto += f"📏 *Km:* {conductor.get('km', 'N/A')}\n"
        texto += f"💰 *Precio:* {conductor.get('precio', 'N/A')}€\n"
        
        if conductor.get('observaciones'):
            texto += f"\n📝 *Obs:* {conductor.get('observaciones', '')[:100]}\n"
        
        # Mostrar cambios pendientes
        if cambios:
            texto += "\n" + "═" * 25 + "\n"
            texto += "⚠️ *CAMBIOS PENDIENTES:*\n"
            for campo_key, valores in cambios.items():
                texto += f"• {valores['nombre']}: `{valores['anterior']}` → `{valores['nuevo']}`\n"
        
        texto += "\n_Selecciona un campo para modificar o confirma:_"
        return texto
    
    async def confirmar_cambios(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirma y aplica todos los cambios"""
        logger.info("🔔 [MOD_RUTA] ENTRANDO EN confirmar_cambios")
        query = update.callback_query
        await query.answer()
        
        cambios = context.user_data.get('cambios_pendientes', {})
        conductor = context.user_data.get('conductor_seleccionado', {})
        
        if not cambios:
            await query.answer("No hay cambios pendientes", show_alert=True)
            return MOD_RUTA_DETALLE
        
        fila_excel = conductor.get('fila_excel')
        viaje_id = conductor.get('viaje_id')
        nombre_conductor = conductor.get('nombre', '')
        telegram_id = conductor.get('telegram_id') or self._obtener_telegram_id_conductor(nombre_conductor)
        
        # Aplicar cambios al Excel y BD
        errores = []
        for campo_key, valores in cambios.items():
            # Actualizar Excel
            if fila_excel:
                if not self._actualizar_excel(fila_excel, campo_key, valores['nuevo']):
                    errores.append(f"Excel: {campo_key}")
            
            # Actualizar BD
            if viaje_id:
                if not self._actualizar_bd(viaje_id, campo_key, valores['nuevo']):
                    errores.append(f"BD: {campo_key}")
        
        # Sincronizar con Drive
        drive_ok = self._sync_to_drive()
        
        # Notificar al conductor
        notificacion_ok = False
        if telegram_id:
            mensaje = self._generar_mensaje_modificacion(nombre_conductor, cambios)
            notificacion_ok = await self._notificar_conductor(telegram_id, mensaje)
        
        # Generar resumen
        texto = "✅ *CAMBIOS APLICADOS*\n\n"
        texto += f"👤 Conductor: {nombre_conductor}\n"
        texto += f"📅 Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        
        texto += "*Cambios realizados:*\n"
        for campo_key, valores in cambios.items():
            texto += f"• {valores['nombre']}: `{valores['nuevo']}`\n"
        
        texto += "\n*Estado:*\n"
        texto += f"• Excel: {'✅' if not errores else '⚠️'}\n"
        texto += f"• Google Drive: {'✅' if drive_ok else '❌'}\n"
        texto += f"• Notificación: {'✅ Enviada' if notificacion_ok else '⚠️ No enviada (sin Telegram)'}\n"
        
        if errores:
            texto += f"\n⚠️ Errores: {', '.join(errores)}"
        
        await query.edit_message_text(texto, parse_mode="Markdown")
        
        # Limpiar datos
        context.user_data.clear()
        
        return ConversationHandler.END
    
    async def llamar_conductor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el teléfono del conductor para llamar"""
        query = update.callback_query
        telefono = query.data.replace("llamar_", "")
        
        if not telefono or telefono == "None":
            await query.answer("❌ No hay teléfono registrado", show_alert=True)
            return MOD_RUTA_DETALLE
        
        conductor = context.user_data.get('conductor_seleccionado', {})
        nombre = conductor.get('nombre', 'Conductor')
        
        await query.answer(f"📞 {telefono}", show_alert=True)
        
        # Enviar mensaje con el teléfono clickeable
        await query.message.reply_text(
            f"📞 *LLAMAR A {nombre}*\n\n"
            f"Teléfono: `{telefono}`\n\n"
            f"[Llamar](tel:{telefono})",
            parse_mode="Markdown"
        )
        return MOD_RUTA_DETALLE
    
    async def volver_zonas(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a la selección de zonas"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "🔄 *MODIFICAR VIAJE EN RUTA*\n\n"
            "Selecciona la zona:",
            parse_mode="Markdown",
            reply_markup=self._get_keyboard_zonas()
        )
        return MOD_RUTA_ZONA
    
    async def volver_conductores(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a la lista de conductores"""
        query = update.callback_query
        await query.answer()
        
        zona = context.user_data.get('zona_seleccionada', '')
        conductores = self._obtener_conductores_en_ruta(zona)
        context.user_data['conductores'] = conductores
        
        if not conductores:
            await query.edit_message_text(
                f"❌ No hay conductores en ruta en {zona}.",
                reply_markup=self._get_keyboard_zonas()
            )
            return MOD_RUTA_ZONA
        
        # Mostrar lista
        texto = f"🚛 *CONDUCTORES EN RUTA - {zona}*\n\n"
        keyboard = []
        
        for i, c in enumerate(conductores):
            nombre = c.get('nombre', 'N/A')
            telefono = c.get('telefono', 'Sin teléfono')
            carga = c.get('lugar_carga', '?')
            descarga = c.get('lugar_entrega', '?')
            
            texto += f"• *{nombre}* - 📞 {telefono}\n"
            texto += f"   🚛 {carga} → {descarga}\n\n"
            
            nombre_corto = nombre.split()[0] if nombre else f"Conductor {i+1}"
            keyboard.append([
                InlineKeyboardButton(
                    f"{nombre_corto} - {carga}→{descarga}",
                    callback_data=f"conductor_{i}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="volver_zonas")])
        
        await query.edit_message_text(
            texto,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MOD_RUTA_CONDUCTOR
    
    async def volver_detalle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve al detalle del viaje"""
        # Puede venir de CallbackQuery o Message
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            message = query.message
        else:
            message = update.message
        
        conductor = context.user_data.get('conductor_seleccionado', {})
        cambios = context.user_data.get('cambios_pendientes', {})
        
        texto = self._formatear_detalle_viaje_con_cambios(conductor, cambios)
        keyboard = self._get_keyboard_campos(conductor)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                texto,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await message.reply_text(
                texto,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        return MOD_RUTA_DETALLE
    
    async def cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela la operación y devuelve el teclado de admin"""
        context.user_data.clear()
        
        from teclados import teclado_admin
        
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                "❌ Operación cancelada.\n\n¿Qué más necesitas?",
                reply_markup=teclado_admin
            )
        else:
            await update.message.reply_text(
                "❌ Operación cancelada.\n\n¿Qué más necesitas?",
                reply_markup=teclado_admin
            )
        
        return ConversationHandler.END


# ============================================================
# FUNCIÓN PARA INTEGRAR EN BOT_TRANSPORTE.PY
# ============================================================

def crear_modificador_viajes_ruta(excel_path: str, db_path: str, es_admin_func,
                                    subir_drive_func=None, bot=None, movildata_api=None):
    """
    Crea una instancia del modificador de viajes en ruta.
    
    Uso en bot_transporte.py:
    
        from modificador_viajes_ruta import crear_modificador_viajes_ruta, ModificadorViajesRuta
        
        # En main():
        modificador_ruta = crear_modificador_viajes_ruta(
            config.EXCEL_EMPRESA,
            config.DB_PATH,
            es_admin,
            subir_excel_a_drive,
            app.bot,
            movildata
        )
        app.add_handler(modificador_ruta.get_conversation_handler())
    """
    return ModificadorViajesRuta(
        excel_path=excel_path,
        db_path=db_path,
        es_admin_func=es_admin_func,
        subir_drive_func=subir_drive_func,
        bot=bot,
        movildata_api=movildata_api
    )
