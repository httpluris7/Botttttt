# ============================================================
# REEMPLAZA LA FUNCIÓN mis_viajes EN bot_transporte.py
# ============================================================
# Versión 2.0 - Soporte hasta 10 cargas y 10 descargas

import urllib.parse
import random
import re
from datetime import datetime, timedelta

MAX_CARGAS = 10
MAX_DESCARGAS = 10


def generar_link_maps(direccion: str) -> str:
    """Genera link de Google Maps"""
    if not direccion or str(direccion).lower() in ['nan', 'none', '']:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(direccion)}"


def generar_link_waze(direccion: str) -> str:
    """Genera link de Waze"""
    if not direccion or str(direccion).lower() in ['nan', 'none', '']:
        return ""
    return f"https://waze.com/ul?q={urllib.parse.quote(direccion)}&navigate=yes"


def extraer_cargas_adicionales(observaciones: str) -> dict:
    """
    Extrae TODAS las cargas y descargas adicionales de las observaciones.
    Soporta hasta CARGA2..CARGA10 y DESCARGA2..DESCARGA10.
    
    Returns:
        dict con 'cargas_extra': [lista], 'descargas_extra': [lista]
        Y también mantiene 'carga2'/'descarga2' para compatibilidad
    """
    resultado = {
        'carga2': None,
        'descarga2': None,
        'cargas_extra': [],     # Todas las cargas adicionales (2,3,4...)
        'descargas_extra': [],  # Todas las descargas adicionales
    }
    
    if not observaciones:
        return resultado
    
    # Extraer cargas adicionales (CARGA2..CARGA10)
    for i in range(2, MAX_CARGAS + 1):
        match = re.search(rf'CARGA{i}:\s*([^|]+)', observaciones)
        if match:
            valor = match.group(1).strip()
            resultado['cargas_extra'].append(valor)
            if i == 2:
                resultado['carga2'] = valor
    
    # Extraer descargas adicionales (DESCARGA2..DESCARGA10)
    for i in range(2, MAX_DESCARGAS + 1):
        match = re.search(rf'DESCARGA{i}:\s*([^|]+)', observaciones)
        if match:
            valor = match.group(1).strip()
            resultado['descargas_extra'].append(valor)
            if i == 2:
                resultado['descarga2'] = valor
    
    return resultado


def simular_horarios(km: int, indice_viaje: int = 0) -> dict:
    """Genera horarios realistas basados en km"""
    ahora = datetime.now()
    
    if indice_viaje == 0:
        minutos_hasta_carga = random.randint(60, 120)
    else:
        minutos_hasta_carga = 180 + (indice_viaje * 240)
    
    hora_carga = ahora + timedelta(minutes=minutos_hasta_carga)
    hora_carga = hora_carga.replace(minute=(hora_carga.minute // 15) * 15, second=0)
    
    km = km or 200
    horas_viaje = max(1, km / 75)
    minutos_viaje = int(horas_viaje * 60) + random.randint(20, 45)
    
    hora_descarga = hora_carga + timedelta(minutes=minutos_viaje)
    hora_descarga = hora_descarga.replace(minute=(hora_descarga.minute // 15) * 15, second=0)
    
    return {
        "fecha_carga": hora_carga.strftime("%d/%m") if hora_carga.date() > ahora.date() else "Hoy",
        "hora_carga": hora_carga.strftime("%H:%M"),
        "fecha_descarga": hora_descarga.strftime("%d/%m") if hora_descarga.date() > ahora.date() else "Hoy",
        "hora_descarga": hora_descarga.strftime("%H:%M"),
    }


async def mis_viajes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mis viajes asignados - FORMATO CON HASTA 10 CARGAS/DESCARGAS"""
    user = update.effective_user
    conductor = db.obtener_conductor(user.id)
    admin = es_admin(user.id)
    
    if not conductor:
        await update.message.reply_text("❌ Primero /start")
        return
    
    viajes = db.obtener_viajes_conductor(conductor['nombre'])
    
    if not viajes:
        await update.message.reply_text("📦 No tienes viajes asignados.")
        return
    
    mensaje = f"🚛 TUS VIAJES ({len(viajes)})\n"
    
    for i, v in enumerate(viajes[:3]):
        cliente = v.get('cliente', 'N/A')
        mercancia = v.get('mercancia', 'N/A')
        km = v.get('km', 0) or 0
        intercambio = v.get('intercambio', '')
        observaciones = v.get('observaciones', '')
        
        # Extraer todas las cargas/descargas adicionales
        adicionales = extraer_cargas_adicionales(observaciones)
        
        # Lugar principal (usar dirección si existe)
        lugar_carga = v.get('direccion_carga') or v.get('lugar_carga', '')
        lugar_descarga = v.get('direccion_descarga') or v.get('lugar_entrega', '')
        
        if str(lugar_carga).lower() in ['nan', 'none', '']:
            lugar_carga = v.get('lugar_carga', 'Sin especificar')
        if str(lugar_descarga).lower() in ['nan', 'none', '']:
            lugar_descarga = v.get('lugar_entrega', 'Sin especificar')
        
        # Construir lista completa de cargas y descargas
        todas_cargas = [lugar_carga] + adicionales['cargas_extra']
        todas_descargas = [lugar_descarga] + adicionales['descargas_extra']
        
        horarios = simular_horarios(km, i)
        hay_intercambio = intercambio and str(intercambio).upper().strip() == 'SI'
        
        mensaje += f"\n{'═'*30}\n"
        mensaje += f"📋 VIAJE {i+1}\n"
        mensaje += f"{'═'*30}\n"
        
        mensaje += f"📦 MERCANCÍA: {mercancia}\n"
        mensaje += f"📏 {km}km"
        if hay_intercambio:
            mensaje += f" | 🔄 Intercambio de palés"
        mensaje += "\n"
        
        # ══════ CARGAS ══════
        mensaje += f"\n{'━'*30}\n"
        mensaje += f"📥 CARGAS ({len(todas_cargas)}) - {cliente}\n"
        mensaje += f"{'━'*30}\n"
        
        for j, carga in enumerate(todas_cargas):
            etiqueta = f"{j+1}ª Carga"
            mensaje += f"\n📍 {etiqueta}: {carga}\n"
            link_maps = generar_link_maps(carga)
            link_waze = generar_link_waze(carga)
            if link_maps:
                mensaje += f"🗺️ Maps: {link_maps}\n"
            if link_waze:
                mensaje += f"🚗 Waze: {link_waze}\n"
        
        if hay_intercambio:
            mensaje += f"\n🔄 Intercambio de palés\n"
        mensaje += f"\n📅 {horarios['fecha_carga']} a las {horarios['hora_carga']}\n"
        
        # ══════ DESCARGAS ══════
        mensaje += f"\n{'━'*30}\n"
        mensaje += f"📤 DESCARGAS ({len(todas_descargas)})\n"
        mensaje += f"{'━'*30}\n"
        
        for j, descarga in enumerate(todas_descargas):
            etiqueta = f"{j+1}ª Descarga"
            mensaje += f"\n📍 {etiqueta}: {descarga}\n"
            link_maps = generar_link_maps(descarga)
            link_waze = generar_link_waze(descarga)
            if link_maps:
                mensaje += f"🗺️ Maps: {link_maps}\n"
            if link_waze:
                mensaje += f"🚗 Waze: {link_waze}\n"
        
        mensaje += f"\n📅 {horarios['fecha_descarga']} a las {horarios['hora_descarga']}\n"
        
        # Observaciones (limpias, sin códigos internos)
        obs_limpia = observaciones
        if obs_limpia:
            # Quitar todos los CARGAN y DESCARGAN de las observaciones visibles
            for n in range(2, MAX_CARGAS + 1):
                obs_limpia = re.sub(rf'\s*\|\s*CARGA{n}:[^|]+', '', obs_limpia)
            for n in range(2, MAX_DESCARGAS + 1):
                obs_limpia = re.sub(rf'\s*\|\s*DESCARGA{n}:[^|]+', '', obs_limpia)
            obs_limpia = obs_limpia.strip()
            if obs_limpia and str(obs_limpia).lower() not in ['nan', 'none', '']:
                mensaje += f"\n📝 NOTAS: {obs_limpia}\n"
    
    if len(viajes) > 3:
        mensaje += f"\n\n📋 Tienes {len(viajes) - 3} viaje(s) más."
    
    await update.message.reply_text(mensaje)
