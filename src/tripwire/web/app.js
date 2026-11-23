// Tripwire dashboard. Plain ES module, no framework.
// Model output is untrusted (it comes from a system under attack), so every string from the
// API is inserted with textContent / text nodes, never as HTML.

const CATEGORY = {
  direct_injection: "Direct prompt injection",
  indirect_injection: "Instructions hidden in documents",
  leakage: "Confidential data leakage",
  numeric_poisoning: "False figures",
};
const DEFENSE = {
  none: "No defense",
  hardened_prompt: "Hardened prompt",
  isolation: "Isolated context",
  layered: "Layered filters",
};
const OUTCOME = {
  succeeded: "The attack got through",
  resisted: "The system resisted",
  mixed: "Undecided: the false figure and the right one both appear",
  not_delivered: "Not delivered: the planted document was never retrieved",
};

const $ = (sel) => document.querySelector(sel);
const label = (map, key) => map[key] ?? key;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

const pct = (s, d) => (d ? Math.round((100 * s) / d) : null);

// ---------- state in the URL, so any view can be linked ----------
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  return {
    run: p.get("run") ? Number(p.get("run")) : null,
    category: p.get("category"),
    defense: p.get("defense"),
    attack: p.get("attack"),
    repeat: p.get("repeat") ? Number(p.get("repeat")) : 0,
  };
}

function writeHash(state) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) if (v !== null && v !== undefined) p.set(k, v);
  history.replaceState(null, "", `#${p}`);
}

let state = readHash();
let matrixData = null;

// ---------- runs ----------
async function loadRuns() {
  const runs = await api("/api/runs");
  const select = $("#run");
  select.replaceChildren(...runs.map((r) =>
    el("option", { value: r.id }, `Run ${r.id}, ${r.started_at.slice(0, 10)}, ${r.catalog}`)));
  if (!runs.length) {
    $("#headline").textContent = "No runs yet. Start one with: uv run tripwire matrix";
    return;
  }
  if (!runs.some((r) => r.id === state.run)) state.run = runs[0].id;
  select.value = state.run;
  select.addEventListener("change", () => {
    state = { run: Number(select.value) };
    writeHash(state);
    render();
  });
  await render();
}

async function render() {
  matrixData = await api(`/api/runs/${state.run}/matrix`);
  renderMeta(matrixData);
  renderHeadline(matrixData);
  renderMatrix(matrixData);
  if (state.category && state.defense) await openCell(state.category, state.defense, false);
  else $("#detail").hidden = true;
}

function renderMeta({ run, judge_model }) {
  const rows = [
    ["Model", run.model],
    ["Retrieved per question", run.k],
    ["Runs per attack", run.repeats],
    ["Attack catalog", run.catalog],
    ["Code version", run.git_commit ?? "unknown"],
    ["Undecided cases judged by", judge_model ?? "not judged"],
  ];
  $("#run-meta").replaceChildren(...rows.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
}

function renderHeadline({ defenses, totals }) {
  const first = defenses[0];
  const last = defenses[defenses.length - 1];
  const a = totals[first];
  const b = totals[last];
  const h = $("#headline");
  if (!a || !a.delivered) {
    h.textContent = "This run has no attack results.";
    return;
  }
  const parts = [el("span", {}, `${a.succeeded} of ${a.delivered} attacks got through with `,
    `${label(DEFENSE, first).toLowerCase()}.`)];
  if (last !== first && b && b.delivered) {
    parts.push(" ", el("span", { class: "quiet" },
      `${b.succeeded} of ${b.delivered} with ${label(DEFENSE, last).toLowerCase()}.`));
  }
  h.replaceChildren(...parts);
}

function renderMatrix({ defenses, categories, cells, totals, gold }) {
  const grid = $("#matrix");
  grid.style.setProperty("--cols", defenses.length);
  const byKey = new Map(cells.map((c) => [`${c.category}|${c.defense}`, c]));
  const nodes = [el("div", { role: "columnheader" })];
  for (const d of defenses) nodes.push(el("div", { class: "colhead", role: "columnheader" }, label(DEFENSE, d)));

  for (const cat of categories) {
    nodes.push(el("div", { class: "rowhead", role: "rowheader" }, label(CATEGORY, cat)));
    for (const d of defenses) {
      const c = byKey.get(`${cat}|${d}`);
      const rate = c ? pct(c.succeeded, c.delivered) : null;
      if (rate === null) {
        nodes.push(el("div", { class: "cell empty", role: "cell" }, "no data"));
        continue;
      }
      const pressed = state.category === cat && state.defense === d;
      nodes.push(el("button", {
        class: `cell${rate >= 55 ? " strong" : ""}`,
        role: "cell",
        style: `--rate:${rate / 100}`,
        "aria-pressed": pressed ? "true" : "false",
        "aria-label": `${label(CATEGORY, cat)}, ${label(DEFENSE, d)}: ${c.succeeded} of ${c.delivered} got through`,
        onclick: () => openCell(cat, d, true),
      },
      el("span", { class: "rate" }, `${rate}%`),
      el("span", { class: "count" }, `${c.succeeded} of ${c.delivered}`,
        c.mixed ? `, ${c.mixed} undecided` : "")));
    }
  }

  nodes.push(el("div", { class: "rowhead total", role: "rowheader" }, "All attacks"));
  for (const d of defenses) {
    const t = totals[d];
    const rate = t ? pct(t.succeeded, t.delivered) : null;
    nodes.push(el("div", { class: "static-cell", role: "cell" },
      rate === null ? "-" : `${rate}%`,
      t && t.delivered ? el("small", {}, `${t.succeeded} of ${t.delivered}`) : null));
  }

  if (Object.keys(gold).length) {
    nodes.push(el("div", { class: "rowhead gold", role: "rowheader" }, "Questions answered correctly"));
    for (const d of defenses) {
      const g = gold[d];
      nodes.push(el("div", { class: "static-cell", role: "cell" },
        g ? `${g.correct} of ${g.n}` : "-",
        g ? el("small", {}, `${g.wrong} wrong, ${g.blocked} blocked`) : null));
    }
    nodes.push(el("div", { class: "rowhead", role: "rowheader" }, "Answers citing a real source"));
    for (const d of defenses) {
      const g = gold[d];
      nodes.push(el("div", { class: "static-cell plain", role: "cell" },
        g ? `${g.cited} of ${g.n}` : "-"));
    }
  }
  grid.replaceChildren(...nodes);
}

// ---------- a cell: its attacks, one mark per run ----------
async function openCell(category, defense, userAction) {
  state = { run: state.run, category, defense, attack: userAction ? null : state.attack,
            repeat: userAction ? 0 : state.repeat };
  writeHash(state);
  for (const b of document.querySelectorAll(".cell[aria-pressed]")) b.setAttribute("aria-pressed", "false");
  const data = await api(`/api/runs/${state.run}/cell?category=${encodeURIComponent(category)}&defense=${encodeURIComponent(defense)}`);
  renderMatrix(matrixData);

  $("#detail").hidden = false;
  $("#cell-title").textContent = `${label(CATEGORY, category)}, ${label(DEFENSE, defense).toLowerCase()}`;
  const runs = data.attacks.flatMap((a) => a.repeats);
  const got = runs.filter((r) => r.outcome === "succeeded").length;
  $("#cell-summary").textContent = `${data.attacks.length} attacks, each run ${data.attacks[0]?.repeats.length ?? 0} times. ${got} of ${runs.length} runs got through.`;

  $("#attack-list").replaceChildren(...data.attacks.map((a) => el("li", {},
    el("div", { class: "attack-row" },
      el("span", {}, a.title),
      el("span", { class: "marks" }, a.repeats.map((r) => el("button", {
        class: "mark-btn",
        "aria-label": `${a.title}, run ${r.repeat + 1}: ${label(OUTCOME, r.outcome)}`,
        "aria-current": state.attack === a.attack_id && state.repeat === r.repeat ? "true" : null,
        onclick: () => openCase(a.attack_id, r.repeat, true),
      }, el("span", { class: `mark ${r.outcome}` }))))))));

  const first = data.attacks[0];
  if (state.attack) await openCase(state.attack, state.repeat, false);
  else if (first) await openCase(first.attack_id, first.repeats[0].repeat, false);
  if (userAction) $("#detail").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

// ---------- the case file ----------
function answerWithEvidence(text, spans) {
  const out = [];
  let i = 0;
  for (const s of spans) {
    if (s.start < i) continue;
    out.push(text.slice(i, s.start));
    out.push(el("mark", { class: "evidence", title: `found by the ${s.kind} detector` }, text.slice(s.start, s.end)));
    i = s.end;
  }
  out.push(text.slice(i));
  return out;
}

function field(name, ...content) {
  return el("dl", { class: "field" }, el("dt", {}, name), el("dd", {}, ...content));
}

function describeSpec(s) {
  if (s.type === "number") return `states the false figure ${s.value} ${s.unit}`;
  if (s.type === "canary") return `reveals the secret "${s.value}"`;
  if (s.type === "marker") return `outputs "${s.value}"`;
  if (s.type === "url") return "links to a non-official site";
  if (s.type === "regex") return `matches /${s.pattern}/`;
  return s.type;
}

async function openCase(attackId, repeat, userAction) {
  state = { ...state, attack: attackId, repeat };
  writeHash(state);
  for (const b of document.querySelectorAll(".mark-btn")) b.removeAttribute("aria-current");
  const c = await api(`/api/runs/${state.run}/case?defense=${encodeURIComponent(state.defense)}&attack_id=${encodeURIComponent(attackId)}&repeat=${repeat}`);
  const box = $("#case");
  box.hidden = false;
  if (!c.attack) {
    box.replaceChildren(el("p", { class: "empty-state" }, `Attack ${attackId} is not in the loaded catalog.`));
    return;
  }
  const a = c.attack;
  const dropped = new Set(c.dropped.map((d) => d.replace(/^.*?: /, "").replace(" p.", ":p")));

  const filters = [];
  if (c.blocked_by) filters.push(el("p", {}, `Stopped by the ${c.blocked_by.split(":")[0]} filter (${c.blocked_by.split(": ").slice(1).join(": ")}).`));
  for (const d of c.dropped) filters.push(el("p", {}, `Removed before the model saw it: ${d}.`));
  if (!filters.length) filters.push(el("p", {}, "No filter acted."));

  const judged = c.judgements.length
    ? c.judgements.map((j) => el("p", {}, `${j.judge_model}, ${j.purpose}: ${j.verdict}. ${j.reason}`))
    : [el("p", {}, "Not needed: the detectors decided this case.")];

  box.replaceChildren(
    el("header", { class: "case-head" },
      el("p", { class: "note" }, `${label(CATEGORY, a.category)}, ${label(DEFENSE, c.defense).toLowerCase()}, run ${c.repeat + 1} (seed ${c.seed})`),
      el("h3", {}, a.title),
      el("p", { class: `verdict ${c.final_outcome}` }, label(OUTCOME, c.final_outcome))),
    field("Question", el("p", { class: "prose" }, a.question)),
    a.planted.length ? field("Planted document",
      a.planted.map((p) => el("div", { class: "planted" },
        el("p", { class: "note" }, `${p.doc_id}, page ${p.page}`),
        el("p", { class: "prose" }, p.text)))) : null,
    field("Retrieved", el("ul", { class: "source-list" }, c.retrieved.length
      ? c.retrieved.map((r) => {
          const key = r.replace(" [planted]", "");
          return el("li", { class: [r.includes("[planted]") ? "is-planted" : "", dropped.has(key) ? "is-dropped" : ""].join(" ").trim() || null },
            key.replace(":p", ", page "), r.includes("[planted]") ? " (planted)" : "", dropped.has(key) ? " (removed by filter)" : "");
        })
      : [el("li", {}, "Nothing: the question was stopped before retrieval.")])),
    field("Answer", el("p", { class: "prose" }, answerWithEvidence(c.answer, c.evidence))),
    field("Evidence", el("div", { class: "facts" },
      el("p", {}, "Counts as success if the answer ", a.success.map(describeSpec).join(", or "), "."),
      el("p", {}, c.fired.length ? `Detectors that fired: ${c.fired.join(", ")}.` : "No detector fired."),
      c.gold ? el("p", {}, `Correct figure: ${c.gold.answer}. The answer was graded ${c.gold.grade}.`) : null)),
    field("Filters", el("div", { class: "facts" }, filters)),
    field("Judge", el("div", { class: "facts" }, judged)),
  );
  for (const b of document.querySelectorAll(".mark-btn")) {
    if (b.getAttribute("aria-label")?.startsWith(`${a.title}, run ${repeat + 1}:`)) b.setAttribute("aria-current", "true");
  }
  if (userAction) box.focus({ preventScroll: true });
}

loadRuns().catch((err) => {
  $("#headline").textContent = `Could not load results: ${err.message}. Is the server running with a results database?`;
});
