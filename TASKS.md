# TASKS.md — Tablero de tareas del proyecto

> Antes de empezar una tarea, **márcala como `[EN PROGRESO]` con tu nombre de agente**.
> Al terminar, cámbiala a `[HECHO]`.
> Si bloqueás otra tarea, indica el bloqueo con `⛔`.

---

## 🔴 Pendiente (nadie la ha tomado)

- [ ] **DEPLOY-01** — Subir proyecto a GitHub (crear repo, .gitignore, primer push)
  - Archivos relevantes: todos excepto `*.tiff`, `*.pkl`, `cache/`
  - Prerequisito para: DEPLOY-02

- [ ] **DEPLOY-02** — Desplegar en Streamlit Cloud o EC2
  - Prerequisito: DEPLOY-01
  - Opciones documentadas en AGENTS.md

- [ ] **UI-01** — Separar en múltiples páginas (Streamlit multi-page)
  - Crear carpeta `pages/` con: Análisis, Histórico, Metodología
  - No tocar: lógica de `core.py`, `copernicus_api.py`

- [ ] **UI-02** — Refinar CSS y layout general
  - El otro agente (Gemini) ya agregó CSS base en `app.py`
  - No sobreescribir el bloque `<style>` existente, solo extender

- [ ] **FEAT-01** — Calculadora de impacto CO₂
  - 1 ha bosque ≈ 150-300 ton CO₂
  - Agregar como métrica extra en el dashboard, debajo de las 4 métricas actuales

- [ ] **FEAT-02** — Gráfico histórico NDVI del CSV
  - Usar `Sentinel-2 L2A-3_NDVI-*.csv` ya analizado
  - Mostrar en una nueva pestaña o página con plotly/altair

- [ ] **FEAT-03** — Migración a FastAPI + React (largo plazo)
  - Ver DECISIONS.md para el plan de migración
  - No iniciar hasta que DEPLOY-02 esté hecho

---

## 🟡 En progreso

- [ ] **TRAIN-01** — Ejecutar `entrenar_modelo.py` con datos multi-zona
  - **[EN PROGRESO — Usuario]**
  - Descargas: ~50 composites con caché
  - Genera: `modelo_clasificador.pkl` con 3 clases
  - ⛔ Bloquea: cualquier cambio a `core.py → clasificar_tipo()` hasta terminar

---

## 🟢 Completado

- [x] **MODEL-01** — Clasificador Random Forest 3 clases (tala / incendio / sin cambio)
- [x] **MODEL-02** — Agregar B12/NBR como feature (9 features totales)
- [x] **MODEL-03** — Entrenamiento multi-zona, multi-año, multi-estación
- [x] **DATA-01** — Sistema de caché en `cache/` para composites
- [x] **MAP-01** — Sombreado toggleable con polígonos reales de cada zona
- [x] **MAP-02** — Capas RGB Sentinel-2 en el mapa (imagen real del período)
- [x] **MAP-03** — Mini-mapa satelital al seleccionar fila en tabla
- [x] **MAP-04** — Botón "Abrir en Google Maps" con coordenadas exactas
- [x] **UI-00** — Dashboard Streamlit con CSS base, sidebar simplificado, atajos de fechas
- [x] **DOC-01** — CLAUDE.md, AGENTS.md, TASKS.md, DECISIONS.md, CONVENTIONS.md

---

## Reglas para agentes

1. **Una tarea a la vez por agente** — no tomes dos tareas simultáneas
2. **No toques archivos en uso** — si TRAIN-01 está en progreso, no modifiques `core.py`
3. **Marca siempre el estado** antes de empezar
4. **Si creas un archivo nuevo**, agrégalo a la lista de archivos en `AGENTS.md`
5. **Si tomás una decisión de arquitectura**, documentala en `DECISIONS.md`
