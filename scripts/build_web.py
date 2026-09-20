# -*- coding: utf-8 -*-
"""
build_web.py — готовит данные для веб-карты (папка docs/ для GitHub Pages).

  docs/data/model.json      точность модели и вклад переменных (из maxentResults.csv)
  docs/data/points.geojson  исходные точки обследования (из locust_coord.csv)
  docs/data/layers.json     описание растровых слоёв
  docs/layers/*.png         растры в Web Mercator, раскрашенные, с прозрачным NoData

    pip install rasterio numpy pandas pillow matplotlib
    python scripts/build_web.py --maxent-results res_all/maxentResults.csv \
        --points locust_coord.csv --results-dir res_all --layers-dir maxent_input/layers
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

SPECIES = "locusts"
NODATA = -9999

# name: (подпись, единицы, группа, описание, палитра)
VARS = {
    "bio01_tmean":   ("Annual mean temperature", "°C", "Climate", "WorldClim bio01", "temp"),
    "bio04_tseason": ("Temperature seasonality", "SD, °C", "Climate", "WorldClim bio04", "temp"),
    "bio05_tmax":    ("Max temperature of warmest month", "°C", "Climate", "WorldClim bio05", "temp"),
    "bio06_tmin":    ("Min temperature of coldest month", "°C", "Climate", "WorldClim bio06", "cold"),
    "bio12_prec":    ("Annual precipitation", "mm", "Climate", "WorldClim bio12", "water"),
    "bio15_pseason": ("Precipitation seasonality", "CV, %", "Climate", "WorldClim bio15", "water"),
    "lst_day":       ("Daytime land surface temperature", "°C", "Satellite", "MODIS MOD11A2, Apr–Sep 2015–2024", "temp"),
    "lst_night":     ("Night-time land surface temperature", "°C", "Satellite", "MODIS MOD11A2, Apr–Sep 2015–2024", "temp"),
    "ndvi_spring":   ("Spring NDVI", "", "Satellite", "MODIS MOD13A2, Apr–Jun 2015–2024", "veg"),
    "ndvi_season":   ("Growing-season NDVI", "", "Satellite", "MODIS MOD13A2, Apr–Sep 2015–2024", "veg"),
    "ndvi_max":      ("Maximum NDVI", "", "Satellite", "MODIS MOD13A2, Apr–Sep 2015–2024", "veg"),
    "prec_spring":   ("Spring precipitation", "mm", "Reanalysis", "ERA5-Land, Apr–Jun 2015–2024", "water"),
    "soilm_spring":  ("Spring soil moisture", "m³/m³", "Reanalysis", "ERA5-Land, 0–7 cm layer", "water"),
    "snow_winter":   ("Winter snow depth", "cm", "Reanalysis", "ERA5-Land, Dec–Feb 2015–2024", "cold"),
    "elev":          ("Elevation", "m", "Terrain", "SRTM 90 m", "relief"),
    "slope":         ("Slope", "°", "Terrain", "SRTM 90 m", "relief"),
    "lc_grass":      ("Grass cover fraction", "%", "Land cover", "Copernicus Land Cover 2019", "veg"),
    "lc_crops":      ("Cropland fraction", "%", "Land cover", "Copernicus Land Cover 2019", "crops"),
    "lc_shrub":      ("Shrub cover fraction", "%", "Land cover", "Copernicus Land Cover 2019", "veg"),
    "lc_bare":       ("Bare ground fraction", "%", "Land cover", "Copernicus Land Cover 2019", "bare"),
    "soil_sand":     ("Soil sand content", "%", "Soil", "OpenLandMap", "bare"),
    "soil_clay":     ("Soil clay content", "%", "Soil", "OpenLandMap", "relief"),
}

REGIONS = {
    "Акмолинская область": "Akmola Region", "Северо-Казахстанская область": "North Kazakhstan Region",
    "Костанайская область": "Kostanay Region", "Павлодарская область": "Pavlodar Region",
    "Карагандинская область": "Karaganda Region", "Западно-Казахстанская область": "West Kazakhstan Region",
    "Актюбинская область": "Aktobe Region", "Мангистауская область": "Mangystau Region",
    "Улытауская область": "Ulytau Region", "Атырауская область": "Atyrau Region",
    "Алматинская область": "Almaty Region", "Туркестанская область": "Turkistan Region",
    "Жамбылская область": "Jambyl Region", "Кызылординская область": "Kyzylorda Region",
    "Жетысуская область": "Jetisu Region", "Абайская область": "Abai Region",
}
ZONE_WORDS = {
    "Очень увлажнённая": "Very humid", "Увлажнённая": "Humid", "Полузасушливая": "Semi-arid",
    "Аридная": "Arid", "Умеренно тёплая": "moderately warm", "Тёплая": "warm", "Жаркая": "hot",
}
HABITATS = {
    "Луговая степь (разнотравье)": "Meadow steppe (forbs)",
    "Полынно-ковыльная степь": "Wormwood–feather grass steppe",
    "Полынная степь": "Wormwood steppe",
    "Злаково-полынная степь": "Grass–wormwood steppe",
    "Злаковая степь": "Grass steppe",
    "Ковыльно-злаковая степь": "Feather grass–grass steppe",
    "Рудеральный (придорожный, разнотравный)": "Ruderal (roadside, forbs)",
    "Типчаково-пырейная степь": "Fescue–couch grass steppe",
    "Ковыльно-типчаково-полынная степь": "Feather grass–fescue–wormwood steppe",
    "Злаково-ковыльная степь": "Grass–feather grass steppe",
    "Пырейно-типчаковая степь": "Couch grass–fescue steppe",
    "Типчаково-ковыльная степь": "Fescue–feather grass steppe",
    "Полынно-злаковая степь": "Wormwood–grass steppe",
    "Ковыльно-типчаково-злаковая степь": "Feather grass–fescue–grass steppe",
    "Типчаково-полынная степь": "Fescue–wormwood steppe",
    "Злаково-типчаково-ковыльная степь": "Grass–fescue–feather grass steppe",
    "Типчаковая степь": "Fescue steppe",
    "Разнотравная степь": "Forb steppe",
    "Агроценоз (посев пшеницы)": "Cropland (wheat)",
    "Полынно-злаково-разнотравная степь": "Wormwood–grass–forb steppe",
    "Агроценоз (посев люцерны)": "Cropland (alfalfa)",
    "Агроценоз (бахчевые культуры)": "Cropland (melons and gourds)",
    "Кустарниково-древесная растительность речных пойм": "Riparian shrubs and woodland",
    "Агроценоз (посев люцерны) и полынная степь": "Cropland (alfalfa) and wormwood steppe",
    "Старовозрастные посевы житняка": "Old crested wheatgrass plantings",
    "Злаково-разнотравная степь": "Grass–forb steppe",
    "Агроценоз (посев кукурузы)": "Cropland (maize)",
}
_TR = dict(zip("абвгдезийклмнопрстуфыэәғқңөұүһі",
               "abvgdeziyklmnoprstufyeagqnouuhi"))
_TR.update({"ё": "yo", "ж": "zh", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
            "ъ": "", "ь": "", "ю": "yu", "я": "ya"})


def translit(text):
    """Кириллица (рус./каз.) -> латиница, упрощённая схема BGN."""
    import re
    text = re.sub(r"(ий|ый)\b", "y", str(text))
    out = []
    for ch in text:
        low = ch.lower()
        t = _TR.get(low, ch)
        out.append(t.capitalize() if ch != low and t else t)
    return "".join(out)


def zone_en(z):
    parts = [ZONE_WORDS.get(p.strip(), translit(p.strip())) for p in str(z).split("/")]
    return ", ".join(parts)


def district_en(d):
    import re
    d = re.sub(r"\s*\bрайон\b\s*", " ", str(d), flags=re.I).strip()
    if d.startswith("г."):
        return translit(d[2:].strip())
    return f"{translit(d)} District"

PALETTES = {
    # как в MaxEnt: синий -> голубой -> зелёный -> жёлтый -> оранжевый -> красный
    "suit":   ["#0000ff", "#0080ff", "#00ffff", "#00ff80", "#80ff00", "#ffff00", "#ff8000", "#ff0000"],
    "sd":     ["#f3f1f7", "#c9c1dc", "#8f7fb6", "#56438a", "#2a1c52"],
    "binary": ["#b8551f"],
    "temp":   ["#2c4a78", "#6f9cc4", "#f1ecd2", "#e59a52", "#a8341e"],
    "cold":   ["#1d2f5c", "#4f7fb8", "#a9cbe3", "#eef3f5"],
    "water":  ["#f4efdc", "#bcd9c9", "#5fa6b1", "#2c6a8f", "#17325e"],
    "veg":    ["#f2ead3", "#cdd49a", "#8fb164", "#4b7f3f", "#1f4a2a"],
    "crops":  ["#f4f1e6", "#ecd98f", "#d9b23b", "#a37a12", "#5c4208"],
    "bare":   ["#eef0e8", "#e5d6ae", "#cfa66d", "#a26b3c", "#5e3a1f"],
    "relief": ["#f3f1ea", "#cfc5ad", "#a08f73", "#6b5c48", "#342c24"],
}


# ------------------------------------------------------------------ model.json
def build_model(csv_path, out):
    df = pd.read_csv(csv_path)
    df = df[df.Species.str.startswith(SPECIES)].copy()
    avg = df[df.Species.str.contains("average")].iloc[0]
    reps = df[~df.Species.str.contains("average")]
    variables = []
    for v, (label, unit, group, source, _) in VARS.items():
        if f"{v} contribution" not in df:
            continue
        variables.append({
            "id": v, "label": label, "unit": unit, "group": group, "source": source,
            "contribution": round(float(avg[f"{v} contribution"]), 1),
            "permutation": round(float(avg[f"{v} permutation importance"]), 1),
            "auc_only": round(float(reps[f"AUC with only {v}"].mean()), 3),
            "auc_without": round(float(reps[f"AUC without {v}"].mean()), 3),
        })
    variables.sort(key=lambda x: -(x["contribution"] + x["permutation"]))
    model = {
        "name": SPECIES,
        "n_train": float(avg["#Training samples"]), "n_test": float(avg["#Test samples"]),
        "n_total": int(round(avg["#Training samples"] + avg["#Test samples"])),
        "auc_train": round(float(avg["Training AUC"]), 3),
        "auc_test": round(float(avg["Test AUC"]), 3),
        "auc_test_sd": round(float(reps["Test AUC"].std(ddof=0)), 3),
        "auc_test_reps": [round(float(x), 3) for x in reps["Test AUC"]],
        "auc_train_reps": [round(float(x), 3) for x in reps["Training AUC"]],
        "thr_10ptp": round(float(avg["10 percentile training presence Cloglog threshold"]), 3),
        "thr_10ptp_area": round(float(avg["10 percentile training presence area"]), 3),
        "thr_10ptp_omission": round(float(avg["10 percentile training presence test omission"]), 3),
        "thr_mtss": round(float(avg["Maximum training sensitivity plus specificity Cloglog threshold"]), 3),
        "thr_mtss_area": round(float(avg["Maximum training sensitivity plus specificity area"]), 3),
        "background": int(round(avg["#Background points"])),
        "replicates": int(len(reps)),
        "variables": variables,
    }
    write_json(os.path.join(out, "data", "model.json"), model)
    print(f"model.json: test AUC {model['auc_test']} ± {model['auc_test_sd']}, {len(variables)} переменных")
    return model


# ------------------------------------------------------------------ points.geojson
def build_points(csv_path, out):
    df = pd.read_csv(csv_path, sep=None, engine="python", encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(subset=["Широта", "Долгота"])
    num = "Численность за час сбора (экз.)"
    feats = []
    for (lat, lon), g in df.groupby(["Широта", "Долгота"]):
        first = g.iloc[0]
        note = "; ".join(sorted(set(g["Примечание"].dropna().astype(str))))
        recs = (g.sort_values(num, ascending=False)
                 [["Латинское название саранчового", num]]
                 .values.tolist())
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {
                "region": REGIONS.get(first["Область"], translit(first["Область"])),
                "district": district_en(first["Район"]),
                "place": translit(first["Населенный пункт"]),
                "zone": zone_en(first["Агроклиматическая зона"]),
                "habitat": HABITATS.get(first["Тип местообитания"], translit(first["Тип местообитания"])),
                "vegetation": first["Растительный состав (название на латинском)"],
                "approx": "восстановлены приблизительно" in note,
                "n_species": int(g["Латинское название саранчового"].nunique()),
                "total": float(np.nansum(g[num])),
                "records": [[a, None if pd.isna(c) else float(c)] for a, c in recs],
            },
        })
    write_json(os.path.join(out, "data", "points.geojson"),
               {"type": "FeatureCollection", "features": feats})
    print(f"points.geojson: {len(feats)} мест обследования, {len(df)} записей")


# ------------------------------------------------------------------ растры
def read_raster(path):
    import rasterio
    with rasterio.open(path) as src:
        a = src.read(1).astype("float32")
        nd = src.nodata if src.nodata is not None else NODATA
        a[(a == nd) | ~np.isfinite(a)] = np.nan
        return a, src.transform


def to_mercator(a, transform, width):
    from rasterio.crs import CRS
    from rasterio.warp import Resampling, calculate_default_transform, reproject
    src_crs, dst_crs = CRS.from_epsg(4326), CRS.from_epsg(3857)
    h, w = a.shape
    left, top = transform.c, transform.f
    right, bottom = left + w * transform.a, top + h * transform.e
    _, dw0, dh0 = calculate_default_transform(src_crs, dst_crs, w, h, left, bottom, right, top)
    dh = int(round(width * dh0 / dw0))
    dt, _, _ = calculate_default_transform(src_crs, dst_crs, w, h, left, bottom, right, top,
                                           dst_width=width, dst_height=dh)
    dst = np.full((dh, width), np.nan, dtype="float32")
    reproject(a, dst, src_transform=transform, src_crs=src_crs, dst_transform=dt,
              dst_crs=dst_crs, resampling=Resampling.bilinear,
              src_nodata=np.nan, dst_nodata=np.nan)
    # границы в градусах для Leaflet
    from rasterio.warp import transform as tr_pts
    xs = [dt.c, dt.c + width * dt.a]
    ys = [dt.f + dh * dt.e, dt.f]
    lon, lat = tr_pts(dst_crs, src_crs, xs, ys)
    return dst, [[lat[0], lon[0]], [lat[1], lon[1]]]


def colorize(a, vmin, vmax, colors, alpha=235):
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("c", colors)
    t = np.clip((a - vmin) / (vmax - vmin if vmax > vmin else 1), 0, 1)
    rgba = (cmap(np.nan_to_num(t)) * 255).astype("uint8")
    rgba[..., 3] = np.where(np.isfinite(a), alpha, 0)
    return rgba


def save_png(rgba, path):
    from PIL import Image
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def build_layers(results_dir, layers_dir, out, model, width):
    os.makedirs(os.path.join(out, "layers"), exist_ok=True)
    meta, bounds = {}, None
    old = os.path.join(out, "data", "layers.json")
    if os.path.exists(old):                    # дополняем, а не затираем ранее собранные слои
        with open(old, encoding="utf-8") as f:
            prev = json.load(f)
        meta, bounds = prev.get("layers", {}), prev.get("bounds")

    def add(name, arr, transform, vmin, vmax, palette, **info):
        nonlocal bounds
        merc, b = to_mercator(arr, transform, width)
        bounds = bounds or b
        colors = PALETTES[palette]
        if palette == "binary":
            rgba = np.zeros(merc.shape + (4,), dtype="uint8")
            rgb = tuple(int(colors[0][i:i + 2], 16) for i in (1, 3, 5))
            on = np.isfinite(merc) & (merc >= vmin)
            rgba[on, :3] = rgb; rgba[on, 3] = 215
        else:
            rgba = colorize(merc, vmin, vmax, colors)
        save_png(rgba, os.path.join(out, "layers", f"{name}.png"))
        meta[name] = {"file": f"layers/{name}.png", "min": round(float(vmin), 3),
                      "max": round(float(vmax), 3), "colors": colors, **info}
        print(f"  {name:14s} {vmin:.3g} … {vmax:.3g}")

    if results_dir:
        avg = os.path.join(results_dir, f"{SPECIES}_avg.asc")
        sd = os.path.join(results_dir, f"{SPECIES}_stddev.asc")
        if os.path.exists(avg):
            a, t = read_raster(avg)
            add("suitability", a, t, 0, 1, "suit", label="Habitat suitability",
                unit="cloglog, 0–1", kind="result")
            if model:
                add("binary", a, t, model["thr_10ptp"], 1, "binary",
                    label="Suitable area", kind="result",
                    unit=f"suitability ≥ {model['thr_10ptp']:.2f} (10th percentile training presence)")
        else:
            print(f"нет {avg}")
        if os.path.exists(sd):
            a, t = read_raster(sd)
            add("sd", a, t, 0, float(np.nanpercentile(a, 99)), "sd",
                label="Prediction uncertainty", unit="SD across 5 replicates", kind="result")

    if layers_dir:
        for v, (label, unit, group, source, pal) in VARS.items():
            p = next((os.path.join(layers_dir, v + ext) for ext in (".asc", ".tif")
                      if os.path.exists(os.path.join(layers_dir, v + ext))), None)
            if not p:
                print(f"  нет слоя {v}")
                continue
            a, t = read_raster(p)
            lo, hi = np.nanpercentile(a, [2, 98])
            add(v, a, t, lo, hi, pal, label=label, unit=unit, group=group,
                source=source, kind="env")

    import time
    write_json(os.path.join(out, "data", "layers.json"),
               {"bounds": bounds, "built": time.strftime("%Y%m%d%H%M%S"), "layers": meta})
    print(f"\nГотово: {len(meta)} слоёв -> {os.path.abspath(os.path.join(out, 'layers'))}")
    if not meta:
        print("ВНИМАНИЕ: ни одного слоя не найдено — проверьте --results-dir и --layers-dir")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maxent-results", help="maxentResults.csv")
    ap.add_argument("--points", help="исходная таблица locust_coord.csv")
    ap.add_argument("--results-dir", help="папка результатов MaxEnt с locusts_avg.asc")
    ap.add_argument("--layers-dir", help="папка с 22 слоями .asc")
    ap.add_argument("--out", default="docs")
    ap.add_argument("--width", type=int, default=2200, help="ширина PNG в пикселях")
    args = ap.parse_args()

    model = build_model(args.maxent_results, args.out) if args.maxent_results else None
    mj = os.path.join(args.out, "data", "model.json")
    if model is None and os.path.exists(mj):
        with open(mj, encoding="utf-8") as f:
            model = json.load(f)
    if args.points:
        build_points(args.points, args.out)
    if args.results_dir or args.layers_dir:
        build_layers(args.results_dir, args.layers_dir, args.out, model, args.width)


if __name__ == "__main__":
    main()
