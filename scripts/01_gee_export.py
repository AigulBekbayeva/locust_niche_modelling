# -*- coding: utf-8 -*-
"""
01_gee_export.py — выгрузка предикторов для MaxEnt из Google Earth Engine.

Все слои экспортируются на ОДНУ сетку (EPSG:4326, 30" ≈ 1 км, выровнена
по сетке WorldClim), что обязательно для MaxEnt: одинаковые экстент,
размер ячейки и число строк/столбцов.

Установка и запуск:
    pip install earthengine-api
    earthengine authenticate        # один раз
    python 01_gee_export.py

Результат: GeoTIFF-файлы в папке Google Drive EXPORT_FOLDER
(по одному файлу на переменную). Их нужно скачать в ./gee_layers/
и дальше запустить 02_prepare_maxent.py.
"""
import ee

# ------------------------------------------------------------------ настройки
GEE_PROJECT = "your-gee-project-id"   # <-- ваш Cloud-проект с включённым Earth Engine
EXPORT_FOLDER = "locust_maxent_layers"

YEAR_START, YEAR_END = 2015, 2024      # многолетнее осреднение
SEASON = (4, 9)                         # сезон активности саранчовых: апрель–сентябрь
SPRING = (4, 6)                         # отрождение личинок: апрель–июнь
# зима (дек–фев) — зимовка яиц под снегом, см. блок ERA5

# Сетка: 1/120° (30"), экстент — Казахстан с запасом, кратный шагу сетки
RES = 1.0 / 120.0
XMIN, YMAX = 46.4, 55.5
NCOLS, NROWS = 4920, 1800               # до 87.4° в.д. и 40.5° с.ш.
XMAX, YMIN = XMIN + NCOLS * RES, YMAX - NROWS * RES
CRS = "EPSG:4326"
TRANSFORM = [RES, 0, XMIN, 0, -RES, YMAX]
NODATA = -9999
# ----------------------------------------------------------------------------

ee.Initialize(project=GEE_PROJECT)

region = ee.Geometry.Rectangle([XMIN, YMIN, XMAX, YMAX], proj=CRS, geodesic=False)
kz = (ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017")
      .filter(ee.Filter.eq("country_na", "Kazakhstan")))
kz_mask = ee.Image.constant(1).clip(kz.geometry().buffer(5000)).mask()

years = ee.Filter.calendarRange(YEAR_START, YEAR_END, "year")
season = ee.Filter.calendarRange(SEASON[0], SEASON[1], "month")
spring = ee.Filter.calendarRange(SPRING[0], SPRING[1], "month")


def agg_mean(img, max_px=1024):
    """Корректное осреднение мелкого разрешения (30–250 м) до 1 км."""
    return (img.reduceResolution(ee.Reducer.mean(), maxPixels=max_px)
               .reproject(crs=CRS, crsTransform=TRANSFORM))


def bilinear(col):
    """Для грубых/синусоидальных данных — билинейная интерполяция при перепроецировании."""
    return col.map(lambda i: i.resample("bilinear"))


layers = {}

# --- 1. Климат: WorldClim v1 (1 км, 1960–1990). Температуры хранятся ×10.
wc = ee.Image("WORLDCLIM/V1/BIO")
layers["bio01_tmean"]   = wc.select("bio01").multiply(0.1)   # ср. год. t, °C
layers["bio04_tseason"] = wc.select("bio04").multiply(0.01)  # сезонность t (SD, °C)
layers["bio05_tmax"]    = wc.select("bio05").multiply(0.1)   # макс. t самого тёплого мес.
layers["bio06_tmin"]    = wc.select("bio06").multiply(0.1)   # мин. t самого холодного мес.
layers["bio12_prec"]    = wc.select("bio12")                  # год. осадки, мм
layers["bio15_pseason"] = wc.select("bio15")                  # сезонность осадков, CV

# --- 2. Температура поверхности: MODIS MOD11A2 (8 дней, 1 км). Кельвины ×0.02.
lst = (ee.ImageCollection("MODIS/061/MOD11A2").filter(years).filter(season))
lst = bilinear(lst)
layers["lst_day"] = (lst.select("LST_Day_1km").mean()
                     .multiply(0.02).subtract(273.15))
layers["lst_night"] = (lst.select("LST_Night_1km").mean()
                       .multiply(0.02).subtract(273.15))


# --- 3. Растительность: MODIS MOD13A2 NDVI (16 дней, 1 км), только хорошие пиксели.
def ndvi_qa(img):
    good = img.select("SummaryQA").lte(1)
    return img.select("NDVI").multiply(0.0001).updateMask(good)


ndvi = bilinear(ee.ImageCollection("MODIS/061/MOD13A2").filter(years).map(ndvi_qa))
layers["ndvi_season"] = ndvi.filter(season).mean()
layers["ndvi_spring"] = ndvi.filter(spring).mean()
layers["ndvi_max"] = ndvi.filter(season).max()

# --- 4. Реанализ ERA5-Land (месячные, ~11 км) — осадки, влажность почвы, снег.
#     CHIRPS не используется: он покрывает только до 50° с.ш.
era = bilinear(ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filter(years))
n_years = YEAR_END - YEAR_START + 1
layers["prec_spring"] = (era.filter(spring).select("total_precipitation_sum")
                         .sum().divide(n_years).multiply(1000))          # мм за апр–июн
layers["soilm_spring"] = (era.filter(spring)
                          .select("volumetric_soil_water_layer_1").mean())  # м³/м³
winter = ee.Filter.Or(ee.Filter.calendarRange(12, 12, "month"),
                      ee.Filter.calendarRange(1, 2, "month"))
layers["snow_winter"] = (era.filter(winter)
                         .select("snow_depth").mean().multiply(100))     # см

# --- 5. Рельеф: SRTM 90 м -> среднее по 1 км.
dem = ee.Image("CGIAR/SRTM90_V4").select("elevation")
layers["elev"] = agg_mean(dem)
layers["slope"] = agg_mean(ee.Terrain.slope(dem))

# --- 6. Земной покров: Copernicus Global Land Cover 100 м (2019), доли покрытия, %.
lc = ee.Image("COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019")
layers["lc_grass"] = agg_mean(lc.select("grass-coverfraction"))
layers["lc_crops"] = agg_mean(lc.select("crops-coverfraction"))
layers["lc_shrub"] = agg_mean(lc.select("shrub-coverfraction"))
layers["lc_bare"] = agg_mean(lc.select("bare-coverfraction"))

# --- 7. Почвы: OpenLandMap 250 м, поверхностный слой (0 см), % массы.
#     Важно для откладки кубышек.
layers["soil_sand"] = agg_mean(
    ee.Image("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02").select("b0"))
layers["soil_clay"] = agg_mean(
    ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select("b0"))

# ------------------------------------------------------------------ экспорт
tasks = []
for name, img in layers.items():
    out = (img.rename(name).toFloat()
              .updateMask(kz_mask)
              .unmask(NODATA, sameFootprint=False))
    task = ee.batch.Export.image.toDrive(
        image=out,
        description=f"maxent_{name}",
        folder=EXPORT_FOLDER,
        fileNamePrefix=name,
        region=region,
        crs=CRS,
        crsTransform=TRANSFORM,
        maxPixels=1e10,
        formatOptions={"noData": NODATA},
    )
    task.start()
    tasks.append(task)
    print(f"запущено: {name}")

print(f"\nВсего задач: {len(tasks)}. Статус: https://code.earthengine.google.com/tasks")
print(f"Сетка: {NCOLS} x {NROWS}, шаг {RES:.8f}°, экстент {XMIN},{YMIN} – {XMAX},{YMAX}")
