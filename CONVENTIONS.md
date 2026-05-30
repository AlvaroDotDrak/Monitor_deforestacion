# CONVENTIONS.md — Convenciones del proyecto

> Seguir estas reglas mantiene el código consistente cuando trabajan múltiples agentes.

---

## Idioma

- **Código (variables, funciones, clases):** español
- **Comentarios:** español, solo cuando el "por qué" no es obvio
- **Strings de UI (mensajes al usuario):** español
- **Commits de git:** español

---

## Nombres de variables

```python
# Bandas satelitales → b04, b08, b12 (minúscula + número)
b04_base    = ...
b08_reciente = ...

# Arrays NDVI/NBR → ndvi1, ndvi2 / nbr1, nbr2
# ndvi1 = período base, ndvi2 = período reciente
ndvi1 = calcular_ndvi(b04, b08)

# Zonas detectadas → siempre lista de dicts con las mismas keys
zona = {
    "latitud":       float,
    "longitud":      float,
    "area_ha":       float,
    "caida_ndvi":    float,   # positivo = pérdida, negativo = ganancia
    "severidad":     str,     # "Grave" | "Moderada" | "Leve" | "Recuperación"
    "compacidad":    float,   # 0-1
    "tipo_evento":   str,     # "perdida" | "recuperacion"
    "_color":        str,     # color folium: "red" | "orange" | "green" | "beige"
    "_geojson":      dict,    # geometría GeoJSON del polígono real
    "_ndvi_antes":   float | None,
    "_ndvi_despues": float | None,
    "_nbr_antes":    float | None,
    "_nbr_despues":  float | None,
}

# Bounding box → siempre lista [lon_oeste, lat_sur, lon_este, lat_norte]
BBOX = [-72.34, -35.38, -72.17, -35.27]

# Fechas → siempre strings "YYYY-MM-DD"
desde = "2022-06-01"
hasta = "2022-08-31"
```

---

## Estructura de archivos

```
core.py            # Solo funciones puras — SIN imports de streamlit
app.py             # Solo UI — toda la lógica va en core.py
copernicus_api.py  # Solo comunicación con la API — SIN lógica de análisis
entrenar_modelo.py # Script standalone — NO importar desde otros archivos
```

**Regla:** Si una función se necesita en más de un lugar → va en `core.py`.

---

## Funciones

```python
# Nombres en español, snake_case
def calcular_ndvi(b04, b08):        # ✅
def calculateNDVI(B04, B08):        # ❌

# Parámetros opcionales que pueden ser None → siempre con default None
def clasificar_tipo(caida_ndvi, mes_inicio, area_ha,
                    ndvi_antes=None, ndvi_despues=None,  # opcionales
                    compacidad=None, nbr_antes=None, nbr_despues=None):

# Retorno de clasificar_tipo → siempre tupla (str, str_color_hex)
return "🔥 Incendio Forestal", "#e74c3c"   # ✅
return "Incendio"                           # ❌ falta el color

# Retorno de crear_compuesto → siempre 4 valores aunque b12 sea None
return b04_med, b08_med, ndvi_med, b12_med  # b12_med puede ser None
```

---

## Manejo de None / NaN

```python
# Arrays NDVI/NBR pueden tener NaN en bordes o nubes — siempre verificar
np.seterr(divide='ignore', invalid='ignore')  # al inicio de cálculos
valido = ~np.isnan(ndvi1) & ~np.isnan(ndvi2)  # máscara de píxeles válidos

# Parámetros None → usar valores neutros, NO lanzar error
_nbr_a = nbr_antes if nbr_antes is not None else 0.5
```

---

## Streamlit session_state

Claves estandarizadas (no inventar nuevas sin documentarlas):

```python
# Resultados del análisis
st.session_state["ndvi1"]           # array numpy
st.session_state["ndvi2"]           # array numpy
st.session_state["cambio"]          # array numpy
st.session_state["zonas"]           # lista de dicts
st.session_state["mapa"]            # objeto folium.Map
st.session_state["mascara_alerta"]  # array bool
st.session_state["bounds"]          # rasterio BoundingBox
st.session_state["fecha1"]          # date
st.session_state["fecha2"]          # date
st.session_state["modo_label"]      # str (descripción del modo)

# Composites descargados (prefijo comp_1_ = base, comp_2_ = reciente)
st.session_state["comp_1_b04"]        # lista de arrays numpy
st.session_state["comp_1_b08"]        # lista de arrays numpy
st.session_state["comp_1_b12"]        # lista de arrays numpy (puede ser None)
st.session_state["comp_1_transform"]  # rasterio transform
st.session_state["comp_1_bounds"]     # rasterio BoundingBox
st.session_state["comp_1_fecha"]      # date
st.session_state["comp_1_rgb"]        # str base64 PNG

# Año/estación seleccionados en sidebar
st.session_state["ano_base"]      # int
st.session_state["ano_reciente"]  # int
st.session_state["estacion"]      # str ("❄️ Invierno (Jun–Ago)" etc.)
```

---

## Caché de archivos

```python
# Nombre de archivo en cache/ → generado por _nombre_cache() en copernicus_api.py
# Formato: comp_{bbox}_{desde}_{hasta}_{nubes}nc_{tipo}.tiff
# Ejemplo: comp_-72.34_-35.38_-72.17_-35.27_2022-06-01_2022-08-31_10nc_ndvi.tiff

# NUNCA borrar cache/ sin avisar — contiene horas de descargas
# Para invalidar caché de un período específico → borrar el archivo puntual
```

---

## Categorías de detección (emojis fijos)

```python
"🔥 Incendio Forestal — Alta severidad"      # delta_nbr < -0.44
"🔥 Incendio Forestal — Severidad moderada"  # delta_nbr < -0.27
"🔥 Incendio Forestal — Baja severidad"      # delta_nbr < -0.10
"🪓 Tala Industrial"                          # area >= 10 ha, forma compacta
"✂️ Tala Selectiva"                           # area < 10 ha
"🌱 Recuperación / Replante"                  # NDVI aumentando
"📉 Degradación Gradual"                      # caída moderada difusa
"🟢 Sin cambio significativo"                 # sin cambio real

# Colores hexadecimales asociados (NO cambiar — consistencia en mapas y tablas)
COLORES = {
    "incendio_alto":    "#c0392b",
    "incendio_moderado":"#e74c3c",
    "incendio_bajo":    "#e67e22",
    "tala_industrial":  "#e67e22",
    "tala_selectiva":   "#f39c12",
    "recuperacion":     "#27ae60",
    "degradacion":      "#8e44ad",
    "sin_cambio":       "#95a5a6",
}
```

---

## Lo que NO hacer

```python
# ❌ No hardcodear credenciales
token = obtener_token("correo@gmail.com", "password123")  # NUNCA

# ❌ No usar tempfile para composites (se pierde entre sesiones)
carpeta = tempfile.mkdtemp()  # Solo para entrenar_modelo.py, NO en app.py

# ❌ No importar streamlit en core.py
import streamlit as st  # ❌ en core.py

# ❌ No cambiar la firma de detectar_zonas() sin actualizar app.py también
# ❌ No sobreescribir modelo_clasificador.pkl sin correr entrenar_modelo.py
# ❌ No mezclar estaciones en comparaciones (verano vs invierno = ruido)
```
