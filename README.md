# 🌊 Análisis Multitemporal — Río Chinchiná, Caldas

Script Python con **Google Earth Engine** para detectar y exportar el trazado del cauce del Río Chinchiná en los años **2006, 2012, 2018 y 2026**, generando un archivo **KML por año** para comparación en Google Earth Pro.

---

## 📋 Requisitos

```bash
pip install earthengine-api geemap
```

> Necesitas una cuenta de **Google Earth Engine** registrada en [earthengine.google.com](https://earthengine.google.com)

---

## 🚀 Ejecución

### Paso 1 — Autenticar GEE (solo la primera vez)

```bash
earthengine authenticate
```

### Paso 2 — Ejecutar el script

```bash
python rio_chinchina_gee.py
```

### Paso 3 — Monitorear exportaciones

Las tareas de exportación corren en segundo plano. Revisa su estado en:  
👉 [https://code.earthengine.google.com/tasks](https://code.earthengine.google.com/tasks)

### Paso 4 — Descargar los KML

Ve a **Google Drive → carpeta `RioChinchina_KML`** y descarga los 4 archivos:
- `cauce_rio_chinchina_2006.kml`
- `cauce_rio_chinchina_2012.kml`
- `cauce_rio_chinchina_2018.kml`
- `cauce_rio_chinchina_2026.kml`

### Paso 5 — Abrir en Google Earth Pro

1. Abre **Google Earth Pro**
2. `Archivo → Importar...` → selecciona los 4 `.kml` a la vez (o uno por uno)
3. Cada año aparecerá como una capa independiente en el panel izquierdo
4. Activa/desactiva años para comparar la evolución del cauce

---

## 🛰️ Satélites utilizados

| Año  | Satélite         | Colección GEE                     | Resolución |
|------|------------------|-----------------------------------|------------|
| 2006 | Landsat 5 TM     | `LANDSAT/LT05/C02/T1_L2`         | 30 m       |
| 2012 | Landsat 7 ETM+   | `LANDSAT/LE07/C02/T1_L2`         | 30 m       |
| 2018 | Landsat 8 OLI    | `LANDSAT/LC08/C02/T1_L2`         | 30 m       |
| 2026 | Landsat 9 OLI-2  | `LANDSAT/LC09/C02/T1_L2`         | 30 m       |
|      | *(respaldo S2)*  | `COPERNICUS/S2_SR_HARMONIZED`     | 10 m       |

---

## 🌊 Índice de agua: MNDWI

```
MNDWI = (Green - SWIR) / (Green + SWIR)
```

- **Umbral**: `MNDWI > 0.05`  
- Detecta cauces de ríos, incluyendo zonas turbulentas y de sombra en cordillera  
- Superior al NDWI clásico en zonas montañosas con vegetación densa

---

## 🗺️ Área de estudio

```
Cuenca del Río Chinchiná (~1.052 km²)
├── Nacimiento : Parque Nacional Los Nevados (~5.200 m s.n.m.)
├── Eje urbano : Manizales / Villamaría
└── Desembocadura: Río Cauca (~860 m s.n.m.)

Bounding Box: [-75.92°W, 4.80°N] → [-75.33°W, 5.15°N]
Municipios: Manizales, Villamaría, Chinchiná, Palestina, Neira
```

---

## ⚙️ Estructura del script

```
rio_chinchina_gee.py
├── inicializar_gee()           # Autenticación GEE
├── AOI_CUENCA                  # Geometría de la cuenca
├── CONFIGURACION_ANOS          # Config por año (colección, bandas, ventana)
├── mascara_nubes_landsat_457() # Máscara nubes L4/5/7
├── mascara_nubes_landsat_89()  # Máscara nubes L8/9
├── mascara_nubes_sentinel2()   # Máscara nubes S2
├── calcular_mndwi()            # Cálculo MNDWI
├── obtener_compuesto_anual()   # Compuesto de mediana con menor nubosidad
├── extraer_cauce()             # Vectorización de píxeles de agua
├── exportar_kml()              # Exportación a Google Drive en formato KML
├── visualizar_mapa()           # Mapa interactivo con geemap (Jupyter)
└── main()                      # Flujo principal
```

---

## 💡 Notas técnicas

- **Landsat 7 (2012)**: Tiene el defecto "SLC-off" desde mayo 2003 que genera franjas sin datos. El compuesto de **mediana** de múltiples escenas mitiga este problema efectivamente.
- **Ventana temporal**: El script usa una ventana de ±6 meses para capturar las escenas con **menos nubes** (temporada relativamente seca: diciembre–marzo).
- **Escalado de reflectancias**: Colección 2 Level 2 de Landsat aplica factor `× 0.0000275 + (-0.2)` automáticamente en el script.
- **Ruido**: Para ríos de 10-50m de ancho como el Chinchiná, la resolución de 30m (Landsat) puede subestimar el cauce en zonas estrechas. El respaldo con Sentinel-2 (10m) mejora esto para 2026.
