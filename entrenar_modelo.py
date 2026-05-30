"""
Entrenamiento multi-zona, multi-año, multi-estación — 3 clases.

Zonas:
  1. Constitución / Maule         → tala de plantaciones
  2. Nacimiento / Biobío          → tala industrial y selectiva (Arauco)
  3. Penco / Tomé / Lirquén 2026  → incendio enero 2026

Clases:
  0 = Sin cambio
  1 = Tala / Cosecha forestal
  2 = Incendio forestal

Uso:
    python3 entrenar_modelo.py
"""
import numpy as np
import math, os, getpass, tempfile, time, json
import rasterio
import rasterio.warp
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from rasterio.env import Env
from rasterio.transform import from_bounds as tfb
from scipy import ndimage
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.utils.class_weight import compute_sample_weight
import joblib

from tqdm import tqdm
from copernicus_api import obtener_token, descargar_compuesto

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

ZONAS_TALA = [
    {"nombre": "Constitución / Maule",
     "bbox":   [-72.34, -35.38, -72.17, -35.27]},
    {"nombre": "Nacimiento / Biobío",
     "bbox":   [-72.60, -37.40, -72.20, -37.10]},
]

ZONA_INCENDIO = {
    "nombre":   "Incendio Penco-Tomé enero 2026",
    "bbox":     [-73.20, -36.99, -72.80, -36.55],
    "base":     ("2025-10-01", "2025-12-31"),
    "reciente": ("2026-02-01", "2026-03-31"),
}

# Cada par: (año_base, año_reciente, hansen_lossyear_que_captura)
PARES_ANOS = [
    (2020, 2022, 21),   # pérdidas 2021
    (2021, 2023, 22),   # pérdidas 2022
    (2022, 2024, 23),   # pérdidas 2023
]

def periodo(estacion, ano):
    """Retorna (desde, hasta) para una estación y año."""
    if estacion == "invierno":
        return f"{ano}-06-01", f"{ano}-08-31"
    elif estacion == "primavera":
        return f"{ano}-09-01", f"{ano}-11-30"
    elif estacion == "verano":
        return f"{ano}-12-01", f"{ano+1}-02-28"
    elif estacion == "otono":
        return f"{ano}-03-01", f"{ano}-05-31"

ESTACIONES = ["invierno", "primavera", "verano", "otono"]
MES_ESTACION = {"invierno": 7, "primavera": 10, "verano": 1, "otono": 4}

MAX_NUBES    = 10
MODELO_SALIDA = "modelo_clasificador.pkl"
HANSEN_URL   = (
    "https://storage.googleapis.com/earthenginepartners-hansen/"
    "GFC-2023-v1.11/Hansen_GFC-2023-v1.11_lossyear_30S_080W.tif"
)

ETIQUETA_SIN_CAMBIO = 0
ETIQUETA_TALA       = 1
ETIQUETA_INCENDIO   = 2

# ══════════════════════════════════════════════════════════════════════════════
# CREDENCIALES
# ══════════════════════════════════════════════════════════════════════════════
CREDENCIALES_FILE = os.path.join(os.path.dirname(__file__), ".copernicus_creds.json")

print("=== Entrenamiento multi-zona — Monitor IA ===\n")

creds_guardadas = None
if os.path.exists(CREDENCIALES_FILE):
    with open(CREDENCIALES_FILE) as f:
        creds_guardadas = json.load(f)
    print(f"Sesión guardada: {creds_guardadas['usuario']}")
    print("  1) Usar sesión guardada")
    print("  2) Iniciar sesión con otra cuenta")
    opcion = input("Opción [1/2]: ").strip()
    if opcion == "2":
        creds_guardadas = None

if creds_guardadas:
    usuario    = creds_guardadas["usuario"]
    contrasena = creds_guardadas["contrasena"]
else:
    usuario    = input("Usuario Copernicus: ").strip()
    contrasena = input("Contraseña: ").strip()

print("\nConectando...")
token = obtener_token(usuario, contrasena)
print("Token OK.\n")

if not creds_guardadas or opcion == "2":
    guardar = input("¿Guardar credenciales para próximas ejecuciones? [s/n]: ").strip().lower()
    if guardar == "s":
        with open(CREDENCIALES_FILE, "w") as f:
            json.dump({"usuario": usuario, "contrasena": contrasena}, f)
        print(f"  Credenciales guardadas en {CREDENCIALES_FILE}\n")

_token_ts = time.time()

def token_fresco():
    """Renueva el token solo si lleva más de 9 minutos (expira en 10)."""
    global token, _token_ts
    if time.time() - _token_ts > 540:
        token = obtener_token(usuario, contrasena)
        _token_ts = time.time()
    return token

# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ══════════════════════════════════════════════════════════════════════════════
np.seterr(divide="ignore", invalid="ignore")

def calc_ndvi(b04, b08):
    return np.where((b08+b04)==0, np.nan, (b08-b04)/(b08+b04))

def calc_nbr(b08, b12):
    return np.where((b08+b12)==0, np.nan, (b08-b12)/(b08+b12))

def leer_composite(ruta):
    with rasterio.open(ruta) as src:
        b04 = src.read(1).astype(float)
        b08 = src.read(2).astype(float)
        b12 = src.read(3).astype(float) if src.count >= 3 else None
        return b04, b08, b12, src.transform, src.bounds, src.width, src.height

def calcular_zona_features(delta_ndvi, transform, bounds, ancho, alto):
    """Calcula compacidad y área por pixel según zonas de cambio."""
    lat_c        = (bounds.bottom + bounds.top) / 2
    ha_por_pixel = (abs(transform.a)*111320*math.cos(math.radians(lat_c)) *
                    abs(transform.e)*111320) / 10000

    alerta = (delta_ndvi < -0.10) & ~np.isnan(delta_ndvi)
    etiq, n = ndimage.label(alerta)

    comp_arr = np.full((alto, ancho), 0.5)
    area_arr = np.zeros((alto, ancho))

    for i in range(1, n + 1):
        m = etiq == i
        if m.sum() < 5:
            continue
        interior  = ndimage.binary_erosion(m)
        perimetro = max(1, int(m.sum() - interior.sum()))
        comp      = float((4 * math.pi * m.sum()) / (perimetro ** 2))
        comp_arr[m] = comp
        area_arr[m] = m.sum() * ha_por_pixel

    return comp_arr, area_arr

def remuestrear_hansen(bbox, ancho, alto, bounds):
    """Descarga y remuestrea Hansen GFC al grid de la zona."""
    sentinel_transform = tfb(bounds.left, bounds.bottom, bounds.right, bounds.top, ancho, alto)
    hansen_raster = np.zeros((alto, ancho), dtype=np.uint8)

    with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(HANSEN_URL) as src:
            bbox_t = (bbox[0], bbox[1], bbox[2], bbox[3])
            window     = from_bounds(*bbox_t, src.transform)
            hansen_raw = src.read(1, window=window)
            h_tr       = src.window_transform(window)
            h_crs      = src.crs

    with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(HANSEN_URL) as src:
            rasterio.warp.reproject(
                source=hansen_raw, destination=hansen_raster,
                src_transform=h_tr, src_crs=h_crs,
                dst_transform=sentinel_transform, dst_crs=h_crs,
                resampling=Resampling.nearest,
            )
    return hansen_raster

# ══════════════════════════════════════════════════════════════════════════════
# RECOLECCIÓN DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
todas_X, todas_y = [], []

# Generar todas las combinaciones para mostrar progreso total
combinaciones = [
    (zona, estacion, ano_base, ano_rec, lossyear)
    for zona in ZONAS_TALA
    for estacion in ESTACIONES
    for ano_base, ano_rec, lossyear in PARES_ANOS
]
total = len(combinaciones) + 1  # +1 por la zona de incendio

print(f"Total de descargas a procesar: {total * 2} composites")
print(f"(Los archivos en caché no se vuelven a descargar)\n")

# ── Zonas de TALA ─────────────────────────────────────────────────────────────
hansen_cache = {}
barra = tqdm(combinaciones, desc="Descargando y procesando", unit="combinación",
             bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")

for zona, estacion, ano_base, ano_rec, lossyear in barra:
    bbox = zona["bbox"]
    desde_b, hasta_b = periodo(estacion, ano_base)
    desde_r, hasta_r = periodo(estacion, ano_rec)
    mes = MES_ESTACION[estacion]

    barra.set_postfix_str(f"{zona['nombre'][:15]} | {estacion} {ano_base}→{ano_rec}")

    try:
        ruta_b = descargar_compuesto(token_fresco(), bbox, desde_b, hasta_b, max_nubes=MAX_NUBES)
        ruta_r = descargar_compuesto(token_fresco(), bbox, desde_r, hasta_r, max_nubes=MAX_NUBES)
    except Exception as e:
        tqdm.write(f"  ⚠ Error: {e} — omitiendo")
        continue

    b04_b, b08_b, b12_b, transform, bounds, ancho, alto = leer_composite(ruta_b)
    b04_r, b08_r, b12_r, *_                              = leer_composite(ruta_r)

    ndvi_b     = calc_ndvi(b04_b, b08_b)
    ndvi_r     = calc_ndvi(b04_r, b08_r)
    delta_ndvi = ndvi_r - ndvi_b

    tiene_nbr = b12_b is not None and b12_r is not None
    nbr_b  = calc_nbr(b08_b, b12_b) if tiene_nbr else None
    nbr_r  = calc_nbr(b08_r, b12_r) if tiene_nbr else None
    d_nbr  = (nbr_r - nbr_b)        if tiene_nbr else None

    # Downsamplear zonas grandes para acelerar ndimage.label (~9x más rápido)
    if ancho * alto > 400_000:
        N = 3
        ndvi_b     = ndvi_b[::N, ::N]
        ndvi_r     = ndvi_r[::N, ::N]
        delta_ndvi = delta_ndvi[::N, ::N]
        if tiene_nbr:
            nbr_b = nbr_b[::N, ::N]
            nbr_r = nbr_r[::N, ::N]
            d_nbr = d_nbr[::N, ::N]
        alto, ancho = ndvi_b.shape
        from rasterio.transform import Affine as _Aff
        transform = _Aff(transform.a*N, 0, transform.c, 0, transform.e*N, transform.f)

    comp_arr, area_arr = calcular_zona_features(delta_ndvi, transform, bounds, ancho, alto)

    key = (zona["nombre"], ancho, alto)
    if key not in hansen_cache:
        tqdm.write(f"  Descargando Hansen para {zona['nombre']}...")
        hansen_cache[key] = remuestrear_hansen(bbox, ancho, alto, bounds)
    hansen = hansen_cache[key]

    mascara_tala = (hansen == lossyear)
    mascara_nc   = (hansen == 0)
    valido = ~np.isnan(ndvi_b) & ~np.isnan(ndvi_r)
    if tiene_nbr:
        valido &= ~np.isnan(nbr_b) & ~np.isnan(nbr_r)

    idx_t  = np.where(mascara_tala & valido)
    idx_nc = np.where(mascara_nc   & valido)
    n_tala = len(idx_t[0])
    n_nc   = min(len(idx_nc[0]), n_tala * 4)

    if n_tala < 10:
        tqdm.write(f"  ⚠ Muy pocos ejemplos de tala ({n_tala}) — omitiendo")
        continue

    rng    = np.random.default_rng(42)
    sel_t  = rng.choice(len(idx_t[0]),  size=n_tala, replace=False)
    sel_nc = rng.choice(len(idx_nc[0]), size=n_nc,   replace=False)

    def extraer(idx, sel):
        r, c = idx[0][sel], idx[1][sel]
        base = [
            ndvi_b[r,c], ndvi_r[r,c], delta_ndvi[r,c],
            np.full(len(r), float(mes)),
            comp_arr[r,c], area_arr[r,c],
        ]
        if tiene_nbr:
            base += [nbr_b[r,c], nbr_r[r,c], d_nbr[r,c]]
        else:
            base += [np.full(len(r), 0.5), np.full(len(r), 0.5), np.zeros(len(r))]
        return np.column_stack(base)

    todas_X.append(extraer(idx_t,  sel_t))
    todas_y.append(np.full(n_tala, ETIQUETA_TALA))
    todas_X.append(extraer(idx_nc, sel_nc))
    todas_y.append(np.full(n_nc,   ETIQUETA_SIN_CAMBIO))

    tqdm.write(f"  ✓ {zona['nombre'][:20]} | {estacion} {ano_base}→{ano_rec} | tala:{n_tala} nc:{n_nc}")

# ── Zona INCENDIO ─────────────────────────────────────────────────────────────
print(f"\n{'═'*60}")
print(f"Zona: {ZONA_INCENDIO['nombre']}")
print(f"{'═'*60}")

try:
    bbox = ZONA_INCENDIO["bbox"]
    desde_b, hasta_b = ZONA_INCENDIO["base"]
    desde_r, hasta_r = ZONA_INCENDIO["reciente"]

    print(f"\n  Pre-fuego ({desde_b} → {hasta_b}) → Post-fuego ({desde_r} → {hasta_r})")
    for intento in range(3):
        try:
            ruta_b = descargar_compuesto(token_fresco(), bbox, desde_b, hasta_b, max_nubes=MAX_NUBES)
            ruta_r = descargar_compuesto(token_fresco(), bbox, desde_r, hasta_r, max_nubes=MAX_NUBES)
            break
        except Exception as e:
            if "429" in str(e) and intento < 2:
                print(f"  ⏳ Rate limit (429) — esperando 60 seg... (intento {intento+1}/3)")
                time.sleep(60)
            else:
                raise

    b04_b, b08_b, b12_b, transform, bounds, ancho, alto = leer_composite(ruta_b)
    b04_r, b08_r, b12_r, *_ = leer_composite(ruta_r)

    ndvi_b     = calc_ndvi(b04_b, b08_b)
    ndvi_r     = calc_ndvi(b04_r, b08_r)
    delta_ndvi = ndvi_r - ndvi_b

    tiene_nbr  = b12_b is not None and b12_r is not None
    nbr_b  = calc_nbr(b08_b, b12_b) if tiene_nbr else None
    nbr_r  = calc_nbr(b08_r, b12_r) if tiene_nbr else None
    d_nbr  = (nbr_r - nbr_b) if tiene_nbr else None

    # Downsamplear si la zona es grande (misma lógica que zonas de tala)
    if ancho * alto > 400_000:
        N = 3
        ndvi_b     = ndvi_b[::N, ::N]
        ndvi_r     = ndvi_r[::N, ::N]
        delta_ndvi = delta_ndvi[::N, ::N]
        if tiene_nbr:
            nbr_b = nbr_b[::N, ::N]
            nbr_r = nbr_r[::N, ::N]
            d_nbr = d_nbr[::N, ::N]
        alto, ancho = ndvi_b.shape
        from rasterio.transform import Affine as _Aff
        transform = _Aff(transform.a*N, 0, transform.c, 0, transform.e*N, transform.f)

    comp_arr, area_arr = calcular_zona_features(delta_ndvi, transform, bounds, ancho, alto)

    # Etiquetas por NBR: quemado si delta_nbr < -0.27 (moderado-alto)
    valido = ~np.isnan(ndvi_b) & ~np.isnan(ndvi_r)
    if tiene_nbr:
        valido &= ~np.isnan(nbr_b) & ~np.isnan(nbr_r)
        mascara_inc = (d_nbr < -0.27) & valido
        mascara_nc  = (np.abs(d_nbr) < 0.05) & (np.abs(delta_ndvi) < 0.05) & valido
    else:
        mascara_inc = (delta_ndvi < -0.30) & valido
        mascara_nc  = (np.abs(delta_ndvi) < 0.05) & valido

    idx_inc = np.where(mascara_inc)
    idx_nc  = np.where(mascara_nc)
    n_inc   = len(idx_inc[0])
    n_nc    = min(len(idx_nc[0]), n_inc * 4)

    mes_inc = 1  # enero (temporada incendios)

    rng    = np.random.default_rng(42)
    sel_i  = rng.choice(n_inc,           size=n_inc, replace=False)
    sel_nc = rng.choice(len(idx_nc[0]),  size=n_nc,  replace=False)

    def extraer_inc(idx, sel):
        r, c = idx[0][sel], idx[1][sel]
        base = [
            ndvi_b[r,c], ndvi_r[r,c], delta_ndvi[r,c],
            np.full(len(r), float(mes_inc)),
            comp_arr[r,c], area_arr[r,c],
        ]
        if tiene_nbr:
            base += [nbr_b[r,c], nbr_r[r,c], d_nbr[r,c]]
        else:
            base += [np.full(len(r), 0.5), np.full(len(r), 0.5), np.zeros(len(r))]
        return np.column_stack(base)

    X_inc = extraer_inc(idx_inc, sel_i)
    X_nc  = extraer_inc(idx_nc,  sel_nc)

    todas_X.append(X_inc)
    todas_y.append(np.full(len(X_inc), ETIQUETA_INCENDIO))
    todas_X.append(X_nc)
    todas_y.append(np.full(len(X_nc), ETIQUETA_SIN_CAMBIO))

    print(f"  ✓ Incendio: {n_inc} | Sin cambio: {n_nc}")

except Exception as e:
    print(f"  ⚠ Error zona incendio: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# ENTRENAMIENTO
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*60)
print("ENTRENANDO MODELO")
print("═"*60)

X_full = np.vstack(todas_X)
y_full = np.concatenate(todas_y)

dist = {0: int((y_full==0).sum()), 1: int((y_full==1).sum()), 2: int((y_full==2).sum())}
print(f"\nDataset completo:")
print(f"  Sin cambio (0): {dist[0]:>7,}")
print(f"  Tala       (1): {dist[1]:>7,}")
print(f"  Incendio   (2): {dist[2]:>7,}")
print(f"  Total:          {len(X_full):>7,}")

# Submuestreo: máx 50,000 por clase para evitar entrenamiento de horas
MAX_POR_CLASE = 50_000
rng = np.random.default_rng(42)
indices = []
for clase in [0, 1, 2]:
    idx_clase = np.where(y_full == clase)[0]
    n = min(len(idx_clase), MAX_POR_CLASE)
    if n > 0:
        indices.append(rng.choice(idx_clase, size=n, replace=False))

indices = np.concatenate(indices)
rng.shuffle(indices)
X = X_full[indices]
y = y_full[indices]

dist2 = {0: int((y==0).sum()), 1: int((y==1).sum()), 2: int((y==2).sum())}
print(f"\nDataset submuestreado (máx {MAX_POR_CLASE:,}/clase):")
print(f"  Sin cambio (0): {dist2[0]:>7,}")
print(f"  Tala       (1): {dist2[1]:>7,}")
print(f"  Incendio   (2): {dist2[2]:>7,}")
print(f"  Total:          {len(X):>7,}")
print(f"  Features:       {X.shape[1]}")

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2,
                                                     random_state=42, stratify=y)

print(f"\nEntrenando XGBoost (GPU CUDA, 500 árboles)...")
t0 = time.time()
modelo = XGBClassifier(
    n_estimators=500,
    max_depth=8,
    learning_rate=0.1,
    device="cuda",
    tree_method="hist",
    num_class=3,
    objective="multi:softprob",
    eval_metric="mlogloss",
    early_stopping_rounds=50,
    random_state=42,
    verbosity=1,
)

sample_weight = compute_sample_weight("balanced", y_train)
modelo.fit(
    X_train, y_train,
    sample_weight=sample_weight,
    eval_set=[(X_test, y_test)],
    verbose=50,
)

print(f"Entrenamiento completado en {time.time()-t0:.0f} segundos.")

# Guardar antes del reporte para no perder el modelo si algo falla
joblib.dump(modelo, MODELO_SALIDA)
print(f"\n✓ Modelo guardado en {MODELO_SALIDA}")

y_pred_raw = modelo.predict(X_test)
y_pred = y_pred_raw if y_pred_raw.ndim == 1 else np.argmax(y_pred_raw, axis=1)
clases_presentes = sorted(np.unique(y_test).astype(int))
nombres_clases = ["Sin cambio", "Tala/Cosecha", "Incendio"]

print("\n--- Resultados en datos de prueba ---")
print(classification_report(
    y_test, y_pred,
    labels=clases_presentes,
    target_names=[nombres_clases[i] for i in clases_presentes],
    zero_division=0,
))

nombres = ["ndvi_antes","ndvi_despues","delta_ndvi","mes",
           "compacidad","area_ha","nbr_antes","nbr_despues","delta_nbr"]
print("Importancia de features:")
for n, imp in sorted(zip(nombres, modelo.feature_importances_), key=lambda x: -x[1]):
    print(f"  {n:<15} {imp:.3f}  {'█' * int(imp*40)}")

print(f"\n  Clases activas: {[nombres_clases[i] for i in clases_presentes]}")
print(f"  Zonas:  Constitución + Nacimiento + Penco-Tomé")
print(f"  Años:   2020-2024 (tala) + 2025-2026 (incendio)")
