import streamlit as st
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import io
import os
import requests
import rasterio
import folium
from datetime import date

import core
from core import leer_banda, calcular_ndvi, calcular_nbr, crear_compuesto, detectar_zonas, crear_mapa, clasificar_tipo
import base64
from copernicus_api import obtener_token, buscar_imagenes, descargar_compuesto, descargar_rgb

BBOX = [-72.34, -35.38, -72.17, -35.27]  # Constitución / Putú / Carrizal


# ── Banner de Bienvenida Premium ───────────────────────────────────────────────
st.markdown(
    """
    <div style="background: linear-gradient(135deg, #132e18 0%, #08170d 100%); 
                padding: 25px 35px; border-radius: 16px; margin-bottom: 25px; 
                border-left: 8px solid #2ecc71; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
        <h1 style="color: white; margin: 0; font-size: 30px; font-weight: 700; display: flex; align-items: center; font-family: 'Outfit', sans-serif;">
            <span style="margin-right: 15px;">🔍</span> Módulo de Análisis Comparativo
        </h1>
        <p style="color: #a3e2b2; margin: 8px 0 0 0; font-size: 14.5px; font-family: 'Outfit', sans-serif; opacity: 0.9; line-height: 1.5;">
            Compara imágenes satelitales <b>Sentinel-2</b> de dos fechas distintas para detectar deforestación, tala y severidad de incendios forestales usando Inteligencia Artificial.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# Determinar si el modelo de machine learning está disponible
ml_activo = core._modelo_rf is not None

# ── Helpers de fechas ──────────────────────────────────────────────────────────
ESTACIONES = {
    "❄️ Invierno (Jun–Ago)": (6, 1, 8, 31, 0),   # mismo año
    "☀️ Verano (Nov–Ene)":   (11, 1, 1, 31, 1),   # hasta año+1
}

def rango_desde_ano(ano, estacion):
    m_ini, d_ini, m_fin, d_fin, sig_ano = ESTACIONES[estacion]
    return date(ano, m_ini, d_ini), date(ano + sig_ano, m_fin, d_fin)

ANO_HOY = date.today().year
ANOS    = list(range(2018, ANO_HOY + 1))

# ── Sidebar (Configuración & Control) ──────────────────────────────────────────
with st.sidebar:
    st.header("Configuración")

    # Estado del modelo de IA
    if ml_activo:
        st.markdown(
            """
            <div style="background-color: rgba(46, 204, 113, 0.15); padding: 12px; border-radius: 8px; border-left: 5px solid #2ecc71; margin-bottom: 20px;">
                <h4 style="color: #2ecc71; margin: 0; font-size: 14px; font-weight: bold;">🧠 Clasificador ML Activo</h4>
                <p style="color: #e2f9e6; margin: 4px 0 0 0; font-size: 11px;">
                    Modelo XGBoost entrenado con datos de Hansen GFC y Sentinel-2.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div style="background-color: rgba(230, 126, 34, 0.15); padding: 12px; border-radius: 8px; border-left: 5px solid #e67e22; margin-bottom: 20px;">
                <h4 style="color: #e67e22; margin: 0; font-size: 14px; font-weight: bold;">⚠️ Clasificador Heurístico</h4>
                <p style="color: #fdf2e9; margin: 4px 0 0 0; font-size: 11px;">
                    Modelo RandomForestClassifier no encontrado. Usando reglas de fallback.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Opción 1: Datos de demostración (Constitución)
    st.subheader("🚀 Demostración rápida")
    usar_demo = st.button("⚡ Cargar Datos de Constitución (Maule)", use_container_width=True)
    if usar_demo:
        st.session_state["use_demo"] = True
        # Limpiar resultados anteriores para recalcular con los nuevos parámetros
        for k in ["zonas", "ndvi1", "ndvi2", "cambio", "mapa", "mascara_alerta"]:
            st.session_state.pop(k, None)

    # Estado de la demostración
    use_demo = st.session_state.get("use_demo", False)
    if use_demo:
        st.success("📝 Modo Demo: Constitución, Maule")
        if st.button("Restablecer / Subir archivos propios", use_container_width=True):
            st.session_state["use_demo"] = False
            for k in ["zonas", "ndvi1", "ndvi2", "cambio", "mapa", "mascara_alerta"]:
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()

    if not use_demo:
        # ── Credenciales ────────────────────────────────────────────────────
        st.subheader("🛰️ Credenciales Copernicus")
        api_usuario = st.text_input("Usuario", key="api_user",
                                    placeholder="correo@ejemplo.com")
        api_clave   = st.text_input("Contraseña", type="password", key="api_pass")

        st.divider()

        # ── Atajos rápidos ──────────────────────────────────────────────────
        st.subheader("⚡ Atajos")
        c1, c2, c3 = st.columns(3)
        if c1.button("2 años", use_container_width=True):
            st.session_state["ano_base"]     = ANO_HOY - 3
            st.session_state["ano_reciente"] = ANO_HOY - 1
        if c2.button("5 años", use_container_width=True):
            st.session_state["ano_base"]     = ANO_HOY - 6
            st.session_state["ano_reciente"] = ANO_HOY - 1
        if c3.button("🔥 2017", use_container_width=True, help="Antes/después megaincendio"):
            st.session_state["ano_base"]     = 2016
            st.session_state["ano_reciente"] = 2018
            st.session_state["estacion"]     = "❄️ Invierno (Jun–Ago)"

        st.divider()

        # ── Selección de años y estación ────────────────────────────────────
        st.subheader("📊 Comparación")

        ano_base = st.selectbox(
            "Año base (antes)",
            ANOS,
            index=ANOS.index(st.session_state.get("ano_base", 2022)),
            key="ano_base",
        )
        ano_rec = st.selectbox(
            "Año reciente (después)",
            ANOS,
            index=ANOS.index(st.session_state.get("ano_reciente", 2024)),
            key="ano_reciente",
        )
        estacion = st.radio(
            "Estación",
            list(ESTACIONES.keys()),
            index=list(ESTACIONES.keys()).index(
                st.session_state.get("estacion", "❄️ Invierno (Jun–Ago)")
            ),
            key="estacion",
        )

        # Calcular rangos automáticamente
        f1_desde, f1_hasta = rango_desde_ano(ano_base, estacion)
        f2_desde, f2_hasta = rango_desde_ano(ano_rec,  estacion)

        st.caption(f"Base:     {f1_desde} → {f1_hasta}")
        st.caption(f"Reciente: {f2_desde} → {f2_hasta}")

        # Fechas representativas para gráficos
        fecha1 = f1_desde
        fecha2 = f2_desde
        b04_1 = b08_1 = b04_2 = b08_2 = None

    else:
        fecha1 = date(2022, 6, 7)
        fecha2 = date(2024, 7, 6)
        b04_1 = b08_1 = b04_2 = b08_2 = None
        api_usuario = api_clave = ""
        f1_desde = f1_hasta = f2_desde = f2_hasta = None

    # ── Parámetros de detección ─────────────────────────────────────────────
    st.divider()
    st.subheader("⚙️ Detección")
    umbral = st.slider("Umbral caída NDVI", 0.10, 0.35, 0.15, 0.01,
                       help="Mínima caída de NDVI para disparar una alerta.")
    min_ha = st.slider("Superficie mínima (ha)", 0.1, 5.0, 0.5, 0.1,
                       help="Ignora zonas más pequeñas que este valor.")
    api_nubes = st.slider("Máx. nubosidad (%)", 0, 30, 10,
                          help="Filtra imágenes con más nubes que este porcentaje.")

    analizar = st.button("🔍 Analizar", use_container_width=True, type="primary")

    # Explicación de NDVI
    st.divider()
    with st.expander("📚 ¿Cómo funciona el NDVI?"):
        st.markdown(
            """
            El **NDVI** (Normalized Difference Vegetation Index) estima la salud de la vegetación:
            
            $$\\text{NDVI} = \\frac{\\text{NIR} - \\text{Red}}{\\text{Red} + \\text{NIR}}$$
            
            * **NIR (B08):** Infrarrojo cercano (reflejado fuertemente por hojas sanas).
            * **Red (B04):** Rojo visible (absorbido por la clorofila).
            
            **Interpretación:**
            * **0.6 a 0.9:** Bosques densos y sanos.
            * **0.2 a 0.5:** Cultivos o vegetación dispersa.
            * **< 0.1:** Suelo desnudo, áreas quemadas o cosechadas.
            """
        )

# ── Procesamiento y Análisis de Datos ──────────────────────────────────────────
comp_disponible = all(k in st.session_state for k in [
    "comp_1_b04", "comp_1_b08", "comp_1_transform", "comp_1_bounds",
    "comp_2_b04", "comp_2_b08",
])

archivos_listos = use_demo or comp_disponible

# Descarga automática al presionar Analizar (si no es demo)
if analizar and not use_demo:
    if not api_usuario or not api_clave:
        st.error("Ingresa tus credenciales de Copernicus en el panel izquierdo.")
        st.stop()
    try:
        progreso = st.progress(0, text="Conectando con Copernicus...")
        token    = obtener_token(api_usuario, api_clave)

        for label, desde, hasta, clave, pct in [
            ("base",     f1_desde, f1_hasta, "comp_1", 10),
            ("reciente", f2_desde, f2_hasta, "comp_2", 55),
        ]:
            progreso.progress(pct, text=f"Descargando compuesto NDVI {label} ({desde} → {hasta})...")
            ruta = descargar_compuesto(token, BBOX, str(desde), str(hasta),
                                       max_nubes=api_nubes)
            with rasterio.open(ruta) as src:
                st.session_state[f"{clave}_b04"]       = [src.read(1).astype(float)]
                st.session_state[f"{clave}_b08"]       = [src.read(2).astype(float)]
                st.session_state[f"{clave}_b12"]       = [src.read(3).astype(float)] if src.count >= 3 else None
                st.session_state[f"{clave}_transform"] = src.transform
                st.session_state[f"{clave}_bounds"]    = src.bounds
                st.session_state[f"{clave}_fecha"]     = desde
                st.session_state[f"{clave}_n"]         = 1

            progreso.progress(pct + 20, text=f"Descargando imagen color natural {label}...")
            rgb_bytes = descargar_rgb(token, BBOX, str(desde), str(hasta), max_nubes=api_nubes)
            st.session_state[f"{clave}_rgb"] = base64.b64encode(rgb_bytes).decode()

        progreso.progress(100, text="Descarga completa.")
        comp_disponible = True
        archivos_listos = True
        # Limpiar resultados anteriores para recalcular
        for k in ["zonas", "ndvi1", "ndvi2", "cambio", "mapa", "mascara_alerta"]:
            st.session_state.pop(k, None)

    except ValueError as e:
        st.error(str(e)); st.stop()
    except Exception as e:
        st.error(f"Error al descargar: {e}"); st.stop()

if not archivos_listos:
    st.markdown(
        """
        <div style="background-color: #f7fafc; padding: 30px; border-radius: 12px; border: 1px solid #e2e8f0; margin-top: 10px;">
            <h3 style="color: #2d3748; margin-top: 0; font-family: 'Outfit', sans-serif; font-weight: 600;">👋 ¡Módulo de Análisis Listo!</h3>
            <p style="color: #4a5568; font-size: 15px; margin-bottom: 20px; line-height: 1.6;">
                Esta sección permite comparar imágenes satelitales Sentinel-2 en dos períodos de tiempo para detectar perturbaciones. 
                Por favor, selecciona una opción en el panel izquierdo para comenzar el análisis:
            </p>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px; margin-bottom: 25px;">
                <div style="background: white; padding: 20px; border-radius: 8px; border: 1px solid #cbd5e0; border-top: 4px solid #2ecc71; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <h4 style="margin: 0 0 10px 0; color: #1e3f20; font-weight: bold;">⚡ 1. Demostración Rápida</h4>
                    <p style="margin: 0; color: #718096; font-size: 13.5px; line-height: 1.5;">
                        Carga instantáneamente imágenes locales de la Región del Maule y ejecuta el análisis. Ideal para pruebas rápidas.
                    </p>
                </div>
                <div style="background: white; padding: 20px; border-radius: 8px; border: 1px solid #cbd5e0; border-top: 4px solid #9b59b6; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <h4 style="margin: 0 0 10px 0; color: #4a1f60; font-weight: bold;">🛰️ 2. Descarga Automática</h4>
                    <p style="margin: 0; color: #718096; font-size: 13.5px; line-height: 1.5;">
                        Ingresa tus credenciales de Copernicus para descargar directamente los compuestos satelitales del área a analizar.
                    </p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.stop()

# Ejecución del Análisis
if analizar or "zonas" in st.session_state or (use_demo and "zonas" not in st.session_state):
    
    if analizar or ("zonas" not in st.session_state):
        with st.spinner("Procesando imágenes multiespectrales y ejecutando algoritmos..."):
            
            if use_demo:
                # Cargar archivos locales del Maule
                b04_arr1, transform, bounds = leer_banda("2022-06-07-00_00_2022-06-07-23_59_Sentinel-2_L2A_B04_(Raw).tiff")
                b08_arr1, _, _              = leer_banda("2022-06-07-00_00_2022-06-07-23_59_Sentinel-2_L2A_B08_(Raw).tiff")
                b04_arr2, _, _              = leer_banda("2024-07-06-00_00_2024-07-06-23_59_Sentinel-2_L2A_B04_(Raw).tiff")
                b08_arr2, _, _              = leer_banda("2024-07-06-00_00_2024-07-06-23_59_Sentinel-2_L2A_B08_(Raw).tiff")
                
                ndvi1 = calcular_ndvi(b04_arr1, b08_arr1)
                ndvi2 = calcular_ndvi(b04_arr2, b08_arr2)
                fecha1 = date(2022, 6, 7)
                fecha2 = date(2024, 7, 6)
                modo_label = "Datos de Demostración (Constitución, Región del Maule)"
                nbr1 = nbr2 = None
                
            else:
                # Modo compuesto Copernicus
                b12_1 = st.session_state.get("comp_1_b12")
                b12_2 = st.session_state.get("comp_2_b12")
                _, _, ndvi1, b12_med1 = crear_compuesto(
                    st.session_state["comp_1_b04"],
                    st.session_state["comp_1_b08"],
                    b12_1,
                )
                _, _, ndvi2, b12_med2 = crear_compuesto(
                    st.session_state["comp_2_b04"],
                    st.session_state["comp_2_b08"],
                    b12_2,
                )
                # Calcular NBR si hay B12
                nbr1 = calcular_nbr(st.session_state["comp_1_b08"][0], b12_med1) if b12_med1 is not None else None
                nbr2 = calcular_nbr(st.session_state["comp_2_b08"][0], b12_med2) if b12_med2 is not None else None
                transform  = st.session_state["comp_1_transform"]
                bounds     = st.session_state["comp_1_bounds"]
                fecha1     = st.session_state.get("comp_1_fecha", fecha1)
                fecha2     = st.session_state.get("comp_2_fecha", fecha2)
                tiene_nbr  = nbr1 is not None and nbr2 is not None
                modo_label = f"Compuesto de Mediana — Sentinel Hub {'+ NBR (B12)' if tiene_nbr else ''}"

            cambio = ndvi2 - ndvi1
            zonas, mascara_alerta = detectar_zonas(
                cambio, transform, bounds, umbral, min_ha=min_ha,
                ndvi1=ndvi1, ndvi2=ndvi2,
                nbr1=nbr1,
                nbr2=nbr2,
            )
            mapa = crear_mapa(zonas, bounds, fecha1.month)

            st.session_state["modo_label"]     = modo_label
            st.session_state["ndvi1"]          = ndvi1
            st.session_state["ndvi2"]          = ndvi2
            st.session_state["cambio"]         = cambio
            st.session_state["zonas"]          = zonas
            st.session_state["mapa"]           = mapa
            st.session_state["mascara_alerta"] = mascara_alerta
            st.session_state["fecha1"]         = fecha1
            st.session_state["fecha2"]         = fecha2
            st.session_state["bounds"]         = bounds

    # Recuperar datos guardados
    ndvi1          = st.session_state["ndvi1"]
    ndvi2          = st.session_state["ndvi2"]
    cambio         = st.session_state["cambio"]
    zonas          = st.session_state["zonas"]
    mapa           = st.session_state["mapa"]
    mascara_alerta = st.session_state["mascara_alerta"]
    bounds         = st.session_state["bounds"]
    fecha1         = st.session_state.get("fecha1", fecha1)
    fecha2         = st.session_state.get("fecha2", fecha2)

    # Calcular estadísticas generales
    zonas_perdida     = [z for z in zonas if z["tipo_evento"] == "perdida"]
    zonas_recuperacion = [z for z in zonas if z["tipo_evento"] == "recuperacion"]
    area_total = sum(z["area_ha"] for z in zonas_perdida)
    graves     = sum(1 for z in zonas_perdida if z["severidad"] == "Grave")
    moderadas  = sum(1 for z in zonas_perdida if z["severidad"] == "Moderada")

    # Mostrar tipo de análisis
    st.caption(f"🔧 **Modo de análisis:** {st.session_state.get('modo_label', '')}")

    # Columnas de Métricas Resumen
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Zonas pérdida",         len(zonas_perdida))
    c2.metric("Área afectada",         f"{area_total:.1f} ha")
    c3.metric("Graves 🔴",             graves)
    c4.metric("🌱 Recuperación",       len(zonas_recuperacion))

    # Tabs de visualización de resultados
    tab1, tab2, tab3 = st.tabs(["📊 Análisis NDVI", "🗺️ Mapa de alertas", "📋 Tabla de alertas"])

    # Tab 1: Visualizaciones NDVI y Diferencial
    with tab1:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6), dpi=150, facecolor='none')
        fig.patch.set_alpha(0.0) # Fondo transparente
        kw = dict(cmap="RdYlGn", vmin=0, vmax=1)

        # Plot NDVI Fecha 1
        im0 = axes[0].imshow(ndvi1, **kw)
        axes[0].set_title(f"NDVI Base ({fecha1.strftime('%d/%m/%Y')})", color="#1e3f20", fontsize=13, fontweight='bold', pad=10)
        cbar0 = fig.colorbar(im0, ax=axes[0], fraction=0.046, pad=0.04)
        cbar0.ax.tick_params(labelsize=8)
        cbar0.outline.set_visible(False)
        axes[0].axis('off')

        # Plot NDVI Fecha 2
        im1 = axes[1].imshow(ndvi2, **kw)
        axes[1].set_title(f"NDVI Reciente ({fecha2.strftime('%d/%m/%Y')})", color="#1e3f20", fontsize=13, fontweight='bold', pad=10)
        cbar1 = fig.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)
        cbar1.ax.tick_params(labelsize=8)
        cbar1.outline.set_visible(False)
        axes[1].axis('off')

        # Plot Diferencial (ΔNDVI) con bordes de alarma superpuestos
        im2 = axes[2].imshow(cambio, cmap="RdYlGn", vmin=-0.4, vmax=0.4)
        axes[2].set_title("Diferencial NDVI (ΔNDVI)\n(Rojo = Pérdida de Vegetación)", color="#721c24", fontsize=13, fontweight='bold', pad=10)
        cbar2 = fig.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)
        cbar2.ax.tick_params(labelsize=8)
        cbar2.outline.set_visible(False)
        
        if mascara_alerta.any():
            axes[2].contour(mascara_alerta, levels=[0.5], colors="#e74c3c", linewidths=1.2, linestyles='solid')
        
        axes[2].axis('off')

        plt.tight_layout()
        st.pyplot(fig)
        plt.close()

    # Tab 2: Mapa Georreferenciado Interactivo
    with tab2:
        rgb1 = st.session_state.get("comp_1_rgb")
        rgb2 = st.session_state.get("comp_2_rgb")
        if rgb1 and rgb2:
            img_bounds = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]
            folium.raster_layers.ImageOverlay(
                image=f"data:image/png;base64,{rgb1}",
                bounds=img_bounds,
                opacity=0.9,
                name=f"🛰️ Sentinel-2 {fecha1.strftime('%b %Y')} (base)",
                show=False,
            ).add_to(mapa)
            folium.raster_layers.ImageOverlay(
                image=f"data:image/png;base64,{rgb2}",
                bounds=img_bounds,
                opacity=0.9,
                name=f"🛰️ Sentinel-2 {fecha2.strftime('%b %Y')} (reciente)",
                show=False,
            ).add_to(mapa)
            folium.LayerControl(collapsed=False).add_to(mapa)
            st.caption("💡 Activa las capas Sentinel-2 en el control superior derecho del mapa para ver la imagen real de cada período.")

        mapa_html = mapa._repr_html_()
        st.components.v1.html(mapa_html, height=580, scrolling=False)

    # Tab 3: Tabla de Detalles y Descargas
    with tab3:
        if not zonas:
            st.warning(f"No se han detectado alertas con el umbral (>{umbral}) y superficie mínima (>{min_ha} ha) actuales. Intenta ajustar los deslizadores del panel izquierdo.")
        else:
            st.markdown("<p style='color: #4a5568; margin-bottom: 12px; font-size:14px;'>Listado detallado de zonas afectadas por orden de superficie. La clasificación de evento se determina usando Inteligencia Artificial.</p>", unsafe_allow_html=True)
            filas = []
            for z in zonas:
                tipo, _ = clasificar_tipo(
                    z["caida_ndvi"], fecha1.month, z["area_ha"],
                    ndvi_antes=z.get("_ndvi_antes"),
                    ndvi_despues=z.get("_ndvi_despues"),
                    compacidad=z.get("compacidad"),
                )
                
                # Decorar severidad con colores visuales directos mediante emojis
                emoji_sev = "🔴 Grave" if z["severidad"] == "Grave" else "🟠 Moderada" if z["severidad"] == "Moderada" else "🟡 Leve"
                
                filas.append({
                    "Clasificación":   tipo,
                    "Severidad":       emoji_sev,
                    "Superficie (ha)": z["area_ha"],
                    "Δ NDVI":          z["caida_ndvi"],
                    "Compacidad":      z.get("compacidad", 0),
                    "Latitud GPS":     z["latitud"],
                    "Longitud GPS":    z["longitud"],
                })

            df = pd.DataFrame(filas)

            # Dataframe con selección de fila
            seleccion = st.dataframe(
                df,
                column_config={
                    "Clasificación":   st.column_config.TextColumn("Clasificación"),
                    "Severidad":       st.column_config.TextColumn("Severidad"),
                    "Superficie (ha)": st.column_config.NumberColumn("Superficie", format="%.2f ha"),
                    "Δ NDVI": st.column_config.ProgressColumn(
                        "Cambio NDVI", format="%.3f", min_value=-0.4, max_value=0.6,
                    ),
                    "Compacidad": st.column_config.ProgressColumn(
                        "Compacidad", format="%.2f", min_value=0.0, max_value=1.0,
                        help="1.0 = forma regular (plantación) | <0.3 = forma irregular (incendio)",
                    ),
                    "Latitud GPS":  st.column_config.NumberColumn("Latitud",  format="%.6f"),
                    "Longitud GPS": st.column_config.NumberColumn("Longitud", format="%.6f"),
                },
                use_container_width=True,
                height=340,
                on_select="rerun",
                selection_mode="single-row",
            )

            # Mini-mapa del punto seleccionado
            filas_sel = seleccion.selection.rows if seleccion.selection else []
            if filas_sel:
                idx  = filas_sel[0]
                zona = zonas[idx]
                tipo_sel, _ = clasificar_tipo(
                    zona["caida_ndvi"], fecha1.month, zona["area_ha"],
                    ndvi_antes=zona["_ndvi_antes"],
                    ndvi_despues=zona["_ndvi_despues"],
                )

                st.markdown("---")
                col_info, col_map = st.columns([1, 3])

                with col_info:
                     st.markdown(f"### 📍 Zona seleccionada")
                     st.metric("Tipo", tipo_sel.split("(")[0].strip())
                     st.metric("Superficie", f"{zona['area_ha']} ha")
                     st.metric("Caída NDVI", f"-{zona['caida_ndvi']}")
                     st.metric("Severidad", zona["severidad"])
                     st.caption(f"📌 {zona['latitud']}, {zona['longitud']}")
                     st.link_button(
                         "🌍 Abrir en Google Maps",
                         f"https://www.google.com/maps?q={zona['latitud']},{zona['longitud']}&z=15",
                     )

                with col_map:
                    mini = folium.Map(
                        location=[zona["latitud"], zona["longitud"]],
                        zoom_start=14,
                        tiles="OpenStreetMap",
                        name="Mapa base",
                    )
                    # Capas Sentinel-2 del período base y reciente
                    img_bounds_mini = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]
                    if rgb1:
                        folium.raster_layers.ImageOverlay(
                            image=f"data:image/png;base64,{rgb1}",
                            bounds=img_bounds_mini,
                            opacity=0.95,
                            name=f"🛰️ Sentinel-2 {fecha1.strftime('%b %Y')} — base",
                            show=False,
                        ).add_to(mini)
                    if rgb2:
                        folium.raster_layers.ImageOverlay(
                            image=f"data:image/png;base64,{rgb2}",
                            bounds=img_bounds_mini,
                            opacity=0.95,
                            name=f"🛰️ Sentinel-2 {fecha2.strftime('%b %Y')} — reciente",
                            show=True,
                        ).add_to(mini)
                    folium.TileLayer(
                        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                        attr="Esri", name="Google Satellite (actual)",
                    ).add_to(mini)

                    # Sombreado del área afectada (toggleable)
                    geojson_zona = zona.get("_geojson")
                    if geojson_zona:
                        COLORES_FILL = {
                            "red":    ("#e74c3c", "#e74c3c"),
                            "orange": ("#e67e22", "#f39c12"),
                            "beige":  ("#f5cba7", "#e59866"),
                            "green":  ("#27ae60", "#2ecc71"),
                        }
                        fill, stroke = COLORES_FILL.get(zona["_color"], ("#888", "#888"))
                        grupo_sombra = folium.FeatureGroup(
                            name="🟥 Área afectada (sombreado)", show=True
                        )
                        folium.GeoJson(
                            geojson_zona,
                            style_function=lambda x, f=fill, s=stroke: {
                                "fillColor":   f,
                                "color":       s,
                                "weight":      2,
                                "fillOpacity": 0.4,
                                "opacity":     0.9,
                            },
                            tooltip=f"{zona['area_ha']} ha — {tipo_sel}",
                        ).add_to(grupo_sombra)
                        grupo_sombra.add_to(mini)

                    # Marcador central
                    folium.CircleMarker(
                        location=[zona["latitud"], zona["longitud"]],
                        radius=6, color=zona["_color"],
                        fill=True, fill_opacity=0.9,
                        popup=f"{tipo_sel} — {zona['area_ha']} ha",
                    ).add_to(mini)
                    folium.Marker(
                        location=[zona["latitud"], zona["longitud"]],
                        icon=folium.DivIcon(
                            html=f'<div style="font-size:11px;font-weight:bold;'
                                 f'background:white;padding:3px 6px;border-radius:4px;'
                                 f'border:2px solid {zona["_color"]};white-space:nowrap;">'
                                 f'{zona["area_ha"]} ha</div>',
                            icon_size=(80, 24), icon_anchor=(40, 12),
                        ),
                    ).add_to(mini)
                    folium.LayerControl(collapsed=False).add_to(mini)
                    st.components.v1.html(mini._repr_html_(), height=500)
                    if rgb1 and rgb2:
                        st.caption("💡 Activa/desactiva capas en el control del mapa para comparar vistas.")

            # Generación y Descarga de Reportes en Formato CSV
            csv_buf = io.StringIO()
            df.to_csv(csv_buf, index=False)
            
            st.download_button(
                label="⬇️ Descargar Reporte Completo de Alertas (CSV)",
                data=csv_buf.getvalue(),
                file_name=f"alertas_monitoreo_maule_{fecha1}_{fecha2}.csv",
                mime="text/csv",
                use_container_width=True,
            )
