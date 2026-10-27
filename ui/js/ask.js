// "Ask the rulebook" tab: question -> retrieval + hessian.AI -> checked answer with citations.
// The answer, quotes and validation messages are untrusted text: shown with textContent only.

const EXAMPLE_QUESTIONS = [
  "Was muss bei einer Stornierung (Abgabegrund 88) immer gefuellt werden?",
  "Wann wird der Abgabegrund 41 verwendet?",
  "What does ANZAHL-AU mean in the DBVO data block?",
];
const MAX_QUESTION = 500;

function renderAsk() {
  const box = document.getElementById("ask-view");
  if (APP.mode === "offline") {
    clear(box).append(offlineNeedsServer("Ask the rulebook"));
    return;
  }
  if (box.dataset.built === "1") return;
  box.dataset.built = "1";

  const question = h("textarea", { id: "question", rows: 3, maxlength: MAX_QUESTION, "aria-label": "Your question",
    placeholder: "Ask about the DTA EEL rulebook, in German or English…" });
  const counter = h("span", { class: "hint", text: `0 / ${MAX_QUESTION}` });
  question.addEventListener("input", () => { counter.textContent = `${question.value.length} / ${MAX_QUESTION}`; });
  const askButton = h("button", { class: "primary", id: "ask-button", text: "Ask" });
  const result = h("div", { id: "ask-result", "aria-live": "polite" });

  const examples = h("div", { class: "examples" }, h("span", { class: "hint", text: "Examples:" }),
    EXAMPLE_QUESTIONS.map((q) => {
      const b = h("button", { class: "example", text: q });
      b.addEventListener("click", () => { question.value = q; counter.textContent = `${q.length} / ${MAX_QUESTION}`; question.focus(); });
      return b;
    }));

  askButton.addEventListener("click", () => withBusy(askButton, "Asking…", async () => {
    const text = question.value.trim();
    if (!text) {
      clear(result).append(message("warn", "Please type a question first."));
      return;
    }
    clear(result).append(loading("Searching the rulebook and asking the model (up to 90 seconds)…"));
    try {
      showAnswer(result, await api("/api/ask", { method: "POST", body: { question: text }, timeoutMs: 100000 }));
    } catch (err) {
      clear(result).append(message("error", "The question could not be answered. " + problemText(err)));
    }
  }));

  clear(box).append(
    h("h2", { text: "Ask the rulebook" }),
    message("info", "The answer comes from an AI model reading the retrieved rulebook passages. Every quote is checked word for word against the passage. " +
      "A checked quote proves the quote exists, not that the answer is right. A person must review it; this is not a legal decision."),
    h("label", { for: "question", text: "Your question" }), question,
    h("div", { class: "toolbar" }, askButton, counter), examples, result);
}

function showAnswer(box, r) {
  clear(box);
  const status = r.status;
  const cites = Array.isArray(r.citations) ? r.citations : [];
  const errors = Array.isArray(r.validation_errors) ? r.validation_errors : [];
  box.append(h("p", {}, "Status: ", badge(status)));

  if (status === "ANSWERED") {
    box.append(h("div", { class: "answer answer-ok" }, h("h3", { text: "Answer" }), h("p", { class: "answer-text", text: r.answer })));
  } else if (status === "BLOCKED") {
    // privacy airlock: personal data was left after pseudonymization. Its own red card, not the yellow review box.
    const priv = (r.audit && r.audit.privacy) || {};
    box.append(h("div", { class: "answer answer-blocked", role: "alert" },
      h("h3", { text: "⛔ Blocked by the privacy airlock" }),
      h("p", { text: "Your question or a retrieved passage still contained personal data after it was replaced. Nothing was sent to the model, and there is no answer." }),
      errors.length ? h("ul", {}, errors.map((e) => h("li", { text: e }))) : null,
      (priv.blocked_categories || []).length ? h("p", { class: "meta", text: "Categories: " + priv.blocked_categories.join(", ") }) : null,
      h("p", { class: "meta", text: "Remove names, numbers and contact data from the question, or check the Datenschutz tab." })));
  } else if (status === "NOT_FOUND") {
    box.append(h("div", { class: "answer answer-none" }, h("h3", { text: "Not in the documents" }),
      h("p", { text: "The retrieved rulebook passages do not contain an answer to this question. No answer is shown." }),
      r.answer ? h("details", {}, h("summary", { text: "Show the model's note" }), h("p", { class: "unverified", text: r.answer })) : null));
  } else {
    box.append(h("div", { class: "answer answer-review", role: "alert" },
      h("h3", { text: "⚠ Needs human review – this is NOT a confirmed answer" }),
      h("p", { text: "A check failed or the model was unsure. Do not use the text below without a person verifying it against the rulebook." }),
      errors.length ? h("ul", {}, errors.map((e) => h("li", { text: e }))) : null,
      h("details", {}, h("summary", { text: "Show the unverified model text" }), h("p", { class: "unverified", text: r.answer || "(no text)" }))));
  }

  if (status !== "NEEDS_REVIEW" && status !== "BLOCKED" && errors.length) {
    box.append(h("h4", { text: "Validation errors" }), h("ul", { class: "errors" }, errors.map((e) => h("li", { text: e }))));
  }
  if (!errors.length) box.append(h("p", { class: "meta", text: "Validation: every check passed." }));

  box.append(h("h4", { text: `Citations (${cites.length})` }));
  if (!cites.length) box.append(h("p", { class: "meta", text: "No citations." }));
  cites.forEach((c) => box.append(citationCard(c)));

  const a = r.audit || {};
  box.append(h("details", { class: "audit", open: true }, h("summary", { text: "Audit" }),
    h("table", {}, h("tbody", {}, [
      ["Model", `${a.provider || "—"} / ${a.model_id || "—"}`], ["Model revision", a.model_revision],
      ["Attempts", a.attempts], ["Prompt contract", a.prompt_contract_version], ["Run", a.run_id],
      ["Time", a.timestamp ? shortDate(a.timestamp) : "—"], ["Passages sent", (a.input_ids || []).join(", ")],
      ["Validation errors", a.validation_error_count],
      ["Privacy", a.privacy ? `policy ${a.privacy.policy_version || "—"}; removed ${formatValue(a.privacy.categories_removed || {})}` : "—"],
    ].map(([k, v]) => h("tr", {}, h("th", { text: k }), h("td", { text: formatValue(v) })))))));
}

function citationCard(c) {
  const doc = String(c.chunk_id || "").split("/")[0] || "—";
  let level;
  if (c.match_level === "exact") level = h("span", { class: "match match-exact", text: "exact match" });
  else if (c.match_level === "table") level = h("span", { class: "match match-table", text: "matched across a table – please spot-check" });
  else level = h("span", { class: "match match-none", text: "quote NOT verified" });
  return h("div", { class: "card citation" },
    h("p", { class: "evidence", text: `Document ${doc} · Section ${formatValue(c.section)} · Page ${formatValue(c.page)}  (${formatValue(c.chunk_id)})` }),
    h("blockquote", { text: c.quote }), level);
}
