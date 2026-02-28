/**
 * AntiGravity Core v1.0 — Dashboard
 */
(() => {
  "use strict";

  const API = "";
  let forecastData = [];

  // Theme
  function getTheme() { return localStorage.getItem("ag-theme") || "dark"; }
  function setTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("ag-theme", t);
  }
  setTheme(getTheme());
  function isLight() { return getTheme() === "light"; }

  const $ = (s) => document.querySelector(s);

  const el = {
    carbonCurrent: $("#carbon-current"),
    carbonMin: $("#carbon-forecast-min"),
    carbonDelta: $("#carbon-delta"),
    carbonBadge: $("#carbon-badge"),
    telemWatts: $("#telem-watts"),
    telemTemp: $("#telem-temp"),
    telemTdp: $("#telem-tdp"),
    telemVram: $("#telem-vram"),
    barWatts: $("#bar-watts"),
    barTemp: $("#bar-temp"),
    barTdp: $("#bar-tdp"),
    barVram: $("#bar-vram"),
    telemetryBadge: $("#telemetry-badge"),
    queueBody: $("#queue-body"),
    queueCount: $("#queue-count"),
    decisionLog: $("#decision-log"),
    decisionCount: $("#decision-count"),
    btnDecide: $("#btn-decide"),
    btnAddJob: $("#btn-add-job"),
    modalOverlay: $("#modal-overlay"),
    btnCancel: $("#btn-cancel-modal"),
    btnSubmit: $("#btn-submit-job"),
    canvas: $("#forecast-canvas"),
  };

  async function api(path, opts = {}) {
    try {
      const res = await fetch(API + path, {
        headers: { "Content-Type": "application/json" },
        ...opts,
      });
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // Carbon
  function updateCarbon(c) {
    if (!c) return;
    el.carbonCurrent.textContent = Math.round(c.current_intensity);
    el.carbonMin.textContent = Math.round(c.forecast_min);
    el.carbonDelta.textContent = (c.delta >= 0 ? "+" : "") + c.delta;

    const cls = c.classification;
    el.carbonBadge.textContent = cls;
    el.carbonBadge.className = "tag " + (cls === "HIGH" ? "tag-red" : cls === "LOW" ? "tag-green" : "tag-amber");
  }

  // Telemetry
  function updateTelemetry(t) {
    if (!t) return;
    el.telemWatts.textContent = Math.round(t.current_watts) + "W";
    el.telemTemp.textContent = Math.round(t.core_temp_c) + "°C";
    el.telemTdp.textContent = Math.round(t.tdp_cap_watts) + "W";
    el.telemVram.textContent = Math.round(t.vram_used_gb) + "/" + Math.round(t.vram_total_gb) + "GB";

    el.barWatts.style.width = Math.min(100, t.tdp_utilization_pct) + "%";
    el.barTemp.style.width = Math.min(100, (t.core_temp_c / 100) * 100) + "%";
    el.barTdp.style.width = Math.min(100, (t.tdp_cap_watts / 400) * 100) + "%";
    el.barVram.style.width = Math.min(100, (t.vram_used_gb / t.vram_total_gb) * 100) + "%";

    el.telemetryBadge.textContent = t.is_failsafe ? "FAILSAFE" : "MI300X";
    el.telemetryBadge.className = "tag " + (t.is_failsafe ? "tag-red" : "tag-muted");
  }

  // Queue
  function updateQueue(q) {
    if (!q) return;
    el.queueCount.textContent = q.total_jobs + " job" + (q.total_jobs !== 1 ? "s" : "");

    if (!q.jobs || q.jobs.length === 0) {
      el.queueBody.innerHTML = '<tr><td colspan="5" class="empty-state">No jobs</td></tr>';
      return;
    }

    el.queueBody.innerHTML = q.jobs.map(j => {
      const dl = new Date(j.deadline);
      const t = dl.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return `<tr>
        <td class="task-id">${esc(j.task_id)}</td>
        <td>${j.priority}</td>
        <td>${j.vram_req_gb}GB</td>
        <td>${t}</td>
        <td><span class="status-badge s-${j.status}">${j.status}</span></td>
      </tr>`;
    }).join("");
  }

  // Decisions
  function updateDecisions(history, count) {
    el.decisionCount.textContent = count;
    if (!history || history.length === 0) {
      el.decisionLog.innerHTML = '<div class="empty-state">Run a decision cycle to see results here.</div>';
      return;
    }

    el.decisionLog.innerHTML = [...history].reverse().map(d => {
      const action = d.decision?.action || "UNKNOWN";
      const taskId = d.decision?.task_id || "--";
      const ts = new Date(d.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      return `<div class="log-entry">
        <div class="log-top">
          <span class="log-action a-${action}">${action}</span>
          <span class="log-meta">${esc(taskId)} · ${ts}</span>
        </div>
        <div class="log-json">${highlight(JSON.stringify(d, null, 2))}</div>
      </div>`;
    }).join("");
  }

  // Chart
  function drawChart() {
    const c = el.canvas;
    if (!c || !forecastData.length) return;
    const ctx = c.getContext("2d");
    const rect = c.parentElement.getBoundingClientRect();
    c.width = rect.width * 2;
    c.height = rect.height * 2;
    ctx.scale(2, 2);

    const w = rect.width, h = rect.height;
    const vals = forecastData.map(r => r.intensity);
    const lo = Math.min(...vals) - 20;
    const hi = Math.max(...vals) + 20;
    const range = hi - lo || 1;
    const pad = 16;
    const uw = w - pad * 2;
    const step = vals.length > 1 ? uw / (vals.length - 1) : 0;

    ctx.clearRect(0, 0, w, h);

    // grid
    const gridColor = isLight() ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.04)";
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      const y = (h / 4) * i;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }

    // fill
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, "rgba(59,130,246,0.08)");
    grad.addColorStop(1, "rgba(59,130,246,0.0)");

    ctx.beginPath();
    ctx.moveTo(pad, h);
    vals.forEach((v, i) => {
      const x = pad + i * step;
      const y = h - ((v - lo) / range) * (h - 24) - 12;
      ctx.lineTo(x, y);
    });
    ctx.lineTo(pad + (vals.length - 1) * step, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // line
    ctx.beginPath();
    vals.forEach((v, i) => {
      const x = pad + i * step;
      const y = h - ((v - lo) / range) * (h - 24) - 12;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#3b82f6";
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.stroke();

    // dots
    vals.forEach((v, i) => {
      const x = pad + i * step;
      const y = h - ((v - lo) / range) * (h - 24) - 12;
      ctx.beginPath();
      ctx.arc(x, y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = v > 400 ? "#ef4444" : v < 100 ? "#22c55e" : "#3b82f6";
      ctx.fill();
    });

    // labels
    ctx.font = "500 9px Inter, sans-serif";
    ctx.fillStyle = isLight() ? "rgba(0,0,0,0.3)" : "rgba(255,255,255,0.25)";
    ctx.textAlign = "center";
    vals.forEach((v, i) => {
      if (i % 3 === 0 || i === vals.length - 1) {
        const x = pad + i * step;
        ctx.fillText(Math.round(v), x, h - 2);
      }
    });
  }

  // JSON highlight
  function highlight(json) {
    return json.replace(
      /("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
      m => {
        let c = "jn";
        if (/^"/.test(m)) c = /:$/.test(m) ? "jk" : "js";
        else if (/true|false/.test(m)) c = "jb";
        else if (/null/.test(m)) c = "jnull";
        return `<span class="${c}">${m}</span>`;
      }
    );
  }

  // Poll
  async function poll() {
    const data = await api("/api/status");
    if (!data) return;
    updateCarbon(data.carbon);
    updateTelemetry(data.telemetry);
    updateQueue(data.queue);

    const history = await api("/api/history");
    if (history) updateDecisions(history, data.decisions_made);
    drawChart();
  }

  async function initForecast() {
    const resp = await api("/api/carbon");
    if (resp && resp.current && resp.forecast_min) {
      const now = Date.now();
      const cur = resp.current, min = resp.forecast_min, avg = resp.forecast_avg;
      const v = [cur, cur * .92, cur * .8, avg * .85, min * 1.1, min, min * 1.2, avg * .9, avg, avg * 1.05, cur * .85, cur * .95];
      forecastData = v.map((val, i) => ({
        timestamp: new Date(now + i * 1800000).toISOString(),
        intensity: Math.round(val),
      }));
    }
  }

  // Events
  el.btnDecide.addEventListener("click", async () => {
    el.btnDecide.textContent = "Running…";
    el.btnDecide.disabled = true;
    await api("/api/decide", { method: "POST", body: "{}" });
    await poll();
    el.btnDecide.textContent = "Run Decision";
    el.btnDecide.disabled = false;
  });

  el.btnAddJob.addEventListener("click", () => el.modalOverlay.classList.add("open"));
  el.btnCancel.addEventListener("click", () => el.modalOverlay.classList.remove("open"));
  el.modalOverlay.addEventListener("click", e => { if (e.target === el.modalOverlay) el.modalOverlay.classList.remove("open"); });

  // Theme toggle
  $("#btn-theme").addEventListener("click", () => {
    setTheme(isLight() ? "dark" : "light");
    drawChart();
  });

  el.btnSubmit.addEventListener("click", async () => {
    const id = $("#job-id").value.trim();
    if (!id) return;
    const res = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({
        task_id: id,
        priority: parseInt($("#job-priority").value, 10),
        vram_req_gb: parseFloat($("#job-vram").value),
        deadline: new Date(Date.now() + parseFloat($("#job-deadline").value) * 3600000).toISOString(),
      }),
    });
    if (res?.ok) {
      el.modalOverlay.classList.remove("open");
      $("#job-id").value = "";
      await poll();
    }
  });

  window.addEventListener("resize", drawChart);

  (async () => {
    await initForecast();
    await poll();
    setInterval(poll, 3000);
  })();
})();
