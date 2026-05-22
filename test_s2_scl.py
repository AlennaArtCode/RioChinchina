import ee, json

ee.Initialize(project='ee-fernando1quim')

with open('chinchina_osm.geojson', encoding='utf-8') as f:
    gj = json.load(f)

rio_union = ee.Geometry.MultiLineString(
    [feat['geometry']['coordinates'] for feat in gj['features']
     if len(feat['geometry']['coordinates']) >= 2]
)
aoi = rio_union.buffer(800)

print("Checking Sentinel-2 SCL==6 (Water) pixels:")
for anno, f_ini, f_fin in [
    (2018, '2017-06-01', '2019-06-30'),
    (2026, '2024-06-01', '2026-05-22'),
]:
    col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
           .filterBounds(aoi)
           .filterDate(f_ini, f_fin)
           .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50)))
    
    # We want to see how many times SCL == 6 occurs in each pixel, or just the median SCL
    # SCL is a categorical band, so median might not make sense directly, but mode does!
    # Let's count how many pixels have mode SCL == 6
    scl_mode = col.select('SCL').reduce(ee.Reducer.mode()).clip(aoi)
    water_mask = scl_mode.eq(6).selfMask()
    
    cnt = water_mask.reduceToVectors(
        geometry=aoi, scale=10, geometryType='polygon',
        eightConnected=True, labelProperty='water',
        maxPixels=1e10, bestEffort=True
    ).filter(ee.Filter.eq('water', 1)).size().getInfo()
    print(f"Year {anno} - Mode SCL==6 Count: {cnt}")
    
    # Let's also check if we can compute water frequency: fraction of scenes where SCL == 6
    def is_water(img):
        return img.select('SCL').eq(6).copyProperties(img, ['system:time_start'])
    
    water_freq = col.map(is_water).mean().clip(aoi)
    # Check frequency stats in AOI
    freq_stats = water_freq.reduceRegion(
        reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), "", True),
        geometry=aoi,
        scale=10,
        maxPixels=1e10
    ).getInfo()
    print(f"Year {anno} - Water Freq stats:", freq_stats)
    
    for th in [0.05, 0.1, 0.2, 0.3]:
        cnt_freq = water_freq.gte(th).selfMask().reduceToVectors(
            geometry=aoi, scale=10, geometryType='polygon',
            eightConnected=True, labelProperty='water',
            maxPixels=1e10, bestEffort=True
        ).filter(ee.Filter.eq('water', 1)).size().getInfo()
        print(f"  Water Freq >= {th} Count: {cnt_freq}")
