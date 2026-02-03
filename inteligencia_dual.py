"""
INTELIGENCIA DUAL - GPT + SQL
==============================
Version 10.0 - Gasolineras en ruta inteligentes + Disponibilidad conductor
"""

import os
import sqlite3
import logging
import asyncio
import threading
import urllib.parse
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from openai import OpenAI
from dotenv import load_dotenv
from interprete_gpt import interpretar_mensaje
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

def chat_libre(mensaje: str, nombre: str = "") -> str:
    try:
        nombre_corto = nombre.split()[0] if nombre else "compañero"
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Eres un asistente amigable para conductores de camión. Hablas con {nombre_corto}. Sé breve y usa emojis."},
                {"role": "user", "content": mensaje}
            ],
            temperature=0.8,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error chat_libre: {e}")
        return "🤖 Perdona, ¿qué me decías?"


class InteligenciaDual:
    
    def __init__(self, db_path: str, movildata_api=None):
        self.db_path = db_path
        self.movildata = movildata_api
        logger.info("[OK] Inteligencia Dual v10 inicializada")
    
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
                    ruta["destino_lat"], ruta["destino_lon"] = coords_carga
                    ruta["destino_nombre"] = lugar_carga
                elif dist_a_descarga > 5:
                    ruta["tiene_ruta"] = True
                    ruta["destino_lat"], ruta["destino_lon"] = coords_descarga
                    ruta["destino_nombre"] = lugar_descarga
        
        return ruta
    
    def _formatear_viaje_detallado(self, viaje: Dict, indice: int = 0, es_admin: bool = False) -> str:
        cliente = viaje.get('cliente', 'N/A')
        mercancia = viaje.get('mercancia', 'N/A')
        precio = viaje.get('precio', 0)
        km = viaje.get('km', 0)
        observaciones = viaje.get('observaciones', '')
        
        lugar_carga = viaje.get('lugar_carga', '')
        direccion_carga = viaje.get('direccion_carga', '')
        lugar_entrega = viaje.get('lugar_entrega', '')
        direccion_descarga = viaje.get('direccion_descarga', '')
        
        horarios = simular_horarios(viaje, indice)
        
        respuesta = f"📦 MERCANCÍA: {mercancia}\n"
        if es_admin and precio:
            respuesta += f"💰 {precio}€ | "
        if km:
            respuesta += f"📏 {km}km"
        respuesta += "\n"
        
        # CARGA
        respuesta += f"\n{'━'*30}\n📥 CARGA - {cliente}\n{'━'*30}\n"
        dir_carga = direccion_carga if direccion_carga and direccion_carga.lower() not in ['nan', 'none', ''] else lugar_carga
        if dir_carga:
            respuesta += f"📍 {dir_carga}\n📅 {horarios['fecha_carga']} a las {horarios['hora_carga']}\n"
            respuesta += f"🗺️ Maps: {generar_link_maps(dir_carga)}\n🚗 Waze: {generar_link_waze(dir_carga)}\n"
        
        # DESCARGA
        respuesta += f"\n{'━'*30}\n📤 DESCARGA\n{'━'*30}\n"
        dir_descarga = direccion_descarga if direccion_descarga and direccion_descarga.lower() not in ['nan', 'none', ''] else lugar_entrega
        if dir_descarga:
            respuesta += f"📍 {dir_descarga}\n📅 {horarios['fecha_descarga']} a las {horarios['hora_descarga']}\n"
            respuesta += f"🗺️ Maps: {generar_link_maps(dir_descarga)}\n🚗 Waze: {generar_link_waze(dir_descarga)}\n"
        
        if observaciones and str(observaciones).lower() not in ['nan', 'none', '']:
            respuesta += f"\n📝 NOTAS: {observaciones}"
        
        return respuesta
    
    def _buscar_gasolineras_inteligente(self, conductor: Dict, tractora: str, es_admin: bool = False) -> str:
        """
        Busca gasolineras de forma inteligente:
        1. Detecta si tiene viaje asignado
        2. Calcula la ruta
        3. Busca gasolineras EN RUTA
        4. Añade aviso de descanso si es necesario
        """
        nombre = conductor.get('nombre', '')
        viajes = self.obtener_mis_viajes(nombre)
        estado = self._obtener_estado_conductor(tractora)
        ruta = self._determinar_ruta_actual(tractora, viajes)
        
        respuesta = ""
        
        # Añadir aviso de descanso si es necesario
        if estado.get("necesita_descanso_pronto"):
            minutos = estado.get("minutos_hasta_descanso", 0)
            respuesta += f"⚠️ ATENCIÓN: Descanso obligatorio en {minutos} minutos\n\n"
        elif estado.get("minutos_hasta_descanso") and estado["minutos_hasta_descanso"] < 90:
            minutos = estado["minutos_hasta_descanso"]
            respuesta += f"⏰ Recuerda: Descanso en {minutos} minutos\n\n"
        
        # Si tiene ruta definida, buscar en ruta
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
        
        # Si no hay ruta, buscar por provincia
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
    
    def responder(self, telegram_id: int, mensaje: str, conductor: Dict, es_admin: bool = False) -> str:
        interpretacion = interpretar_mensaje(mensaje)
        intencion = interpretacion.get('intencion', 'no_entendido')
        parametros = interpretacion.get('parametros', {})
        confianza = interpretacion.get('confianza', 0)
        
        logger.info(f"[INTENT] {intencion} (conf={confianza}, admin={es_admin})")
        
        nombre = conductor.get('nombre', '')
        tractora = conductor.get('tractora', '')
        
        # SALUDOS
        if intencion == 'saludar':
            nombre_corto = nombre.split()[0] if nombre else 'compañero'
            perfil = "👔 Responsable" if es_admin else "🚛 Conductor"
            return f"👋 ¡Hola {nombre_corto}! ({perfil})\n¿Qué necesitas?"
        
        if intencion == 'despedir':
            return "👋 ¡Hasta luego! Buen viaje 🛣️"
        
        # MI VEHÍCULO
        if intencion == 'consultar_vehiculo':
            respuesta = f"🚛 TU CAMIÓN\n\nTractora: {tractora or 'N/A'}\nRemolque: {conductor.get('remolque', 'N/A')}\nBase: {conductor.get('ubicacion', 'N/A')}"
            if self.movildata and tractora:
                pos = self.movildata.get_last_location_plate(tractora)
                if pos:
                    respuesta += f"\n\n📡 GPS: {pos.get('municipio', 'N/A')} | {pos.get('velocidad', 0)} km/h"
            return respuesta
        
        # MIS VIAJES
        if intencion in ['consultar_viajes', 'proxima_entrega']:
            viajes = self.obtener_mis_viajes(nombre)
            if not viajes:
                return "📦 No tienes viajes asignados."
            
            respuesta = f"🚛 TUS VIAJES ({len(viajes)})\n"
            for i, v in enumerate(viajes[:3]):
                respuesta += f"\n{'═'*30}\n📋 VIAJE {i+1}\n{'═'*30}\n"
                respuesta += self._formatear_viaje_detallado(v, i, es_admin)
            
            if len(viajes) > 3:
                respuesta += f"\n\n📋 Tienes {len(viajes)-3} viaje(s) más."
            return respuesta
        
        # MI UBICACIÓN
        if intencion == 'consultar_ubicacion':
            if self.movildata and tractora:
                pos = self.movildata.get_last_location_plate(tractora)
                if pos:
                    return f"📍 TU POSICIÓN\n\n🚛 {tractora}\n📍 {pos.get('municipio', 'N/A')}, {pos.get('provincia', 'N/A')}\n🏎️ {pos.get('velocidad', 0)} km/h"
            return f"📍 Base: {conductor.get('ubicacion', 'N/A')}"
        
        # GASOLINERAS - INTELIGENTE
        if intencion == 'consultar_gasolineras':
            provincia_solicitada = parametros.get('ciudad', '') or parametros.get('provincia', '')
            
            # Si pide una provincia específica
            if provincia_solicitada:
                try:
                    resultado = run_async(obtener_gasolineras(provincia_solicitada, mostrar_precio=es_admin))
                    return resultado
                except Exception as e:
                    logger.error(f"Error gasolineras: {e}")
                    return f"⛽ Error al buscar en {provincia_solicitada}"
            
            # Si no, buscar de forma inteligente
            return self._buscar_gasolineras_inteligente(conductor, tractora, es_admin)
        
        # RESUMEN
        if intencion == 'consultar_resumen':
            if es_admin:
                viajes_total = len(self.obtener_todos_viajes())
                conductores = len(self.obtener_conductores())
                return f"📊 RESUMEN GENERAL\n\n👥 Conductores: {conductores}\n📦 Viajes: {viajes_total}"
            else:
                viajes = self.obtener_mis_viajes(nombre)
                return f"📊 TU RESUMEN\n\n👤 {nombre}\n🚛 {tractora or 'N/A'}\n📦 Viajes: {len(viajes)}"
        
        # NO ENTENDIDO → CHAT LIBRE
        if intencion == 'no_entendido' or confianza < 0.5:
            return chat_libre(mensaje, nombre)
        
        return chat_libre(mensaje, nombre)
