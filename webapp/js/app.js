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

function populateSystems(config) {
  $$(".system-select").forEach((select) => {
    select.replaceChildren(...config.answer_systems.map((system) => {
      const option = document.createElement("option");
      option.value = system.id;
      option.textContent = system.label;
      option.selected = system.id === config.default_system;
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
    watershed_enriched: "Derived watershed context",
    graphrag_retrieval_started: "Searching GraphRAG communities",
    graphrag_answer_synthesized: "Generated GraphRAG answer",
    plain_rag_retrieval_started: "Searching source passages",
    plain_rag_answer_synthesized: "Generated passage RAG answer",
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

function normalizeAnswerMarkdown(value) {
  return String(value ?? "")
    .replace(/^\s*(?:#+\s*)?1\.\s*Land use recommendation\s*$/gim, "## Land use recommendation")
    .replace(/^\s*(?:#+\s*)?2\.\s*Limitations(?: and other important notes)?\s*$/gim, "## Limitations and other important notes");
}

function citationKey(value) {
  return value.includes(":") ? value.split(":").at(-1) : value;
}

function renderMarkdown(value, citationDetails = {}) {
  const source = normalizeAnswerMarkdown(value).replace(
    /\b(?:P\d{6}:)?P\d{6}_CL\d+\b|\bS\d+\b/g,
    (citation) => {
      const key = citationKey(citation);
      return citationDetails[key]
        ? `<a class="citation-link" data-citation-id="${key}" href="#citation-${key}">${citation}</a>`
        : citation;
    },
  );
  if (!window.marked?.parse || !window.DOMPurify?.sanitize) {
    return escapeHTML(source).replaceAll("\n", "<br>");
  }
  const parsed = window.marked.parse(source, { gfm: true, breaks: true });
  return window.DOMPurify.sanitize(parsed, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style"],
    FORBID_ATTR: ["style"],
  });
}

function score(value) {
  return typeof value === "number" ? value.toFixed(3) : "unknown";
}

const facetGuidance = {
  "aridity regime": {
    meaning: "The long-term balance between precipitation and potential evapotranspiration. P/PET indicates how much atmospheric water demand can be met by precipitation.",
    relevance: "Moisture availability can limit evapotranspiration, irrigation cooling, vegetation response, and moisture recycling. ClimateKG uses this value when comparing the watershed with the hydroclimatic setting of published findings.",
  },
  "koppen-geiger climate regime": {
    meaning: "A broad climate classification based on long-term temperature and precipitation patterns. Percentages show the share of the watershed in each class.",
    relevance: "This provides a coarse climate analogue for ranking study settings. It helps identify evidence from broadly similar regimes, but does not by itself establish that two locations are environmentally equivalent.",
  },
  "background wind regime": {
    meaning: "The season's area-averaged 10 m wind direction, speed, and directional persistence. Direction is reported as where the wind comes from; persistence describes how consistently it maintains that direction.",
    relevance: "Background flow affects local advection, downwind influence, and whether land-surface contrasts can organize patch or edge circulations. ClimateKG compares the matching season and preserves wind direction as a separate spatial condition.",
  },
  "terrain setting": {
    meaning: "The watershed's elevation distribution, local relief, and typical slope. The p10-p90 range excludes the lowest and highest ten percent of elevation values.",
    relevance: "Terrain can redirect airflow, create windward and leeward differences, and make evidence from flat or idealized studies less transferable. These values help screen and rank those study contexts.",
  },
  "land-cover composition": {
    meaning: "The fraction of the watershed occupied by the main mapped land-cover classes in the stated reference year.",
    relevance: "This is the baseline from which a land-use intervention would begin. ClimateKG uses it to compare study land surfaces and to avoid treating an intervention as transferable when the relevant source or replacement cover is absent. It describes composition, not patch shape or edge arrangement.",
  },
};

function guidanceForFacet(item) {
  const notion = (item.notion || "").toLowerCase();
  if (notion.includes("background wind regime")) return facetGuidance["background wind regime"];
  return facetGuidance[notion] || {
    meaning: "A measured or derived environmental property of the selected watershed.",
    relevance: "ClimateKG compares this property with conditions reported by indexed studies. It is a retrieval and applicability signal, not a probability that a scientific finding is true.",
  };
}

function showFacetDetails(item) {
  const dialog = $("#facet-dialog");
  const guidance = guidanceForFacet(item);
  const source = item.source || {};
  $("#facet-dialog-domain").textContent = item.domain || "watershed context";
  $("#facet-dialog-title").textContent = item.notion || "Context detail";
  $("#facet-dialog-body").innerHTML = `
    <section><h3>Value used</h3><p>${escapeHTML(item.description)}</p></section>
    <section><h3>What it means</h3><p>${escapeHTML(guidance.meaning)}</p></section>
    <section><h3>Why it matters here</h3><p>${escapeHTML(guidance.relevance)}</p><p class="ranking-note">This is a context-matching and applicability signal, not a probability that a scientific finding is true.</p></section>
    <section class="source-detail"><h3>Data provenance</h3>
      <dl>
        <dt>Dataset</dt><dd>${escapeHTML(source.dataset || "Not recorded")}</dd>
        <dt>Version</dt><dd>${escapeHTML(source.version || "Not recorded")}</dd>
        <dt>Period</dt><dd>${escapeHTML(source.temporal_window || "Not specified")}</dd>
        <dt>Method</dt><dd>${escapeHTML(source.method || "Not recorded")}</dd>
      </dl>
    </section>`;
  dialog.showModal();
}

function endpointText(endpoint) {
  if (!endpoint) return "Not recorded";
  if (typeof endpoint === "string") return endpoint;
  return endpoint.state ? `${endpoint.concept} (${endpoint.state})` : endpoint.concept;
}

function facetText(item) {
  if (typeof item === "string") return item;
  return `${item.domain} / ${item.notion}: ${item.description}`;
}

function showCitationDetails(item) {
  const dialog = $("#citation-dialog");
  const paper = item.paper || {};
  const claim = item.claim || {};
  const from = claim.from || claim.from_state_id;
  const to = claim.to || claim.to_state_id;
  const contexts = item.contexts || [];
  const conditioning = item.conditioning_facets || [];
  const contextFacets = item.context_facets || [];
  const blocks = item.source_blocks || [];
  $("#citation-dialog-domain").textContent = item.kind === "source_excerpt" ? "Source excerpt" : "Scientific evidence";
  $("#citation-dialog-title").textContent = item.citation_id || claim.id || "Citation details";
  $("#citation-dialog-body").innerHTML = `
    <section><h3>Paper</h3><p><strong>${escapeHTML(paper.title || "Title not recorded")}</strong>${paper.year ? ` (${escapeHTML(paper.year)})` : ""}</p><p class="citation-meta">${escapeHTML(paper.id || "")}${paper.doi ? ` · DOI ${escapeHTML(paper.doi)}` : ""}</p></section>
    ${claim.description ? `<section><h3>Claim</h3><p>${escapeHTML(claim.description)}</p><dl class="evidence-dl"><dt>From</dt><dd>${escapeHTML(endpointText(from))}</dd><dt>Relation</dt><dd>${escapeHTML(claim.relation || "Not recorded")}</dd><dt>To</dt><dd>${escapeHTML(endpointText(to))}</dd><dt>Evidence role</dt><dd>${escapeHTML(claim.evidence_role || "Not recorded")}</dd></dl></section>` : ""}
    ${contexts.length ? `<section><h3>Supporting study context</h3>${contexts.map((context) => `<article class="evidence-detail"><strong>${escapeHTML(context.label)}</strong><p>${escapeHTML(context.description || "")}</p><span>${escapeHTML(context.id)}</span></article>`).join("")}</section>` : ""}
    ${conditioning.length ? `<section><h3>Conditioning facets</h3>${conditioning.map((facet) => `<p>${escapeHTML(facetText(facet))}</p>`).join("")}</section>` : ""}
    ${contextFacets.length ? `<details class="all-context-facets"><summary>All facets in the supporting context</summary>${contextFacets.map((facet) => `<p>${escapeHTML(facetText(facet))}</p>`).join("")}</details>` : ""}
    <section><h3>Supporting source passages</h3>${blocks.length ? blocks.map((block) => `<article class="source-block-detail"><strong>${escapeHTML(block.id)}${block.page ? ` · page ${escapeHTML(block.page)}` : ""}</strong><p>${escapeHTML(block.text || "Passage text not available")}</p><span>${escapeHTML((block.section_path || []).join?.(" › ") || block.section_path || "")}</span></article>`).join("") : `<p>No source passage was returned with this citation.</p>`}</section>`;
  dialog.showModal();
}

function renderRetrievalTrace(result) {
  if (result.system === "graphrag") {
    const communities = result.communities || [];
    const evidence = result.evidence || [];
    return `<section class="result-section"><h3>GraphRAG retrieval trace</h3><div class="trace-grid">
      <article><strong>${communities.length}</strong><span>communities searched</span>${communities.slice(0, 3).map((item) => `<p>${escapeHTML(item.id)} · ${score(item.score)}</p>`).join("")}</article>
      <article><strong>${evidence.length}</strong><span>relationships supplied</span>${evidence.slice(0, 4).map((item) => `<p>${escapeHTML(item.evidence_id)} · ${score(item.score)}</p>`).join("")}</article>
      <article><strong>${new Set(evidence.map((item) => item.paper)).size}</strong><span>papers represented</span><p>Community retrieval, then relationship ranking</p></article>
    </div></section>
    <section class="result-section"><h3>Retrieved relationship evidence</h3><div class="citation-list">${evidence.slice(0, 8).map((item) => `<article><strong>${escapeHTML(item.evidence_id)}</strong><p>${escapeHTML(item.description)}</p><span>${escapeHTML(item.paper_title)} · ${escapeHTML((item.blocks || []).map((block) => `${block.block_id}, p. ${block.page}`).join("; "))}</span></article>`).join("")}</div></section>`;
  }
  if (result.system === "plain_rag") {
    const sources = result.sources || [];
    return `<section class="result-section"><h3>Passage retrieval trace</h3><div class="trace-grid">
      <article><strong>${sources.length}</strong><span>source chunks supplied</span>${sources.slice(0, 4).map((item, index) => `<p>S${index + 1} · ${score(item.score)}</p>`).join("")}</article>
      <article><strong>${new Set(sources.map((item) => item.paper)).size}</strong><span>papers represented</span><p>Embedding similarity with metadata ranking</p></article>
    </div></section>
    <section class="result-section"><h3>Retrieved source passages</h3><div class="citation-list">${sources.map((item, index) => `<article><strong>S${index + 1}</strong><p>${escapeHTML(item.paper)} · ${escapeHTML(item.heading || item.section)}</p><span>${escapeHTML(item.text.slice(0, 360))}${item.text.length > 360 ? "…" : ""}</span></article>`).join("")}</div></section>`;
  }
  const contexts = result.contexts || [];
  return `<section class="result-section"><h3>Evidence trace</h3><div class="trace-grid">
    <article><strong>${contexts.length}</strong><span>top contexts shown</span>${contexts.slice(0, 3).map((item) => `<p>${escapeHTML(item.context_id)} · ${score(item.context_similarity?.overall_score)}</p>`).join("")}</article>
    <article><strong>${result.claims?.length || 0}</strong><span>top claims shown</span>${(result.claims || []).slice(0, 4).map((item) => `<p>${escapeHTML(item.claim_id)} · ${score(item.R_claim)}</p>`).join("")}</article>
    <article><strong>${result.paths?.length || 0}</strong><span>evidence paths shown</span><p>${escapeHTML(result.paths?.[0]?.claim_ids?.join(" → ") || "No mechanism path selected")}</p></article>
  </div></section>`;
}

function renderStageTrace(stages = []) {
  if (!stages.length) return `<p class="empty-copy">No step trace was recorded for this run.</p>`;
  return `<ol class="trace-steps">${stages.map((stage) => `
    <li>
      <strong>${escapeHTML(stageLabel(stage.name))}</strong>
      ${stage.details && Object.keys(stage.details).length ? `<pre>${escapeHTML(JSON.stringify(stage.details, null, 2))}</pre>` : ""}
    </li>`).join("")}</ol>`;
}

function renderClimateKGProcessingTrace(result) {
  if (result.system !== "climatekg") return "";
  const userFacets = result.user_facets || [];
  const derivedFacets = result.derived_facets || [];
  return `<section class="result-section"><h3>Parsed query and context</h3><div class="trace-grid">
    <article><strong>${escapeHTML(result.mode || "unknown")}</strong><span>query mode</span><p>${escapeHTML(result.question || "")}</p></article>
    <article><strong>${userFacets.length}</strong><span>user-stated context facets</span>${userFacets.slice(0, 4).map((item) => `<p>${escapeHTML(item.domain)} / ${escapeHTML(item.notion)}</p>`).join("")}</article>
    <article><strong>${derivedFacets.length}</strong><span>derived watershed facets</span>${derivedFacets.slice(0, 4).map((item) => `<p>${escapeHTML(item.domain)} / ${escapeHTML(item.notion)}</p>`).join("")}</article>
  </div>${result.spatial_support ? `<pre class="trace-json">${escapeHTML(JSON.stringify(result.spatial_support, null, 2))}</pre>` : ""}</section>`;
}

function renderProvenanceTrace(result) {
  const citations = Object.entries(result.provenance || {});
  if (result.system !== "climatekg") return "";
  return `<section class="result-section"><h3>Cited sources</h3>${citations.length ? `<div class="citation-list">${citations.map(([claim, item]) => `<article><strong>${escapeHTML(claim)}</strong><p>${escapeHTML(item.title)} (${escapeHTML(item.year || "n.d.")})${item.pages?.length ? `, pages ${escapeHTML(item.pages.join(", "))}` : ""}</p><span>${escapeHTML(item.source_block_ids?.join(", ") || "")}</span></article>`).join("")}</div>` : `<p class="empty-copy">No cited Claim survived grounding validation.</p>`}</section>`;
}

function renderTracePanel(result, stages) {
  return `<section class="trace-panel" hidden>
    <header><div><p class="eyebrow">Run trace</p><h2>How this answer was produced</h2></div></header>
    <section class="result-section"><h3>Pipeline steps</h3>${renderStageTrace(stages)}</section>
    ${renderClimateKGProcessingTrace(result)}
    ${renderRetrievalTrace(result)}
    ${renderProvenanceTrace(result)}
    <section class="result-section"><h3>Trace files</h3><p class="artifact-path">${escapeHTML(result.artifact_dir || "No artifact directory recorded")}</p></section>
  </section>`;
}

function renderResult(container, result, stages = []) {
  const derived = result.derived_facets || [];
  container.innerHTML = `
    <article class="answer-panel">
      <header><div><p class="eyebrow">${escapeHTML(result.system_label || "ClimateKG")} answer</p><h2>${escapeHTML(result.question || "Result")}</h2></div><span class="mode-badge">${escapeHTML(result.mode || "query")}</span></header>
      <div class="answer-text">${renderMarkdown(result.answer, result.citation_details || {})}</div>
    </article>
    ${derived.length ? `<section class="result-section"><h3>Watershed context used</h3><p class="section-note">Select a context value to see what it means, why it affects evidence matching, and where it came from.</p><div class="facet-grid">${derived.map((item, index) => `<button class="facet-card" type="button" data-facet-index="${index}"><span>${escapeHTML(item.domain)}</span><strong>${escapeHTML(item.notion)}</strong><p>${escapeHTML(item.description)}</p><small>View explanation</small></button>`).join("")}</div></section>` : ""}
    ${result.warnings?.length ? `<details class="warning-list"><summary>${result.warnings.length} method notices</summary>${result.warnings.map((item) => `<p>${escapeHTML(item)}</p>`).join("")}</details>` : ""}
    <div class="trace-toggle-row"><button class="secondary-button trace-toggle" type="button">Show trace</button></div>
    ${renderTracePanel(result, stages)}`;
  container.querySelectorAll("[data-facet-index]").forEach((card) => {
    card.addEventListener("click", () => showFacetDetails(derived[Number(card.dataset.facetIndex)]));
  });
  container.querySelectorAll("[data-citation-id]").forEach((citation) => {
    citation.addEventListener("click", (event) => {
      event.preventDefault();
      const item = result.citation_details?.[citation.dataset.citationId];
      if (item) showCitationDetails(item);
    });
  });
  const toggle = container.querySelector(".trace-toggle");
  const panel = container.querySelector(".trace-panel");
  toggle?.addEventListener("click", () => {
    const willShow = panel.hasAttribute("hidden");
    panel.toggleAttribute("hidden", !willShow);
    toggle.textContent = willShow ? "Hide trace" : "Show trace";
  });
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
      renderResult(container, job.result, job.stages);
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
  populateSystems(state.config);
  const ready = state.config.graph_ready && state.config.graphrag_ready && state.config.plain_rag_ready && state.config.koppen_ready && state.config.watersheds.ready;
  $("#system-dot").classList.toggle("ready", ready);
  $("#system-label").textContent = ready ? "Corpus and watershed data ready" : "Setup required";
  setWorkflow(window.location.hash === "#planning" ? "planning" : "process");

  $("#process-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submitJob("/api/process-query", {
      question: $("#process-question").value,
      system: $("#process-system").value,
    }, $("#process-result"), event.submitter);
  });
  $("#planning-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submitJob("/api/land-use-plan", {
      watershed_id: state.selected,
      objective: $("#planning-objective").value,
      additional_information: $("#additional-information").value,
      system: $("#planning-system").value,
    }, $("#planning-result"), event.submitter);
  });
  $("#watershed-find").addEventListener("click", findWatershed);
  $("#facet-dialog-close").addEventListener("click", () => $("#facet-dialog").close());
  $("#facet-dialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) event.currentTarget.close();
  });
  $("#citation-dialog-close").addEventListener("click", () => $("#citation-dialog").close());
  $("#citation-dialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) event.currentTarget.close();
  });
  $("#watershed-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); findWatershed(); }
  });
  await initializeMap();
}

initialize().catch((error) => {
  $("#system-label").textContent = error.message;
  $("#map-status").textContent = error.message;
});
