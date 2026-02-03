"""
GESTIONES - CAMIONEROS Y VIAJES
================================
Sistema completo para añadir y modificar camioneros y viajes.
- Botón "Volver atrás" durante creación
- Botón "Editar" antes de confirmar
- Modificar viajes/camioneros existentes
- Sincronización con Google Drive
"""

import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes, 
    ConversationHandler, 
    CommandHandler, 
    MessageHandler, 
    filters
)
import openpyxl
from openpyxl.comments import Comment
from pathlib import Path

logger = logging.getLogger(__name__)

# Estados de la conversación
MENU_PRINCIPAL = 0
MENU_TIPO = 1
MENU_ACCION = 2

# Camionero
CAM_NOMBRE = 10
CAM_TELEFONO = 11
CAM_TRACTORA = 12
CAM_REMOLQUE = 13
CAM_UBICACION = 14
CAM_CONFIRMAR = 15
CAM_EDITAR_CAMPO = 16

# Viaje
VIA_ZONA = 20
VIA_CLIENTE = 21
VIA_NUM_PEDIDO = 22
VIA_REF_CLIENTE = 23
VIA_INTERCAMBIO = 24
VIA_LUGAR_CARGA = 25
VIA_CARGA_ADICIONAL = 26
VIA_CARGA_ADICIONAL_LUGAR = 27
VIA_LUGAR_DESCARGA = 28
VIA_DESCARGA_ADICIONAL = 29
VIA_DESCARGA_ADICIONAL_LUGAR = 30
VIA_MERCANCIA = 31
VIA_KM = 32
VIA_PRECIO = 33
VIA_CONFIRMAR = 34
VIA_EDITAR_CAMPO = 35
VIA_EDITAR_VALOR = 36

# Modificar existente
MOD_ELEGIR_VIAJE = 40
MOD_ELEGIR_CAMIONERO = 41
MOD_CAMPO = 42
MOD_VALOR = 43


class GestionesManager:
    """Gestiona altas y modificaciones de camioneros y viajes"""
    
    def __init__(self, excel_path: str, db_path: str, es_admin_func, subir_drive_func=None):
        self.excel_path = excel_path
        self.db_path = db_path
        self.es_admin = es_admin_func
        self.subir_drive = subir_drive_func
        
        # Mapeo de campos de viaje
        self.campos_viaje = {
            '1': ('zona', '🗺️ Zona'),
            '2': ('cliente', '🏢 Cliente'),
            '3': ('num_pedido', '🔢 Nº Pedido'),
            '4': ('ref_cliente', '🏷️ Ref. Cliente'),
            '5': ('intercambio', '🔄 Intercambio'),
            '6': ('lugar_carga', '📍 Lugar de Carga'),
            '7': ('carga_adicional', '📍 Carga Adicional'),
            '8': ('lugar_descarga', '📍 Lugar de Descarga'),
            '9': ('descarga_adicional', '📍 Descarga Adicional'),
            '10': ('mercancia', '📦 Mercancía'),
            '11': ('km', '📏 Kilómetros'),
            '12': ('precio', '💰 Precio'),
        }
        
        # Mapeo de campos de camionero
        self.campos_camionero = {
            '1': ('nombre', '👤 Nombre'),
            '2': ('telefono', '📱 Teléfono'),
            '3': ('tractora', '🚛 Tractora'),
            '4': ('remolque', '📦 Remolque'),
            '5': ('ubicacion', '📍 Ubicación'),
        }
        
    def get_conversation_handler(self):
        """Devuelve el ConversationHandler"""
        return ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^🛠️ Gestiones$"), self.inicio),
                CommandHandler("gestiones", self.inicio),
            ],
            states={
                MENU_PRINCIPAL: [
                    MessageHandler(filters.Regex("^🚛 Camionero$"), self.menu_camionero),
                    MessageHandler(filters.Regex("^📦 Viaje$"), self.menu_viaje),
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                ],
                MENU_ACCION: [
                    MessageHandler(filters.Regex("^➕ Añadir$"), self.accion_añadir),
                    MessageHandler(filters.Regex("^✏️ Modificar$"), self.accion_modificar),
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.inicio),
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                ],
                
                # === CAMIONERO ===
                CAM_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.cam_nombre)],
                CAM_TELEFONO: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.cam_volver_nombre),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.cam_telefono),
                ],
                CAM_TRACTORA: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.cam_volver_telefono),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.cam_tractora),
                ],
                CAM_REMOLQUE: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.cam_volver_tractora),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.cam_remolque),
                ],
                CAM_UBICACION: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.cam_volver_remolque),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.cam_ubicacion),
                ],
                CAM_CONFIRMAR: [
                    MessageHandler(filters.Regex("^✅ Confirmar$"), self.cam_guardar),
                    MessageHandler(filters.Regex("^✏️ Editar$"), self.cam_editar),
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                ],
                CAM_EDITAR_CAMPO: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.cam_mostrar_resumen),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.cam_editar_campo),
                ],
                
                # === VIAJE ===
                VIA_ZONA: [
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_zona),
                ],
                VIA_CLIENTE: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_zona),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_cliente),
                ],
                VIA_NUM_PEDIDO: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_cliente),
                    MessageHandler(filters.Regex("^⏭️ Saltar$"), self.via_saltar_num_pedido),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_num_pedido),
                ],
                VIA_REF_CLIENTE: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_num_pedido),
                    MessageHandler(filters.Regex("^⏭️ Saltar$"), self.via_saltar_ref_cliente),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_ref_cliente),
                ],
                VIA_INTERCAMBIO: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_ref_cliente),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_intercambio),
                ],
                VIA_LUGAR_CARGA: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_intercambio),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_lugar_carga),
                ],
                VIA_CARGA_ADICIONAL: [
                    MessageHandler(filters.Regex("^➕ Sí$"), self.via_pedir_carga_adicional),
                    MessageHandler(filters.Regex("^➡️ No$"), self.via_saltar_carga_adicional),
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_intercambio),
                ],
                VIA_CARGA_ADICIONAL_LUGAR: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_carga_adicional),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_carga_adicional_lugar),
                ],
                VIA_LUGAR_DESCARGA: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_carga),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_lugar_descarga),
                ],
                VIA_DESCARGA_ADICIONAL: [
                    MessageHandler(filters.Regex("^➕ Sí$"), self.via_pedir_descarga_adicional),
                    MessageHandler(filters.Regex("^➡️ No$"), self.via_saltar_descarga_adicional),
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_lugar_descarga_pre),
                ],
                VIA_DESCARGA_ADICIONAL_LUGAR: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_descarga_adicional),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_descarga_adicional_lugar),
                ],
                VIA_MERCANCIA: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_descarga),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_mercancia),
                ],
                VIA_KM: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_mercancia),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_km),
                ],
                VIA_PRECIO: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_volver_km),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_precio),
                ],
                VIA_CONFIRMAR: [
                    MessageHandler(filters.Regex("^✅ Confirmar$"), self.via_guardar),
                    MessageHandler(filters.Regex("^✏️ Editar$"), self.via_editar),
                    MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
                ],
                VIA_EDITAR_CAMPO: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_mostrar_resumen),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_editar_campo),
                ],
                VIA_EDITAR_VALOR: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.via_editar),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.via_editar_valor),
                ],
                
                # === MODIFICAR EXISTENTE ===
                MOD_ELEGIR_VIAJE: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.menu_viaje),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.mod_elegir_viaje),
                ],
                MOD_ELEGIR_CAMIONERO: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.menu_camionero),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.mod_elegir_camionero),
                ],
                MOD_CAMPO: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.mod_volver_lista),
                    MessageHandler(filters.Regex("^✅ Guardar cambios$"), self.mod_guardar),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.mod_elegir_campo),
                ],
                MOD_VALOR: [
                    MessageHandler(filters.Regex("^⬅️ Volver$"), self.mod_mostrar_resumen),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.mod_nuevo_valor),
                ],
            },
            fallbacks=[
                CommandHandler("cancelar", self.cancelar),
                MessageHandler(filters.Regex("^❌ Cancelar$"), self.cancelar),
            ],
        )
    
    def _sync_to_drive(self):
        """Sincroniza el Excel con Google Drive"""
        if self.subir_drive:
            try:
                result = self.subir_drive()
                if result:
                    logger.info("[GESTIONES] ✅ Excel sincronizado con Drive")
                return result
            except Exception as e:
                logger.error(f"[GESTIONES] Error sincronizando: {e}")
                return False
        return True
    
    def _get_viajes_sin_asignar(self, limite=10):
        """Obtiene los últimos viajes sin asignar del Excel"""
        try:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb.active
            
            viajes = []
            fila = 3
            while ws.cell(row=fila, column=9).value:
                transportista = ws.cell(row=fila, column=5).value
                if not transportista or str(transportista).strip() == "":
                    viajes.append({
                        'fila': fila,
                        'cliente': ws.cell(row=fila, column=9).value or "",
                        'num_pedido': ws.cell(row=fila, column=10).value,
                        'ref_cliente': ws.cell(row=fila, column=11).value,
                        'intercambio': ws.cell(row=fila, column=12).value or "NO",
                        'lugar_carga': ws.cell(row=fila, column=14).value or "",
                        'lugar_descarga': ws.cell(row=fila, column=17).value or "",
                        'mercancia': ws.cell(row=fila, column=20).value or "",
                        'precio': ws.cell(row=fila, column=23).value or 0,
                        'km': ws.cell(row=fila, column=24).value or 0,
                        'zona': (ws.cell(row=fila, column=28).value or "").replace("ZONA: ", ""),
                    })
                fila += 1
            
            wb.close()
            return viajes[-limite:] if len(viajes) > limite else viajes
        except Exception as e:
            logger.error(f"[GESTIONES] Error leyendo viajes: {e}")
            return []
    
    def _get_camioneros(self, limite=10):
        """Obtiene los camioneros del Excel"""
        try:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb.active
            
            camioneros = []
            fila = 3
            while ws.cell(row=fila, column=5).value:
                nombre = ws.cell(row=fila, column=5).value
                if nombre and str(nombre).strip():
                    # Obtener teléfono del comentario
                    telefono = ""
                    cell = ws.cell(row=fila, column=5)
                    if cell.comment:
                        import re
                        match = re.search(r'(\d{9,})', cell.comment.text)
                        if match:
                            telefono = match.group(1)
                    
                    camioneros.append({
                        'fila': fila,
                        'nombre': nombre,
                        'telefono': telefono,
                        'tractora': ws.cell(row=fila, column=7).value or "",
                        'remolque': ws.cell(row=fila, column=8).value or "",
                        'ubicacion': ws.cell(row=fila, column=2).value or "",
                    })
                fila += 1
            
            wb.close()
            return camioneros[-limite:] if len(camioneros) > limite else camioneros
        except Exception as e:
            logger.error(f"[GESTIONES] Error leyendo camioneros: {e}")
            return []
    
    # ============================================================
    # MENÚ PRINCIPAL
    # ============================================================
    
    async def inicio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menú principal de gestiones"""
        user = update.effective_user
        
        if not self.es_admin(user.id):
            await update.message.reply_text("❌ Solo administradores pueden acceder.")
            return ConversationHandler.END
        
        context.user_data.clear()
        
        keyboard = [
            ["🚛 Camionero", "📦 Viaje"],
            ["❌ Cancelar"]
        ]
        
        await update.message.reply_text(
            "🛠️ *GESTIONES*\n\n¿Qué quieres gestionar?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MENU_PRINCIPAL
    
    async def menu_camionero(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menú de camionero"""
        context.user_data['tipo'] = 'camionero'
        
        keyboard = [
            ["➕ Añadir", "✏️ Modificar"],
            ["⬅️ Volver", "❌ Cancelar"]
        ]
        
        await update.message.reply_text(
            "🚛 *CAMIONERO*\n\n¿Qué quieres hacer?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MENU_ACCION
    
    async def menu_viaje(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menú de viaje"""
        context.user_data['tipo'] = 'viaje'
        
        keyboard = [
            ["➕ Añadir", "✏️ Modificar"],
            ["⬅️ Volver", "❌ Cancelar"]
        ]
        
        await update.message.reply_text(
            "📦 *VIAJE*\n\n¿Qué quieres hacer?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MENU_ACCION
    
    async def accion_añadir(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Redirige a añadir según tipo"""
        tipo = context.user_data.get('tipo')
        if tipo == 'camionero':
            return await self.cam_inicio(update, context)
        else:
            return await self.via_inicio(update, context)
    
    async def accion_modificar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Redirige a modificar según tipo"""
        tipo = context.user_data.get('tipo')
        if tipo == 'camionero':
            return await self.mod_listar_camioneros(update, context)
        else:
            return await self.mod_listar_viajes(update, context)
    
    # ============================================================
    # AÑADIR CAMIONERO
    # ============================================================
    
    async def cam_inicio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicio añadir camionero"""
        context.user_data['camionero'] = {}
        
        keyboard = [["❌ Cancelar"]]
        
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 1/5\n\n"
            "👤 *¿Nombre completo?*\n\n"
            "_Ejemplo: LUIS PEREZ GARCIA_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_NOMBRE
    
    async def cam_nombre(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda nombre"""
        context.user_data['camionero']['nombre'] = update.message.text.upper().strip()
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 2/5\n\n"
            "📱 *¿Teléfono?*\n\n"
            "_Ejemplo: 666111222_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_TELEFONO
    
    async def cam_volver_nombre(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Volver a nombre"""
        keyboard = [["❌ Cancelar"]]
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 1/5\n\n"
            "👤 *¿Nombre completo?*\n\n"
            f"_Anterior: {context.user_data['camionero'].get('nombre', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_NOMBRE
    
    async def cam_telefono(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda teléfono"""
        telefono = update.message.text.strip().replace(" ", "").replace("+34", "")
        
        if not telefono.isdigit() or len(telefono) < 9:
            await update.message.reply_text("⚠️ Teléfono no válido. Introduce 9 dígitos:")
            return CAM_TELEFONO
        
        context.user_data['camionero']['telefono'] = telefono
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 3/5\n\n"
            "🚛 *¿Matrícula tractora?*\n\n"
            "_Ejemplo: 1234ABC_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_TRACTORA
    
    async def cam_volver_telefono(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Volver a teléfono"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 2/5\n\n"
            "📱 *¿Teléfono?*\n\n"
            f"_Anterior: {context.user_data['camionero'].get('telefono', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_TELEFONO
    
    async def cam_tractora(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda tractora"""
        context.user_data['camionero']['tractora'] = update.message.text.upper().strip().replace(" ", "")
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 4/5\n\n"
            "📦 *¿Matrícula remolque?*\n\n"
            "_Ejemplo: R1234BCD_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_REMOLQUE
    
    async def cam_volver_tractora(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Volver a tractora"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 3/5\n\n"
            "🚛 *¿Matrícula tractora?*\n\n"
            f"_Anterior: {context.user_data['camionero'].get('tractora', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_TRACTORA
    
    async def cam_remolque(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda remolque"""
        context.user_data['camionero']['remolque'] = update.message.text.upper().strip().replace(" ", "")
        
        keyboard = [
            ["AZAGRA", "TUDELA", "CALAHORRA"],
            ["SAN ADRIAN", "LOGROÑO", "PAMPLONA"],
            ["⬅️ Volver", "❌ Cancelar"]
        ]
        
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 5/5\n\n"
            "📍 *¿Ubicación base?*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_UBICACION
    
    async def cam_volver_remolque(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Volver a remolque"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "Paso 4/5\n\n"
            "📦 *¿Matrícula remolque?*\n\n"
            f"_Anterior: {context.user_data['camionero'].get('remolque', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_REMOLQUE
    
    async def cam_ubicacion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda ubicación y muestra resumen"""
        context.user_data['camionero']['ubicacion'] = update.message.text.upper().strip()
        return await self.cam_mostrar_resumen(update, context)
    
    async def cam_mostrar_resumen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra resumen del camionero"""
        cam = context.user_data['camionero']
        
        keyboard = [["✏️ Editar", "✅ Confirmar"], ["❌ Cancelar"]]
        
        await update.message.reply_text(
            "🚛 *NUEVO CAMIONERO*\n\n"
            "📋 *RESUMEN:*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"1. 👤 Nombre: *{cam.get('nombre', '')}*\n"
            f"2. 📱 Teléfono: *{cam.get('telefono', '')}*\n"
            f"3. 🚛 Tractora: *{cam.get('tractora', '')}*\n"
            f"4. 📦 Remolque: *{cam.get('remolque', '')}*\n"
            f"5. 📍 Ubicación: *{cam.get('ubicacion', '')}*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "¿Es correcto?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_CONFIRMAR
    
    async def cam_editar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pregunta qué campo editar"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            "✏️ *EDITAR CAMIONERO*\n\n"
            "¿Qué campo quieres editar? (1-5)\n\n"
            "1. 👤 Nombre\n"
            "2. 📱 Teléfono\n"
            "3. 🚛 Tractora\n"
            "4. 📦 Remolque\n"
            "5. 📍 Ubicación",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_EDITAR_CAMPO
    
    async def cam_editar_campo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recibe campo a editar y pide nuevo valor"""
        campo_num = update.message.text.strip()
        
        if campo_num not in self.campos_camionero:
            await update.message.reply_text("⚠️ Introduce un número del 1 al 5:")
            return CAM_EDITAR_CAMPO
        
        campo_key, campo_nombre = self.campos_camionero[campo_num]
        context.user_data['editando_campo'] = campo_key
        
        valor_actual = context.user_data['camionero'].get(campo_key, '')
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            f"✏️ *EDITAR {campo_nombre.upper()}*\n\n"
            f"Valor actual: *{valor_actual}*\n\n"
            "Escribe el nuevo valor:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CAM_EDITAR_CAMPO
    
    async def cam_guardar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda camionero en Excel"""
        cam = context.user_data['camionero']
        
        try:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb.active
            
            fila = 3
            while ws.cell(row=fila, column=5).value:
                fila += 1
            
            ws.cell(row=fila, column=2, value=cam['ubicacion'])
            ws.cell(row=fila, column=5, value=cam['nombre'])
            ws.cell(row=fila, column=7, value=cam['tractora'])
            ws.cell(row=fila, column=8, value=cam['remolque'])
            
            comentario = Comment(f"Tel. empresa: {cam['telefono']}", "Bot")
            ws.cell(row=fila, column=5).comment = comentario
            
            wb.save(self.excel_path)
            wb.close()
            
            logger.info(f"[GESTIONES] Camionero añadido: {cam['nombre']}")
            
            drive_ok = self._sync_to_drive()
            
            mensaje = f"✅ *¡CAMIONERO AÑADIDO!*\n\n👤 {cam['nombre']}\n🚛 {cam['tractora']}\n\n"
            mensaje += "☁️ _Sincronizado con Drive_" if drive_ok else "⚠️ _Guardado local_"
            
            await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            
        except Exception as e:
            logger.error(f"[GESTIONES] Error: {e}")
            await update.message.reply_text(f"❌ Error: {e}", reply_markup=ReplyKeyboardRemove())
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # ============================================================
    # AÑADIR VIAJE
    # ============================================================
    
    async def via_inicio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicio añadir viaje"""
        context.user_data['viaje'] = {}
        
        keyboard = [
            ["ZONA NORTE", "ZONA SUR"],
            ["ZONA CENTRO", "ZONA ESTE"],
            ["❌ Cancelar"]
        ]
        
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\n"
            "Paso 1/10\n\n"
            "🗺️ *¿Zona?*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_ZONA
    
    async def via_zona(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['viaje']['zona'] = update.message.text.upper().strip()
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\nPaso 2/10\n\n🏢 *¿Cliente?*\n\n_Ejemplo: HERO, NESTLE..._",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_CLIENTE
    
    async def via_volver_zona(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            ["ZONA NORTE", "ZONA SUR"],
            ["ZONA CENTRO", "ZONA ESTE"],
            ["❌ Cancelar"]
        ]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\nPaso 1/10\n\n🗺️ *¿Zona?*\n\n_Anterior: {context.user_data['viaje'].get('zona', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_ZONA
    
    async def via_cliente(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['viaje']['cliente'] = update.message.text.upper().strip()
        
        keyboard = [["⏭️ Saltar"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\nPaso 3/10\n\n🔢 *¿Nº Pedido?*\n\n_Ejemplo: 12345 (o Saltar)_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_NUM_PEDIDO
    
    async def via_volver_cliente(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\nPaso 2/10\n\n🏢 *¿Cliente?*\n\n_Anterior: {context.user_data['viaje'].get('cliente', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_CLIENTE
    
    async def via_num_pedido(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto = update.message.text.strip()
        try:
            context.user_data['viaje']['num_pedido'] = float(texto)
        except:
            context.user_data['viaje']['num_pedido'] = texto
        return await self._via_pedir_ref_cliente(update, context)
    
    async def via_saltar_num_pedido(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['viaje']['num_pedido'] = None
        return await self._via_pedir_ref_cliente(update, context)
    
    async def _via_pedir_ref_cliente(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["⏭️ Saltar"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\nPaso 4/10\n\n🏷️ *¿Ref. Cliente?*\n\n_Ejemplo: 251235 (o Saltar)_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_REF_CLIENTE
    
    async def via_volver_num_pedido(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["⏭️ Saltar"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\nPaso 3/10\n\n🔢 *¿Nº Pedido?*\n\n_Anterior: {context.user_data['viaje'].get('num_pedido', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_NUM_PEDIDO
    
    async def via_ref_cliente(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto = update.message.text.strip()
        try:
            context.user_data['viaje']['ref_cliente'] = float(texto)
        except:
            context.user_data['viaje']['ref_cliente'] = texto.upper()
        return await self._via_pedir_intercambio(update, context)
    
    async def via_saltar_ref_cliente(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['viaje']['ref_cliente'] = None
        return await self._via_pedir_intercambio(update, context)
    
    async def _via_pedir_intercambio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["✅ SÍ", "❌ NO"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\nPaso 5/10\n\n🔄 *¿Intercambio de palés?*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_INTERCAMBIO
    
    async def via_volver_ref_cliente(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["⏭️ Saltar"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\nPaso 4/10\n\n🏷️ *¿Ref. Cliente?*\n\n_Anterior: {context.user_data['viaje'].get('ref_cliente', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_REF_CLIENTE
    
    async def via_intercambio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto = update.message.text.strip().upper()
        context.user_data['viaje']['intercambio'] = "SI" if "SÍ" in texto or "SI" in texto else "NO"
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\nPaso 6/10\n\n📍 *¿Lugar de CARGA?*\n\n_Ejemplo: CALAHORRA_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_LUGAR_CARGA
    
    async def via_volver_intercambio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["✅ SÍ", "❌ NO"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\nPaso 5/10\n\n🔄 *¿Intercambio?*\n\n_Anterior: {context.user_data['viaje'].get('intercambio', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_INTERCAMBIO
    
    async def via_lugar_carga(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['viaje']['lugar_carga'] = update.message.text.upper().strip()
        context.user_data['viaje']['carga_adicional'] = None  # Resetear
        
        keyboard = [["➕ Sí", "➡️ No"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n"
            f"📍 Carga principal: *{context.user_data['viaje']['lugar_carga']}*\n\n"
            f"¿Hay otra carga adicional?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_CARGA_ADICIONAL
    
    async def via_pedir_carga_adicional(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pide el lugar de carga adicional"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\n📍 *¿Segunda carga?*\n\n_Ejemplo: TUDELA_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_CARGA_ADICIONAL_LUGAR
    
    async def via_carga_adicional_lugar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda carga adicional y pasa a descarga"""
        context.user_data['viaje']['carga_adicional'] = update.message.text.upper().strip()
        return await self._pedir_lugar_descarga(update, context)
    
    async def via_saltar_carga_adicional(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Salta carga adicional y pasa a descarga"""
        context.user_data['viaje']['carga_adicional'] = None
        return await self._pedir_lugar_descarga(update, context)
    
    async def via_volver_carga_adicional(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a preguntar carga adicional"""
        keyboard = [["➕ Sí", "➡️ No"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n"
            f"📍 Carga principal: *{context.user_data['viaje'].get('lugar_carga', '')}*\n\n"
            f"¿Hay otra carga adicional?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_CARGA_ADICIONAL
    
    async def _pedir_lugar_descarga(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pide lugar de descarga"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\n📍 *¿Lugar de DESCARGA?*\n\n_Ejemplo: BARCELONA_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_LUGAR_DESCARGA
    
    async def via_volver_carga(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a carga adicional o carga principal"""
        if context.user_data['viaje'].get('carga_adicional'):
            return await self.via_volver_carga_adicional(update, context)
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n📍 *¿Lugar de CARGA?*\n\n_Anterior: {context.user_data['viaje'].get('lugar_carga', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_LUGAR_CARGA
    
    async def via_lugar_descarga(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['viaje']['lugar_descarga'] = update.message.text.upper().strip()
        context.user_data['viaje']['descarga_adicional'] = None  # Resetear
        
        keyboard = [["➕ Sí", "➡️ No"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n"
            f"📍 Descarga principal: *{context.user_data['viaje']['lugar_descarga']}*\n\n"
            f"¿Hay otra descarga adicional?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_DESCARGA_ADICIONAL
    
    async def via_pedir_descarga_adicional(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pide el lugar de descarga adicional"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\n📍 *¿Segunda descarga?*\n\n_Ejemplo: VALENCIA_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_DESCARGA_ADICIONAL_LUGAR
    
    async def via_descarga_adicional_lugar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda descarga adicional y pasa a mercancía"""
        context.user_data['viaje']['descarga_adicional'] = update.message.text.upper().strip()
        return await self._pedir_mercancia(update, context)
    
    async def via_saltar_descarga_adicional(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Salta descarga adicional y pasa a mercancía"""
        context.user_data['viaje']['descarga_adicional'] = None
        return await self._pedir_mercancia(update, context)
    
    async def via_volver_descarga_adicional(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a preguntar descarga adicional"""
        keyboard = [["➕ Sí", "➡️ No"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n"
            f"📍 Descarga principal: *{context.user_data['viaje'].get('lugar_descarga', '')}*\n\n"
            f"¿Hay otra descarga adicional?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_DESCARGA_ADICIONAL
    
    async def via_volver_lugar_descarga_pre(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a pedir lugar de descarga"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n📍 *¿Lugar de DESCARGA?*\n\n_Anterior: {context.user_data['viaje'].get('lugar_descarga', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_LUGAR_DESCARGA
    
    async def via_volver_descarga(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a descarga adicional o descarga principal"""
        if context.user_data['viaje'].get('descarga_adicional'):
            return await self.via_volver_descarga_adicional(update, context)
        keyboard = [["➕ Sí", "➡️ No"], ["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n"
            f"📍 Descarga principal: *{context.user_data['viaje'].get('lugar_descarga', '')}*\n\n"
            f"¿Hay otra descarga adicional?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_DESCARGA_ADICIONAL
    
    async def _pedir_mercancia(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pide tipo de mercancía"""
        keyboard = [
            ["REFRIGERADO +2º", "CONGELADO -18º"],
            ["REFRIGERADO +5º", "SECO"],
            ["⬅️ Volver", "❌ Cancelar"]
        ]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\n📦 *¿Mercancía?*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_MERCANCIA
    
    async def via_volver_lugar_carga(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n📍 *¿Lugar de CARGA?*\n\n_Anterior: {context.user_data['viaje'].get('lugar_carga', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_LUGAR_CARGA
    
    async def via_volver_lugar_descarga(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n📍 *¿Lugar de DESCARGA?*\n\n_Anterior: {context.user_data['viaje'].get('lugar_descarga', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_LUGAR_DESCARGA
    
    async def via_mercancia(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['viaje']['mercancia'] = update.message.text.upper().strip()
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\n📏 *¿Kilómetros?*\n\n_Ejemplo: 450_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_KM
    
    async def via_volver_mercancia(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            ["REFRIGERADO +2º", "CONGELADO -18º"],
            ["REFRIGERADO +5º", "SECO"],
            ["⬅️ Volver", "❌ Cancelar"]
        ]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\n📦 *¿Mercancía?*\n\n_Anterior: {context.user_data['viaje'].get('mercancia', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_MERCANCIA
    
    async def via_km(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto = update.message.text.strip().replace("km", "").replace("KM", "").replace(" ", "")
        
        try:
            context.user_data['viaje']['km'] = float(texto)
        except:
            await update.message.reply_text("⚠️ Introduce solo el número:")
            return VIA_KM
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            "📦 *NUEVO VIAJE*\n\nPaso 10/10\n\n💰 *¿Precio (€)?*\n\n_Ejemplo: 850_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_PRECIO
    
    async def via_volver_km(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        await update.message.reply_text(
            f"📦 *NUEVO VIAJE*\n\nPaso 9/10\n\n📏 *¿Kilómetros?*\n\n_Anterior: {context.user_data['viaje'].get('km', '')}_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_KM
    
    async def via_precio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        texto = update.message.text.strip().replace("€", "").replace(" ", "")
        
        try:
            context.user_data['viaje']['precio'] = float(texto)
        except:
            await update.message.reply_text("⚠️ Introduce solo el número:")
            return VIA_PRECIO
        
        return await self.via_mostrar_resumen(update, context)
    
    async def via_mostrar_resumen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra resumen del viaje"""
        via = context.user_data['viaje']
        eur_km = via.get('precio', 0) / via.get('km', 1) if via.get('km', 0) > 0 else 0
        
        keyboard = [["✏️ Editar", "✅ Confirmar"], ["❌ Cancelar"]]
        
        # Formatear carga
        carga_str = via.get('lugar_carga', '')
        if via.get('carga_adicional'):
            carga_str += f" (+{via['carga_adicional']})"
        
        # Formatear descarga
        descarga_str = via.get('lugar_descarga', '')
        if via.get('descarga_adicional'):
            descarga_str += f" (+{via['descarga_adicional']})"
        
        resumen = "📦 *NUEVO VIAJE*\n\n📋 *RESUMEN:*\n━━━━━━━━━━━━━━━━━━━━\n"
        resumen += f"1. 🗺️ Zona: *{via.get('zona', '')}*\n"
        resumen += f"2. 🏢 Cliente: *{via.get('cliente', '')}*\n"
        resumen += f"3. 🔢 Nº Pedido: *{via.get('num_pedido', '-')}*\n"
        resumen += f"4. 🏷️ Ref. Cliente: *{via.get('ref_cliente', '-')}*\n"
        resumen += f"5. 🔄 Intercambio: *{via.get('intercambio', 'NO')}*\n"
        resumen += f"6. 📍 Carga: *{carga_str}*\n"
        resumen += f"7. 📍 Carga adicional: *{via.get('carga_adicional', '-')}*\n"
        resumen += f"8. 📍 Descarga: *{descarga_str}*\n"
        resumen += f"9. 📍 Descarga adicional: *{via.get('descarga_adicional', '-')}*\n"
        resumen += f"10. 📦 Mercancía: *{via.get('mercancia', '')}*\n"
        resumen += f"11. 📏 KM: *{via.get('km', 0):.0f}*\n"
        resumen += f"12. 💰 Precio: *{via.get('precio', 0):.0f}€*\n"
        resumen += f"━━━━━━━━━━━━━━━━━━━━\n"
        resumen += f"📊 Ratio: *{eur_km:.2f} €/km*\n\n"
        resumen += "¿Es correcto?"
        
        await update.message.reply_text(
            resumen,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_CONFIRMAR
    
    async def via_editar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pregunta qué campo editar"""
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            "✏️ *EDITAR VIAJE*\n\n"
            "¿Qué campo quieres editar? (1-12)\n\n"
            "1. 🗺️ Zona\n"
            "2. 🏢 Cliente\n"
            "3. 🔢 Nº Pedido\n"
            "4. 🏷️ Ref. Cliente\n"
            "5. 🔄 Intercambio\n"
            "6. 📍 Lugar Carga\n"
            "7. 📍 Carga Adicional\n"
            "8. 📍 Lugar Descarga\n"
            "9. 📍 Descarga Adicional\n"
            "10. 📦 Mercancía\n"
            "11. 📏 Kilómetros\n"
            "12. 💰 Precio",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_EDITAR_CAMPO
    
    async def via_editar_campo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recibe campo a editar"""
        campo_num = update.message.text.strip()
        
        if campo_num not in self.campos_viaje:
            await update.message.reply_text("⚠️ Introduce un número del 1 al 12:")
            return VIA_EDITAR_CAMPO
        
        campo_key, campo_nombre = self.campos_viaje[campo_num]
        context.user_data['editando_campo'] = campo_key
        
        valor_actual = context.user_data['viaje'].get(campo_key, '-')
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            f"✏️ *EDITAR {campo_nombre.split(' ', 1)[1].upper()}*\n\n"
            f"Valor actual: *{valor_actual}*\n\n"
            "Escribe el nuevo valor:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return VIA_EDITAR_VALOR
    
    async def via_editar_valor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda nuevo valor y vuelve al resumen"""
        campo = context.user_data.get('editando_campo')
        valor = update.message.text.strip()
        
        # Convertir según el campo
        if campo in ['km', 'precio', 'num_pedido']:
            try:
                valor = float(valor.replace("€", "").replace("km", "").replace("KM", ""))
            except:
                pass
        elif campo == 'intercambio':
            valor = "SI" if "SÍ" in valor.upper() or "SI" in valor.upper() else "NO"
        else:
            valor = valor.upper()
        
        context.user_data['viaje'][campo] = valor
        
        return await self.via_mostrar_resumen(update, context)
    
    async def via_guardar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda viaje en Excel"""
        via = context.user_data['viaje']
        
        try:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb.active
            
            fila = 3
            while ws.cell(row=fila, column=9).value:
                fila += 1
            
            ws.cell(row=fila, column=9, value=via.get('cliente'))
            if via.get('num_pedido'):
                ws.cell(row=fila, column=10, value=via['num_pedido'])
            if via.get('ref_cliente'):
                ws.cell(row=fila, column=11, value=via['ref_cliente'])
            ws.cell(row=fila, column=12, value=via.get('intercambio', 'NO'))
            
            # Lugar de carga
            ws.cell(row=fila, column=14, value=via.get('lugar_carga'))
            # Si hay carga adicional, añadir como nota/comentario
            if via.get('carga_adicional'):
                nota_carga = Comment(f"2 CARGAS: {via.get('lugar_carga')} + {via.get('carga_adicional')}", "Bot")
                ws.cell(row=fila, column=14).comment = nota_carga
            
            # Lugar de descarga
            ws.cell(row=fila, column=17, value=via.get('lugar_descarga'))
            # Si hay descarga adicional, añadir como nota/comentario
            if via.get('descarga_adicional'):
                nota_descarga = Comment(f"2 DESCARGAS: {via.get('lugar_descarga')} + {via.get('descarga_adicional')}", "Bot")
                ws.cell(row=fila, column=17).comment = nota_descarga
            
            ws.cell(row=fila, column=20, value=via.get('mercancia'))
            ws.cell(row=fila, column=23, value=via.get('precio'))
            ws.cell(row=fila, column=24, value=via.get('km'))
            ws.cell(row=fila, column=25, value=f"=W{fila}/X{fila}")
            
            # Observaciones: incluir zona y cargas/descargas adicionales
            observaciones = f"ZONA: {via.get('zona', '')}"
            if via.get('carga_adicional'):
                observaciones += f" | CARGA2: {via.get('carga_adicional')}"
            if via.get('descarga_adicional'):
                observaciones += f" | DESCARGA2: {via.get('descarga_adicional')}"
            ws.cell(row=fila, column=28, value=observaciones)
            
            wb.save(self.excel_path)
            wb.close()
            
            # Formatear mensaje
            carga_str = via.get('lugar_carga', '')
            if via.get('carga_adicional'):
                carga_str += f" + {via['carga_adicional']}"
            
            descarga_str = via.get('lugar_descarga', '')
            if via.get('descarga_adicional'):
                descarga_str += f" + {via['descarga_adicional']}"
            
            logger.info(f"[GESTIONES] Viaje añadido: {via.get('cliente')} {carga_str}→{descarga_str}")
            
            drive_ok = self._sync_to_drive()
            
            mensaje = f"✅ *¡VIAJE AÑADIDO!*\n\n🏢 {via.get('cliente')}\n📍 {carga_str} → {descarga_str}\n💰 {via.get('precio', 0):.0f}€\n\n"
            mensaje += "☁️ _Sincronizado con Drive_" if drive_ok else "⚠️ _Guardado local_"
            
            await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            
        except Exception as e:
            logger.error(f"[GESTIONES] Error: {e}")
            await update.message.reply_text(f"❌ Error: {e}", reply_markup=ReplyKeyboardRemove())
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # ============================================================
    # MODIFICAR VIAJE EXISTENTE
    # ============================================================
    
    async def mod_listar_viajes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lista los últimos 10 viajes sin asignar"""
        viajes = self._get_viajes_sin_asignar(10)
        
        logger.info(f"[GESTIONES] mod_listar_viajes encontró {len(viajes)} viajes")
        
        if not viajes:
            await update.message.reply_text(
                "📦 No hay viajes sin asignar para modificar.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Guardar en context.user_data
        context.user_data['viajes_lista'] = viajes
        context.user_data['tipo'] = 'viaje'
        
        mensaje = "✏️ *MODIFICAR VIAJE*\n\n📦 Últimos viajes sin asignar:\n\n"
        
        for i, v in enumerate(viajes, 1):
            precio = v.get('precio', 0)
            precio_str = f"{precio:.0f}€" if precio else "Sin precio"
            mensaje += f"*{i}.* {v.get('cliente', '?')} | {v.get('lugar_carga', '?')} → {v.get('lugar_descarga', '?')} | {precio_str}\n"
        
        mensaje += f"\n¿Cuál quieres modificar? (1-{len(viajes)})"
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MOD_ELEGIR_VIAJE
    
    async def mod_elegir_viaje(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Selecciona viaje a modificar"""
        texto = update.message.text.strip()
        logger.info(f"[GESTIONES] mod_elegir_viaje recibido: '{texto}'")
        
        viajes = context.user_data.get('viajes_lista', [])
        logger.info(f"[GESTIONES] viajes_lista tiene {len(viajes)} elementos")
        
        if not viajes:
            await update.message.reply_text("⚠️ No hay viajes en la lista. Vuelve a intentarlo.")
            return await self.mod_listar_viajes(update, context)
        
        try:
            num = int(texto)
            
            if num < 1 or num > len(viajes):
                await update.message.reply_text(f"⚠️ Introduce un número del 1 al {len(viajes)}:")
                return MOD_ELEGIR_VIAJE
            
            viaje = viajes[num - 1]
            context.user_data['viaje'] = viaje.copy()
            context.user_data['viaje_fila'] = viaje['fila']
            context.user_data['modificando'] = True
            
            logger.info(f"[GESTIONES] Viaje seleccionado fila {viaje['fila']}: {viaje.get('cliente')}")
            
            # Mostrar resumen y devolver MOD_CAMPO
            via = context.user_data['viaje']
            
            keyboard = [["✅ Guardar cambios"], ["⬅️ Volver", "❌ Cancelar"]]
            
            mensaje = "✏️ *MODIFICAR VIAJE*\n\n📋 *DATOS ACTUALES:*\n━━━━━━━━━━━━━━━━━━━━\n"
            mensaje += f"1. 🗺️ Zona: *{via.get('zona', '-')}*\n"
            mensaje += f"2. 🏢 Cliente: *{via.get('cliente', '-')}*\n"
            mensaje += f"3. 🔢 Nº Pedido: *{via.get('num_pedido', '-')}*\n"
            mensaje += f"4. 🏷️ Ref. Cliente: *{via.get('ref_cliente', '-')}*\n"
            mensaje += f"5. 🔄 Intercambio: *{via.get('intercambio', 'NO')}*\n"
            mensaje += f"6. 📍 Carga: *{via.get('lugar_carga', '-')}*\n"
            mensaje += f"7. 📍 Descarga: *{via.get('lugar_descarga', '-')}*\n"
            mensaje += f"8. 📦 Mercancía: *{via.get('mercancia', '-')}*\n"
            
            km = via.get('km', 0)
            precio = via.get('precio', 0)
            km_str = f"{km:.0f}" if km else "-"
            precio_str = f"{precio:.0f}€" if precio else "-"
            mensaje += f"9. 📏 KM: *{km_str}*\n"
            mensaje += f"10. 💰 Precio: *{precio_str}*\n"
            mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
            mensaje += "¿Qué campo quieres editar? (1-10)\n\nO pulsa *Guardar cambios* para terminar."
            
            await update.message.reply_text(
                mensaje,
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return MOD_CAMPO
            
        except ValueError:
            await update.message.reply_text(f"⚠️ Introduce un número del 1 al {len(viajes)}:")
            return MOD_ELEGIR_VIAJE
    
    async def mod_mostrar_resumen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra resumen del viaje a modificar"""
        via = context.user_data.get('viaje', {})
        
        keyboard = [["✅ Guardar cambios"], ["⬅️ Volver", "❌ Cancelar"]]
        
        mensaje = "✏️ *MODIFICAR VIAJE*\n\n📋 *DATOS ACTUALES:*\n━━━━━━━━━━━━━━━━━━━━\n"
        mensaje += f"1. 🗺️ Zona: *{via.get('zona', '-')}*\n"
        mensaje += f"2. 🏢 Cliente: *{via.get('cliente', '-')}*\n"
        mensaje += f"3. 🔢 Nº Pedido: *{via.get('num_pedido', '-')}*\n"
        mensaje += f"4. 🏷️ Ref. Cliente: *{via.get('ref_cliente', '-')}*\n"
        mensaje += f"5. 🔄 Intercambio: *{via.get('intercambio', 'NO')}*\n"
        mensaje += f"6. 📍 Carga: *{via.get('lugar_carga', '-')}*\n"
        mensaje += f"7. 📍 Descarga: *{via.get('lugar_descarga', '-')}*\n"
        mensaje += f"8. 📦 Mercancía: *{via.get('mercancia', '-')}*\n"
        
        km = via.get('km', 0)
        precio = via.get('precio', 0)
        km_str = f"{km:.0f}" if km else "-"
        precio_str = f"{precio:.0f}€" if precio else "-"
        mensaje += f"9. 📏 KM: *{km_str}*\n"
        mensaje += f"10. 💰 Precio: *{precio_str}*\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += "¿Qué campo quieres editar? (1-10)\n\nO pulsa *Guardar cambios* para terminar."
        
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MOD_CAMPO
    
    async def mod_volver_lista(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve a la lista de viajes"""
        return await self.mod_listar_viajes(update, context)
    
    async def mod_elegir_campo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Elige campo a modificar (viaje o camionero)"""
        campo_num = update.message.text.strip()
        tipo = context.user_data.get('tipo', 'viaje')
        
        if tipo == 'camionero':
            if campo_num not in self.campos_camionero:
                await update.message.reply_text("⚠️ Introduce un número del 1 al 5:")
                return MOD_CAMPO
            
            campo_key, campo_nombre = self.campos_camionero[campo_num]
            context.user_data['editando_campo'] = campo_key
            
            valor_actual = context.user_data.get('camionero', {}).get(campo_key, '-')
        else:
            if campo_num not in self.campos_viaje:
                await update.message.reply_text("⚠️ Introduce un número del 1 al 10:")
                return MOD_CAMPO
            
            campo_key, campo_nombre = self.campos_viaje[campo_num]
            context.user_data['editando_campo'] = campo_key
            
            valor_actual = context.user_data.get('viaje', {}).get(campo_key, '-')
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            f"✏️ *EDITAR {campo_nombre.split(' ', 1)[1].upper()}*\n\n"
            f"Valor actual: *{valor_actual}*\n\n"
            "Escribe el nuevo valor:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MOD_VALOR
    
    async def mod_nuevo_valor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda nuevo valor y muestra resumen"""
        campo = context.user_data.get('editando_campo')
        valor = update.message.text.strip()
        tipo = context.user_data.get('tipo', 'viaje')
        
        # Convertir valor según el campo
        if campo in ['km', 'precio']:
            try:
                valor = float(valor.replace("€", "").replace("km", "").replace("KM", ""))
            except:
                pass
        elif campo == 'num_pedido':
            try:
                valor = float(valor)
            except:
                pass
        elif campo == 'intercambio':
            valor = "SI" if "SÍ" in valor.upper() or "SI" in valor.upper() else "NO"
        elif campo == 'telefono':
            valor = valor.replace(" ", "").replace("+34", "")
        else:
            valor = valor.upper()
        
        # Guardar en el diccionario correcto
        if tipo == 'camionero':
            if 'camionero' not in context.user_data:
                context.user_data['camionero'] = {}
            context.user_data['camionero'][campo] = valor
            logger.info(f"[GESTIONES] Camionero campo '{campo}' actualizado a: {valor}")
            return await self._mod_mostrar_resumen_camionero(update, context)
        else:
            if 'viaje' not in context.user_data:
                context.user_data['viaje'] = {}
            context.user_data['viaje'][campo] = valor
            logger.info(f"[GESTIONES] Viaje campo '{campo}' actualizado a: {valor}")
            return await self._mod_mostrar_resumen_viaje(update, context)
    
    async def _mod_mostrar_resumen_viaje(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra resumen del viaje"""
        via = context.user_data.get('viaje', {})
        
        keyboard = [["✅ Guardar cambios"], ["⬅️ Volver", "❌ Cancelar"]]
        
        mensaje = "✏️ *MODIFICAR VIAJE*\n\n✅ Campo actualizado!\n\n📋 *DATOS ACTUALES:*\n━━━━━━━━━━━━━━━━━━━━\n"
        mensaje += f"1. 🗺️ Zona: *{via.get('zona', '-')}*\n"
        mensaje += f"2. 🏢 Cliente: *{via.get('cliente', '-')}*\n"
        mensaje += f"3. 🔢 Nº Pedido: *{via.get('num_pedido', '-')}*\n"
        mensaje += f"4. 🏷️ Ref. Cliente: *{via.get('ref_cliente', '-')}*\n"
        mensaje += f"5. 🔄 Intercambio: *{via.get('intercambio', 'NO')}*\n"
        mensaje += f"6. 📍 Carga: *{via.get('lugar_carga', '-')}*\n"
        mensaje += f"7. 📍 Descarga: *{via.get('lugar_descarga', '-')}*\n"
        mensaje += f"8. 📦 Mercancía: *{via.get('mercancia', '-')}*\n"
        
        km = via.get('km', 0)
        precio = via.get('precio', 0)
        km_str = f"{km:.0f}" if km else "-"
        precio_str = f"{precio:.0f}€" if precio else "-"
        mensaje += f"9. 📏 KM: *{km_str}*\n"
        mensaje += f"10. 💰 Precio: *{precio_str}*\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += "¿Editar otro campo? (1-10)\n\nO pulsa *Guardar cambios* para terminar."
        
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MOD_CAMPO
    
    async def _mod_mostrar_resumen_camionero(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra resumen del camionero"""
        cam = context.user_data.get('camionero', {})
        
        keyboard = [["✅ Guardar cambios"], ["⬅️ Volver", "❌ Cancelar"]]
        
        mensaje = "✏️ *MODIFICAR CAMIONERO*\n\n✅ Campo actualizado!\n\n📋 *DATOS ACTUALES:*\n━━━━━━━━━━━━━━━━━━━━\n"
        mensaje += f"1. 👤 Nombre: *{cam.get('nombre', '-')}*\n"
        mensaje += f"2. 📱 Teléfono: *{cam.get('telefono', '-')}*\n"
        mensaje += f"3. 🚛 Tractora: *{cam.get('tractora', '-')}*\n"
        mensaje += f"4. 📦 Remolque: *{cam.get('remolque', '-')}*\n"
        mensaje += f"5. 📍 Ubicación: *{cam.get('ubicacion', '-')}*\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += "¿Editar otro campo? (1-5)\n\nO pulsa *Guardar cambios* para terminar."
        
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MOD_CAMPO
    
    async def mod_guardar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda cambios en Excel (viaje o camionero)"""
        tipo = context.user_data.get('tipo', 'viaje')
        
        if tipo == 'camionero':
            return await self._mod_guardar_camionero(update, context)
        else:
            return await self._mod_guardar_viaje(update, context)
    
    async def _mod_guardar_viaje(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda cambios de viaje en Excel"""
        via = context.user_data.get('viaje', {})
        fila = context.user_data.get('viaje_fila')
        
        if not fila:
            await update.message.reply_text("❌ Error: No se encontró la fila del viaje")
            context.user_data.clear()
            return ConversationHandler.END
        
        try:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb.active
            
            ws.cell(row=fila, column=9, value=via.get('cliente'))
            ws.cell(row=fila, column=10, value=via.get('num_pedido'))
            ws.cell(row=fila, column=11, value=via.get('ref_cliente'))
            ws.cell(row=fila, column=12, value=via.get('intercambio', 'NO'))
            ws.cell(row=fila, column=14, value=via.get('lugar_carga'))
            ws.cell(row=fila, column=17, value=via.get('lugar_descarga'))
            ws.cell(row=fila, column=20, value=via.get('mercancia'))
            ws.cell(row=fila, column=23, value=via.get('precio'))
            ws.cell(row=fila, column=24, value=via.get('km'))
            ws.cell(row=fila, column=28, value=f"ZONA: {via.get('zona', '')}")
            
            wb.save(self.excel_path)
            wb.close()
            
            logger.info(f"[GESTIONES] Viaje modificado fila {fila}: {via.get('cliente')}")
            
            drive_ok = self._sync_to_drive()
            
            mensaje = f"✅ *¡VIAJE MODIFICADO!*\n\n🏢 {via.get('cliente')}\n📍 {via.get('lugar_carga')} → {via.get('lugar_descarga')}\n\n"
            mensaje += "☁️ _Sincronizado con Drive_" if drive_ok else "⚠️ _Guardado local_"
            
            await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            
        except Exception as e:
            logger.error(f"[GESTIONES] Error modificando viaje: {e}")
            await update.message.reply_text(f"❌ Error: {e}", reply_markup=ReplyKeyboardRemove())
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def _mod_guardar_camionero(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guarda cambios de camionero en Excel"""
        cam = context.user_data.get('camionero', {})
        fila = context.user_data.get('camionero_fila')
        
        if not fila:
            await update.message.reply_text("❌ Error: No se encontró la fila del camionero")
            context.user_data.clear()
            return ConversationHandler.END
        
        try:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb.active
            
            ws.cell(row=fila, column=2, value=cam.get('ubicacion'))
            ws.cell(row=fila, column=5, value=cam.get('nombre'))
            ws.cell(row=fila, column=7, value=cam.get('tractora'))
            ws.cell(row=fila, column=8, value=cam.get('remolque'))
            
            # Actualizar teléfono en comentario si existe
            if cam.get('telefono'):
                comentario = Comment(f"Tel. empresa: {cam['telefono']}", "Bot")
                ws.cell(row=fila, column=5).comment = comentario
            
            wb.save(self.excel_path)
            wb.close()
            
            logger.info(f"[GESTIONES] Camionero modificado fila {fila}: {cam.get('nombre')}")
            
            drive_ok = self._sync_to_drive()
            
            mensaje = f"✅ *¡CAMIONERO MODIFICADO!*\n\n👤 {cam.get('nombre')}\n🚛 {cam.get('tractora')}\n📍 {cam.get('ubicacion')}\n\n"
            mensaje += "☁️ _Sincronizado con Drive_" if drive_ok else "⚠️ _Guardado local_"
            
            await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            
        except Exception as e:
            logger.error(f"[GESTIONES] Error modificando camionero: {e}")
            await update.message.reply_text(f"❌ Error: {e}", reply_markup=ReplyKeyboardRemove())
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # ============================================================
    # MODIFICAR CAMIONERO EXISTENTE
    # ============================================================
    
    async def mod_listar_camioneros(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lista los camioneros"""
        camioneros = self._get_camioneros(10)
        
        if not camioneros:
            await update.message.reply_text(
                "🚛 No hay camioneros para modificar.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        context.user_data['camioneros_lista'] = camioneros
        
        mensaje = "✏️ *MODIFICAR CAMIONERO*\n\n🚛 Camioneros:\n\n"
        
        for i, c in enumerate(camioneros, 1):
            mensaje += f"*{i}.* {c.get('nombre', '?')} | {c.get('tractora', '?')}\n"
        
        mensaje += "\n¿Cuál quieres modificar? (1-10)"
        
        keyboard = [["⬅️ Volver", "❌ Cancelar"]]
        
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MOD_ELEGIR_CAMIONERO
    
    async def mod_elegir_camionero(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Selecciona camionero a modificar"""
        texto = update.message.text.strip()
        
        camioneros = context.user_data.get('camioneros_lista', [])
        
        if not camioneros:
            await update.message.reply_text("⚠️ No hay camioneros en la lista.")
            return await self.mod_listar_camioneros(update, context)
        
        try:
            num = int(texto)
            
            if num < 1 or num > len(camioneros):
                await update.message.reply_text(f"⚠️ Introduce un número del 1 al {len(camioneros)}:")
                return MOD_ELEGIR_CAMIONERO
            
            camionero = camioneros[num - 1]
            context.user_data['camionero'] = camionero.copy()
            context.user_data['camionero_fila'] = camionero['fila']
            context.user_data['modificando'] = True
            context.user_data['tipo'] = 'camionero'
            
            logger.info(f"[GESTIONES] Camionero seleccionado fila {camionero['fila']}: {camionero.get('nombre')}")
            
            # Mostrar resumen directamente
            cam = context.user_data['camionero']
            
            keyboard = [["✅ Guardar cambios"], ["⬅️ Volver", "❌ Cancelar"]]
            
            mensaje = "✏️ *MODIFICAR CAMIONERO*\n\n📋 *DATOS ACTUALES:*\n━━━━━━━━━━━━━━━━━━━━\n"
            mensaje += f"1. 👤 Nombre: *{cam.get('nombre', '-')}*\n"
            mensaje += f"2. 📱 Teléfono: *{cam.get('telefono', '-')}*\n"
            mensaje += f"3. 🚛 Tractora: *{cam.get('tractora', '-')}*\n"
            mensaje += f"4. 📦 Remolque: *{cam.get('remolque', '-')}*\n"
            mensaje += f"5. 📍 Ubicación: *{cam.get('ubicacion', '-')}*\n"
            mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
            mensaje += "¿Qué campo quieres editar? (1-5)\n\nO pulsa *Guardar cambios* para terminar."
            
            await update.message.reply_text(
                mensaje,
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return MOD_CAMPO
            
        except ValueError:
            await update.message.reply_text(f"⚠️ Introduce un número del 1 al {len(camioneros)}:")
            return MOD_ELEGIR_CAMIONERO
    
    async def mod_mostrar_resumen_camionero(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra resumen del camionero a modificar"""
        cam = context.user_data.get('camionero', {})
        
        keyboard = [["✅ Guardar cambios"], ["⬅️ Volver", "❌ Cancelar"]]
        
        mensaje = "✏️ *MODIFICAR CAMIONERO*\n\n📋 *DATOS ACTUALES:*\n━━━━━━━━━━━━━━━━━━━━\n"
        mensaje += f"1. 👤 Nombre: *{cam.get('nombre', '-')}*\n"
        mensaje += f"2. 📱 Teléfono: *{cam.get('telefono', '-')}*\n"
        mensaje += f"3. 🚛 Tractora: *{cam.get('tractora', '-')}*\n"
        mensaje += f"4. 📦 Remolque: *{cam.get('remolque', '-')}*\n"
        mensaje += f"5. 📍 Ubicación: *{cam.get('ubicacion', '-')}*\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += "¿Qué campo quieres editar? (1-5)\n\nO pulsa *Guardar cambios* para terminar."
        
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return MOD_CAMPO
    
    # ============================================================
    # CANCELAR
    # ============================================================
    
    async def cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela la operación"""
        context.user_data.clear()
        await update.message.reply_text("❌ Operación cancelada", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
