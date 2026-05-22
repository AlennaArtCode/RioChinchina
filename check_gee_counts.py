import ee, json, sys

ee.Initialize(project='ee-fernando1quim')

with open('chinchina_osm.geojson', encoding='utf-8') as f:
    gj = json.load(f)

rio_union = ee.Geometry.MultiLineString(
    [feat['geometry']['coordinates'] for feat in gj['features']
     if len(feat['geometry']['coordinates']) >= 2]
)

aoi = rio_union.buffer(800)

print("Checking JRC 2006:")
jrc_occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select('occurrence').clip(aoi)
agua = jrc_occ.gte(30).selfMask()
cauce = agua.reduceToVectors(
    geometry=aoi, scale=30, geometryType='polygon',
    eightConnected=True, labelProperty='agua',
    maxPixels=1e10, bestEffort=True,
).filter(ee.Filter.eq('agua', 1))
print("JRC 2006 Count:", cauce.size().getInfo())

print("Checking Sentinel-2 2018:")
def mask_s2(img):
    scl = img.select('SCL')
    mask = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11))
    return img.updateMask(mask).divide(10000).copyProperties(img, ['system:time_start'])

col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
       .filterBounds(aoi).filterDate('2017-06-01', '2019-06-30')
       .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
       .map(mask_s2))
print("S2 Scenes count:", col.size().getInfo())
comp  = col.median().clip(aoi)
verde = comp.select('B3')
swir  = comp.select('B11').resample('bilinear').reproject(
    crs=comp.select('B3').projection(), scale=10)
mndwi = verde.subtract(swir).divide(verde.add(swir)).rename('MNDWI')
agua_s2 = mndwi.gte(0.05).selfMask()
cauce_s2 = agua_s2.reduceToVectors(
    geometry=aoi, scale=10, geometryType='polygon',
    eightConnected=True, labelProperty='agua',
    maxPixels=1e10, bestEffort=True,
).filter(ee.Filter.eq('agua', 1))
print("S2 2018 Count:", cauce_s2.size().getInfo())
