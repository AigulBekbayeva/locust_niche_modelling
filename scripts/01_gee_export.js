/**
 * 01_gee_export.js — выгрузка предикторов для MaxEnt (Google Earth Engine Code Editor)
 *
 * Все слои экспортируются на ОДНУ сетку: EPSG:4326, 30" (~1 км), выровнена
 * по WorldClim. Каждый слой -> отдельный GeoTIFF в Google Drive (папка EXPORT_FOLDER).
 *
 * Как запустить:
 *   1. Вставьте код в https://code.earthengine.google.com и нажмите Run.
 *   2. На вкладке Tasks (справа) появятся задачи — нажмите RUN у каждой.
 *   3. Скачайте файлы из Drive в папку gee_layers/ и запустите 02_prepare_maxent.py.
 */

// ------------------------------------------------------------------ настройки
var EXPORT_FOLDER = 'locust_maxent_layers';

var YEAR_START = 2015, YEAR_END = 2024;   // многолетнее осреднение
var SEASON = [4, 9];                        // сезон активности: апрель–сентябрь
var SPRING = [4, 6];                        // отрождение личинок: апрель–июнь

// Сетка 1/120°, экстент — Казахстан с запасом, кратный шагу сетки
var RES = 1 / 120;
var XMIN = 46.4, YMAX = 55.5;
var NCOLS = 4920, NROWS = 1800;             // до 87.4° в.д. и 40.5° с.ш.
var XMAX = XMIN + NCOLS * RES, YMIN = YMAX - NROWS * RES;
var CRS = 'EPSG:4326';
var TRANSFORM = [RES, 0, XMIN, 0, -RES, YMAX];
var NODATA = -9999;

// Показать точки находок (необязательно): загрузите CSV как Table asset
// (Assets -> NEW -> CSV), предварительно переименовав столбцы Широта/Долгота
// в lat/lon латиницей, и укажите путь:
var POINTS_ASSET = null;  // например 'projects/your-project/assets/locust_coord'
// ----------------------------------------------------------------------------

var region = ee.Geometry.Rectangle([XMIN, YMIN, XMAX, YMAX], CRS, false);
var kz = ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017')
  .filter(ee.Filter.eq('country_na', 'Kazakhstan'));
var kzMask = ee.Image.constant(1).clip(kz.geometry().buffer(5000)).mask();

var years = ee.Filter.calendarRange(YEAR_START, YEAR_END, 'year');
var season = ee.Filter.calendarRange(SEASON[0], SEASON[1], 'month');
var spring = ee.Filter.calendarRange(SPRING[0], SPRING[1], 'month');
var winter = ee.Filter.or(
  ee.Filter.calendarRange(12, 12, 'month'),
  ee.Filter.calendarRange(1, 2, 'month'));

// Корректное осреднение мелкого разрешения (30–250 м) до 1 км
function aggMean(img) {
  return img.reduceResolution({reducer: ee.Reducer.mean(), maxPixels: 1024})
            .reproject({crs: CRS, crsTransform: TRANSFORM});
}
// Билинейная интерполяция для грубых / синусоидальных данных
function bilinear(col) {
  return col.map(function (i) { return i.resample('bilinear'); });
}

var layers = {};

// --- 1. Климат: WorldClim v1 (1 км). Температуры хранятся ×10.
var wc = ee.Image('WORLDCLIM/V1/BIO');
layers.bio01_tmean   = wc.select('bio01').multiply(0.1);   // ср. год. t, °C
layers.bio04_tseason = wc.select('bio04').multiply(0.01);  // сезонность t (SD, °C)
layers.bio05_tmax    = wc.select('bio05').multiply(0.1);   // макс. t тёплого месяца
layers.bio06_tmin    = wc.select('bio06').multiply(0.1);   // мин. t холодного месяца
layers.bio12_prec    = wc.select('bio12');                  // год. осадки, мм
layers.bio15_pseason = wc.select('bio15');                  // сезонность осадков, CV

// --- 2. Температура поверхности: MODIS MOD11A2 (Кельвины ×0.02)
var lst = bilinear(ee.ImageCollection('MODIS/061/MOD11A2').filter(years).filter(season));
layers.lst_day   = lst.select('LST_Day_1km').mean().multiply(0.02).subtract(273.15);
layers.lst_night = lst.select('LST_Night_1km').mean().multiply(0.02).subtract(273.15);

// --- 3. Растительность: MODIS MOD13A2 NDVI, только хорошие пиксели
var ndvi = bilinear(ee.ImageCollection('MODIS/061/MOD13A2').filter(years)
  .map(function (img) {
    return img.select('NDVI').multiply(0.0001)
              .updateMask(img.select('SummaryQA').lte(1))
              .copyProperties(img, ['system:time_start']);
  }));
layers.ndvi_season = ndvi.filter(season).mean();
layers.ndvi_spring = ndvi.filter(spring).mean();
layers.ndvi_max    = ndvi.filter(season).max();

// --- 4. ERA5-Land (месячные, ~11 км). CHIRPS не подходит: только до 50° с.ш.
var era = bilinear(ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR').filter(years));
var nYears = YEAR_END - YEAR_START + 1;
layers.prec_spring  = era.filter(spring).select('total_precipitation_sum')
                         .sum().divide(nYears).multiply(1000);          // мм за апр–июн
layers.soilm_spring = era.filter(spring)
                         .select('volumetric_soil_water_layer_1').mean(); // м³/м³
layers.snow_winter  = era.filter(winter).select('snow_depth')
                         .mean().multiply(100);                          // см

// --- 5. Рельеф: SRTM 90 м -> среднее по 1 км
var dem = ee.Image('CGIAR/SRTM90_V4').select('elevation');
layers.elev  = aggMean(dem);
layers.slope = aggMean(ee.Terrain.slope(dem));

// --- 6. Земной покров: Copernicus 100 м (2019), доли покрытия, %
var lc = ee.Image('COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019');
layers.lc_grass = aggMean(lc.select('grass-coverfraction'));
layers.lc_crops = aggMean(lc.select('crops-coverfraction'));
layers.lc_shrub = aggMean(lc.select('shrub-coverfraction'));
layers.lc_bare  = aggMean(lc.select('bare-coverfraction'));

// --- 7. Почвы: OpenLandMap 250 м, поверхностный слой, %
layers.soil_sand = aggMean(
  ee.Image('OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02').select('b0'));
layers.soil_clay = aggMean(
  ee.Image('OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02').select('b0'));

// ------------------------------------------------------------------ экспорт
var names = Object.keys(layers);
names.forEach(function (name) {
  var out = layers[name].rename(name).toFloat()
    .updateMask(kzMask)
    .unmask(NODATA, false);
  Export.image.toDrive({
    image: out,
    description: 'maxent_' + name,
    folder: EXPORT_FOLDER,
    fileNamePrefix: name,
    region: region,
    crs: CRS,
    crsTransform: TRANSFORM,
    maxPixels: 1e10,
    formatOptions: {noData: NODATA}
  });
});
print('Задач экспорта: ' + names.length + ' (вкладка Tasks -> RUN)', names);
print('Сетка', NCOLS + ' x ' + NROWS, 'шаг', RES);

// ------------------------------------------------------------------ проверка на карте
Map.centerObject(kz, 5);
Map.addLayer(layers.ndvi_spring.updateMask(kzMask),
  {min: 0, max: 0.6, palette: ['#d7c9a3', '#a6d96a', '#1a9641']}, 'NDVI весна');
Map.addLayer(layers.bio06_tmin.updateMask(kzMask),
  {min: -25, max: 0, palette: ['#313695', '#74add1', '#ffffbf']}, 'bio06 мин. t', false);
Map.addLayer(layers.lc_crops.updateMask(kzMask),
  {min: 0, max: 100, palette: ['white', '#e6ab02']}, 'Доля пашни', false);
Map.addLayer(layers.soil_sand.updateMask(kzMask),
  {min: 10, max: 80, palette: ['#8c510a', '#f6e8c3']}, 'Песок, %', false);
Map.addLayer(ee.Image().paint(kz, 0, 2), {palette: 'black'}, 'Граница РК');

if (POINTS_ASSET) {
  var pts = ee.FeatureCollection(POINTS_ASSET);
  Map.addLayer(pts, {color: 'red'}, 'Находки саранчовых');
  print('Точек:', pts.size());
}
