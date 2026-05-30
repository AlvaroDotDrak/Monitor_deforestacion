"""
Módulo para buscar y descargar imágenes Sentinel-2 desde Copernicus Data Space.
Cuenta gratuita en: https://dataspace.copernicus.eu

Descarga usando Sentinel Hub Process API — descarga solo el área y bandas
necesarias sin bajar el producto completo (600MB+).

Los composites se guardan en cache/ para no volver a descargarlos.
"""
import requests
import os

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)


def _nombre_cache(bbox, fecha_inicio, fecha_fin, max_nubes, sufijo='ndvi'):
    """Genera un nombre de archivo único para el composite."""
    w, s, e, n = bbox
    return os.path.join(
        CACHE_DIR,
        f"comp_{w}_{s}_{e}_{n}_{fecha_inicio}_{fecha_fin}_{max_nubes}nc_{sufijo}.tiff"
        .replace(' ', '').replace('/', '-')
    )

TOKEN_URL   = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
SH_URL      = "https://sh.dataspace.copernicus.eu/api/v1/process"


def obtener_token(usuario, contrasena):
    """Token con credenciales de usuario normal de dataspace.copernicus.eu"""
    resp = requests.post(TOKEN_URL, data={
        "client_id":  "cdse-public",
        "username":   usuario,
        "password":   contrasena,
        "grant_type": "password",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def buscar_imagenes(token, bbox, fecha_inicio, fecha_fin, max_nubes=10):
    """
    Busca imágenes Sentinel-2 L2A disponibles.
    bbox: [lon_oeste, lat_sur, lon_este, lat_norte]
    Retorna lista de dicts con id, nombre, fecha y nubes.
    """
    w, s, e, n = bbox
    footprint = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"

    filtro = (
        f"Collection/Name eq 'SENTINEL-2' and "
        f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
        f"and att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') and "
        f"ContentDate/Start gt {fecha_inicio}T00:00:00.000Z and "
        f"ContentDate/Start lt {fecha_fin}T23:59:59.999Z and "
        f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' "
        f"and att/OData.CSC.DoubleAttribute/Value lt {max_nubes}) and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{footprint}')"
    )

    resp = requests.get(
        CATALOG_URL,
        params={"$filter": filtro, "$orderby": "ContentDate/Start desc", "$top": 20},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    resp.raise_for_status()

    resultados = []
    for p in resp.json().get("value", []):
        nubes = next(
            (a["Value"] for a in p.get("Attributes", []) if a["Name"] == "cloudCover"), 0
        )
        resultados.append({
            "id":     p["Id"],
            "nombre": p["Name"],
            "fecha":  p["ContentDate"]["Start"][:10],
            "nubes":  round(nubes, 1),
        })
    return resultados


def descargar_compuesto(token, bbox, fecha_inicio, fecha_fin, destino=None,
                        max_nubes=10, resolucion=20):
    """
    Descarga un compuesto de mediana (B04+B08+B12) para el período y área dados.
    Guarda en cache/ para no volver a descargar si ya existe.

    Parámetros:
        token:        token de acceso (solo se usa si no hay caché)
        bbox:         [lon_oeste, lat_sur, lon_este, lat_norte]
        fecha_inicio: str 'YYYY-MM-DD'
        fecha_fin:    str 'YYYY-MM-DD'
        destino:      ruta donde guardar (si None usa cache/ automáticamente)
        max_nubes:    porcentaje máximo de nubosidad por imagen
        resolucion:   resolución en metros (10 o 20)

    Retorna:
        ruta del archivo GeoTIFF guardado
    """
    # Verificar caché primero
    ruta_cache = _nombre_cache(bbox, fecha_inicio, fecha_fin, max_nubes, 'ndvi')
    if destino is None:
        destino = ruta_cache
    if os.path.exists(ruta_cache):
        print(f'  [caché] {os.path.basename(ruta_cache)}')
        return ruta_cache

    # Evalscript: compuesto de mediana — B04, B08, B12.
    # B12 (SWIR) permite calcular NBR para detectar incendios.
    # Excluye nubes (SCL 8,9,10) y sombras (SCL 3).
    evalscript = """
    //VERSION=3
    function setup() {
        return {
            input:  [{ bands: ["B04", "B08", "B12", "SCL"] }],
            output: { bands: 3, sampleType: "UINT16" },
            mosaicking: "ORBIT"
        };
    }
    function evaluatePixel(samples) {
        var b04v=[], b08v=[], b12v=[];
        for (var i=0; i<samples.length; i++) {
            var scl = samples[i].SCL;
            if (scl!==3 && scl!==8 && scl!==9 && scl!==10) {
                b04v.push(samples[i].B04);
                b08v.push(samples[i].B08);
                b12v.push(samples[i].B12);
            }
        }
        if (b04v.length===0) return [0,0,0];
        b04v.sort(function(a,b){return a-b;});
        b08v.sort(function(a,b){return a-b;});
        b12v.sort(function(a,b){return a-b;});
        var mid=Math.floor(b04v.length/2);
        return [
            Math.round(b04v[mid]*10000),
            Math.round(b08v[mid]*10000),
            Math.round(b12v[mid]*10000)
        ];
    }
    """

    w, s, e, n = bbox
    payload = {
        "input": {
            "bounds": {
                "bbox": [w, s, e, n],
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{fecha_inicio}T00:00:00Z",
                        "to":   f"{fecha_fin}T23:59:59Z",
                    },
                    "maxCloudCoverage": max_nubes,
                },
            }],
        },
        "output": {
            "width":  int((e - w) * 111320 / resolucion),
            "height": int((n - s) * 111320 / resolucion),
            "responses": [{
                "identifier": "default",
                "format": {"type": "image/tiff"},
            }],
        },
        "evalscript": evalscript,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "image/tiff",
    }

    resp = requests.post(SH_URL, json=payload, headers=headers, timeout=180)

    if resp.status_code == 401:
        raise ValueError("Credenciales incorrectas o token expirado.")
    if resp.status_code == 403:
        raise ValueError(
            "Sin acceso al Sentinel Hub Process API. "
            "Asegúrate de que tu cuenta en dataspace.copernicus.eu esté activada."
        )
    if resp.status_code == 400:
        raise ValueError(f"Error en la petición: {resp.text[:300]}")

    resp.raise_for_status()

    with open(destino, "wb") as f:
        f.write(resp.content)

    # Guardar también en caché si el destino es distinto
    if destino != ruta_cache:
        with open(ruta_cache, "wb") as f:
            f.write(resp.content)

    return destino


def descargar_rgb(token, bbox, fecha_inicio, fecha_fin, max_nubes=10, resolucion=10):
    """
    Descarga imagen de color natural (B04, B03, B02) como PNG para visualización.
    Usa caché para no volver a descargar si ya existe.
    Retorna bytes PNG listos para mostrar en folium ImageOverlay.
    """
    ruta_cache = _nombre_cache(bbox, fecha_inicio, fecha_fin, max_nubes, 'rgb').replace('.tiff', '.png')
    if os.path.exists(ruta_cache):
        print(f'  [caché] {os.path.basename(ruta_cache)}')
        with open(ruta_cache, 'rb') as f:
            return f.read()
    evalscript = """
    //VERSION=3
    function setup() {
        return {
            input:  [{ bands: ["B04", "B03", "B02"] }],
            output: { bands: 3, sampleType: "UINT8" },
            mosaicking: "ORBIT"
        };
    }
    function evaluatePixel(samples) {
        var r = [], g = [], b = [];
        for (var i = 0; i < samples.length; i++) {
            r.push(samples[i].B04);
            g.push(samples[i].B03);
            b.push(samples[i].B02);
        }
        if (r.length === 0) return [0, 0, 0];
        r.sort(function(a,b){return a-b;});
        g.sort(function(a,b){return a-b;});
        b.sort(function(a,b){return a-b;});
        var mid = Math.floor(r.length / 2);
        // Corrección gamma para colores naturales sin saturar
        function gamma(v) { return Math.round(Math.pow(Math.min(1, v * 3.5), 0.7) * 255); }
        return [gamma(r[mid]), gamma(g[mid]), gamma(b[mid])];
    }
    """

    w, s, e, n = bbox
    payload = {
        "input": {
            "bounds": {
                "bbox": [w, s, e, n],
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{fecha_inicio}T00:00:00Z",
                        "to":   f"{fecha_fin}T23:59:59Z",
                    },
                    "maxCloudCoverage": max_nubes,
                },
            }],
        },
        "output": {
            "width":  int((e - w) * 111320 / resolucion),
            "height": int((n - s) * 111320 / resolucion),
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": evalscript,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "image/png",
    }

    resp = requests.post(SH_URL, json=payload, headers=headers, timeout=180)
    resp.raise_for_status()

    # Guardar en caché
    with open(ruta_cache, 'wb') as f:
        f.write(resp.content)

    return resp.content  # bytes PNG
