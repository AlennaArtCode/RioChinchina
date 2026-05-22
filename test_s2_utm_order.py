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
    # DO NOT divide the whole image by 10000 here to avoid scaling SCL or other issues
    # Just scale the bands we need when we need them, or divide just the spectral bands
    # Let's select only the bands we need and divide them
    spectral_bands = img.select(['B3', 'B11'])
    scaled = spectral_bands.divide(10000)
    return scaled.updateMask(mask).copyProperties(img, ['system:time_start'])

col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi)
       .filterDate('2017-06-01', '2019-06-30')
       .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 80)) # Use 80% to be sure we have data
       .map(mask_s2))

print("S2 collection size:", col.size().getInfo())

comp = col.median()
# Reproject SWIR BEFORE clipping
swir = comp.select('B11').resample('bilinear').reproject(crs='EPSG:32618', scale=10)
verde = comp.select('B3')

mndwi = verde.subtract(swir).divide(verde.add(swir)).rename('MNDWI')
# Clip MNDWI to AOI AFTER computing
mndwi_clipped = mndwi.clip(aoi)

stats = mndwi_clipped.reduceRegion(
    reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), "", True),
    geometry=aoi,
    scale=10,
    maxPixels=1e10
).getInfo()
print("MNDWI stats with correct reprojection order:", stats)

for th in [0.0, 0.05, 0.1]:
    cnt = mndwi_clipped.gte(th).selfMask().reduceToVectors(
        geometry=aoi, scale=10, geometryType='polygon',
        eightConnected=True, labelProperty='agua',
        maxPixels=1e10, bestEffort=True
    ).filter(ee.Filter.eq('agua', 1)).size().getInfo()
    print(f"  MNDWI >= {th} Count: {cnt}")
