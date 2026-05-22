import ee, json

ee.Initialize(project='ee-fernando1quim')

with open('chinchina_osm.geojson', encoding='utf-8') as f:
    gj = json.load(f)

rio_union = ee.Geometry.MultiLineString(
    [feat['geometry']['coordinates'] for feat in gj['features']
     if len(feat['geometry']['coordinates']) >= 2]
)
aoi = rio_union.buffer(800)

def mask_l7(img):
    qa = img.select('QA_PIXEL')
    # Bit 3: Cloud, Bit 4: Cloud Shadow
    mask = qa.bitwiseAnd(1<<3).eq(0).And(qa.bitwiseAnd(1<<4).eq(0))
    return img.updateMask(mask).multiply(0.0000275).add(-0.2).copyProperties(img, ['system:time_start'])

col7 = (ee.ImageCollection('LANDSAT/LE07/C02/T1_L2')
        .filterBounds(aoi)
        .filterDate('2011-01-01', '2013-12-31')
        .filter(ee.Filter.lt('CLOUD_COVER', 70))
        .map(mask_l7))

print("Landsat 7 Scenes:", col7.size().getInfo())

comp = col7.median()
mndwi = comp.normalizedDifference(['SR_B2', 'SR_B5']).rename('MNDWI') # L7: B2 is Green, B5 is SWIR1
mndwi_clipped = mndwi.clip(aoi)

stats = mndwi_clipped.reduceRegion(
    reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), "", True),
    geometry=aoi,
    scale=30,
    maxPixels=1e10
).getInfo()
print("L7 MNDWI stats:", stats)

for th in [-0.2, -0.15, -0.1, -0.05, 0.0, 0.05]:
    cnt = mndwi_clipped.gte(th).selfMask().reduceToVectors(
        geometry=aoi, scale=30, geometryType='polygon',
        eightConnected=True, labelProperty='agua',
        maxPixels=1e10, bestEffort=True
    ).filter(ee.Filter.eq('agua', 1)).size().getInfo()
    print(f"  L7 MNDWI >= {th} Count: {cnt}")
