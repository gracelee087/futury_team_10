// "Review report" tab: runs run_review.py through the server and shows the real report.json,
// plus the human review-decision form (the human gate: nothing is ever approved automatically).

const REPORT_STATUS_ORDER = ["BLOCKED", "MISMATCH", "NEEDS_REVIEW", "NOT EVALUATED", "PASS"];
const DECISION_LABELS = { approve: "Approve", reject: "Reject", needs_changes: "Needs changes" };

function sourceAnchor(source) {
  return "item-src-" + String(source).replace(/[^A-Za-z0-9]+/g, "_");
}

async function renderReport() {
  const box = document.getElementById("report-view");
  if (APP.mode === "offline") return renderOfflineReport(box);
  if (box.dataset.built === "1") return;   // keep what the user is looking at when switching tabs
  box.dataset.built = "1";

  const runButton = h("button", { class: "primary", id: "run-review", text: "Run review" });
  const body = h("div", { id: "report-body" });
  const decision = h("div", { id: "decision-box" });
  clear(box).append(
    h("div", { class: "toolbar" }, runButton,
      h("span", { class: "hint", text: "Runs run_review.py on the sample TEEL0 file; takes a few seconds." })),
    body, decision);

  runButton.addEventListener("click", () => withBusy(runButton, "Running review…", async () => {
    clear(body).append(loading("Running the review (up to 2 minutes)…"));
    try {
      showReport(body, await api("/api/review/run", { method: "POST" }));
      loadDecisions(decision);
    } catch (err) {
      clear(body).append(message("error", "The review could not be run. " + problemText(err)));
    }
  }));

  clear(body).append(loading("Loading the latest review report…"));
  try {
    showReport(body, await api("/api/review/latest"));
  } catch (err) {
    clear(body).append(err.status === 404
      ? message("info", "There is no review report yet. Click “Run review” to create one.")
      : message("error", "The latest report could not be loaded. " + problemText(err)));
  }
  buildDecisionForm(decision);
}

/* ---------- report ---------- */

function showReport(body, payload) {
  const report = payload.data;
  APP.report = payload;
  const r = report.report || {};
  const counts = r.counts || {};
  const findings = Array.isArray(report.findings) ? report.findings : [];

  const filter = h("select", { id: "status-filter", "aria-label": "Filter findings by status" },
    h("option", { value: "", text: "All statuses" }),
    REPORT_STATUS_ORDER.concat([...new Set(findings.map((f) => f.status))].filter((s) => !REPORT_STATUS_ORDER.includes(s)))
      .filter((s) => findings.some((f) => f.status === s))
      .map((s) => h("option", { value: s, text: `${s} (${findings.filter((f) => f.status === s).length})` })));
  const tbody = h("tbody");
  const table = h("table", { class: "findings" },
    h("thead", {}, h("tr", {}, ["ID", "Rule", "Expected", "Actual", "Status", "Source", "Reason"].map((t) => h("th", { text: t })))),
    tbody);

  const draw = () => {
    clear(tbody);
    findings.filter((f) => !filter.value || f.status === filter.value).forEach((f) => {
      const detail = h("tr", { class: "detail-row", hidden: true },
        h("td", { colspan: 7 }, evidenceChain(report, f)));
      const toggle = h("button", { class: "link", "aria-expanded": "false", text: String(f.id) });
      toggle.addEventListener("click", () => {
        detail.hidden = !detail.hidden;
        toggle.setAttribute("aria-expanded", String(!detail.hidden));
      });
      tbody.append(
        h("tr", { class: "finding-" + String(f.status).replace(/\W+/g, "-").toLowerCase() },
          h("td", {}, toggle), h("td", { text: f.rule }), h("td", { class: "val", text: formatValue(f.expected) }),
          h("td", { class: "val", text: formatValue(f.actual) }), h("td", {}, badge(f.status)),
          h("td", { class: "evidence", text: f.source }), h("td", { text: f.reason || "" })),
        detail);
    });
    if (!tbody.children.length) tbody.append(h("tr", {}, h("td", { colspan: 7, text: "No findings with this status." })));
  };
  filter.addEventListener("change", draw);
  draw();

  clear(body).append(
    h("h3", { text: `Report ${r.id || "(no id)"}` }),
    h("p", {}, "Overall: ", badge(r.overall_status), "  ",
      Object.entries(counts).filter(([, n]) => n > 0).map(([s, n]) => [h("span", { class: "count" }, `${n} × `, badge(s)), " "])),
    h("p", { class: "meta", text: `Created ${r.created_at || "—"} · ${r.scope || ""}` }),
    h("p", { class: "meta", text: `Template: ${r.template || "—"}` }),
    h("h4", { text: "Findings" }),
    h("p", { class: "toolbar" }, h("label", {}, "Status: ", filter),
      h("span", { class: "hint", text: "Click a finding ID to see its evidence chain." })),
    table,
    robustnessBlock(report.robustness),
    report.trace_url ? h("p", { class: "meta" }, "Trace: ", h("code", { text: report.trace_url })) : null);
}

function evidenceChain(report, f) {
  const execution = report.execution || {};
  const tc = report.test_case || {};
  const steps = [
    ["Report", (report.report || {}).id],
    ["Run", `${execution.id || "—"} (file ${execution.file || "—"})`],
    ["Test case", `${tc.id || "—"} (${tc.source || "—"})`],
    ["Criterion", f.criterion_id || "none recorded for this check"],
  ];
  const chain = h("p", { class: "chain" });
  steps.forEach(([label, value]) => {
    chain.append(h("span", { class: "chain-step", title: label, text: `${label}: ${value}` }), h("span", { class: "chain-arrow", text: "→" }));
  });
  const jump = h("button", { class: "chain-link", text: `Source: ${f.source}` });
  jump.addEventListener("click", () => jumpToItem(sourceAnchor(f.source)));
  chain.append(jump);
  return h("div", {}, chain,
    f.reason ? h("p", {}, h("strong", { text: "Why: " }), f.reason) : null,
    h("p", { class: "meta", text: "Expected values come from the cited source; the actual value is read from the software output." }));
}

function robustnessBlock(rb) {
  if (!rb) return h("p", { class: "msg msg-info", text: "No robustness result in this report." });
  const rows = (rb.attacks || []).map((a) => h("tr", {}, h("td", { text: a.kind }), h("td", { text: a.attack }),
    h("td", {}, badge(a.result)), h("td", { text: (a.failed_checks || []).join(", ") || "—" })));
  return h("div", { class: "robustness" },
    h("h4", { text: "Robustness: does the checker notice deliberate errors?" }),
    h("p", {}, h("strong", { text: rb.result || "—" }), `  ·  baseline: ${rb.baseline || "—"}  ·  tool: ${rb.tool || "—"}`),
    h("p", { class: "meta", text: "CAUGHT = a check failed as it should. BLOCKED = the input guard rejected the broken data. " +
      "MISSED = the attack was not noticed. “Baseline: no false alarm” means the unchanged, correct data raised no alarm." }),
    rows.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Kind", "Attack", "Result", "Checks that failed"].map((t) => h("th", { text: t })))),
      h("tbody", {}, rows)) : null);
}

/* ---------- human review decision ---------- */

function buildDecisionForm(box) {
  const reviewer = h("input", { type: "text", id: "reviewer", maxlength: 80, required: true, autocomplete: "off" });
  const decision = h("select", { id: "decision" },
    h("option", { value: "", text: "Choose…" }),
    Object.entries(DECISION_LABELS).map(([v, label]) => h("option", { value: v, text: label })));
  const comment = h("textarea", { id: "comment", rows: 3, maxlength: 1000 });
  const status = h("div", { id: "decision-status" });
  const submit = h("button", { class: "primary", type: "submit", text: "Record decision" });
  const form = h("form", { class: "decision-form" },
    h("label", {}, "Reviewer name", reviewer), h("label", {}, "Decision", decision),
    h("label", {}, "Comment", comment), submit, status);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    clear(status);
    if (!reviewer.value.trim() || !decision.value) {
      status.append(message("warn", "Please enter your name and choose a decision."));
      return;
    }
    await withBusy(submit, "Saving…", async () => {
      try {
        const body = { reviewer: reviewer.value, decision: decision.value, comment: comment.value };
        if (APP.report && APP.report.data.report) body.report_id = APP.report.data.report.id;
        await api("/api/review/decision", { method: "POST", body });
        status.append(message("ok", "Decision recorded in the append-only review log."));
        comment.value = "";
        loadDecisions(box);
      } catch (err) {
        status.append(message("error", "The decision was not saved. " + problemText(err)));
      }
    });
  });
  clear(box).append(
    h("h4", { text: "Human review decision" }),
    message("info", "This is the human gate. A person records the decision; the system never approves anything by itself. " +
      "In this demo the reviewer name is typed in and not verified."),
    form, h("div", { id: "decision-history" }));
  loadDecisions(box);
}

async function loadDecisions(box) {
  const target = box.querySelector("#decision-history");
  if (!target) return;
  clear(target).append(loading("Loading review history…"));
  try {
    const events = (await api("/api/review/decision")).events.slice().reverse();
    const current = APP.report && APP.report.data.report ? APP.report.data.report.id : null;
    const mine = events.find((e) => e.report_id === current);
    clear(target).append(h("h4", { text: "Review history (newest first)" }),
      h("p", {}, "Latest human decision for this report: ",
        mine ? h("span", { class: "decision decision-" + String(mine.decision).replace(/\W/g, ""), text: DECISION_LABELS[mine.decision] || String(mine.decision) })
             : [badge("NEEDS_REVIEW"), " no decision recorded yet – pending human review"]),
      events.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Time", "Report", "Reviewer", "Decision", "Comment"].map((t) => h("th", { text: t })))),
        h("tbody", {}, events.map((e) => h("tr", {}, h("td", { text: shortDate(e.timestamp) }), h("td", { class: "evidence", text: e.report_id || "—" }),
          h("td", { text: e.reviewer }), h("td", {}, h("span", { class: "decision decision-" + String(e.decision).replace(/\W/g, ""), text: DECISION_LABELS[e.decision] || String(e.decision) })),
          h("td", { text: e.comment || "" })))))
        : h("p", { class: "meta", text: "No decisions recorded yet. The report is unreviewed." }));
  } catch (err) {
    clear(target).append(message("error", "The review history could not be loaded. " + problemText(err)));
  }
}
