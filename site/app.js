// Renders the page from data/*.json (built by site/build_data.py).
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const getJSON = (f) => fetch(`data/${f}.json`).then((r) => r.json());

const MATH = { delimiters: [
  { left: "\\[", right: "\\]", display: true },
  { left: "\\(", right: "\\)", display: false },
  { left: "$$", right: "$$", display: true },
], throwOnError: false };

function renderMath(el) {
  if (window.renderMathInElement) renderMathInElement(el, MATH);
}

function plain(text) {
  return text.replace(/\*\*(.+?)\*\*/g, "$1"); // drop markdown bold markers; keep everything else verbatim
}

function chartDefaults() {
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.color = css("--muted");
  Chart.defaults.borderColor = css("--grid");
  Chart.defaults.animation = false;
  Chart.defaults.maintainAspectRatio = false;
}

// ---- headline ----
function headline(summary) {
  const g = summary["0.5b"].gsm8k;
  document.getElementById("h-base").textContent = `${g.base}%`;
  document.getElementById("h-trained").textContent = `${g.trained}%`;
  const p = g.p < 0.001 ? "p < 0.001" : `p = ${g.p.toFixed(3)}`;
  document.getElementById("h-paired").textContent = `${g.fixed} problems fixed, ${g.broken} broken, paired sign test ${p}.`;
}

// ---- explorer ----
function explorer(items) {
  const select = document.getElementById("ex-select");
  items.forEach((it, i) => {
    const o = document.createElement("option");
    const words = it.question.split(/\s+/).slice(0, 9).join(" ");
    o.value = i;
    o.textContent = `${it.kind === "fixed" ? "Fixed" : "Broken"} · ${words}…`;
    select.appendChild(o);
  });
  const side = (el, label, s) => {
    el.className = `answer ${s.correct ? "right" : "wrong"}`;
    el.innerHTML = "";
    const h = document.createElement("header");
    h.innerHTML = `<span></span><span></span>`;
    h.children[0].textContent = label;
    h.children[1].textContent = `${s.correct ? "✓ right" : "✗ wrong"}: ${s.answer ?? "no answer"}`;
    const body = document.createElement("div");
    body.className = "body";
    body.textContent = plain(s.response);
    el.append(h, body);
    renderMath(body);
  };
  const show = (i) => {
    const it = items[i];
    const q = document.getElementById("ex-question");
    q.textContent = it.question;
    const gold = document.createElement("span");
    gold.className = "gold";
    gold.textContent = `Correct answer: ${it.gold} · ${it.id}`;
    q.appendChild(gold);
    side(document.getElementById("ex-base"), "Base model", it.base);
    side(document.getElementById("ex-grpo"), "After GRPO", it.grpo);
  };
  select.addEventListener("change", () => show(select.value));
  show(0);
}

// ---- method formulas ----
function formulas() {
  if (!window.katex) return;
  katex.render(String.raw`A_i = \frac{R_i - \operatorname{mean}(R_1,\dots,R_G)}{\operatorname{std}(R_1,\dots,R_G)}`,
    document.getElementById("f-adv"), { displayMode: true, throwOnError: false });
  katex.render(String.raw`J(\theta) = \frac{1}{G}\sum_{i=1}^{G}\frac{1}{|o_i|}\sum_{t=1}^{|o_i|}\min\!\big(r_{i,t}A_i,\ \operatorname{clip}(r_{i,t},1-\epsilon,1+\epsilon)A_i\big) - \beta\,D_{KL}(\pi_\theta \,\|\, \pi_{ref})`,
    document.getElementById("f-obj"), { displayMode: true, throwOnError: false });
}

// ---- training dynamics ----
const RUNS = [
  { key: "grpo-0.5b", label: "0.5B, lr 1e-5", note: "The headline run: steady improvement, small KL, no collapse in 250 steps." },
  { key: "grpo-0.5b-lr3e-5", label: "0.5B, lr 3e-5", note: "Three times the learning rate: faster at first, then KL and garbage answers climb after step ~150 while greedy validation barely moves." },
  { key: "grpo-1.5b", label: "1.5B, lr 1e-5", note: "500 steps over two sessions. Validation peaks at step 350; the collapse starts around step 330. Test accuracy did not improve." },
];

function dynamics(training) {
  const charts = {};
  const line = (id, yFmt) => new Chart(document.getElementById(id), {
    type: "line",
    data: { labels: [], datasets: [{ data: [], borderColor: css("--c1"), backgroundColor: css("--c1"), pointRadius: 0, borderWidth: 2, tension: 0.25, spanGaps: true }] },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => yFmt(c.parsed.y) } } },
      scales: { x: { type: "linear", title: { display: true, text: "step" } }, y: { ticks: { callback: yFmt } } },
    },
  });
  charts.reward = line("c-reward", (v) => v.toFixed(2));
  charts.val = line("c-val", (v) => `${Math.round(v * 10) / 10}%`);
  charts.kl = line("c-kl", (v) => v.toFixed(3));
  charts.garbage = line("c-garbage", (v) => `${(100 * v).toFixed(0)}%`);
  charts.val.data.datasets[0].pointRadius = 3;

  const tabs = document.getElementById("run-tabs");
  const select = (run) => {
    const d = training[run.key];
    const xy = (xs, ys) => xs.map((x, i) => ({ x, y: ys[i] }));
    charts.reward.data.datasets[0].data = xy(d.step, d.reward);
    charts.val.data.datasets[0].data = xy(d.val_step, d.val);
    charts.kl.data.datasets[0].data = xy(d.step, d.kl);
    charts.garbage.data.datasets[0].data = xy(d.step, d.garbage_rate.map((v) => v ?? 0));
    Object.values(charts).forEach((c) => c.update());
    document.getElementById("run-note").textContent = run.note;
    [...tabs.children].forEach((b) => b.setAttribute("aria-selected", b.dataset.key === run.key));
  };
  RUNS.forEach((run) => {
    const b = document.createElement("button");
    b.type = "button";
    b.role = "tab";
    b.dataset.key = run.key;
    b.textContent = run.label;
    b.addEventListener("click", () => select(run));
    tabs.appendChild(b);
  });
  select(RUNS[0]);
}

// ---- ablations ----
function ablations(abl) {
  const runs = abl.runs;
  const colors = runs.map((r) => r.run === "grpo-0.5b" ? css("--text") : r.run.includes("lr3e-5") ? css("--wrong") : css("--c2"));
  new Chart(document.getElementById("c-abl"), {
    type: "bar",
    data: {
      labels: runs.map((r) => r.label),
      datasets: [{ data: runs.map((r) => r.test), backgroundColor: colors, borderRadius: 4 }],
    },
    options: {
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        title: { display: true, text: `GSM8K test accuracy at step 250 (base model ${abl.base_test}%, dashed)` },
        tooltip: { callbacks: { label: (c) => {
          const r = runs[c.dataIndex];
          return `${r.test}% · vs base +${r.fixed}/−${r.broken} (p = ${r.p.toFixed(3)})`;
        } } },
      },
      scales: { x: { min: 45, max: 56, ticks: { callback: (v) => `${v}%` } } },
    },
    plugins: [{
      id: "baseLine",
      afterDraw(chart) {
        const x = chart.scales.x.getPixelForValue(abl.base_test);
        const { top, bottom } = chart.chartArea;
        const g = chart.ctx;
        g.save();
        g.strokeStyle = css("--muted");
        g.setLineDash([5, 4]);
        g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke();
        g.restore();
      },
    }],
  });
}

// ---- gallery ----
function gallery(items) {
  const root = document.getElementById("gallery-items");
  items.forEach((it, i) => {
    const d = document.createElement("details");
    d.className = "card";
    if (i === 0) d.open = true;
    const s = document.createElement("summary");
    s.innerHTML = "<h3></h3><span class='meta'></span>";
    s.querySelector("h3").textContent = it.title;
    s.querySelector(".meta").textContent = `${it.run} · correct answer ${it.gold}`;
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = it.note;
    const pre = document.createElement("pre");
    pre.textContent = plain(it.response);
    d.append(s, note, pre);
    root.appendChild(d);
  });
}

Promise.all(["summary", "explorer", "training", "ablations", "gallery"].map(getJSON)).then(([summary, ex, training, abl, gal]) => {
  chartDefaults();
  headline(summary);
  explorer(ex);
  formulas();
  dynamics(training);
  ablations(abl);
  gallery(gal);
}).catch((e) => {
  console.error(e);
  document.querySelector("main").insertAdjacentHTML("afterbegin", "<p class='muted'>Could not load the result data.</p>");
});
