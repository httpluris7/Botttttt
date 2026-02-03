# ============================================================
# REEMPLAZA LA FUNCIÓN mis_viajes EN bot_transporte.py
# ============================================================
# Busca la función actual (líneas ~471-497) y reemplázala por esta:

import urllib.parse
import random
import re
from datetime import datetime, timedelta

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
    """Extrae cargas y descargas adicionales de las observaciones"""
    resultado = {'carga2': None, 'descarga2': None}
    
    if not observaciones:
        return resultado
    
    # Buscar CARGA2: xxx
    match_carga = re.search(r'CARGA2:\s*([^|]+)', observaciones)
    if match_carga:
        resultado['carga2'] = match_carga.group(1).strip()
    
    # Buscar DESCARGA2: xxx
    match_descarga = re.search(r'DESCARGA2:\s*([^|]+)', observaciones)
    if match_descarga:
        resultado['descarga2'] = match_descarga.group(1).strip()
    
    return resultado

def simular_horarios(km: int, indice_viaje: int = 0) -> dict:
    """Genera horarios realistas basados en km"""
    ahora = datetime.now()
    
    # Primer viaje: carga en 1-2h, siguientes: +3-4h por viaje
    if indice_viaje == 0:
        minutos_hasta_carga = random.randint(60, 120)
    else:
        minutos_hasta_carga = 180 + (indice_viaje * 240)
    
    hora_carga = ahora + timedelta(minutes=minutos_hasta_carga)
    hora_carga = hora_carga.replace(minute=(hora_carga.minute // 15) * 15, second=0)
    
    # Tiempo de viaje: ~75km/h + margen
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
    """Mis viajes asignados - FORMATO DETALLADO CON CARGAS/DESCARGAS ADICIONALES"""
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
    
    for i, v in enumerate(viajes[:3]):  # Máximo 3 viajes
        cliente = v.get('cliente', 'N/A')
        mercancia = v.get('mercancia', 'N/A')
        km = v.get('km', 0) or 0
        intercambio = v.get('intercambio', '')
        observaciones = v.get('observaciones', '')
        
        # Extraer cargas/descargas adicionales de observaciones
        adicionales = extraer_cargas_adicionales(observaciones)
        
        # Lugares (usar direcciones si existen, si no lugares)
        lugar_carga = v.get('direccion_carga') or v.get('lugar_carga', '')
        lugar_descarga = v.get('direccion_descarga') or v.get('lugar_entrega', '')
        
        # Limpiar valores nulos
        if str(lugar_carga).lower() in ['nan', 'none', '']:
            lugar_carga = v.get('lugar_carga', 'Sin especificar')
        if str(lugar_descarga).lower() in ['nan', 'none', '']:
            lugar_descarga = v.get('lugar_entrega', 'Sin especificar')
        
        # Horarios simulados
        horarios = simular_horarios(km, i)
        
        # Detectar intercambio
        hay_intercambio = intercambio and str(intercambio).upper().strip() == 'SI'
        
        mensaje += f"\n{'═'*30}\n"
        mensaje += f"📋 VIAJE {i+1}\n"
        mensaje += f"{'═'*30}\n"
        
        # Mercancía y KM
        mensaje += f"📦 MERCANCÍA: {mercancia}\n"
        mensaje += f"📏 {km}km"
        if hay_intercambio:
            mensaje += f" | 🔄 Intercambio de palés"
        mensaje += "\n"
        
        # ══════ CARGA ══════
        mensaje += f"\n{'━'*30}\n"
        mensaje += f"📥 CARGA - {cliente}\n"
        mensaje += f"{'━'*30}\n"
        
        # Mostrar carga principal
        mensaje += f"📍 1ª Carga: {lugar_carga}\n"
        link_maps = generar_link_maps(lugar_carga)
        link_waze = generar_link_waze(lugar_carga)
        if link_maps:
            mensaje += f"🗺️ Maps: {link_maps}\n"
        if link_waze:
            mensaje += f"🚗 Waze: {link_waze}\n"
        
        # Si hay carga adicional, mostrarla
        if adicionales['carga2']:
            mensaje += f"\n📍 2ª Carga: {adicionales['carga2']}\n"
            link_maps2 = generar_link_maps(adicionales['carga2'])
            link_waze2 = generar_link_waze(adicionales['carga2'])
            if link_maps2:
                mensaje += f"🗺️ Maps: {link_maps2}\n"
            if link_waze2:
                mensaje += f"🚗 Waze: {link_waze2}\n"
        
        if hay_intercambio:
            mensaje += f"🔄 Intercambio de palés\n"
        mensaje += f"📅 {horarios['fecha_carga']} a las {horarios['hora_carga']}\n"
        
        # ══════ DESCARGA ══════
        mensaje += f"\n{'━'*30}\n"
        mensaje += f"📤 DESCARGA\n"
        mensaje += f"{'━'*30}\n"
        
        # Mostrar descarga principal
        mensaje += f"📍 1ª Descarga: {lugar_descarga}\n"
        link_maps = generar_link_maps(lugar_descarga)
        link_waze = generar_link_waze(lugar_descarga)
        if link_maps:
            mensaje += f"🗺️ Maps: {link_maps}\n"
        if link_waze:
            mensaje += f"🚗 Waze: {link_waze}\n"
        
        # Si hay descarga adicional, mostrarla
        if adicionales['descarga2']:
            mensaje += f"\n📍 2ª Descarga: {adicionales['descarga2']}\n"
            link_maps2 = generar_link_maps(adicionales['descarga2'])
            link_waze2 = generar_link_waze(adicionales['descarga2'])
            if link_maps2:
                mensaje += f"🗺️ Maps: {link_maps2}\n"
            if link_waze2:
                mensaje += f"🚗 Waze: {link_waze2}\n"
        
        mensaje += f"📅 {horarios['fecha_descarga']} a las {horarios['hora_descarga']}\n"
        
        # Observaciones (sin mostrar los códigos internos)
        obs_limpia = observaciones
        if obs_limpia:
            # Quitar CARGA2 y DESCARGA2 de las observaciones visibles
            obs_limpia = re.sub(r'\s*\|\s*CARGA2:[^|]+', '', obs_limpia)
            obs_limpia = re.sub(r'\s*\|\s*DESCARGA2:[^|]+', '', obs_limpia)
            obs_limpia = obs_limpia.strip()
            if obs_limpia and str(obs_limpia).lower() not in ['nan', 'none', '']:
                mensaje += f"\n📝 NOTAS: {obs_limpia}\n"
    
    # Si hay más viajes
    if len(viajes) > 3:
        mensaje += f"\n\n📋 Tienes {len(viajes) - 3} viaje(s) más."
    
    await update.message.reply_text(mensaje)
