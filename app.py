import streamlit as st

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
