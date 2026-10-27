// Talks to ui/server.py. Errors are turned into plain-English messages; secrets never reach this file.

class ApiProblem extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/** api("/api/x") for GET, api("/api/x", {method: "POST", body: {...}}) for POST. Resolves to parsed JSON. */
async function api(path, options = {}) {
  const method = options.method || "GET";
  const headers = { "Accept": "application/json" };
  const init = { method, headers, cache: "no-store" };
  if (method === "POST") {
    headers["X-Requested-With"] = "team10-ui"; // the server refuses POSTs without it
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body || {});
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs || 130000);
  init.signal = controller.signal;
  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    throw new ApiProblem(err.name === "AbortError"
      ? "The server took too long to answer."
      : "The server cannot be reached. Is ui/server.py running?", 0);
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    data = null;
  }
  if (!response.ok) {
    throw new ApiProblem((data && data.error) || `The server answered with an error (${response.status}).`, response.status);
  }
  if (data === null) throw new ApiProblem("The server sent an answer this page cannot read.", response.status);
  return data;
}

function problemText(err) {
  return err instanceof ApiProblem ? err.message : "Something unexpected went wrong in the page.";
}
