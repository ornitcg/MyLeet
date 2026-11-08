"use strict";

const $ = (id) => document.getElementById(id);
const state = { problem: null, editor: null, saveTimer: null, results: null, selected: 0 };

// ---------- helpers ----------
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const fmt = (v) => JSON.stringify(v);
const fmtArgs = (args) => Object.entries(args).map(([k, v]) => `${k} = ${fmt(v)}`).join(", ");

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ---------- editor ----------
function initEditor() {
  const ta = $("editor");
  if (window.CodeMirror) {
    const cm = CodeMirror.fromTextArea(ta, {
      mode: "python", theme: "material-darker", lineNumbers: true, indentUnit: 4,
      tabSize: 4, matchBrackets: true, autoCloseBrackets: true, direction: "ltr",
      extraKeys: {
        Tab: (c) => c.somethingSelected() ? c.indentSelection("add") : c.replaceSelection("    ", "end"),
        "Shift-Tab": (c) => c.indentSelection("subtract"),
        "Ctrl-Enter": () => run("all"),
        "Ctrl-'": () => run("examples"),
      },
    });
    cm.on("change", scheduleSave);
    state.editor = { get: () => cm.getValue(), set: (v) => { cm.setValue(v); cm.clearHistory(); }, refresh: () => cm.refresh() };
  } else {
    // CDN unavailable: plain textarea fallback
    ta.addEventListener("input", scheduleSave);
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Tab") { e.preventDefault(); document.execCommand("insertText", false, "    "); }
      if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); run("all"); }
    });
    state.editor = { get: () => ta.value, set: (v) => { ta.value = v; }, refresh: () => {} };
  }
}

function scheduleSave() {
  if (!state.problem) return;
  $("saveState").textContent = "";
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(async () => {
    try {
      await api(`/api/problems/${state.problem.slug}/save`, { code: state.editor.get() });
      $("saveState").textContent = "נשמר";
    } catch { $("saveState").textContent = "שמירה נכשלה"; }
  }, 800);
}

// ---------- problem list ----------
async function loadList() {
  const items = await api("/api/problems");
  const sel = $("problemSelect");
  sel.innerHTML = `<option value="">— בחרי בעיה —</option>` +
    items.map((p) => `<option value="${esc(p.slug)}">${p.solved ? "✓ " : ""}${esc(p.title)}</option>`).join("");
  if (state.problem) sel.value = state.problem.slug;
  $("problemList").innerHTML = items.length
    ? items.map((p) => `<li><a href="#/p/${esc(p.slug)}"><span class="check">${p.solved ? "✓" : ""}</span><span dir="auto">${esc(p.title)}</span></a></li>`).join("")
    : `<li class="muted">עדיין אין בעיות. צרי את הראשונה למעלה.</li>`;
  return items;
}

// ---------- new problem ----------
async function generate() {
  const description = $("newDesc").value.trim();
  if (!description) { $("newDesc").focus(); return; }
  const btn = $("genBtn");
  btn.disabled = true;
  $("genError").classList.add("hidden");
  const started = Date.now();
  const tick = () => { $("genStatus").innerHTML = `<span class="spinner"></span>Claude כותב דוגמאות, טסטים ופתרון ייחוס... (${Math.round((Date.now() - started) / 1000)} שניות)`; };
  tick();
  const timer = setInterval(tick, 1000);
  try {
    const { slug } = await api("/api/problems", { description, title: $("newTitle").value });
    $("newDesc").value = ""; $("newTitle").value = "";
    location.hash = `#/p/${slug}`;
  } catch (e) {
    $("genError").textContent = e.message;
    $("genError").classList.remove("hidden");
  } finally {
    clearInterval(timer);
    $("genStatus").textContent = "";
    btn.disabled = false;
  }
}

// ---------- problem view ----------
function renderDescription(p) {
  const examples = p.examples.map((e, i) => `
    <div class="example">
      <h3>דוגמה ${i + 1}:</h3>
      <div class="example-box"><b>Input:</b> ${esc(fmtArgs(e.args))}
<b>Output:</b> ${esc(fmt(e.expected))}${e.explanation ? `
<b>Explanation:</b> <span class="expl" dir="auto">${esc(e.explanation)}</span>` : ""}</div>
    </div>`).join("");
  const constraints = p.constraints.length
    ? `<h3>אילוצים:</h3><ul class="constraints">${p.constraints.map((c) => `<li><code>${esc(c)}</code></li>`).join("")}</ul>` : "";
  const assumptions = p.assumptions.length
    ? `<div class="note"><b>הנחות ש-Claude הניח (התיאור לא הגדיר אותן במפורש):</b><ul>${p.assumptions.map((a) => `<li dir="auto">${esc(a)}</li>`).join("")}</ul></div>` : "";
  const warnings = (p.warnings || []).length
    ? `<div class="note warn">${p.warnings.map(esc).join("<br>")}</div>` : "";
  const orderNote = { unordered: "סדר האיברים בתשובה לא משנה.", unordered_nested: "סדר האיברים (גם ברשימות הפנימיות) לא משנה.", float: "התשובה נבדקת בדיוק של 10⁻⁶." }[p.compare];

  $("descBody").innerHTML = `
    <h1><span dir="auto">${esc(p.title)}</span>${p.solved ? `<span class="badge">נפתר ✓</span>` : ""}</h1>
    <div class="description" dir="auto">${esc(p.description)}</div>
    ${examples}
    ${constraints}
    ${orderNote ? `<p class="muted">${orderNote}</p>` : ""}
    ${assumptions}
    ${warnings}
    <div class="meta muted">פונקציה: <code>${esc(p.signature)}</code> · ${p.test_count} טסטים</div>`;
}

async function openProblem(slug) {
  showView("viewProblem");
  try {
    const p = await api(`/api/problems/${encodeURIComponent(slug)}`);
    state.problem = p;
    state.openSub = null;
    renderDescription(p);
    setTab("desc");
    renderSubmissions();
    state.editor.set(p.code);
    state.editor.refresh();
    $("saveState").textContent = "";
    $("resultsBody").innerHTML = `<p class="muted">הריצי את הקוד כדי לראות תוצאות. <span dir="ltr">Ctrl+Enter</span> שולח את כל הטסטים.</p>`;
    $("problemSelect").value = slug;
  } catch (e) {
    $("descBody").innerHTML = `<pre class="error-box">${esc(e.message)}</pre>`;
  }
}

async function run(scope) {
  if (!state.problem) return;
  clearTimeout(state.saveTimer);
  $("runBtn").disabled = $("submitBtn").disabled = true;
  $("resultsBody").innerHTML = `<p><span class="spinner"></span>מריץ...</p>`;
  try {
    const res = await api(`/api/problems/${state.problem.slug}/run`, { code: state.editor.get(), scope });
    state.results = res;
    const firstBad = res.results.findIndex((r) => r.status !== "pass");
    state.selected = firstBad === -1 ? 0 : firstBad;
    renderResults();
    $("saveState").textContent = "נשמר";
    if (scope === "all" && res.passed === res.total && !state.problem.solved) {
      state.problem.solved = true;
      renderDescription(state.problem);
      loadList();
    }
    if (res.saved_submission) {
      addSubmissionToState(res.saved_submission);
      $("resultsBody").insertAdjacentHTML("afterbegin",
        `<div class="flash">✓ הפתרון נשמר בלשונית "הפתרונות שלי"</div>`);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<pre class="error-box">${esc(e.message)}</pre>`;
  } finally {
    $("runBtn").disabled = $("submitBtn").disabled = false;
  }
}

function renderResults() {
  const res = state.results;
  if (res.fatal) {
    $("resultsBody").innerHTML = `<div class="verdict bad">Compile / Runtime Error</div><div class="detail"><pre class="bad">${esc(res.fatal)}</pre></div>`;
    return;
  }
  const all = res.passed === res.total;
  const statuses = res.results.map((r) => r.status);
  const verdict = all ? (res.scope === "all" ? "Accepted" : "הדוגמאות עברו")
    : statuses.includes("timeout") ? "Time Limit Exceeded"
    : statuses.includes("error") ? "Runtime Error" : "Wrong Answer";
  const chips = res.results.map((r, i) =>
    `<button class="chip ${r.status} ${i === state.selected ? "active" : ""}" data-i="${i}">${esc(r.name)}</button>`).join("");

  const r = res.results[state.selected];
  let detail = `<div class="label">Input</div><pre>${esc(fmtArgs(r.args))}</pre>`;
  if (r.status === "pass" || r.status === "fail") {
    detail += `<div class="label">Output</div><pre class="${r.status === "pass" ? "good" : "bad"}">${esc(fmt(r.actual))}</pre>`;
  }
  detail += `<div class="label">Expected</div><pre>${esc(fmt(r.expected))}</pre>`;
  if (r.error) detail += `<div class="label">Error</div><pre class="bad">${esc(r.error)}</pre>`;
  if (r.stdout) detail += `<div class="label">Stdout</div><pre>${esc(r.stdout)}</pre>`;
  if (r.status === "skipped") detail += `<p class="muted">הטסט לא רץ כי טסט קודם חרג מזמן הריצה.</p>`;
  if (r.ms !== undefined) detail += `<div class="label">${r.ms} ms</div>`;

  $("resultsBody").innerHTML = `
    <div class="verdict ${all ? "ok" : "bad"}">${verdict} <span class="muted small">${res.passed} / ${res.total} עברו</span></div>
    <div class="chips">${chips}</div>
    <div class="detail">${detail}</div>`;
  $("resultsBody").querySelectorAll(".chip").forEach((c) =>
    c.addEventListener("click", () => { state.selected = +c.dataset.i; renderResults(); }));
}

// ---------- saved solutions ----------
const subsCache = {}; // "slug/id" -> code

function setTab(name) {
  document.querySelectorAll(".desc-panel .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $("descBody").classList.toggle("hidden", name !== "desc");
  $("subsBody").classList.toggle("hidden", name !== "subs");
  if (name === "subs") renderSubmissions();
}

function addSubmissionToState(entry) {
  state.problem.submissions.unshift(entry);
  state.openSub = null;
  renderSubmissions();
}

function fmtTime(iso) {
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function renderSubmissions() {
  const subs = state.problem ? state.problem.submissions : [];
  $("subsCount").textContent = subs.length ? `(${subs.length})` : "";
  if (!subs.length) {
    $("subsBody").innerHTML = `<p class="muted">עדיין אין פתרונות שמורים.</p>
      <p class="muted">לחיצה על "שמור פתרון" (או <span dir="ltr">Ctrl+S</span>) שומרת עותק של הקוד.
      גם כל הגשה שעוברת את כל הטסטים נשמרת כאן אוטומטית.</p>`;
    return;
  }
  $("subsBody").innerHTML = `<ul class="subs-list">${subs.map((s) => {
    const tag = s.kind === "accepted"
      ? `<span class="tag accepted">עבר ✓ ${s.passed}/${s.total}</span>`
      : `<span class="tag manual">שמירה ידנית</span>`;
    const open = state.openSub === s.id;
    const code = subsCache[`${state.problem.slug}/${s.id}`];
    const body = open ? `<div class="sub-body">${code === undefined ? `<p><span class="spinner"></span>טוען...</p>`
      : `<pre>${esc(code)}</pre><button class="btn btn-sm" data-load="${s.id}">טען לעורך</button>`}</div>` : "";
    return `<li class="sub"><button class="sub-head" data-id="${s.id}">${tag}
      <span class="sub-note" dir="auto">${esc(s.note || "")}</span>
      <span class="sub-time">${fmtTime(s.created)}</span></button>${body}</li>`;
  }).join("")}</ul>`;
}

async function toggleSubmission(id) {
  state.openSub = state.openSub === id ? null : id;
  renderSubmissions();
  const key = `${state.problem.slug}/${id}`;
  if (state.openSub === id && subsCache[key] === undefined) {
    try {
      subsCache[key] = (await api(`/api/problems/${state.problem.slug}/submissions/${id}`)).code;
    } catch (e) {
      subsCache[key] = `# שגיאה בטעינה: ${e.message}`;
    }
    renderSubmissions();
  }
}

function loadSubmission(id) {
  const code = subsCache[`${state.problem.slug}/${id}`];
  if (code === undefined) return;
  if (!confirm("לטעון את הפתרון הזה לעורך? הקוד שבעורך כרגע יוחלף.\nכדאי לשמור אותו קודם אם הוא חשוב לך.")) return;
  state.editor.set(code);
  scheduleSave();
}

function openSaveDialog() {
  if (!state.problem) return;
  $("saveNote").value = "";
  $("saveDialog").showModal();
  $("saveNote").focus();
}

async function saveSubmission() {
  const note = $("saveNote").value;
  try {
    const entry = await api(`/api/problems/${state.problem.slug}/submissions`, { code: state.editor.get(), note });
    subsCache[`${state.problem.slug}/${entry.id}`] = state.editor.get();
    addSubmissionToState(entry);
    $("saveState").textContent = "הפתרון נשמר ✓";
  } catch (e) {
    alert(`השמירה נכשלה: ${e.message}`);
  }
}

// ---------- resizable panels ----------
const LAYOUT_KEY = "myleet.layout";
const LAYOUT_DEFAULT = { descW: 42, resultsH: 38 }; // percentages

function loadLayout() {
  try { return { ...LAYOUT_DEFAULT, ...JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") }; }
  catch { return { ...LAYOUT_DEFAULT }; }
}
function saveLayout(layout) {
  try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch { /* storage unavailable */ }
}

function initSplitters() {
  const layout = loadLayout();
  const ws = $("viewProblem"), code = $("codePanel");
  const apply = () => {
    ws.style.setProperty("--desc-w", `${layout.descW}%`);
    code.style.setProperty("--results-h", `${layout.resultsH}%`);
    state.editor && state.editor.refresh();
  };
  const clampPct = (px, total, minPx, maxPx) => (Math.min(Math.max(px, minPx), Math.max(minPx, total - maxPx)) / total) * 100;

  // Column splitter: description width. In RTL the description is on the right side.
  const setDescFromX = (x) => {
    const r = ws.getBoundingClientRect();
    const rtl = getComputedStyle(ws).direction === "rtl";
    const px = rtl ? r.right - x : x - r.left;
    layout.descW = clampPct(px, r.width, 220, 340);
  };
  // Row splitter: results height, measured from the bottom of the code panel.
  const setResultsFromY = (y) => {
    const r = code.getBoundingClientRect();
    layout.resultsH = clampPct(r.bottom - y, r.height, 70, 150);
  };

  const makeDraggable = (el, onMove, axisClass, key, keyStep) => {
    let frame = 0;
    el.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      el.classList.add("dragging");
      document.body.classList.add(axisClass);
    });
    el.addEventListener("pointermove", (e) => {
      if (!el.hasPointerCapture(e.pointerId)) return;
      onMove(e);
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(apply);
    });
    const end = (e) => {
      if (!el.hasPointerCapture(e.pointerId)) return;
      el.releasePointerCapture(e.pointerId);
      el.classList.remove("dragging");
      document.body.classList.remove(axisClass);
      saveLayout(layout);
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
    el.addEventListener("dblclick", () => { layout[key] = LAYOUT_DEFAULT[key]; apply(); saveLayout(layout); });
    el.addEventListener("keydown", (e) => {
      const d = keyStep(e.key);
      if (!d) return;
      e.preventDefault();
      layout[key] = Math.min(80, Math.max(15, layout[key] + d));
      apply(); saveLayout(layout);
    });
  };

  makeDraggable($("splitCols"), (e) => setDescFromX(e.clientX), "resizing-col", "descW",
    (k) => ({ ArrowLeft: 2, ArrowRight: -2 })[k] * (getComputedStyle(ws).direction === "rtl" ? 1 : -1) || 0);
  makeDraggable($("splitRows"), (e) => setResultsFromY(e.clientY), "resizing-row", "resultsH",
    (k) => ({ ArrowUp: 3, ArrowDown: -3 })[k] || 0);
  apply();
}

// ---------- routing ----------
function showView(id) {
  for (const v of ["viewNew", "viewProblem"]) $(v).classList.toggle("hidden", v !== id);
}

async function route() {
  const m = location.hash.match(/^#\/p\/([a-z0-9-]+)/);
  if (m) return openProblem(m[1]);
  state.problem = null;
  $("problemSelect").value = "";
  showView("viewNew");
  $("newDesc").focus();
}

window.addEventListener("hashchange", route);
document.addEventListener("DOMContentLoaded", async () => {
  initEditor();
  initSplitters();
  $("genBtn").addEventListener("click", generate);
  $("runBtn").addEventListener("click", () => run("examples"));
  $("submitBtn").addEventListener("click", () => run("all"));
  $("resetBtn").addEventListener("click", () => {
    if (state.problem && confirm("לאפס את הקוד לשלד ההתחלתי? הקוד הנוכחי יימחק.")) state.editor.set(state.problem.stub);
  });
  document.querySelectorAll(".desc-panel .tab").forEach((t) => t.addEventListener("click", () => setTab(t.dataset.tab)));
  $("subsBody").addEventListener("click", (e) => {
    const load = e.target.closest("[data-load]");
    if (load) return loadSubmission(load.dataset.load);
    const head = e.target.closest(".sub-head");
    if (head) toggleSubmission(head.dataset.id);
  });
  $("saveSubBtn").addEventListener("click", openSaveDialog);
  $("saveDialog").addEventListener("close", () => {
    if ($("saveDialog").returnValue === "save") saveSubmission();
    $("saveDialog").returnValue = "";
  });
  document.addEventListener("keydown", (e) => {
    // e.code is the physical key, so this also works with a Hebrew keyboard layout.
    if ((e.ctrlKey || e.metaKey) && (e.code === "KeyS" || e.key.toLowerCase() === "s")) {
      e.preventDefault(); // never trigger the browser's "save page" dialog
      if (state.problem && !$("saveDialog").open) openSaveDialog();
    }
  });
  $("problemSelect").addEventListener("change", (e) => { location.hash = e.target.value ? `#/p/${e.target.value}` : "#/new"; });
  await loadList();
  route();
});
