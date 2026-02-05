"""
INTELIGENCIA DUAL - GPT + SQL
==============================
Version 11.0 - Con soporte para GESTIONES por lenguaje natural
"""

import os
import sqlite3
import logging
import asyncio
import threading
import urllib.parse
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
from dotenv import load_dotenv
from interprete_gpt import interpretar_mensaje, es_intencion_gestion, INTENCIONES_GESTIONES
from apis_externas import obtener_gasolineras, obtener_gasolineras_en_ruta, calcular_distancia_km

load_dotenv()
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

COORDENADAS_LUGARES = {
    "MELIDA": (42.3833, -1.5500), "MÉLIDA": (42.3833, -1.5500),
    "MERIDA": (38.9161, -6.3436), "MÉRIDA": (38.9161, -6.3436),
    "CALAHORRA": (42.3050, -1.9653), "SAN ADRIAN": (42.3417, -1.9333),
    "TUDELA": (42.0617, -1.6067), "LOGROÑO": (42.4650, -2.4456),
    "PAMPLONA": (42.8125, -1.6458), "ZARAGOZA": (41.6488, -0.8891),
    "MADRID": (40.4168, -3.7038), "BARCELONA": (41.3851, 2.1734),
    "TORREJON DE ARDOZ": (40.4603, -3.4689), "VIC": (41.9304, 2.2546),
    "ALCANTARILLA": (37.9694, -1.2136), "AZAGRA": (42.3167, -1.8833),
    "GETAFE": (40.3047, -3.7311), "ARCHENA": (38.1167, -1.3000),
    "MURCIA": (37.9922, -1.1307),
}

def obtener_coordenadas_lugar(lugar: str) -> Optional[tuple]:
    if not lugar:
        return None
    return COORDENADAS_LUGARES.get(lugar.upper().strip())

def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        result = None
        exception = None
        def run():
            nonlocal result, exception
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                new_loop.close()
            except Exception as e:
                exception = e
        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=60)
        if exception:
            raise exception
        return result
    else:
        return asyncio.run(coro)

def generar_link_maps(direccion: str) -> str:
    if not direccion or direccion.lower() in ['nan', 'none', '']:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(direccion)}"

def generar_link_waze(direccion: str) -> str:
    if not direccion or direccion.lower() in ['nan', 'none', '']:
        return ""
    return f"https://waze.com/ul?q={urllib.parse.quote(direccion)}&navigate=yes"

def simular_horarios(viaje: Dict, indice_viaje: int = 0) -> Dict:
    ahora = datetime.now()
    km = viaje.get('km', 0) or 200
    minutos_hasta_carga = random.randint(60, 120) if indice_viaje == 0 else 180 + (indice_viaje * 240)
    hora_carga = ahora + timedelta(minutes=minutos_hasta_carga)
    hora_carga = hora_carga.replace(minute=(hora_carga.minute // 15) * 15, second=0, microsecond=0)
    horas_viaje = max(1, km / 75)
    hora_descarga = hora_carga + timedelta(minutes=int(horas_viaje * 60) + random.randint(20, 45))
    hora_descarga = hora_descarga.replace(minute=(hora_descarga.minute // 15) * 15, second=0, microsecond=0)
    return {
        "fecha_carga": hora_carga.strftime("%d/%m") if hora_carga.date() > ahora.date() else "Hoy",
        "hora_carga": hora_carga.strftime("%H:%M"),
        "fecha_descarga": hora_descarga.strftime("%d/%m") if hora_descarga.date() > hora_carga.date() else "Hoy",
        "hora_descarga": hora_descarga.strftime("%H:%M"),
    }

ASSISTANT_ID = "asst_DmmRrep6S45qhxWJ4TeUofaG"

# Historial de threads por usuario para mantener contexto
_threads_usuarios = {}

def chat_libre(mensaje: str, nombre: str = "", telegram_id: int = None) -> str:
    """Chat usando el Assistant de OpenAI para consultas de transporte"""
    try:
        nombre_corto = nombre.split()[0] if nombre else "compañero"
        
        # Reutilizar thread si el usuario ya tiene uno (mantiene contexto)
        thread_id = _threads_usuarios.get(telegram_id)
        
        if thread_id:
            try:
                # Verificar que el thread sigue válido
                client.beta.threads.retrieve(thread_id)
            except Exception:
                thread_id = None
        
        if not thread_id:
            thread = client.beta.threads.create()
            thread_id = thread.id
            if telegram_id:
                _threads_usuarios[telegram_id] = thread_id
        
        # Añadir mensaje del usuario
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=f"[Conductor: {nombre_corto}] {mensaje}"
        )
        
        # Ejecutar el Assistant
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID,
            timeout=30
        )
        
        if run.status == "completed":
            messages = client.beta.threads.messages.list(
                thread_id=thread_id,
                limit=1,
                order="desc"
            )
            respuesta = messages.data[0].content[0].text.value
            return respuesta
        else:
            logger.error(f"Assistant run status: {run.status}")
            return "🤖 Perdona, no he podido procesar tu consulta. Inténtalo de nuevo."
    
    except Exception as e:
        logger.error(f"Error chat_libre (Assistant): {e}")
        return "🤖 Perdona, ¿qué me decías?"


class InteligenciaDual:
    
    def __init__(self, db_path: str, movildata_api=None):
        self.db_path = db_path
        self.movildata = movildata_api
        logger.info("[OK] Inteligencia Dual v11 inicializada (con gestiones)")
    
    def _query(self, query: str, params: tuple = (), fetch_one: bool = False):
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
            logger.error(f"Error SQL: {e}")
            return None
    
    def obtener_mis_viajes(self, nombre: str) -> List[Dict]:
        return self._query("SELECT * FROM viajes_empresa WHERE conductor_asignado LIKE ?", (f"%{nombre}%",)) or []
    
    def obtener_todos_viajes(self) -> List[Dict]:
        return self._query("SELECT * FROM viajes_empresa") or []
    
    def obtener_conductores(self) -> List[Dict]:
        return self._query("SELECT * FROM conductores_empresa") or []
    
    def _obtener_estado_conductor(self, tractora: str) -> Dict:
        """Obtiene estado completo: GPS, velocidad, disponibilidad"""
        estado = {
            "lat": None, "lon": None, "velocidad": 0, "motor_encendido": False,
            "en_movimiento": False, "municipio": None, "provincia": None,
            "horas_restantes": None, "minutos_hasta_descanso": None, "necesita_descanso_pronto": False
        }
        
        if not self.movildata or not tractora:
            return estado
        
        pos = self.movildata.get_last_location_plate(tractora)
        if pos:
            estado["lat"] = pos.get("latitud")
            estado["lon"] = pos.get("longitud")
            estado["velocidad"] = pos.get("velocidad", 0)
            estado["motor_encendido"] = pos.get("motor_encendido", False)
            estado["en_movimiento"] = estado["velocidad"] > 5
            estado["municipio"] = pos.get("municipio")
            estado["provincia"] = pos.get("provincia")
        
        disp = self.movildata.get_disponibilidad_por_matricula(tractora)
        if disp:
            estado["horas_restantes"] = disp.get("horas_restantes_hoy", 0)
            estado["minutos_hasta_descanso"] = disp.get("minutos_hasta_descanso", 999)
            estado["necesita_descanso_pronto"] = disp.get("necesita_descanso_pronto", False)
        
        return estado
    
    def _determinar_ruta_actual(self, tractora: str, viajes: List[Dict]) -> Dict:
        """Determina la ruta actual basándose en GPS y viajes"""
        ruta = {"tiene_ruta": False, "origen_lat": None, "origen_lon": None,
                "destino_lat": None, "destino_lon": None, "destino_nombre": None}
        
        if not viajes:
            return ruta
        
        viaje = viajes[0]
        lugar_carga = viaje.get("lugar_carga", "")
        lugar_descarga = viaje.get("lugar_entrega", "")
        
        coords_carga = obtener_coordenadas_lugar(lugar_carga)
        coords_descarga = obtener_coordenadas_lugar(lugar_descarga)
        
        estado = self._obtener_estado_conductor(tractora)
        
        if estado["lat"] and estado["lon"]:
            ruta["origen_lat"] = estado["lat"]
            ruta["origen_lon"] = estado["lon"]
            
            if coords_carga and coords_descarga:
                dist_a_carga = calcular_distancia_km(estado["lat"], estado["lon"], coords_carga[0], coords_carga[1])
                dist_a_descarga = calcular_distancia_km(estado["lat"], estado["lon"], coords_descarga[0], coords_descarga[1])
                
                if dist_a_carga < dist_a_descarga and dist_a_carga > 5:
                    ruta["tiene_ruta"] = True
                    ruta["destino_lat"] = coords_carga[0]
                    ruta["destino_lon"] = coords_carga[1]
                    ruta["destino_nombre"] = lugar_carga
                elif dist_a_descarga > 5:
                    ruta["tiene_ruta"] = True
                    ruta["destino_lat"] = coords_descarga[0]
                    ruta["destino_lon"] = coords_descarga[1]
                    ruta["destino_nombre"] = lugar_descarga
        
        return ruta
    
    def _formatear_viaje_detallado(self, viaje: Dict, indice: int = 0, es_admin: bool = False) -> str:
        """Formatea un viaje con todos los detalles"""
        cliente = viaje.get('cliente', 'N/A')
        mercancia = viaje.get('tipo_mercancia', viaje.get('mercancia', 'N/A'))
        lugar_carga = viaje.get('lugar_carga', 'N/A')
        lugar_descarga = viaje.get('lugar_entrega', viaje.get('lugar_descarga', 'N/A'))
        km = viaje.get('km', 'N/A')
        observaciones = viaje.get('observaciones', '')
        
        dir_carga = viaje.get('direccion_carga', '')
        dir_descarga = viaje.get('direccion_descarga', '')
        
        horarios = simular_horarios(viaje, indice)
        
        respuesta = f"🏢 Cliente: {cliente}\n📦 Mercancía: {mercancia}\n\n"
        respuesta += f"📍 CARGA: {lugar_carga}\n"
        respuesta += f"   📅 {horarios['fecha_carga']} ⏰ {horarios['hora_carga']}\n"
        if dir_carga:
            respuesta += f"   🗺️ [Maps]({generar_link_maps(dir_carga)}) | [Waze]({generar_link_waze(dir_carga)})\n"
        
        respuesta += f"\n📍 DESCARGA: {lugar_descarga}\n"
        respuesta += f"   📅 {horarios['fecha_descarga']} ⏰ {horarios['hora_descarga']}\n"
        if dir_descarga:
            respuesta += f"   🗺️ [Maps]({generar_link_maps(dir_descarga)}) | [Waze]({generar_link_waze(dir_descarga)})\n"
        
        respuesta += f"\n📏 Distancia: {km} km"
        
        if es_admin and viaje.get('precio'):
            respuesta += f" | 💰 {viaje['precio']}€"
        
        if observaciones:
            respuesta += f"\n📝 Obs: {observaciones[:100]}"
        
        return respuesta
    
    def _buscar_gasolineras_inteligente(self, conductor: Dict, tractora: str, es_admin: bool = False) -> str:
        """Busca gasolineras de forma inteligente"""
        nombre = conductor.get('nombre', '')
        viajes = self.obtener_mis_viajes(nombre)
        estado = self._obtener_estado_conductor(tractora)
        ruta = self._determinar_ruta_actual(tractora, viajes)
        
        respuesta = ""
        
        if estado.get("necesita_descanso_pronto"):
            minutos = estado.get("minutos_hasta_descanso", 0)
            respuesta += f"⚠️ ATENCIÓN: Descanso obligatorio en {minutos} minutos\n\n"
        elif estado.get("minutos_hasta_descanso") and estado["minutos_hasta_descanso"] < 90:
            minutos = estado["minutos_hasta_descanso"]
            respuesta += f"⏰ Recuerda: Descanso en {minutos} minutos\n\n"
        
        if ruta["tiene_ruta"] and ruta["origen_lat"] and ruta["destino_lat"]:
            try:
                resultado = run_async(obtener_gasolineras_en_ruta(
                    ruta["origen_lat"], ruta["origen_lon"],
                    ruta["destino_lat"], ruta["destino_lon"],
                    mostrar_precio=es_admin,
                    limite=3
                ))
                respuesta += resultado
                return respuesta
            except Exception as e:
                logger.error(f"Error gasolineras en ruta: {e}")
        
        provincia = estado.get("provincia") or conductor.get("ubicacion", "")
        if provincia:
            mapeo = {'AZAGRA': 'Navarra', 'TUDELA': 'Navarra', 'CALAHORRA': 'La Rioja', 
                     'MELIDA': 'Navarra', 'ZARAGOZA': 'Zaragoza', 'MADRID': 'Madrid'}
            provincia = mapeo.get(provincia.upper(), provincia)
            
            try:
                resultado = run_async(obtener_gasolineras(
                    provincia, 
                    estado.get("lat"), 
                    estado.get("lon"),
                    mostrar_precio=es_admin
                ))
                respuesta += resultado
                return respuesta
            except Exception as e:
                logger.error(f"Error gasolineras provincia: {e}")
        
        return respuesta + "⛽ No pude encontrar gasolineras. Indica una provincia: 'gasolineras en Navarra'"
    
    def responder(self, telegram_id: int, mensaje: str, conductor: Dict, es_admin: bool = False) -> Tuple[str, Optional[str]]:
        """
        Responde al mensaje del usuario.
        
        Returns:
            Tuple[str, Optional[str]]: (respuesta_texto, accion_especial)
            
            accion_especial puede ser:
            - None: respuesta normal
            - 'añadir_conductor': iniciar flujo añadir conductor
            - 'añadir_viaje': iniciar flujo añadir viaje
            - 'modificar_conductor': iniciar flujo modificar conductor
            - 'modificar_viaje': iniciar flujo modificar viaje
            - 'menu_gestiones': mostrar menú de gestiones
        """
        interpretacion = interpretar_mensaje(mensaje)
        intencion = interpretacion.get('intencion', 'no_entendido')
        parametros = interpretacion.get('parametros', {})
        confianza = interpretacion.get('confianza', 0)
        
        logger.info(f"[INTENT] {intencion} (conf={confianza}, admin={es_admin})")
        
        nombre = conductor.get('nombre', '')
        tractora = conductor.get('tractora', '')
        
        # === GESTIONES (solo admin) ===
        if es_intencion_gestion(intencion):
            if not es_admin:
                return ("⚠️ Esta función solo está disponible para administradores.", None)
            
            # Devolver la acción especial para que el bot inicie el flujo
            if intencion == 'añadir_conductor':
                return ("🚛 Vamos a añadir un nuevo conductor...", 'añadir_conductor')
            elif intencion == 'añadir_viaje':
                return ("📦 Vamos a crear un nuevo viaje...", 'añadir_viaje')
            elif intencion == 'modificar_conductor':
                return ("✏️ Vamos a modificar un conductor...", 'modificar_conductor')
            elif intencion == 'modificar_viaje':
                return ("✏️ Vamos a modificar un viaje...", 'modificar_viaje')
            elif intencion == 'menu_gestiones':
                return ("🛠️ Abriendo menú de gestiones...", 'menu_gestiones')
        
        # === SALUDOS ===
        if intencion == 'saludar':
            nombre_corto = nombre.split()[0] if nombre else 'compañero'
            perfil = "👔 Responsable" if es_admin else "🚛 Conductor"
            return (f"👋 ¡Hola {nombre_corto}! ({perfil})\n¿Qué necesitas?", None)
        
        if intencion == 'despedir':
            return ("👋 ¡Hasta luego! Buen viaje 🛣️", None)
        
        # === MI VEHÍCULO ===
        if intencion == 'consultar_vehiculo':
            respuesta = f"🚛 TU CAMIÓN\n\nTractora: {tractora or 'N/A'}\nRemolque: {conductor.get('remolque', 'N/A')}\nBase: {conductor.get('ubicacion', 'N/A')}"
            if self.movildata and tractora:
                pos = self.movildata.get_last_location_plate(tractora)
                if pos:
                    respuesta += f"\n\n📡 GPS: {pos.get('municipio', 'N/A')} | {pos.get('velocidad', 0)} km/h"
            return (respuesta, None)
        
        # === MIS VIAJES ===
        if intencion in ['consultar_viajes', 'proxima_entrega']:
            viajes = self.obtener_mis_viajes(nombre)
            if not viajes:
                return ("📦 No tienes viajes asignados.", None)
            
            respuesta = f"🚛 TUS VIAJES ({len(viajes)})\n"
            for i, v in enumerate(viajes[:3]):
                respuesta += f"\n{'═'*30}\n📋 VIAJE {i+1}\n{'═'*30}\n"
                respuesta += self._formatear_viaje_detallado(v, i, es_admin)
            
            if len(viajes) > 3:
                respuesta += f"\n\n📋 Tienes {len(viajes)-3} viaje(s) más."
            return (respuesta, None)
        
        # === MI UBICACIÓN ===
        if intencion == 'consultar_ubicacion':
            if self.movildata and tractora:
                pos = self.movildata.get_last_location_plate(tractora)
                if pos:
                    return (f"📍 TU POSICIÓN\n\n🚛 {tractora}\n📍 {pos.get('municipio', 'N/A')}, {pos.get('provincia', 'N/A')}\n🏎️ {pos.get('velocidad', 0)} km/h", None)
            return (f"📍 Base: {conductor.get('ubicacion', 'N/A')}", None)
        
        # === GASOLINERAS ===
        if intencion == 'consultar_gasolineras':
            provincia_solicitada = parametros.get('ciudad', '') or parametros.get('provincia', '')
            
            if provincia_solicitada:
                try:
                    resultado = run_async(obtener_gasolineras(provincia_solicitada, mostrar_precio=es_admin))
                    return (resultado, None)
                except Exception as e:
                    logger.error(f"Error gasolineras: {e}")
                    return (f"⛽ Error al buscar en {provincia_solicitada}", None)
            
            return (self._buscar_gasolineras_inteligente(conductor, tractora, es_admin), None)
        
        # === RESUMEN ===
        if intencion == 'consultar_resumen':
            if es_admin:
                viajes_total = len(self.obtener_todos_viajes())
                conductores = len(self.obtener_conductores())
                return (f"📊 RESUMEN GENERAL\n\n👥 Conductores: {conductores}\n📦 Viajes: {viajes_total}", None)
            else:
                viajes = self.obtener_mis_viajes(nombre)
                return (f"📊 TU RESUMEN\n\n👤 {nombre}\n🚛 {tractora or 'N/A'}\n📦 Viajes: {len(viajes)}", None)
        
        # === NO ENTENDIDO → ASSISTANT TRANSPORTE ===
        if intencion == 'no_entendido' or confianza < 0.5:
            return (chat_libre(mensaje, nombre, telegram_id), None)
        
        return (chat_libre(mensaje, nombre, telegram_id), None)
    
    # Método legacy para compatibilidad (sin tupla)
    def responder_simple(self, telegram_id: int, mensaje: str, conductor: Dict, es_admin: bool = False) -> str:
        """Versión simple que solo devuelve texto (para compatibilidad)"""
        respuesta, _ = self.responder(telegram_id, mensaje, conductor, es_admin)
        return respuesta
