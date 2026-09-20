/* MaxEnt web map: locust habitat suitability in Kazakhstan */
(function () {
  "use strict";

  const state = { model: null, layers: null, bounds: null, overlay: null, active: null,
                  opacity: 0.85, showAllEnv: false };
  const $ = (id) => document.getElementById(id);

  /* English labels for every layer (override labels stored in the data files) */
  const VAR_META = {
    suitability: { label: "Habitat suitability", unit: "cloglog, 0–1" },
    binary: { label: "Suitable area", unit: "10th percentile training presence threshold" },
    sd: { label: "Prediction uncertainty", unit: "SD across 5 replicates" },
    bio01_tmean: { label: "Annual mean temperature", unit: "°C", group: "Climate", source: "WorldClim bio01" },
    bio04_tseason: { label: "Temperature seasonality", unit: "SD, °C", group: "Climate", source: "WorldClim bio04" },
    bio05_tmax: { label: "Max temperature of warmest month", unit: "°C", group: "Climate", source: "WorldClim bio05" },
    bio06_tmin: { label: "Min temperature of coldest month", unit: "°C", group: "Climate", source: "WorldClim bio06" },
    bio12_prec: { label: "Annual precipitation", unit: "mm", group: "Climate", source: "WorldClim bio12" },
    bio15_pseason: { label: "Precipitation seasonality", unit: "CV, %", group: "Climate", source: "WorldClim bio15" },
    lst_day: { label: "Daytime land surface temperature", unit: "°C", group: "Satellite", source: "MODIS MOD11A2, Apr–Sep 2015–2024" },
    lst_night: { label: "Night-time land surface temperature", unit: "°C", group: "Satellite", source: "MODIS MOD11A2, Apr–Sep 2015–2024" },
    ndvi_spring: { label: "Spring NDVI", unit: "NDVI", group: "Satellite", source: "MODIS MOD13A2, Apr–Jun 2015–2024" },
    ndvi_season: { label: "Growing-season NDVI", unit: "NDVI", group: "Satellite", source: "MODIS MOD13A2, Apr–Sep 2015–2024" },
    ndvi_max: { label: "Maximum NDVI", unit: "NDVI", group: "Satellite", source: "MODIS MOD13A2, Apr–Sep 2015–2024" },
    prec_spring: { label: "Spring precipitation", unit: "mm", group: "Reanalysis", source: "ERA5-Land, Apr–Jun 2015–2024" },
    soilm_spring: { label: "Spring soil moisture", unit: "m³/m³", group: "Reanalysis", source: "ERA5-Land, 0–7 cm layer" },
    snow_winter: { label: "Winter snow depth", unit: "cm", group: "Reanalysis", source: "ERA5-Land, Dec–Feb 2015–2024" },
    elev: { label: "Elevation", unit: "m", group: "Terrain", source: "SRTM 90 m" },
    slope: { label: "Slope", unit: "°", group: "Terrain", source: "SRTM 90 m" },
    lc_grass: { label: "Grass cover fraction", unit: "%", group: "Land cover", source: "Copernicus Land Cover 2019" },
    lc_crops: { label: "Cropland fraction", unit: "%", group: "Land cover", source: "Copernicus Land Cover 2019" },
    lc_shrub: { label: "Shrub cover fraction", unit: "%", group: "Land cover", source: "Copernicus Land Cover 2019" },
    lc_bare: { label: "Bare ground fraction", unit: "%", group: "Land cover", source: "Copernicus Land Cover 2019" },
    soil_sand: { label: "Soil sand content", unit: "%", group: "Soil", source: "OpenLandMap" },
    soil_clay: { label: "Soil clay content", unit: "%", group: "Soil", source: "OpenLandMap" },
  };
  const meta = (id) => VAR_META[id] || (state.layers[id] || {});
  const fmt = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x)) ? "—"
    : Number(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ---------- map ---------- */
  const map = L.map("map", { zoomControl: true, minZoom: 3, maxZoom: 13, zoomSnap: 0.25 })
    .fitBounds([[40.5, 46.4], [55.5, 87.4]]);
  const bases = {
    light: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }),
    sat: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      attribution: "Esri, Maxar, Earthstar Geographics", maxZoom: 19 }),
    topo: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap, SRTM, &copy; OpenTopoMap", maxZoom: 17 }),
  };
  let base = bases.light.addTo(map);
  document.querySelectorAll('input[name="base"]').forEach((r) => r.addEventListener("change", (e) => {
    map.removeLayer(base); base = bases[e.target.value].addTo(map); base.bringToBack();
  }));
  map.createPane("rasters").style.zIndex = 350;
  map.createPane("points").style.zIndex = 620;

  /* ---------- data ---------- */
  const getJSON = (url) => fetch(url, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (location.protocol === "file:") {
    document.querySelector(".intro").insertAdjacentHTML("beforeend",
      `<p class="empty">This page was opened as a local file, so the browser blocks the data files. ` +
      `Open it from GitHub Pages, or run <code>python -m http.server</code> inside the docs folder and go to http://localhost:8000.</p>`);
  }
  Promise.all([getJSON("data/model.json"), getJSON("data/layers.json"), getJSON("data/points.geojson")])
    .then(([model, layers, points]) => {
      state.model = model;
      state.layers = layers && layers.layers ? layers.layers : {};
      state.bounds = layers && layers.bounds;
      state.version = (layers && layers.built) || "";
      if (model) renderModel(model);
      renderResults();
      renderEnv();
      if (points) renderPoints(points);
      const first = ["suitability", "binary", "sd"].find((k) => state.layers[k]);
      if (first) setActive(first);
      else renderLegend();
    });

  /* ---------- accuracy ---------- */
  function renderModel(m) {
    $("lede").textContent = `A MaxEnt model built from ${m.n_total} locust and grasshopper occurrence sites and ${m.variables.length} environmental layers: climate, MODIS satellite data, ERA5-Land reanalysis, terrain, land cover and soils.`;
    $("aucChart").innerHTML = aucSVG(m);
    const q = m.auc_test >= 0.8 ? "good" : m.auc_test >= 0.7 ? "acceptable" : "weak";
    $("accText").innerHTML =
      `AUC measures how well the model separates occurrence sites from random background points: 0.5 is no better than chance, 1 is perfect. ` +
      `On held-out sites (5-fold cross-validation) AUC = <b>${fmt(m.auc_test, 3)} ± ${fmt(m.auc_test_sd, 3)}</b>, which is ${q}. ` +
      `At a threshold of ${fmt(m.thr_10ptp)}, ${fmt(m.thr_10ptp_area * 100, 0)}% of the area is classed as suitable, ` +
      `and ${fmt(m.thr_10ptp_omission * 100, 0)}% of held-out sites fall outside it.`;
  }

  function aucSVG(m) {
    const W = 340, x0 = 14, x1 = W - 14, lo = 0.5, hi = 1.0;
    const X = (v) => x0 + (Math.min(Math.max(v, lo), hi) - lo) / (hi - lo) * (x1 - x0);
    const yTr = 70, yTe = 92, yAx = 112;
    let s = `<svg viewBox="0 0 ${W} 138" role="img" aria-label="Test AUC ${m.auc_test} plus or minus ${m.auc_test_sd}">`;
    s += `<text class="big" x="${x0}" y="30">${fmt(m.auc_test, 2)}</text>`;
    s += `<text class="big-sub" x="${x0 + 72}" y="22">mean test AUC</text>`;
    s += `<text class="big-sub" x="${x0 + 72}" y="37">across ${m.replicates} replicates, ± ${fmt(m.auc_test_sd, 3)}</text>`;
    // ± SD band
    s += `<rect x="${X(m.auc_test - m.auc_test_sd)}" y="${yTe - 9}" width="${X(m.auc_test + m.auc_test_sd) - X(m.auc_test - m.auc_test_sd)}" height="18" rx="3" fill="#2f5d50" opacity=".13"/>`;
    s += `<line x1="${x0}" x2="${x1}" y1="${yAx}" y2="${yAx}" stroke="#9aa597"/>`;
    [0.5, 0.6, 0.7, 0.8, 0.9, 1.0].forEach((t) => {
      s += `<line x1="${X(t)}" x2="${X(t)}" y1="${yAx}" y2="${yAx + 4}" stroke="#9aa597"/>`;
      s += `<text x="${X(t)}" y="${yAx + 16}" text-anchor="middle">${fmt(t, 1)}</text>`;
    });
    s += `<text x="${x0}" y="${yAx + 28}" text-anchor="start">chance</text>`;
    s += `<text x="${x1}" y="${yAx + 28}" text-anchor="end">perfect</text>`;
    s += `<text x="${x1}" y="${yTr + 4}" text-anchor="end">training</text>`;
    s += `<text x="${x1}" y="${yTe + 4}" text-anchor="end">test</text>`;
    m.auc_train_reps.forEach((v) => { s += `<circle cx="${X(v)}" cy="${yTr}" r="4" fill="none" stroke="#4c5a52" stroke-width="1.3"/>`; });
    m.auc_test_reps.forEach((v) => { s += `<circle cx="${X(v)}" cy="${yTe}" r="4.5" fill="#2f5d50"/>`; });
    s += `<line x1="${X(m.auc_test)}" x2="${X(m.auc_test)}" y1="${yTe - 12}" y2="${yTe + 12}" stroke="#1e2a24" stroke-width="2"/>`;
    s += `<line x1="${X(m.auc_train)}" x2="${X(m.auc_train)}" y1="${yTr - 9}" y2="${yTr + 9}" stroke="#4c5a52" stroke-width="1.5"/>`;
    return s + "</svg>";
  }

  /* ---------- layer lists ---------- */
  const RESULT_ROWS = [
    ["suitability", "Habitat suitability", "Mean of 5 replicates, cloglog scale 0–1"],
    ["binary", "Suitable area", "Suitability above the 10th percentile training presence threshold"],
    ["sd", "Prediction uncertainty", "Spread between replicates: higher means less reliable"],
  ];

  function row(id, name, meta, extra = "", value = "") {
    const ok = !!state.layers[id];
    const b = document.createElement("button");
    b.type = "button"; b.className = "layer-row"; b.dataset.id = id;
    b.setAttribute("role", "radio"); b.setAttribute("aria-checked", "false");
    if (!ok) b.setAttribute("aria-disabled", "true");
    b.innerHTML = `<span class="layer-name">${esc(name)}</span><span class="layer-val">${value}</span>` +
      `<span class="layer-meta">${esc(meta)}${ok ? "" : " · layer not built yet"}</span>${extra}`;
    b.addEventListener("click", () => { if (ok) setActive(id); });
    return b;
  }

  function renderResults() {
    const box = $("resultList"); box.innerHTML = "";
    RESULT_ROWS.forEach(([id, n, m]) => box.appendChild(row(id, n, m)));
    if (!Object.keys(state.layers).length) {
      box.insertAdjacentHTML("beforeend", `<p class="empty">Raster layers are not built yet. Run scripts/build_web.py with the MaxEnt output folder and the layers folder.</p>`);
    }
  }

  function renderEnv() {
    const box = $("envList"); box.innerHTML = "";
    const vars = state.model ? state.model.variables : [];
    const max = Math.max(1, ...vars.map((v) => Math.max(v.contribution, v.permutation)));
    const shown = state.showAllEnv ? vars : vars.slice(0, 8);
    shown.forEach((v) => {
      const bars = `<span class="bars" aria-hidden="true">` +
        `<span class="bar c"><i style="width:${v.contribution / max * 100}%"></i></span>` +
        `<span class="bar p"><i style="width:${v.permutation / max * 100}%"></i></span></span>`;
      const val = `${fmt(v.contribution, 1)} / ${fmt(v.permutation, 1)}%`;
      const vm = VAR_META[v.id] || v;
      const b = row(v.id, vm.label, `${vm.group}: ${vm.source}`, bars, val);
      b.setAttribute("aria-label", `${v.label}: contribution ${v.contribution}%, permutation importance ${v.permutation}%`);
      box.appendChild(b);
    });
    const more = $("envMore");
    more.hidden = vars.length <= 8;
    more.textContent = state.showAllEnv ? "Show top 8 only" : `Show all ${vars.length}`;
    more.onclick = () => { state.showAllEnv = !state.showAllEnv; renderEnv(); markActive(); };
  }

  function markActive() {
    document.querySelectorAll(".layer-row").forEach((b) =>
      b.setAttribute("aria-checked", String(b.dataset.id === state.active)));
  }

  /* ---------- raster ---------- */
  function setActive(id) {
    const L0 = state.layers[id];
    if (!L0 || !state.bounds) return;
    state.active = id;
    if (state.overlay) map.removeLayer(state.overlay);
    const src = state.version ? `${L0.file}?v=${state.version}` : L0.file;
    state.overlay = L.imageOverlay(src, state.bounds, { pane: "rasters", opacity: state.opacity,
      alt: meta(state.active).label, interactive: false }).addTo(map);
    markActive();
    renderLegend();
  }

  function renderLegend() {
    const el = $("legend");
    const L0 = state.active && state.layers[state.active];
    let h = "";
    if (L0) {
      const v = state.model && state.model.variables.find((x) => x.id === state.active);
      const mt = meta(state.active);
      h += `<h3>${esc(mt.label)}</h3>`;
      h += `<p class="sub">${esc(mt.unit || "")}${v ? `${mt.unit ? " · " : ""}contribution ${fmt(v.contribution, 1)}%, permutation ${fmt(v.permutation, 1)}%` : ""}</p>`;
      if (state.active === "binary") {
        h += `<div class="swatch"><i style="background:${L0.colors[0]}"></i>suitable (≥ ${fmt(L0.min)})</div>`;
      } else {
        const dec = Math.abs(L0.max - L0.min) < 5 ? 2 : 0;
        h += `<div class="ramp" style="background:linear-gradient(90deg,${L0.colors.join(",")})"></div>`;
        h += `<div class="ramp-ticks"><span>${fmt(L0.min, dec)}</span><span>${fmt((L0.min + L0.max) / 2, dec)}</span><span>${fmt(L0.max, dec)}</span></div>`;
        if (L0.kind === "result" && state.active === "suitability") {
          h += `<div class="ramp-ticks"><span>low</span><span>high</span></div>`;
        }
      }
      h += `<label class="opacity">Opacity<input type="range" min="0" max="100" value="${Math.round(state.opacity * 100)}" id="opacity" aria-label="Layer opacity"></label>`;
    }
    if ($("showPoints").checked && state.pointsLayer) {
      h += `<div class="pts"><span class="pt" style="width:8px;height:8px"></span><span class="pt" style="width:14px;height:14px"></span>survey sites, sized by abundance<span class="pt hollow" style="width:10px;height:10px;margin-left:6px"></span>approx. location</div>`;
    }
    el.innerHTML = h;
    const op = $("opacity");
    if (op) op.addEventListener("input", (e) => {
      state.opacity = e.target.value / 100;
      if (state.overlay) state.overlay.setOpacity(state.opacity);
    });
  }

  /* ---------- survey sites ---------- */
  function renderPoints(gj) {
    const n = gj.features.length;
    const recs = gj.features.reduce((a, f) => a + f.properties.records.length, 0);
    $("pointsCount").textContent = `(${n} sites, ${recs} records)`;
    const small = window.innerWidth < 760;
    const maxT = Math.max(...gj.features.map((f) => f.properties.total || 0), 1);
    state.pointsLayer = L.geoJSON(gj, {
      pane: "points",
      pointToLayer: (f, ll) => L.circleMarker(ll, {
        pane: "points",
        radius: (small ? 2.5 : 3.5) + (small ? 5 : 8) * Math.sqrt((f.properties.total || 0) / maxT),
        color: f.properties.approx ? "#1e2a24" : "#ffffff", weight: 1.5,
        fillColor: f.properties.approx ? "#ffffff" : "#1e2a24", fillOpacity: 0.95,
      }),
      onEachFeature: (f, layer) => {
        layer.bindPopup(() => popup(f.properties), { maxWidth: 340 });
        layer.bindTooltip(esc(f.properties.place), { direction: "top", offset: [0, -6] });
      },
    }).addTo(map);
    $("showPoints").addEventListener("change", (e) => {
      if (e.target.checked) state.pointsLayer.addTo(map); else map.removeLayer(state.pointsLayer);
      renderLegend();
    });
    renderLegend();
  }

  function popup(p) {
    const rows = p.records.map(([lat, c]) =>
      `<tr><td class="lat">${esc(lat)}</td><td class="n">${c === null ? "—" : fmt(c, 0)}</td></tr>`).join("");
    return `<div class="pp"><h4>${esc(p.place)}</h4>` +
      `<p class="where">${esc(p.district)}, ${esc(p.region)}</p>` +
      `<dl><dt>Habitat</dt><dd>${esc(p.habitat)}</dd>` +
      `<dt>Vegetation</dt><dd class="lat">${esc(p.vegetation)}</dd>` +
      `<dt>Agroclimate</dt><dd>${esc(p.zone)}</dd></dl>` +
      `<div class="list"><table><tr><td class="muted">Species (${p.n_species})</td><td class="n muted">ind./hour</td></tr>${rows}</table></div>` +
      (p.approx ? `<p class="warn">Location approximated from the district name.</p>` : "") +
      `</div>`;
  }

  /* ---------- repository link and mobile panel ---------- */
  const m = location.hostname.match(/^([^.]+)\.github\.io$/);
  if (m) {
    const repo = location.pathname.split("/").filter(Boolean)[0];
    $("repoLink").href = `https://github.com/${m[1]}/${repo || ""}`;
  }
  $("panelToggle").addEventListener("click", () => {
    const p = $("panel"), c = p.classList.toggle("collapsed");
    $("panelToggle").setAttribute("aria-expanded", String(!c));
    setTimeout(() => map.invalidateSize(), 260);
  });
})();
