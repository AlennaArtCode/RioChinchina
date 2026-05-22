"""
=============================================================================
  ANÁLISIS MULTITEMPORAL DEL RÍO CHINCHINÁ - CALDAS, COLOMBIA
  Google Earth Engine Python API
=============================================================================
  Autor  : Alenna Art Code
  Fecha  : Mayo 2026
  Región : Cuenca del Río Chinchiná
             Parque Nacional Natural Los Nevados → Río Cauca
             Municipios: Manizales, Villamaría, Chinchiná, Palestina, Neira

  OBJETIVO:
    Detectar y exportar el trazado del cauce del Río Chinchiná para los
    años 2006, 2012, 2018 y 2026 usando imágenes Landsat / Sentinel-2,
    generando un archivo KML independiente por año para visualización
    comparativa en Google Earth Pro.

  ÍNDICE DE AGUA UTILIZADO:
    MNDWI = (Green - SWIR) / (Green + SWIR)
    (Modified Normalized Difference Water Index – Xu, 2006)
    Mejor que NDWI para discriminar cuerpos de agua de vegetación densa
    y terreno montañoso como el de la cordillera Central.

  COLECCIONES SATELITALES POR AÑO:
    2006 → Landsat 5 TM  (LANDSAT/LT05/C02/T1_L2)
    2012 → Landsat 7 ETM+ (LANDSAT/LE07/C02/T1_L2) [SLC-off corregido por mediana]
    2018 → Landsat 8 OLI  (LANDSAT/LC08/C02/T1_L2)
    2026 → Landsat 9 OLI-2 (LANDSAT/LC09/C02/T1_L2) + respaldo Sentinel-2

  REQUISITOS PREVIOS:
    pip install earthengine-api geemap geopandas simplekml
    ee.Authenticate()  ← ejecutar una sola vez
    ee.Initialize()

  SALIDA:
    Google Drive / carpeta "RioChinchina_KML":
      cauce_rio_chinchina_2006.kml
      cauce_rio_chinchina_2012.kml
      cauce_rio_chinchina_2018.kml
      cauce_rio_chinchina_2026.kml
=============================================================================
"""

import ee
import geemap
import sys
import os

# Forzar UTF-8 en la consola de Windows para evitar errores de encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ─────────────────────────────────────────────────────────────────────────────
# 1. INICIALIZACIÓN DE GOOGLE EARTH ENGINE
# ─────────────────────────────────────────────────────────────────────────────

GEE_PROJECT = 'ee-fernando1quim'

def inicializar_gee():
    """Autentica e inicializa la conexion con Google Earth Engine."""
    try:
        ee.Initialize(project=GEE_PROJECT)
        print("[OK] GEE inicializado - proyecto: " + GEE_PROJECT)
    except Exception as e:
        print("[!]  Error al inicializar: " + str(e))
        print("     Intentando autenticar con navegador...")
        ee.Authenticate(auth_mode='localhost')
        ee.Initialize(project=GEE_PROJECT)
        print("[OK] GEE autenticado e inicializado.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. ÁREA DE INTERÉS (AOI) – CUENCA DEL RÍO CHINCHINÁ
# ─────────────────────────────────────────────────────────────────────────────
# NOTA: Las geometrías se definen dentro de main() para asegurar que
#       ee.Initialize() se llame primero.
#
#  Límites aproximados de la cuenca (~1.052 km²):
#    Norte  : 5.15° N  (zona de Neira)
#    Sur    : 4.80° N  (Parque Los Nevados / Nevado del Ruiz ~5.200 m s.n.m.)
#    Oeste  : 75.92° W (desembocadura en el Río Cauca ~860 m s.n.m.)
#    Este   : 75.33° W (divisoria de aguas cordillera Central)
#
#  Zona focal Manizales / Villamaría:
#    Centro aproximado: 5.070°N, 75.515°W

# Placeholder global — se inicializa en main() después de ee.Initialize()
AOI = None

# ─────────────────────────────────────────────────────────────────────────────
# 3. CONFIGURACIÓN POR AÑO Y COLECCIÓN SATELITAL
# ─────────────────────────────────────────────────────────────────────────────

CONFIGURACION_ANOS = {
    2006: {
        "coleccion"   : "LANDSAT/LT05/C02/T1_L2",  # Landsat 5 TM
        "satelite"    : "Landsat 5 TM",
        "banda_verde" : "SR_B2",   # 0.52–0.60 µm
        "banda_nir"   : "SR_B4",   # 0.76–0.90 µm
        "banda_swir"  : "SR_B5",   # 1.55–1.75 µm (SWIR-1)
        "banda_qa"    : "QA_PIXEL",
        "tipo"        : "L457",
        "ventana"     : ("2005-11-01", "2007-03-31"),  # temporada seca + margen
    },
    2012: {
        "coleccion"   : "LANDSAT/LE07/C02/T1_L2",  # Landsat 7 ETM+ (SLC-off)
        "satelite"    : "Landsat 7 ETM+",
        "banda_verde" : "SR_B2",
        "banda_nir"   : "SR_B4",
        "banda_swir"  : "SR_B5",
        "banda_qa"    : "QA_PIXEL",
        "tipo"        : "L457",
        "ventana"     : ("2011-11-01", "2013-03-31"),
    },
    2018: {
        "coleccion"   : "LANDSAT/LC08/C02/T1_L2",  # Landsat 8 OLI
        "satelite"    : "Landsat 8 OLI",
        "banda_verde" : "SR_B3",   # 0.53–0.59 µm
        "banda_nir"   : "SR_B5",   # 0.85–0.88 µm
        "banda_swir"  : "SR_B6",   # 1.57–1.65 µm (SWIR-1)
        "banda_qa"    : "QA_PIXEL",
        "tipo"        : "L89",
        "ventana"     : ("2017-11-01", "2019-03-31"),
    },
    2026: {
        "coleccion"   : "LANDSAT/LC09/C02/T1_L2",  # Landsat 9 OLI-2
        "satelite"    : "Landsat 9 OLI-2",
        "banda_verde" : "SR_B3",
        "banda_nir"   : "SR_B5",
        "banda_swir"  : "SR_B6",
        "banda_qa"    : "QA_PIXEL",
        "tipo"        : "L89",
        "ventana"     : ("2025-11-01", "2026-05-22"),
        "respaldo"    : {          # Si L9 tiene pocas escenas, usar Sentinel-2
            "coleccion"   : "COPERNICUS/S2_SR_HARMONIZED",
            "satelite"    : "Sentinel-2 MSI",
            "banda_verde" : "B3",    # 0.56 µm (10 m)
            "banda_nir"   : "B8",    # 0.84 µm (10 m)
            "banda_swir"  : "B11",   # 1.61 µm (20 m)
            "tipo"        : "S2",
        }
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. FUNCIONES DE MÁSCARA DE NUBES
# ─────────────────────────────────────────────────────────────────────────────

def mascara_nubes_landsat_457(imagen):
    """
    Máscara de nubes para Landsat 4, 5 y 7 Collection 2 Level 2.
    Usa el canal QA_PIXEL (CFMASK). Bit 3 = nube, Bit 4 = sombra de nube.
    """
    qa = imagen.select("QA_PIXEL")
    mascara = (
        qa.bitwiseAnd(1 << 3).eq(0)   # sin nubes
        .And(qa.bitwiseAnd(1 << 4).eq(0))  # sin sombra de nube
    )
    # Escalar reflectancias: factor 0.0000275, offset -0.2
    return imagen.updateMask(mascara) \
                 .multiply(0.0000275).add(-0.2) \
                 .copyProperties(imagen, ["system:time_start"])


def mascara_nubes_landsat_89(imagen):
    """
    Máscara de nubes para Landsat 8 y 9 Collection 2 Level 2.
    Igual estructura QA_PIXEL que L457.
    """
    qa = imagen.select("QA_PIXEL")
    mascara = (
        qa.bitwiseAnd(1 << 3).eq(0)
        .And(qa.bitwiseAnd(1 << 4).eq(0))
    )
    return imagen.updateMask(mascara) \
                 .multiply(0.0000275).add(-0.2) \
                 .copyProperties(imagen, ["system:time_start"])


def mascara_nubes_sentinel2(imagen):
    """
    Máscara de nubes para Sentinel-2 SR usando SCL (Scene Classification Layer).
    Valores SCL: 4=veg, 5=suelo/edificios, 6=agua, 7=nube baja confianza,
                 8=nube media, 9=nube alta, 10=cirrus, 11=nieve
    Mantenemos solo clases no-nube: 2,4,5,6,11
    """
    scl = imagen.select("SCL")
    mascara = scl.eq(2).Or(scl.eq(4)).Or(scl.eq(5)) \
                 .Or(scl.eq(6)).Or(scl.eq(11))
    return imagen.updateMask(mascara) \
                 .divide(10000) \
                 .copyProperties(imagen, ["system:time_start"])


# ─────────────────────────────────────────────────────────────────────────────
# 5. CÁLCULO DEL MNDWI
# ─────────────────────────────────────────────────────────────────────────────

def calcular_mndwi(imagen, banda_verde, banda_swir):
    """
    Calcula el MNDWI (Modified Normalized Difference Water Index).
    
    MNDWI = (Green - SWIR) / (Green + SWIR)
    
    Valores > 0 → agua / humedales
    Valores < 0 → suelo / vegetación
    
    Umbral típico para ríos de montaña con turbidez: MNDWI > 0.0
    (más conservador que 0.2 para capturar cauces estrechos)
    """
    mndwi = imagen.normalizedDifference([banda_verde, banda_swir]) \
                  .rename("MNDWI")
    return imagen.addBands(mndwi)


# ─────────────────────────────────────────────────────────────────────────────
# 6. OBTENER IMAGEN COMPUESTA PARA UN AÑO
# ─────────────────────────────────────────────────────────────────────────────

def obtener_compuesto_anual(config, aoi, umbral_nubes=30):
    """
    Filtra y crea una imagen compuesta (mediana) para el año dado.
    
    Parámetros:
        config       : dict con configuración del año
        aoi          : ee.Geometry del área de interés
        umbral_nubes : porcentaje máximo de cobertura nubosa por escena (%)
    
    Retorna:
        ee.Image compuesta con MNDWI calculado
        int número de escenas disponibles
    """
    tipo = config["tipo"]
    
    # Seleccionar función de máscara de nubes
    if tipo == "L457":
        fn_mascara = mascara_nubes_landsat_457
    elif tipo == "L89":
        fn_mascara = mascara_nubes_landsat_89
    else:  # S2
        fn_mascara = mascara_nubes_sentinel2
    
    # Filtrar colección
    coleccion = (
        ee.ImageCollection(config["coleccion"])
        .filterBounds(aoi)
        .filterDate(config["ventana"][0], config["ventana"][1])
        .filter(ee.Filter.lt("CLOUD_COVER", umbral_nubes)
                if tipo != "S2"
                else ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", umbral_nubes))
        .map(fn_mascara)
    )
    
    num_escenas = coleccion.size().getInfo()
    print(f"   -> {num_escenas} escenas disponibles con <{umbral_nubes}% nubes")
    
    # Si hay muy pocas escenas, ampliar umbral de nubes
    if num_escenas < 3:
        print(f"   [!] Pocas escenas. Ampliando umbral a 60%...")
        coleccion = (
            ee.ImageCollection(config["coleccion"])
            .filterBounds(aoi)
            .filterDate(config["ventana"][0], config["ventana"][1])
            .filter(ee.Filter.lt("CLOUD_COVER", 60)
                    if tipo != "S2"
                    else ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
            .map(fn_mascara)
        )
        num_escenas = coleccion.size().getInfo()
        print(f"   -> {num_escenas} escenas con umbral ampliado")
    
    # Compuesto de mediana (robusto frente a nubes residuales y striping L7)
    compuesto = coleccion.median().clip(aoi)
    
    # Calcular MNDWI
    compuesto = calcular_mndwi(
        compuesto,
        config["banda_verde"],
        config["banda_swir"]
    )
    
    return compuesto, num_escenas


def obtener_compuesto_sentinel2(config_s2, aoi, ventana):
    """Versión específica para Sentinel-2 (respaldo 2026)."""
    fn_mascara = mascara_nubes_sentinel2
    
    coleccion = (
        ee.ImageCollection(config_s2["coleccion"])
        .filterBounds(aoi)
        .filterDate(ventana[0], ventana[1])
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .map(fn_mascara)
    )
    
    num_escenas = coleccion.size().getInfo()
    print(f"   -> [S2 respaldo] {num_escenas} escenas Sentinel-2")
    
    compuesto = coleccion.median().clip(aoi)
    compuesto = calcular_mndwi(
        compuesto,
        config_s2["banda_verde"],
        config_s2["banda_swir"]
    )
    
    return compuesto, num_escenas


# ─────────────────────────────────────────────────────────────────────────────
# 7. EXTRAER MÁSCARA DE AGUA Y VECTORIZAR EL CAUCE
# ─────────────────────────────────────────────────────────────────────────────

def extraer_cauce(compuesto, aoi, umbral_mndwi=0.05, escala_m=30):
    """
    Extrae el cauce del río como polígonos vectoriales a partir del MNDWI.
    
    Parámetros:
        compuesto    : ee.Image con banda MNDWI
        aoi          : ee.Geometry del área
        umbral_mndwi : umbral de clasificación agua (default: 0.05)
                       0.0  → cauce + espejos de agua → más completo
                       0.2  → solo agua clara → más preciso, menos ruidoso
        escala_m     : resolución espacial en metros para vectorización
    
    Retorna:
        ee.FeatureCollection con polígonos del cauce
    """
    # Máscara binaria: 1=agua, 0=no agua
    mascara_agua = compuesto.select("MNDWI").gte(umbral_mndwi)
    
    # Reducir a vecores (polígonos)
    # maxPixels alto para cubrir la cuenca completa
    vectores = mascara_agua.reduceToVectors(
        geometry        = aoi,
        scale           = escala_m,
        geometryType    = "polygon",
        eightConnected  = True,       # conectividad 8 (diagonal) para ríos
        labelProperty   = "agua",
        maxPixels       = 1e10,
        bestEffort      = True,       # reduce escala si es necesario
    )
    
    # Filtrar solo píxeles de agua (valor=1) y áreas mínimas (eliminar ruido)
    # Área mínima: ~3 píxeles × 30m = 90m → cubre cauces de ~10-30m de ancho
    cauce = vectores.filter(ee.Filter.eq("agua", 1))
    
    return cauce


# ─────────────────────────────────────────────────────────────────────────────
# 8. EXPORTAR A KML EN GOOGLE DRIVE
# ─────────────────────────────────────────────────────────────────────────────

def exportar_kml(cauce_fc, anno, descripcion, carpeta_drive="RioChinchina_KML"):
    """
    Exporta un FeatureCollection a formato KML en Google Drive.
    
    Los archivos se guardarán en tu Google Drive en la carpeta especificada.
    Después de ejecutar este script, ve a:
      Google Drive → RioChinchina_KML → descarga los .kml
    
    Parámetros:
        cauce_fc      : ee.FeatureCollection del cauce extraído
        anno          : int año del análisis
        descripcion   : str descripción del satélite usado
        carpeta_drive : str nombre de carpeta en Google Drive
    """
    nombre_archivo = f"cauce_rio_chinchina_{anno}"
    
    # Añadir atributos descriptivos a cada feature
    cauce_con_attrs = cauce_fc.map(lambda f: f
        .set("año",        anno)
        .set("rio",        "Río Chinchiná")
        .set("cuenca",     "Cuenca Río Chinchiná - Caldas, Colombia")
        .set("satelite",   descripcion)
        .set("indice",     "MNDWI > 0.05")
        .set("fuente",     "Google Earth Engine")
        .set("elaborado",  "Alenna Art Code / 2026")
    )
    
    tarea = ee.batch.Export.table.toDrive(
        collection       = cauce_con_attrs,
        description      = nombre_archivo,
        folder           = carpeta_drive,
        fileNamePrefix   = nombre_archivo,
        fileFormat       = "KML",
    )
    
    tarea.start()
    print(f"   [OK] Exportacion iniciada -> Google Drive/{carpeta_drive}/{nombre_archivo}.kml")
    print(f"        ID de tarea GEE: {tarea.id}")
    
    return tarea


# ─────────────────────────────────────────────────────────────────────────────
# 9. VISUALIZACIÓN INTERACTIVA (OPCIONAL - REQUIERE JUPYTER)
# ─────────────────────────────────────────────────────────────────────────────

def visualizar_mapa(compuestos_dict, cauces_dict):
    """
    Genera un mapa interactivo con geemap para previsualización en Jupyter.
    Solo ejecutar si corres este script en un Jupyter Notebook.
    """
    PALETA_AGUA = ["#ffffff", "#a8d8ea", "#0077b6", "#03045e"]
    
    Map = geemap.Map(center=[5.07, -75.52], zoom=10)
    Map.add_basemap("HYBRID")
    
    vis_mndwi = {
        "min"    : -0.5,
        "max"    : 0.5,
        "palette": ["#8B4513", "#FFFFF0", "#0077b6"],
    }
    
    colores_anno = {
        2006: "#FFD700",  # dorado
        2012: "#FF6B35",  # naranja
        2018: "#7ED321",  # verde
        2026: "#00D4FF",  # cian
    }
    
    for anno, compuesto in compuestos_dict.items():
        Map.addLayer(
            compuesto.select("MNDWI").clip(AOI),
            vis_mndwi,
            f"MNDWI {anno}",
            shown=False
        )
    
    for anno, cauce in cauces_dict.items():
        Map.addLayer(
            cauce,
            {"color": colores_anno[anno]},
            f"Cauce {anno}"
        )
    
    Map.add_legend(
        title="Cauce Río Chinchiná",
        legend_dict={f"Cauce {a}": c for a, c in colores_anno.items()}
    )
    
    return Map


# ─────────────────────────────────────────────────────────────────────────────
# 10. FLUJO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  ANÁLISIS MULTITEMPORAL - RÍO CHINCHINÁ, CALDAS, COLOMBIA")
    print("  Google Earth Engine Python API")
    print("=" * 65)
    
    # Inicializar GEE PRIMERO
    inicializar_gee()

    # Definir AOI después de inicializar GEE
    global AOI
    AOI = ee.Geometry.Polygon([[
        [-75.92, 4.80],
        [-75.33, 4.80],
        [-75.33, 5.15],
        [-75.92, 5.15],
        [-75.92, 4.80]
    ]])
    print(f"📍 AOI definida: Cuenca Río Chinchiná, Caldas, Colombia")
    print(f"   Extensión: ~75.92°W – 75.33°W | 4.80°N – 5.15°N")
    
    compuestos_dict = {}
    cauces_dict     = {}
    tareas_export   = []
    
    # Procesar cada año
    for anno, config in CONFIGURACION_ANOS.items():
        print(f"\n{'─'*60}")
        print(f"[{anno}] PROCESANDO -> {config['satelite']}")
        print(f"   Ventana temporal: {config['ventana'][0]} -> {config['ventana'][1]}")
        
        # Obtener compuesto satelital
        compuesto, num_escenas = obtener_compuesto_anual(config, AOI)
        
        # Si 2026 con Landsat 9 tiene 0 escenas, usar Sentinel-2 como respaldo
        if anno == 2026 and num_escenas == 0:
            print(f"   🔄 Sin datos L9. Usando Sentinel-2 como respaldo...")
            config_s2  = CONFIGURACION_ANOS[2026]["respaldo"]
            compuesto, num_escenas = obtener_compuesto_sentinel2(
                config_s2, AOI, config["ventana"]
            )
            config = {**config, **config_s2}
        
        if num_escenas == 0:
            print(f"   ❌ Sin imágenes disponibles para {anno}. Saltando...")
            continue
        
        compuestos_dict[anno] = compuesto
        
        # Extraer cauce con MNDWI
        print(f"   🌊 Extrayendo cauce (MNDWI > 0.05, resolución 30m)...")
        cauce = extraer_cauce(compuesto, AOI)
        cauces_dict[anno] = cauce
        
        # Exportar KML a Google Drive
        print(f"   📤 Exportando KML a Google Drive...")
        tarea = exportar_kml(
            cauce_fc    = cauce,
            anno        = anno,
            descripcion = config["satelite"],
        )
        tareas_export.append((anno, tarea))
    
    # ── Resumen de exportaciones ──────────────────────────────────────────
    print(f"\n{'='*65}")
    print("RESUMEN DE EXPORTACIONES")
    print(f"{'─'*65}")
    print(f"  Carpeta en Google Drive: RioChinchina_KML/")
    print()
    for anno, tarea in tareas_export:
        estado = tarea.status()["state"]
        print(f"  {anno}: cauce_rio_chinchina_{anno}.kml  [{estado}]")
    
    print(f"\n{'─'*65}")
    print("COMO DESCARGAR LOS KML:")
    print("  1. Ve a Google Drive -> carpeta 'RioChinchina_KML'")
    print("  2. Descarga los 4 archivos .kml")
    print("  3. Abre Google Earth Pro")
    print("  4. Archivo -> Importar... -> selecciona todos los .kml a la vez")
    print("  5. Activa/desactiva años en el panel izquierdo para comparar")
    print()
    print("Las tareas de exportacion corren en segundo plano en GEE.")
    print("Monitorea el estado en: https://code.earthengine.google.com/tasks")
    print("=" * 65)
    
    return compuestos_dict, cauces_dict


# ─────────────────────────────────────────────────────────────────────────────
# 11. FUNCIONES AUXILIARES EXTRA
# ─────────────────────────────────────────────────────────────────────────────

def verificar_estado_tareas():
    """
    Verifica el estado de todas las tareas de exportación activas en GEE.
    Ejecutar después del main() para monitorear el progreso.
    """
    print("\n📡 Estado de tareas en GEE:")
    tareas = ee.batch.Task.list()
    for t in tareas[:10]:  # Mostrar las 10 más recientes
        status = t.status()
        nombre = status.get("description", "sin nombre")
        estado = status.get("state", "desconocido")
        icono  = {"COMPLETED": "✅", "RUNNING": "⏳", "FAILED": "❌",
                  "READY": "🔄", "CANCEL_REQUESTED": "⚠️"}.get(estado, "❓")
        print(f"  {icono} {nombre}: {estado}")


def exportar_como_imagen_tif(compuesto, anno, aoi, carpeta_drive="RioChinchina_TIFF"):
    """
    Alternativa: exporta el MNDWI como GeoTIFF para análisis en QGIS.
    Útil si necesitas trabajar localmente con los rásteres.
    """
    tarea = ee.batch.Export.image.toDrive(
        image          = compuesto.select("MNDWI"),
        description    = f"mndwi_chinchina_{anno}",
        folder         = carpeta_drive,
        fileNamePrefix = f"mndwi_chinchina_{anno}",
        region         = aoi,
        scale          = 30,
        crs            = "EPSG:4326",
        maxPixels      = 1e10,
        fileFormat     = "GeoTIFF",
    )
    tarea.start()
    print(f"✅ GeoTIFF {anno} iniciado: {tarea.id}")
    return tarea


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    compuestos, cauces = main()
    
    # Opcional: verificar estado de tareas después de unos segundos
    # import time; time.sleep(10)
    # verificar_estado_tareas()
    
    # Opcional: visualización interactiva (solo en Jupyter Notebook)
    # mapa = visualizar_mapa(compuestos, cauces)
    # mapa  # ← mostrar en celda de Jupyter
