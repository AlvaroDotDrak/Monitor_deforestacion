import numpy as np
import rasterio
import rasterio.warp
from rasterio.features import shapes as rasterio_shapes
from rasterio.io import MemoryFile
from rasterio.transform import xy
from rasterio.enums import Resampling
from scipy import ndimage
import folium
import math
import os
import joblib

# Cargar modelo ML si existe, si no usa reglas heurísticas
_MODELO_PATH = os.path.join(os.path.dirname(__file__), 'modelo_clasificador.pkl')
_modelo_rf = joblib.load(_MODELO_PATH) if os.path.exists(_MODELO_PATH) else None


def leer_banda(fuente):
    """Lee una banda desde ruta de archivo o bytes subidos por Streamlit."""
    if isinstance(fuente, str):
        with rasterio.open(fuente) as src:
            return src.read(1).astype(float), src.transform, src.bounds
    else:
        with MemoryFile(fuente.read()) as memfile:
            with memfile.open() as src:
                return src.read(1).astype(float), src.transform, src.bounds


def calcular_ndvi(b04, b08):
    np.seterr(divide='ignore', invalid='ignore')
    return np.where((b08 + b04) == 0, np.nan, (b08 - b04) / (b08 + b04))


def calcular_nbr(b08, b12):
    """NBR = (B08 - B12) / (B08 + B12). Negativo = zona quemada."""
    np.seterr(divide='ignore', invalid='ignore')
    return np.where((b08 + b12) == 0, np.nan, (b08 - b12) / (b08 + b12))


BBOX_DEFAULT = [-72.34, -35.38, -72.17, -35.27]  # Constitución / Maule
MAX_PIXELS   = 2500  # límite Copernicus por dimensión
RESOLUCION_M = 20    # metros por pixel


def validar_bbox(bbox):
    """
    Valida y si es necesario recorta el bbox para que quepa en el límite
    de Copernicus (2500×2500 px a 20m/px ≈ 50km × 50km).

    Retorna:
        bbox_valido  : [lon_o, lat_s, lon_e, lat_n] (posiblemente recortado)
        ancho_px     : int
        alto_px      : int
        ancho_km     : float
        alto_km      : float
        recortado    : bool  (True si se tuvo que recortar)
    """
    lon_o, lat_s, lon_e, lat_n = bbox
    lat_c = (lat_s + lat_n) / 2

    m_por_grado_lon = 111_320 * math.cos(math.radians(lat_c))
    m_por_grado_lat = 111_320

    ancho_m = abs(lon_e - lon_o) * m_por_grado_lon
    alto_m  = abs(lat_n - lat_s) * m_por_grado_lat

    ancho_px = int(ancho_m / RESOLUCION_M)
    alto_px  = int(alto_m  / RESOLUCION_M)

    limite_m = MAX_PIXELS * RESOLUCION_M  # 50,000 m = 50 km
    recortado = False

    if ancho_m > limite_m:
        exceso  = (ancho_m - limite_m) / 2
        lon_o   = lon_o + exceso / m_por_grado_lon
        lon_e   = lon_e - exceso / m_por_grado_lon
        ancho_m = limite_m
        ancho_px = MAX_PIXELS
        recortado = True

    if alto_m > limite_m:
        exceso  = (alto_m - limite_m) / 2
        lat_s   = lat_s + exceso / m_por_grado_lat
        lat_n   = lat_n - exceso / m_por_grado_lat
        alto_m  = limite_m
        alto_px = MAX_PIXELS
        recortado = True

    return (
        [round(lon_o, 6), round(lat_s, 6), round(lon_e, 6), round(lat_n, 6)],
        ancho_px,
        alto_px,
        round(ancho_m / 1000, 1),
        round(alto_m  / 1000, 1),
        recortado,
    )


def crear_compuesto(lista_b04, lista_b08, lista_b12=None):
    """
    Apila varias imágenes y calcula el NDVI mediano pixel a pixel.
    La mediana elimina nubes residuales sin configuración extra.
    Requiere al menos 2 imágenes para ser útil.
    """
    # Reemplazar 0 con NaN (píxeles sin dato o con máscara de nubes)
    def limpiar(arr):
        return np.where(arr == 0, np.nan, arr.astype(float))

    stack_b04 = np.stack([limpiar(b) for b in lista_b04], axis=0)
    stack_b08 = np.stack([limpiar(b) for b in lista_b08], axis=0)

    b04_med = np.nanmedian(stack_b04, axis=0)
    b08_med = np.nanmedian(stack_b08, axis=0)

    b12_med = None
    if lista_b12:
        stack_b12 = np.stack([limpiar(b) for b in lista_b12], axis=0)
        b12_med   = np.nanmedian(stack_b12, axis=0)

    return b04_med, b08_med, calcular_ndvi(b04_med, b08_med), b12_med


def _calcular_compacidad(mascara):
    """
    Compacidad = (4π × área) / perímetro²
    Valores: 1.0 = círculo perfecto, <0.3 = forma muy irregular
    Plantaciones: 0.4–0.9 | Incendios: 0.05–0.35
    """
    area = mascara.sum()
    if area == 0:
        return 0.0
    interior = ndimage.binary_erosion(mascara)
    perimetro = max(1, int(area - interior.sum()))
    return float((4 * math.pi * area) / (perimetro ** 2))


def clasificar_tipo(caida_ndvi, mes_inicio, area_ha,
                    ndvi_antes=None, ndvi_despues=None, compacidad=None,
                    nbr_antes=None, nbr_despues=None):
    """
    Clasifica en 6 categorías usando reglas basadas en dominio forestal chileno.
    El modelo ML confirma si hubo cambio real; las reglas determinan el tipo.
    Temporada de incendios Chile: diciembre–marzo.
    """
    temporada_incendio = mes_inicio in [12, 1, 2, 3]
    comp = compacidad if compacidad is not None else 0.5

    # ── Recuperación / Replante ──────────────────────────────────────────────
    # NDVI aumentó significativamente → zona que se está recuperando
    if caida_ndvi <= -0.20:
        return "🌱 Recuperación / Replante", "#27ae60"

    # ── Sin cambio ───────────────────────────────────────────────────────────
    if caida_ndvi < 0.10:
        return "🟢 Sin cambio significativo", "#95a5a6"

    delta_nbr = (nbr_despues - nbr_antes) if (nbr_antes is not None and nbr_despues is not None) else None
    _nbr_a    = nbr_antes   if nbr_antes   is not None else 0.5
    _nbr_d    = nbr_despues if nbr_despues is not None else 0.5
    _d_nbr    = delta_nbr   if delta_nbr   is not None else 0.0

    # ── Modelo ML ────────────────────────────────────────────────────────────
    if _modelo_rf is not None and ndvi_antes is not None and ndvi_despues is not None:
        n_features = len(_modelo_rf.feature_importances_)
        n_clases   = len(_modelo_rf.classes_)

        if n_features == 9:
            features = np.array([[
                ndvi_antes, ndvi_despues, ndvi_despues - ndvi_antes,
                float(mes_inicio), comp, area_ha,
                _nbr_a, _nbr_d, _d_nbr,
            ]])
        else:
            features = np.array([[
                ndvi_antes, ndvi_despues, ndvi_despues - ndvi_antes,
                float(temporada_incendio), comp, area_ha,
            ]])

        pred = int(_modelo_rf.predict(features)[0])
        prob = _modelo_rf.predict_proba(features)[0].max()

        if n_clases == 3:
            # Modelo nuevo — 3 clases directas
            if pred == 0:
                return f"🟢 Sin cambio significativo ({prob:.0%})", "#95a5a6"
            elif pred == 2:
                if _d_nbr < -0.44:
                    return f"🔥 Incendio Forestal — Alta severidad ({prob:.0%})", "#c0392b"
                elif _d_nbr < -0.27:
                    return f"🔥 Incendio Forestal — Severidad moderada ({prob:.0%})", "#e74c3c"
                else:
                    return f"🔥 Incendio Forestal — Baja severidad ({prob:.0%})", "#e67e22"
            else:
                if area_ha >= 10 and comp >= 0.35:
                    return f"🪓 Tala Industrial ({prob:.0%})", "#e67e22"
                return f"✂️ Tala Selectiva ({prob:.0%})", "#f39c12"
        else:
            # Modelo anterior — 2 clases
            if pred == 0:
                return "🟢 Sin cambio significativo", "#95a5a6"
            if temporada_incendio and caida_ndvi >= 0.30 and comp < 0.40:
                return f"🔥 Incendio Forestal ({prob:.0%})", "#e74c3c"
            if area_ha >= 10 and comp >= 0.35:
                return f"🪓 Tala Industrial ({prob:.0%})", "#e67e22"
            return f"✂️ Tala Selectiva ({prob:.0%})", "#f39c12"

    # ── Fallback: reglas heurísticas (sin modelo) ────────────────────────────
    if temporada_incendio and caida_ndvi >= 0.30 and comp < 0.40:
        return "🔥 Incendio Forestal", "#e74c3c"
    if caida_ndvi >= 0.20 and area_ha >= 10 and comp >= 0.35:
        return "🪓 Tala Industrial", "#e67e22"
    if caida_ndvi >= 0.15 and area_ha < 10:
        return "✂️ Tala Selectiva", "#f39c12"
    if caida_ndvi >= 0.20 and area_ha >= 10:
        return "🪓 Tala Industrial", "#e67e22"
    return "📉 Degradación Gradual", "#8e44ad"


def detectar_zonas(cambio, transform, bounds, umbral=0.15, min_ha=0.5,
                   ndvi1=None, ndvi2=None, nbr1=None, nbr2=None):
    """
    Detecta zonas de pérdida Y de recuperación de vegetación.
    Retorna lista de dicts con compacidad, área, severidad y tipo de evento.
    """
    lat_centro    = (bounds.top + bounds.bottom) / 2
    lon_step_m    = abs(transform.a) * 111320 * math.cos(math.radians(lat_centro))
    lat_step_m    = abs(transform.e) * 111320
    ha_por_pixel  = (lon_step_m * lat_step_m) / 10000
    min_pixels    = max(1, int(min_ha / ha_por_pixel))

    zonas  = []
    alerta = np.zeros_like(cambio, dtype=bool)

    # ── Zonas de pérdida ─────────────────────────────────────────────────────
    mascara_perdida = (cambio < -umbral) & ~np.isnan(cambio)
    alerta |= mascara_perdida

    etiq_p, n_p = ndimage.label(mascara_perdida)
    for i in range(1, n_p + 1):
        m = etiq_p == i
        if m.sum() < min_pixels:
            continue

        filas, cols  = np.where(m)
        lon, lat     = xy(transform, int(filas.mean()), int(cols.mean()))
        caida        = float(-cambio[m].mean())
        area_ha      = round(m.sum() * ha_por_pixel, 2)
        compacidad   = _calcular_compacidad(m)

        if caida >= 0.35:
            severidad, color = "Grave",    "red"
        elif caida >= 0.22:
            severidad, color = "Moderada", "orange"
        else:
            severidad, color = "Leve",     "beige"

        # Extraer polígono geográfico real de la zona
        poligonos = list(rasterio_shapes(m.astype(np.uint8), mask=m.astype(np.uint8), transform=transform))
        geojson_geom = poligonos[0][0] if poligonos else None

        zonas.append({
            "latitud":       round(lat, 6),
            "longitud":      round(lon, 6),
            "area_ha":       area_ha,
            "caida_ndvi":    round(caida, 3),
            "severidad":     severidad,
            "compacidad":    round(compacidad, 3),
            "tipo_evento":   "perdida",
            "_color":        color,
            "_geojson":      geojson_geom,
            "_ndvi_antes":   float(np.nanmean(ndvi1[m])) if ndvi1 is not None else None,
            "_ndvi_despues": float(np.nanmean(ndvi2[m])) if ndvi2 is not None else None,
            "_nbr_antes":    float(np.nanmean(nbr1[m]))  if nbr1  is not None else None,
            "_nbr_despues":  float(np.nanmean(nbr2[m]))  if nbr2  is not None else None,
        })

    # ── Zonas de recuperación ────────────────────────────────────────────────
    UMBRAL_RECUPERACION = 0.20
    mascara_rec = (cambio > UMBRAL_RECUPERACION) & ~np.isnan(cambio)
    etiq_r, n_r = ndimage.label(mascara_rec)

    for i in range(1, n_r + 1):
        m = etiq_r == i
        if m.sum() < min_pixels:
            continue

        filas, cols  = np.where(m)
        lon, lat     = xy(transform, int(filas.mean()), int(cols.mean()))
        ganancia     = float(cambio[m].mean())
        area_ha      = round(m.sum() * ha_por_pixel, 2)
        compacidad   = _calcular_compacidad(m)

        poligonos_r = list(rasterio_shapes(m.astype(np.uint8), mask=m.astype(np.uint8), transform=transform))
        geojson_rec = poligonos_r[0][0] if poligonos_r else None

        zonas.append({
            "latitud":       round(lat, 6),
            "longitud":      round(lon, 6),
            "area_ha":       area_ha,
            "caida_ndvi":    round(-ganancia, 3),
            "severidad":     "Recuperación",
            "compacidad":    round(compacidad, 3),
            "tipo_evento":   "recuperacion",
            "_color":        "green",
            "_geojson":      geojson_rec,
            "_ndvi_antes":   float(np.nanmean(ndvi1[m])) if ndvi1 is not None else None,
            "_ndvi_despues": float(np.nanmean(ndvi2[m])) if ndvi2 is not None else None,
            "_nbr_antes":    float(np.nanmean(nbr1[m]))  if nbr1  is not None else None,
            "_nbr_despues":  float(np.nanmean(nbr2[m]))  if nbr2  is not None else None,
        })

    zonas.sort(key=lambda z: z["area_ha"], reverse=True)
    return zonas, alerta


def crear_mapa(zonas, bounds, mes_inicio):
    lat_c = (bounds.top + bounds.bottom) / 2
    lon_c = (bounds.left + bounds.right) / 2

    mapa = folium.Map(location=[lat_c, lon_c], zoom_start=12)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satélite", overlay=False
    ).add_to(mapa)
    folium.TileLayer("OpenStreetMap", name="Mapa").add_to(mapa)

    # ── Capas de sombreado por área ──────────────────────────────────────────
    COLORES_FILL = {
        "red":   ("#e74c3c", "#e74c3c"),
        "orange":("#e67e22", "#f39c12"),
        "beige": ("#f5cba7", "#e59866"),
        "green": ("#27ae60", "#2ecc71"),
    }

    grupo_perdida   = folium.FeatureGroup(name="🟥 Áreas afectadas (sombreado)", show=True)
    grupo_recuper   = folium.FeatureGroup(name="🟩 Áreas en recuperación (sombreado)", show=True)

    for z in zonas:
        geom = z.get("_geojson")
        if not geom or z["area_ha"] < 0.3:
            continue
        fill, stroke = COLORES_FILL.get(z["_color"], ("#888", "#888"))
        tipo_str = "perdida" if z["tipo_evento"] == "perdida" else "recuperacion"
        grupo = grupo_perdida if tipo_str == "perdida" else grupo_recuper

        folium.GeoJson(
            geom,
            style_function=lambda x, f=fill, s=stroke: {
                "fillColor":   f,
                "color":       s,
                "weight":      1.5,
                "fillOpacity": 0.35,
                "opacity":     0.8,
            },
            tooltip=f"{z['area_ha']} ha — Δ NDVI {z['caida_ndvi']:+.3f}",
        ).add_to(grupo)

    grupo_perdida.add_to(mapa)
    grupo_recuper.add_to(mapa)

    # ── Marcadores de punto ──────────────────────────────────────────────────
    for z in zonas:
        tipo, _ = clasificar_tipo(
            z["caida_ndvi"], mes_inicio, z["area_ha"],
            ndvi_antes=z.get("_ndvi_antes"),
            ndvi_despues=z.get("_ndvi_despues"),
            compacidad=z.get("compacidad"),
            nbr_antes=z.get("_nbr_antes"),
            nbr_despues=z.get("_nbr_despues"),
        )
        folium.CircleMarker(
            location=[z["latitud"], z["longitud"]],
            radius=8,
            color=z["_color"],
            fill=True,
            fill_opacity=0.85,
            popup=folium.Popup(
                f"""
                <div style="font-family:'Outfit', -apple-system, sans-serif; font-size:13px; color:#333; line-height:1.4; min-width:180px;">
                    <h4 style="margin:0 0 8px 0; color:#1e3f20; border-bottom:2px solid #2ecc71; padding-bottom:4px; font-weight:600;">Alerta de Cambio</h4>
                    <b>Clasificación:</b> {tipo}<br>
                    <b>Severidad:</b> <span style="color:{'red' if z['severidad']=='Grave' else 'orange' if z['severidad']=='Moderada' else '#d4ac0d'}; font-weight:bold;">{z['severidad']}</span><br>
                    <b>Superficie:</b> {z['area_ha']} ha<br>
                    <b>Caída NDVI:</b> -{z['caida_ndvi']}<br>
                    <div style="margin-top:8px; font-size:11px; color:#666; border-top:1px solid #eee; padding-top:4px;">
                        <b>Coordenadas:</b><br>{z['latitud']}, {z['longitud']}
                    </div>
                </div>
                """,
                max_width=250,
            ),
            tooltip=f"{tipo} — {z['area_ha']} ha",
        ).add_to(mapa)

    leyenda_html = """
    <div style="position:fixed; bottom:30px; left:30px; background:rgba(255,255,255,0.92);
                backdrop-filter:blur(5px); -webkit-backdrop-filter:blur(5px);
                padding:15px; border-radius:12px; box-shadow:0 6px 20px rgba(0,0,0,0.15);
                border:1px solid rgba(255,255,255,0.6); font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size:13px; z-index:1000; color:#2c3e50; line-height:1.5; min-width:170px;">
      <b style="font-size:14px; display:block; margin-bottom:8px; color:#1e3f20; font-weight:bold;">Clasificación de Alertas</b>
      <div style="display:flex; align-items:center; margin-bottom:6px;">
        <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:red; margin-right:8px; box-shadow:0 0 4px rgba(255,0,0,0.5);"></span>
        <span>Pérdida Grave / Incendio</span>
      </div>
      <div style="display:flex; align-items:center; margin-bottom:6px;">
        <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:orange; margin-right:8px; box-shadow:0 0 4px rgba(255,165,0,0.5);"></span>
        <span>Tala / Cosecha Forestal</span>
      </div>
      <div style="display:flex; align-items:center;">
        <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:beige; border:1px solid #ccc; margin-right:8px;"></span>
        <span>Cambio Estacional / Leve</span>
      </div>
    </div>
    """
    mapa.get_root().html.add_child(folium.Element(leyenda_html))
    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa
