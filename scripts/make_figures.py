# -*- coding: utf-8 -*-
"""make_figures.py — графики для README по results/locusts/maxentResults.csv."""
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False})
INK, STEPPE, STRAW, GREY = "#1e2a24", "#2f5d50", "#c9a227", "#9aa597"

LAB = {
    "bio01_tmean": "Ср. годовая t (bio01)", "bio04_tseason": "Сезонность t (bio04)",
    "bio05_tmax": "Макс. t тёплого мес. (bio05)", "bio06_tmin": "Мин. t холодного мес. (bio06)",
    "bio12_prec": "Годовые осадки (bio12)", "bio15_pseason": "Сезонность осадков (bio15)",
    "elev": "Высота", "slope": "Уклон", "lc_bare": "Доля открытого грунта",
    "lc_crops": "Доля пашни", "lc_grass": "Доля травяного покрова", "lc_shrub": "Доля кустарников",
    "lst_day": "LST днём", "lst_night": "LST ночью", "ndvi_max": "NDVI макс.",
    "ndvi_season": "NDVI за сезон", "ndvi_spring": "NDVI весной", "prec_spring": "Осадки весной",
    "soilm_spring": "Влажность почвы весной", "snow_winter": "Снег зимой",
    "soil_sand": "Песок в почве", "soil_clay": "Глина в почве",
}

df = pd.read_csv("results/locusts/maxentResults.csv").copy()
is_avg = df.Species.str.contains("average")
avg, reps = df[is_avg].iloc[0], df[~is_avg]
VARS = [c.replace(" contribution", "") for c in df.columns if c.endswith(" contribution")]

# 1. AUC ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7.5, 2.6))
ax.scatter(reps["Training AUC"], [1] * len(reps), s=60, facecolor="none", edgecolor=INK, label="обучение")
ax.scatter(reps["Test AUC"], [0] * len(reps), s=70, color=STEPPE, label="тест")
sd = reps["Test AUC"].std(ddof=0)
ax.barh(0, 2 * sd, left=avg["Test AUC"] - sd, height=.5, color=STEPPE, alpha=.15)
ax.vlines(avg["Test AUC"], -.35, .35, color=INK, lw=2.2)
ax.vlines(avg["Training AUC"], .7, 1.3, color=INK, lw=1.4)
ax.text(avg["Test AUC"], -.62, f"{avg['Test AUC']:.3f} ± {sd:.3f}", ha="center", fontsize=9, fontweight="bold")
ax.text(reps["Training AUC"].max() + .012, 1, f"{avg['Training AUC']:.3f}", va="center", fontsize=9)
for x, t in [(.5, "случайная модель"), (.7, "приемлемо"), (.8, "хорошо")]:
    ax.axvline(x, color=GREY, lw=.8, ls=":")
    ax.text(x + .004, 1.62, t, fontsize=8, color=GREY)
ax.set_yticks([0, 1]); ax.set_yticklabels(["Тестовый AUC", "Обучающий AUC"])
ax.set_xlim(.48, 1.0); ax.set_ylim(-.9, 1.9); ax.set_xlabel("AUC")
ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
ax.set_title("Точность модели: 5-кратная кросс-валидация, 93 точки", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig("figures/auc.png", dpi=160)

# 2. Вклад переменных --------------------------------------------------------
d = pd.DataFrame({"pc": [avg[f"{v} contribution"] for v in VARS],
                  "pi": [avg[f"{v} permutation importance"] for v in VARS]}, index=VARS)
d = d.assign(s=d.pc + d.pi).sort_values("s")
d = d[d.s >= 1]
fig, ax = plt.subplots(figsize=(8, 6.2))
y = np.arange(len(d))
ax.barh(y + .2, d.pc, .4, color=STEPPE, label="Вклад в обучение, %")
ax.barh(y - .2, d.pi, .4, color=STRAW, label="Пермутационная важность, %")
for yi, (pc, pi) in enumerate(zip(d.pc, d.pi)):
    ax.text(pc + .4, yi + .2, f"{pc:.1f}", va="center", fontsize=7.5, color=INK)
    ax.text(pi + .4, yi - .2, f"{pi:.1f}", va="center", fontsize=7.5, color=INK)
ax.set_yticks(y); ax.set_yticklabels([LAB[v] for v in d.index], fontsize=9)
ax.set_xlabel("%"); ax.legend(frameon=False, loc="lower right", fontsize=9)
ax.set_title("Вклад переменных, среднее по 5 повторам", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig("figures/variable_importance.png", dpi=160)

# 3. Jackknife: AUC с одной переменной и без неё ------------------------------
only = pd.Series({v: reps[f"AUC with only {v}"].mean() for v in VARS})
without = pd.Series({v: reps[f"AUC without {v}"].mean() for v in VARS})
order = only.sort_values().index
fig, ax = plt.subplots(figsize=(8, 6.6))
y = np.arange(len(order))
ax.barh(y, only[order] - .5, left=.5, color=[STEPPE if v >= .6 else "#c9d0c2" for v in only[order]],
        label="модель только с этой переменной")
ax.scatter(without[order], y, marker="|", s=120, color=INK, label="модель без этой переменной")
ax.axvline(avg["Test AUC"], color=INK, ls="--", lw=1)
ax.text(avg["Test AUC"] - .005, len(order) - .2, f"полная модель {avg['Test AUC']:.3f}", ha="right", fontsize=8)
ax.axvline(.5, color=GREY, lw=.8)
ax.set_yticks(y); ax.set_yticklabels([LAB[v] for v in order], fontsize=8.5)
ax.set_xlim(.44, .82); ax.set_xlabel("Тестовый AUC (среднее по 5 повторам)")
ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(.45, -.08), ncol=2, fontsize=8.5)
ax.set_title("Jackknife: информативность переменных по тестовым данным", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig("figures/jackknife.png", dpi=160)
print("готово: figures/auc.png, variable_importance.png, jackknife.png")
