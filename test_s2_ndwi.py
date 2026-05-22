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
    return img.updateMask(mask).divide(10000).copyProperties(img, ['system:time_start'])

col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi)
       .filterDate('2017-06-01', '2019-06-30')
       .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 80))
       .map(mask_s2))
comp = col.median().clip(aoi)
verde = comp.select('B3')  # Green (10m)
nir = comp.select('B8')    # NIR (10m)
ndwi = verde.subtract(nir).divide(verde.add(nir)).rename('NDWI')

stats = ndwi.reduceRegion(
    reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), "", True),
    geometry=aoi,
    scale=10,
    maxPixels=1e10
).getInfo()
print("NDWI stats in AOI:", stats)

for th in [-0.2, -0.1, 0.0, 0.05, 0.1, 0.2]:
    cnt = ndwi.gte(th).selfMask().reduceToVectors(
        geometry=aoi, scale=10, geometryType='polygon',
        eightConnected=True, labelProperty='agua',
        maxPixels=1e10, bestEffort=True
    ).filter(ee.Filter.eq('agua', 1)).size().getInfo()
    print(f"  NDWI >= {th} Count: {cnt}")
