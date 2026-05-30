# DECISIONS.md — Registro de decisiones de arquitectura

> Antes de cambiar algo que aparece aquí, **leer el razonamiento**.
> Si se decide cambiar igual, agregar una nueva entrada en vez de borrar la anterior.

---

## DEC-001 — Streamlit como framework principal
**Fecha:** Mayo 2026
**Estado:** Activo

**Decisión:** Usar Streamlit en vez de Django, Flask o FastAPI+React.

**Razón:** Proyecto académico con plazo de 2 semanas. Streamlit permite construir el dashboard completo sin separar backend/frontend. El usuario tiene Python básico-intermedio.

**Consecuencia aceptada:** Re-ejecuta el script completo en cada interacción (más lento que React).

**Ruta futura:** Migrar a FastAPI + React cuando el proyecto pase a producto real. El usuario tiene experiencia con FastAPI. Ver DEC-008.

---

## DEC-002 — Sentinel Hub Process API para descargas
**Fecha:** Mayo 2026
**Estado:** Activo

**Decisión:** Usar Sentinel Hub Process API (`sh.dataspace.copernicus.eu`) en vez de descargar productos completos via OData.

**Razón:** La API OData de Copernicus devuelve nodos vacíos (posible cambio en la API en 2025). Sentinel Hub permite descargar exactamente el área y bandas necesarias (~3-5MB por composite vs ~600MB producto completo).

**No revertir:** El enfoque OData fue probado y falló para todos los productos. No intentar reactivarlo.

---

## DEC-003 — Random Forest en vez de red neuronal
**Fecha:** Mayo 2026
**Estado:** Activo

**Decisión:** Usar scikit-learn RandomForestClassifier en vez de CNN o red neuronal.

**Razón:** scikit-learn no requiere GPU, se entrena en minutos con los datos disponibles, y es interpretable (feature importance). El usuario no tiene GPU dedicada.

**Precisión alcanzada:** ~87% con 9 features.

**Cuándo cambiar:** Si se agregan más datos y se quiere superar 93%, considerar XGBoost (mismo enfoque, mejor rendimiento) o un CNN simple si se tienen >10,000 ejemplos etiquetados por clase.

---

## DEC-004 — Compuesto de mediana via evalscript en vez de descargar imágenes individuales
**Fecha:** Mayo 2026
**Estado:** Activo

**Decisión:** Una sola petición a Sentinel Hub que devuelve el composite de mediana, en vez de descargar N imágenes y calcular la mediana localmente.

**Razón:** Reduce descargas de N×20MB a 1×5MB. Sentinel Hub hace el cálculo server-side. El usuario no tiene que gestionar fechas individuales.

**Consecuencia:** No se puede ver qué imagen individual contribuyó a cada pixel.

---

## DEC-005 — 3 clases en el modelo (no binario)
**Fecha:** Mayo 2026
**Estado:** Activo (pendiente reentrenamiento completo)

**Decisión:** Modelo 3 clases: sin cambio / tala / incendio.

**Razón:** El objetivo del proyecto incluye detectar incendios. Con solo 2 clases el modelo no puede distinguir incendio de tala.

**Datos de incendio:** Zona Penco-Tomé-Lirquén enero 2026. Labels via `delta_nbr < -0.27`.

**Compatibilidad:** `clasificar_tipo()` detecta automáticamente si el modelo tiene 2 o 3 clases. El modelo anterior (2 clases) sigue funcionando.

---

## DEC-006 — Caché de composites en `cache/`
**Fecha:** Mayo 2026
**Estado:** Activo

**Decisión:** Guardar cada composite descargado en `cache/` con nombre único basado en bbox+fechas+nubes.

**Razón:** Evita re-descargar en análisis repetidos. Crítico para el entrenamiento (~50 descargas que con caché son instantáneas en ejecuciones posteriores).

**No borrar cache/ sin avisar al usuario.** Contiene horas de descargas.

---

## DEC-007 — Polígonos reales via rasterio.features.shapes
**Fecha:** Mayo 2026
**Estado:** Activo

**Decisión:** Extraer el contorno real de cada zona detectada usando `rasterio.features.shapes()` en vez de mostrar solo un punto o círculo aproximado.

**Razón:** El sombreado del área real en el mapa es mucho más informativo que un marcador circular, especialmente para mostrar la forma de taladas (rectángulares) vs incendios (irregulares).

**Impacto en rendimiento:** Con 500+ zonas el mapa puede ser lento. Si hay problemas, aumentar `min_ha` en el slider para reducir zonas mostradas.

---

## DEC-008 — Plan de migración a FastAPI + React (futuro)
**Fecha:** Mayo 2026
**Estado:** Planificado, no iniciado

**Decisión:** Cuando el proyecto evolucione a producto real, migrar a FastAPI backend + React frontend.

**Arquitectura objetivo:**
```
EC2 t3.small:
  FastAPI (puerto 8000) → modelo cargado en memoria, cache/ en EBS
  Nginx (puerto 80/443) → proxy inverso

S3:
  Frontend React (estático, ~$0.01/mes)
  Leaflet.js para mapas (reemplaza Folium)
```

**Ventaja clave:** El modelo se carga una sola vez para todos los usuarios (no por sesión como en Streamlit). Con FastAPI async, t3.small maneja 10-15 usuarios simultáneos.

**Prerequisito:** Completar DEPLOY-01 y DEPLOY-02 primero.

---

## DEC-009 — Bandas B04 + B08 + B12 en todos los composites
**Fecha:** Mayo 2026
**Estado:** Activo

**Decisión:** Descargar siempre las 3 bandas (B04, B08, B12) en un solo TIFF de 3 bandas.

**Razón:** B12 permite calcular NBR para detectar incendios. El costo adicional de descarga es mínimo (~10% más pesado). Sin B12, la detección de incendios es solo por reglas heurísticas.

**Compatibilidad:** Si por alguna razón el composite solo tiene 2 bandas, `calcular_nbr()` retorna None y el sistema cae a reglas. No rompe nada.
