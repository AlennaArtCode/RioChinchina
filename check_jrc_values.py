import ee, json

ee.Initialize(project='ee-fernando1quim')

with open('chinchina_osm.geojson', encoding='utf-8') as f:
    gj = json.load(f)

rio_union = ee.Geometry.MultiLineString(
    [feat['geometry']['coordinates'] for feat in gj['features']
     if len(feat['geometry']['coordinates']) >= 2]
)
aoi = rio_union.buffer(800)

jrc_occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select('occurrence').clip(aoi)

# Get stats of occurrence in aoi
stats = jrc_occ.reduceRegion(
    reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), "", True),
    geometry=aoi,
    scale=30,
    maxPixels=1e10
).getInfo()

print("JRC Occurrence stats in AOI:", stats)

# Check counts for different thresholds of JRC
for th in [5, 10, 20, 30, 50, 80]:
    try:
        cnt = jrc_occ.gte(th).selfMask().reduceToVectors(
            geometry=aoi, scale=30, geometryType='polygon',
            eightConnected=True, labelProperty='agua',
            maxPixels=1e10, bestEffort=True
        ).filter(ee.Filter.eq('agua', 1)).size().getInfo()
        print(f"JRC >= {th}% Count: {cnt}")
    except Exception as e:
        print(f"Error for th={th}: {e}")
