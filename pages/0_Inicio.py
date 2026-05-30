import streamlit as st
import os

# ── Inyección de CSS Personalizado (Estilo Moderno & Premium) ──────────────────
if os.path.exists("style.css"):
    with open("style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ── Banner de Bienvenida Premium ───────────────────────────────────────────────
st.markdown(
    """
    <div style="background: linear-gradient(135deg, #132e18 0%, #08170d 100%); 
                padding: 30px 40px; border-radius: 16px; margin-bottom: 30px; 
                border-left: 8px solid #2ecc71; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
        <h1 style="color: white; margin: 0; font-size: 34px; font-weight: 700; display: flex; align-items: center; font-family: 'Outfit', sans-serif;">
            <span style="margin-right: 15px;">🌿</span> Monitor IA — Detección de Deforestación e Incendios
        </h1>
        <p style="color: #a3e2b2; margin: 10px 0 0 0; font-size: 15.5px; font-family: 'Outfit', sans-serif; opacity: 0.9; line-height: 1.6;">
            Plataforma avanzada de monitoreo satelital con imágenes <b>Sentinel-2</b> de Copernicus. 
            Aplica algoritmos de procesamiento digital y modelos de Inteligencia Artificial para detectar pérdida de vegetación, tala ilegal e incendios forestales en la zona centro-sur de Chile.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# ── Introducción y Flujo del Sistema ───────────────────────────────────────────
st.markdown("## 🧭 Acceso a las Secciones de la Plataforma")
st.markdown("Usa el menú lateral o los siguientes enlaces rápidos para navegar por los diferentes módulos del sistema:")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        """
        <div class="card-inicio">
            <h3>🔍 Módulo de Análisis</h3>
            <p>Compara imágenes de Sentinel-2 de dos períodos históricos para detectar y clasificar alertas en tiempo real. Permite descargar reportes y vectorizar áreas dañadas.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)
    st.page_link("pages/1_Análisis.py", label="Ir al Análisis Comparativo", icon="🔍", use_container_width=True)

with col2:
    st.markdown(
        """
        <div class="card-inicio">
            <h3>📈 Histórico de NDVI</h3>
            <p>Visualiza y filtra series de tiempo del NDVI promedio, mínimo y máximo en los últimos 5 años de la zona monitoreada. Ideal para ver la recuperación y estacionalidad.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)
    st.page_link("pages/2_Histórico.py", label="Ver Histórico Temporal", icon="📈", use_container_width=True)

with col3:
    st.markdown(
        """
        <div class="card-inicio">
            <h3>📚 Metodología Científica</h3>
            <p>Conoce en detalle el funcionamiento matemático de los índices espectrales (NDVI, NBR), las características del modelo de IA (Random Forest) y los datos de entrenamiento.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)
    st.page_link("pages/3_Metodología.py", label="Ver Teoría y Modelado", icon="📚", use_container_width=True)

st.divider()

# ── Características de la Plataforma ───────────────────────────────────────────
st.markdown("## ⚙️ Características Principales del Monitor Satelital")

c_col1, c_col2 = st.columns(2)

with c_col1:
    st.markdown(
        """
        * **🛰️ Descarga de Sentinel Hub (Process API):** El sistema se conecta directamente a la API de Copernicus para descargar los compuestos de mediana filtrando nubosidad. Esto reduce el consumo de datos de ~600MB a ~4MB por consulta.
        * **🧠 Inteligencia Artificial:** Un clasificador Random Forest (Entrenado en Nacimiento, Constitución y Tomé) decide automáticamente si la caída de vegetación corresponde a un proceso de cosecha forestal (Tala Industrial o Tala Selectiva) o a un Incendio Forestal.
        * **🗺️ Polígonos de Afectación Reales:** A través de la vectorización espectral con rasterio, el sistema delinea el contorno exacto de cada perturbación y calcula su área precisa en hectáreas.
        """
    )

with c_col2:
    st.markdown(
        """
        * **⚡ Modo Demostración Integrado:** Explora de inmediato las capacidades del sistema en la Región del Maule (Constitución) con datos locales precargados de 2022 y 2024 sin necesidad de ingresar credenciales.
        * **🗄️ Sistema de Caché Inteligente:** Los composites multiespectrales se almacenan localmente en la carpeta `cache/` para optimizar consultas repetidas y entrenamientos.
        * **🗺️ Mini-Mapas Satelitales e Integración GPS:** Al seleccionar cualquier alerta en el listado, el sistema genera dinámicamente un mapa local superpuesto con la capa Sentinel y proporciona un enlace directo a Google Maps.
        """
    )

st.divider()

# ── Footer / Info Académica ───────────────────────────────────────────────────
st.markdown(
    """
    <div style="text-align: center; color: #718096; font-size: 13px; margin-top: 20px;">
        <p><b>Monitor IA — Sistema de Monitoreo de Deforestación e Incendios</b></p>
        <p>Proyecto desarrollado para el ramo de <i>Innovación e Intraemprendimiento 2</i> | <b>INACAP</b></p>
    </div>
    """,
    unsafe_allow_html=True
)
