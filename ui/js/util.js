// Shared helpers. Every piece of text that comes from the data (reports, test cases, AI answers,
// quotes) is put on the page with textContent through h(): it can never become markup.
// This UI never builds markup from data.

// Shared state. mode: "unknown" until the server answered /api/health, then "live" or "offline" (sample data).
const APP = { mode: "unknown", health: null, report: null };

/** h("tag", {class: "x", onclick: fn, "data-id": "y"}, child, "text", ...) -> DOM element */
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "text") el.textContent = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

// The native append() turns arrays into "[object ...]" text and null into "null". Flatten arrays and
// skip empty values, so el.append(list.map(...), maybeNull) works like h() does.
const nativeAppend = Element.prototype.append;
Element.prototype.append = function (...children) {
  return nativeAppend.apply(this, children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
};

function clear(el) {
  el.replaceChildren();
  return el;
}

/* ---------- status badges ---------- */

const STATUS_STYLES = {
  "PASS": "badge-pass",
  "MISMATCH": "badge-mismatch",
  "NOT EVALUATED": "badge-not-evaluated",
  "NOT_EVALUATED": "badge-not-evaluated",
  "NEEDS_REVIEW": "badge-needs-review",
  "BLOCKED": "badge-blocked",
  "ANSWERED": "badge-pass",
  "NOT_FOUND": "badge-not-evaluated",
  "GENUINE": "badge-pass",
  "TAMPERED": "badge-mismatch",
  "LEDGER_TAMPERED": "badge-mismatch",
  "UNKNOWN_RUN": "badge-not-evaluated",
  "NEVER SUBMITTED": "badge-never",
  "SUBMITTED": "badge-neutral",
  "CAUGHT": "badge-pass",
  "MISSED": "badge-mismatch",
  "available": "badge-pass",
  "unavailable": "badge-not-evaluated",
};

/** Unknown statuses are neutral gray, never green: a status we do not know cannot look like a pass. */
function badge(status) {
  const text = status === null || status === undefined || status === "" ? "UNKNOWN" : String(status);
  const style = Object.prototype.hasOwnProperty.call(STATUS_STYLES, text) ? STATUS_STYLES[text] : "badge-neutral";
  return h("span", { class: "badge " + style, text: text.replace(/_/g, " ") });
}

/* ---------- values and messages ---------- */

function formatValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function message(kind, ...children) {
  return h("div", { class: "msg msg-" + kind, role: kind === "error" ? "alert" : "status" }, children);
}

function loading(text) {
  return h("p", { class: "loading", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), " " + text);
}

function shortDate(iso) {
  const d = new Date(iso);
  return isNaN(d) ? String(iso || "—") : d.toLocaleString("en-GB", { hour12: false });
}

function pre(value) {
  return h("pre", { text: typeof value === "string" ? value : JSON.stringify(value, null, 2) });
}

/** Run an async action behind a button: disables it and shows a busy label, restores it afterwards. */
async function withBusy(button, busyLabel, action) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}
