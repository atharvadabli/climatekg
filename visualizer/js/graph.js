const SVG_NS = "http://www.w3.org/2000/svg";

function svgElement(name, attributes = {}, text = "") {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  if (text) element.textContent = text;
  return element;
}

function shorten(value, size = 32) {
  const text = String(value || "");
  return text.length > size ? `${text.slice(0, size - 1)}…` : text;
}

function endpointLabel(endpoint) {
  return [endpoint?.concept, endpoint?.state].filter(Boolean).join(" · ");
}

function claimStateId(endpoint, states) {
  const concept = endpoint?.concept?.toLowerCase();
  const state = endpoint?.state?.toLowerCase();
  return states.find((item) => item.concept.toLowerCase() === concept && item.state.toLowerCase() === state)?.id;
}

export function claimGraph(data, options = {}) {
  const allowed = new Set(options.relations || ["causal", "associative"]);
  const claims = data.claims.filter((claim) => allowed.has(claim.relation)).slice(0, options.limit || 20);
  const nodes = [];
  const edges = [];
  const stateNodes = new Map();
  const ensureState = (endpoint, side, index) => {
    const label = endpointLabel(endpoint);
    const key = `${endpoint.concept}::${endpoint.state}`.toLowerCase();
    if (!stateNodes.has(key)) {
      const node = {
        key,
        ref: claimStateId(endpoint, data.states),
        type: "state",
        label,
        endpoint,
        side,
        indexes: [],
      };
      stateNodes.set(key, node);
      nodes.push(node);
    }
    stateNodes.get(key).indexes.push(index);
    return stateNodes.get(key);
  };
  claims.forEach((claim, index) => {
    const source = ensureState(claim.from, "source", index);
    const target = ensureState(claim.to, "target", index);
    const claimNode = { key: claim.id, ref: claim.id, type: "claim", label: claim.id, claim, index };
    nodes.push(claimNode);
    edges.push({ from: source, to: claimNode, type: claim.relation, ref: claim.id, label: claim.description });
    edges.push({ from: claimNode, to: target, type: claim.relation, ref: claim.id, label: claim.description });
  });
  const spacing = 84;
  const height = Math.max(620, claims.length * spacing + 100);
  nodes.forEach((node) => {
    if (node.type === "claim") {
      node.x = 520;
      node.y = 70 + node.index * spacing;
    } else {
      node.x = node.side === "source" ? 185 : 855;
      node.y = 70 + node.indexes.reduce((sum, value) => sum + value, 0) / node.indexes.length * spacing;
    }
  });
  return { nodes, edges, width: 1040, height, count: claims.length };
}

export function contextGraph(data) {
  const contexts = data.contexts.map((context, index) => ({
    key: context.id,
    ref: context.id,
    type: "context",
    label: context.label,
    context,
    index,
  }));
  const lookup = new Map(contexts.map((node) => [node.key, node]));
  const depthMemo = new Map();
  const depth = (node, visiting = new Set()) => {
    if (depthMemo.has(node.key)) return depthMemo.get(node.key);
    if (visiting.has(node.key) || !node.context.parent_ids.length) return 0;
    visiting.add(node.key);
    const result = 1 + Math.max(...node.context.parent_ids.map((id) => lookup.has(id) ? depth(lookup.get(id), visiting) : 0));
    depthMemo.set(node.key, result);
    return result;
  };
  const columns = new Map();
  contexts.forEach((node) => {
    const value = depth(node);
    node.depth = value;
    if (!columns.has(value)) columns.set(value, []);
    columns.get(value).push(node);
  });
  const maxRows = Math.max(1, ...[...columns.values()].map((items) => items.length));
  const height = Math.max(620, maxRows * 108 + 120);
  columns.forEach((items, column) => items.forEach((node, row) => {
    node.x = 175 + column * 310;
    node.y = 90 + (row + 0.5) * ((height - 150) / items.length);
  }));
  const edges = [];
  contexts.forEach((node) => node.context.parent_ids.forEach((id) => {
    if (lookup.has(id)) edges.push({ from: lookup.get(id), to: node, type: "parent", ref: node.key, label: `Parent of ${node.label}` });
  }));
  data.transitions.forEach((transition) => {
    const from = lookup.get(transition.from_context_id);
    const to = lookup.get(transition.to_context_id);
    if (from && to) edges.push({ from, to, type: "transition", ref: transition.id, label: transition.label });
  });
  return { nodes: contexts, edges, width: Math.max(1040, (columns.size + 1) * 310), height, count: contexts.length };
}

export function provenanceGraph(data, claimId) {
  const claim = data.claims.find((item) => item.id === claimId) || data.claims[0];
  if (!claim) return { nodes: [], edges: [], width: 1040, height: 620, count: 0 };
  const nodes = [];
  const edges = [];
  const center = { key: claim.id, ref: claim.id, type: "claim", label: claim.id, claim, x: 520, y: 300 };
  nodes.push(center);
  const add = (object, type, label, x, y, edgeType) => {
    if (!object) return;
    const node = { key: object.id, ref: object.id, type, label, x, y };
    if (type === "state" && object.concept) node.endpoint = { concept: object.concept, state: object.state };
    nodes.push(node);
    edges.push({ from: node, to: center, type: edgeType, ref: object.id, label });
  };
  const scope = claim.scope_type === "context"
    ? data.contexts.find((item) => item.id === claim.scope_id)
    : data.transitions.find((item) => item.id === claim.scope_id);
  add(scope, claim.scope_type, scope?.label || claim.scope_id, 170, 300, "scope");
  const source = { id: claimStateId(claim.from, data.states) || `${claim.id}:from`, ...claim.from };
  const target = { id: claimStateId(claim.to, data.states) || `${claim.id}:to`, ...claim.to };
  add(source, "state", endpointLabel(claim.from), 380, 95, "endpoint");
  add(target, "state", endpointLabel(claim.to), 660, 95, "endpoint");
  claim.conditioning_facet_ids.forEach((id, index) => {
    const facet = data.facets.find((item) => item.id === id);
    add(facet, "facet", facet?.notion || id, 810, 230 + index * 92, "conditions");
  });
  claim.evidence_block_ids.forEach((id, index) => {
    const block = data.source_blocks.find((item) => item.id === id);
    add(block, "source_block", `p.${block?.page ?? "?"} · ${shorten(block?.text, 38)}`, 310 + index * 260, 525, "evidence");
  });
  return { nodes, edges, width: 1040, height: 650, count: nodes.length, claim };
}

function edgePath(from, to) {
  const bend = Math.max(40, Math.abs(to.x - from.x) * 0.42);
  return `M ${from.x} ${from.y} C ${from.x + bend} ${from.y}, ${to.x - bend} ${to.y}, ${to.x} ${to.y}`;
}

export class GraphRenderer {
  constructor(svg, onSelect) {
    this.svg = svg;
    this.onSelect = onSelect;
    this.model = null;
    this.viewBox = { x: 0, y: 0, width: 1040, height: 620 };
    this.drag = null;
    this.installPanZoom();
  }

  render(model, selectedRef = null) {
    this.model = model;
    this.svg.replaceChildren();
    this.svg.setAttribute("viewBox", `0 0 ${model.width} ${model.height}`);
    this.viewBox = { x: 0, y: 0, width: model.width, height: model.height };
    const defs = svgElement("defs");
    const marker = svgElement("marker", { id: "arrow", viewBox: "0 0 10 10", refX: "8", refY: "5", markerWidth: "5", markerHeight: "5", orient: "auto-start-reverse" });
    marker.append(svgElement("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "arrow-head" }));
    defs.append(marker);
    this.svg.append(defs);
    const edgeLayer = svgElement("g", { class: "edge-layer" });
    model.edges.forEach((edge) => {
      const path = svgElement("path", { d: edgePath(edge.from, edge.to), class: `graph-edge ${edge.type}`, "marker-end": "url(#arrow)" });
      path.append(svgElement("title", {}, edge.label || edge.ref || edge.type));
      if (edge.ref) {
        path.classList.add("selectable");
        path.addEventListener("click", () => this.onSelect(edge.ref));
      }
      edgeLayer.append(path);
    });
    this.svg.append(edgeLayer);
    const nodeLayer = svgElement("g", { class: "node-layer" });
    model.nodes.forEach((node) => {
      const group = svgElement("g", { class: `graph-node ${node.type}${(node.ref || node.key) === selectedRef ? " selected" : ""}`, transform: `translate(${node.x} ${node.y})`, tabindex: "0", role: "button" });
      group.setAttribute("aria-label", `${node.type}: ${node.label}`);
      group.append(svgElement("title", {}, `${node.label}${node.ref ? ` (${node.ref})` : ""}`));
      const width = node.type === "claim" ? 126 : 250;
      const height = node.type === "claim" ? 52 : 64;
      group.append(svgElement("rect", { x: -width / 2, y: -height / 2, width, height, rx: "5" }));
      group.append(svgElement("text", { x: "0", y: node.type === "claim" ? "-2" : "-7", "text-anchor": "middle" }, shorten(node.label, node.type === "claim" ? 18 : 34)));
      if (node.type === "claim") group.append(svgElement("text", { x: "0", y: "16", "text-anchor": "middle", class: "node-subtitle" }, node.claim?.relation || "claim"));
      else group.append(svgElement("text", { x: "0", y: "14", "text-anchor": "middle", class: "node-subtitle" }, node.ref || node.type));
      group.addEventListener("click", () => this.onSelect(node.ref || node.key, node));
      group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") this.onSelect(node.ref || node.key, node); });
      nodeLayer.append(group);
    });
    this.svg.append(nodeLayer);
  }

  fit() {
    if (!this.model) return;
    this.viewBox = { x: 0, y: 0, width: this.model.width, height: this.model.height };
    this.applyViewBox();
  }

  applyViewBox() {
    const { x, y, width, height } = this.viewBox;
    this.svg.setAttribute("viewBox", `${x} ${y} ${width} ${height}`);
  }

  installPanZoom() {
    this.svg.addEventListener("wheel", (event) => {
      event.preventDefault();
      const scale = event.deltaY > 0 ? 1.12 : 0.88;
      const point = this.svg.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      const local = point.matrixTransform(this.svg.getScreenCTM().inverse());
      const nextWidth = Math.max(280, Math.min(6000, this.viewBox.width * scale));
      const nextHeight = this.viewBox.height * (nextWidth / this.viewBox.width);
      const ratioX = (local.x - this.viewBox.x) / this.viewBox.width;
      const ratioY = (local.y - this.viewBox.y) / this.viewBox.height;
      this.viewBox.x = local.x - ratioX * nextWidth;
      this.viewBox.y = local.y - ratioY * nextHeight;
      this.viewBox.width = nextWidth;
      this.viewBox.height = nextHeight;
      this.applyViewBox();
    }, { passive: false });
    this.svg.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".graph-node")) return;
      this.drag = { x: event.clientX, y: event.clientY, startX: this.viewBox.x, startY: this.viewBox.y };
      this.svg.setPointerCapture(event.pointerId);
      this.svg.classList.add("dragging");
    });
    this.svg.addEventListener("pointermove", (event) => {
      if (!this.drag) return;
      const rect = this.svg.getBoundingClientRect();
      this.viewBox.x = this.drag.startX - (event.clientX - this.drag.x) * this.viewBox.width / rect.width;
      this.viewBox.y = this.drag.startY - (event.clientY - this.drag.y) * this.viewBox.height / rect.height;
      this.applyViewBox();
    });
    const stop = () => { this.drag = null; this.svg.classList.remove("dragging"); };
    this.svg.addEventListener("pointerup", stop);
    this.svg.addEventListener("pointercancel", stop);
  }
}
