# AGENTS.md — Instrucciones para agentes de IA

Este archivo explica el proyecto y cómo continuar trabajando en él.
Lee también `CLAUDE.md` para contexto técnico completo.

---

## Contexto del proyecto

Sistema de monitoreo satelital para detectar tala ilegal e incendios forestales en Chile.
Usuario: Álvaro (estudiante INACAP, ramo Innovación e Intraemprendimiento 2).
Nivel Python: básico-intermedio. Prefiere explicaciones claras antes de implementar.

**Objetivo de negocio:** Herramienta para CONAF y dueños de terrenos que detecta
cambios de vegetación en imágenes Sentinel-2 y clasifica si es tala o incendio.

---

## Cómo trabaja el usuario con agentes IA

- Usa múltiples agentes en paralelo (Claude, Gemini, Cursor, etc.)
- Pide explicación antes de implementar cambios grandes
- Le gusta entender qué hace cada parte antes de correrla
- Trabaja en `/home/alvaro/Documentos/Monitor_IA/`

---

## Estado actual del proyecto

**Lo que YA funciona:**
- Dashboard Streamlit completo (`app.py`) con descarga automática de Sentinel Hub
- Clasificador Random Forest 3 clases (tala / incendio / sin cambio)
- Detección de zonas con polígonos reales en mapa Folium interactivo
- Sombreado toggleable, capas Sentinel-2 RGB, mini-mapa por zona
- Sistema de caché en `cache/` para no re-descargar imágenes
- Entrenamiento multi-zona, multi-año, multi-estación (`entrenar_modelo.py`)

**Lo que está PENDIENTE (próximas tareas sugeridas):**
1. Subir a GitHub + desplegar en Streamlit Cloud
2. Calculadora de CO₂ (hectáreas → toneladas carbono)
3. Gráfico histórico NDVI del CSV en el dashboard
4. Verificar que la detección de incendios mejore tras reentrenar con zona 3

---

## Reglas importantes al modificar código

### NO romper estas cosas:
- `clasificar_tipo()` en `core.py` debe ser compatible con modelos de 2 Y 3 clases
- `descargar_compuesto()` en `copernicus_api.py` debe seguir usando la caché de `cache/`
- El modo demo de `app.py` usa archivos TIFF locales — no eliminarlos del flujo
- La firma de `detectar_zonas()` incluye `nbr1` y `nbr2` opcionales — mantenerlos opcionales

### Siempre verificar:
```bash
python3 -c "import ast; ast.parse(open('core.py').read()); print('OK')"
python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```

---

## Arquitectura de archivos clave

```
app.py              # Streamlit UI — solo presentación y flujo
core.py             # Toda la lógica de análisis (importar desde aquí)
copernicus_api.py   # Solo comunicación con Sentinel Hub API
entrenar_modelo.py  # Script standalone — no se importa desde app.py
```

**Regla:** `app.py` no debe tener lógica de análisis. Todo va en `core.py`.

---

## Funciones principales en core.py

```python
calcular_ndvi(b04, b08)          # → array NDVI
calcular_nbr(b08, b12)           # → array NBR (B12 puede ser None → retorna None)
crear_compuesto(lista_b04, lista_b08, lista_b12=None)  # → b04_med, b08_med, ndvi_med, b12_med
detectar_zonas(cambio, transform, bounds, umbral=0.15, min_ha=0.5, ndvi1, ndvi2, nbr1, nbr2)
clasificar_tipo(caida_ndvi, mes_inicio, area_ha, ndvi_antes, ndvi_despues, compacidad, nbr_antes, nbr_despues)
crear_mapa(zonas, bounds, mes_inicio)  # → folium.Map con polígonos y markers
```

---

## API de Copernicus

```python
from copernicus_api import obtener_token, descargar_compuesto, descargar_rgb

token = obtener_token(usuario, contrasena)

# Descarga composite B04+B08+B12 (con caché automática)
ruta = descargar_compuesto(token, bbox, "2024-06-01", "2024-08-31", max_nubes=10)

# Lee las 3 bandas del composite
with rasterio.open(ruta) as src:
    b04 = src.read(1).astype(float)
    b08 = src.read(2).astype(float)
    b12 = src.read(3).astype(float)  # siempre hay 3 bandas
```

**bbox formato:** `[lon_oeste, lat_sur, lon_este, lat_norte]`
**Coordenadas zona principal:** `[-72.34, -35.38, -72.17, -35.27]`

---

## Modelo ML

```python
import joblib
modelo = joblib.load('modelo_clasificador.pkl')
# modelo.classes_ → [0, 1, 2] si es el nuevo (3 clases)
# modelo.classes_ → [0, 1]    si es el anterior (2 clases)
# modelo.feature_importances_ → 9 features si tiene NBR, 6 si no
```

**No sobreescribir** `modelo_clasificador.pkl` sin correr `entrenar_modelo.py` primero.

---

## Sesión de entrenamiento

```bash
python3 entrenar_modelo.py
# Pide usuario/contraseña de dataspace.copernicus.eu
# ~50 descargas (con caché son instantáneas si ya existen)
# ~45-60 minutos la primera vez, ~15 min con caché completa
# Genera modelo_clasificador.pkl con 3 clases
```

**Zonas de entrenamiento:**
- `[-72.34, -35.38, -72.17, -35.27]` — Constitución/Maule (tala)
- `[-72.60, -37.40, -72.20, -37.10]` — Nacimiento/Biobío (tala)
- `[-73.20, -37.00, -72.80, -36.55]` — Penco/Tomé 2026 (incendio)

---

## Tareas frecuentes

### Agregar una nueva categoría de detección
1. Modificar `clasificar_tipo()` en `core.py`
2. Agregar color en `COLORES_FILL` de `crear_mapa()` y del mini-mapa en `app.py`
3. Si necesita nueva clase ML → reentrenar `entrenar_modelo.py`

### Agregar una nueva zona geográfica al entrenamiento
1. Agregar a `ZONAS_TALA` o crear una nueva `ZONA_INCENDIO` en `entrenar_modelo.py`
2. Correr el script (descargará los nuevos composites, los demás quedan en caché)

### Cambiar el área de análisis (bbox)
1. Modificar `BBOX` en `app.py` (línea ~18)
2. Limpiar `cache/` si se quiere re-descargar para el nuevo área

### Agregar nueva feature al modelo
1. Calcular el array de la feature en `detectar_zonas()` y guardarlo en el dict de zona
2. Pasarlo a `clasificar_tipo()` en los 3 lugares donde se llama
3. Actualizar `extraer()` en `entrenar_modelo.py`
4. Reentrenar

---

## Problemas conocidos y soluciones

| Problema | Causa | Solución |
|---|---|---|
| `ValueError: X has N features, model expects M` | Modelo entrenado con distinto nº features | Reentrenar o usar el modelo correcto |
| `KeyError: comp_1_transform` | Session state con datos del modelo anterior | Re-descargar compuestos (click Analizar de nuevo) |
| `El producto no tiene nodos accesibles` | API antigua de OData — ya no funciona | Usar solo `descargar_compuesto()` (Sentinel Hub) |
| Imagen muy pixelada | Resolución en 20m | Cambiar `resolucion=10` en `descargar_rgb()` |
| Mapa muy lento | Demasiados polígonos GeoJSON | Aumentar `min_ha` en el slider del sidebar |

---

## Credenciales

**Nunca hardcodear credenciales en el código.**
El usuario tiene cuenta en `dataspace.copernicus.eu`.
En el dashboard las ingresa por el sidebar cada sesión.
En `entrenar_modelo.py` las pide por terminal con `getpass`.

---

## Próximas mejoras sugeridas (por prioridad)

1. **Streamlit Cloud deploy** — crear `.gitignore`, subir a GitHub, conectar share.streamlit.io
2. **Calculadora CO₂** — 1 ha bosque ≈ 150-300 ton CO₂; agregar métrica en el dashboard
3. **Gráfico histórico NDVI** — usar el CSV de 5 años ya analizado, mostrar con plotly
4. **Detección de agua (NDWI)** — banda B03, útil para distinguir inundaciones de talas
5. **Notificaciones** — email/Telegram cuando se detecta alerta grave en zona monitoreada
