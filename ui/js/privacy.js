// "Datenschutz" tab: what the AI sees, the data-flow map, the leak-test scorecard and a short "why" box.
// All text from the server is untrusted and shown with textContent through h().

const PRIVACY_EXAMPLE =
  "Frau Anna Beispiel (VSNR 12 150685 B 123, anna.beispiel@example.org, Tel. 069/123456) war vom 11.03.2026 bis 20.03.2026 " +
  "arbeitsunfähig (AU). Welche Daten braucht die Anforderung mit Abgabegrund 41?";
const PRIVACY_MAX = 5000;
const LIGHT_LABEL = { green: "GREEN", yellow: "YELLOW", red: "RED" };

function renderPrivacy() {
  const box = document.getElementById("privacy-view");
  if (APP.mode === "offline") {
    clear(box).append(offlineNeedsServer("Datenschutz"));
    return;
  }
  if (box.dataset.built === "1") return;
  box.dataset.built = "1";

  const flows = h("div", { id: "privacy-flows" }, loading("Loading the data-flow map…"));
  const score = h("div", { id: "privacy-score" }, loading("Loading the leak-test result (the first run can take a few seconds)…"));
  clear(box).append(
    h("h2", { text: "Datenschutz – privacy airlock" }),
    message("info", "Before any text goes to the AI model, personal data is found by fixed rules (no AI) and replaced by tokens like PERSON_1. " +
      "A second check blocks the request if anything personal is left. This page shows that live."),
    previewSection(),
    h("h3", { text: "2. Data-flow map" }), flows,
    h("h3", { text: "3. Leak-test scorecard" }), score,
    whyBox());
  loadFlows(flows);
  loadScore(score);
}

/* ---------- 1. what the AI sees ---------- */

function previewSection() {
  const input = h("textarea", { id: "privacy-input", rows: 6, maxlength: PRIVACY_MAX, "aria-label": "Text to check" });
  input.value = PRIVACY_EXAMPLE;
  const out = h("div", { id: "privacy-preview", "aria-live": "polite" });
  const run = h("button", { class: "primary", text: "Show what leaves the system" });
  run.addEventListener("click", () => withBusy(run, "Checking…", async () => {
    const text = input.value.trim();
    if (!text) {
      clear(out).append(message("warn", "Please type or paste some text first."));
      return;
    }
    clear(out).append(loading("Checking…"));
    try {
      showPreview(out, text, await api("/api/privacy/preview", { method: "POST", body: { text }, timeoutMs: 20000 }));
    } catch (err) {
      clear(out).append(message("error", "The check could not be done. " + problemText(err)));
    }
  }));
  return h("section", {},
    h("h3", { text: "1. What the AI sees" }),
    h("p", { class: "meta", text: "Synthetic example below. Use made-up data only; the text is processed in memory and not stored or logged." }),
    input, h("div", { class: "toolbar" }, run), out);
}

function showPreview(out, original, r) {
  clear(out);
  const cats = Object.entries((r.summary && r.summary.categories) || {});
  if (r.blocked) {
    out.append(h("div", { class: "answer answer-blocked", role: "alert" },
      h("h3", { text: "⛔ BLOCKED – nothing would be sent" }),
      h("p", { text: "Personal data was still present after replacing it (" + (r.blocked_categories || []).join(", ") + "). " +
        "The request would be stopped here, no model call. The cleaned text is not shown because it still contains personal data." })));
  } else {
    out.append(message("info", `Would be sent: yes, in the cleaned form below. Policy ${r.policy_version}, key source: ${r.key_source}.`));
  }
  out.append(h("div", { class: "side-by-side" },
    h("div", {}, h("h4", { text: "You typed (stays here)" }), h("pre", { class: "orig", text: original })),
    h("div", {}, h("h4", { text: "What the AI sees" }), h("pre", { class: "clean", text: r.blocked ? "(withheld)" : r.clean_text }))));
  out.append(h("h4", { text: `Categories removed (${(r.summary && r.summary.total) || 0})` }),
    cats.length ? h("table", {}, h("tbody", {}, cats.map(([name, count]) => h("tr", {}, h("th", { text: name }), h("td", { text: count })))))
      : h("p", { class: "meta", text: "Nothing personal was found in this text." }));
}

/* ---------- 2. data-flow map ---------- */

function lightBadge(light) {
  return h("span", { class: "light light-" + (LIGHT_LABEL[light] ? light : "unknown"), text: LIGHT_LABEL[light] || "UNKNOWN" });
}

function loadFlows(box) {
  api("/api/privacy/flows").then((data) => {
    clear(box).append(
      h("p", { class: "meta", text: `Built from the policy (${data.policy_version}) and this server's settings. Reports are kept ${data.retention_days} days.` }),
      h("table", { class: "flows" },
        h("thead", {}, h("tr", {}, ["Destination", "What is sent", "Protection", "Where", "Light"].map((t) => h("th", { text: t })))),
        h("tbody", {}, data.flows.map((f) => h("tr", {},
          h("td", {}, h("strong", { text: f.destination }), h("div", { class: "meta", text: f.note })),
          h("td", { text: f.sends }), h("td", { text: f.protection }), h("td", { text: f.location }), h("td", {}, lightBadge(f.light)))))),
      h("p", { class: "meta" }, Object.entries(data.light_meaning || {}).map(([k, v]) => [lightBadge(k), " " + v + "  "])));
  }, (err) => clear(box).append(message("error", "The data-flow map could not be loaded. " + problemText(err))));
}

/* ---------- 3. scorecard ---------- */

function scoreRow(label, value, note) {
  return h("tr", {}, h("th", { text: label }), h("td", { text: value }), h("td", { class: "meta", text: note || "" }));
}

function loadScore(box) {
  api("/api/privacy/leaktest", { timeoutMs: 130000 }).then(({ source, result }) => {
    const a = result.author, i = result.independent, fp = result.false_positives;
    clear(box).append(
      h("p", { class: "meta", text: `Result ${source}, generated ${shortDate(result.generated_at)}. Synthetic data only.` }),
      h("h4", { text: "Author's own tests (not independent)" }),
      h("table", {}, h("tbody", {},
        scoreRow("Records / planted values", `${a.records} / ${a.planted}`, "sent through ask() with a fake model, plus the log path and the audit record"),
        scoreRow("Leaked", String(a.leaked), "goal 0; detectors were tuned on records like these, so this is not independent evidence"),
        scoreRow("Extra random draws (8 x 50)", `${a.extra_seeds.planted} planted, ${a.extra_seeds.leaked} leaked`, "same generator, same templates"),
        scoreRow("Stress: names without a cue word", `${a.stress_uncued_names.planted} planted, ${a.stress_uncued_names.leaked} leaked`, "known limit of regex detection"))),
      h("h4", { text: "Independent reviewer set" }),
      h("table", {}, h("tbody", {},
        scoreRow("First run, before the fix", `${i.first_run_before_fix.caught} of ${i.planted} caught, ${i.first_run_before_fix.leaked} leaked`, i.first_run_before_fix.note),
        scoreRow("After the fix", `${i.planted - i.leaked_after_fix} of ${i.planted} removed`, `${i.records} records written by someone else; fixed because of them, so re-check with new records`))),
      h("h4", { text: "False positives on rulebook text" }),
      h("table", {}, h("tbody", {},
        scoreRow("50-chunk sample", `${fp.sample.strict} of ${fp.sample.chunks} (strict)`, `${fp.sample.specimens_allowed} with public specimen values allowed`),
        scoreRow("All chunks", `${fp.all.strict} of ${fp.all.chunks} (strict)`, `${fp.all.specimens_allowed} with public specimen values allowed`))),
      h("h4", { text: "Known limits" }),
      h("ul", {}, (result.known_limits || []).map((t) => h("li", { text: t }))));
  }, (err) => clear(box).append(message("error", "The leak-test result could not be loaded. " + problemText(err))));
}

/* ---------- 4. why ---------- */

function whyBox() {
  return h("section", { class: "card why" },
    h("h3", { text: "4. Why this matters" }),
    h("ul", {}, [
      "Health data (Art. 9 GDPR): sick-leave dates of a named person are health data and need special protection.",
      "Social data (§ 35 SGB I): social secrecy applies to data held by insurers and their service providers.",
      "Privacy by design (Art. 25 GDPR): protection is built into the code path, not added by hand afterwards.",
      "Data minimization (Art. 5(1)(c) GDPR): the AI gets only what it needs, never names or numbers.",
      "Storage limitation (Art. 5(1)(e) GDPR): reports are deleted automatically after a set number of days.",
    ].map((t) => h("li", { text: t }))),
    h("p", { class: "meta", text: "Engineering view, not legal advice. Pseudonymized data is still personal data while it can be linked back." }));
}
