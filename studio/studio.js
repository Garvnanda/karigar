// Karigar Studio. The customer only taps choices (weights are the one thing typed); the order
// sentence is written by the service from those choices. Every number shown comes from /shop.
(() => {
  "use strict";
  const app = document.getElementById("app");
  const $ = (s, el = document) => el.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const inr = n => (typeof n === "number" ? "₹" + Math.round(n).toLocaleString("en-IN") : "—");
  const grams = n => (typeof n === "number" ? n.toFixed(2) + " g" : "—");
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const ICON = {
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>',
    spin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.2-8.6"/></svg>',
    dot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="12" r="4"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>',
    mark: '<svg class="mark" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.25" aria-hidden="true"><path d="M24 8 10 20l14 20 14-20L24 8Z"/><path d="M10 20h28M19 20l5 20 5-20M19 20l5-12 5 12"/></svg>',
    flower: '<svg class="mark" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.25" aria-hidden="true"><circle cx="24" cy="24" r="4"/><path d="M24 20c-3-6-3-10 0-12 3 2 3 6 0 12ZM28 24c6-3 10-3 12 0-2 3-6 3-12 0ZM24 28c3 6 3 10 0 12-3-2-3-6 0-12ZM20 24c-6 3-10 3-12 0 2-3 6-3 12 0Z"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
  };
  const PIECE = {
    ring: { name: "Ring", pic: "ring_halo_solitaire" }, bangle: { name: "Bangle or kada", pic: "bangle_temple_kada" },
    pendant: { name: "Pendant", pic: "pendant_temple_lotus" }, chain: { name: "Chain", pic: "chain_rope" },
    earring: { name: "Earrings (pair)", pic: "earring_jhumka" }, nosepin: { name: "Nose pin", pic: "nosepin_flower" },
    coin: { name: "Gold coin", pic: "coin_lotus_10g" },
  };
  const DEFAULT_FAMILY = { ring: "ring_floral_cluster", bangle: "bangle_temple_kada", pendant: "pendant_heart_halo", chain: "chain_rope",
    earring: "earring_jhumka", nosepin: "nosepin_flower", coin: "coin_lotus_10g" };
  const STAGE = { intake: "Reading your choices", plan: "Working out the gold", design: "Drawing three designs",
    solve: "Solving each design to the gram", solved: "Weights and price ready", deliver: "Rendering photos and 3D models", done: "Ready" };
  const STAGE_ORDER = Object.keys(STAGE);
  let OPT = null, CAT = {};

  async function api(path, body) {
    const r = await fetch("/shop/" + path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data?.error?.message || "Something went wrong (" + r.status + "). Try again.");
    return data;
  }
  async function options() {
    if (!OPT) {
      OPT = await api("options");
      try { (await (await fetch("catalogue.json")).json()).families.forEach(f => { CAT[f.family] = f; }); } catch {}
    }
    return OPT;
  }
  const codes = () => store.get("karigar.codes", []);
  function remember(code) { const c = codes().filter(x => x !== code); c.unshift(code); store.set("karigar.codes", c.slice(0, 50)); count(); }
  function count() { const n = codes().length; $("#order-count").textContent = n ? String(n) : ""; }

  // ------------------------------------------------------------- ornament (the deck's mandala, drawn as geometry)
  const MANDALA = (() => {
    const c = 200, out = [];
    const ring = r => out.push(`<circle cx="${c}" cy="${c}" r="${r}"/>`);
    [196, 188, 150, 112, 70, 36, 14].forEach(ring);
    const petals = (n, r0, r1, w, rot = 0) => { for (let k = 0; k < n; k++) {
      const a = (k / n) * 2 * Math.PI + rot, b = w / r1;
      const p = (rr, aa) => `${(c + rr * Math.cos(aa)).toFixed(1)} ${(c + rr * Math.sin(aa)).toFixed(1)}`;
      out.push(`<path d="M${p(r0, a - b)} Q${p(r1, a - b * 1.4)} ${p(r1 + 8, a)} Q${p(r1, a + b * 1.4)} ${p(r0, a + b)}"/>`); } };
    petals(16, 36, 66, 12); petals(16, 70, 106, 16, Math.PI / 16); petals(32, 112, 146, 10); petals(48, 150, 184, 6, Math.PI / 48);
    for (let k = 0; k < 64; k++) { const a = (k / 64) * 2 * Math.PI;
      out.push(`<circle cx="${(c + 192 * Math.cos(a)).toFixed(1)}" cy="${(c + 192 * Math.sin(a)).toFixed(1)}" r="1.6" fill="currentColor"/>`); }
    return `<svg class="mandala" viewBox="0 0 400 400" fill="none" stroke="currentColor" stroke-width="0.8" aria-hidden="true">${out.join("")}</svg>`;
  })();
  const ARCHES = (() => {
    const w = 64, n = 30, out = [];
    for (let k = 0; k < n; k++) { const x = k * w;
      out.push(`<path d="M${x + 6} 56V30Q${x + 6} 8 ${x + 32} 4Q${x + 58} 8 ${x + 58} 30V56"/>`); }
    return `<svg class="arches" viewBox="0 0 ${w * n} 56" preserveAspectRatio="xMidYMax slice" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true">${out.join("")}</svg>`;
  })();

  // ------------------------------------------------------------- the tray
  function tray({ family, model, picture, name, fact, metal }) {
    const fam = CAT[family] || {};
    const src = model || fam.model, pic = picture || fam.picture;
    const media = src
      ? `<model-viewer src="${esc(src)}" ${pic ? `poster="${esc(pic)}"` : ""} camera-controls auto-rotate rotation-per-second="18deg" camera-orbit="0deg 72deg 135%" min-camera-orbit="auto auto 90%" max-camera-orbit="auto auto 220%" interaction-prompt="none" shadow-intensity="0" exposure="1.15" environment-image="neutral" alt="${esc(name || fam.title || "Design")} in 3D; drag to turn it"></model-viewer>`
      : pic ? `<img class="still" src="${esc(pic)}" alt="${esc(name || fam.title || "Design")}">` : "";
    return `<div class="tray">${MANDALA}${media}<div class="tray-caption"><div><div class="name">${esc(name || fam.title || "")}</div>
      <div class="tray-hint">${src ? "Drag to turn" : ""}</div></div><div class="fact">${fact || ""}</div></div></div>`;
  }
  function tint(metal) {
    const mv = $(".tray model-viewer"); const rgb = OPT?.metal_tint?.[metal];
    if (!mv || !rgb) return;
    const apply = () => (mv.model?.materials || []).forEach(m => { if (/^gold/.test(m.name)) m.pbrMetallicRoughness.setBaseColorFactor([...rgb, 1]); });
    mv.model ? apply() : mv.addEventListener("load", apply, { once: true });
  }

  // ------------------------------------------------------------- intro
  async function intro() {
    await options().catch(() => {});
    const f = CAT.ring_halo_solitaire || {};
    const w = f.weights_g ? `${grams(f.weights_g.balanced)} of 22K, measured on the model` : "";
    app.innerHTML = `<section class="room intro">${tray({ family: "ring_halo_solitaire", fact: w })}
      <div class="slip"><p class="hindi" lang="hi">कारीगर</p><h1>A new piece, solved to your gold.</h1>
        <p class="lead">Tap a few choices. Get three castable designs, priced line by line.</p>
        <p class="actions"><a class="btn btn--gold" href="#/design">Create your design</a>${codes().length ? '<a class="btn btn--quiet" href="#/orders">My orders</a>' : ""}</p>
        <dl class="ledger"><div><dt>Bring old gold</dt><dd>We design to its exact weight</dd></div>
          <div><dt>Every price line</dt><dd>Shows where its number came from</dd></div>
          <div><dt>19 designs</dt><dd>Rings to jhumkas, in 3D</dd></div></dl>
        <ul class="pills" aria-label="What you get"><li>3 designs</li><li>Castable STL</li><li>Job card</li><li>Quote with old-gold credit</li></ul></div></section>`;
  }

  // ------------------------------------------------------------- the form
  const draft = () => store.get("karigar.draft", { metal: "yellow", karat: 22, gem: "none", target: { kind: "weight" } });
  const saveDraft = f => store.set("karigar.draft", f);
  const STEPS = ["piece", "style", "karat", "metal", "stone", "size", "gold", "review"];
  const needsSize = p => ["ring", "bangle", "chain"].includes(p);

  function radios(name, items, value, cls = "chips") {
    return `<fieldset class="choices ${cls}"><legend class="visually-hidden">${esc(name)}</legend>${items.map((it, i) => {
      const id = `${name}-${i}`;
      return `<input type="radio" name="${esc(name)}" id="${id}" value="${esc(it.value)}" ${String(it.value) === String(value ?? "") ? "checked" : ""}>
        <label class="choice" for="${id}">${it.html}</label>`; }).join("")}</fieldset>`;
  }

  function stepBody(step, f) {
    const o = OPT;
    if (step === "piece") return { h: "What shall we make?", help: "Each one is a design our karigar can cast.",
      body: radios("piece", o.pieces.map(p => ({ value: p, html: `<span class="pic"><img src="${esc(CAT[PIECE[p].pic]?.picture || "")}" alt="" loading="lazy"></span><span class="name">${esc(PIECE[p].name)}</span>` })), f.piece, "tiles") };
    if (step === "style") return { h: "Pick a style.", help: "Weights shown are for the balanced version in 22K.",
      body: radios("style", o.styles[f.piece].map(s => {
        const fam = CAT[s.id] || {};
        const pic = !s.id || s.id === "floral" ? "" : fam.picture;
        const title = s.id === "floral" ? "Classic floral" : s.id ? s.title : "Karigar's pick";
        const sub = s.id && s.id !== "floral" && fam.weights_g ? `${grams(fam.weights_g.balanced)}` : s.id ? "" : "Our choice for your gold";
        return { value: s.id, html: `<span class="pic ${pic ? "" : "pic--mark"}">${pic ? `<img src="${esc(pic)}" alt="" loading="lazy">` : s.id === "floral" ? ICON.flower : ICON.mark}</span><span class="name">${esc(title)}</span><span class="sub">${esc(sub)}</span>` };
      }), f.style ?? "", "tiles") };
    if (step === "karat") return { h: "Which gold?", help: "Higher karat is purer gold and a softer metal.",
      body: radios("karat", o.karats.map(k => ({ value: k, html: `<strong>${k}K</strong><span class="sub">${{ 22: "916", 18: "750", 14: "585" }[k]} purity</span>` })), f.karat, "rows") };
    if (step === "metal") return { h: "Which colour of gold?", help: "",
      body: radios("metal", o.metals.map(m => ({ value: m, html: `<span class="swatch swatch--${m}"></span><span>${m[0].toUpperCase() + m.slice(1)} gold</span>` })), f.metal, "rows") };
    if (step === "stone") return { h: "A stone?", help: "Leave the size to us and the design's own stone is used.",
      body: radios("gem", o.gems.map(g => ({ value: g, html: `<span class="swatch swatch--${g}"></span><span>${g === "none" ? "No stone" : g[0].toUpperCase() + g.slice(1)}</span>` })), f.gem, "rows")
        + (f.gem && f.gem !== "none" ? `<div><p class="help">Stone size</p>${radios("stone_ct", [{ value: "", html: "Design's own" }, ...o.stone_ct.map(c => ({ value: c, html: `${c} ct` }))], f.stone_ct ?? "")}</div>` : "") };
    if (step === "size") {
      if (f.piece === "ring") return { h: "Ring size?", help: "Indian sizes. Not sure? Size 12 to 14 fits most women.", body: radios("size", o.ring_sizes.map(n => ({ value: n, html: String(n) })), f.size) };
      if (f.piece === "bangle") return { h: "Bangle size?", help: "Measured inside, in the 2-N system.", body: radios("size", o.bangle_sizes.map(n => ({ value: n, html: n })), f.size) };
      return { h: "Chain length?", help: "Including the clasp.", body: radios("size", o.chain_in.map(n => ({ value: n, html: `${n} in` })), f.size) };
    }
    if (step === "gold") {
      const t = f.target || {};
      const kinds = radios("kind", [
        { value: "exchange", html: "<strong>I'll bring old gold</strong><span class=\"sub\">Designed to use all of it</span>" },
        { value: "weight", html: "<strong>A weight I want</strong><span class=\"sub\">Finished weight in grams</span>" },
        { value: "budget", html: "<strong>A budget</strong><span class=\"sub\">Everything included</span>" }], t.kind, "rows");
      let more = "";
      if (t.kind === "weight" || t.kind === "exchange") more += `<div class="field"><label for="grams">${t.kind === "exchange" ? "Weight of your old gold" : "Finished weight"}</label>
        <div class="unit"><input id="grams" inputmode="decimal" type="number" min="0.1" max="${o.max_grams}" step="0.01" value="${esc(t.grams ?? "")}" placeholder="0.00"><span>g</span></div></div>`;
      if (t.kind === "exchange") more += `<div><p class="help">Purity of the old gold</p>${radios("oldkarat", o.old_karats.map(k => ({ value: k, html: `${k}K` })), t.karat)}</div>`;
      if (t.kind === "budget") more += radios("inr", o.budgets.map(b => ({ value: b, html: inr(b) })), t.inr);
      return { h: "How much gold?", help: "", body: kinds + more + '<p class="err" id="gold-err" hidden></p>' };
    }
    const rows = [["Piece", PIECE[f.piece]?.name, "piece"], ["Style", styleTitle(f), "style"], ["Gold", `${f.karat}K ${f.metal}`, "karat"],
      ["Stone", f.gem === "none" ? "None" : `${f.gem}${f.stone_ct ? ", " + f.stone_ct + " ct" : ""}`, "stone"]];
    if (needsSize(f.piece)) rows.push(["Size", f.piece === "chain" ? `${f.size} in` : String(f.size), "size"]);
    rows.push(["Gold amount", targetText(f.target), "gold"]);
    return { h: "Ready to design.", help: "Karigar draws three versions and solves each to your gold.",
      body: `<dl class="summary">${rows.map(([k, v, s]) => `<dt>${k}</dt><dd>${esc(v)}<button type="button" data-goto="${s}">Change</button></dd>`).join("")}</dl>` };
  }
  const styleTitle = f => { const s = (OPT.styles[f.piece] || []).find(x => x.id === (f.style || "")); return !s ? "" : s.id === "floral" ? "Classic floral" : s.id ? s.title : "Karigar's pick"; };
  const targetText = t => !t ? "" : t.kind === "weight" ? `${t.grams} g finished` : t.kind === "budget" ? `${inr(t.inr)} all in` : t.kind === "exchange" ? `Old gold, ${t.grams} g of ${t.karat}K` : "";

  function stepValid(step, f) {
    if (step === "piece") return !!f.piece;
    if (step === "style") return true;                     // no choice = Karigar's pick
    if (step === "karat") return !!f.karat;
    if (step === "metal") return !!f.metal;
    if (step === "stone") return !!f.gem;
    if (step === "size") return !needsSize(f.piece) || f.size != null;
    if (step === "gold") { const t = f.target || {}; const g = Number(t.grams);
      return t.kind === "budget" ? !!t.inr : (g > 0 && g <= OPT.max_grams && (t.kind === "weight" || !!t.karat)); }
    return true;
  }

  async function design(stepName) {
    try { await options(); } catch (e) { app.innerHTML = `<section class="slip"><p class="err">${esc(e.message)}</p></section>`; return; }
    const f = draft();
    const steps = STEPS.filter(s => s !== "size" || needsSize(f.piece));
    let i = Math.max(0, steps.indexOf(stepName));
    while (i > 0 && !stepValid(steps[i - 1], f)) i--;            // never skip an unanswered question
    const step = steps[i], q = stepBody(step, f);
    const fam = f.style && f.style !== "floral" ? f.style : f.piece ? DEFAULT_FAMILY[f.piece] : "ring_halo_solitaire";
    const famInfo = CAT[fam] || {};
    app.innerHTML = `<section class="room room--form">${tray({ family: fam, name: famInfo.title, fact: f.karat ? `${f.karat}K ${f.metal || ""} gold` : "" })}
      <form class="slip q" id="q" novalidate>
        <div class="progress"><span>Step ${i + 1} of ${steps.length}</span><ol>${steps.map((_, k) => `<li class="${k < i ? "done" : k === i ? "now" : ""}"></li>`).join("")}</ol></div>
        <div><h2>${esc(q.h)}</h2>${q.help ? `<p class="help">${esc(q.help)}</p>` : ""}</div>
        ${q.body}
        <div class="stepnav">${i > 0 ? `<a class="btn btn--quiet" href="#/design/${steps[i - 1]}">${ICON.back}Back</a>` : "<span></span>"}
          ${step === "review" ? '<button class="btn btn--gold" type="submit" id="go">Make my designs</button>' : `<button class="btn btn--gold" type="submit" id="next">Next</button>`}</div>
        <p class="err" id="form-err" hidden></p>
      </form></section>`;
    tint(f.metal);
    const form = $("#q");
    const next = $("#next");
    const sync = () => { if (next) next.disabled = !stepValid(step, draft()); };
    form.addEventListener("change", ev => {
      const t = ev.target, d = draft();
      if (t.name === "piece") { d.piece = t.value; delete d.style; delete d.size; }
      if (t.name === "style") d.style = t.value;
      if (t.name === "karat") d.karat = Number(t.value);
      if (t.name === "metal") { d.metal = t.value; tint(t.value); }
      if (t.name === "gem") { d.gem = t.value; if (t.value === "none") delete d.stone_ct; }
      if (t.name === "stone_ct") d.stone_ct = t.value ? Number(t.value) : null;
      if (t.name === "size") d.size = d.piece === "bangle" ? t.value : Number(t.value);
      if (t.name === "kind") d.target = { kind: t.value, grams: d.target?.grams };
      if (t.name === "oldkarat") d.target = { ...d.target, karat: Number(t.value) };
      if (t.name === "inr") d.target = { ...d.target, inr: Number(t.value) };
      saveDraft(d);
      if (["piece", "style", "gem", "kind"].includes(t.name)) design(step); else sync();
    });
    form.addEventListener("input", ev => {
      if (ev.target.id !== "grams") return;
      const d = draft(); d.target = { ...d.target, grams: ev.target.value === "" ? undefined : Number(ev.target.value) }; saveDraft(d);
      const bad = ev.target.value !== "" && !(Number(ev.target.value) > 0 && Number(ev.target.value) <= OPT.max_grams);
      ev.target.setAttribute("aria-invalid", String(bad));
      const e = $("#gold-err"); e.hidden = !bad; e.textContent = bad ? `Enter a weight between 0.01 and ${OPT.max_grams} g.` : "";
      sync();
    });
    form.addEventListener("click", ev => { const g = ev.target.closest("[data-goto]"); if (g) location.hash = "#/design/" + g.dataset.goto; });
    form.addEventListener("submit", async ev => {
      ev.preventDefault();
      if (step !== "review") { if (stepValid(step, draft())) location.hash = "#/design/" + steps[i + 1]; return; }
      const go = $("#go"); go.disabled = true; go.setAttribute("aria-busy", "true"); go.textContent = "Sending to the workshop…";
      try {
        const d = draft(), body = { ...d, style: d.style || "" };
        if (body.gem === "none") delete body.stone_ct;
        const r = await api("designs", { form: body });
        remember(r.code); location.hash = "#/o/" + r.code;
      } catch (e) { const er = $("#form-err"); er.hidden = false; er.textContent = e.message; go.disabled = false; go.removeAttribute("aria-busy"); go.textContent = "Make my designs"; }
    });
    sync();
    $("h2", form).focus?.();
  }

  // ------------------------------------------------------------- one order
  let poll = null;
  async function order(code, picked) {
    clearTimeout(poll);
    let v;
    try { v = await api("orders/" + encodeURIComponent(code)); } catch (e) {
      app.innerHTML = `<section class="slip"><h2>We couldn't open that order.</h2><p class="err">${esc(e.message)}</p><a class="btn btn--quiet" href="#/orders">My orders</a></section>`; return; }
    if (location.hash.split("/")[2] !== code) return;            // the visitor moved on
    remember(code);
    const f = v.form || {};
    const fam = f.style && f.style !== "floral" ? f.style : DEFAULT_FAMILY[f.piece] || "ring_halo_solitaire";
    const working = ["queued", "running", "solved"].includes(v.status) && v.result_status !== "needs_info";
    if (v.designs?.length && v.status !== "queued") return designsView(v, picked, working);
    let body;
    if (v.result_status === "needs_info" && v.status === "done") {
      body = `<h2>One more thing.</h2>${v.questions.map((q, n) => `<form class="q" data-topic="${esc(q.topic)}"><p>${esc(q.text)}</p>
        ${q.options.length ? radios("a" + n, q.options.map(o => ({ value: o, html: esc(o) })), null) : ""}
        <p class="actions">${q.options.length ? '<button class="btn" type="submit">Answer</button>' : ""}<a class="btn btn--quiet" href="#/design/review">Change my choices</a></p></form>`).join("")}`;
    } else if (v.result_status === "infeasible" || v.result_status === "out_of_scope") {
      const inf = v.infeasible || {};
      body = `<h2>That can't be cast as asked.</h2><p>${esc(v.explanation || inf.binding_constraint || "")}</p>
        ${inf.alternatives?.length ? `<div><p class="help">What would work</p><ul>${inf.alternatives.map(a => `<li>${esc(a)}</li>`).join("")}</ul></div>` : ""}
        <p class="actions"><a class="btn" href="#/design/gold">Change the gold</a><a class="btn btn--quiet" href="#/design/review">Change other choices</a></p>`;
    } else if (v.status === "failed") {
      body = `<h2>The workshop hit a problem.</h2><p>Your choices are saved. Send them again and we'll start over.</p><p class="actions"><a class="btn" href="#/design/review">Try again</a></p>`;
    } else {
      const at = Math.max(-1, ...v.steps.map(s => STAGE_ORDER.indexOf(s)));
      body = `<h2>Your designs are being made.</h2>
        <ol class="steps">${STAGE_ORDER.slice(0, 6).map((s, k) => `<li class="${k <= at ? "done" : k === at + 1 ? "now" : ""}">${k <= at ? ICON.check : k === at + 1 ? ICON.spin : ICON.dot}<span>${STAGE[s]}</span></li>`).join("")}</ol>
        ${v.worker_online ? '<p class="muted">Usually under a minute. You can leave; it stays in My orders.</p>' : '<p class="note">The workshop is offline right now. Your order is saved and starts as soon as it is back.</p>'}`;
    }
    app.innerHTML = `<section class="room">${tray({ family: fam, fact: `${f.karat}K ${f.metal} gold` })}<div class="slip">${body}</div></section>`;
    tint(f.metal);
    app.querySelectorAll("form[data-topic]").forEach(fm => fm.addEventListener("submit", async ev => {
      ev.preventDefault();
      const val = fm.querySelector("input:checked")?.value; if (!val) return;
      const b = fm.querySelector("button"); b.disabled = true; b.setAttribute("aria-busy", "true");
      try { await api(`orders/${code}/answer`, { topic: fm.dataset.topic, value: val }); order(code); }
      catch (e) { b.disabled = false; b.removeAttribute("aria-busy"); fm.insertAdjacentHTML("beforeend", `<p class="err">${esc(e.message)}</p>`); }
    }));
    if (working || v.status === "queued") poll = setTimeout(() => order(code), 2500);
  }

  function designsView(v, picked, working) {
    const ds = v.designs, code = v.code, paid = v.purchase;
    const cur = ds.find(d => d.version === Number(picked)) || ds.find(d => paid && d.version === paid.version) || ds[Math.floor(ds.length / 2)] || ds[0];
    const w = cur.weights || {}, q = cur.quote || {}, files = cur.files || {};
    const lines = (q.lines || []).map(l => `<tr><td>${esc(l.label)}${l.assumed ? '<span class="tag">assumed</span>' : ""}<span class="src">${esc(l.source)}</span></td><td class="amt">${inr(l.amount_inr)}</td></tr>`).join("");
    const label = d => { const t = (d.variant || "").replace(/^.*\((.*)\)$/, "$1") || d.variant || ""; return t.charAt(0).toUpperCase() + t.slice(1); };
    const n = ds.length, exch = typeof q.to_pay === "number";
    const head = paid ? "Your order." : n === 3 ? "Three designs, one gold." : n === 2 ? "Two designs for your gold." : "One design for your gold.";
    const sub = paid ? (paid.status === "reserved" ? "Reserved. Pay at the shop when you collect it." : "Paid (demo). The shop will call you when it is cast.") : n < 3 ? "The other versions could not be cast at this gold, so they are not offered." : "Each is solved to your gold and checked on its model.";
    app.innerHTML = `<section class="room">${tray({ model: files.glb, picture: files.render_hero, name: cur.variant,
        fact: `${grams(w.finished_g)}${typeof w.tolerance_g === "number" ? " ± " + w.tolerance_g.toFixed(2) + " g" : ""}` })}
      <div class="slip">
        <div><h2>${head}</h2><p class="help">${sub}</p></div>
        <fieldset class="choices designs"><legend class="visually-hidden">Designs</legend>${ds.map((d, n) => `<input type="radio" name="v" id="v${n}" value="${d.version}" ${d === cur ? "checked" : ""} ${paid && paid.version !== d.version ? "disabled" : ""}>
          <label class="choice" for="v${n}"><span class="pic">${d.files?.render_hero ? `<img src="${esc(d.files.render_hero)}" alt="">` : ""}</span><span class="name">${esc(label(d))}</span><span class="sub">${inr(d.quote?.total)}</span></label>`).join("")}</fieldset>
        <div><p class="muted">${exch ? "You pay, after your old gold" : "Total, everything included"}</p><div class="price">${inr(exch ? q.to_pay : q.total)}</div>
          <p class="weight">${grams(w.finished_g)} finished${typeof w.tolerance_g === "number" ? ` ± ${w.tolerance_g.toFixed(2)} g` : ""}</p>
          <p class="muted">Cast at ${grams(w.casting_g ?? w.modelled_g)}.${exch ? ` Design total ${inr(q.total)}, less your old gold.` : ""}</p></div>
        ${lines ? `<details><summary>See every price line</summary><table class="lines"><tbody>${lines}</tbody><tfoot><tr><td>Total</td><td class="amt">${inr(q.total)}</td></tr></tfoot></table></details>` : ""}
        ${working ? '<p class="note">Photos and 3D models are still rendering; the numbers are final.</p>' : ""}
        <p class="actions">${paid ? `<a class="btn btn--quiet" href="#/orders">My orders</a>` : `<a class="btn btn--gold" href="#/pay/${code}/${cur.version}" ${working ? 'aria-disabled="true"' : ""}>Order this design</a><a class="btn btn--quiet" href="#/design/review">Change my choices</a>`}</p>
        ${files.stl || files.job_card_md ? `<div class="files">${files.job_card_md ? `<a href="${esc(files.job_card_md)}" target="_blank" rel="noopener">Workshop job card</a>` : ""}${files.stl ? `<a href="${esc(files.stl)}">STL for casting</a>` : ""}</div>` : ""}
      </div></section>`;
    tint(null);
    app.querySelector(".designs").addEventListener("change", ev => { location.hash = `#/o/${code}/${ev.target.value}`; });
    const pay = app.querySelector('[aria-disabled="true"]'); if (pay) pay.addEventListener("click", ev => ev.preventDefault());
    if (working) poll = setTimeout(() => order(code, cur.version), 3000);
  }

  // ------------------------------------------------------------- demo checkout
  async function pay(code, version) {
    let v; try { v = await api("orders/" + code); } catch (e) { app.innerHTML = `<section class="slip"><p class="err">${esc(e.message)}</p></section>`; return; }
    const d = v.designs.find(x => x.version === Number(version));
    if (!d || v.purchase) { location.hash = `#/o/${code}`; return; }
    const q = d.quote || {}, due = typeof q.to_pay === "number" ? q.to_pay : q.total;
    app.innerHTML = `<section class="room">${tray({ model: d.files?.glb, picture: d.files?.render_hero, name: d.variant, fact: grams(d.weights?.finished_g) })}
      <form class="slip q" id="pay" novalidate>
        <div><h2>Place your order.</h2><p class="help">${esc(d.variant)}, ${grams(d.weights?.finished_g)}.</p></div>
        <p class="demo" role="note">${ICON.info}<span>Demo checkout. No money moves and no card details are asked.</span></p>
        <div class="field"><label for="name">Your name</label><input id="name" autocomplete="name" required maxlength="80"></div>
        <div class="field"><label for="phone">Phone, for the shop to call you</label><input id="phone" type="tel" autocomplete="tel" inputmode="tel" required placeholder="+91 98765 43210"></div>
        ${radios("method", [{ value: "upi", html: "<strong>UPI</strong><span class=\"sub\">Demo</span>" }, { value: "card", html: "<strong>Card</strong><span class=\"sub\">Demo</span>" },
          { value: "pay_at_store", html: "<strong>Pay at the shop</strong><span class=\"sub\">Reserve now</span>" }], "upi", "rows")}
        <table class="lines"><tbody><tr><td>Design total</td><td class="amt">${inr(q.total)}</td></tr>${typeof q.to_pay === "number" ? `<tr><td>After your old gold</td><td class="amt">${inr(q.to_pay)}</td></tr>` : ""}</tbody></table>
        <p class="err" id="pay-err" hidden></p>
        <div class="stepnav"><a class="btn btn--quiet" href="#/o/${code}/${version}">${ICON.back}Back</a><button class="btn btn--gold" type="submit" id="paybtn">Pay ${inr(due)}</button></div>
      </form></section>`;
    const form = $("#pay");
    form.addEventListener("change", () => { $("#paybtn").textContent = form.method.value === "pay_at_store" ? "Reserve this design" : `Pay ${inr(due)}`; });
    form.addEventListener("submit", async ev => {
      ev.preventDefault();
      const name = $("#name").value.trim(), phone = $("#phone").value.trim(), err = $("#pay-err");
      const bad = !name ? "Enter your name." : !/^\+?[0-9][0-9 -]{8,15}$/.test(phone) ? "Enter a phone number of 9 to 16 digits." : "";
      $("#name").setAttribute("aria-invalid", String(!name)); $("#phone").setAttribute("aria-invalid", String(!!bad && !!name));
      if (bad) { err.hidden = false; err.textContent = bad; return; }
      const b = $("#paybtn"); b.disabled = true; b.setAttribute("aria-busy", "true"); b.textContent = "Processing…";
      try {
        const r = await api(`orders/${code}/checkout`, { version: Number(version), name, phone, method: form.method.value });
        receipt(code, r.purchase, d);
      } catch (e) { err.hidden = false; err.textContent = e.message; b.disabled = false; b.removeAttribute("aria-busy"); b.textContent = `Pay ${inr(due)}`; }
    });
  }

  function receipt(code, p, d) {
    app.innerHTML = `<section class="room">${tray({ model: d.files?.glb, picture: d.files?.render_hero, name: d.variant, fact: grams(d.weights?.finished_g) })}
      <div class="slip"><div><h2>Ordered.</h2><p class="help">${p.status === "reserved" ? "Reserved. Pay at the shop when you collect it." : "Demo payment recorded."} The shop will call ${esc(p.name)}.</p></div>
        <div class="receipt"><table class="lines"><tbody><tr><td>${esc(p.variant)}</td><td class="amt">${inr(p.total_inr)}</td></tr>${p.due_inr !== p.total_inr ? `<tr><td>Paid after your old gold</td><td class="amt">${inr(p.due_inr)}</td></tr>` : ""}<tr><td>Status</td><td class="amt">${esc(p.status)}</td></tr></tbody></table>
          <div><p class="help">Your order code. Keep it to open this order on another device.</p><p class="code">${esc(code)}</p></div></div>
        <p class="actions"><a class="btn" href="#/orders">My orders</a><button class="btn btn--quiet" type="button" id="copy">Copy order link</button></p></div></section>`;
    $("#copy").addEventListener("click", async ev => {
      const url = location.origin + location.pathname + "#/o/" + code;
      try { await navigator.clipboard.writeText(url); ev.target.textContent = "Link copied"; } catch { ev.target.textContent = url; }
    });
  }

  // ------------------------------------------------------------- my orders
  async function orders() {
    const list = codes();
    app.innerHTML = `<section class="container"><div class="slip" style="max-width:820px;margin-inline:auto"><h2>My orders</h2><ul class="list" id="ol">${list.map(c => `<li data-c="${esc(c)}"></li>`).join("")}</ul>
      ${list.length ? "" : '<div class="empty"><p>No orders on this device yet.</p><a class="btn btn--gold" href="#/design">Create your design</a></div>'}
      <form id="find" class="q"><div class="field"><label for="code">Have an order code from another device?</label><input id="code" autocomplete="off" pattern="[A-Za-z0-9_-]{24}" placeholder="24-character code"></div><p><button class="btn btn--quiet" type="submit">Open order</button></p></form></div></section>`;
    $("#find").addEventListener("submit", ev => { ev.preventDefault(); const c = $("#code").value.trim(); if (/^[A-Za-z0-9_-]{24}$/.test(c)) location.hash = "#/o/" + c; });
    await Promise.all(list.map(async c => {
      const li = app.querySelector(`[data-c="${c}"]`);
      try {
        const v = await api("orders/" + c), f = v.form || {}, p = v.purchase;
        const d = (v.designs || []).find(x => p && x.version === p.version) || (v.designs || [])[1] || (v.designs || [])[0];
        const pic = d?.files?.render_hero || CAT[f.style || DEFAULT_FAMILY[f.piece]]?.picture;
        const state = p ? [p.status, "paid"] : v.result_status === "needs_info" ? ["Needs your answer", "working"] : v.result_status === "infeasible" ? ["Can't be cast as asked", "stuck"]
          : v.status === "failed" ? ["Workshop problem", "stuck"] : v.status === "done" ? ["Designs ready", ""] : ["Being made", "working"];
        li.innerHTML = `<a class="order" href="#/o/${c}"><span class="thumb">${pic ? `<img src="${esc(pic)}" alt="">` : ""}</span>
          <span><h3>${esc(f.karat)}K ${esc(PIECE[f.piece]?.name || "")}${p ? ", " + esc(p.variant) : ""}</h3><span class="muted">${esc(targetText(f.target))}${p ? ", " + inr(p.due_inr ?? p.total_inr) : ""}. ${new Date(v.created * 1000).toLocaleDateString()}</span></span>
          <span class="state ${state[1] ? "state--" + state[1] : ""}">${esc(state[0])}</span></a>`;
      } catch { li.innerHTML = `<p class="muted">An order this device remembers could not be opened.</p>`; }
    }));
  }

  // ------------------------------------------------------------- router
  function route() {
    clearTimeout(poll);
    const [, page, a, b] = location.hash.split("/");
    document.querySelectorAll("[data-nav]").forEach(n => n.toggleAttribute("aria-current", n.dataset.nav === page || (page === "o" && n.dataset.nav === "orders")));
    document.querySelectorAll("[data-nav][aria-current]").forEach(n => n.setAttribute("aria-current", "page"));
    if (page === "design") return design(a);
    if (page === "o" && a) return order(a, b);
    if (page === "pay" && a) return pay(a, b);
    if (page === "orders") return orders();
    return intro();
  }
  document.querySelector(".foot")?.insertAdjacentHTML("beforebegin", ARCHES);
  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });
  count();
  route();
})();
