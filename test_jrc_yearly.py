import ee, json

ee.Initialize(project='ee-fernando1quim')

with open('chinchina_osm.geojson', encoding='utf-8') as f:
    gj = json.load(f)

rio_union = ee.Geometry.MultiLineString(
    [feat['geometry']['coordinates'] for feat in gj['features']
     if len(feat['geometry']['coordinates']) >= 2]
)
aoi = rio_union.buffer(800)

jrc_coll = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")

for anno in [2006, 2012]:
    img_jrc = (jrc_coll
               .filterBounds(aoi)
               .filter(ee.Filter.eq('year', anno))
               .first()) # Unclipped first
    
    # Class 2: seasonal water, Class 3: permanent water
    # Let's count features for class >= 2
    agua = img_jrc.select('waterClass').gte(2).selfMask()
    # Clip after
    agua_clipped = agua.clip(aoi)
    
    cnt = agua_clipped.reduceToVectors(
        geometry=aoi, scale=30, geometryType='polygon',
        eightConnected=True, labelProperty='waterClass',
        maxPixels=1e10, bestEffort=True
    ).filter(ee.Filter.eq('waterClass', 1)).size().getInfo()
    print(f"JRC Yearly {anno} - waterClass >= 2 Count:", cnt)
    
    # Also check count for waterClass == 3 (permanent only)
    agua_perm = img_jrc.select('waterClass').eq(3).selfMask().clip(aoi)
    cnt_perm = agua_perm.reduceToVectors(
        geometry=aoi, scale=30, geometryType='polygon',
        eightConnected=True, labelProperty='waterClass',
        maxPixels=1e10, bestEffort=True
    ).filter(ee.Filter.eq('waterClass', 1)).size().getInfo()
    print(f"  Permanent waterClass == 3 Count:", cnt_perm)
