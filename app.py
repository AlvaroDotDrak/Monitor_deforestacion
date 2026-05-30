import streamlit as st
import os

# ── Configuración Global de Página ──────────────────────────────────────────
st.set_page_config(
    page_title="Monitor IA — Deforestación e Incendios",
    page_icon="🌿",
    layout="wide",
)

# ── CSS global — cargado una sola vez para todas las páginas ─────────────────
@st.cache_data
def _cargar_css():
    if os.path.exists("style.css"):
        with open("style.css", encoding="utf-8") as f:
            return f.read()
    return ""

css = _cargar_css()
if css:
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

# ── Configuración de Páginas y Navegación Multipage ─────────────────────────
inicio_page = st.Page(
    "pages/0_Inicio.py",
    title="Inicio",
    icon="🏠",
    default=True
)

analisis_page = st.Page(
    "pages/1_Análisis.py",
    title="Módulo de Análisis",
    icon="🔍"
)

historico_page = st.Page(
    "pages/2_Histórico.py",
    title="Histórico NDVI",
    icon="📈"
)

metodologia_page = st.Page(
    "pages/3_Metodología.py",
    title="Metodología",
    icon="📚"
)

# ── Crear la Barra de Navegación ─────────────────────────────────────────────
pg = st.navigation([inicio_page, analisis_page, historico_page, metodologia_page])
pg.run()
