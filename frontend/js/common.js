(function () {
  try {
    const saved = localStorage.getItem("theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch (e) {}
})();

window.TD = {
  esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },
  lap(sec) {
    if (sec == null) return "–";
    const m = Math.floor(sec / 60), s = (sec - m * 60).toFixed(3).padStart(6, "0");
    return `${m}:${s}`;
  },
  pct(x) { return x == null ? "–" : `${Math.round(x * 100)}%`; },
  num(x, unit = "") { return x == null ? "–" : `${Number.isInteger(x) ? x.toFixed(1) : x}${unit}`; },
  myReports() {
    try { return JSON.parse(localStorage.getItem("myReports") || "[]"); } catch (e) { return []; }
  },
  rememberReport(id) {
    try { localStorage.setItem("myReports", JSON.stringify([id, ...TD.myReports().filter(x => x !== id)].slice(0, 100))); } catch (e) {}
  },
  forgetReport(id) {
    try { localStorage.setItem("myReports", JSON.stringify(TD.myReports().filter(x => x !== id))); } catch (e) {}
  },
  NAMES: { LF: "Left front", RF: "Right front", LR: "Left rear", RR: "Right rear" },
  initTheme() {
    const btn = document.getElementById("theme-btn");
    if (!btn) return;
    const current = () => document.documentElement.dataset.theme ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const label = () => { btn.textContent = current() === "dark" ? "Light mode" : "Dark mode"; };
    label();
    btn.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      label();
      document.dispatchEvent(new Event("themechange"));
    });
  },
  async llmStatus() {
    const pill = document.getElementById("llm-status");
    if (!pill) return;
    try {
      const s = await (await fetch("/api/status")).json();
      pill.textContent = s.llm_enabled ? `AI narrative · ${s.providers.join(" → ")}` : "AI off · template narrative";
      pill.title = s.llm_enabled ? "Narratives are written by an LLM and fact-checked against the rule engine."
        : "Add GEMINI_API_KEY or OPENROUTER_API_KEY to the .env file to enable AI-written narratives.";
    } catch (e) { pill.textContent = "Server offline"; }
  },
};
document.addEventListener("DOMContentLoaded", () => { TD.initTheme(); TD.llmStatus(); });
