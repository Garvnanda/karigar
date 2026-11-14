// Karigar console. Every number shown comes from /api (the worker's JobResult); nothing is computed here.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} },
  };
  let token = store.get("karigar.owner");
  let lang = store.get("karigar.lang") || "en";
  let conversation = null;
  let orders = [];
  let current = null;

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // Indian grouping of a stored rupee amount (display only, same as replies.inr).
  const inr = n => (typeof n === "number" ? "₹" + Math.round(n).toLocaleString("en-IN") : "—");
  const g = n => (typeof n === "number" ? n.toFixed(2) + " g" : "—");
  const when = t => (t ? new Date(t * 1000).toLocaleString() : "—");
  const safeUrl = u => (typeof u === "string" && /^(\/files\/|https:\/\/)/.test(u) ? u : null);

  async function api(path, opts = {}) {
    const r = await fetch(path, { ...opts, headers: { "Authorization": "Bearer " + token, "Content-Type": "application/json", ...(opts.headers || {}) } });
    if (r.status === 401) { signOut(); throw new Error("Sign-in needed"); }
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body?.error?.message || ("HTTP " + r.status));
    return body;
  }

  function applyLang() {
    document.documentElement.lang = lang === "hi" ? "hi" : "en";
    document.querySelectorAll("[data-en]").forEach(el => { el.textContent = lang === "hi" ? el.dataset.hi : el.dataset.en; });
  }

  function show(tab) {
    document.querySelectorAll("[role=tab]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    ["orders", "try", "catalogue", "rate", "workshop", "system"].forEach(t => { $("#tab-" + t).hidden = t !== tab || !token; });
    $("#login").hidden = !!token;
    if (!token) return;
    if (tab === "orders") loadOrders();
    if (tab === "catalogue") loadCatalogue();
    if (tab === "system") loadSystem();
    if (tab === "rate" || tab === "workshop") loadShop();
    if (location.hash.slice(1) !== tab) history.replaceState(null, "", "#" + tab);
  }

  function signOut() { token = null; store.set("karigar.owner", null); show("orders"); }

  // ---------------- orders
  async function loadOrders() {
    try { orders = (await api("/api/orders")).orders; } catch (e) { $("#orders").innerHTML = `<li class="err">${esc(e.message)}</li>`; return; }
    renderOrders();
    if (!current && orders[0]) openOrder(orders[0].order_id);
  }

  function renderOrders() {
    const q = $("#q").value.toLowerCase(), st = $("#st").value;
    const rows = orders.filter(o => (!st || o.status === st) && (!q || [o.order_id, o.piece, o.karat].join(" ").toLowerCase().includes(q)));
    $("#orders").innerHTML = rows.length ? rows.map(o => {
      const w = (o.finished_g || []).filter(x => typeof x === "number");
      const t = (o.total_inr || []).filter(x => typeof x === "number");
      return `<li><button data-id="${esc(o.order_id)}" ${o.order_id === current ? 'aria-current="true"' : ""}>
        <strong>${esc(o.karat ? o.karat + "K " : "")}${esc(o.piece || "order")}</strong>
        <span class="pill ${esc(o.status)}">${esc(o.status)}</span>
        <span class="meta"><span class="num">${w.length ? w.map(g).join(" · ") : "—"}</span> ${t.length ? "· " + t.map(inr).join(" · ") : ""}</span>
        <span class="id">${esc(o.order_id)} · ${esc(when(o.created))}</span></button></li>`;
    }).join("") : `<li class="muted">No orders yet. Try one in "Try it".</li>`;
  }

  async function openOrder(id) {
    current = id; renderOrders();
    const d = $("#detail");
    d.innerHTML = `<p class="muted">Loading ${esc(id)}…</p>`;
    let o;
    try { o = await api("/api/orders/" + encodeURIComponent(id)); } catch (e) { d.innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
    const brief = o.brief || {};
    const facts = Object.entries(brief).filter(([k, v]) => v != null && v !== "" && typeof v !== "object" && !["lang"].includes(k));
    d.innerHTML = `
      <header><p class="mono muted">${esc(o.order_id)} · <span class="pill ${esc(o.status)}">${esc(o.status)}</span></p>
        <p class="request">“${esc(o.request || "")}”</p></header>
      ${facts.length ? `<dl class="kv">${facts.map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${esc(v)}</dd>`).join("")}</dl>` : ""}
      ${(brief.assumptions || []).length ? `<p class="muted">Assumed: ${brief.assumptions.map(esc).join("; ")}</p>` : ""}
      ${o.explanation ? `<p>${esc(o.explanation)}</p>` : ""}
      <div class="variants">${(o.versions || []).map(variant).join("") || '<p class="muted">No designs yet.</p>'}</div>
      ${(o.versions || []).length ? `<form class="row edit-row" id="edit-form">
        <label for="edit-text" class="sr">Edit</label>
        <input id="edit-text" placeholder="e.g. Middle one, but make the flower slightly bigger">
        <button class="primary" type="submit">Send edit</button></form><p id="edit-out" class="muted"></p>` : ""}`;
    const f = $("#edit-form");
    if (f) f.addEventListener("submit", async ev => {
      ev.preventDefault();
      const text = $("#edit-text").value.trim(); if (!text) return;
      $("#edit-out").textContent = "Working…";
      try {
        const r = await api(`/api/orders/${encodeURIComponent(id)}/edits`, { method: "POST", body: JSON.stringify({ text, wait_s: 45 }) });
        $("#edit-out").textContent = r.reply || "Queued.";
        openOrder(id); loadOrders();
      } catch (e) { $("#edit-out").textContent = e.message; }
    });
  }

  function variant(v) {
    const w = v.weights || {}, q = v.quote || {}, files = v.files || {};
    const glb = safeUrl(files.glb), img = safeUrl(files.render_hero);
    const view = glb ? `<model-viewer src="${esc(glb)}" camera-controls auto-rotate shadow-intensity="0.6" exposure="1.1" alt="3D model of ${esc(v.variant)}" ${img ? `poster="${esc(img)}"` : ""}></model-viewer>`
      : img ? `<img src="${esc(img)}" alt="${esc(v.variant)} render">` : "";
    const lines = (q.lines || []).map(l => `<tr><td>${esc(l.label)}${l.assumed ? ' <span class="assumed">assumed</span>' : ""}<span class="src">${esc(l.source)}</span></td><td class="amt">${inr(l.amount_inr)}</td></tr>`).join("");
    const checks = (v.mesh_checks || []).map(c => `<div><span class="pill ${esc(c.status)}">${esc(c.status)}</span><span>${esc(c.text || c.rule)}</span></div>`).join("");
    const links = [["render_hero", "Photo"], ["stl", "STL"], ["glb", "3D (GLB)"], ["job_card_md", "Job card"], ["quote", "Quote JSON"]]
      .filter(([k]) => safeUrl(files[k])).map(([k, l]) => `<a href="${esc(files[k])}" target="_blank" rel="noopener noreferrer">${l}</a>`).join("");
    const edit = v.edit ? `<p class="muted">Edit “${esc(v.edit_text)}”: ${esc(v.edit.summary || "")}</p>` : "";
    return `<section class="variant">
      <h3>v${esc(v.version)} · ${esc(v.variant)}</h3>${view}
      <div class="weight">${g(w.finished_g)}${typeof w.tolerance_g === "number" ? " ± " + w.tolerance_g.toFixed(2) + " g" : ""}</div>
      <div class="muted num">cast ${g(w.casting_g ?? w.modelled_g)}${typeof w.expected_loss_pct === "number" ? ` · loss ${w.expected_loss_pct}%` : ""}</div>
      <div class="total">${inr(q.total)}${typeof q.to_pay === "number" ? ` <span class="muted">· to pay ${inr(q.to_pay)}</span>` : ""}</div>
      ${lines ? `<details><summary>Quote lines</summary><table class="lines"><tbody>${lines}</tbody></table></details>` : ""}
      ${checks ? `<div class="checks">${checks}</div>` : ""}
      ${edit}<div class="files">${links || '<span class="muted">Files still being made</span>'}</div></section>`;
  }

  // ---------------- try it (same reply text Nonilion shows)
  function bubble(text, me) {
    const el = document.createElement("div");
    el.className = "msg" + (me ? " me" : "");
    // Replies are Markdown with [label](url) links: render only those links, everything else as text.
    el.innerHTML = esc(text).replace(/\[([^\]]+)\]\(((?:https:\/\/|\/files\/)[^)\s]+)\)/g, (_, l, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${l}</a>`)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    $("#chat").append(el); el.scrollIntoView({ block: "end" });
    return el;
  }

  $("#chat-form").addEventListener("submit", async ev => {
    ev.preventDefault();
    const text = $("#msg").value.trim(); if (!text) return;
    bubble(text, true); $("#msg").value = "";
    const wait = bubble("…", false);
    try {
      const path = conversation ? `/api/conversations/${encodeURIComponent(conversation)}/messages` : "/api/orders";
      const r = await api(path, { method: "POST", body: JSON.stringify({ text, agent: $("#agent").value, wait_s: 45, ...(conversation ? {} : {}) }) });
      conversation = r.conversation;
      wait.remove(); bubble(r.reply || "Queued. Send any message to fetch the result.", false);
      current = null;
    } catch (e) { wait.textContent = e.message; }
  });

  // ---------------- catalogue + system
  let cat = null;
  async function loadCatalogue() {
    if (!cat) {
      try { cat = (await (await fetch("catalogue.json")).json()).families; } catch { $("#cat").innerHTML = '<p class="err">catalogue.json missing: run scripts/make_catalogue.py</p>'; return; }
    }
    $("#cat").innerHTML = cat.map(f => {
      const w = f.weights_g || {};
      return `<div class="fam"><span class="kind">${esc(f.piece_type)} · ${esc(f.karat)}K</span><h3>${esc(f.title)}</h3>
        <div class="w"><span>lighter ${g(w.lighter)}</span><span>balanced ${g(w.balanced)}</span><span>statement ${g(w.statement)}</span></div>
        <button class="ghost" data-start="${esc(f.title)}" data-piece="${esc(f.piece_type)}">Start an order</button></div>`;
    }).join("");
  }
  $("#cat").addEventListener("click", ev => {
    const b = ev.target.closest("[data-start]"); if (!b) return;
    conversation = null;
    $("#msg").value = `22K ${b.dataset.start}`;
    show("try"); $("#msg").focus();
  });

  async function loadSystem() {
    try {
      const s = await api("/api/system");
      const rows = [["Worker", s.worker_online ? "online" : "offline"], ["Worker last seen", when(s.worker_last_seen)],
        ...Object.entries(s.by_status || {}).map(([k, v]) => ["Jobs " + k, v]), ["Last job update", when(s.last_job_update)]];
      $("#sys").innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
    } catch (e) { $("#sys").innerHTML = `<dd class="err">${esc(e.message)}</dd>`; }
  }

  // ---------------- gold rate + workshop (both live on the worker; it reports through a shop job)
  function renderShop(sh) {
    if (!sh) { $("#rates tbody").innerHTML = '<tr><td class="muted">No report from the worker yet. Press refresh.</td></tr>'; $("#cal").innerHTML = ""; return; }
    $("#rates tbody").innerHTML = (sh.rates || []).map(r => `<tr><td><strong>${esc(r.karat)}K</strong>
      <span class="pill ${r.status === "ok" ? "pass" : r.status === "stale" ? "warn" : "fail"}">${esc(r.status)}</span>
      <span class="src">${esc(r.source || "")} · set ${esc(r.set_at || "—")}</span></td>
      <td class="amt">${typeof r.per_g === "number" ? "₹" + r.per_g.toLocaleString("en-IN") + "/g" : "—"}</td></tr>`).join("");
    const c = sh.calibration || {}, t = c.tolerance || {};
    const tol = Object.entries(t).map(([k, v]) => `${k} ${v}`).join(", ");
    $("#cal").innerHTML = [["Workshop", c.workshop || "(default)"], ["Learned", c.summary], ["Loss", c.loss_pct + "%"],
      ["Records", c.records], ["Tolerance", tol || "—"], ["Report from", when(sh.reported_at)]]
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
    if (c.workshop && !$("#cal-ws").value) $("#cal-ws").value = c.workshop;
  }
  async function shop(body, out) {
    out.textContent = "Asking the worker…";
    try {
      const r = await api("/api/shop", { method: "POST", body: JSON.stringify({ ...body, wait_s: 45 }) });
      if (r.shop) renderShop({ ...r.shop, reported_at: Date.now() / 1000 });
      out.textContent = r.status === "done" ? (r.shop?.refresh?.message || (r.shop?.recorded ? `Recorded: loss ${r.shop.recorded.loss_pct}%` : "Updated."))
        : r.status === "failed" ? "The worker could not do that: " + (r.error || "")
        : "Queued: the worker is offline or busy; it runs on its next poll.";
    } catch (e) { out.textContent = e.message; }
  }
  async function loadShop() {
    try { renderShop((await api("/api/shop")).shop); } catch (e) { $("#rate-out").textContent = e.message; }
  }
  $("#rate-refresh").addEventListener("click", () => shop({ action: "refresh_rate" }, $("#rate-out")));
  $("#cal-form").addEventListener("submit", ev => {
    ev.preventDefault();
    shop({ action: "calibrate", workshop: $("#cal-ws").value.trim(), designed_g: parseFloat($("#cal-d").value),
           actual_g: parseFloat($("#cal-a").value) }, $("#cal-out"));
  });

  // ---------------- wiring
  document.querySelector(".tabs").addEventListener("click", ev => { const b = ev.target.closest("[data-tab]"); if (b) show(b.dataset.tab); });
  $("#orders").addEventListener("click", ev => { const b = ev.target.closest("[data-id]"); if (b) openOrder(b.dataset.id); });
  $("#q").addEventListener("input", renderOrders);
  $("#st").addEventListener("change", renderOrders);
  $("#logout").addEventListener("click", signOut);
  $("#lang").addEventListener("click", () => { lang = lang === "hi" ? "en" : "hi"; store.set("karigar.lang", lang); applyLang(); });
  $("#login-form").addEventListener("submit", async ev => {
    ev.preventDefault();
    token = $("#token").value.trim();
    try { await api("/api/system"); store.set("karigar.owner", token); $("#login-err").hidden = true; show("orders"); }
    catch (e) { $("#login-err").textContent = "That token was refused. Check KARIGAR_OWNER_TOKEN on the service."; $("#login-err").hidden = false; token = null; }
  });
  applyLang();
  show(["orders", "try", "catalogue", "rate", "workshop", "system"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "orders");
})();
