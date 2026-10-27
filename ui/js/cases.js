// "Test cases" tab: the 500 synthetic cases (300 golden/generated + 200 stories), search and filters,
// the expected-vs-observed detail view, and the harness summary.

const CASE_QUERY = { source: "all", group: "", category: "", kind: "", q: "", page: 1, page_size: 25 };
let caseSearchTimer = null;

async function renderCases() {
  if (APP.mode === "offline") return renderOfflineCases();
  const view = document.getElementById("test-case-list-view");
  document.getElementById("test-case-detail").hidden = true;
  view.hidden = false;
  if (view.dataset.built !== "1") {
    view.dataset.built = "1";
    renderHarnessBox();
    loadCaseList();
  }
}

/* ---------- harness ---------- */

async function renderHarnessBox() {
  const box = document.getElementById("harness-box");
  const limit = h("input", { type: "number", id: "harness-limit", min: 1, max: 300, value: 50, "aria-label": "Number of cases to run" });
  const run = h("button", { class: "primary", text: "Run harness" });
  const out = h("div", { id: "harness-summary" });
  clear(box).append(h("h3", { text: "Harness: how well does the reviewer find the planted errors?" }),
    h("div", { class: "toolbar" }, h("label", {}, "Cases to run (1–300): ", limit), run,
      h("span", { class: "hint", text: "The harness runs the DBVO review on the first N of the 300 generated cases. Story cases are not run by it." })),
    out);
  run.addEventListener("click", () => withBusy(run, "Running…", async () => {
    clear(out).append(loading("Running the harness (up to 2 minutes)…"));
    try {
      const n = Number(limit.value);
      showHarness(out, await api("/api/harness/run", { method: "POST", body: { limit: n } }));
    } catch (err) {
      clear(out).append(message("error", "The harness could not be run. " + problemText(err)));
    }
  }));
  clear(out).append(loading("Loading the latest harness result…"));
  try {
    showHarness(out, await api("/api/harness/latest"));
  } catch (err) {
    clear(out).append(err.status === 404 ? message("info", "No harness run yet. Choose a number and click “Run harness”.")
      : message("error", "The harness result could not be loaded. " + problemText(err)));
  }
}

function showHarness(out, h0) {
  const s = h0.summary || {};
  const cats = Object.entries(s.by_category || {});
  clear(out).append(
    h("p", {}, h("strong", { text: `${s.correct ?? "?"} of ${s.cases ?? "?"}` }), " cases judged correctly · ",
      h("strong", { text: `${s.detected ?? "?"} of ${s.must_flag_cases ?? "?"}` }), " planted errors found · ",
      h("strong", { text: `${s.false_alarms ?? "?"} of ${s.clean_cases ?? "?"}` }), " clean cases wrongly flagged"),
    h("p", { class: "meta", text: `Run ${s.run_id || "—"} · code version ${s.git_sha || "—"} · file ${h0.file}. ` +
      "Synthetic cases only; the score says how the reviewer handles these 300 cases, not that real software is correct." }),
    cats.length ? h("details", {}, h("summary", { text: `Results by category (${cats.length})` }),
      h("table", {}, h("thead", {}, h("tr", {}, [h("th", { text: "Group | category" }), h("th", { text: "Outcomes" })])),
        h("tbody", {}, cats.map(([k, v]) => h("tr", {}, h("td", { text: k }), h("td", { text: Object.entries(v).map(([o, n]) => `${o}: ${n}`).join(", ") })))))) : null);
}

/* ---------- list ---------- */

async function loadCaseList() {
  const target = document.getElementById("test-case-list");
  const searchHadFocus = !!document.activeElement && document.activeElement.type === "search" && target.contains(document.activeElement);
  clear(target).append(loading("Loading test cases…"));
  const params = new URLSearchParams();
  Object.entries(CASE_QUERY).forEach(([k, v]) => { if (v !== "" && v !== null) params.set(k, v); });
  try {
    const data = await api("/api/testcases?" + params.toString());
    drawCaseList(target, data, searchHadFocus);
  } catch (err) {
    clear(target).append(message("error", "The test cases could not be loaded. " + problemText(err)));
  }
}

function filterSelect(label, key, values, current) {
  const sel = h("select", { "aria-label": label },
    h("option", { value: "", text: `${label}: all` }),
    values.map((v) => h("option", { value: v, text: v.length > 70 ? v.slice(0, 67) + "…" : v, title: v, selected: v === current })));
  sel.addEventListener("change", () => { CASE_QUERY[key] = sel.value; CASE_QUERY.page = 1; loadCaseList(); });
  return sel;
}

function drawCaseList(target, data, searchHadFocus) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  const source = h("select", { "aria-label": "Source" },
    [["all", "All 500 cases"], ["golden", "Generated 300 (golden, decision, output, ambiguous)"], ["stories", "Stories 200"]]
      .map(([v, t]) => h("option", { value: v, text: t, selected: v === CASE_QUERY.source })));
  source.addEventListener("change", () => {
    Object.assign(CASE_QUERY, { source: source.value, group: "", category: "", kind: "", page: 1 });
    loadCaseList();
  });
  const search = h("input", { type: "search", placeholder: "Search id, category, kind…", value: CASE_QUERY.q, "aria-label": "Search", maxlength: 100 });
  search.addEventListener("input", () => {
    clearTimeout(caseSearchTimer);
    caseSearchTimer = setTimeout(() => { CASE_QUERY.q = search.value; CASE_QUERY.page = 1; loadCaseList(); }, 300);
  });
  const prev = h("button", { text: "← Previous", disabled: CASE_QUERY.page <= 1 });
  const next = h("button", { text: "Next →", disabled: CASE_QUERY.page >= pages });
  prev.addEventListener("click", () => { CASE_QUERY.page -= 1; loadCaseList(); });
  next.addEventListener("click", () => { CASE_QUERY.page += 1; loadCaseList(); });

  const rows = data.items.map((c) => {
    const tr = h("tr", { class: "clickable", tabindex: 0, "data-case": c.id },
      h("td", { text: c.id }), h("td", { text: c.group }), h("td", { text: c.category }), h("td", { text: c.kind }),
      h("td", { text: c.must_flag === null || c.must_flag === undefined ? "— (should be clean)" : c.must_flag }));
    tr.addEventListener("click", () => showTestCaseDetail(c.id));
    tr.addEventListener("keydown", (ev) => { if (ev.key === "Enter") showTestCaseDetail(c.id); });
    return tr;
  });
  clear(target).append(
    h("div", { class: "toolbar filters" }, source, filterSelect("Group", "group", data.facets.groups, CASE_QUERY.group),
      filterSelect("Category", "category", data.facets.categories, CASE_QUERY.category),
      filterSelect("Kind", "kind", data.facets.kinds, CASE_QUERY.kind), search),
    h("p", { id: "list-count", class: "meta", text: `${data.total} case(s) match · page ${data.page} of ${pages}` }),
    data.items.length ? h("table", {}, h("thead", {}, h("tr", {}, ["ID", "Group", "Category", "Kind of output", "Error the reviewer must flag"].map((t) => h("th", { text: t })))),
      h("tbody", {}, rows)) : message("info", "No test case matches these filters."),
    h("div", { class: "toolbar" }, prev, next));
  if (searchHadFocus) {   // typing in the search box must not lose the cursor when the list redraws
    search.focus();
    search.setSelectionRange(search.value.length, search.value.length);
  }
}

/* ---------- detail ---------- */

async function showTestCaseDetail(id) {
  const detail = document.getElementById("test-case-detail");
  document.getElementById("test-case-list-view").hidden = true;
  detail.hidden = false;
  clear(detail).append(loading("Loading test case…"));
  const back = h("button", { id: "back-to-list", text: "← Back to list" });
  back.addEventListener("click", () => { detail.hidden = true; document.getElementById("test-case-list-view").hidden = false; });
  try {
    const data = await api("/api/testcases/" + encodeURIComponent(id));
    drawCaseDetail(detail, data, back);
  } catch (err) {
    clear(detail).append(back, message("error", "The test case could not be loaded. " + problemText(err)));
  }
}

/** Rows for the expected-vs-observed table. Only DBVO cases can be compared field by field. */
function comparisonRows(c) {
  const exp = c.expected || {};
  const rows = [];
  if ("dbvo" in exp && c.observed_dbvo !== undefined) {
    const sent = c.observed_dbvo !== null;
    rows.push(["41 is sent", exp.send_41 ? "yes" : "no", sent ? "yes" : "no", exp.send_41 === sent ? "match" : "mismatch"]);
    const e = exp.dbvo || {}, o = c.observed_dbvo || {};
    [...new Set([...Object.keys(e), ...Object.keys(o)])].forEach((k) => {
      const ev = formatValue(e[k]), ov = formatValue(o[k]);
      const kind = k in e && k in o ? (ev === ov ? "match" : "mismatch") : "info";
      rows.push([k, ev, ov, kind]);
    });
  } else {
    Object.entries(exp).forEach(([k, v]) => rows.push([k, formatValue(v), "see the raw output below", "info"]));
  }
  return rows;
}

function drawCaseDetail(detail, data, back) {
  const c = data.case;
  const rows = comparisonRows(c);
  const hr = data.harness_result;
  const verdict = { match: "✓ same", mismatch: "✗ differs", info: "not compared" };
  const raw = ["observed_dbvo", "observed_61", "messages", "employer_41"].filter((k) => c[k] !== undefined);
  clear(detail).append(back,
    h("h3", { text: `${c.id} — ${c.category}` }),
    h("p", { class: "meta", text: `Source: ${c.source} · group: ${c.group} · kind of output: ${c.observed_kind}` }),
    h("p", {}, "Error the reviewer must flag: ", h("strong", { text: c.must_flag === null || c.must_flag === undefined ? "none (this output is correct)" : c.must_flag })),
    h("h4", { text: "Scenario (input)" }), pre(c.scenario),
    h("h4", { text: "Expected vs. observed" }),
    rows.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Field", "Expected", "Observed", "Result"].map((t) => h("th", { text: t })))),
      h("tbody", {}, rows.map(([k, e, o, kind]) => h("tr", { class: kind }, h("td", { text: k }), h("td", { text: e }), h("td", { text: o }), h("td", { text: verdict[kind] }))))) : message("info", "This case has no expected values."),
    h("p", { class: "meta", text: "Rows in red differ. “not compared” means the value exists on one side only or the case type is not compared field by field." }),
    raw.map((k) => [h("h4", { text: `Raw ${k}` }), pre(c[k])]),
    h("h4", { text: "Reviewer result (latest harness run)" }),
    hr ? [h("p", {}, badge(hr.ok ? "PASS" : "MISMATCH"), `  ${hr.outcome}`, hr.flagged && hr.flagged.length ? `  (flagged: ${hr.flagged.join(", ")})` : ""),
      h("p", { class: "meta", text: `From ${data.harness_file}` }),
      h("table", {}, h("thead", {}, h("tr", {}, ["Check", "Expected", "Actual", "Status"].map((t) => h("th", { text: t })))),
        h("tbody", {}, (hr.findings || []).map((f) => h("tr", {}, h("td", { text: f.id }), h("td", { text: formatValue(f.expected) }), h("td", { text: formatValue(f.actual) }), h("td", {}, badge(f.status))))))]
      : message("info", "The latest harness run does not include this case (stories are not run by the harness, or no run yet)."));
}
