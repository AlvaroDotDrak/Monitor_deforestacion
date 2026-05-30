import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os
import glob
from datetime import datetime

# ── Configuración de Página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Histórico NDVI — Monitor IA",
    page_icon="📈",
    layout="wide",
)

# ── Inyección de CSS Personalizado (Estilo Moderno & Premium) ──────────────────
if os.path.exists("style.css"):
    with open("style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Banner de Bienvenida Premium ───────────────────────────────────────────────
st.markdown(
    """
    <div style="background: linear-gradient(135deg, #0f233a 0%, #06101c 100%); 
                padding: 25px 35px; border-radius: 16px; margin-bottom: 25px; 
                border-left: 8px solid #3498db; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
        <h1 style="color: white; margin: 0; font-size: 30px; font-weight: 700; display: flex; align-items: center; font-family: 'Outfit', sans-serif;">
            <span style="margin-right: 15px;">📈</span> Histórico Temporal de NDVI
        </h1>
        <p style="color: #a9cbe8; margin: 8px 0 0 0; font-size: 14.5px; font-family: 'Outfit', sans-serif; opacity: 0.9; line-height: 1.5;">
            Visualiza la evolución de la salud vegetal de la zona de interés a lo largo de los últimos 5 años. Filtra anomalías y analiza las tendencias de recuperación y degradación estacional.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# ── Buscar archivo CSV en el directorio ─────────────────────────────────────────
archivos_csv = glob.glob("Sentinel-2 L2A-3_NDVI-*.csv")
ruta_csv = archivos_csv[0] if archivos_csv else None

df = None
if ruta_csv:
    try:
        df = pd.read_csv(ruta_csv)
    except Exception as e:
        st.error(f"Error al cargar el archivo CSV local: {e}")
else:
    st.warning("⚠️ No se encontró el archivo CSV de NDVI histórico en el proyecto.")

# Permitir subir un archivo propio si no se encontró o se desea cambiar
uploader_csv = st.file_uploader("Subir archivo CSV de NDVI histórico (Copernicus Statistical API)", type=["csv"])
if uploader_csv:
    try:
        df = pd.read_csv(uploader_csv)
        st.success("CSV cargado correctamente por el usuario.")
    except Exception as e:
        st.error(f"Error al procesar el archivo subido: {e}")

if df is not None:
    # ── Limpieza y Normalización de Datos ──────────────────────────────────────
    # Limpiar prefijos de columna "C0/"
    df.columns = [c.replace("C0/", "") for c in df.columns]
    
    # Validar columnas críticas
    columnas_necesarias = ["date", "mean", "min", "max", "stDev", "cloudCoveragePercent"]
    if not all(col in df.columns for col in columnas_necesarias):
        st.error("El archivo CSV no posee el formato estándar de la API Estadística de Copernicus.")
        st.write("Columnas detectadas:", list(df.columns))
        st.stop()
        
    # Convertir fecha y ordenar
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # ── Sidebar de Filtros ─────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Filtros Históricos")
        
        # Filtro de Nubosidad
        max_nubes = st.slider(
            "Filtrar por nubosidad máx. (%)",
            min_value=0,
            max_value=100,
            value=20,
            help="Excluye del gráfico las mediciones con un porcentaje de nubosidad mayor al seleccionado."
        )
        
        # Filtro de Fechas
        min_fecha = df["date"].min().to_pydatetime()
        max_fecha = df["date"].max().to_pydatetime()
        
        rango_fechas = st.slider(
            "Rango de Fechas",
            min_value=min_fecha,
            max_value=max_fecha,
            value=(min_fecha, max_fecha),
            format="DD/MM/YYYY"
        )
        
    # Aplicar filtros
    df_filtrado = df[
        (df["cloudCoveragePercent"] <= max_nubes) &
        (df["date"] >= rango_fechas[0]) &
        (df["date"] <= rango_fechas[1])
    ]
    
    if df_filtrado.empty:
        st.warning("No hay datos disponibles para los filtros seleccionados.")
        st.stop()
        
    # ── Métricas Clave ────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    
    ultimo_val = df_filtrado["mean"].iloc[-1]
    ultimo_fecha = df_filtrado["date"].iloc[-1].strftime("%d/%m/%Y")
    promedio_hist = df_filtrado["mean"].mean()
    min_row = df_filtrado.loc[df_filtrado["mean"].idxmin()]
    max_row = df_filtrado.loc[df_filtrado["mean"].idxmax()]
    
    c1.metric(
        label=f"Último NDVI Medio ({ultimo_fecha})",
        value=f"{ultimo_val:.3f}",
        delta=f"{(ultimo_val - promedio_hist):+.3f} vs promedio"
    )
    c2.metric(
        label="Promedio NDVI",
        value=f"{promedio_hist:.3f}"
    )
    c3.metric(
        label=f"Mínimo NDVI ({min_row['date'].strftime('%d/%m/%Y')})",
        value=f"{min_row['mean']:.3f}",
        delta="Anomalía negativa" if min_row['mean'] < 0.5 else None,
        delta_color="inverse"
    )
    c4.metric(
        label=f"Máximo NDVI ({max_row['date'].strftime('%d/%m/%Y')})",
        value=f"{max_row['mean']:.3f}"
    )
    
    # ── Gráfico de Línea Temporal Premium ─────────────────────────────────────
    st.subheader("📈 Evolución Temporal del NDVI")
    
    fig = go.Figure()
    
    # Banda de desviación estándar (stDev)
    lim_superior = (df_filtrado["mean"] + df_filtrado["stDev"]).tolist()
    lim_inferior = (df_filtrado["mean"] - df_filtrado["stDev"]).tolist()
    fechas = df_filtrado["date"].tolist()
    
    # Desviación superior
    fig.add_trace(go.Scatter(
        x=fechas + fechas[::-1],
        y=lim_superior + lim_inferior[::-1],
        fill='toself',
        fillcolor='rgba(46, 204, 113, 0.12)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip",
        showlegend=True,
        name="Rango de Desviación (stDev)"
    ))
    
    # Línea del Promedio
    fig.add_trace(go.Scatter(
        x=df_filtrado["date"],
        y=df_filtrado["mean"],
        mode='lines',
        name='NDVI Medio',
        line=dict(color='#2ecc71', width=3),
        hovertemplate="<b>Fecha:</b> %{x|%d/%m/%Y}<br><b>NDVI Medio:</b> %{y:.3f}<extra></extra>"
    ))
    
    # Puntos de Mínimo y Máximo
    fig.add_trace(go.Scatter(
        x=[min_row['date']],
        y=[min_row['mean']],
        mode='markers',
        name='Mínimo Histórico',
        marker=dict(color='#e74c3c', size=10, symbol='triangle-down'),
        hovertemplate="<b>Mínimo Histórico</b><br>Fecha: %{x|%d/%m/%Y}<br>NDVI: %{y:.3f}<extra></extra>"
    ))
    
    fig.add_trace(go.Scatter(
        x=[max_row['date']],
        y=[max_row['mean']],
        mode='markers',
        name='Máximo Histórico',
        marker=dict(color='#27ae60', size=10, symbol='triangle-up'),
        hovertemplate="<b>Máximo Histórico</b><br>Fecha: %{x|%d/%m/%Y}<br>NDVI: %{y:.3f}<extra></extra>"
    ))
    
    # Diseño estético general
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=20, r=20, t=10, b=20),
        height=450,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(0, 0, 0, 0.05)',
            linewidth=1,
            linecolor='rgba(0,0,0,0.1)'
        ),
        yaxis=dict(
            title="Índice NDVI",
            range=[0, 1],
            showgrid=True,
            gridcolor='rgba(0, 0, 0, 0.05)',
            linewidth=1,
            linecolor='rgba(0,0,0,0.1)'
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # ── Tabla de Datos e Información adicional ────────────────────────────────
    st.divider()
    
    col_izq, col_der = st.columns([1, 1])
    
    with col_izq:
        st.subheader("📋 Datos Históricos")
        st.write("Se muestran las últimas 10 mediciones con los filtros actuales:")
        st.dataframe(
            df_filtrado[["date", "mean", "min", "max", "stDev", "cloudCoveragePercent"]]
            .rename(columns={
                "date": "Fecha",
                "mean": "NDVI Medio",
                "min": "Mínimo",
                "max": "Máximo",
                "stDev": "Desv. Est.",
                "cloudCoveragePercent": "Nubosidad (%)"
            })
            .tail(10),
            use_container_width=True
        )
        
    with col_der:
        st.subheader("💡 Análisis de Tendencias")
        st.markdown(
            """
            * **Ciclos Estacionales:** El NDVI oscila naturalmente debido a las estaciones en la región del Maule. Suele alcanzar máximos al final de la primavera/inicio del verano (alta actividad fotosintética) y mínimos en invierno.
            * **Detección de Perturbaciones:** Una caída abrupta y permanente en el NDVI medio que no se recupere en las estaciones siguientes suele indicar **deforestación, tala o incendios forestales**.
            * **Nubosidad:** Las nubes bajas y la neblina reducen artificialmente el NDVI. Te sugerimos mantener el filtro de nubosidad por debajo del **20%** para un análisis más preciso.
            """
        )
else:
    st.info("Sube un archivo CSV con datos históricos para habilitar este panel.")
