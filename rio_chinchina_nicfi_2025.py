"""
=============================================================================
  RÍO CHINCHINÁ — Extracción de Alta Resolución con Planet NICFI (2025)
  Resolución espacial: 4.77 metros por píxel
  
  MÉTODO:
  - Carga el trazado detallado de OSM (2.884 nodos)
  - Buffer de 600m para absorber desplazamientos y evitar el Río Cauca
  - Mosaico mediano Planet NICFI 2025
  - NDWI Planet nativo: (G - N) / (G + N)
  - Filtro NIR absoluto para evitar falsos positivos
  - Vectorización nativa a 4.77m en EPSG:32618 (UTM Zone 18N)
=============================================================================
"""
import ee
import json
import os
import urllib.request
import sys
import io

# Asegurar codificación utf-8 en consola de Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

GEE_PROJECT = 'ee-fernando1quim'
NDWI_UMBRAL = 0.12        # Umbral NDWI para agua en Planet NICFI
NIR_MAXIMO = 1500         # Reflectancia NIR máxima (escala 0-10000)
AREA_MINIMA = 200         # Área mínima del polígono en m² (aprox 9 px a 4.77m)
BUFFER_AOI = 600          # Buffer desde la línea del río

def main():
    print("=" * 75)
    print("  RÍO CHINCHINÁ — Procesamiento de Alta Resolución Planet NICFI (2025)")
    print("=" * 75)

    # Inicializar Earth Engine
    try:
        ee.Initialize(project=GEE_PROJECT)
        print("[OK] GEE inicializado con éxito.")
    except Exception as e:
        print("La inicialización de GEE falló. Asegúrese de estar autenticado.")
        raise e

    # 1. Cargar trazado oficial de OSM
    try:
        with open('chinchina_osm.geojson', encoding='utf-8') as f:
            gj = json.load(f)
        print(f"[OK] GeoJSON de OSM cargado con {len(gj['features'])} segmentos.")
    except Exception as e:
        print("Error al abrir chinchina_osm.geojson.")
        raise e

    rio_union = ee.Geometry.MultiLineString(
        [feat['geometry']['coordinates'] for feat in gj['features']
         if len(feat['geometry']['coordinates']) >= 2]
    )
    aoi = rio_union.buffer(BUFFER_AOI)
    print(f"[OK] Corredor de análisis de {BUFFER_AOI}m creado.")

    # 2. Cargar colección Planet NICFI
    print("Cargando colección Planet NICFI...")
    nicfi = ee.ImageCollection('projects/planet-nicfi/assets/basemaps/americas')
    
    # Filtrar por fecha y generar mosaico mediano
    mosaico = (nicfi
               .filterBounds(aoi)
               .filterDate('2025-01-01', '2025-12-31')
               .median()
               .clip(aoi))
               
    # 3. Extraer bandas y calcular NDWI estándar
    # Bandas NICFI: R (Rojo), G (Verde), B (Azul), N (NIR)
    band_g = mosaico.select('G')
    band_n = mosaico.select('N')
    
    ndwi = (band_g.subtract(band_n)
            .divide(band_g.add(band_n))
            .rename('NDWI'))
            
    # 4. Clasificación y filtros espectrales
    # Agua tiene alto NDWI y muy baja reflectancia en el Infrarrojo Cercano (N)
    mascara_agua = ndwi.gte(NDWI_UMBRAL).And(band_n.lt(NIR_MAXIMO))
    agua_final = mascara_agua.selfMask()
    
    # 5. Vectorización a resolución nativa de 4.77m en UTM 18N
    print("Vectorizando cauce a escala nativa de 4.77m...")
    poligonos = agua_final.reduceToVectors(
        geometry=aoi,
        scale=4.77,
        crs='EPSG:32618',
        geometryType='polygon',
        eightConnected=True,
        labelProperty='agua',
        maxPixels=1e10,
        bestEffort=True
    ).filter(ee.Filter.eq('agua', 1))

    # 6. Filtrar por superficie mínima para remover pequeñas sombras
    def calcular_area(f):
        return f.set('area_m2', f.geometry().area(maxError=1))
        
    cauce_filtrado = (poligonos
                      .map(calcular_area)
                      .filter(ee.Filter.gt('area_m2', AREA_MINIMA)))

    n_polys = cauce_filtrado.size().getInfo()
    print(f"Polígonos detectados (> {AREA_MINIMA} m²): {n_polys}")

    if n_polys == 0:
        print("[ADVERTENCIA] No se detectaron polígonos. Verifique si su cuenta tiene acceso a Planet NICFI.")
        return

    # Añadir metadatos
    metodo_str = f'Planet-NICFI-4.77m|NDWI>={NDWI_UMBRAL}|NIR<{NIR_MAXIMO}|area>{AREA_MINIMA}m2|buffer{BUFFER_AOI}m'
    cauce_final = cauce_filtrado.map(lambda f: f
        .set('anno', 2025)
        .set('rio', 'Rio Chinchina')
        .set('satelite', 'Planet NICFI 4.77m')
        .set('metodo', metodo_str)
        .set('version', 'v6_nicfi')
        .set('proyecto', 'AlennaArtCode / 2026')
    )

    # 7. Descargar KML
    os.makedirs('RioChinchina_KML_v6', exist_ok=True)
    filename = 'cauce_rio_chinchina_2025_nicfi_v6.kml'
    filepath = os.path.join('RioChinchina_KML_v6', filename)

    try:
        url = cauce_final.getDownloadURL(
            filetype='kml',
            filename='cauce_rio_chinchina_2025_nicfi_v6'
        )
        print(f"Descargando {filename}...")
        response = urllib.request.urlopen(url, timeout=120)
        kml_data = response.read()
        with open(filepath, 'wb') as out_f:
            out_f.write(kml_data)
        size_kb = len(kml_data) / 1024
        print(f"[OK] Guardado: {filepath} ({size_kb:.1f} KB | {n_polys} polígonos)")
    except Exception as e:
        print(f"[ERROR] La descarga falló: {e}")
        print("Lanzando tarea de exportación a Google Drive...")
        tarea = ee.batch.Export.table.toDrive(
            collection=cauce_final,
            description='cauce_rio_chinchina_2025_nicfi_v6',
            folder='RioChinchina_KML_v6',
            fileNamePrefix='cauce_rio_chinchina_2025_nicfi_v6',
            fileFormat='KML'
        )
        tarea.start()
        print(f"[DRIVE] Tarea iniciada: {tarea.id}")

if __name__ == '__main__':
    main()
