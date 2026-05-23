"""
=============================================================================
  RÍO CHINCHINÁ — SCRIPT DE PRECISIÓN Y CONTROL DE ERRORES (MasterGIS v12)
  Usa coordenadas EXACTAS de OSM (2.884 nodos del río real)
  Buffer estrecho de 100m (Excluye Aeropuerto La Nubia y Zona Industrial Maltería)
  
  METODOLOGÍA DE CÉSAR AYBAR:
  - Clave A: Índice Espectral AWEIsh para supresión urbana (reflectancia física)
  - Clave B: Análisis de relieve SRTM (máscara de pendientes < 8°)
  - Clave C: Filtro morfológico de conectividad (connectedPixelCount >= 8 píxeles)
  - Clave D: Buffer ceñido de 100m
  
  Años procesados: 2006, 2012, 2018, 2025, 2026.
=============================================================================
"""
import ee
import json
import os
import sys
import io
import urllib.request

# Asegurar codificación utf-8 en consola de Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

GEE_PROJECT = 'ee-fernando1quim'

def main():
    print("=" * 75)
    print("  RÍO CHINCHINÁ — GEE MasterGIS v12 (Precisión Quirúrgica)")
    print("  AWEIsh + Máscara Pendientes + Filtro Conectividad + Buffer 100m")
    print("=" * 75)

    # Inicializar Earth Engine
    try:
        ee.Initialize(project=GEE_PROJECT)
        print("[OK] GEE inicializado con éxito.")
    except Exception as e:
        print("La inicialización de GEE falló. Autentique e intente de nuevo.")
        raise e

    # 1. Cargar el trazado detallado del Río Chinchiná (desde OSM)
    try:
        with open('chinchina_osm.geojson', encoding='utf-8') as f:
            gj = json.load(f)
        print(f"[OK] GeoJSON de OSM cargado: {len(gj['features'])} segmentos.")
    except Exception as e:
        print("Error al cargar chinchina_osm.geojson.")
        raise e

    # Unir todas las líneas en una sola geometría
    rio_union = ee.Geometry.MultiLineString(
        [feat['geometry']['coordinates'] for feat in gj['features']
         if len(feat['geometry']['coordinates']) >= 2]
    )

    # Clave D: Buffer ceñido de 100 metros para confinar la búsqueda al lecho real
    # Esto excluye geográficamente el Aeropuerto La Nubia y la zona de Maltería
    aoi = rio_union.buffer(100)
    print("[OK] Corredor de análisis creado: buffer de 100m geodésico.")
    
    os.makedirs('RioChinchina_KML_v6', exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PARTE 1: DATOS HISTÓRICOS — JRC Yearly (2006, 2012)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 75)
    print("  DATOS JRC (Landsat 5/7) — 2006 y 2012")
    print("─" * 75)
    
    jrc_coll = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")
    sat_map = {2006: 'Landsat 5 TM (JRC Yearly)', 2012: 'Landsat 7 ETM+ (JRC Yearly)'}

    for anno in [2006, 2012]:
        print(f"\n  Procesando {anno}...")
        img_jrc = (jrc_coll
                   .filterBounds(aoi)
                   .filter(ee.Filter.eq('year', anno))
                   .first())

        # waterClass >= 2: agua estacional o permanente
        agua = img_jrc.select('waterClass').gte(2).selfMask().clip(aoi)

        # Vectorizar en 30m (resolución nativa JRC)
        cauce_raw = agua.reduceToVectors(
            geometry=aoi,
            scale=30,
            geometryType='polygon',
            eightConnected=True,
            labelProperty='agua',
            maxPixels=1e10,
            bestEffort=True,
        ).filter(ee.Filter.eq('agua', 1))

        # Filtro de área >= 500 m²
        def set_area_jrc(f):
            return f.set('area_m2', f.geometry().area(maxError=5))
        
        cauce = (cauce_raw
                 .map(set_area_jrc)
                 .filter(ee.Filter.gt('area_m2', 500)))
        
        n = cauce.size().getInfo()
        print(f"  Polígonos JRC {anno}: {n}")

        cauce_final = cauce.map(lambda f: f
            .set('anno', anno)
            .set('rio', 'Rio Chinchina')
            .set('satelite', sat_map[anno])
            .set('metodo', 'JRC Yearly History waterClass >= 2 | buffer 100m OSM')
            .set('version', 'v6')
            .set('proyecto', 'AlennaArtCode / 2026')
        )

        _descargar_o_drive(cauce_final, anno, n)

    # ═══════════════════════════════════════════════════════════════════════
    # PARTE 2: SENTINEL-2 — 2018, 2025, 2026
    # ═══════════════════════════════════════════════════════════════════════
    # Ingesta de Sentinel-2 L2A y compuesto mediano anual
    # Conservar solo vegetación (4), suelo (5), agua (6) y nieve (11) mediante banda SCL
    def enmascarar_scl_sentinel(img):
        scl = img.select('SCL')
        mascara_calidad = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(11))
        return img.updateMask(mascara_calidad)

    configs_s2 = [
        {
            'anno': 2018,
            'f_ini': '2017-06-01', 'f_fin': '2019-06-30',
            'desc': '2018 (±18 meses, máxima cobertura)',
            'nube_pct': 50,
        },
        {
            'anno': 2025,
            'f_ini': '2025-01-01', 'f_fin': '2025-12-31',
            'desc': '2025 (anual, compuesto de precisión)',
            'nube_pct': 60,
        },
        {
            'anno': 2026,
            'f_ini': '2024-06-01', 'f_fin': '2026-05-22',
            'desc': '2026 (anual, mejor cobertura reciente)',
            'nube_pct': 70,
        },
    ]

    for cfg in configs_s2:
        anno    = cfg['anno']
        f_ini   = cfg['f_ini']
        f_fin   = cfg['f_fin']
        nube_pct= cfg['nube_pct']

        print(f"\n{'─'*75}")
        print(f"  SENTINEL-2 {anno}  ({cfg['desc']})")
        print(f"{'─'*75}")

        col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
               .filterBounds(aoi)
               .filterDate(f_ini, f_fin)
               .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', nube_pct))
               .map(enmascarar_scl_sentinel))

        n_esc = col.size().getInfo()
        print(f"  Escenas disponibles (<{nube_pct}% nubes): {n_esc}")
        
        if n_esc == 0:
            print(f"  [ADVERTENCIA] Sin escenas con filtro. Intentando con filtro relajado a 90%...")
            col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                   .filterBounds(aoi)
                   .filterDate(f_ini, f_fin)
                   .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 90))
                   .map(enmascarar_scl_sentinel))
            n_esc = col.size().getInfo()
            print(f"  Escenas (modo permisivo): {n_esc}")
            if n_esc == 0:
                print(f"  [ERROR] Sin datos para {anno}.")
                continue

        # Generar compuesto mediano
        mosaico_mediana = col.median()

        # Homogeneizar resoluciones a 10 metros usando interpolación bilineal
        proj_10m = mosaico_mediana.select('B3').projection()

        # Escalar bandas a reflectancia física (0-1) dividiendo por 10000
        band_blue = mosaico_mediana.select('B2').divide(10000)
        band_green = mosaico_mediana.select('B3').divide(10000)
        band_nir = mosaico_mediana.select('B8').divide(10000)

        # Reproyectar SWIR bands (B11 y B12 son nativamente de 20m)
        band_swir1_10m = mosaico_mediana.select('B11').resample('bilinear').reproject(crs=proj_10m, scale=10).divide(10000)
        band_swir2_10m = mosaico_mediana.select('B12').resample('bilinear').reproject(crs=proj_10m, scale=10).divide(10000)

        # Clave A: Cálculo del Índice Espectral AWEIsh para supresión urbana
        aweish = (band_blue
                 .add(band_green.multiply(2.5))
                 .subtract((band_nir.add(band_swir1_10m)).multiply(1.5))
                 .subtract(band_swir2_10m.multiply(0.25))
                 .rename('AWEIsh'))

        # Clave B: Análisis de Terreno con SRTM para eliminar sombras de montaña
        srtm = ee.Image('USGS/SRTMGL1_003').clip(aoi)
        pendiente = ee.Terrain.slope(srtm)
        mascara_pendiente = pendiente.lt(8) # Excluir zonas con pendiente >= 8°

        # Segmentación binaria y Filtros Espectrales Absorbentes
        # Limitar reflectancia NIR a 11% (0.11) para asegurar agua real
        filtro_espectral_nir = band_nir.lt(0.11)
        mascara_agua = aweish.gte(0.1).And(filtro_espectral_nir).And(mascara_pendiente)

        # Clave C: Filtro morfológico de conectividad de píxeles para limpiar ruido
        # Excluye parches aislados de menos de 8 píxeles contiguos (~800 m²)
        conteo_conectados = mascara_agua.selfMask().connectedPixelCount(maxSize=100, eightConnected=True)
        raster_agua_limpio = mascara_agua.updateMask(conteo_conectados.gte(8))

        # Vectorización precisa sobre CRS métrico local EPSG:32618 (UTM 18N)
        agua_forzada = raster_agua_limpio.selfMask().reproject(crs='EPSG:32618', scale=10)
        
        print(f"  Vectorizando (scale=10m, EPSG:32618)...")
        poligonos_rio = agua_forzada.reduceToVectors(
            reducer=ee.Reducer.countEvery(),
            geometry=aoi,
            crs='EPSG:32618',
            scale=10,
            geometryType='polygon',
            eightConnected=True,
            maxPixels=1e10
        )

        # Filtrado final por área geométrica del polígono (> 500 m²)
        def calcular_area(feature):
            return feature.set('area_m2', feature.geometry().area(maxError=1))

        vectores_finales = (poligonos_rio.map(calcular_area)
                           .filter(ee.Filter.gt('area_m2', 500)))

        n_filtrado = vectores_finales.size().getInfo()
        print(f"  Polígonos > 500 m²: {n_filtrado}")

        # Metadatos del proyecto
        metodo_str = 'AWEIsh>=0.1|NIR<0.11|pendiente<8°|buffer_100m|conectividad>=8px|area>500m2|SCL_enmascarado|10m'
        cauce_final = vectores_finales.map(lambda f: f
            .set('anno', anno)
            .set('rio', 'Rio Chinchina')
            .set('satelite', 'Sentinel-2 MSI 10m')
            .set('metodo', metodo_str)
            .set('version', 'v6')
            .set('proyecto', 'AlennaArtCode / 2026')
        )

        _descargar_o_drive(cauce_final, anno, n_filtrado)

    print("\n" + "=" * 75)
    print("  PROCESO COMPLETADO — TODOS LOS KMLs GENERADOS CON PRECISIÓN MÁXIMA")
    print("=" * 75)


def _descargar_o_drive(cauce_final, anno, n_polys):
    """Intenta descargar directamente el KML; si falla, exporta a Drive como respaldo."""
    filename = f'cauce_rio_chinchina_{anno}_v6.kml'
    filepath = os.path.join('RioChinchina_KML_v6', filename)
    
    if n_polys == 0:
        print(f"  [ADVERTENCIA] 0 polígonos detectados para {anno}. No se genera archivo.")
        # Escribimos un KML vacío para evitar fallos de carga en el frontend
        kml_vacio = '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Vacio</name></Document></kml>'
        with open(filepath, 'w', encoding='utf-8') as out_f:
            out_f.write(kml_vacio)
        return

    try:
        url = cauce_final.getDownloadURL(
            filetype='kml',
            filename=f'cauce_rio_chinchina_{anno}_v6'
        )
        print(f"  Descargando directamente {filename}...")
        response = urllib.request.urlopen(url, timeout=300)
        kml_data = response.read()
        with open(filepath, 'wb') as out_f:
            out_f.write(kml_data)
        size_kb = len(kml_data) / 1024
        print(f"  [OK] {filepath} guardado localmente ({size_kb:.1f} KB | {n_polys} polígonos)")
    except Exception as e:
        print(f"  [DESCARGA DIRECTA FALLIDA] {e}")
        print(f"  Lanzando tarea de exportación a Google Drive...")
        
        # Exportar a Google Drive como respaldo
        tarea = ee.batch.Export.table.toDrive(
            collection=cauce_final,
            description=f'cauce_rio_chinchina_{anno}_v6',
            folder='RioChinchina_KML_v6',
            fileNamePrefix=f'cauce_rio_chinchina_{anno}_v6',
            fileFormat='KML'
        )
        tarea.start()
        print(f"  [DRIVE] Tarea iniciada: {tarea.id}")
        print(f"  Monitorear en: https://code.earthengine.google.com/tasks")


if __name__ == '__main__':
    main()
