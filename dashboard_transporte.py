"""
DASHBOARD TRANSPORTE - Streamlit + ML
=======================================
Panel de analítica con Machine Learning para COSMOSDATA.

INSTALAR:
    pip install streamlit plotly pandas scikit-learn

EJECUTAR:
    streamlit run dashboard_transporte.py --server.port 8501 --server.address 0.0.0.0
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import os
import math
from datetime import datetime, timedelta, date

# ML
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import r2_score, mean_absolute_error

# ================================================================
# CONFIG
# ================================================================
DB_PATH = os.getenv("DB_PATH", "/root/bot-transporte/Botttttt/logistica.db")

st.set_page_config(
    page_title="🚛 COSMOSDATA Analytics",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .block-container {padding-top: 1rem;}
    div[data-testid="stMetricValue"] {font-size: 1.8rem;}
    .stTabs [data-baseweb="tab-list"] {gap: 8px;}
    .stTabs [data-baseweb="tab"] {
        background-color: #f0f2f6; border-radius: 8px; padding: 8px 16px;
    }
</style>
""", unsafe_allow_html=True)


# ================================================================
# DATA LAYER
# ================================================================
@st.cache_data(ttl=60)
def cargar_datos():
    """Carga todos los datos de la BD."""
    conn = sqlite3.connect(DB_PATH)

    df_viajes = pd.read_sql_query("SELECT * FROM viajes_empresa", conn)
    df_conductores = pd.read_sql_query(
        "SELECT * FROM conductores_empresa WHERE nombre IS NOT NULL AND nombre != ''", conn
    )
    df_vehiculos = pd.read_sql_query("SELECT * FROM vehiculos_empresa", conn)

    # Tablas de analítica (pueden no existir)
    try:
        df_eventos = pd.read_sql_query("SELECT * FROM eventos_operativos", conn)
    except Exception:
        df_eventos = pd.DataFrame()
    try:
        df_metricas = pd.read_sql_query("SELECT * FROM metricas_diarias", conn)
    except Exception:
        df_metricas = pd.DataFrame()
    try:
        df_historico = pd.read_sql_query("SELECT * FROM historico_viajes", conn)
    except Exception:
        df_historico = pd.DataFrame()

    conn.close()

    # Enriquecer viajes
    if not df_viajes.empty:
        df_viajes['tiene_conductor'] = (
            df_viajes['conductor_asignado'].notna() & (df_viajes['conductor_asignado'] != '')
        )
        df_viajes['eur_km'] = np.where(
            df_viajes['km'] > 0, (df_viajes['precio'] / df_viajes['km']).round(3), 0
        )
        df_viajes['mercancia_grupo'] = df_viajes['mercancia'].apply(normalizar_mercancia)
        # Ruta como texto
        df_viajes['ruta'] = df_viajes['lugar_carga'].fillna('?') + ' → ' + df_viajes['lugar_entrega'].fillna('?')

    return df_viajes, df_conductores, df_vehiculos, df_eventos, df_metricas, df_historico


def normalizar_mercancia(m):
    if not m or not isinstance(m, str):
        return 'OTRO'
    m = m.upper()
    if 'CONGEL' in m:
        return 'CONGELADO'
    elif 'REFRIG' in m or 'REFIG' in m:
        return 'REFRIGERADO'
    elif 'SECO' in m:
        return 'SECO'
    return 'OTRO'


# ================================================================
# ML MODELS
# ================================================================
@st.cache_resource(ttl=300)
def entrenar_modelo_precio(_df_json):
    """Entrena modelo de predicción de precios."""
    df = pd.read_json(_df_json)
    df_ml = df[(df['km'] > 0) & (df['precio'] > 0) & df['mercancia_grupo'].notna() & df['zona'].notna()].copy()

    if len(df_ml) < 10:
        return None, None, None, None

    le_mercancia = LabelEncoder()
    le_zona = LabelEncoder()
    le_cliente = LabelEncoder()

    df_ml['mercancia_enc'] = le_mercancia.fit_transform(df_ml['mercancia_grupo'])
    df_ml['zona_enc'] = le_zona.fit_transform(df_ml['zona'])
    df_ml['cliente_enc'] = le_cliente.fit_transform(df_ml['cliente'].fillna('OTRO'))

    features = ['km', 'mercancia_enc', 'zona_enc', 'cliente_enc']
    X = df_ml[features].values
    y = df_ml['precio'].values

    modelo = GradientBoostingRegressor(
        n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42, min_samples_leaf=3
    )
    modelo.fit(X, y)

    y_pred = modelo.predict(X)
    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)
    cv_r2 = r2
    if len(df_ml) >= 20:
        cv_scores = cross_val_score(modelo, X, y, cv=min(5, len(df_ml) // 4), scoring='r2')
        cv_r2 = cv_scores.mean()

    encoders = {'mercancia': le_mercancia, 'zona': le_zona, 'cliente': le_cliente}
    metricas = {'r2': r2, 'mae': mae, 'cv_r2': cv_r2, 'n_train': len(df_ml)}

    return modelo, encoders, features, metricas


@st.cache_resource(ttl=300)
def segmentar_clientes(_df_json):
    """Segmenta clientes con K-Means."""
    df = pd.read_json(_df_json)
    df_cli = df[df['precio'] > 0].groupby('cliente').agg(
        viajes=('id', 'count'), facturacion=('precio', 'sum'),
        km_medio=('km', 'mean'), precio_medio=('precio', 'mean'), eur_km_medio=('eur_km', 'mean'),
    ).reset_index()

    if len(df_cli) < 4:
        return df_cli, None

    feat = ['viajes', 'facturacion', 'precio_medio', 'eur_km_medio']
    X = df_cli[feat].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = min(4, len(df_cli))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df_cli['segmento'] = kmeans.fit_predict(X_scaled)

    nombres = {}
    for seg in range(n_clusters):
        g = df_cli[df_cli['segmento'] == seg]
        high_f = g['facturacion'].mean() > df_cli['facturacion'].median()
        high_v = g['viajes'].mean() > df_cli['viajes'].median()
        if high_f and high_v:
            nombres[seg] = '⭐ Premium'
        elif high_f:
            nombres[seg] = '💎 Alto valor'
        elif high_v:
            nombres[seg] = '📦 Volumen'
        else:
            nombres[seg] = '🌱 Crecimiento'
    df_cli['segmento_nombre'] = df_cli['segmento'].map(nombres)

    return df_cli, kmeans


def detectar_anomalias_precio(df):
    """Detecta precios anómalos via Z-score por mercancía."""
    df_a = df[(df['km'] > 0) & (df['precio'] > 0)].copy()
    if len(df_a) < 5:
        return pd.DataFrame()

    medias = df_a.groupby('mercancia_grupo')['eur_km'].agg(['mean', 'std']).reset_index()
    medias.columns = ['mercancia_grupo', 'eur_km_media', 'eur_km_std']
    df_a = df_a.merge(medias, on='mercancia_grupo', how='left')
    df_a['eur_km_std'] = df_a['eur_km_std'].fillna(0.1)
    df_a['z_score'] = (df_a['eur_km'] - df_a['eur_km_media']) / df_a['eur_km_std'].clip(lower=0.01)
    df_a['anomalia'] = df_a['z_score'].abs() > 1.5
    return df_a[df_a['anomalia']].sort_values('z_score')


def predecir_conductor_optimo(df_viajes, df_conductores):
    """Sugiere mejor conductor para cada viaje sin asignar basándose en historial."""
    sin_asignar = df_viajes[~df_viajes['tiene_conductor']].copy()
    if sin_asignar.empty or len(df_viajes[df_viajes['tiene_conductor']]) < 5:
        return pd.DataFrame()

    # Historial: qué conductores han hecho rutas similares
    asignados = df_viajes[df_viajes['tiene_conductor']].copy()

    resultados = []
    for _, viaje in sin_asignar.iterrows():
        zona = viaje.get('zona', '')
        mercancia = viaje.get('mercancia_grupo', '')

        # Conductores que han operado en esa zona con esa mercancía
        candidatos = asignados[
            (asignados['zona'] == zona)
        ].groupby('conductor_asignado').agg(
            viajes_zona=('id', 'count'),
            km_total=('km', 'sum'),
        ).reset_index().sort_values('viajes_zona', ascending=False)

        if candidatos.empty:
            sugerencia = 'Sin datos suficientes'
            score = 0
        else:
            sugerencia = candidatos.iloc[0]['conductor_asignado']
            score = min(100, candidatos.iloc[0]['viajes_zona'] * 20)

        resultados.append({
            'viaje_id': viaje['id'],
            'cliente': viaje['cliente'],
            'ruta': viaje['ruta'],
            'zona': zona,
            'mercancia': mercancia,
            'conductor_sugerido': sugerencia,
            'confianza': f"{score}%",
        })

    return pd.DataFrame(resultados)


# ================================================================
# COORDENADAS PARA MAPA
# ================================================================
COORDS = {
    "AZAGRA": (42.317, -1.883), "CALAHORRA": (42.305, -1.965), "TUDELA": (42.062, -1.607),
    "PAMPLONA": (42.813, -1.646), "ZARAGOZA": (41.649, -0.889), "MADRID": (40.417, -3.704),
    "BARCELONA": (41.385, 2.173), "MURCIA": (37.992, -1.131), "MALAGA": (36.721, -4.421),
    "SEVILLA": (37.389, -5.984), "VALENCIA": (39.470, -0.376), "BILBAO": (43.263, -2.935),
    "LOGROÑO": (42.465, -2.446), "GIRONA": (41.979, 2.821), "VIC": (41.930, 2.255),
    "GETAFE": (40.305, -3.731), "ALCANTARILLA": (37.969, -1.214), "SAN ADRIAN": (42.342, -1.933),
    "ARCHENA": (38.117, -1.300), "TORREJON": (40.460, -3.469), "ALFARO": (42.183, -1.750),
    "ALMERIA": (36.834, -2.464), "CARTAGENA": (37.606, -0.986), "GUADALAJARA": (40.633, -3.167),
    "MOLINA": (38.044, -1.207), "ESTELLA": (42.667, -2.033), "TAFALLA": (42.517, -1.667),
    "HARO": (42.583, -2.850), "ARNEDO": (42.217, -2.100), "CORELLA": (42.117, -1.783),
    "CAPARROSO": (42.333, -1.633), "PERALTA": (42.333, -1.800), "FALCES": (42.383, -1.800),
    "MENDAVIA": (42.433, -2.200), "LODOSA": (42.433, -2.083), "LERIDA": (41.618, 0.625),
    "LLEIDA": (41.618, 0.625), "TARRAGONA": (41.119, 1.245), "CADIZ": (36.527, -6.288),
    "ALICANTE": (38.345, -0.481), "ALBACETE": (38.994, -1.856), "BURGOS": (42.344, -3.697),
    "VITORIA": (42.847, -2.673), "SAN SEBASTIAN": (43.321, -1.985), "CORDOBA": (37.888, -4.779),
    "GRANADA": (37.177, -3.599), "TOLEDO": (39.857, -4.024), "VALLADOLID": (41.652, -4.724),
    "SALAMANCA": (40.970, -5.663), "MERIDA": (38.916, -6.344), "BADAJOZ": (38.879, -6.970),
    "VIGO": (42.231, -8.713), "GIJON": (43.532, -5.661), "SANTANDER": (43.462, -3.810),
}


def get_coord(lugar):
    if not lugar:
        return None
    u = lugar.upper()
    for k, v in COORDS.items():
        if k in u:
            return v
    return None


# ================================================================
# SIDEBAR
# ================================================================
with st.sidebar:
    st.title("🚛 COSMOSDATA")
    st.caption("Analytics + ML v1.0")
    st.divider()

    pagina = st.radio("📊 Sección", [
        "🏠 Resumen",
        "📦 Viajes",
        "👥 Conductores",
        "💰 Facturación",
        "🗺️ Mapa de Rutas",
        "🤖 Predictor de Precios",
        "🎯 Segmentación Clientes",
        "⚠️ Anomalías de Precio",
        "🧠 Sugerencia de Conductor",
        "📈 Tendencias",
        "🔧 Constructor de Gráficos",
    ])
    st.divider()
    if st.button("🔄 Refrescar datos"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()


# Cargar datos
df_viajes, df_conductores, df_vehiculos, df_eventos, df_metricas, df_historico = cargar_datos()


# ================================================================
# 🏠 RESUMEN
# ================================================================
if pagina == "🏠 Resumen":
    st.title("🏠 Panel General")

    c1, c2, c3, c4, c5 = st.columns(5)
    total = len(df_viajes)
    asignados = int(df_viajes['tiene_conductor'].sum()) if 'tiene_conductor' in df_viajes.columns else 0
    sin_asignar = total - asignados
    facturacion = df_viajes['precio'].sum()
    km_total = df_viajes['km'].sum()

    c1.metric("📦 Viajes", total)
    c2.metric("✅ Asignados", asignados)
    c3.metric("⚠️ Sin asignar", sin_asignar)
    c4.metric("💰 Facturación", f"{facturacion:,.0f}€")
    c5.metric("📏 KM Totales", f"{km_total:,.0f}")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Viajes por Cliente")
        df_cli = df_viajes.groupby('cliente').agg(
            viajes=('id', 'count'), total=('precio', 'sum')
        ).reset_index().sort_values('viajes', ascending=True)
        fig = px.bar(df_cli, y='cliente', x='viajes', orientation='h',
                     color='total', color_continuous_scale='Viridis', labels={'total': '€ Total'})
        fig.update_layout(height=500, yaxis_title='')
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("📦 Por Mercancía")
        df_merc = df_viajes.groupby('mercancia_grupo').agg(
            viajes=('id', 'count'), precio_medio=('precio', 'mean')
        ).reset_index()
        fig = px.pie(df_merc, values='viajes', names='mercancia_grupo',
                     hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("🗺️ Por Zona")
        df_zona = df_viajes.groupby('zona').size().reset_index(name='viajes')
        fig = px.pie(df_zona, values='viajes', names='zona',
                     hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)


# ================================================================
# 📦 VIAJES
# ================================================================
elif pagina == "📦 Viajes":
    st.title("📦 Análisis de Viajes")

    col1, col2, col3 = st.columns(3)
    with col1:
        clientes_sel = st.multiselect("Cliente", sorted(df_viajes['cliente'].dropna().unique()))
    with col2:
        mercancias_sel = st.multiselect("Mercancía", sorted(df_viajes['mercancia_grupo'].dropna().unique()))
    with col3:
        zonas_sel = st.multiselect("Zona", sorted(df_viajes['zona'].dropna().unique()))

    df_f = df_viajes.copy()
    if clientes_sel:
        df_f = df_f[df_f['cliente'].isin(clientes_sel)]
    if mercancias_sel:
        df_f = df_f[df_f['mercancia_grupo'].isin(mercancias_sel)]
    if zonas_sel:
        df_f = df_f[df_f['zona'].isin(zonas_sel)]

    st.metric("Viajes filtrados", len(df_f))

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("💰 Precio vs Distancia")
        fig = px.scatter(df_f[df_f['km'] > 0], x='km', y='precio', color='mercancia_grupo',
                         size='precio', hover_data=['cliente', 'lugar_carga', 'lugar_entrega'],
                         trendline='ols', labels={'km': 'Kilómetros', 'precio': 'Precio €'})
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("📊 €/km por Mercancía")
        fig = px.box(df_f[df_f['eur_km'] > 0], x='mercancia_grupo', y='eur_km',
                     color='mercancia_grupo', points='all',
                     labels={'eur_km': '€/km', 'mercancia_grupo': ''})
        fig.update_layout(height=500, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 Detalle")
    cols = ['cliente', 'lugar_carga', 'lugar_entrega', 'mercancia', 'precio', 'km', 'eur_km',
            'conductor_asignado', 'zona', 'estado']
    st.dataframe(df_f[[c for c in cols if c in df_f.columns]], use_container_width=True, hide_index=True)


# ================================================================
# 👥 CONDUCTORES
# ================================================================
elif pagina == "👥 Conductores":
    st.title("👥 Análisis de Conductores")

    c1, c2, c3 = st.columns(3)
    ausentes = len(df_conductores[df_conductores['absentismo'].notna() & (df_conductores['absentismo'] != '')])
    c1.metric("👥 Total", len(df_conductores))
    c2.metric("✅ Activos", len(df_conductores) - ausentes)
    c3.metric("🚫 Ausentes", ausentes)

    st.subheader("📊 Carga de Trabajo")
    df_carga = df_viajes[df_viajes['tiene_conductor']].groupby('conductor_asignado').agg(
        viajes=('id', 'count'), km=('km', 'sum'), facturacion=('precio', 'sum'), eur_km=('eur_km', 'mean')
    ).reset_index().sort_values('facturacion', ascending=True)

    if not df_carga.empty:
        fig = make_subplots(rows=1, cols=2, subplot_titles=("Viajes asignados", "Facturación generada"))
        fig.add_trace(go.Bar(y=df_carga['conductor_asignado'], x=df_carga['viajes'],
                             orientation='h', marker_color='#636EFA', name='Viajes'), row=1, col=1)
        fig.add_trace(go.Bar(y=df_carga['conductor_asignado'], x=df_carga['facturacion'],
                             orientation='h', marker_color='#00CC96', name='€'), row=1, col=2)
        fig.update_layout(height=max(400, len(df_carga) * 30), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 Listado")
    st.dataframe(
        df_conductores[['nombre', 'tractora', 'remolque', 'ubicacion', 'zona', 'absentismo']],
        use_container_width=True, hide_index=True
    )


# ================================================================
# 💰 FACTURACIÓN
# ================================================================
elif pagina == "💰 Facturación":
    st.title("💰 Análisis de Facturación")

    df_f = df_viajes[df_viajes['precio'] > 0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Total", f"{df_f['precio'].sum():,.0f}€")
    c2.metric("📊 Media/Viaje", f"{df_f['precio'].mean():,.0f}€")
    c3.metric("📏 KM Totales", f"{df_f['km'].sum():,}")
    eur_km_g = df_f['precio'].sum() / df_f['km'].sum() if df_f['km'].sum() > 0 else 0
    c4.metric("💶 €/km medio", f"{eur_km_g:.2f}")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Por Cliente")
        df_cli = df_f.groupby('cliente').agg(
            facturacion=('precio', 'sum'), viajes=('id', 'count')
        ).reset_index().sort_values('facturacion', ascending=False)
        fig = px.bar(df_cli, x='cliente', y='facturacion', text='viajes',
                     color='facturacion', color_continuous_scale='Greens')
        fig.update_traces(texttemplate='%{text}v', textposition='outside')
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("€/km por Mercancía")
        df_merc = df_f[df_f['km'] > 0].groupby('mercancia_grupo').agg(
            eur_km=('eur_km', 'mean'), viajes=('id', 'count')
        ).reset_index().sort_values('eur_km', ascending=False)
        fig = px.bar(df_merc, x='mercancia_grupo', y='eur_km', text='viajes',
                     color='eur_km', color_continuous_scale='Oranges')
        fig.update_traces(texttemplate='%{text}v', textposition='outside')
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("🗺️ Top 15 Rutas por Rentabilidad")
    df_rutas = df_f[df_f['km'] > 0].copy()
    df_rutas_agg = df_rutas.groupby('ruta').agg(
        eur_km=('eur_km', 'mean'), viajes=('id', 'count'), total=('precio', 'sum')
    ).reset_index().sort_values('eur_km', ascending=False).head(15)
    fig = px.bar(df_rutas_agg, y='ruta', x='eur_km', orientation='h',
                 color='viajes', color_continuous_scale='Viridis',
                 text=df_rutas_agg['eur_km'].round(2))
    fig.update_layout(height=max(400, len(df_rutas_agg) * 30), yaxis_title='')
    st.plotly_chart(fig, use_container_width=True)


# ================================================================
# 🗺️ MAPA DE RUTAS
# ================================================================
elif pagina == "🗺️ Mapa de Rutas":
    st.title("🗺️ Mapa de Rutas")

    rows_map = []
    for _, v in df_viajes.iterrows():
        c1 = get_coord(v.get('lugar_carga', ''))
        c2 = get_coord(v.get('lugar_entrega', ''))
        if c1 and c2:
            rows_map.append({
                'lat_o': c1[0], 'lon_o': c1[1], 'lat_d': c2[0], 'lon_d': c2[1],
                'ruta': v.get('ruta', ''), 'cliente': v['cliente'],
                'precio': v.get('precio', 0), 'km': v.get('km', 0),
            })

    if rows_map:
        df_map = pd.DataFrame(rows_map)
        fig = go.Figure()

        for _, r in df_map.iterrows():
            fig.add_trace(go.Scattermapbox(
                lat=[r['lat_o'], r['lat_d']], lon=[r['lon_o'], r['lon_d']],
                mode='lines', line=dict(width=1.5, color='#636EFA'),
                hoverinfo='text', showlegend=False,
                text=f"{r['ruta']}<br>{r['cliente']}<br>{r['precio']}€ | {r['km']}km",
            ))

        orig = df_map.drop_duplicates(subset=['lat_o', 'lon_o'])
        fig.add_trace(go.Scattermapbox(
            lat=orig['lat_o'], lon=orig['lon_o'], mode='markers',
            marker=dict(size=10, color='#00CC96'), text=orig['ruta'], name='📍 Carga',
        ))
        dest = df_map.drop_duplicates(subset=['lat_d', 'lon_d'])
        fig.add_trace(go.Scattermapbox(
            lat=dest['lat_d'], lon=dest['lon_d'], mode='markers',
            marker=dict(size=8, color='#EF553B'), text=dest['ruta'], name='📍 Descarga',
        ))

        fig.update_layout(
            mapbox=dict(style='open-street-map', center=dict(lat=40.5, lon=-2.5), zoom=5),
            height=700, margin=dict(l=0, r=0, t=0, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay rutas con coordenadas conocidas.")


# ================================================================
# 🤖 PREDICTOR DE PRECIOS
# ================================================================
elif pagina == "🤖 Predictor de Precios":
    st.title("🤖 Predictor de Precios (ML)")
    st.caption("Modelo GradientBoosting entrenado con tus viajes reales")

    df_json = df_viajes.to_json()
    modelo, encoders, features, metricas_ml = entrenar_modelo_precio(df_json)

    if modelo is None:
        st.warning("Necesitas al menos 10 viajes con precio y km para entrenar el modelo.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🎯 R² (ajuste)", f"{metricas_ml['r2']:.3f}")
        c2.metric("📊 R² (cross-val)", f"{metricas_ml['cv_r2']:.3f}")
        c3.metric("📏 Error medio", f"{metricas_ml['mae']:.0f}€")
        c4.metric("📚 Datos entreno", metricas_ml['n_train'])

        st.divider()
        col_l, col_r = st.columns([1, 2])

        with col_l:
            st.subheader("🔮 Predecir precio")
            km_in = st.number_input("Kilómetros", min_value=10, max_value=3000, value=400, step=10)
            merc_in = st.selectbox("Mercancía", encoders['mercancia'].classes_)
            zona_in = st.selectbox("Zona", encoders['zona'].classes_)
            cli_in = st.selectbox("Cliente", encoders['cliente'].classes_)

            if st.button("💰 Predecir", type="primary", use_container_width=True):
                X_pred = np.array([[
                    km_in,
                    encoders['mercancia'].transform([merc_in])[0],
                    encoders['zona'].transform([zona_in])[0],
                    encoders['cliente'].transform([cli_in])[0],
                ]])
                precio_pred = modelo.predict(X_pred)[0]
                st.success(f"### 💰 Precio estimado: {precio_pred:,.0f}€")
                st.info(f"📏 €/km estimado: {precio_pred / km_in:.2f}")

                df_sim = df_viajes[
                    (df_viajes['km'].between(km_in * 0.7, km_in * 1.3)) &
                    (df_viajes['mercancia_grupo'] == merc_in)
                ]
                if len(df_sim) > 0:
                    st.caption(
                        f"📊 Viajes similares ({len(df_sim)}): "
                        f"media {df_sim['precio'].mean():,.0f}€, "
                        f"rango {df_sim['precio'].min():,.0f}€ - {df_sim['precio'].max():,.0f}€"
                    )

        with col_r:
            st.subheader("📊 Importancia de Variables")
            imp = pd.DataFrame({
                'feature': ['Kilómetros', 'Mercancía', 'Zona', 'Cliente'],
                'importancia': modelo.feature_importances_
            }).sort_values('importancia', ascending=True)
            fig = px.bar(imp, y='feature', x='importancia', orientation='h',
                         color='importancia', color_continuous_scale='Blues')
            fig.update_layout(height=250, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("🎯 Real vs Predicho")
            df_ml = df_viajes[(df_viajes['km'] > 0) & (df_viajes['precio'] > 0)].copy()
            df_ml['mercancia_enc'] = encoders['mercancia'].transform(df_ml['mercancia_grupo'])
            df_ml['zona_enc'] = encoders['zona'].transform(df_ml['zona'])
            df_ml['cliente_enc'] = encoders['cliente'].transform(df_ml['cliente'].fillna('OTRO'))
            df_ml['precio_pred'] = modelo.predict(df_ml[features].values)

            fig = px.scatter(df_ml, x='precio', y='precio_pred', color='mercancia_grupo',
                             hover_data=['cliente', 'ruta'],
                             labels={'precio': 'Real €', 'precio_pred': 'Predicho €'})
            fig.add_shape(type='line', x0=0, x1=df_ml['precio'].max(),
                          y0=0, y1=df_ml['precio'].max(), line=dict(dash='dash', color='gray'))
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)


# ================================================================
# 🎯 SEGMENTACIÓN CLIENTES
# ================================================================
elif pagina == "🎯 Segmentación Clientes":
    st.title("🎯 Segmentación de Clientes (K-Means)")

    df_json = df_viajes.to_json()
    df_cli, kmeans = segmentar_clientes(df_json)

    if kmeans is None:
        st.warning("Necesitas al menos 4 clientes con viajes.")
    else:
        st.subheader("📊 Mapa de Segmentos")
        fig = px.scatter(df_cli, x='viajes', y='facturacion', size='precio_medio',
                         color='segmento_nombre', text='cliente',
                         hover_data=['km_medio', 'eur_km_medio'],
                         labels={'viajes': 'Nº Viajes', 'facturacion': 'Facturación €'})
        fig.update_traces(textposition='top center', textfont_size=9)
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📋 Detalle por Segmento")
        for seg in sorted(df_cli['segmento_nombre'].unique()):
            with st.expander(f"{seg} ({len(df_cli[df_cli['segmento_nombre'] == seg])} clientes)"):
                g = df_cli[df_cli['segmento_nombre'] == seg][[
                    'cliente', 'viajes', 'facturacion', 'precio_medio', 'eur_km_medio'
                ]].sort_values('facturacion', ascending=False)
                g.columns = ['Cliente', 'Viajes', 'Facturación €', 'Precio Medio €', '€/km']
                st.dataframe(g, use_container_width=True, hide_index=True)

        # Radar
        st.subheader("🕸️ Perfil de Segmentos")
        df_r = df_cli.groupby('segmento_nombre').agg(
            viajes=('viajes', 'mean'), facturacion=('facturacion', 'mean'),
            precio_medio=('precio_medio', 'mean'), eur_km=('eur_km_medio', 'mean'),
        ).reset_index()
        for col in ['viajes', 'facturacion', 'precio_medio', 'eur_km']:
            mx = df_r[col].max()
            df_r[f'{col}_n'] = df_r[col] / mx if mx > 0 else 0

        fig = go.Figure()
        cats = ['Volumen', 'Facturación', 'Precio medio', '€/km']
        for _, row in df_r.iterrows():
            vals = [row['viajes_n'], row['facturacion_n'], row['precio_medio_n'], row['eur_km_n']]
            fig.add_trace(go.Scatterpolar(
                r=vals + [vals[0]], theta=cats + [cats[0]], fill='toself', name=row['segmento_nombre']
            ))
        fig.update_layout(height=450, polar=dict(radialaxis=dict(visible=True, range=[0, 1])))
        st.plotly_chart(fig, use_container_width=True)


# ================================================================
# ⚠️ ANOMALÍAS
# ================================================================
elif pagina == "⚠️ Anomalías de Precio":
    st.title("⚠️ Detector de Anomalías en Precios")
    st.caption("Viajes con €/km inusual respecto a su tipo de mercancía")

    anomalias = detectar_anomalias_precio(df_viajes)

    if anomalias.empty:
        st.success("✅ No se detectaron anomalías significativas.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("⚠️ Total", len(anomalias))
        c2.metric("📉 Infravalorados", len(anomalias[anomalias['z_score'] < 0]))
        c3.metric("📈 Sobrevalorados", len(anomalias[anomalias['z_score'] > 0]))

        fig = px.scatter(anomalias, x='km', y='precio', color='z_score',
                         color_continuous_scale='RdYlGn', color_continuous_midpoint=0,
                         size=anomalias['z_score'].abs(),
                         hover_data=['cliente', 'lugar_carga', 'lugar_entrega', 'mercancia_grupo', 'eur_km'])
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📉 Infravalorados")
            bajos = anomalias[anomalias['z_score'] < -1.5][[
                'cliente', 'ruta', 'mercancia', 'km', 'precio', 'eur_km', 'eur_km_media'
            ]].sort_values('z_score')
            if not bajos.empty:
                bajos['diff_€/km'] = (bajos['eur_km'] - bajos['eur_km_media']).round(3)
                st.dataframe(bajos, use_container_width=True, hide_index=True)
            else:
                st.info("Ninguno")
        with col2:
            st.subheader("📈 Sobrevalorados")
            altos = anomalias[anomalias['z_score'] > 1.5][[
                'cliente', 'ruta', 'mercancia', 'km', 'precio', 'eur_km', 'eur_km_media'
            ]].sort_values('z_score', ascending=False)
            if not altos.empty:
                altos['diff_€/km'] = (altos['eur_km'] - altos['eur_km_media']).round(3)
                st.dataframe(altos, use_container_width=True, hide_index=True)
            else:
                st.info("Ninguno")


# ================================================================
# 🧠 SUGERENCIA DE CONDUCTOR
# ================================================================
elif pagina == "🧠 Sugerencia de Conductor":
    st.title("🧠 Sugerencia de Conductor (ML)")
    st.caption("Basado en historial: qué conductor ha operado más en esa zona y mercancía")

    sugerencias = predecir_conductor_optimo(df_viajes, df_conductores)

    if sugerencias.empty:
        st.info("No hay viajes sin asignar o datos insuficientes para sugerir.")
    else:
        st.metric("📦 Viajes sin asignar", len(sugerencias))
        st.divider()

        st.dataframe(
            sugerencias[['cliente', 'ruta', 'zona', 'mercancia', 'conductor_sugerido', 'confianza']],
            use_container_width=True, hide_index=True,
            column_config={
                'confianza': st.column_config.ProgressColumn(
                    "Confianza", format="%s", min_value=0, max_value=100,
                ),
            }
        )

        st.divider()
        st.subheader("📊 Experiencia por Zona")
        df_exp = df_viajes[df_viajes['tiene_conductor']].groupby(
            ['zona', 'conductor_asignado']
        ).agg(viajes=('id', 'count')).reset_index()

        fig = px.bar(df_exp.sort_values('viajes', ascending=False).head(20),
                     x='conductor_asignado', y='viajes', color='zona',
                     labels={'conductor_asignado': 'Conductor', 'viajes': 'Viajes en zona'})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)


# ================================================================
# 📈 TENDENCIAS
# ================================================================
elif pagina == "📈 Tendencias":
    st.title("📈 Tendencias")

    if df_metricas.empty:
        st.warning("⚠️ Integra `analitica_transporte.py` para recoger datos históricos.")
        st.info("Análisis estático con datos actuales:")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Distribución de Precios")
            fig = px.histogram(df_viajes[df_viajes['precio'] > 0], x='precio', nbins=20,
                               color='mercancia_grupo', barmode='overlay')
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.subheader("Distribución de Kilómetros")
            fig = px.histogram(df_viajes[df_viajes['km'] > 0], x='km', nbins=20,
                               color='zona', barmode='overlay')
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
    else:
        metricas_disp = [c for c in df_metricas.columns
                         if c not in ('id', 'fecha') and df_metricas[c].dtype in ('int64', 'float64')]
        sel = st.multiselect("Métricas", metricas_disp, default=metricas_disp[:3])
        if sel:
            fig = go.Figure()
            for m in sel:
                fig.add_trace(go.Scatter(x=df_metricas['fecha'], y=df_metricas[m],
                                         mode='lines+markers', name=m))
            fig.update_layout(height=500, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)


# ================================================================
# 🔧 CONSTRUCTOR DE GRÁFICOS
# ================================================================
elif pagina == "🔧 Constructor de Gráficos":
    st.title("🔧 Constructor de Gráficos")
    st.caption("Combina columnas libremente para explorar los datos.")

    tablas = {'viajes_empresa': df_viajes, 'conductores_empresa': df_conductores,
              'vehiculos_empresa': df_vehiculos}
    if not df_eventos.empty:
        tablas['eventos_operativos'] = df_eventos
    if not df_historico.empty:
        tablas['historico_viajes'] = df_historico

    tabla_sel = st.selectbox("📂 Tabla", list(tablas.keys()))
    df = tablas[tabla_sel]

    if df.empty:
        st.info("Tabla vacía.")
    else:
        st.success(f"📊 {len(df)} registros | {len(df.columns)} columnas")
        cols_num = df.select_dtypes(include=['number']).columns.tolist()
        cols_cat = df.select_dtypes(include=['object']).columns.tolist()

        tipo = st.selectbox("📈 Tipo", [
            "Barras", "Barras H", "Líneas", "Scatter", "Pie", "Histograma", "Box Plot", "Heatmap", "Sunburst"
        ])

        col1, col2 = st.columns(2)
        with col1:
            if tipo in ["Barras", "Barras H", "Líneas"]:
                eje_x = st.selectbox("Agrupar (X)", cols_cat + cols_num)
                eje_y = st.selectbox("Valor (Y)", cols_num)
                agg = st.selectbox("Agregación", ["count", "sum", "mean", "min", "max"])
            elif tipo == "Scatter":
                eje_x = st.selectbox("X", cols_num)
                eje_y = st.selectbox("Y", cols_num, index=min(1, len(cols_num) - 1))
            elif tipo == "Pie":
                eje_x = st.selectbox("Categoría", cols_cat)
                eje_y = st.selectbox("Valor", ['count'] + cols_num)
            elif tipo == "Histograma":
                eje_x = st.selectbox("Columna", cols_num)
            elif tipo == "Box Plot":
                eje_x = st.selectbox("Categoría", cols_cat)
                eje_y = st.selectbox("Valor", cols_num)
            elif tipo == "Heatmap":
                eje_x = st.selectbox("Col 1", cols_cat)
                eje_y = st.selectbox("Col 2", cols_cat, index=min(1, len(cols_cat) - 1))
            elif tipo == "Sunburst":
                niveles = st.multiselect("Niveles jerárquicos", cols_cat, default=cols_cat[:2])
                eje_y = st.selectbox("Valor", ['count'] + cols_num)

        with col2:
            color = st.selectbox("Color por", ['Ninguno'] + cols_cat + cols_num)
            if color == 'Ninguno':
                color = None
            titulo = st.text_input("Título", f"{tipo}: {tabla_sel}")
            altura = st.slider("Altura", 300, 800, 500)

        st.divider()
        try:
            if tipo in ["Barras", "Barras H", "Líneas"]:
                if agg == "count":
                    df_agg = df.groupby(eje_x).size().reset_index(name='count')
                    y_col = 'count'
                else:
                    df_agg = df.groupby(eje_x).agg({eje_y: agg}).reset_index()
                    y_col = eje_y
                if tipo == "Barras":
                    fig = px.bar(df_agg, x=eje_x, y=y_col, color=color, title=titulo)
                elif tipo == "Barras H":
                    fig = px.bar(df_agg, y=eje_x, x=y_col, orientation='h', color=color, title=titulo)
                else:
                    fig = px.line(df_agg, x=eje_x, y=y_col, markers=True, title=titulo)
            elif tipo == "Scatter":
                fig = px.scatter(df, x=eje_x, y=eje_y, color=color, trendline='ols', title=titulo)
            elif tipo == "Pie":
                if eje_y == 'count':
                    df_p = df.groupby(eje_x).size().reset_index(name='count')
                    fig = px.pie(df_p, names=eje_x, values='count', hole=0.4, title=titulo)
                else:
                    df_p = df.groupby(eje_x).agg({eje_y: 'sum'}).reset_index()
                    fig = px.pie(df_p, names=eje_x, values=eje_y, hole=0.4, title=titulo)
            elif tipo == "Histograma":
                fig = px.histogram(df, x=eje_x, color=color, title=titulo)
            elif tipo == "Box Plot":
                fig = px.box(df, x=eje_x, y=eje_y, color=color, points='all', title=titulo)
            elif tipo == "Heatmap":
                df_h = df.groupby([eje_x, eje_y]).size().reset_index(name='count')
                df_pv = df_h.pivot(index=eje_y, columns=eje_x, values='count').fillna(0)
                fig = px.imshow(df_pv, title=titulo, color_continuous_scale='Blues')
            elif tipo == "Sunburst":
                if eje_y == 'count':
                    fig = px.sunburst(df, path=niveles, title=titulo)
                else:
                    fig = px.sunburst(df, path=niveles, values=eje_y, title=titulo)

            fig.update_layout(height=altura)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📋 Ver datos"):
                st.dataframe(df.head(100), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error: {e}")
            st.info("Prueba otra combinación.")


# ================================================================
# FOOTER
# ================================================================
st.divider()
st.caption(
    f"🚛 COSMOSDATA Analytics + ML v1.0 | "
    f"BD: {DB_PATH} | "
    f"{len(df_viajes)} viajes | {len(df_conductores)} conductores | "
    f"Última carga: {datetime.now().strftime('%H:%M:%S')}"
)
