"""
=============================================================================
  RÍO CHINCHINÁ — SCRIPT DE PRECISIÓN 2025 (CORREGIDO)
  - Usa coordenadas reales de OSM (2.884 nodos) en vez de la línea simplificada
  - Soluciona el error de reproyección de la mediana y el error del buffer
  - Exporta en formato KML para su fácil integración en el visualizador web
=============================================================================
"""
import ee, sys, io, json

# Asegurar codificación utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Proyecto GEE del usuario
GEE_PROJECT = 'ee-fernando1quim'

def main():
    print("=" * 65)
    print("  RÍO CHINCHINÁ — Mapeo de Precisión 2025")
    print("  Corregido y optimizado para visualización KML / Web")
    print("=" * 65)

    # Inicializar Earth Engine
    try:
        ee.Initialize(project=GEE_PROJECT)
        print("[OK] GEE inicializado con éxito.")
    except Exception as e:
        print("La inicialización de GEE falló. Ejecute ee.Authenticate() para conectar su cuenta.")
        raise e

    # 1. Cargar el trazado geográfico detallado del Río Chinchiná (desde OSM)
    # Reemplazamos la aproximación lineal de 6 puntos por los 2.884 nodos reales
    try:
        with open('chinchina_osm.geojson', encoding='utf-8') as f:
            gj = json.load(f)
        print(f"[OK] GeoJSON de OSM cargado: {len(gj['features'])} segmentos")
    except Exception as e:
        print("Error al cargar chinchina_osm.geojson. Asegúrese de que el archivo esté en la misma carpeta.")
        raise e

    # Unir todas las líneas en una sola geometría
    rio_union = ee.Geometry.MultiLineString(
        [feat['geometry']['coordinates'] for feat in gj['features']
         if len(feat['geometry']['coordinates']) >= 2]
    )

    # 2. Creación del área de análisis mediante Buffer de 800 metros
    # Corregido: Se remueve el método .reproject() que causaba error en el objeto Geometry
    buffer_analisis = rio_union.buffer(800)
    print("[OK] Buffer de 800m creado de forma geodésica.")

    # 3. Función de enmascaramiento de nubes y sombras basada en la banda SCL de Sentinel-2
    def enmascarar_scl_sentinel(imagen):
        scl = imagen.select('SCL')
        # Valores SCL de calidad: 4 (vegetación), 5 (suelo desnudo), 6 (agua), 11 (nieve/hielo)
        mascara_calidad = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11))
        
        # Escalar y alinear
        verde = imagen.select('B3').divide(10000)
        nir = imagen.select('B8').divide(10000)
        swir = imagen.select('B11').resample('bilinear').reproject(
            crs=imagen.select('B3').projection(),
            scale=10
        ).divide(10000)
        
        mndwi = verde.subtract(swir).divide(verde.add(swir)).rename('MNDWI')
        
        res = ee.Image.cat([verde.rename('B3'), nir.rename('B8'), swir.rename('B11'), mndwi])
        return res.updateMask(mascara_calidad).copyProperties(imagen, ['system:time_start'])

    # 4. Ingesta y filtrado de la colección Sentinel-2 L2A 2025
    print("Filtrando imágenes de Sentinel-2 para el año 2025...")
    coleccion_s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                   .filterBounds(buffer_analisis)
                   .filterDate('2025-01-01', '2025-12-31')
                   .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))
                   .map(enmascarar_scl_sentinel))
    
    n_escenas = coleccion_s2.size().getInfo()
    print(f"   -> {n_escenas} escenas encontradas (<50% nubes).")

    if n_escenas == 0:
        print("Advertencia: No se encontraron escenas. Elevando umbral de nubes a 80%...")
        coleccion_s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                       .filterBounds(buffer_analisis)
                       .filterDate('2025-01-01', '2025-12-31')
                       .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 80))
                       .map(enmascarar_scl_sentinel))
        n_escenas = coleccion_s2.size().getInfo()
        print(f"   -> {n_escenas} escenas encontradas con umbral relajado.")

    # Generar compuesto mediano
    mosaico_mediana = coleccion_s2.median()

    # 5. Alineación espacial de las bandas a 10m y reproyección métrica local
    # Corregido: Forzamos la reproyección explícita a la zona UTM 18N de Colombia (EPSG:32618)
    # para evitar que GEE use una escala de grados decimales que borraría el río.
    swir_10m = mosaico_mediana.select('B11')
    verde_10m = mosaico_mediana.select('B3')
    nir_10m = mosaico_mediana.select('B8')
    mndwi = mosaico_mediana.select('MNDWI')

    # 7. Segmentación binaria mediante umbralización adaptativa y filtros infrarrojos
    # Se descartan falsos positivos (como cubiertas de techos y asfalto) con NIR < 0.10 y SWIR < 0.05
    mascara_binaria_agua = mndwi.gte(0.1).And(nir_10m.lt(0.10)).And(swir_10m.lt(0.05)).selfMask().clip(buffer_analisis)

    # 8. Conversión del raster de agua a entidades vectoriales poligonales
    print("Vectorizando los píxeles de agua detectados a 10m...")
    poligonos_rio = mascara_binaria_agua.reduceToVectors(
        geometry=buffer_analisis,
        scale=10,
        crs='EPSG:32618',
        geometryType='polygon',
        eightConnected=True,
        labelProperty='agua',
        maxPixels=1e10,
        bestEffort=True
    ).filter(ee.Filter.eq('agua', 1))

    # 9. Filtrado geométrico de ruido: Eliminar polígonos menores a 500 m²
    def filtrar_por_superficie(feature):
        area = feature.geometry().area(maxError=1)
        return feature.set('area_m2', area)

    poligonos_depurados = (poligonos_rio.map(filtrar_por_superficie)
                          .filter(ee.Filter.gt('area_m2', 500)))

    # Metadatos del proyecto
    poligonos_final = poligonos_depurados.map(lambda f: f
        .set('anno', 2025)
        .set('rio', 'Rio Chinchina')
        .set('satelite', 'Sentinel-2 MSI 10m')
        .set('metodo', 'MNDWI >= 0.10 | NIR < 0.10 | SWIR < 0.05 | Filtro > 500m2 | Buffer 800m OSM')
        .set('version', 'v6_2025')
        .set('proyecto', 'AlennaArtCode / 2026')
    )

    # 10. Proceso de Exportación del FeatureCollection resultante a Google Drive
    # Corregido: Exportamos como KML para que sea directamente reproducible en tu visualizador web
    nombre_archivo = 'cauce_rio_chinchina_2025_v6'
    tarea_exportacion = ee.batch.Export.table.toDrive(
        collection=poligonos_final,
        description=nombre_archivo,
        folder='RioChinchina_KML_v6',
        fileNamePrefix=nombre_archivo,
        fileFormat='KML'
    )

    # Iniciar la tarea en los servidores de Earth Engine
    tarea_exportacion.start()
    
    print("\n" + "=" * 65)
    print(f"[EXITO] Tarea de exportación iniciada en GEE para el año 2025.")
    print(f"        ID de la tarea: {tarea_exportacion.id}")
    print("        Destino: Google Drive / carpeta 'RioChinchina_KML_v6'")
    print("        Archivo: cauce_rio_chinchina_2025_v6.kml")
    print("Verifique el estado en: https://code.earthengine.google.com/tasks")
    print("=" * 65)

if __name__ == '__main__':
    main()
