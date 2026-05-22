"""
=============================================================================
  RÍO CHINCHINÁ — SCRIPT v6 DEFINITIVO
  Usa coordenadas EXACTAS de OSM (2.884 nodos del río real)
  Buffer estrecho de 800m
  2006 / 2012: JRC Yearly History (waterClass >= 2) sin clipping prematuro
  2018 / 2026: Sentinel-2 10m (MNDWI >= 0.05) con reproyección UTM y orden correcto
=============================================================================
"""
import ee, sys, io, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

GEE_PROJECT = 'ee-fernando1quim'

def main():
    print("=" * 65)
    print("  RIO CHINCHINA v6 — GEE Script Corrección Proyección y JRC")
    print("  2.884 nodos reales | Buffer 800m | JRC Yearly + S2 UTM")
    print("=" * 65)

    try:
        ee.Initialize(project=GEE_PROJECT)
        print("[OK] GEE inicializado")
    except Exception:
        ee.Authenticate(auth_mode='localhost')
        ee.Initialize(project=GEE_PROJECT)

    # ── Cargar GeoJSON descargado de OSM ─────────────────────────────────
    with open('chinchina_osm.geojson', encoding='utf-8') as f:
        gj = json.load(f)

    print(f"[OK] GeoJSON cargado: {len(gj['features'])} segmentos OSM")

    # Unir todas las líneas en una sola geometría
    rio_union = ee.Geometry.MultiLineString(
        [feat['geometry']['coordinates'] for feat in gj['features']
         if len(feat['geometry']['coordinates']) >= 2]
    )

    # Buffer estrecho: 800m a cada lado del cauce real
    aoi = rio_union.buffer(800)
    print("[OK] Corredor creado: 800m buffer sobre coordenadas OSM exactas")

    # ── JRC Yearly History para 2006 y 2012 ───────────────────────────
    jrc_coll = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")

    for anno in [2006, 2012]:
        print(f"\n{'─'*60}")
        print(f"[{anno}] JRC Yearly History | waterClass >= 2 (Seasonal/Permanent)")

        img_jrc = jrc_coll.filterBounds(aoi).filter(ee.Filter.eq('year', anno)).first()
        
        # waterClass >= 2: seasonal (2) y permanent (3)
        agua = img_jrc.select('waterClass').gte(2).selfMask()
        
        # Clip a la AOI después de computar para evitar problemas de proyección
        agua_clipped = agua.clip(aoi)

        cauce = agua_clipped.reduceToVectors(
            geometry=aoi, scale=30, geometryType='polygon',
            eightConnected=True, labelProperty='agua',
            maxPixels=1e10, bestEffort=True,
        ).filter(ee.Filter.eq('agua', 1))

        sat_map = {2006: 'Landsat 5 TM (JRC Yearly)', 2012: 'Landsat 7 ETM+ (JRC Yearly)'}
        cauce_attr = cauce.map(lambda f: f
            .set('anno', anno).set('rio', 'Rio Chinchina')
            .set('satelite', sat_map[anno])
            .set('metodo', 'JRC Yearly History waterClass >= 2 | buffer 800m OSM')
            .set('version', 'v6').set('proyecto', 'AlennaArtCode / 2026')
        )

        nombre = f'cauce_rio_chinchina_{anno}_v6'
        t = ee.batch.Export.table.toDrive(
            collection=cauce_attr, description=nombre,
            folder='RioChinchina_KML_v6', fileNamePrefix=nombre, fileFormat='KML',
        )
        t.start()
        print(f"   [OK] Tarea de exportación iniciada para {anno}. ID: {t.id}")

    # ── Sentinel-2 (10m) para 2018 y 2026 ───────────────────────────────
    def mask_s2(img):
        scl = img.select('SCL')
        mask = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11))
        # Seleccionamos y dividimos solo las bandas espectrales para no alterar SCL ni metadatos
        spectral = img.select(['B3', 'B11'])
        scaled = spectral.divide(10000)
        return scaled.updateMask(mask).copyProperties(img, ['system:time_start'])

    for anno, f_ini, f_fin in [
        (2018, '2017-06-01', '2019-06-30'),
        (2026, '2024-06-01', '2026-05-22'),
    ]:
        print(f"\n{'─'*60}")
        print(f"[{anno}] Sentinel-2 MSI 10m | buffer OSM 800m")

        col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
               .filterBounds(aoi).filterDate(f_ini, f_fin)
               .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))
               .map(mask_s2))
        n = col.size().getInfo()
        print(f"   -> {n} escenas (<50% nubes)")

        if n < 5:
            col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                   .filterBounds(aoi).filterDate(f_ini, f_fin)
                   .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 80)).map(mask_s2))
            n = col.size().getInfo()
            print(f"   -> {n} escenas (<80% nubes)")

        comp  = col.median()
        # Reproyectamos SWIR (B11) a la zona UTM local (EPSG:32618, Zone 18N) a 10m ANTES de hacer clip
        swir  = comp.select('B11').resample('bilinear').reproject(crs='EPSG:32618', scale=10)
        verde = comp.select('B3')
        
        mndwi = verde.subtract(swir).divide(verde.add(swir)).rename('MNDWI')
        
        # Umbral 0.05 y clip a la AOI
        agua  = mndwi.gte(0.05).selfMask().clip(aoi)

        cauce = agua.reduceToVectors(
            geometry=aoi, scale=10, geometryType='polygon',
            eightConnected=True, labelProperty='agua',
            maxPixels=1e10, bestEffort=True,
        ).filter(ee.Filter.eq('agua', 1))

        cauce_attr = cauce.map(lambda f: f
            .set('anno', anno).set('rio', 'Rio Chinchina')
            .set('satelite', 'Sentinel-2 MSI 10m')
            .set('metodo', 'MNDWI >= 0.05 | buffer 800m OSM | 10m')
            .set('version', 'v6').set('proyecto', 'AlennaArtCode / 2026')
        )

        nombre = f'cauce_rio_chinchina_{anno}_v6'
        t = ee.batch.Export.table.toDrive(
            collection=cauce_attr, description=nombre,
            folder='RioChinchina_KML_v6', fileNamePrefix=nombre, fileFormat='KML',
        )
        t.start()
        print(f"   [OK] Tarea de exportación iniciada para {anno}. ID: {t.id}")

    print(f"\n{'='*65}")
    print("RESUMEN → Google Drive / RioChinchina_KML_v6/")
    print("  2006 + 2012: JRC Yearly History waterClass >= 2 | buffer OSM 800m")
    print("  2018 + 2026: Sentinel-2 10m | MNDWI >= 0.05 | buffer OSM 800m")
    print("Monitorea las tareas en: https://code.earthengine.google.com/tasks")
    print("=" * 65)

if __name__ == '__main__':
    main()
