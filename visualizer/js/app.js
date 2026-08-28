import { api } from "./api.js";
import { GraphRenderer, claimGraph, contextGraph, provenanceGraph } from "./graph.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  manifest: null,
  paper: null,
  index: new Map(),
  selectedRef: null,
  graphMode: "claims",
  entityType: "claims",
  entityFilter: "",
  query: null,
  currentArtifactId: null,
};

const graph = new GraphRenderer($("#knowledge-graph"), (ref, graphNode) => openReference(ref, graphNode));

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value, digits = 3) {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

function titleCase(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function refButton(id, label = id, className = "ref-button") {
  if (!id) return "<span class=\"muted\">None</span>";
  return `<button class="${className}" data-ref="${escapeHTML(id)}">${escapeHTML(label)}</button>`;
}

function refList(ids, empty = "None") {
  if (!ids?.length) return `<span class="muted">${escapeHTML(empty)}</span>`;
  return `<div class="ref-list">${ids.map((id) => refButton(id)).join("")}</div>`;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("visible"), 3200);
}

function setLoading(element, message) {
  element.innerHTML = `<div class="loading-state"><span></span>${escapeHTML(message)}</div>`;
}

function buildIndex(paper) {
  const index = new Map();
  const groups = {
    context: paper.contexts,
    facet: paper.facets,
    transition: paper.transitions,
    claim: paper.claims,
    state: paper.states,
    source_block: paper.source_blocks,
  };
  Object.entries(groups).forEach(([type, items]) => items.forEach((object) => index.set(object.id, { type, object })));
  state.index = index;
}

async function loadPaper(artifactId, preserveView = true) {
  $("#paper-title").textContent = "Loading paper…";
  try {
    state.paper = await api.paper(artifactId);
    state.currentArtifactId = artifactId;
    buildIndex(state.paper);
    state.selectedRef = null;
    renderPaperSummary();
    renderGraph();
    renderEntityTabs();
    renderEntityTable();
    clearInspector();
    if (!preserveView) showView("graph");
  } catch (error) {
    showToast(`Paper could not be loaded: ${error.message}`, true);
  }
}

function renderPaperSummary() {
  const paper = state.paper.paper;
  $("#paper-title").textContent = paper.title.replace(/^#\s*/, "");
  $("#paper-meta").innerHTML = [paper.id, paper.year, paper.doi].filter(Boolean).map((value) => `<span>${escapeHTML(value)}</span>`).join("");
  const metrics = [
    ["Claims", state.paper.claims.length],
    ["Contexts", state.paper.contexts.length],
    ["Facets", state.paper.facets.length],
    ["Blocks", state.paper.source_blocks.length],
  ];
  $("#paper-metrics").innerHTML = metrics.map(([label, value]) => `<div><strong>${value}</strong><span>${label}</span></div>`).join("");
}

function graphOptions() {
  const relations = [];
  if ($("#causal-filter").checked) relations.push("causal");
  if ($("#associative-filter").checked) relations.push("associative");
  return { limit: Number($("#claim-limit").value), relations };
}

function renderGraph() {
  if (!state.paper) return;
  let model;
  if (state.graphMode === "contexts") {
    model = contextGraph(state.paper);
    $("#graph-kicker").textContent = "Settings and comparisons";
    $("#graph-title").textContent = "Context map";
  } else if (state.graphMode === "provenance") {
    model = provenanceGraph(state.paper, state.selectedRef);
    $("#graph-kicker").textContent = "Claim to cited evidence";
    $("#graph-title").textContent = model.claim ? `Provenance · ${model.claim.id}` : "Provenance";
  } else {
    model = claimGraph(state.paper, graphOptions());
    $("#graph-kicker").textContent = "Scientific relationships";
    $("#graph-title").textContent = "Claim graph";
  }
  $("#graph-status").textContent = `${model.count} ${state.graphMode === "claims" ? "relationships" : "objects"}`;
  $("#graph-empty").hidden = model.nodes.length > 0;
  $("#graph-empty").textContent = "No objects match the current filters.";
  graph.render(model, state.selectedRef);
}

const entityConfigs = {
  claims: {
    label: "Claims",
    rows: () => state.paper.claims,
    headings: ["ID", "Relationship", "Type", "Scope", "Evidence"],
    cells: (item) => [
      refButton(item.id),
      `<div class="relationship-cell"><strong>${escapeHTML(item.from.concept)} <span>${escapeHTML(item.from.state)}</span></strong><i>→</i><strong>${escapeHTML(item.to.concept)} <span>${escapeHTML(item.to.state)}</span></strong><small>${escapeHTML(item.description)}</small></div>`,
      `<span class="badge ${item.relation}">${escapeHTML(item.relation)}</span><small>${escapeHTML(titleCase(item.evidence_role))}</small>`,
      refButton(item.scope_id),
      refList(item.evidence_block_ids),
    ],
  },
  contexts: {
    label: "Contexts",
    rows: () => state.paper.contexts,
    headings: ["ID", "Study setting", "Parents", "Spatial support", "Evidence"],
    cells: (item) => [refButton(item.id), `<strong>${escapeHTML(item.label)}</strong><small>${escapeHTML(item.aliases.join(" · "))}</small>`, refList(item.parent_ids), item.spatial_support ? `<span class="badge neutral">${escapeHTML(item.spatial_support.kind)}</span><small>${escapeHTML(item.spatial_support.name)}</small>` : "—", refList(item.evidence_block_ids)],
  },
  facets: {
    label: "Facets",
    rows: () => state.paper.facets,
    headings: ["ID", "Domain", "Condition", "Context", "Evidence"],
    cells: (item) => [refButton(item.id), `<span class="badge domain-${escapeHTML(item.domain)}">${escapeHTML(titleCase(item.domain))}</span>`, `<strong>${escapeHTML(item.notion)}</strong><small>${escapeHTML(item.description)}</small>`, refButton(item.context_id), refList(item.evidence_block_ids)],
  },
  transitions: {
    label: "Transitions",
    rows: () => state.paper.transitions,
    headings: ["ID", "Comparison", "From", "To", "Evidence"],
    cells: (item) => [refButton(item.id), `<strong>${escapeHTML(item.label)}</strong><small>${escapeHTML(item.description)}</small>`, refButton(item.from_context_id), refButton(item.to_context_id), refList(item.evidence_block_ids)],
  },
  states: {
    label: "States",
    rows: () => state.paper.states,
    headings: ["ID", "Concept", "State", "Aliases"],
    cells: (item) => [refButton(item.id), `<strong>${escapeHTML(item.concept)}</strong>`, escapeHTML(item.state), escapeHTML(item.aliases.join(" · ") || "—")],
  },
  source_blocks: {
    label: "SourceBlocks",
    rows: () => state.paper.source_blocks,
    headings: ["ID", "Page", "Type", "Section", "Text"],
    cells: (item) => [refButton(item.id), item.page ?? "—", `<span class="badge neutral">${escapeHTML(item.block_type)}</span>`, escapeHTML(item.section_path.join(" › ") || "—"), `<div class="block-preview">${escapeHTML(item.text)}</div>`],
  },
};

function renderEntityTabs() {
  $("#entity-tabs").innerHTML = Object.entries(entityConfigs).map(([key, config]) => {
    const count = config.rows().length;
    return `<button data-entity="${key}" class="${key === state.entityType ? "active" : ""}">${config.label}<span>${count}</span></button>`;
  }).join("");
}

function searchableText(value) {
  return JSON.stringify(value).toLowerCase();
}

function renderEntityTable() {
  if (!state.paper) return;
  const config = entityConfigs[state.entityType];
  const term = state.entityFilter.trim().toLowerCase();
  const allRows = config.rows();
  const matched = term ? allRows.filter((item) => searchableText(item).includes(term)) : allRows;
  const rows = matched.slice(0, 200);
  $("#entity-head").innerHTML = `<tr>${config.headings.map((heading) => `<th>${heading}</th>`).join("")}</tr>`;
  $("#entity-body").innerHTML = rows.map((item) => `<tr>${config.cells(item).map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("");
  $("#table-summary").textContent = `${matched.length} of ${allRows.length} ${config.label.toLowerCase()}${matched.length > 200 ? " · first 200 shown" : ""}`;
}

function objectHeader(type, object) {
  const labels = {
    claim: object.description,
    facet: object.notion,
    context: object.label,
    transition: object.label,
    state: `${object.concept} · ${object.state}`,
    source_block: `Page ${object.page ?? "?"} · ${object.block_type}`,
  };
  return labels[type] || object.id;
}

function field(label, content) {
  return `<section class="inspector-section"><div class="section-label">${escapeHTML(label)}</div>${content}</section>`;
}

function relatedToBlock(blockId) {
  const paper = state.paper;
  const result = [];
  [["Context", paper.contexts], ["Facet", paper.facets], ["Transition", paper.transitions], ["Claim", paper.claims]].forEach(([type, items]) => {
    items.filter((item) => item.evidence_block_ids?.includes(blockId)).forEach((item) => result.push([type, item.id]));
  });
  return result;
}

function detailsFor(type, object) {
  if (type === "claim") {
    return [
      `<div class="claim-statement"><div>${escapeHTML(object.from.concept)} <strong>${escapeHTML(object.from.state)}</strong></div><span>→</span><div>${escapeHTML(object.to.concept)} <strong>${escapeHTML(object.to.state)}</strong></div></div>`,
      `<p class="lead-text">${escapeHTML(object.description)}</p>`,
      field("Classification", `<div class="property-grid"><span>Relation</span><strong>${escapeHTML(object.relation)}</strong><span>Evidence role</span><strong>${escapeHTML(titleCase(object.evidence_role))}</strong><span>Scope</span>${refButton(object.scope_id)}</div>`),
      field("Conditioning Facets", refList(object.conditioning_facet_ids, "No material conditioning Facets")),
      field("Supporting SourceBlocks", refList(object.evidence_block_ids)),
      `<button class="primary-button full-width" data-provenance="${escapeHTML(object.id)}">Show complete provenance graph</button>`,
    ].join("");
  }
  if (type === "facet") {
    return `<p class="lead-text">${escapeHTML(object.description)}</p>${field("Properties", `<div class="property-grid"><span>Domain</span><strong>${escapeHTML(titleCase(object.domain))}</strong><span>Origin</span><strong>${escapeHTML(object.origin)}</strong><span>Context</span>${refButton(object.context_id)}</div>`)}${field("Supporting SourceBlocks", refList(object.evidence_block_ids))}${object.source ? field("Provenance source", `<pre>${escapeHTML(JSON.stringify(object.source, null, 2))}</pre>`) : ""}`;
  }
  if (type === "context") {
    const children = state.paper.contexts.filter((item) => item.parent_ids.includes(object.id)).map((item) => item.id);
    const facets = state.paper.facets.filter((item) => item.context_id === object.id).map((item) => item.id);
    const claims = state.paper.claims.filter((item) => item.scope_type === "context" && item.scope_id === object.id).map((item) => item.id);
    return `${object.spatial_support ? field("Spatial support", `<div class="property-grid"><span>Kind</span><strong>${escapeHTML(object.spatial_support.kind)}</strong><span>Name</span><strong>${escapeHTML(object.spatial_support.name)}</strong><span>Resolution</span><strong>${escapeHTML(object.spatial_support.resolution)}</strong></div>`) : ""}${field("Parent contexts", refList(object.parent_ids))}${field("Child contexts", refList(children))}${field("Facets", refList(facets))}${field("Claims scoped here", refList(claims))}${field("Supporting SourceBlocks", refList(object.evidence_block_ids))}`;
  }
  if (type === "transition") {
    const claims = state.paper.claims.filter((item) => item.scope_type === "transition" && item.scope_id === object.id).map((item) => item.id);
    return `<p class="lead-text">${escapeHTML(object.description)}</p>${field("Compared contexts", `<div class="transition-pair">${refButton(object.from_context_id)}<span>→</span>${refButton(object.to_context_id)}</div>`)}${field("Claims scoped here", refList(claims))}${field("Supporting SourceBlocks", refList(object.evidence_block_ids))}`;
  }
  if (type === "state") {
    const claims = state.paper.claims.filter((item) => [item.from, item.to].some((endpoint) => endpoint.concept.toLowerCase() === object.concept.toLowerCase() && endpoint.state.toLowerCase() === object.state.toLowerCase())).map((item) => item.id);
    return `${field("Concept", `<p class="lead-text">${escapeHTML(object.concept)}</p>`)}${field("State", `<p>${escapeHTML(object.state)}</p>`)}${field("Aliases", object.aliases.length ? `<p>${escapeHTML(object.aliases.join(" · "))}</p>` : `<span class="muted">None</span>`)}${field("Claims using this State", refList(claims))}`;
  }
  if (type === "source_block") {
    const related = relatedToBlock(object.id);
    return `<div class="source-meta"><span>Page ${object.page ?? "?"}</span><span>${escapeHTML(object.block_type)}</span><span>Order ${object.order}</span></div>${object.section_path.length ? `<div class="section-path">${escapeHTML(object.section_path.join(" › "))}</div>` : ""}<blockquote>${escapeHTML(object.text)}</blockquote>${field("Objects supported by this passage", related.length ? `<div class="related-list">${related.map(([kind, id]) => `<div><span>${kind}</span>${refButton(id)}</div>`).join("")}</div>` : `<span class="muted">No recorded evidence links</span>`)}${field("Source locator", `<pre>${escapeHTML(JSON.stringify(object.source_locator, null, 2))}</pre>`)}`;
  }
  return `<pre>${escapeHTML(JSON.stringify(object, null, 2))}</pre>`;
}

function showInspector(type, object) {
  $("#inspector").classList.add("open");
  $("#inspector-type").textContent = titleCase(type);
  $("#inspector-id").textContent = object.id;
  $("#inspector-body").innerHTML = `<h3>${escapeHTML(objectHeader(type, object))}</h3>${detailsFor(type, object)}`;
}

function clearInspector() {
  $("#inspector").classList.remove("open");
  $("#inspector-type").textContent = "Inspector";
  $("#inspector-id").textContent = "Select an object";
  $("#inspector-body").innerHTML = `<div class="empty-state">Click any node, row, Facet ID, Claim ID, Context ID, or SourceBlock ID.</div>`;
}

function paperIdFromReference(ref) {
  return /^P\d{6}/.exec(ref)?.[0] || null;
}

async function openReference(ref, graphNode = null) {
  if (!ref) return;
  const paperId = paperIdFromReference(ref);
  if (paperId && state.paper?.paper.id !== paperId && state.manifest.papers.some((paper) => paper.id === paperId)) {
    const target = state.manifest.papers.find((paper) => paper.id === paperId);
    $("#paper-select").value = target.artifact_id;
    await loadPaper(target.artifact_id);
  }
  const indexed = state.index.get(ref);
  if (!indexed) {
    if (graphNode?.type === "state" && graphNode.endpoint) {
      const endpoint = graphNode.endpoint;
      const virtualState = { id: graphNode.key, concept: endpoint.concept, state: endpoint.state, aliases: [] };
      state.selectedRef = graphNode.key;
      showInspector("state", virtualState);
      renderGraph();
      return;
    }
    showToast(`Referenced object is not present in the loaded paper: ${ref}`, true);
    return;
  }
  state.selectedRef = ref;
  showInspector(indexed.type, indexed.object);
  if ($("#graph-view").classList.contains("active")) renderGraph();
}

function renderQueryList() {
  const queries = state.manifest.queries;
  $("#query-count").textContent = `${queries.length} saved reports`;
  $("#query-list").innerHTML = queries.length ? queries.map((query) => `<button class="query-list-item" data-trace="${query.trace_id}"><span>${escapeHTML(query.query_id)} · ${escapeHTML(query.mode || "unknown")}</span><strong>${escapeHTML(query.question)}</strong><small>${escapeHTML(query.run_id)} · open for full scores and paths</small></button>`).join("") : `<div class="empty-state">No query reports found.</div>`;
}

function scoreBar(value) {
  const width = Math.max(0, Math.min(100, Number(value || 0) * 100));
  return `<div class="score"><span style="width:${width}%"></span><strong>${formatNumber(value)}</strong></div>`;
}

function queryFacets(report) {
  return report.query_spec?.context?.facets || [];
}

function renderQueryReport(report) {
  const spec = report.query_spec || {};
  const synthesis = report.synthesis || {};
  const contexts = (report.context_candidates || []).slice(0, 30);
  const claims = (report.claim_candidates || []).slice(0, 50);
  const paths = report.paths || [];
  const facets = queryFacets(report);
  $("#query-detail").innerHTML = `
    <header class="query-report-header">
      <div><span class="eyebrow">${escapeHTML(report.query_id)} · ${escapeHTML(spec.mode || "unknown mode")}</span><h3>${escapeHTML(spec.user_question || "Saved query")}</h3></div>
      <div class="query-facets">${facets.map((facet) => `<span title="${escapeHTML(facet.description)}">${escapeHTML(facet.id)} · ${escapeHTML(facet.notion)}</span>`).join("")}</div>
    </header>
    <section class="answer-panel"><div class="section-label">Grounded answer</div><div class="answer-text">${escapeHTML(report.answer || "No answer was produced.")}</div></section>
    ${report.warnings?.length ? `<section class="warning-panel"><div class="section-label">Warnings</div>${report.warnings.map((warning) => `<p>${escapeHTML(warning)}</p>`).join("")}</section>` : ""}
    <div class="trace-tabs">
      <button class="active" data-trace-tab="synthesis">Synthesis</button>
      <button data-trace-tab="contexts">Context similarity <span>${contexts.length}</span></button>
      <button data-trace-tab="claims">Claim gating <span>${claims.length}</span></button>
      <button data-trace-tab="paths">Paths <span>${paths.length}</span></button>
      <button data-trace-tab="evidence">Evidence</button>
    </div>
    <div class="trace-panel active" data-trace-panel="synthesis">${renderSynthesis(synthesis)}</div>
    <div class="trace-panel" data-trace-panel="contexts">${renderContextCandidates(contexts)}</div>
    <div class="trace-panel" data-trace-panel="claims">${renderClaimCandidates(claims)}</div>
    <div class="trace-panel" data-trace-panel="paths">${renderPaths(paths)}</div>
    <div class="trace-panel" data-trace-panel="evidence">${renderQueryEvidence(report.source_blocks || {})}</div>`;
}

function renderSynthesis(synthesis) {
  if (!synthesis.items?.length) return `<div class="empty-state">No structured synthesis items.</div>`;
  return `<div class="synthesis-list">${synthesis.items.map((item) => `<article><span class="badge neutral">${escapeHTML(titleCase(item.kind))}</span><p>${escapeHTML(item.text)}</p><div class="support-row"><span>Claims</span>${refList(item.support_claim_ids)}</div>${item.support_query_facet_ids?.length ? `<div class="support-row"><span>Query Facets</span><div class="ref-list">${item.support_query_facet_ids.map((id) => `<code>${escapeHTML(id)}</code>`).join("")}</div></div>` : ""}</article>`).join("")}</div>`;
}

function renderContextCandidates(contexts) {
  if (!contexts.length) return `<div class="empty-state">No Context candidates.</div>`;
  return `<div class="trace-table"><div class="trace-row trace-head"><span>Context</span><span>Overall similarity</span><span>Coverage</span><span>Missing query Facets</span></div>${contexts.map((item) => `<div class="trace-row"><span>${refButton(item.context_id)}<small>${escapeHTML(item.paper_id)}</small></span><span>${scoreBar(item.context_similarity?.overall_score)}</span><span>${scoreBar(item.context_similarity?.coverage)}</span><span>${escapeHTML((item.context_similarity?.missing_query_facets || []).join(", ") || "None")}</span></div>`).join("")}</div>`;
}

function renderClaimCandidates(claims) {
  if (!claims.length) return `<div class="empty-state">No Claim candidates.</div>`;
  return `<div class="trace-table claims-trace"><div class="trace-row trace-head"><span>Claim</span><span>Retrieval R</span><span>Applicability A</span><span>Coverage</span><span>Channels</span></div>${claims.map((item) => `<div class="trace-row"><span>${refButton(item.claim_id)}<small>${item.applicability_known ? "known context" : "unknown context"}</small></span><span>${scoreBar(item.R_claim)}</span><span>${scoreBar(item.A_claim)}</span><span>${formatNumber(item.context_coverage)}</span><span>${escapeHTML((item.channels || []).join(" · "))}</span></div>`).join("")}</div>`;
}

function renderPaths(paths) {
  if (!paths.length) return `<div class="empty-state">No mechanism paths passed search.</div>`;
  return `<div class="path-list">${paths.map((path, index) => `<article><header><strong>Path ${index + 1}</strong><span>R<sub>path</sub> ${formatNumber(path.R_path)}</span></header><div class="path-flow">${path.claim_ids.map((id, claimIndex) => `${claimIndex ? "<i>→</i>" : ""}${refButton(id)}`).join("")}</div><div class="path-scores"><span>Applicability ${formatNumber(path.A_path)}</span><span>Coherence ${formatNumber(path.C_path)}</span><span>Mechanism ${formatNumber(path.M_path)}</span></div></article>`).join("")}</div>`;
}

function renderQueryEvidence(sourceBlocks) {
  const entries = Object.entries(sourceBlocks);
  if (!entries.length) return `<div class="empty-state">No SourceBlocks stored in this report.</div>`;
  return `<div class="evidence-groups">${entries.map(([claimId, blocks]) => `<section><header>${refButton(claimId)}<span>${blocks.length} passage${blocks.length === 1 ? "" : "s"}</span></header>${blocks.map((block) => `<article><div>${refButton(block.id)}<span>Page ${block.page ?? "?"}</span></div><p>${escapeHTML(block.text)}</p></article>`).join("")}</section>`).join("")}</div>`;
}

async function loadQuery(traceId) {
  setLoading($("#query-detail"), "Loading query report…");
  try {
    state.query = await api.query(traceId);
    $$(".query-list-item").forEach((button) => button.classList.toggle("active", button.dataset.trace === traceId));
    renderQueryReport(state.query);
  } catch (error) {
    $("#query-detail").innerHTML = `<div class="empty-state error-text">${escapeHTML(error.message)}</div>`;
  }
}

function showView(view) {
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $$(".view").forEach((section) => section.classList.toggle("active", section.id === `${view}-view`));
  $("#paper-sidebar").classList.toggle("query-mode", view === "queries");
  if (view === "graph") setTimeout(() => graph.fit(), 0);
}

function bindEvents() {
  document.addEventListener("click", (event) => {
    const ref = event.target.closest("[data-ref]");
    if (ref) { event.preventDefault(); openReference(ref.dataset.ref); return; }
    const provenance = event.target.closest("[data-provenance]");
    if (provenance) {
      state.selectedRef = provenance.dataset.provenance;
      state.graphMode = "provenance";
      $$("#graph-mode button").forEach((button) => button.classList.toggle("active", button.dataset.mode === "provenance"));
      showView("graph");
      renderGraph();
      return;
    }
    const traceTab = event.target.closest("[data-trace-tab]");
    if (traceTab) {
      const tab = traceTab.dataset.traceTab;
      $$("[data-trace-tab]").forEach((button) => button.classList.toggle("active", button.dataset.traceTab === tab));
      $$("[data-trace-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.tracePanel === tab));
    }
  });
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  $("#paper-select").addEventListener("change", (event) => loadPaper(event.target.value));
  $("#refresh-button").addEventListener("click", async () => {
    state.manifest = await api.refresh();
    populateManifest();
    showToast("Artifact folders rescanned");
  });
  $("#graph-mode").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-mode]");
    if (!button) return;
    state.graphMode = button.dataset.mode;
    $$("#graph-mode button").forEach((item) => item.classList.toggle("active", item === button));
    renderGraph();
  });
  $("#claim-limit").addEventListener("input", (event) => { $("#claim-limit-output").value = event.target.value; renderGraph(); });
  $("#causal-filter").addEventListener("change", renderGraph);
  $("#associative-filter").addEventListener("change", renderGraph);
  $("#fit-graph").addEventListener("click", () => graph.fit());
  $("#entity-tabs").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-entity]");
    if (!button) return;
    state.entityType = button.dataset.entity;
    renderEntityTabs();
    renderEntityTable();
  });
  $("#entity-search").addEventListener("input", (event) => { state.entityFilter = event.target.value; renderEntityTable(); });
  $("#global-search").addEventListener("input", (event) => {
    state.entityFilter = event.target.value;
    $("#entity-search").value = event.target.value;
    if (event.target.value) { showView("entities"); renderEntityTable(); }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
      event.preventDefault();
      $("#global-search").focus();
    }
    if (event.key === "Escape") clearInspector();
  });
  $("#close-inspector").addEventListener("click", clearInspector);
  $("#query-list").addEventListener("click", (event) => {
    const item = event.target.closest("[data-trace]");
    if (item) loadQuery(item.dataset.trace);
  });
}

function populateManifest() {
  const papers = state.manifest.papers;
  $("#paper-select").innerHTML = papers.map((paper) => `<option value="${paper.artifact_id}">${paper.id} · ${escapeHTML(paper.title)}${paper.artifact_source === "prompt_example" ? " · prompt replay" : ""}</option>`).join("");
  renderQueryList();
}

async function initialize() {
  bindEvents();
  try {
    state.manifest = await api.manifest();
    populateManifest();
    if (!state.manifest.papers.length) throw new Error("No final_paper.json artifacts were found.");
    await loadPaper(state.manifest.papers[0].artifact_id, false);
  } catch (error) {
    showToast(error.message, true);
    $("#paper-title").textContent = "Artifacts unavailable";
    $("#graph-empty").hidden = false;
    $("#graph-empty").textContent = `Start visualizer/server.py from the project root. ${error.message}`;
  }
}

initialize();
