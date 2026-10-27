(async function () {
  const root = document.getElementById("root");
  const id = new URLSearchParams(location.search).get("id");
  const { esc, lap, pct, num, NAMES } = TD;
  const CORNERS = ["LF", "RF", "LR", "RR"];
  const SERIES = { LF: "var(--series-1)", RF: "var(--series-2)", LR: "var(--series-3)", RR: "var(--series-4)" };

  if (!id) { root.innerHTML = '<p class="empty">No report selected. <a href="/">Upload a session</a>.</p>'; return; }
  const res = await fetch(`/api/reports/${encodeURIComponent(id)}`);
  if (!res.ok) { root.innerHTML = '<p class="empty">This report was not found. <a href="/">Back to uploads</a>.</p>'; return; }
  const R = await res.json();
  TD.rememberReport(id);
  const S = R.stats, N = R.narrative, ctx = R.context || {};
  const win = R.config_window;
  const flagsById = Object.fromEntries(R.flags.map(f => [f.id, f]));
  const top = flagsById[R.takeaway_flag_id];
  const ls = S.lap_summary;
  document.title = `${S.session.racer || "Session"} · Debrief`;

  const ctxPills = [
    [ctx.make, ctx.model].filter(Boolean).join(" "), ctx.drivetrain, ctx.tyre_compound, ctx.session_type,
    ctx.camber_front_deg != null ? `Camber F ${ctx.camber_front_deg}°` : null,
    ctx.camber_rear_deg != null ? `R ${ctx.camber_rear_deg}°` : null,
    ctx.cold_pressure_front_psi != null ? `Cold F ${ctx.cold_pressure_front_psi} psi` : null,
    ctx.cold_pressure_rear_psi != null ? `R ${ctx.cold_pressure_rear_psi} psi` : null,
  ].filter(Boolean);

  const inDriverSection = f => S.driver_style && f.category === "driver" && f.action;
  const actionable = R.flags.filter(f => f.severity !== "info" && !inDriverSection(f));
  const observations = R.flags.filter(f => f.severity === "info");
  const notes = Object.fromEntries((N.tyre_notes || []).map(n => [n.tyre, n.note]));
  const hasPressure = CORNERS.some(c => S.tyres[c].pressure_psi);
  const sheet = R.setup_sheet;
  const style = S.driver_style;
  const driverFlags = R.flags.filter(f => f.category === "driver" && f.action);
  const MIRROR = { LF: true, LR: true, RF: false, RR: false };

  root.innerHTML = `
    <div class="stack">
      <section>
        <p class="muted small" style="margin:0 0 4px">${esc([S.session.racer, S.session.vehicle, S.session.track, S.session.date].filter(Boolean).join(" · "))}</p>
        <h1 id="headline">${esc(N.headline)}</h1>
        <div class="meta-row">${ctxPills.map(p => `<span class="pill">${esc(p)}</span>`).join("")}
          <span class="pill" title="${esc(S.session.filename)}">${esc(S.session.filename || "")}</span>
          <button class="theme-btn no-print" id="print" type="button">Download PDF</button></div>
      </section>

      <div class="hero">
        <div class="hero-main">
        <section class="card takeaway">
          <div class="label">Your one priority for next session</div>
          <div class="text" id="takeaway-text">${esc(N.takeaway)}</div>
          ${top ? `<div class="why">Because: ${esc(top.title)}. <a href="#${top.id}">See the evidence</a></div>` : ""}
        </section>
        <section class="tiles">
        <div class="card tile"><div class="k">Best lap</div><div class="v">${lap(ls.best_time_s)}</div><div class="d">${ls.best_lap ? `lap ${ls.best_lap} of ${ls.count}` : "no timed laps"}</div></div>
        <div class="card tile"><div class="k">Flying laps</div><div class="v">${ls.clean}</div><div class="d">${ls.warmup} warm-up · ${ls.count - ls.clean - ls.warmup} slow/other</div></div>
        <div class="card tile"><div class="k">Ambient</div><div class="v">${num(S.session.ambient_c, " °C")}</div><div class="d">working window ${win.low_c}–${win.high_c} °C</div></div>
        <div class="card tile"><div class="k">Report time</div><div class="v">${R.timings.total_s}s</div><div class="d">CSV to debrief</div></div>
      </section>
        </div>
        <section class="card glance" aria-label="Tyres at a glance">
          <div id="car"></div>
          <div class="cap">Flying-lap average · tap a tyre for detail</div>
        </section>
      </div>

      ${sheet ? `<section class="card">
        <h2>Before your next session</h2>
        <p class="muted small" style="margin:-6px 0 12px">Hot pressure target ${sheet.target_hot_psi} psi
          (${sheet.target_source === "entered" ? "your entry" : "default; enter your tyre's own target on the upload form"}).
          Pressure changes are to the cold pressure you set before going out.</p>
        <div class="sheet">
          <div id="setup-car" class="setup-car"></div>
          <div class="table-scroll"><table class="data sheet-table">
            <thead><tr><th>Tyre</th><th>Pressure</th><th>Camber</th><th>Heat shape</th><th>Tools?</th></tr></thead>
            <tbody>${CORNERS.map(c => {
              const cs = sheet.corners[c];
              const tools = [cs.pressure.tools && "Pressure: no tools", cs.camber.tools && "Camber: needs tools"].filter(Boolean);
              return `<tr><td data-label="Tyre">${NAMES[c]}</td>
                <td data-label="Pressure">${cs.pressure.flag ? `<a href="#${cs.pressure.flag}">${esc(cs.pressure.label)}</a>` : esc(cs.pressure.label)}
                  ${cs.pressure.to_psi ? `<div class="muted small">set ${cs.pressure.to_psi} psi</div>` : ""}</td>
                <td data-label="Camber">${cs.camber.flag ? `<a href="#${cs.camber.flag}">${esc(cs.camber.label)}</a>` : esc(cs.camber.label)}</td>
                <td data-label="Heat shape">${esc(cs.heat_shape.label)}${cs.heat_shape.meaning ? `<div class="muted small">${esc(cs.heat_shape.meaning)}</div>` : ""}</td>
                <td data-label="Tools?" class="small">${tools.length ? tools.map(t => `<div>${esc(t)}</div>`).join("") : "–"}</td></tr>`;
            }).join("")}</tbody></table>
          <p class="muted small" style="margin:8px 0 0">Pressure needs only a tyre gauge and air, about 5 minutes in the pits.
            Camber needs a camber gauge and spanners, or an alignment shop.</p></div>
        </div>
        ${sheet.other.length ? `<h3 class="small" style="margin:16px 0 6px">Also</h3><ul class="sheet-other">${sheet.other.map(o =>
          `<li><a href="#${o.flag}">${esc(o.action)}</a> <span class="muted small">${esc(o.tools)}</span></li>`).join("")}</ul>` : ""}
      </section>` : ""}

      <section class="card narrative">
        <h2>Debrief</h2>
        <p id="summary">${esc(N.summary)}</p>
        <div class="source" id="narr-source">${sourceHtml(N)}</div>
      </section>

      <section class="card ask no-print">
        <h2>Ask about this session</h2>
        <form id="ask-form" class="ask-row">
          <input type="text" id="ask-input" maxlength="300" placeholder="e.g. Why should I add camber on the left front?" aria-label="Your question">
          <button class="btn" type="submit" id="ask-btn">Ask</button>
        </form>
        <div class="chips">${["What should I change before my next session?", "Why are my front tyres cold?",
          "What did I do differently on my best lap?", "Do I need tools for these changes?"].map(q =>
          `<button type="button" class="chip">${esc(q)}</button>`).join("")}</div>
        <div id="ask-answers"></div>
      </section>

      <section>
        <div class="toolbar">
          <h2 style="margin:0">Tyre temperatures across the tread</h2>
          <div class="seg" role="group" aria-label="Driving state">
            <button type="button" data-view="all" aria-pressed="true">All running</button>
            <button type="button" data-view="straight" aria-pressed="false">Straights</button>
            <button type="button" data-view="corner" aria-pressed="false">Loaded in corners</button>
          </div>
        </div>
        <div class="legend" style="margin-bottom:12px">
          <span><i class="sw" style="background:var(--cold)"></i>Cold, below ${win.low_c} °C</span>
          <span><i class="sw" style="background:var(--ok)"></i>In window</span>
          <span><i class="sw" style="background:var(--hot)"></i>Hot, above ${win.high_c} °C</span>
          <span><i class="sw" style="background:var(--off)"></i>Off tread, excluded</span>
          <span><i class="sw line" style="background:var(--text-primary)"></i>Peak held 0.5 s</span>
        </div>
        <div class="car">
          ${CORNERS.map(c => {
            const t = S.tyres[c];
            return `<article class="card" id="tyre-${c}">
              <div class="tyre-head"><h3>${NAMES[c]}</h3><span class="big avg">${num(t.average_c, " °C")}</span></div>
              <div class="tyre-stats">
                <span>Peak <b class="pk">${num(t.peak_c, "°")}</b></span>
                <span>Corner peak <b>${num(t.corner_peak_c, "°")}</b></span>
                <span>In window <b class="iw">${pct(t.share_in_window)}</b></span>
                <span>Inside−outside <b class="io">${num(t.all.inner_minus_outer, "°")}</b></span>
                ${t.pressure_psi ? `<span title="First timed lap ${t.pressure_psi.first_lap ?? "–"} psi">Hot pressure <b>${t.pressure_psi.hot} psi</b></span>` : ""}
              </div>
              <div class="zone" data-corner="${c}"></div>
              <p class="tyre-note" data-corner="${c}">${esc(notes[c] || "")}</p>
            </article>`;
          }).join("")}
        </div>
        <p class="muted small" style="margin-top:8px">Measured over ${esc(ls.window_basis)}. Straights exclude braking and
          acceleration zones. Peaks are the hottest temperature held for at least 0.5 s. Each card shows the tyre as seen
          from behind the car, so inside edges face the middle.</p>
      </section>

      <section class="card">
        <h2>Findings</h2>
        ${actionable.length ? `<ul class="flags">${actionable.map(flagHtml).join("")}</ul>` : '<p class="empty">No setup issues found.</p>'}
        ${observations.length ? `<details class="flag-group-toggle" ${actionable.length ? "" : "open"}>
          <summary class="muted">${observations.length} more observations</summary>
          <ul class="flags" style="margin-top:12px">${observations.map(flagHtml).join("")}</ul></details>` : ""}
      </section>

      ${style ? `<section class="card">
        <h2>Driver style</h2>
        <p class="muted small" style="margin:-6px 0 12px">Your best lap (lap ${ls.best_lap ?? "–"}) against a typical flying lap,
          from the ${esc(style.inputs)}.</p>
        <div class="table-scroll"><table class="data">
          <thead><tr><th>Measure</th><th>Best lap</th><th>Typical lap</th></tr></thead>
          <tbody>${style.metrics.filter(m => m.best != null || m.typical != null).map(m => `<tr><td>${esc(m.label)}</td>
            <td>${num(m.best)} ${esc(m.unit)}</td><td>${num(m.typical)} ${esc(m.unit)}</td></tr>`).join("")}</tbody></table></div>
        ${driverFlags.length ? `<ul class="flags" style="margin-top:14px">${driverFlags.map(flagHtml).join("")}</ul>` : ""}
      </section>` : ""}

      <section class="card">
        <div class="toolbar">
          <h2 style="margin:0">Lap by lap</h2>
          <div class="seg" role="group" aria-label="Lap view">
            <button type="button" data-lapview="chart" aria-pressed="true">Charts</button>
            <button type="button" data-lapview="table" aria-pressed="false">Table</button>
          </div>
        </div>
        <div id="lap-charts">
          <div class="legend">${CORNERS.map(c => `<span><i class="sw line" style="background:${SERIES[c]}"></i>${NAMES[c]}</span>`).join("")}</div>
          <h3 class="small muted" style="margin:12px 0 4px">Average tyre temperature (°C) · shaded band = ${win.low_c}–${win.high_c} °C working window</h3>
          <div id="lap-temp"></div>
          ${hasPressure ? `<h3 class="small muted" style="margin:16px 0 4px">Hot pressure (psi, TPMS)</h3><div id="lap-pressure"></div>` : ""}
          <h3 class="small muted" style="margin:16px 0 4px">Lap time (slow and pit laps hidden)</h3>
          <div id="lap-time"></div>
        </div>
        <div id="lap-table" class="table-scroll" hidden></div>
      </section>

      <section class="card">
        <h2>Data quality</h2>
        <div class="table-scroll"><table class="data">
          <thead><tr><th>Tyre</th><th>Valid readings</th><th>Spikes removed</th><th>Zones excluded</th><th>TPMS pressure</th></tr></thead>
          <tbody>${CORNERS.map(c => {
            const q = S.data_quality.temperature[c];
            return `<tr><td>${NAMES[c]}</td><td>${pct(q.valid_share)}</td><td>${q.spikes_removed}</td>
              <td>${(S.data_quality.off_tread_zones[c] || []).join(", ") || "none"}</td>
              <td>${S.data_quality.pressure_available[c] ? "yes" : "missing"}</td></tr>`;
          }).join("")}</tbody></table></div>
        <div class="actions">
          <span class="muted small">Parse ${R.timings.parse_s}s · stats ${R.timings.stats_s}s · narrative ${R.timings.narrative_s ?? 0}s</span>
          <div class="spacer"></div>
          <button class="btn ghost" id="delete" type="button">Delete report</button>
        </div>
      </section>
    </div>`;

  function sourceHtml(n) {
    if (n.source === "pending") return '<span class="spinner"></span> The AI is writing a plain-English debrief; the findings below are ready now.';
    const why = (n.attempts || []).filter(a => a.error || (a.issues && a.issues.length)).map(a =>
      ` ${esc(a.provider)} attempt ${a.attempt}: ${esc(a.error || a.issues.join(" "))}`).join("");
    return (n.source === "llm"
      ? `Written by ${esc(n.model)} (${esc(n.provider)}) from the verified findings below; every number was checked against the data.`
      : "Template narrative (no AI key configured, or every AI draft failed the fact check).") + why;
  }

  function showNarrative(n) {
    document.getElementById("headline").textContent = n.headline;
    document.getElementById("takeaway-text").textContent = n.takeaway;
    document.getElementById("summary").textContent = n.summary;
    document.getElementById("narr-source").innerHTML = sourceHtml(n);
    for (const t of n.tyre_notes || []) {
      const el = document.querySelector(`.tyre-note[data-corner="${t.tyre}"]`);
      if (el) el.textContent = t.note;
    }
  }

  async function waitForNarrative() {
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 2500));
      try {
        const latest = await (await fetch(`/api/reports/${encodeURIComponent(id)}`)).json();
        if (latest.narrative && latest.narrative.source !== "pending") { showNarrative(latest.narrative); return; }
      } catch (e) {}
    }
    document.getElementById("narr-source").textContent = "The AI debrief is taking longer than usual; reload the page to check again.";
  }

  function flagHtml(f) {
    return `<li class="flag" id="${f.id}">
      <div class="flag-head"><span class="sev ${f.severity}">${f.severity}</span>
        <div><div class="flag-title">${esc(f.title)}</div>
          <p class="flag-detail">${esc(f.detail)}</p>
          ${f.action ? `<p class="flag-action">${esc(f.action)}</p>` : ""}
          ${f.why ? `<p class="flag-why"><b>Why this matters:</b> ${esc(f.why)}</p>` : ""}
          <details class="why"><summary>The numbers behind it · rule ${esc(f.rule)}</summary>
            <pre>${esc(JSON.stringify({ evidence: f.evidence, thresholds: f.thresholds }, null, 2))}</pre></details>
        </div></div></li>`;
  }

  let view = ["all", "straight", "corner"].includes(new URLSearchParams(location.search).get("view"))
    ? new URLSearchParams(location.search).get("view") : "all";
  document.querySelectorAll("[data-view]").forEach(x => x.setAttribute("aria-pressed", x.dataset.view === view));
  function drawZones() {
    document.querySelectorAll(".zone").forEach(box => {
      const c = box.dataset.corner, t = S.tyres[c], v = (t.views || {})[view] || {};
      const card = box.closest("article");
      if (!v.profile) { box.innerHTML = '<p class="empty">Not enough data for this driving state.</p>'; return; }
      Charts.zones(box, v.profile, { lo: win.low_c, hi: win.high_c, title: NAMES[c], mirror: MIRROR[c], peaks: v.zone_peaks });
      card.querySelector(".avg").textContent = num(v.average_c, " °C");
      card.querySelector(".pk").textContent = num(v.peak_c, "°");
      card.querySelector(".iw").textContent = pct(v.share_in_window);
      card.querySelector(".io").textContent = num(v.inner_minus_outer, "°");
    });
  }
  document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => {
    view = b.dataset.view;
    document.querySelectorAll("[data-view]").forEach(x => x.setAttribute("aria-pressed", x === b));
    drawZones();
  }));

  const askForm = document.getElementById("ask-form");
  const askInput = document.getElementById("ask-input");
  const answers = document.getElementById("ask-answers");
  async function ask(question) {
    if (!question.trim()) return;
    const item = document.createElement("div");
    item.className = "qa";
    item.innerHTML = `<div class="q">${esc(question)}</div><div class="a muted"><span class="spinner"></span> Checking this session's data…</div>`;
    answers.prepend(item);
    const btn = document.getElementById("ask-btn");
    btn.disabled = true;
    try {
      const res = await fetch(`/api/reports/${encodeURIComponent(id)}/ask`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
      });
      const body = await res.json();
      const a = item.querySelector(".a");
      if (!res.ok) { a.textContent = typeof body.detail === "string" ? body.detail : "Please ask a slightly longer question."; return; }
      a.classList.toggle("muted", !body.answerable);
      a.innerHTML = esc(body.answer) + (body.cited_flag_ids || []).map(fid =>
        flagsById[fid] ? ` <a class="cite" href="#${fid}">${esc(flagsById[fid].title)}</a>` : "").join("") +
        (body.source === "llm" ? `<div class="source">Answered by ${esc(body.model)}; every number checked against this session.</div>` : "");
    } catch (e) {
      item.querySelector(".a").textContent = "Could not reach the server.";
    } finally {
      btn.disabled = false;
    }
  }
  askForm.addEventListener("submit", ev => { ev.preventDefault(); ask(askInput.value); askInput.value = ""; });
  document.querySelectorAll(".chip").forEach(ch => ch.addEventListener("click", () => ask(ch.textContent)));

  const laps = S.laps.filter(l => l.valid);
  function drawLaps() {
    Charts.lines(document.getElementById("lap-temp"),
      CORNERS.map(c => ({ label: NAMES[c], short: c, color: SERIES[c], points: laps.map(l => [l.lap, l.tyre_avg_c[c]]) })),
      { unit: " °C", band: [win.low_c, win.high_c] });
    if (hasPressure) {
      Charts.lines(document.getElementById("lap-pressure"),
        CORNERS.filter(c => S.tyres[c].pressure_psi).map(c => ({ label: NAMES[c], short: c, color: SERIES[c],
          points: laps.map(l => [l.lap, (l.pressure_psi || {})[c] ?? null]) })),
        { unit: " psi", height: 180 });
    }
    Charts.lines(document.getElementById("lap-time"),
      [{ label: "Lap time", color: "var(--series-1)", points: laps.filter(l => !l.slow).map(l => [l.lap, l.time_s]) }],
      { fmt: v => lap(v), height: 180 });
  }
  document.getElementById("lap-table").innerHTML = `<table class="data">
    <thead><tr><th>Lap</th><th>Time</th><th>Type</th><th>Brake g</th><th>Corner g</th>${CORNERS.map(c => `<th>${c} °C</th>`).join("")}
      ${hasPressure ? CORNERS.map(c => `<th>${c} psi</th>`).join("") : ""}</tr></thead>
    <tbody>${S.laps.map(l => `<tr><td>${l.lap}</td><td>${lap(l.time_s)}</td>
      <td>${!l.valid ? "glitch" : l.slow ? "slow/pit" : l.warmup ? "warm-up" : "flying"}</td>
      <td>${l.braking_g ?? "–"}</td><td>${l.cornering_g ?? "–"}</td>
      ${CORNERS.map(c => `<td>${num(l.tyre_avg_c[c])}</td>`).join("")}
      ${hasPressure ? CORNERS.map(c => `<td>${num((l.pressure_psi || {})[c])}</td>`).join("") : ""}</tr>`).join("")}</tbody></table>`;
  document.querySelectorAll("[data-lapview]").forEach(b => b.addEventListener("click", () => {
    const table = b.dataset.lapview === "table";
    document.getElementById("lap-table").hidden = !table;
    document.getElementById("lap-charts").hidden = table;
    document.querySelectorAll("[data-lapview]").forEach(x => x.setAttribute("aria-pressed", x === b));
  }));

  document.getElementById("delete").addEventListener("click", async () => {
    if (!confirm("Delete this report? This cannot be undone.")) return;
    await fetch(`/api/reports/${encodeURIComponent(id)}`, { method: "DELETE" });
    TD.forgetReport(id);
    location.href = "/";
  });

  if (sheet) Charts.setup(document.getElementById("setup-car"), sheet);
  Charts.car(document.getElementById("car"), S.tyres, {
    lo: win.low_c, hi: win.high_c,
    onSelect: c => document.getElementById(`tyre-${c}`).scrollIntoView({ behavior: "smooth", block: "center" }),
  });
  document.getElementById("print").addEventListener("click", () => window.print());
  // Closed <details> don't print their content, so open them for the PDF and restore after.
  let closed = [];
  addEventListener("beforeprint", () => {
    closed = [...document.querySelectorAll("details:not([open])")];
    closed.forEach(d => { d.open = true; });
  });
  addEventListener("afterprint", () => closed.forEach(d => { d.open = false; }));
  let resizeTimer;
  addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(drawLaps, 150); });

  drawZones();
  drawLaps();
  if (N.source === "pending") waitForNarrative();
})();
