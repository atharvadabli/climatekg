export async function getJSON(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.error || message;
    } catch (_) {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

export const api = {
  manifest: () => getJSON("/api/manifest"),
  refresh: () => getJSON("/api/refresh"),
  paper: (paperId) => getJSON(`/api/papers/${encodeURIComponent(paperId)}`),
  query: (traceId) => getJSON(`/api/queries/${encodeURIComponent(traceId)}`),
};
