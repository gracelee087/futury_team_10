// Team 10 demo UI: tabs, start-up (live or offline), overview and the sources tab.
// The other tabs live in report.js, cases.js, ask.js and seal.js; offline sample screens in offline.js.

const TABS = ["overview", "report", "cases", "ask", "seal", "sources", "privacy"];
const VIEW_IDS = { overview: "overview-view", report: "report-view", cases: "cases-view", ask: "ask-view", seal: "seal-view", sources: "sources-view", privacy: "privacy-view" };
const RENDERERS = { overview: () => renderOverview(), report: () => renderReport(), cases: () => renderCases(),
  ask: () => renderAsk(), seal: () => renderSeal(), sources: () => renderSources(), privacy: () => renderPrivacy() };

function switchTab(tab) {
  if (!TABS.includes(tab)) tab = "overview";
  TABS.forEach((t) => {
    document.getElementById(VIEW_IDS[t]).hidden = t !== tab;
    const button = document.getElementById("tab-" + t);
    button.classList.toggle("active", t === tab);
    button.setAttribute("aria-current", t === tab ? "page" : "false");
  });
  try { history.replaceState(null, "", "#" + tab); } catch (err) { /* file:// may refuse; the tab still works */ }
  RENDERERS[tab]();
}

/* ---------- overview ---------- */

const PIPELINE = [
  ["checker", "Checker", "Deterministic checks and the 14 planted-error attacks", "Rules in code, no AI decides a result"],
  ["harness", "Harness", "300 generated cases scored against the DBVO review", "Shows how often the reviewer finds planted errors"],
  ["retrieval", "Retrieval", "Keyword search in the rulebook chunks + AI answer with checked quotes", "Answers are candidates for a human"],
  ["seal", "Seal", "Run IDs and signed receipts for report fingerprints", "Detects edited or hidden vendor results"],
];

function renderOverview() {
  const box = document.getElementById("overview-view");
  clear(box);
  const live = APP.mode === "live";
  const figure = live ? "/figures/system-overview.png" : "../figures/system-overview.png";
  const parts = (APP.health && APP.health.parts) || {};
  const cards = PIPELINE.map(([key, name, what, note]) => {
    const p = parts[key];
    const state = live ? (p ? p.status : "unavailable") : "unavailable";
    const detail = !live ? "unknown – the server is not reachable (offline sample mode)" : p ? (p.reason || p.version || "") : "not reported by the server";
    return h("div", { class: "card pipe pipe-" + state },
      h("h4", {}, name + " ", badge(state)),
      h("p", { text: what }), h("p", { class: "meta", text: note }),
      h("p", { class: "evidence", text: detail }),
      p && p.cases ? h("p", { class: "meta", text: `${p.cases} cases loaded` + (p.latest_run ? ` · latest run ${p.latest_run}` : "") }) : null);
  });
  box.append(
    h("h2", { text: "What this demo shows" }),
    h("p", { class: "lead", text: "Employers send sick-leave data to health insurers through the electronic procedure for income replacement benefits (Entgeltersatzleistungen, § 95b SGB IV). " +
      "ITSG reviews whether payroll software sends this data correctly. Doing that by hand is slow, so Team 10 built a prototype of the review loop: " +
      "rules from the official documents become checks, the checks run on the software's output, every finding points back to its source, and a person makes the final decision. " +
      "All data here is synthetic." }),
    h("img", { class: "figure", src: figure, alt: "System overview diagram of the Team 10 review loop" }),
    h("h3", { text: "The pipeline and what is running right now" }),
    live ? null : message("warn", "Offline sample mode: availability of the parts is unknown."),
    h("div", { class: "pipeline" }, cards),
    h("h3", { text: "Where to go next" }),
    h("ul", {}, [
      ["report", "Review report – run the review and see every finding with its source and evidence chain."],
      ["cases", "Test cases – browse the 500 synthetic cases and the harness score."],
      ["ask", "Ask the rulebook – questions answered with checked quotes."],
      ["seal", "Trust & seal – how ITSG can tell whether a vendor edited or hid a result."],
    ].map(([tab, text]) => {
      const b = h("button", { class: "link", text: text.split(" – ")[0] });
      b.addEventListener("click", () => switchTab(tab));
      return h("li", {}, b, " – " + text.split(" – ")[1]);
    })),
    h("p", { class: "meta", text: live ? `UI ${APP.health.ui_version} · server time ${shortDate(APP.health.time)}` : "" }));
}

/* ---------- sources & requirements ---------- */

function renderSources() {
  const box = document.getElementById("sources-view");
  if (APP.mode === "offline") return renderOfflineSources(box);
  clear(box).append(loading("Loading the sources used by the latest review…"));
  api("/api/review/latest").then((payload) => drawSources(box, payload), (err) => {
    clear(box).append(h("h2", { text: "Sources & requirements" }), err.status === 404
      ? message("info", "No review report yet, so there are no cited sources to show. Run the review first.")
      : message("error", "The sources could not be loaded. " + problemText(err)));
  });
}

function drawSources(box, payload) {
  const findings = payload.data.findings || [];
  const bySource = new Map();
  findings.forEach((f) => {
    if (!bySource.has(f.source)) bySource.set(f.source, []);
    bySource.get(f.source).push(f);
  });
  const cards = [...bySource.entries()].map(([source, list]) => {
    const ask = h("button", { class: "chain-link", text: "Ask the rulebook about this" });
    ask.addEventListener("click", () => {
      switchTab("ask");
      const q = document.getElementById("question");
      if (q) { q.value = `What does ${source} say?`; q.dispatchEvent(new Event("input")); q.focus(); }
    });
    const criteria = [...new Set(list.map((f) => f.criterion_id).filter(Boolean))];
    return h("div", { class: "card", id: sourceAnchor(source) },
      h("h4", { class: "evidence", text: source }),
      h("p", {}, "Used by checks: ", list.map((f) => [h("span", { class: "chain-step", text: f.id }), " ", badge(f.status), "  "])),
      criteria.length ? h("p", { class: "meta", text: "Criterion IDs: " + criteria.join(", ") }) : null, ask);
  });
  clear(box).append(
    h("h2", { text: "Sources & requirements" }),
    message("info", `These are the sources cited by the ${findings.length} checks of report ${(payload.data.report || {}).id || "—"}. ` +
      "Source records, requirement text and criterion approvals are not part of the live data yet, so they are not shown here; " +
      "the earlier fabricated sample cards appear only in offline sample mode."),
    cards.length ? cards : message("info", "The report cites no sources."));
}

function jumpToItem(id) {
  switchTab("sources");
  const find = () => document.getElementById(id) || document.getElementById("item-" + id);
  const go = () => {
    const target = find();
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.remove("flash");
    void target.offsetWidth; // restart the CSS animation
    target.classList.add("flash");
  };
  if (find()) go(); else setTimeout(go, 400);   // live sources load asynchronously
}

/* ---------- start-up ---------- */

async function boot() {
  TABS.forEach((t) => document.getElementById("tab-" + t).addEventListener("click", () => switchTab(t)));
  try {
    const health = await api("/api/health", { timeoutMs: 15000 });
    if (!health || !health.parts) throw new Error("not our server");
    APP.mode = "live";
    APP.health = health;
  } catch (err) {
    APP.mode = "offline";
    document.getElementById("offline-banner").hidden = false;
    document.title = "OFFLINE SAMPLE DATA — " + document.title;
  }
  switchTab((location.hash || "").slice(1) || "overview");
}

boot();
