const state = {
  config: null,
  map: null,
  watershedLayer: null,
  watershedById: new Map(),
  selected: null,
  selectedLayer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function request(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  let body = {};
  try { body = await response.json(); } catch (_) { /* HTTP status is enough. */ }
  if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`);
  return body;
}

function post(path, payload) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function setWorkflow(name) {
  $$(".workflow-tab").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  $$(".workflow").forEach((view) => view.classList.toggle("active", view.id === `${name}-view`));
  if (name === "planning" && state.map) setTimeout(() => state.map.invalidateSize(), 30);
  if (window.location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
}

function populateModels(config) {
  $$(".model-select").forEach((select) => {
    select.replaceChildren(...config.generation_models.map((model) => {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      option.selected = model === config.default_model;
      return option;
    }));
  });
}

function stageLabel(name) {
  return ({
    corpus_loaded: "Loaded indexed papers",
    query_parsed: "Parsed question and conditions",
    context_evidence_compared: "Compared supplied and derived context",
    query_embedded: "Embedded query",
    contexts_retrieved: "Matched study contexts",
    states_mapped: "Matched scientific states",
    claims_ranked: "Ranked evidence claims",
    paths_searched: "Searched mechanism paths",
    evidence_assembled: "Assembled direct and linked evidence",
    alternatives_retrieved: "Checked alternatives and contradictions",
    evidence_selected: "Selected source passages",
    evidence_trimmed: "Prepared grounded evidence package",
    answer_synthesized: "Generated grounded answer",
    artifacts_written: "Saved complete trace",
  })[name] || name.replaceAll("_", " ");
}

function renderRunning(container) {
  const node = $("#loading-template").content.cloneNode(true);
  container.replaceChildren(node);
}

function renderStages(container, job) {
  const list = container.querySelector(".stage-list");
  if (!list) return;
  list.replaceChildren(...job.stages.map((stage) => {
    const item = document.createElement("li");
    item.textContent = stageLabel(stage.name);
    return item;
  }));
  const current = container.querySelector(".run-status strong");
  if (current && job.stages.length) current.textContent = stageLabel(job.stages.at(-1).name);
}

function escapeHTML(value) {
  const span = document.createElement("span");
  span.textContent = value ?? "";
  return span.innerHTML;
}

function score(value) {
  return typeof value === "number" ? value.toFixed(3) : "unknown";
}

function renderResult(container, result) {
  const citations = Object.entries(result.provenance || {});
  const derived = result.derived_facets || [];
  const contexts = result.contexts || [];
  container.innerHTML = `
    <article class="answer-panel">
      <header><div><p class="eyebrow">Grounded answer</p><h2>${escapeHTML(result.question || "Result")}</h2></div><span class="mode-badge">${escapeHTML(result.mode || "query")}</span></header>
      <div class="answer-text">${escapeHTML(result.answer).replaceAll("\n", "<br>")}</div>
    </article>
    ${derived.length ? `<section class="result-section"><h3>Watershed context used</h3><div class="facet-grid">${derived.map((item) => `<article><span>${escapeHTML(item.domain)}</span><strong>${escapeHTML(item.notion)}</strong><p>${escapeHTML(item.description)}</p></article>`).join("")}</div></section>` : ""}
    <section class="result-section"><h3>Evidence trace</h3><div class="trace-grid">
      <article><strong>${contexts.length}</strong><span>top contexts shown</span>${contexts.slice(0, 3).map((item) => `<p>${escapeHTML(item.context_id)} · ${score(item.context_similarity?.overall_score)}</p>`).join("")}</article>
      <article><strong>${result.claims?.length || 0}</strong><span>top claims shown</span>${(result.claims || []).slice(0, 4).map((item) => `<p>${escapeHTML(item.claim_id)} · ${score(item.R_claim)}</p>`).join("")}</article>
      <article><strong>${result.paths?.length || 0}</strong><span>evidence paths shown</span><p>${escapeHTML(result.paths?.[0]?.claim_ids?.join(" → ") || "No mechanism path selected")}</p></article>
    </div></section>
    <section class="result-section"><h3>Cited sources</h3>${citations.length ? `<div class="citation-list">${citations.map(([claim, item]) => `<article><strong>${escapeHTML(claim)}</strong><p>${escapeHTML(item.title)} (${escapeHTML(item.year || "n.d.")})${item.pages?.length ? `, pages ${escapeHTML(item.pages.join(", "))}` : ""}</p><span>${escapeHTML(item.source_block_ids?.join(", ") || "")}</span></article>`).join("")}</div>` : `<p class="empty-copy">No cited Claim survived grounding validation.</p>`}</section>
    ${result.warnings?.length ? `<details class="warning-list"><summary>${result.warnings.length} pipeline notices</summary>${result.warnings.map((item) => `<p>${escapeHTML(item)}</p>`).join("")}</details>` : ""}
    <p class="artifact-path">Full trace: ${escapeHTML(result.artifact_dir)}</p>`;
}

function renderError(container, message) {
  container.innerHTML = `<article class="error-panel"><strong>Query failed</strong><p>${escapeHTML(message)}</p></article>`;
}

async function watchJob(jobId, container) {
  renderRunning(container);
  while (true) {
    const job = await request(`/api/jobs/${encodeURIComponent(jobId)}`);
    renderStages(container, job);
    if (job.status === "complete") {
      renderResult(container, job.result);
      return;
    }
    if (job.status === "failed") throw new Error(job.error || "Query failed");
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

async function submitJob(path, payload, container, button) {
  button.disabled = true;
  try {
    const job = await post(path, payload);
    await watchJob(job.id, container);
  } catch (error) {
    renderError(container, error.message);
  } finally {
    button.disabled = false;
  }
}

function watershedStyle(feature) {
  const selected = feature.properties.wsconc === state.selected;
  return {
    color: selected ? "#b24c2f" : "#597267",
    weight: selected ? 2.4 : 0.55,
    fillColor: selected ? "#d77852" : "#92b7a2",
    fillOpacity: selected ? 0.68 : 0.24,
  };
}

function selectWatershed(id, layer, fit = false) {
  if (state.selectedLayer) state.watershedLayer.resetStyle(state.selectedLayer);
  state.selected = id;
  state.selectedLayer = layer;
  layer.setStyle(watershedStyle(layer.feature));
  layer.bringToFront();
  const p = layer.feature.properties;
  $("#selected-watershed").innerHTML = `<strong>${escapeHTML(id)}</strong><span>${Number(p.area_sqkm).toLocaleString(undefined, { maximumFractionDigits: 1 })} km² · basin ${escapeHTML(p.bacode)} · sub-basin ${escapeHTML(p.sbcode)}</span>`;
  $("#planning-submit").disabled = false;
  if (fit) state.map.fitBounds(layer.getBounds(), { padding: [30, 30], maxZoom: 8 });
}

async function initializeMap() {
  if (!window.L) throw new Error("Leaflet could not be loaded. Check the network connection and reload.");
  state.map = L.map("watershed-map", { zoomControl: true, minZoom: 4 }).setView([22.8, 79.2], 5);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 12,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);
  const response = await fetch("/api/watersheds");
  if (!response.ok) throw new Error("Watershed boundaries could not be loaded.");
  const geojson = await response.json();
  state.watershedLayer = L.geoJSON(geojson, {
    style: watershedStyle,
    onEachFeature: (feature, layer) => {
      const id = feature.properties.wsconc;
      state.watershedById.set(id, layer);
      layer.bindTooltip(`${id} · ${Number(feature.properties.area_sqkm).toFixed(1)} km²`, { sticky: true });
      layer.on("click", () => selectWatershed(id, layer));
    },
  }).addTo(state.map);
  $("#map-status").textContent = `${geojson.features.length.toLocaleString()} watersheds loaded. Click a boundary to select it.`;
}

function findWatershed() {
  const id = $("#watershed-search").value.trim().toUpperCase();
  const layer = state.watershedById.get(id);
  if (!layer) {
    $("#map-status").textContent = id ? `Watershed ${id} was not found.` : "Enter a watershed ID.";
    return;
  }
  selectWatershed(id, layer, true);
  $("#map-status").textContent = `Selected ${id}.`;
}

async function initialize() {
  $$(".workflow-tab").forEach((button) => button.addEventListener("click", () => setWorkflow(button.dataset.view)));
  state.config = await request("/api/config");
  populateModels(state.config);
  const ready = state.config.graph_ready && state.config.koppen_ready && state.config.watersheds.ready;
  $("#system-dot").classList.toggle("ready", ready);
  $("#system-label").textContent = ready ? "Corpus and watershed data ready" : "Setup required";
  setWorkflow(window.location.hash === "#planning" ? "planning" : "process");

  $("#process-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submitJob("/api/process-query", {
      question: $("#process-question").value,
      model: $("#process-model").value,
    }, $("#process-result"), event.submitter);
  });
  $("#planning-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submitJob("/api/land-use-plan", {
      watershed_id: state.selected,
      objective: $("#planning-objective").value,
      additional_information: $("#additional-information").value,
      model: $("#planning-model").value,
    }, $("#planning-result"), event.submitter);
  });
  $("#watershed-find").addEventListener("click", findWatershed);
  $("#watershed-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); findWatershed(); }
  });
  await initializeMap();
}

initialize().catch((error) => {
  $("#system-label").textContent = error.message;
  $("#map-status").textContent = error.message;
});
