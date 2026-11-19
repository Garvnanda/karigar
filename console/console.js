// Karigar workshop console (shop owner). Every number comes from /api; nothing is computed here
// except grouping digits. Rates and calibration live on the worker and arrive through shop jobs.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const inr = n => (typeof n === "number" ? "₹" + Math.round(n).toLocaleString("en-IN") : "—");
  const grams = n => (typeof n === "number" ? n.toFixed(2) + " g" : "—");
  const when = t => (t ? new Date(t * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—");
  const safe = u => (typeof u === "string" && /^(\/files\/|https:\/\/)/.test(u) ? u : "");
  let token = null;
  try { token = localStorage.getItem("karigar.owner"); } catch {}
  const view = $("#view");

  // ------------------------------------------------------------- the tray (same ornament as the studio)
  const MANDALA = (() => {
    const c = 200, out = [];
    [196, 188, 150, 112, 70, 36, 14].forEach(r => out.push(`<circle cx="${c}" cy="${c}" r="${r}"/>`));
    const petals = (n, r0, r1, w, rot = 0) => { for (let k = 0; k < n; k++) {
      const a = (k / n) * 2 * Math.PI + rot, b = w / r1;
      const p = (rr, aa) => `${(c + rr * Math.cos(aa)).toFixed(1)} ${(c + rr * Math.sin(aa)).toFixed(1)}`;
      out.push(`<path d="M${p(r0, a - b)} Q${p(r1, a - b * 1.4)} ${p(r1 + 8, a)} Q${p(r1, a + b * 1.4)} ${p(r0, a + b)}"/>`); } };
    petals(16, 36, 66, 12); petals(16, 70, 106, 16, Math.PI / 16); petals(32, 112, 146, 10); petals(48, 150, 184, 6, Math.PI / 48);
    for (let k = 0; k < 64; k++) { const a = (k / 64) * 2 * Math.PI;
      out.push(`<circle cx="${(c + 192 * Math.cos(a)).toFixed(1)}" cy="${(c + 192 * Math.sin(a)).toFixed(1)}" r="1.6" fill="currentColor"/>`); }
    return `<svg class="mandala" viewBox="0 0 400 400" fill="none" stroke="currentColor" stroke-width="0.8" aria-hidden="true">${out.join("")}</svg>`;
  })();
  function trayInner({ model, picture, name, fact }) {
    const media = model ? `<model-viewer src="${esc(model)}" ${picture ? `poster="${esc(picture)}"` : ""} camera-controls auto-rotate rotation-per-second="18deg" camera-orbit="0deg 72deg 135%" interaction-prompt="none" exposure="1.15" environment-image="neutral" alt="${esc(name || "Design")} in 3D; drag to turn it"></model-viewer>`
      : picture ? `<img class="still" src="${esc(picture)}" alt="${esc(name || "")}">` : "";
    return `${MANDALA}${media}<div class="tray-caption"><div class="name">${esc(name || "")}</div><div class="fact">${fact || ""}</div></div>`;
  }
  let CAT = null;
  async function catalogue() {
    if (!CAT) { try { CAT = (await (await fetch("/studio/catalogue.json")).json()).families; } catch { CAT = []; } }
    return CAT;
  }
  async function showcase() {
    const c = await catalogue(), f = c.find(x => x.family === "pendant_temple_lotus") || c[0];
    return f ? { model: "/studio/" + f.model, picture: "/studio/" + f.picture, name: f.title, fact: f.weights_g ? `${grams(f.weights_g.balanced)} of 22K, measured on the model` : "" } : {};
  }

  async function api(path, body) {
    const r = await fetch(path, { method: body ? "POST" : "GET", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined });
    if (r.status === 401) { signOut(); throw new Error("Sign in again."); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d?.error?.message || "HTTP " + r.status);
    return d;
  }
  const shop = (body) => api("/api/shop", { ...body, wait_s: 45 });
  function signOut() { token = null; try { localStorage.removeItem("karigar.owner"); } catch {} route(); }
  const room = (trayHtml, slipHtml) => `<section class="room"><div class="tray">${trayHtml}</div><div class="slip">${slipHtml}</div></section>`;

  // ------------------------------------------------------------- overview
  async function home() {
    const sc = await showcase();
    view.innerHTML = room(trayInner(sc), `<p class="hindi" lang="hi">कारीगर</p><h1>The workshop.</h1>
      <p class="lead">Orders from the studio and from Nonilion land here. Weigh what comes back from casting, and every new design learns from it.</p>
      <div class="figures" id="figs"><p class="muted">Loading…</p></div>
      <ul class="pills"><li>Studio orders</li><li>Nonilion chat</li><li>Gold rate</li><li>Calibration</li></ul>`);
    try {
      const [p, s, a, sh] = await Promise.all([api("/api/purchases"), api("/api/system"), api("/api/activity"), api("/api/shop")]);
      const rate22 = (sh.shop?.rates || []).find(r => r.karat === 22);
      const fromNon = a.activity.filter(x => x.channel === "nonilion").length;
      const fig = (href, v, k) => `<a class="figure-card" href="${href}"><span class="v">${esc(v)}</span><span class="k">${esc(k)}</span></a>`;
      $("#figs").innerHTML = fig("#placed", p.purchases.length, "placed orders") + fig("#nonilion", fromNon, "recent requests from Nonilion")
        + fig("#rate", rate22 && typeof rate22.per_g === "number" ? "₹" + rate22.per_g.toLocaleString("en-IN") : "—", `22K per gram${rate22 ? ", " + rate22.status : ""}`)
        + fig("#requests", s.worker_online ? "Online" : "Offline", `Blender worker${s.worker_last_seen ? ", seen " + when(s.worker_last_seen) : ""}`);
      const last = p.purchases[0];
      if (last?.files?.glb) view.querySelector(".tray").innerHTML = trayInner({ model: safe(last.files.glb), picture: safe(last.files.render_hero), name: last.variant, fact: `Latest order, ${esc(last.name)}` });
    } catch (e) { $("#figs").innerHTML = `<p class="err">${esc(e.message)}</p>`; }
  }

  // ------------------------------------------------------------- placed orders
  async function placed() {
    view.innerHTML = room(trayInner(await showcase()), `<div><h1>Placed orders</h1><p class="muted">Pick an order to see it in 3D. Record the weight when the piece comes back finished.</p></div><ul class="ledger" id="ledger"><li class="empty">Loading…</li></ul>`);
    let rows;
    try { rows = (await api("/api/purchases")).purchases; } catch (e) { $("#ledger").innerHTML = `<li class="err">${esc(e.message)}</li>`; return; }
    if (!rows.length) { $("#ledger").innerHTML = `<li class="empty">No placed orders yet. They appear here when a customer orders from the studio.</li>`; return; }
    const select = i => {
      const r = rows[i], w = r.weights || {};
      view.querySelector(".tray").innerHTML = trayInner({ model: safe((r.files || {}).glb), picture: safe((r.files || {}).render_hero), name: r.variant,
        fact: `${grams(w.finished_g)}, ${esc(r.name)}` });
      view.querySelectorAll(".entry").forEach((e, k) => e.setAttribute("aria-current", String(k === i)));
    };
    $("#ledger").innerHTML = rows.map((r, i) => {
      const w = r.weights || {}, f = r.form || {}, pic = safe((r.files || {}).render_hero);
      const cast = w.casting_g ?? w.modelled_g;
      return `<li class="entry" data-i="${i}" tabindex="0">
        <span class="thumb">${pic ? `<img src="${esc(pic)}" alt="">` : ""}</span>
        <div><h3>${esc(r.variant || "Design")}</h3><p class="who">${esc(r.name)}, <a href="tel:${esc(r.phone)}">${esc(r.phone)}</a></p>
          <p class="muted">${esc(f.karat)}K ${esc(f.metal)}, ${when(r.created)}</p></div>
        <div><div class="money">${inr(r.due_inr ?? r.total_inr)}</div>${r.due_inr != null && r.due_inr !== r.total_inr ? `<p class="muted">Design ${inr(r.total_inr)}, less old gold</p>` : ""}<span class="state ${r.status.startsWith("paid") ? "state--paid" : ""}">${esc(r.status)}</span></div>
        <div class="cast"><dl class="facts"><dt>Finished</dt><dd>${grams(w.finished_g)}${typeof w.tolerance_g === "number" ? " ± " + w.tolerance_g.toFixed(2) : ""}</dd><dt>Cast at</dt><dd>${grams(cast)}</dd></dl>
          ${typeof cast === "number" ? `<form data-cast="${cast}"><label class="field" for="act${i}">Weighed after finishing<input id="act${i}" type="number" inputmode="decimal" step="0.01" min="0.01" placeholder="g" required></label>
            <button class="btn" type="submit">Record</button></form><p class="msg"></p>` : ""}</div></li>`;
    }).join("");
    view.querySelectorAll(".entry").forEach(e => {
      e.addEventListener("click", ev => { if (!ev.target.closest("form, a")) select(Number(e.dataset.i)); });
      e.addEventListener("keydown", ev => { if ((ev.key === "Enter" || ev.key === " ") && ev.target === e) { ev.preventDefault(); select(Number(e.dataset.i)); } });
    });
    select(0);
    view.querySelectorAll("form[data-cast]").forEach(fm => fm.addEventListener("submit", async ev => {
      ev.preventDefault();
      const inp = fm.querySelector("input"), v = Number(inp.value), msg = fm.nextElementSibling, b = fm.querySelector("button");
      if (!(v > 0 && v <= 2000)) { inp.setAttribute("aria-invalid", "true"); msg.className = "err"; msg.textContent = "Enter the weighed grams."; return; }
      inp.removeAttribute("aria-invalid"); b.disabled = true; b.setAttribute("aria-busy", "true");
      try {
        const ws = (await api("/api/shop")).shop?.calibration?.workshop || "main";
        const r = await shop({ action: "calibrate", workshop: ws, designed_g: Number(fm.dataset.cast), actual_g: v });
        msg.className = r.status === "done" ? "ok" : "muted";
        msg.textContent = r.status === "done" ? `Recorded. Loss ${r.shop.recorded.loss_pct}%, workshop now ${r.shop.calibration.summary}.` : "Queued: the worker records it on its next poll.";
      } catch (e) { msg.className = "err"; msg.textContent = e.message; }
      b.disabled = false; b.removeAttribute("aria-busy");
    }));
  }

  // ------------------------------------------------------------- nonilion
  async function nonilion() {
    view.innerHTML = `<div class="container page"><div><h1>Nonilion</h1><p class="lead">Two agents in the Nonilion office talk to this service. Customers chat with them in Hinglish; the replies, weights and quotes come from here.</p></div>
      <div class="agents" id="agents"></div>
      <div><h2>How a message travels</h2></div>
      <ol class="route"><li><strong>Nonilion room</strong><span>The jeweller writes to Sakhi or Karigar in the office chat.</span></li>
        <li><strong>This service on Render</strong><span>Receives the chat at the agent's base URL, queues a job, streams progress back.</span></li>
        <li><strong>Blender worker</strong><span>On the laptop: reads the brief, solves the gold, renders, quotes.</span></li>
        <li><strong>Back in the room</strong><span>Weights ± tolerance, the quote, and links to the photo, 3D model, STL and job card.</span></li></ol>
      <div><h2>Live requests</h2><p class="muted">Newest first. Nonilion chats are marked in gold.</p></div><ul class="feed" id="feed"><li class="muted">Loading…</li></ul></div>`;
    let a;
    try { a = await api("/api/activity"); } catch (e) { $("#feed").innerHTML = `<li class="err">${esc(e.message)}</li>`; return; }
    const base = a.base_url || location.origin;
    const card = (name, slug, job) => `<div class="agent"><h3>${name}</h3><p class="muted">${job}</p>
      <div class="url"><code>${esc(base)}/${slug}/v1</code><button class="copy" type="button" data-copy="${esc(base)}/${slug}/v1">Copy base URL</button></div>
      <p class="muted">API key: the value of <code>KARIGAR_API_KEY</code> on Render. Instructions: <code>nonilion/${slug}.md</code>.</p></div>`;
    $("#agents").innerHTML = card("Sakhi", "sakhi", "At the counter: reads the request, asks what is missing, shows the photo and quote.")
      + card("Karigar", "karigar", "In the workshop: the designs, weights, files and edits.");
    view.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied"; } catch { b.textContent = b.dataset.copy; }
    }));
    const label = { nonilion: "Nonilion", studio: "Studio", api: "API" };
    $("#feed").innerHTML = a.activity.map(x => `<li><span class="chan ${x.channel === "nonilion" ? "chan--nonilion" : ""}">${label[x.channel] || esc(x.channel)}${x.channel === "nonilion" && x.agent ? ", " + esc(x.agent) : ""}</span>
      <span class="t">${esc(x.text)}<span class="src">${esc(x.result || x.status)}${x.designs ? `, ${x.designs} designs` : ""}${x.order_id ? ", " + esc(x.order_id) : ""}</span></span>
      <span class="when">${when(x.created)}</span></li>`).join("") || '<li class="muted">No requests yet. Say hello to Sakhi in the Nonilion room.</li>';
  }

  // ------------------------------------------------------------- gold rate
  function rateTable(sh) {
    return `<div class="wrap"><table class="table"><thead><tr><th>Karat</th><th class="num">₹ per gram</th><th>Status</th><th>Set</th></tr></thead><tbody>${(sh?.rates || []).map(r => `<tr><td>${r.karat}K</td>
      <td class="num">${typeof r.per_g === "number" ? r.per_g.toLocaleString("en-IN") : "—"}</td><td><span class="state ${r.status === "ok" ? "state--paid" : ""}">${esc(r.status)}</span></td>
      <td>${esc((r.set_at || "").replace("T", " ").slice(0, 16))}<span class="src">${esc(r.source || "")}</span></td></tr>`).join("") || '<tr><td colspan="4" class="muted">No report from the worker yet.</td></tr>'}</tbody></table></div>`;
  }
  async function rate() {
    view.innerHTML = `<div class="container page"><div><h1>Gold rate</h1><p class="lead">Orders refuse a rate older than 24 hours. The job adds ₹5,000 per 10 g to MCX.</p></div>
      <div class="split"><div class="box" id="rates">Loading…</div>
      <div class="box"><h2>Refresh from MCX</h2><p class="muted">Fetches the MCX gold price now and saves all four karats.</p><p><button class="btn btn--gold" id="refresh">Refresh now</button></p><p id="refresh-msg"></p>
        <h2>Set by hand</h2><p class="muted">Rupees per gram. Values outside the sane range are refused.</p>
        <form id="set" class="row">${[24, 22, 18, 14].map(k => `<label class="field" for="r${k}">${k}K<input id="r${k}" type="number" inputmode="decimal" step="0.01" min="1"></label>`).join("")}
          <button class="btn" type="submit">Save rates</button></form><p id="set-msg"></p></div></div></div>`;
    const show = sh => { $("#rates").innerHTML = rateTable(sh); };
    try { show((await api("/api/shop")).shop); } catch (e) { $("#rates").innerHTML = `<p class="err">${esc(e.message)}</p>`; }
    $("#refresh").addEventListener("click", async ev => {
      const b = ev.currentTarget, m = $("#refresh-msg"); b.disabled = true; b.setAttribute("aria-busy", "true"); m.className = "muted"; m.textContent = "Asking the worker…";
      try { const r = await shop({ action: "refresh_rate" }); if (r.shop) show(r.shop); m.className = r.shop?.refresh?.ok ? "ok" : "err"; m.textContent = r.shop?.refresh?.message || "Queued: the worker is offline or busy."; }
      catch (e) { m.className = "err"; m.textContent = e.message; }
      b.disabled = false; b.removeAttribute("aria-busy");
    });
    $("#set").addEventListener("submit", async ev => {
      ev.preventDefault();
      const rates = {}; [24, 22, 18, 14].forEach(k => { const v = $("#r" + k).value; if (v !== "") rates[String(k)] = Number(v); });
      const m = $("#set-msg");
      if (!Object.keys(rates).length) { m.className = "err"; m.textContent = "Enter at least one karat's rate."; return; }
      try { const r = await shop({ action: "set_rate", rates }); if (r.shop) show(r.shop); m.className = r.shop?.set?.ok ? "ok" : "err"; m.textContent = r.shop?.set?.message || "Queued: the worker saves it on its next poll."; }
      catch (e) { m.className = "err"; m.textContent = e.message; }
    });
  }

  // ------------------------------------------------------------- calibration
  async function workshop() {
    view.innerHTML = `<div class="container page"><div><h1>Calibration</h1><p class="lead">After three weighed pieces, every new weight uses this workshop's own loss and tolerance.</p></div><div id="cal">Loading…</div></div>`;
    try {
      const sh = (await api("/api/shop")).shop;
      const c = sh?.calibration;
      if (!c) { $("#cal").innerHTML = '<p class="muted">No report from the worker yet. Open Gold rate and refresh to wake it.</p>'; return; }
      const t = c.tolerance || {};
      $("#cal").innerHTML = `<div class="split"><dl class="facts"><dt>Workshop</dt><dd>${esc(c.workshop || "default")}</dd><dt>Learned</dt><dd>${esc(c.summary)}</dd>
          <dt>Loss</dt><dd>${esc(c.loss_pct)}%</dd><dt>Tolerance</dt><dd>± ${esc(t.pct ?? "—")}%${t.assumed ? " (assumed default)" : ""}</dd><dt>Reported</dt><dd>${when(sh.reported_at)}</dd></dl>
        <div class="wrap"><table class="table"><thead><tr><th class="num">Cast at</th><th class="num">Weighed</th><th class="num">Loss</th></tr></thead><tbody>${(c.recent || []).map(r => `<tr>
          <td class="num">${grams(r.designed_g)}</td><td class="num">${grams(r.actual_g)}</td><td class="num">${((1 - r.actual_g / r.designed_g) * 100).toFixed(2)}%</td></tr>`).join("") || '<tr><td colspan="3" class="muted">No pieces recorded. Record one from Placed orders.</td></tr>'}</tbody></table></div></div>`;
    } catch (e) { $("#cal").innerHTML = `<p class="err">${esc(e.message)}</p>`; }
  }

  // ------------------------------------------------------------- all requests + system
  async function requests() {
    view.innerHTML = `<div class="container page"><div><h1>All requests</h1><p class="lead">Every order the workshop solved, from the studio, Nonilion chat or the API.</p></div><dl class="facts" id="sys"></dl><div class="wrap" id="req">Loading…</div></div>`;
    try {
      const [{ orders }, s] = await Promise.all([api("/api/orders"), api("/api/system")]);
      $("#sys").innerHTML = [["Worker", s.worker_online ? "online" : "offline"], ["Worker last seen", when(s.worker_last_seen)],
        ...Object.entries(s.by_status || {}).map(([k, v]) => ["Jobs " + k, v])].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
      $("#req").innerHTML = `<table class="table"><thead><tr><th>Order</th><th>Piece</th><th>Status</th><th class="num">Finished</th><th class="num">Total</th><th>Time</th></tr></thead><tbody>${orders.map(o => `<tr>
        <td>${esc(o.order_id)}</td><td>${esc(o.karat ? o.karat + "K " : "")}${esc(o.piece || "")}</td><td>${esc(o.status)}</td>
        <td class="num">${(o.finished_g || []).filter(x => typeof x === "number").map(grams).join(", ") || "—"}</td>
        <td class="num">${(o.total_inr || []).filter(x => typeof x === "number").map(inr).join(", ") || "—"}</td><td>${when(o.created)}</td></tr>`).join("") || '<tr><td colspan="6" class="muted">No orders yet.</td></tr>'}</tbody></table>`;
    } catch (e) { $("#req").innerHTML = `<p class="err">${esc(e.message)}</p>`; }
  }

  // ------------------------------------------------------------- router
  const PAGES = { home, placed, nonilion, rate, workshop, requests };
  async function route() {
    const tab = PAGES[location.hash.slice(1)] ? location.hash.slice(1) : "home";
    $("#login").hidden = !!token; view.hidden = !token; document.body.classList.toggle("locked", !token);
    document.querySelectorAll("[data-tab]").forEach(a => a.toggleAttribute("aria-current", a.dataset.tab === tab && !!token));
    document.querySelectorAll("[data-tab][aria-current]").forEach(a => a.setAttribute("aria-current", "page"));
    if (token) return PAGES[tab]();
    $("#login-tray").innerHTML = trayInner(await showcase());
  }
  $("#out").addEventListener("click", signOut);
  $("#login-form").addEventListener("submit", async ev => {
    ev.preventDefault();
    token = $("#token").value.trim().replace(/^["']+|["']+$/g, "");
    try { await api("/api/system"); try { localStorage.setItem("karigar.owner", token); } catch {} $("#login-err").hidden = true; route(); }
    catch { token = null; $("#login-err").hidden = false; $("#login-err").textContent = "That key was refused. It must match KARIGAR_OWNER_TOKEN on the service."; route(); }
  });
  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });
  route();
})();
