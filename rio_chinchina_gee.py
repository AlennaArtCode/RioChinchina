"""
=============================================================================
  RÍO CHINCHINÁ — SCRIPT v5 DEFINITIVO
  Usa coordenadas EXACTAS de OSM (2.884 nodos del río real)
  Buffer estrecho de 800m + JRC/Sentinel-2
=============================================================================
"""
import ee, sys, io, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

GEE_PROJECT = 'ee-fernando1quim'

def main():
    print("=" * 65)
    print("  RIO CHINCHINA v5 — Coordenadas OSM exactas")
    print("  2.884 nodos reales | Buffer 800m | JRC + S2")
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

    # Convertir cada segmento a ee.Geometry.LineString y unir
    geo_lines = []
    for feat in gj['features']:
        coords = feat['geometry']['coordinates']
        if len(coords) >= 2:
            geo_lines.append(ee.Geometry.LineString(coords))

    # Unir todas las líneas en una sola geometría
    rio_union = ee.Geometry.MultiLineString(
        [feat['geometry']['coordinates'] for feat in gj['features']
         if len(feat['geometry']['coordinates']) >= 2]
    )

    # Buffer estrecho: 800m a cada lado del cauce real
    aoi = rio_union.buffer(800)
    print("[OK] Corredor creado: 800m buffer sobre coordenadas OSM exactas")
    print("     (mucho más preciso que los waypoints manuales de versiones anteriores)")

    # ── JRC Water Occurrence para 2006 y 2012 ───────────────────────────
    # occurrence >= 30%: agua presente al menos 30% del tiempo histórico
    # (bajamos el umbral porque el río es estrecho y puede ser estacional)
    jrc_occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select('occurrence').clip(aoi)

    for anno, umbral in [(2006, 30), (2012, 30)]:
        print(f"\n{'─'*60}")
        print(f"[{anno}] JRC Water Occurrence >= {umbral}%")

        agua = jrc_occ.gte(umbral).selfMask()

        cauce = agua.reduceToVectors(
            geometry=aoi, scale=30, geometryType='polygon',
            eightConnected=True, labelProperty='agua',
            maxPixels=1e10, bestEffort=True,
        ).filter(ee.Filter.eq('agua', 1))

        sat_map = {2006: 'Landsat 5 TM (JRC OSM)', 2012: 'Landsat 7 ETM+ (JRC OSM)'}
        cauce_attr = cauce.map(lambda f: f
            .set('anno', anno).set('rio', 'Rio Chinchina')
            .set('satelite', sat_map[anno])
            .set('metodo', f'JRC Occurrence>={umbral}% | buffer 800m OSM')
            .set('version', 'v5').set('proyecto', 'AlennaArtCode / 2026')
        )

        nombre = f'cauce_rio_chinchina_{anno}_v5'
        t = ee.batch.Export.table.toDrive(
            collection=cauce_attr, description=nombre,
            folder='RioChinchina_KML_v5', fileNamePrefix=nombre, fileFormat='KML',
        )
        t.start()
        print(f"   [OK] ID: {t.id}")

    # ── Sentinel-2 (10m) para 2018 y 2026 ───────────────────────────────
    def mask_s2(img):
        scl = img.select('SCL')
        mask = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11))
        return img.updateMask(mask).divide(10000).copyProperties(img, ['system:time_start'])

    for anno, f_ini, f_fin in [
        (2018, '2017-06-01', '2019-06-30'),
        (2026, '2024-06-01', '2026-05-22'),
    ]:
        print(f"\n{'─'*60}")
        print(f"[{anno}] Sentinel-2 MSI 10m | buffer OSM 800m")

        col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
               .filterBounds(aoi).filterDate(f_ini, f_fin)
               .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
               .map(mask_s2))
        n = col.size().getInfo()
        print(f"   -> {n} escenas (<20% nubes)")

        if n < 3:
            col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                   .filterBounds(aoi).filterDate(f_ini, f_fin)
                   .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50)).map(mask_s2))
            n = col.size().getInfo()
            print(f"   -> {n} escenas (<50% nubes)")

        comp  = col.median().clip(aoi)
        verde = comp.select('B3')
        swir  = comp.select('B11').resample('bilinear').reproject(
            crs=comp.select('B3').projection(), scale=10)
        mndwi = verde.subtract(swir).divide(verde.add(swir)).rename('MNDWI')
        agua  = mndwi.gte(0.05).selfMask()  # umbral más suave en 10m

        cauce = agua.reduceToVectors(
            geometry=aoi, scale=10, geometryType='polygon',
            eightConnected=True, labelProperty='agua',
            maxPixels=1e10, bestEffort=True,
        ).filter(ee.Filter.eq('agua', 1))

        cauce_attr = cauce.map(lambda f: f
            .set('anno', anno).set('rio', 'Rio Chinchina')
            .set('satelite', 'Sentinel-2 MSI 10m')
            .set('metodo', 'MNDWI>0.05 | buffer 800m OSM | 10m')
            .set('version', 'v5').set('proyecto', 'AlennaArtCode / 2026')
        )

        nombre = f'cauce_rio_chinchina_{anno}_v5'
        t = ee.batch.Export.table.toDrive(
            collection=cauce_attr, description=nombre,
            folder='RioChinchina_KML_v5', fileNamePrefix=nombre, fileFormat='KML',
        )
        t.start()
        print(f"   [OK] ID: {t.id}")

    print(f"\n{'='*65}")
    print("RESUMEN → Google Drive / RioChinchina_KML_v5/")
    print("  2006 + 2012: JRC Occurrence >= 30% | buffer OSM 800m")
    print("  2018 + 2026: Sentinel-2 10m | buffer OSM 800m")
    print("Monitorea: https://code.earthengine.google.com/tasks")
    print("=" * 65)

if __name__ == '__main__':
    main()
