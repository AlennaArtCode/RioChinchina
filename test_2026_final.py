import ee, json

ee.Initialize(project='ee-fernando1quim')

with open('chinchina_osm.geojson', encoding='utf-8') as f:
    gj = json.load(f)

rio_union = ee.Geometry.MultiLineString(
    [feat['geometry']['coordinates'] for feat in gj['features']
     if len(feat['geometry']['coordinates']) >= 2]
)
aoi = rio_union.buffer(800)

def mask_s2(img):
    scl = img.select('SCL')
    mask = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11))
    spectral_bands = img.select(['B3', 'B11'])
    scaled = spectral_bands.divide(10000)
    return scaled.updateMask(mask).copyProperties(img, ['system:time_start'])

col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi)
       .filterDate('2024-06-01', '2026-05-22')
       .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50)) # 2026 might have less scenes, let's check
       .map(mask_s2))

print("2026 scenes count:", col.size().getInfo())

comp = col.median()
swir = comp.select('B11').resample('bilinear').reproject(crs='EPSG:32618', scale=10)
verde = comp.select('B3')

mndwi = verde.subtract(swir).divide(verde.add(swir)).rename('MNDWI')
mndwi_clipped = mndwi.clip(aoi)

stats = mndwi_clipped.reduceRegion(
    reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), "", True),
    geometry=aoi,
    scale=10,
    maxPixels=1e10
).getInfo()
print("2026 MNDWI stats:", stats)

for th in [0.0, 0.05, 0.1]:
    cnt = mndwi_clipped.gte(th).selfMask().reduceToVectors(
        geometry=aoi, scale=10, geometryType='polygon',
        eightConnected=True, labelProperty='agua',
        maxPixels=1e10, bestEffort=True
    ).filter(ee.Filter.eq('agua', 1)).size().getInfo()
    print(f"  2026 MNDWI >= {th} Count: {cnt}")
