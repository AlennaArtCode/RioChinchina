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
               .first())
    
    # Calculate histogram in AOI
    hist = img_jrc.select('waterClass').reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=aoi,
        scale=30,
        maxPixels=1e10
    ).getInfo()
    print(f"Year {anno} waterClass histogram:", hist)
