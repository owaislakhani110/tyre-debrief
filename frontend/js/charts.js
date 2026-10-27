window.Charts = (function () {
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  };
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  function tooltip(box) {
    let tip = box.querySelector(".tip");
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; box.appendChild(tip); }
    return {
      show(html, x, y) {
        tip.innerHTML = html;
        tip.style.display = "block";
        const bw = box.clientWidth, tw = tip.offsetWidth;
        tip.style.left = `${Math.min(Math.max(0, x + 12), bw - tw)}px`;
        tip.style.top = `${Math.max(0, y - tip.offsetHeight - 8)}px`;
      },
      hide() { tip.style.display = "none"; },
    };
  }

  function barPath(x, y, w, h, r = 4) {
    r = Math.min(r, w / 2, h);
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }

  function state(v, lo, hi) {
    if (v == null) return { key: "off", label: "Off tread (excluded)", color: "var(--off)" };
    if (v < lo) return { key: "cold", label: `Cold (below ${lo} °C)`, color: "var(--cold)" };
    if (v > hi) return { key: "hot", label: `Hot (above ${hi} °C)`, color: "var(--hot)" };
    return { key: "ok", label: "In working window", color: "var(--ok)" };
  }

  function zones(box, profile, { lo, hi, yMax = 110, title = "", mirror = false, peaks = null }) {
    box.innerHTML = "";
    box.classList.add("chart-box");
    const shown = mirror ? [...profile].reverse() : profile;
    const shownPeaks = peaks ? (mirror ? [...peaks].reverse() : peaks) : null;
    const W = 320, H = 150, m = { t: 10, r: 26, b: 26, l: 30 };
    const pw = W - m.l - m.r, ph = H - m.t - m.b;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
      "aria-label": `${title} zone temperatures ${mirror ? "outside to inside" : "inside to outside"}: ${shown.map(v => v ?? "excluded").join(", ")} °C` }, box);
    const defs = el("defs", {}, svg);
    const pat = el("pattern", { id: `hatch-${Math.random().toString(36).slice(2)}`, width: 6, height: 6,
      patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
    el("rect", { width: 6, height: 6, fill: "var(--surface-2)" }, pat);
    el("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "var(--off)", "stroke-width": 2 }, pat);
    const y = v => m.t + ph - (Math.min(v, yMax) / yMax) * ph;

    for (const g of [0, 50, 100]) {
      el("line", { x1: m.l, x2: W - m.r, y1: y(g), y2: y(g), class: "grid" }, svg);
      el("text", { x: m.l - 6, y: y(g) + 4, "text-anchor": "end" }, svg).textContent = g;
    }
    const slot = pw / 8, bw = slot - 2;
    const tip = tooltip(box);
    shown.forEach((v, i) => {
      const s = state(v, lo, hi);
      const x = m.l + i * slot + 1;
      const h = v == null ? ph * 0.35 : Math.max(2, (Math.min(v, yMax) / yMax) * ph);
      el("path", { d: barPath(x, m.t + ph - h, bw, h),
        fill: v == null ? `url(#${pat.id})` : s.color }, svg);
      const pk = shownPeaks ? shownPeaks[i] : null;
      if (pk != null && v != null) {
        el("line", { x1: x + 2, x2: x + bw - 2, y1: y(pk), y2: y(pk), class: "peak-mark" }, svg);
      }
      const fromInside = mirror ? 8 - i : i + 1;
      const where = fromInside === 1 ? "Inside edge" : fromInside === 8 ? "Outside edge" : `Zone ${fromInside} from inside`;
      const hit = el("rect", { x: m.l + i * slot, y: m.t, width: slot, height: ph, fill: "transparent" }, svg);
      hit.addEventListener("mousemove", ev => {
        const r = box.getBoundingClientRect();
        tip.show(`<div class="t">${where}</div>
          <div class="r"><span class="sw" style="background:${s.color}"></span>${s.label}<b>${v == null ? "–" : v + " °C"}</b></div>
          ${pk != null && v != null ? `<div class="r">Peak held 0.5 s<b>${pk} °C</b></div>` : ""}`,
          ev.clientX - r.left, ev.clientY - r.top);
      });
      hit.addEventListener("mouseleave", () => tip.hide());
    });
    for (const [v, lab] of [[lo, `${lo}°`], [hi, `${hi}°`]]) {
      el("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: "ref" }, svg);
      el("text", { x: W - m.r + 4, y: y(v) + 4 }, svg).textContent = lab;
    }
    el("text", { x: m.l, y: H - 6 }, svg).textContent = mirror ? "Outside" : "Inside";
    el("text", { x: W - m.r, y: H - 6, "text-anchor": "end" }, svg).textContent = mirror ? "Inside" : "Outside";
  }

  function tyreShape(g, x, y, w, h, shape, left) {
    const third = w / 3;
    const hot = { centre_hot: [1], edges_hot: [0, 2], inside_hot: [left ? 2 : 0], outside_hot: [left ? 0 : 2] }[shape] || [];
    for (let i = 0; i < 3; i++) {
      const fill = shape === "unknown" ? "var(--off)" : hot.includes(i) ? "var(--hot)" : "var(--ok)";
      el("rect", { x: x + i * third, y, width: third, height: h, fill, opacity: hot.includes(i) || !hot.length ? 1 : 0.55 }, g);
    }
    el("rect", { x, y, width: w, height: h, rx: 6, fill: "none", stroke: "var(--text-secondary)", "stroke-width": 1.5 }, g);
  }

  function setup(box, sheet) {
    box.innerHTML = "";
    const W = 420, H = 300, body = { x: 160, y: 14, w: 100, h: 272 };
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "setup-svg", role: "img", "aria-label": "Changes to make before the next session" }, box);
    el("rect", { x: body.x, y: body.y, width: body.w, height: body.h, rx: 40, fill: "var(--surface-2)", stroke: "var(--border)", "stroke-width": 1.5 }, svg);
    el("text", { x: W / 2, y: 44, "text-anchor": "middle", class: "lbl" }, svg).textContent = "FRONT";
    const pos = { LF: [124, 44], RF: [266, 44], LR: [124, 186], RR: [266, 186] };
    for (const [c, [x, y]] of Object.entries(pos)) {
      const cs = sheet.corners[c];
      const left = c[0] === "L";
      const g = el("g", {}, svg);
      el("line", { x1: left ? x + 30 : body.x + body.w, x2: left ? body.x : x, y1: y + 34, y2: y + 34, stroke: "var(--border)", "stroke-width": 3 }, g);
      tyreShape(g, x, y, 30, 68, cs.heat_shape.key, left);
      const tx = left ? x - 8 : x + 38, anchor = left ? "end" : "start";
      const p = cs.pressure, cam = cs.camber;
      const lines = [
        [p.change_psi > 0 ? `▲ ${p.label}` : p.change_psi < 0 ? `▼ ${p.label}` : p.flag ? "Hold pressure" : p.label,
         p.change_psi ? "chg" : "same"],
        [cam.direction ? `${cam.direction > 0 ? "More" : "Less"} camber` : "Camber OK", cam.direction ? "chg" : "same"],
        [{ centre_hot: "Hot centre", edges_hot: "Hot edges", inside_hot: "Hot inside", outside_hot: "Hot outside",
           even: "Even tread", unknown: "No data" }[cs.heat_shape.key], "shape"],
      ];
      lines.forEach(([text, cls], i) => {
        el("text", { x: tx, y: y + 18 + i * 17, "text-anchor": anchor, class: `setup-${cls}` }, g).textContent = text;
      });
    }
  }

  function lines(box, series, { unit = "", band = null, fmt = v => v, xLabel = "Lap", height = 220 } = {}) {
    box.innerHTML = "";
    box.classList.add("chart-box");
    const all = series.flatMap(s => s.points).filter(p => p[1] != null);
    if (!all.length) { box.innerHTML = '<p class="empty">Not enough lap data.</p>'; return; }
    const W = Math.max(300, Math.round(box.clientWidth || 720)), H = height, m = { t: 12, r: 64, b: 30, l: 52 };
    const pw = W - m.l - m.r, ph = H - m.t - m.b;
    const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    if (x0 === x1) { x0 -= 1; x1 += 1; }
    let y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (band) { y0 = Math.min(y0, band[0]); y1 = Math.max(y1, band[0]); }
    const raw = (y1 - y0 || 1) / 4;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const tickStep = [1, 2, 5, 10].map(k => k * mag).find(s => s >= raw);
    y0 = Math.floor(y0 / tickStep) * tickStep;
    y1 = Math.ceil(y1 / tickStep) * tickStep;
    if (y0 === y1) y1 += tickStep;
    const X = v => m.l + ((v - x0) / (x1 - x0)) * pw;
    const Y = v => m.t + ph - ((v - y0) / (y1 - y0)) * ph;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img",
      "aria-label": series.map(s => s.label).join(", ") }, box);

    for (let v = y0; v <= y1 + tickStep / 2; v += tickStep) {
      el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: "grid" }, svg);
      el("text", { x: m.l - 8, y: Y(v) + 4, "text-anchor": "end" }, svg).textContent = fmt(Math.round(v * 100) / 100);
    }
    if (band) {
      const top = Math.min(band[1], y1);
      if (band[0] < y1) {
        el("rect", { x: m.l, width: pw, y: Y(top), height: Math.max(0, Y(Math.max(band[0], y0)) - Y(top)),
          fill: "var(--ok)", opacity: 0.07 }, svg);
        el("line", { x1: m.l, x2: W - m.r, y1: Y(band[0]), y2: Y(band[0]), class: "ref" }, svg);
      }
    }
    const step = Math.max(1, Math.ceil((x1 - x0) / Math.max(3, Math.floor(pw / 48))));
    for (let v = Math.ceil(x0); v <= x1; v += step) {
      el("text", { x: X(v), y: H - 10, "text-anchor": "middle" }, svg).textContent = v;
    }

    const endLabels = [];
    for (const s of series) {
      const pts = s.points.filter(p => p[1] != null);
      if (!pts.length) continue;
      el("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${X(p[0])},${Y(p[1])}`).join(""),
        fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
      if (pts.length < 25) {
        for (const p of pts) el("circle", { cx: X(p[0]), cy: Y(p[1]), r: 4, fill: s.color, stroke: "var(--surface-1)", "stroke-width": 2 }, svg);
      }
      const last = pts[pts.length - 1];
      endLabels.push({ x: X(last[0]) + 8, y: Y(last[1]) + 4, text: s.short || s.label });
    }
    if (endLabels.length <= 4) {
      endLabels.sort((a, b) => a.y - b.y);
      for (let i = 1; i < endLabels.length; i++) {
        endLabels[i].y = Math.max(endLabels[i].y, endLabels[i - 1].y + 13);
      }
      for (const l of endLabels) {
        el("text", { x: l.x, y: l.y, style: "fill:var(--text-secondary)" }, svg).textContent = l.text;
      }
    }

    const cross = el("line", { y1: m.t, y2: m.t + ph, stroke: "var(--text-muted)", "stroke-width": 1, opacity: 0 }, svg);
    const hit = el("rect", { x: m.l, y: m.t, width: pw, height: ph, fill: "transparent" }, svg);
    const tip = tooltip(box);
    const xVals = [...new Set(all.map(p => p[0]))].sort((a, b) => a - b);
    hit.addEventListener("mousemove", ev => {
      const r = svg.getBoundingClientRect();
      const sx = ((ev.clientX - r.left) / r.width) * W;
      const xv = xVals.reduce((a, b) => Math.abs(X(b) - sx) < Math.abs(X(a) - sx) ? b : a);
      cross.setAttribute("x1", X(xv)); cross.setAttribute("x2", X(xv)); cross.setAttribute("opacity", 0.5);
      const rows = series.map(s => {
        const p = s.points.find(q => q[0] === xv);
        return p && p[1] != null ? `<div class="r"><span class="sw line" style="background:${s.color}"></span>${TD.esc(s.label)}<b>${fmt(p[1])}${unit}</b></div>` : "";
      }).join("");
      const br = box.getBoundingClientRect();
      tip.show(`<div class="t">${xLabel} ${xv}</div>${rows}`, ev.clientX - br.left, ev.clientY - br.top);
    });
    hit.addEventListener("mouseleave", () => { tip.hide(); cross.setAttribute("opacity", 0); });
  }

  function car(box, tyres, { lo, hi, onSelect }) {
    box.innerHTML = "";
    const W = 230, H = 300;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
      "aria-label": "Tyre overview: " + Object.entries(tyres).map(([c, t]) => `${c} ${t.average_c ?? "no data"} °C`).join(", ") }, box);
    el("rect", { x: 50, y: 14, width: 130, height: 272, rx: 46, fill: "var(--surface-2)", stroke: "var(--border)", "stroke-width": 1.5 }, svg);
    el("rect", { x: 70, y: 70, width: 90, height: 46, rx: 12, fill: "none", stroke: "var(--border)", "stroke-width": 1.5 }, svg);
    el("text", { x: W / 2, y: 44, "text-anchor": "middle", class: "lbl" }, svg).textContent = "FRONT";
    const pos = { LF: [14, 44], RF: [186, 44], LR: [14, 182], RR: [186, 182] };
    for (const [c, [x, y]] of Object.entries(pos)) {
      const t = tyres[c] || {};
      const s = state(t.average_c, lo, hi);
      const word = { cold: "Cold", ok: "In window", hot: "Hot", off: "No data" }[s.key];
      const g = el("a", { tabindex: 0, role: "button", "aria-label": `${c}: ${t.average_c ?? "no data"} °C, ${word}` }, svg);
      const left = c[0] === "L";
      el("line", { x1: left ? x + 30 : 180, x2: left ? 50 : x, y1: y + 32, y2: y + 32,
        stroke: "var(--border)", "stroke-width": 3 }, g);
      el("rect", { x, y, width: 30, height: 64, rx: 8, fill: s.color }, g);
      const cx = x + 15;
      el("text", { x: cx, y: y + 84, "text-anchor": "middle" }, g).textContent = t.average_c != null ? `${t.average_c}°` : "–";
      el("text", { x: cx, y: y + 99, "text-anchor": "middle", class: "lbl" }, g).textContent = word;
      if (onSelect) {
        g.addEventListener("click", () => onSelect(c));
        g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(c); } });
      }
    }
  }

  return { zones, lines, car, setup, state, css };
})();
