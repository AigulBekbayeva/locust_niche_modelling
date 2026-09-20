# -*- coding: utf-8 -*-
"""
02_prepare_maxent.py — подготовка входных данных для MaxEnt (Java, AMNH).

Что делает:
  1. Читает GeoTIFF из ./gee_layers/ и проверяет, что сетки совпадают.
  2. Отбирает слабо коррелирующие переменные (|r| Спирмена < порога).
  3. Пишет выбранные слои в ESRI ASCII (.asc) -> ./maxent_layers/
  4. Чистит точки находок: убирает приблизительные координаты,
     оставляет 1 точку на ячейку для каждого вида, убирает точки вне слоёв.
  5. Строит bias-файл (плотность обследованных точек) для учёта
     неравномерности сбора -> ./maxent_layers/../bias.asc
  6. Пишет samples.csv (species,longitude,latitude) и команду запуска MaxEnt.

    pip install rasterio numpy pandas scipy
    python 02_prepare_maxent.py --csv locust_coord.csv --min-points 15
    python 02_prepare_maxent.py --keep-all      # все слои, без отсева по корреляции
    python 02_prepare_maxent.py --keep-all --one-species Acrididae   # все виды вместе
    python 02_prepare_maxent.py --keep-all --species-col "Растительный состав (название на латинском)"
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd
import rasterio
from scipy.ndimage import gaussian_filter

NODATA = -9999

# Приоритет при отсеве коррелирующих переменных: при конфликте остаётся та,
# что стоит выше (экологически интерпретируемые/прямые — выше).
PRIORITY = [
    "bio06_tmin", "bio05_tmax", "bio12_prec", "bio15_pseason", "bio04_tseason",
    "ndvi_spring", "soilm_spring", "snow_winter", "soil_sand", "soil_clay",
    "lc_crops", "lc_grass", "lc_bare", "lc_shrub", "slope", "elev",
    "prec_spring", "lst_day", "lst_night", "ndvi_season", "ndvi_max", "bio01_tmean",
]

COL_LAT, COL_LON = "Широта", "Долгота"
COL_SP, COL_NOTE = "Латинское название саранчового", "Примечание"


def read_occurrences(path, species_col=None):
    """Читает CSV в любой кодировке (UTF-8/UTF-8-BOM/cp1251) и с любым
    разделителем (, ; таб) и находит нужные столбцы по ключевым словам."""
    df = None
    for enc in ("utf-8-sig", "cp1251"):
        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise SystemExit(f"Не удалось прочитать {path} ни в UTF-8, ни в cp1251")
    df.columns = [str(c).strip() for c in df.columns]
    if species_col:                      # моделировать не саранчовых, а другой столбец
        if species_col not in df.columns:
            raise SystemExit(f"Нет столбца «{species_col}». Столбцы: {list(df.columns)}")
        df = df.drop(columns=[c for c in df.columns if c == COL_SP and c != species_col])
        df = df.rename(columns={species_col: COL_SP})

    wanted = {COL_LAT: ("широт", "lat"), COL_LON: ("долгот", "lon"),
              COL_SP: ("латинское название саранч", "species"), COL_NOTE: ("примеч",)}
    rename = {}
    for target, keys in wanted.items():
        hit = [c for c in df.columns if c == target] or \
              [c for c in df.columns if any(k in c.lower() for k in keys)]
        if hit:
            rename[hit[0]] = target
        elif target != COL_NOTE:
            raise SystemExit(f"Не найден столбец «{target}». Столбцы в файле: {list(df.columns)}")
    df = df.rename(columns=rename)
    if COL_NOTE not in df:
        df[COL_NOTE] = ""
    for c in (COL_LAT, COL_LON):   # десятичная запятая из Excel
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ".").str.strip(),
                              errors="coerce")
    return df


def read_stack(folder):
    files = sorted(glob.glob(os.path.join(folder, "*.tif")))
    if not files:
        raise SystemExit(f"Нет .tif в {folder}. Скачайте экспорт из Google Drive.")
    arrays, ref = {}, None
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0].split("-")[0]
        with rasterio.open(f) as src:
            meta = (src.width, src.height, tuple(round(v, 10) for v in src.transform[:6]))
            if ref is None:
                ref, profile = meta, src.profile
            elif meta != ref:
                raise SystemExit(f"{name}: сетка не совпадает с первым слоем {meta} != {ref}")
            a = src.read(1).astype("float32")
            nd = src.nodata if src.nodata is not None else NODATA
            a[(a == nd) | ~np.isfinite(a)] = np.nan
            arrays[name] = a
    print(f"Слоёв: {len(arrays)}, сетка {ref[0]}x{ref[1]}")
    return arrays, profile


def select_uncorrelated(arrays, thr, n_sample=20000, seed=1):
    names = list(arrays)
    stack = np.stack([arrays[n] for n in names])
    valid = np.all(np.isfinite(stack), axis=0)
    idx = np.flatnonzero(valid)
    rng = np.random.default_rng(seed)
    pick = rng.choice(idx, size=min(n_sample, idx.size), replace=False)
    df = pd.DataFrame(stack.reshape(len(names), -1)[:, pick].T, columns=names)
    corr = df.corr(method="spearman").abs()

    order = [n for n in PRIORITY if n in names] + [n for n in names if n not in PRIORITY]
    keep = []
    for n in order:
        if all(corr.loc[n, k] < thr for k in keep):
            keep.append(n)
    dropped = [n for n in order if n not in keep]
    return keep, dropped, corr, valid


def write_asc(path, arr, transform):
    x0, res, y0 = transform.c, transform.a, transform.f
    nrows, ncols = arr.shape
    out = np.where(np.isfinite(arr), arr, NODATA)
    with open(path, "w") as f:
        f.write(f"ncols {ncols}\nnrows {nrows}\n")
        f.write(f"xllcorner {x0:.10f}\nyllcorner {y0 - nrows * res:.10f}\n")
        f.write(f"cellsize {res:.12f}\nNODATA_value {NODATA}\n")
        np.savetxt(f, out, fmt="%.5g")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="locust_coord.csv")
    ap.add_argument("--layers", default="gee_layers")
    ap.add_argument("--out", default="maxent_input")
    ap.add_argument("--min-points", type=int, default=15,
                    help="минимум уникальных ячеек с находками для моделирования вида")
    ap.add_argument("--corr", type=float, default=0.7, help="порог |r| Спирмена")
    ap.add_argument("--keep-all", action="store_true",
                    help="оставить все слои без отсева по корреляции")
    ap.add_argument("--one-species", metavar="NAME", default=None,
                    help="объединить все виды под одним именем (напр. Acrididae)")
    ap.add_argument("--species-col", default=None,
                    help="столбец, который считать «видом» (по умолчанию — латинское название саранчового)")
    ap.add_argument("--keep-approx", action="store_true",
                    help="не удалять точки с приблизительно восстановленными координатами")
    ap.add_argument("--bias-sigma-km", type=float, default=50)
    args = ap.parse_args()

    os.makedirs(os.path.join(args.out, "layers"), exist_ok=True)
    arrays, profile = read_stack(args.layers)
    tr = profile["transform"]

    # --- коллинеарность
    keep, dropped, corr, valid = select_uncorrelated(arrays, args.corr)
    if args.keep_all:
        keep, dropped = list(arrays), []
    corr.round(3).to_csv(os.path.join(args.out, "correlation_spearman.csv"))
    print(f"Оставлено ({len(keep)}): {', '.join(keep)}")
    print(f"Исключено из-за |r|>={args.corr}: {', '.join(dropped) or '—'}")

    for n in keep:
        write_asc(os.path.join(args.out, "layers", f"{n}.asc"), arrays[n], tr)

    # --- точки находок
    df = read_occurrences(args.csv, args.species_col).dropna(subset=[COL_LAT, COL_LON, COL_SP])
    n0 = len(df)
    note = df[COL_NOTE].fillna("")
    if not args.keep_approx:
        df = df[~note.str.contains("восстановлены приблизительно")]
    print(f"\nЗаписей с координатами: {n0}; после удаления приблизительных: {len(df)}")

    inv = ~tr
    cols, rows = inv * (df[COL_LON].values, df[COL_LAT].values)
    df["col"], df["row"] = np.floor(cols).astype(int), np.floor(rows).astype(int)
    h, w = valid.shape
    inside = (df.row >= 0) & (df.row < h) & (df.col >= 0) & (df.col < w)
    df = df[inside]
    df = df[valid[df.row, df.col]]

    # bias: плотность всех обследованных ячеек (target-group), без учёта вида
    survey = np.zeros(valid.shape, dtype="float32")
    cells = df[["row", "col"]].drop_duplicates()
    survey[cells.row, cells.col] = 1
    sigma_px = args.bias_sigma_km / (tr.a * 111.0)
    bias = gaussian_filter(survey, sigma=sigma_px)
    bias = bias / bias.max() * 100 + 0.1          # MaxEnt требует >0
    bias[~valid] = np.nan
    write_asc(os.path.join(args.out, "bias.asc"), bias, tr)
    print(f"Обследованных ячеек: {len(cells)}; bias.asc: сглаживание σ={args.bias_sigma_km} км")

    if args.one_species:
        df[COL_SP] = args.one_species
        args.min_points = 1

    # прореживание: 1 точка на ячейку на вид; координаты — центр ячейки
    th = df.drop_duplicates(subset=[COL_SP, "row", "col"]).copy()
    counts = th[COL_SP].value_counts()
    species = counts[counts >= args.min_points].index
    th = th[th[COL_SP].isin(species)]
    lon, lat = tr * (th.col.values + 0.5, th.row.values + 0.5)
    samples = pd.DataFrame({
        "species": th[COL_SP].str.strip().str.replace(r"\s+", "_", regex=True).values,
        "longitude": np.round(lon, 6), "latitude": np.round(lat, 6)})
    samples.to_csv(os.path.join(args.out, "samples.csv"), index=False)
    counts.rename("n_cells").to_csv(os.path.join(args.out, "species_counts.csv"))

    print(f"\nВидов с ≥{args.min_points} ячейками: {len(species)}")
    print(counts[counts >= args.min_points].to_string())

    # --- команда запуска
    cmd = ("java -mx4g -jar maxent.jar "
           f"environmentallayers={args.out}/layers samplesfile={args.out}/samples.csv "
           + ("" if args.one_species else f"biasfile={args.out}/bias.asc ") +
           f"outputdirectory={args.out}/results "
           "replicates=5 replicatetype=crossvalidate betamultiplier=1.5 "
           "jackknife=true responsecurves=true pictures=true "
           "outputformat=cloglog writeplotdata=true redoifexists autorun")
    with open(os.path.join(args.out, "run_maxent.txt"), "w") as f:
        f.write(cmd + "\n")
    os.makedirs(os.path.join(args.out, "results"), exist_ok=True)
    print(f"\nЗапуск MaxEnt (положите maxent.jar рядом):\n{cmd}")


if __name__ == "__main__":
    main()
