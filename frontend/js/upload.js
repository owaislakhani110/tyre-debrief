(function () {
  const form = document.getElementById("upload-form");
  const fileInput = document.getElementById("file");
  const drop = document.getElementById("drop");
  const fileName = document.getElementById("file-name");
  const submit = document.getElementById("submit");
  const progress = document.getElementById("progress");
  const bar = progress.querySelector("div");
  const phase = document.getElementById("phase");
  const errorBox = document.getElementById("error");

  function showFile() {
    const f = fileInput.files[0];
    fileName.textContent = f ? `${f.name} · ${(f.size / 1e6).toFixed(1)} MB` : "";
  }
  fileInput.addEventListener("change", showFile);
  ["dragenter", "dragover"].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", ev => {
    if (ev.dataTransfer.files.length) { fileInput.files = ev.dataTransfer.files; showFile(); }
  });

  function busy(text) {
    phase.innerHTML = `<span class="spinner" aria-hidden="true"></span>${TD.esc(text)}`;
  }

  function fail(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
    submit.disabled = false;
    progress.hidden = true;
    phase.textContent = "";
  }

  form.addEventListener("submit", ev => {
    ev.preventDefault();
    errorBox.hidden = true;
    const f = fileInput.files[0];
    if (!f) return fail("Choose a session CSV first.");
    if (!/\.(csv|xrk|xrz)$/i.test(f.name)) return fail("Upload the logger's .xrk file or a .csv export from Race Studio.");

    const data = new FormData(form);
    submit.disabled = true;
    progress.hidden = false;
    bar.style.width = "0";
    phase.textContent = "Uploading…";

    // XHR rather than fetch so large exports show upload progress.
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/reports");
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) bar.style.width = `${Math.round((e.loaded / e.total) * 100)}%`;
    };
    xhr.upload.onload = () => { busy("Analysing session… usually a few seconds"); bar.style.width = "100%"; };
    xhr.onerror = () => fail("Could not reach the server.");
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch (e) {}
      if (xhr.status === 200 && body.id) {
        location.href = `/report?id=${encodeURIComponent(body.id)}`;
      } else {
        fail(body.detail || `Something went wrong (HTTP ${xhr.status}).`);
      }
    };
    xhr.send(data);
  });

  async function loadHistory() {
    const list = document.getElementById("history");
    try {
      const ids = TD.myReports();
      const rows = ids.length ? await (await fetch("/api/reports/summaries", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }),
      })).json() : [];
      if (!rows.length) { list.innerHTML = '<li class="empty">No reports yet. Debriefs you create in this browser appear here.</li>'; return; }
      list.innerHTML = rows.map(r => `
        <li><a href="/report?id=${encodeURIComponent(r.id)}">
          <div class="h-title">${TD.esc(r.headline || r.filename)}</div>
          <div class="h-meta">${TD.esc([r.racer, r.track, r.session_date].filter(Boolean).join(" · "))}</div>
        </a></li>`).join("");
    } catch (e) {
      list.innerHTML = '<li class="empty">Could not load history.</li>';
    }
  }
  async function loadSamples() {
    let rows = [];
    try { rows = await (await fetch("/api/samples")).json(); } catch (e) { return; }
    if (!rows.length) return;
    const sel = document.getElementById("sample");
    const label = r => TD.esc([r.racer, r.track, (r.date || "").split(", ").slice(1).join(", ") || r.date].filter(Boolean).join(" · ") || r.name);
    const option = r => `<option value="${TD.esc(r.name)}" title="${TD.esc(r.problem || "")}">${label(r)} (${r.format}, ${r.size_mb} MB)</option>`;
    const good = rows.filter(r => !r.problem), bad = rows.filter(r => r.problem);
    sel.innerHTML = `<optgroup label="Track sessions">${good.map(option).join("")}</optgroup>` +
      (bad.length ? `<optgroup label="Can't be analysed (shows the reason)">${bad.map(option).join("")}</optgroup>` : "");
    const preferred = good.find(r => r.name.startsWith("satpractice") && r.format === "CSV" && r.size_mb > 100) || good[0];
    if (preferred) sel.value = preferred.name;
    document.getElementById("samples-card").hidden = false;
    const btn = document.getElementById("run-sample");
    btn.addEventListener("click", async () => {
      errorBox.hidden = true;
      btn.disabled = submit.disabled = true;
      busy("Analysing sample session…");
      try {
        const res = await fetch(`/api/samples/${encodeURIComponent(sel.value)}`, { method: "POST" });
        const body = await res.json();
        if (res.ok) { location.href = `/report?id=${encodeURIComponent(body.id)}`; return; }
        fail(body.detail || `Something went wrong (HTTP ${res.status}).`);
      } catch (e) { fail("Could not reach the server."); }
      btn.disabled = false;
    });
  }

  loadHistory();
  loadSamples();
})();
