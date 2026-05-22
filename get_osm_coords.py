import urllib.request, json, urllib.parse, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

query = """
[out:json][timeout:60];
(
  way["waterway"]["name"~"Chinchi",i](4.80,-75.93,5.16,-75.30);
);
out geom;
"""

url  = 'https://overpass-api.de/api/interpreter'
data = urllib.parse.urlencode({'data': query}).encode()
req  = urllib.request.Request(url, data=data, headers={'User-Agent': 'RioChinchina-GEE/1.0'})
resp = urllib.request.urlopen(req, timeout=60)
result = json.loads(resp.read())

elems = result['elements']
print(f"Segmentos encontrados: {len(elems)}")
for el in elems[:8]:
    name = el.get('tags',{}).get('name','?')
    geom = el.get('geometry',[])
    print(f"  ID:{el['id']}  name:{name}  nodos:{len(geom)}")

# Construir GeoJSON
features = []
for el in elems:
    if el.get('geometry'):
        coords = [[n['lon'], n['lat']] for n in el['geometry']]
        features.append({
            'type':'Feature',
            'properties':{'osm_id':el['id'],'name':el.get('tags',{}).get('name','?')},
            'geometry':{'type':'LineString','coordinates':coords}
        })

gj = {'type':'FeatureCollection','features':features}
with open('chinchina_osm.geojson','w', encoding='utf-8') as f:
    json.dump(gj, f, ensure_ascii=False, indent=2)

print(f"\nGuardado: chinchina_osm.geojson  ({len(features)} segmentos)")

# Extraer todos los puntos ordenados por longitud (Este a Oeste)
all_coords = []
for feat in features:
    all_coords.extend(feat['geometry']['coordinates'])

all_coords.sort(key=lambda c: -c[0])   # de E a O (longitud decreciente)
print(f"Total coordenadas: {len(all_coords)}")
print(f"Extremo E (nacimiento): {all_coords[0]}")
print(f"Extremo O (desembocadura): {all_coords[-1]}")
