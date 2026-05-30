# Monitor IA — Detección de Deforestación e Incendios

## Descripción del proyecto
Sistema de monitoreo satelital que detecta pérdida de vegetación (deforestación, tala ilegal, incendios) usando imágenes Sentinel-2 de Copernicus y un clasificador Random Forest entrenado con datos de Global Forest Watch (Hansen GFC) y datos de incendios reales.

Proyecto académico para ramo Innovación e Intraemprendimiento 2 — INACAP.
Orientado a CONAF y dueños de terrenos forestales para detectar tala ilegal.

## Área de interés principal
Zona de Constitución / Putú / Carrizal, Región del Maule, Chile.
- Bounding box: `[-72.34, -35.38, -72.17, -35.27]`
- Hay empresas forestales activas (CMPC, Arauco) con ciclos de cosecha y replante

## Archivos del proyecto

| Archivo | Descripción |
|---|---|
| `app.py` | Dashboard principal Streamlit |
| `core.py` | Funciones análisis: NDVI, NBR, zonas, mapa, clasificador |
| `copernicus_api.py` | API Copernicus: búsqueda + descarga con caché |
| `entrenar_modelo.py` | Entrenamiento multi-zona, multi-año, multi-estación |
| `modelo_clasificador.pkl` | Modelo Random Forest (generado por entrenar_modelo.py) |
| `analizar_ndvi.py` | Script standalone (no parte del dashboard) |
| `requirements.txt` | Dependencias Python |
| `cache/` | Composites descargados (no re-descargar) |

## Cómo ejecutar

```bash
# Dashboard
streamlit run app.py

# Reentrenar modelo (solo cuando se quiera mejorar)
python3 entrenar_modelo.py

# Instalar dependencias
pip install -r requirements.txt
```

## Fuentes de datos

### Sentinel-2 L2A via Sentinel Hub Process API
- Endpoint: `https://sh.dataspace.copernicus.eu/api/v1/process`
- Autenticación: usuario/contraseña de `dataspace.copernicus.eu`
- Bandas usadas: B04 (rojo), B08 (NIR), B12 (SWIR)
- Índices calculados: NDVI = (B08-B04)/(B08+B04), NBR = (B08-B12)/(B08+B12)
- Resolución: 20m/pixel para análisis, 10m para RGB visual

### Hansen GFC 2023 (Global Forest Watch)
- Tile: `Hansen_GFC-2023-v1.11_lossyear_30S_080W.tif`
- URL: `https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11/`
- Resolución: 30m/pixel
- Cubre lat -30° a -40°, lon -70° a -80° (toda la zona de interés)
- Valor 0 = sin pérdida, 1-23 = año de pérdida (2001-2023)

### CSV NDVI histórico (Copernicus Statistical API)
- Archivo: `Sentinel-2 L2A-3_NDVI-*.csv`
- Cobertura: Mayo 2021 — presente, cada ~5 días

## Clasificador ML

### Estado actual
Modelo Random Forest **3 clases** con 9 features.
Se carga automáticamente desde `modelo_clasificador.pkl` al iniciar la app.

### Features del modelo (9)
| Feature | Descripción |
|---|---|
| ndvi_antes | NDVI período base |
| ndvi_despues | NDVI período reciente |
| delta_ndvi | Cambio de NDVI |
| mes | Mes del año (1-12) |
| compacidad | Forma de la zona (1=regular, 0=irregular) |
| area_ha | Área en hectáreas |
| nbr_antes | NBR período base |
| nbr_despues | NBR período reciente |
| delta_nbr | Cambio de NBR (negativo = quema) |

### Clases
- `0` = Sin cambio significativo
- `1` = Tala / Cosecha forestal
- `2` = Incendio forestal

### Datos de entrenamiento
**Zonas de tala:**
- Constitución/Maule: `[-72.34, -35.38, -72.17, -35.27]`
- Nacimiento/Biobío: `[-72.60, -37.40, -72.20, -37.10]`

**Zona de incendio:**
- Penco/Tomé/Lirquén enero 2026: `[-73.20, -37.00, -72.80, -36.55]`
- Base: Oct-Dic 2025 | Reciente: Feb-Mar 2026

**Pares de años:** 3 pares × 4 estaciones × 2 zonas tala + 1 incendio ≈ 50 descargas

**Etiquetado incendio:** pixels con `delta_nbr < -0.27` = incendio confirmado

### Compatibilidad con modelo anterior
`clasificar_tipo()` detecta automáticamente si el modelo tiene 2 o 3 clases.
Si no hay modelo, cae a reglas heurísticas.

## Sistema de caché
Los composites se guardan en `cache/` para no re-descargar.
Nombre: `comp_{bbox}_{desde}_{hasta}_{nubes}nc_{tipo}.tiff`
- Primera descarga: ~30-60 seg por composite
- Con caché: instantáneo

## Dashboard (app.py)

### Flujo de uso
1. Usuario ingresa credenciales Copernicus en sidebar
2. Selecciona año base, año reciente y estación (invierno/verano/etc.)
3. Presiona **Analizar** → descarga 2 composites (con caché) → analiza
4. Ve resultados en 3 tabs: Análisis NDVI | Mapa de alertas | Tabla de alertas

### Atajos rápidos
- "2 años" → year-3 vs year-1
- "5 años" → year-6 vs year-1
- "🔥 2017" → 2016 vs 2018, invierno (megaincendio Chile)

### Funcionalidades del mapa
- Capas de sombreado con polígonos reales de cada zona (toggleable)
- Capas RGB Sentinel-2 del período base y reciente (toggleable)
- Al seleccionar fila en tabla → mini-mapa satelital con sombreado + Google Maps
- LayerControl con: OpenStreetMap, Satélite Esri, Sentinel base, Sentinel reciente, áreas afectadas, áreas recuperación

### Categorías de detección
- 🔥 Incendio Forestal (alta/moderada/baja severidad)
- 🪓 Tala Industrial (>10 ha, forma compacta)
- ✂️ Tala Selectiva (<10 ha)
- 🌱 Recuperación / Replante (NDVI aumentando)
- 📉 Degradación Gradual
- 🟢 Sin cambio significativo

## Despliegue Streamlit Cloud

1. Subir carpeta a GitHub (excluir *.tiff, *.pkl, cache/)
2. En `share.streamlit.io` → conectar repo → seleccionar `app.py`
3. El usuario sube sus propios archivos o usa descarga automática

### .gitignore recomendado
```
*.tiff
*.tif
*.pkl
cache/
__pycache__/
.env
```

## Estado del proyecto (mayo 2026)

### Completado
- [x] Análisis NDVI con dos períodos (compuestos de mediana)
- [x] Detección de zonas con scipy (pérdida + recuperación)
- [x] Mapa interactivo Folium con polígonos reales de cada zona
- [x] Sombreado toggleable de áreas afectadas
- [x] Capas RGB Sentinel-2 en el mapa (imagen real de cada período)
- [x] Mini-mapa satelital al seleccionar fila en tabla
- [x] Botón "Abrir en Google Maps" con coordenadas
- [x] Export CSV de alertas
- [x] Dashboard Streamlit con tabs y métricas
- [x] Clasificador Random Forest 3 clases (sin cambio / tala / incendio)
- [x] Features: NDVI + NBR + compacidad + área + mes
- [x] Entrenamiento multi-zona (Maule + Biobío + incendio 2026)
- [x] Entrenamiento multi-año (2020-2024) y multi-estación (4 estaciones)
- [x] B12 incluida en todas las descargas automáticas
- [x] Sistema de caché en cache/
- [x] Módulo API Copernicus (búsqueda + descarga con caché)
- [x] CLAUDE.md y AGENTS.md

### Pendiente
- [ ] Despliegue en Streamlit Cloud (subir a GitHub primero)
- [ ] Detección de incendios con B12 verificada con datos reales post-entrenamiento
- [ ] Calculadora de impacto CO₂ (hectáreas → toneladas carbono)
- [ ] Gráfico histórico NDVI del CSV en el dashboard
