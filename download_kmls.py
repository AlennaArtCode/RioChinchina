import ee
import json
import urllib.request
import os

GEE_PROJECT = 'ee-fernando1quim'

def main():
    print("=" * 65)
    print("  RÍO CHINCHINÁ — Descarga de Capas KML desde Earth Engine")
    print("=" * 65)
    
    try:
        ee.Initialize(project=GEE_PROJECT)
        print("[OK] GEE Inicializado con éxito.")
    except Exception as e:
        print("La inicialización de GEE falló. Asegúrese de estar autenticado.")
        raise e

    # Cargar GeoJSON de OSM
    try:
        with open('chinchina_osm.geojson', encoding='utf-8') as f:
            gj = json.load(f)
        print(f"[OK] GeoJSON cargado con {len(gj['features'])} segmentos.")
    except Exception as e:
        print("Error al abrir chinchina_osm.geojson. Asegúrese de que existe.")
        raise e

    rio_union = ee.Geometry.MultiLineString(
        [feat['geometry']['coordinates'] for feat in gj['features']
         if len(feat['geometry']['coordinates']) >= 2]
    )

    aoi = rio_union.buffer(800)
    print("[OK] Corredor de análisis de 800m creado.")

    os.makedirs('RioChinchina_KML_v6', exist_ok=True)

    # 1. Años JRC (2006, 2012)
    jrc_coll = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")
    sat_map = {2006: 'Landsat 5 TM (JRC Yearly)', 2012: 'Landsat 7 ETM+ (JRC Yearly)'}
    
    for anno in [2006, 2012]:
        print(f"\nProcesando JRC {anno}...")
        img_jrc = jrc_coll.filterBounds(aoi).filter(ee.Filter.eq('year', anno)).first()
        agua = img_jrc.select('waterClass').gte(2).selfMask()
        agua_clipped = agua.clip(aoi)
        
        cauce = agua_clipped.reduceToVectors(
            geometry=aoi, scale=30, geometryType='polygon',
            eightConnected=True, labelProperty='agua',
            maxPixels=1e10, bestEffort=True,
        ).filter(ee.Filter.eq('agua', 1))
        
        cauce_attr = cauce.map(lambda f: f
            .set('anno', anno).set('rio', 'Rio Chinchina')
            .set('satelite', sat_map[anno])
            .set('metodo', 'JRC Yearly History waterClass >= 2 | buffer 800m OSM')
            .set('version', 'v6').set('proyecto', 'AlennaArtCode / 2026')
        )
        
        filename = f'cauce_rio_chinchina_{anno}_v6.kml'
        filepath = os.path.join('RioChinchina_KML_v6', filename)
        
        try:
            url = cauce_attr.getDownloadURL(filetype='kml', filename=f'cauce_rio_chinchina_{anno}_v6')
            print(f"   Descargando {filename}...")
            response = urllib.request.urlopen(url)
            kml_data = response.read()
            with open(filepath, 'wb') as out_f:
                out_f.write(kml_data)
            print(f"   [OK] Guardado: {filepath} ({len(kml_data)} bytes)")
        except Exception as e:
            print(f"   [ERROR] Error al descargar {anno}: {e}")

    # 2. Años Sentinel-2 (2018, 2025, 2026)
    # NOTA: NO se aplica máscara SCL por píxel.
    # En el Chinchiná andino, el agua es frecuentemente clasificada como
    # SCL=3 (sombra de nube) por el bajo albedo del río. Cualquier máscara
    # SCL elimina el cauce. La mediana sobre muchas escenas es robusta a
    # nubes sin necesidad de máscara explícita.

    s2_configs = [
        (2018, '2017-06-01', '2019-06-30', 0.05, 0.15, 0.10),
        (2025, '2025-01-01', '2025-12-31', 0.05, 0.15, 0.10),
        (2026, '2024-06-01', '2026-05-22', 0.05, 0.15, 0.10)
    ]

    for anno, f_ini, f_fin, mndwi_th, nir_max, swir_max in s2_configs:
        print(f"\nProcesando Sentinel-2 {anno}...")
        
        # Sin máscara SCL — mediana robusta a nubes naturalmente
        col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
               .filterBounds(aoi).filterDate(f_ini, f_fin)
               .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 80))
               .select(['B3', 'B8', 'B11']))
        
        n = col.size().getInfo()
        print(f"   Encontradas {n} escenas (<80% nubes).")
        if n == 0:
            print(f"   [ERROR] Sin escenas para {anno}. Omitiendo.")
            continue
            
        comp = col.median()
        verde = comp.select('B3').divide(10000)
        nir   = comp.select('B8').divide(10000)
        swir  = comp.select('B11').divide(10000)  # 20m nativo
        mndwi = verde.subtract(swir).divide(verde.add(swir))
        
        # Filtros espectrales calibrados (agua turbia de montaña)
        agua = (mndwi.gte(mndwi_th)
                .And(nir.lt(nir_max))
                .And(swir.lt(swir_max))
                .selfMask().clip(aoi))
        
        # Vectorizar a 20m en EPSG:32618 (escala nativa de B11/SWIR)
        # IMPORTANTE: usar 'EPSG:32618' explícito, NO comp.select('B3').projection()
        # (col.median().projection() devuelve EPSG:4326 a 1 grado = 1100km/px)
        cauce = agua.reduceToVectors(
            geometry=aoi, scale=20, crs='EPSG:32618',
            geometryType='polygon', eightConnected=True,
            labelProperty='agua', maxPixels=1e10, bestEffort=True,
        ).filter(ee.Filter.eq('agua', 1))

        # Filtro de área mínima (400 m² = 1 píxel a 20m)
        def set_area(f):
            return f.set('area_m2', f.geometry().area(maxError=1))
        cauce = cauce.map(set_area).filter(ee.Filter.gt('area_m2', 400))

        n_polys = cauce.size().getInfo()
        print(f"   Polígonos detectados: {n_polys}")
            
        cauce_attr = cauce.map(lambda f: f
            .set('anno', anno).set('rio', 'Rio Chinchina')
            .set('satelite', 'Sentinel-2 MSI 20m')
            .set('metodo', f'Mediana-sin-SCL|MNDWI>={mndwi_th}|NIR<{nir_max}|SWIR<{swir_max}|20m|EPSG:32618')
            .set('version', 'v10').set('proyecto', 'AlennaArtCode / 2026')
        )
        
        filename = f'cauce_rio_chinchina_{anno}_v6.kml'
        filepath = os.path.join('RioChinchina_KML_v6', filename)
        
        try:
            url = cauce_attr.getDownloadURL(filetype='kml', filename=f'cauce_rio_chinchina_{anno}_v6')
            print(f"   Descargando {filename}...")
            response = urllib.request.urlopen(url, timeout=180)
            kml_data = response.read()
            with open(filepath, 'wb') as out_f:
                out_f.write(kml_data)
            print(f"   [OK] Guardado: {filepath} ({len(kml_data):,} bytes | {n_polys} polígonos)")
        except Exception as e:
            print(f"   [ERROR] Error al descargar {anno}: {e}")

    print("\n" + "=" * 65)
    print("  DESCARGA COMPLETADA CON ÉXITO")
    print("  Todas las capas KML están guardadas en la carpeta 'RioChinchina_KML_v6'.")
    print("=" * 65)

if __name__ == '__main__':
    main()
