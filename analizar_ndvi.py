import rasterio
from rasterio.transform import xy
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import ndimage
import folium
import csv
import math

# --- Archivos ---
B04_2022 = '2022-06-07-00_00_2022-06-07-23_59_Sentinel-2_L2A_B04_(Raw).tiff'
B08_2022 = '2022-06-07-00_00_2022-06-07-23_59_Sentinel-2_L2A_B08_(Raw).tiff'
B04_2024 = '2024-07-06-00_00_2024-07-06-23_59_Sentinel-2_L2A_B04_(Raw).tiff'
B08_2024 = '2024-07-06-00_00_2024-07-06-23_59_Sentinel-2_L2A_B08_(Raw).tiff'

# --- Calcular NDVI ---
def calcular_ndvi(ruta_b04, ruta_b08):
    with rasterio.open(ruta_b04) as f:
        b04 = f.read(1).astype(float)
    with rasterio.open(ruta_b08) as f:
        b08 = f.read(1).astype(float)
    np.seterr(divide='ignore', invalid='ignore')
    return np.where((b08 + b04) == 0, np.nan, (b08 - b04) / (b08 + b04))

ndvi_2022 = calcular_ndvi(B04_2022, B08_2022)
ndvi_2024 = calcular_ndvi(B04_2024, B08_2024)
cambio = ndvi_2024 - ndvi_2022

# --- Detectar zonas de alerta ---
UMBRAL = 0.15
alerta = (cambio < -UMBRAL) & ~np.isnan(cambio)

# Agrupar pixels conectados en zonas individuales
zonas_etiquetadas, num_zonas = ndimage.label(alerta)
print(f'Zonas de alerta detectadas: {num_zonas}')

# --- Calcular tamaño de pixel en hectáreas ---
with rasterio.open(B04_2022) as src:
    transform = src.transform
    lat_centro = (src.bounds.top + src.bounds.bottom) / 2
    lon_step_m = abs(transform.a) * 111320 * math.cos(math.radians(lat_centro))
    lat_step_m = abs(transform.e) * 111320
    ha_por_pixel = (lon_step_m * lat_step_m) / 10000

print(f'Resolución aproximada: {lon_step_m:.1f}m x {lat_step_m:.1f}m por pixel')
print(f'Área por pixel: {ha_por_pixel:.4f} ha')

# --- Extraer info de cada zona ---
def clasificar_severidad(caida_ndvi):
    if caida_ndvi > 0.35:
        return 'Grave'
    elif caida_ndvi > 0.22:
        return 'Moderada'
    else:
        return 'Leve'

COLOR_SEVERIDAD = {'Grave': 'red', 'Moderada': 'orange', 'Leve': 'yellow'}

zonas = []
MIN_PIXELS = 10  # ignorar zonas menores a 10 pixels (ruido)

with rasterio.open(B04_2022) as src:
    for i in range(1, num_zonas + 1):
        mascara = zonas_etiquetadas == i
        n_pixels = mascara.sum()
        if n_pixels < MIN_PIXELS:
            continue

        # Centro de la zona en coordenadas geográficas
        filas, cols = np.where(mascara)
        fila_centro = int(filas.mean())
        col_centro  = int(cols.mean())
        lon, lat = xy(src.transform, fila_centro, col_centro)

        caida = float(-cambio[mascara].mean())
        area_ha = n_pixels * ha_por_pixel
        severidad = clasificar_severidad(caida)

        zonas.append({
            'zona_id':    i,
            'latitud':    round(lat, 6),
            'longitud':   round(lon, 6),
            'area_ha':    round(area_ha, 2),
            'caida_ndvi': round(caida, 3),
            'severidad':  severidad,
        })

zonas.sort(key=lambda z: z['area_ha'], reverse=True)
print(f'\nZonas válidas (>= {MIN_PIXELS} pixels): {len(zonas)}')
print(f'Área total afectada: {sum(z["area_ha"] for z in zonas):.1f} ha')

# --- Exportar CSV ---
with open('alertas_zonas.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['zona_id','latitud','longitud','area_ha','caida_ndvi','severidad'])
    writer.writeheader()
    writer.writerows(zonas)
print('Coordenadas guardadas en alertas_zonas.csv')

# --- Mapa interactivo con Folium ---
lat_centro = sum(z['latitud'] for z in zonas) / len(zonas)
lon_centro = sum(z['longitud'] for z in zonas) / len(zonas)

mapa = folium.Map(location=[lat_centro, lon_centro], zoom_start=12,
                  tiles='OpenStreetMap')

# Capa de satélite
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri', name='Satélite', overlay=False
).add_to(mapa)

# Marcadores por zona
for z in zonas:
    radio = max(50, min(300, z['area_ha'] * 80))
    folium.CircleMarker(
        location=[z['latitud'], z['longitud']],
        radius=8,
        color=COLOR_SEVERIDAD[z['severidad']],
        fill=True,
        fill_opacity=0.8,
        popup=folium.Popup(
            f"<b>Zona {z['zona_id']}</b><br>"
            f"Severidad: <b>{z['severidad']}</b><br>"
            f"Área: {z['area_ha']} ha<br>"
            f"Caída NDVI: -{z['caida_ndvi']}<br>"
            f"Lat: {z['latitud']}<br>"
            f"Lon: {z['longitud']}",
            max_width=200
        ),
        tooltip=f"{z['severidad']} — {z['area_ha']} ha"
    ).add_to(mapa)

# Leyenda
leyenda = """
<div style="position:fixed; bottom:30px; left:30px; background:white;
            padding:12px; border-radius:8px; border:1px solid grey; font-size:13px;">
  <b>Pérdida de vegetación</b><br>
  <span style="color:red">&#9679;</span> Grave (NDVI &gt; -0.35)<br>
  <span style="color:orange">&#9679;</span> Moderada (NDVI -0.22 a -0.35)<br>
  <span style="color:#cccc00">&#9679;</span> Leve (NDVI -0.15 a -0.22)<br>
  <small>Comparación Jun 2022 – Jul 2024</small>
</div>
"""
mapa.get_root().html.add_child(folium.Element(leyenda))
folium.LayerControl().add_to(mapa)

mapa.save('mapa_alertas.html')
print('Mapa interactivo guardado en mapa_alertas.html')

# --- Imagen comparativa ---
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

im0 = axes[0].imshow(ndvi_2022, cmap='RdYlGn', vmin=0, vmax=1)
axes[0].set_title('NDVI — Junio 2022')
plt.colorbar(im0, ax=axes[0], fraction=0.046)

im1 = axes[1].imshow(ndvi_2024, cmap='RdYlGn', vmin=0, vmax=1)
axes[1].set_title('NDVI — Julio 2024')
plt.colorbar(im1, ax=axes[1], fraction=0.046)

im2 = axes[2].imshow(cambio, cmap='RdYlGn', vmin=-0.4, vmax=0.4)
axes[2].set_title('Cambio NDVI (2024 - 2022)\nRojo = pérdida de vegetación')
plt.colorbar(im2, ax=axes[2], fraction=0.046)
axes[2].contour(alerta, levels=[0.5], colors='red', linewidths=0.8)

plt.suptitle('Análisis de vegetación — Constitución/Putú/Carrizal', fontsize=13, y=1.01)
plt.tight_layout()
plt.savefig('resultado_cambio_ndvi.png', dpi=150, bbox_inches='tight')
print('Imagen guardada en resultado_cambio_ndvi.png')
