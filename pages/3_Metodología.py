import streamlit as st
import os


# ── Banner de Bienvenida Premium ───────────────────────────────────────────────
st.markdown(
    """
    <div style="background: linear-gradient(135deg, #221226 0%, #0e0710 100%); 
                padding: 25px 35px; border-radius: 16px; margin-bottom: 25px; 
                border-left: 8px solid #9b59b6; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
        <h1 style="color: white; margin: 0; font-size: 30px; font-weight: 700; display: flex; align-items: center; font-family: 'Outfit', sans-serif;">
            <span style="margin-right: 15px;">📚</span> Metodología Científica e IA
        </h1>
        <p style="color: #dfcbe6; margin: 8px 0 0 0; font-size: 14.5px; font-family: 'Outfit', sans-serif; opacity: 0.9; line-height: 1.5;">
            Conoce los fundamentos matemáticos de los índices multiespectrales (NDVI y NBR), el flujo de extracción de formas vectoriales y la arquitectura del modelo RandomForestClassifier.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("## 🛰️ 1. Índices Multiespectrales (Sentinel-2)")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <div class="card-teoria">
            <h3>🌿 Índice de Vegetación de Diferencia Normalizada (NDVI)</h3>
            <p>El NDVI es el índice más utilizado para medir la cantidad y salud de la vegetación verde activa. Aprovecha el fuerte contraste de reflectancia que la clorofila tiene en las bandas del <b>Rojo visible (Red)</b> y el <b>Infrarrojo Cercano (NIR)</b>.</p>
            <div style="text-align: center; margin: 15px 0;">
                <p style="font-size: 18px; font-weight: bold; color: #2ecc71;">
                    $$\\text{NDVI} = \\frac{\\text{B08} - \\text{B04}}{\\text{B08} + \\text{B04}}$$
                </p>
            </div>
            <ul>
                <li><b>B08 (Infrarrojo Cercano):</b> Reflejado fuertemente por la estructura celular interna de las hojas sanas.</li>
                <li><b>B04 (Rojo visible):</b> Absorbido fuertemente por la clorofila para realizar la fotosíntesis.</li>
                <li><b>Rango:</b> -1.0 a +1.0. La vegetación densa y sana oscila entre <b>0.6 y 0.9</b>, mientras que el suelo desnudo, rocas o incendios caen a valores inferiores a <b>0.15</b>.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True
    )

with col2:
    st.markdown(
        """
        <div class="card-teoria">
            <h3>🔥 Índice de Relación de Quema Normalizado (NBR)</h3>
            <p>El NBR está diseñado específicamente para resaltar áreas quemadas y estimar la severidad del fuego. Combina la reflectancia del <b>Infrarrojo Cercano (NIR)</b> y la del <b>Infrarrojo de Onda Corta (SWIR)</b>.</p>
            <div style="text-align: center; margin: 15px 0;">
                <p style="font-size: 18px; font-weight: bold; color: #e74c3c;">
                    $$\\text{NBR} = \\frac{\\text{B08} - \\text{B12}}{\\text{B08} + \\text{B12}}$$
                </p>
            </div>
            <ul>
                <li><b>B08 (Infrarrojo Cercano):</b> La vegetación sana refleja mucho esta banda.</li>
                <li><b>B12 (Infrarrojo de Onda Corta):</b> El carbón, cenizas y suelo quemado reflejan fuertemente esta longitud de onda, mientras que las plantas sanas la absorben.</li>
                <li><b>Diferencial (ΔNBR):</b> Se calcula restando el NBR posterior al incendio del anterior. Un valor <b>&Delta;NBR < -0.27</b> es un fuerte indicador de zonas afectadas por fuego reciente.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()

st.markdown("## 🧠 2. Clasificación Inteligente (Machine Learning)")

col3, col4 = st.columns([3, 2])

with col3:
    st.markdown(
        """
        El núcleo de clasificación del Monitor IA utiliza un modelo **Random Forest (Bosque Aleatorio)** optimizado para clasificar anomalías en 3 clases:
        1. 🟢 **Sin Cambio Significativo:** Terreno estable, estacionalidad habitual o recuperación lenta.
        2. 🪓 **Tala / Cosecha Forestal:** Pérdida de cobertura de origen antropogénico (explotación industrial o tala selectiva).
        3. 🔥 **Incendio Forestal:** Pérdida violenta de vegetación con firma térmica de quema (carbonización y pérdida extrema de humedad).
        
        ### Vector de Características (9 Features)
        Para cada zona detectada, se extrae una firma geométrica y radiométrica completa que se alimenta al clasificador:
        """
    )
    
    features_data = {
        "Característica": [
            "ndvi_antes", "ndvi_despues", "delta_ndvi", 
            "nbr_antes", "nbr_despues", "delta_nbr",
            "mes", "area_ha", "compacidad"
        ],
        "Tipo": [
            "Radiométrica", "Radiométrica", "Diferencial",
            "Radiométrica", "Radiométrica", "Diferencial",
            "Temporal", "Geométrica", "Geométrica"
        ],
        "Descripción": [
            "NDVI medio del área antes del período analizado.",
            "NDVI medio del área en el período reciente.",
            "Variación absoluta del NDVI (NDVI Reciente - NDVI Base).",
            "NBR medio del área antes del período analizado (indica humedad y carbón base).",
            "NBR medio del área en el período reciente (indica afectación por fuego).",
            "Variación del NBR (NBR Reciente - NBR Base). Valores muy negativos indican fuego.",
            "Mes de inicio del período de análisis (captura el ciclo estacional de cosechas/incendios).",
            "Superficie total de la perturbación en hectáreas.",
            "Relación área/perímetro. Formas regulares (cuadradas, plantaciones) tienen valores altos (~1). Formas ramificadas (incendios) tienen valores muy bajos."
        ]
    }
    st.table(features_data)

with col4:
    st.markdown(
        """
        <div class="card-teoria" style="border-top: 4px solid #9b59b6;">
            <h3>📊 Datos de Entrenamiento</h3>
            <p>El modelo fue entrenado utilizando datos georreferenciados reales en el centro-sur de Chile:</p>
            <ul>
                <li><b>Zonas de Tala Maule:</b> Constitución / Putú / Carrizal (historias de replante y cosecha).</li>
                <li><b>Zonas de Tala Biobío:</b> Nacimiento / Angol (alta actividad forestal comercial).</li>
                <li><b>Zonas de Incendio Biobío:</b> Penco / Tomé / Lirquén (incendios forestales de enero de 2026, etiquetados mediante severidad NBR de campo).</li>
            </ul>
            <p><b>Por qué Random Forest:</b></p>
            <ul>
                <li>Alta interpretabilidad de características.</li>
                <li>Ejecución e inferencia inmediata sin necesidad de GPU en el servidor.</li>
                <li>Robustez ante valores atípicos y datos con ruido por nubes.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()

st.markdown("## 🗺️ 3. Detección y Vectorización de Contornos")
st.markdown(
    """
    En lugar de generar marcadores circulares aproximados, la plataforma extrae la geometría exacta del daño. El flujo matemático y computacional es el siguiente:
    """
)

pasos_det = {
    "Paso": ["1. Cálculo Diferencial", "2. Umbralización", "3. Etiquetado Conectado", "4. Vectorización GeoJSON"],
    "Operación": [
        "Se calcula la diferencia píxel a píxel: $\\Delta\\text{NDVI} = \\text{NDVI}_2 - \\text{NDVI}_1$",
        "Se aplica un umbral binario. Los píxeles donde $\\Delta\\text{NDVI} < -\\text{Umbral}$ se marcan como perturbados.",
        "Se agrupan los píxeles vecinos conectados usando el algoritmo de etiquetado de componentes de `scipy.ndimage.label`.",
        "Se calculan los contornos geométricos reales de cada zona utilizando `rasterio.features.shapes()`, convirtiéndolos en polígonos georreferenciados (GeoJSON) que se grafican en el mapa interactivo."
    ]
}
st.table(pasos_det)
