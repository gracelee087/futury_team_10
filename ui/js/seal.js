// "Trust & seal" tab: who checks the vendor? Runs the vendor-honesty demo against the real seal server.

const SEAL_LIMITS = [
  "A vendor who changes the tool itself, or the software output before the check, is NOT stopped. The seal only proves “this report is exactly what was submitted for this run”. It does not prove the report is true. ITSG spot checks stay necessary.",
  "A vendor can run the tool many times and only ever submit the best run. The seal makes this visible (many runs, few submissions); it does not prevent it. ITSG has to look at the run list.",
  "HMAC means only ITSG can verify. If anyone ever needs to verify without ITSG's secret, we would need public-key signatures.",
  "Whoever has the server, the secret or the ledger can forge anything. The demo secrets are throwaway: no rotation, no vault, no hardware key.",
  "Traffic to the seal is plain HTTP inside the server's private network; put TLS in front of it for real use. There are no rate limits yet.",
  "Only the report hash is sent to the seal, never the report. Nothing here is a legal approval or certification.",
];

function renderSeal() {
  const box = document.getElementById("seal-view");
  if (APP.mode === "offline") {
    clear(box).append(offlineNeedsServer("Trust & seal"));
    return;
  }
  if (box.dataset.built === "1") return;
  box.dataset.built = "1";

  const demoButton = h("button", { class: "primary", id: "seal-demo", text: "Run vendor-honesty demo" });
  const refresh = h("button", { text: "Refresh runs" });
  const steps = h("div", { id: "seal-steps" });
  const runs = h("div", { id: "seal-runs" });

  demoButton.addEventListener("click", () => withBusy(demoButton, "Running demo…", async () => {
    clear(steps).append(loading("Talking to the seal server…"));
    try {
      const data = await api("/api/seal/demo", { method: "POST", timeoutMs: 60000 });
      showSealSteps(steps, data);
      showSealRuns(runs, data.runs);
    } catch (err) {
      clear(steps).append(message(err.status === 503 ? "warn" : "error", "The demo could not be run. " + problemText(err)));
    }
  }));
  refresh.addEventListener("click", () => withBusy(refresh, "Loading…", () => loadSealRuns(runs)));

  clear(box).append(
    h("h2", { text: "Trust & seal: who checks the vendor?" }),
    h("p", { class: "lead", text: "A software vendor could run our review tool on their own computer and quietly edit a failing result or hide a bad run. " +
      "So the vendor first gets a run ID from ITSG, and afterwards sends ITSG only a fingerprint (hash) of the finished report, which ITSG stamps with a signed receipt. " +
      "ITSG can then see whether a report was edited after sealing (TAMPERED) and which runs were started but never submitted (NEVER SUBMITTED)." }),
    h("div", { class: "toolbar" }, demoButton,
      h("span", { class: "hint", text: "Uses the latest review report and the real seal server. Each demo adds two runs to its ledger. The tokens stay on the server." })),
    steps,
    h("h3", { text: "All runs known to ITSG" }), h("div", { class: "toolbar" }, refresh), runs,
    h("h3", { text: "Honest limits" }), h("ul", { class: "limits" }, SEAL_LIMITS.map((t) => h("li", { text: t }))),
    h("p", { class: "meta", text: "Source: seal/README.md" }));
  loadSealRuns(runs);
}

function showSealSteps(box, data) {
  const labels = { 3: "GENUINE", 4: "TAMPERED", 5: "NEVER SUBMITTED" };
  clear(box).append(h("h3", { text: `Demo result (report ${data.report_id || "—"})` }),
    h("ol", { class: "seal-steps" }, data.steps.map((s) => h("li", { class: "seal-step" },
      h("div", {}, h("strong", { text: s.title })),
      h("div", {}, s.step >= 3 ? badge(s.result) : h("span", { class: "badge badge-neutral", text: s.result }),
        s.run_id ? h("span", { class: "evidence", text: "  " + s.run_id }) : null),
      s.detail ? h("div", { class: "meta", text: s.detail }) : null,
      s.change ? h("div", { class: "meta", text: `Altered: finding ${formatValue(s.change.finding)} changed from ${s.change.from} to ${s.change.to}` }) : null,
      labels[s.step] && s.result !== labels[s.step] ? message("error", `Expected ${labels[s.step]} here but the seal said ${s.result}. Do not trust this run.`) : null))));
}

async function loadSealRuns(target) {
  clear(target).append(loading("Loading runs…"));
  try {
    showSealRuns(target, await api("/api/seal/runs"));
  } catch (err) {
    clear(target).append(message(err.status === 503 ? "warn" : "error", "The runs could not be loaded. " + problemText(err)));
  }
}

function showSealRuns(target, data) {
  if (!data || !Array.isArray(data.runs)) {
    clear(target).append(message("warn", `The seal reports: ${formatValue(data && (data.result || data.reason))}`));
    return;
  }
  clear(target).append(
    h("p", {}, `${data.total} run(s), `, h("strong", { text: `${data.never_submitted} never submitted` })),
    data.runs.length ? h("table", { id: "seal-runs-table" }, h("thead", {}, h("tr", {}, ["Run", "Issued", "Submitted", "State"].map((t) => h("th", { text: t })))),
      h("tbody", {}, data.runs.slice().reverse().map((r) => h("tr", {}, h("td", { class: "evidence", text: r.run_id }),
        h("td", { text: shortDate(r.issued_at) }), h("td", { text: r.submitted ? shortDate(r.submitted_at) : "—" }),
        h("td", {}, badge(r.submitted ? "SUBMITTED" : "NEVER SUBMITTED")))))) : message("info", "No runs yet."));
}
