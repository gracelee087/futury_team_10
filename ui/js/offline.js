// OFFLINE SAMPLE VIEWS (Oussama's original screens). Used only when the server cannot be reached
// (for example index.html opened as a file). They read the fabricated records in js/data.js.
// Live mode never touches DATA, so sample and real data cannot be mixed.

const SAMPLE_NOTE = "Sample data (js/data.js) – fabricated, not a result of the real tools.";

function offlineNeedsServer(name) {
  return message("warn", `“${name}” needs the server. Start python ui/server.py and open http://localhost:8000.`);
}

function findingFor(testCaseId) { return DATA.findings.find((f) => f.test_case_id === testCaseId) || null; }
function executionFor(testCaseId) { return DATA.executions.find((r) => r.test_case_id === testCaseId) || null; }
function criterionFor(id) { return DATA.criteria.find((c) => c.id === id) || null; }
function requirementFor(id) { return DATA.requirements.find((r) => r.id === id) || null; }
function sourceFor(id) { return DATA.sources.find((s) => s.id === id) || null; }

/* ---------- test cases ---------- */

function renderOfflineCases() {
  document.getElementById("test-case-detail").hidden = true;
  document.getElementById("test-case-list-view").hidden = false;
  clear(document.getElementById("harness-box")).append(offlineNeedsServer("Harness"));

  const counts = { "PASS": 0, "MISMATCH": 0, "NOT EVALUATED": 0 };
  DATA.findings.forEach((f) => { if (counts[f.status] !== undefined) counts[f.status] += 1; });
  clear(document.getElementById("list-summary")).append(
    h("p", { class: "meta", text: SAMPLE_NOTE }),
    h("p", {}, Object.entries(counts).map(([s, n]) => [`${n} × `, badge(s), "  "])));

  const rows = DATA.testCases.map((tc) => {
    const finding = findingFor(tc.id);
    const tr = h("tr", { class: "clickable", "data-case": tc.id },
      h("td", { text: tc.id }), h("td", { text: tc.title }), h("td", { text: tc.kind }), h("td", { text: tc.review_status }),
      h("td", {}, badge(finding ? finding.status : "NOT EVALUATED")));
    tr.addEventListener("click", () => showOfflineCaseDetail(tc.id));
    return tr;
  });
  clear(document.getElementById("test-case-list")).append(
    h("table", {}, h("thead", {}, h("tr", {}, ["ID", "Test case", "Kind", "Review", "Result"].map((t) => h("th", { text: t })))),
      h("tbody", {}, rows)));
}

function offlineChain(testCaseId) {
  const tc = DATA.testCases.find((t) => t.id === testCaseId);
  const execution = executionFor(testCaseId);
  const criterion = tc ? criterionFor(tc.criterion_id) : null;
  const requirement = criterion ? requirementFor(criterion.requirement_id) : null;
  const steps = [{ kind: "report", id: DATA.report.id }];
  if (execution) steps.push({ kind: "run", id: execution.id });
  steps.push({ kind: "case", id: testCaseId });
  if (criterion) steps.push({ kind: "criterion", id: criterion.id });
  if (requirement) steps.push({ kind: "requirement", id: requirement.id }, { kind: "source", id: requirement.source_id });
  const chain = h("p", { class: "chain" });
  steps.forEach((s, i) => {
    if (i) chain.append(h("span", { class: "chain-arrow", text: "→" }));
    if (s.kind === "requirement" || s.kind === "source") {
      const b = h("button", { class: "chain-link", "data-jump": s.id, text: s.id });
      b.addEventListener("click", () => jumpToItem(s.id));
      chain.append(b);
    } else {
      chain.append(h("span", { class: "chain-step", text: s.id }));
    }
  });
  return chain;
}

function showOfflineCaseDetail(testCaseId) {
  const tc = DATA.testCases.find((t) => t.id === testCaseId);
  const finding = findingFor(testCaseId);
  const execution = executionFor(testCaseId);
  const detail = document.getElementById("test-case-detail");
  const back = h("button", { id: "back-to-list", text: "← Back to list" });
  back.addEventListener("click", () => renderOfflineCases());
  clear(detail).append(
    h("h3", { text: `${tc.id} — ${tc.title}` }),
    h("p", { class: "meta", text: SAMPLE_NOTE }),
    h("p", { text: `Criterion: ${tc.criterion_id} · Kind: ${tc.kind} · Review: ${tc.review_status} (by ${tc.review.reviewer} at ${tc.review.timestamp})` }),
    h("h4", { text: "Inputs" }), pre(tc.inputs),
    h("h4", { text: "Expected basis" }), h("p", { text: tc.expected_basis }),
    h("h4", { text: "Expected vs. observed" }),
    execution ? offlineComparison(tc.expected, execution.observed)
              : h("p", { class: "warning", text: "No execution output for this case — result cannot be evaluated." }),
    h("h4", { text: "Finding" }), h("p", {}, badge(finding ? finding.status : "NOT EVALUATED"), " " + (finding ? finding.reason : "")),
    h("h4", { text: "Evidence chain (click requirement or source)" }), offlineChain(testCaseId), back);
  document.getElementById("test-case-list-view").hidden = true;
  detail.hidden = false;
}

function offlineComparison(expected, observed) {
  const keys = [...new Set([...Object.keys(expected), ...Object.keys(observed)])];
  return h("table", {}, h("thead", {}, h("tr", {}, ["Field", "Expected", "Observed", "Result"].map((t) => h("th", { text: t })))),
    h("tbody", {}, keys.map((key) => {
      const match = expected[key] === observed[key];
      return h("tr", { class: match ? "match" : "mismatch" }, h("td", { text: key }), h("td", { text: formatValue(expected[key]) }),
        h("td", { text: formatValue(observed[key]) }), h("td", { text: match ? "✓" : "✗ differs" }));
    })));
}

/* ---------- report ---------- */

function renderOfflineReport(box) {
  const report = DATA.report;
  clear(box).append(
    h("p", { class: "meta", text: SAMPLE_NOTE }),
    h("h3", { text: `Report ${report.id}` }), h("p", { text: `Template: ${report.template_id}` }), h("p", { text: `Renderer: ${report.renderer_version}` }),
    h("div", { class: "warning" }, "Because a conformance check failed, this report may ", h("strong", { text: "not" }),
      " be signed off as compliant until the issue is corrected and re-checked."),
    h("h4", { text: "Conformance checks" }),
    h("ul", {}, report.conformance.map((c) => h("li", {}, `${c.check}: `, h("strong", { text: c.status }), c.detail ? ` — ${c.detail}` : ""))),
    h("h4", { text: "Findings included" }),
    h("ul", {}, report.findings.map((id) => h("li", {}, `${id} `, badge((findingFor(id) || {}).status || "NOT EVALUATED")))),
    h("h4", { text: "Human review events" }),
    h("table", {}, h("thead", {}, h("tr", {}, ["Test case", "Reviewer", "Decision", "Timestamp"].map((t) => h("th", { text: t })))),
      h("tbody", {}, DATA.testCases.map((tc) => h("tr", {}, h("td", { text: tc.id }), h("td", { text: tc.review.reviewer }),
        h("td", { text: tc.review.decision }), h("td", { text: tc.review.timestamp }))))),
    h("p", { class: "warning", text: report.limitations }));
}

/* ---------- sources & requirements ---------- */

function renderOfflineSources(box) {
  const jumpButton = (id, label) => {
    const b = h("button", { class: "chain-link", "data-jump": id, text: label });
    b.addEventListener("click", () => jumpToItem(id));
    return b;
  };
  clear(box).append(
    h("p", { class: "meta", text: SAMPLE_NOTE }),
    h("h3", { text: "Sources" }),
    DATA.sources.map((s) => h("div", { class: "card", id: "item-" + s.id }, h("h4", { text: `${s.id} — ${s.title}` }),
      h("p", { text: `Issuer: ${s.issuer} · Version: ${s.version}` }), h("p", { class: "evidence", text: "Citation: " + s.citation }))),
    h("h3", { text: "Requirements (candidates until a human approves them)" }),
    DATA.requirements.map((r) => h("div", { class: "card", id: "item-" + r.id }, h("h4", {}, r.id + " ", badge(r.status.toUpperCase() === "NEEDS_REVIEW" ? "NEEDS_REVIEW" : r.status)),
      h("p", { text: r.text }), h("p", { class: "evidence" }, `From ${r.source_id} (${r.citation}) `, jumpButton(r.source_id, "show source")))),
    h("h3", { text: "Testable criteria (human-approved)" }),
    DATA.criteria.map((c) => h("div", { class: "card", id: "item-" + c.id }, h("h4", {}, c.id + " ", h("span", { class: "decision decision-approve", text: c.status })),
      h("p", { text: c.text }), h("p", { class: "evidence" }, `Approved by ${c.approved_by} · derived from ${c.requirement_id} `, jumpButton(c.requirement_id, "show requirement")))));
}
