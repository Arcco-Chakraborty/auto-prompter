async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}

function fmt(dt) { return dt ? dt.replace("T", " ") : "—"; }

async function loadSessions() {
  const { data } = await fetchJSON("/api/sessions");
  const select = document.querySelector("select[name=session]");
  const list = document.getElementById("sessions-list");
  select.innerHTML = "";
  list.innerHTML = "";
  data.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = JSON.stringify({ id: s.session_id, folder: s.cwd });
    opt.textContent = `${s.label}  —  ${s.cwd}`;
    select.appendChild(opt);

    const li = document.createElement("li");
    li.innerHTML = `<strong>${s.label}</strong><br><span class="muted">${s.cwd} · ${s.session_id}</span>`;
    list.appendChild(li);
  });
}

async function loadJobs() {
  const { data } = await fetchJSON("/api/jobs");
  const tbody = document.querySelector("#jobs-table tbody");
  tbody.innerHTML = "";
  data.forEach((j) => {
    const tr = document.createElement("tr");
    const target = j.target.type === "new"
      ? `new · ${j.target.folder || ""}`
      : `resume · ${j.target.session_id}`;
    tr.innerHTML = `
      <td>${(j.prompt || "").slice(0, 60)}</td>
      <td>${target}</td>
      <td>${fmt(j.next_run_at)}</td>
      <td class="status-${j.status}">${j.enabled ? j.status : "disabled"}</td>
      <td>${fmt(j.last_run_at)}</td>
      <td>
        <button data-act="toggle" data-id="${j.id}">${j.enabled ? "Disable" : "Enable"}</button>
        <button data-act="log" data-id="${j.id}">Log</button>
        <button data-act="delete" data-id="${j.id}">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  });
}

document.querySelector("#jobs-table").addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const { act, id } = btn.dataset;
  if (act === "delete") await fetchJSON(`/api/jobs/${id}`, { method: "DELETE" });
  else if (act === "toggle") await fetchJSON(`/api/jobs/${id}/toggle`, { method: "POST" });
  else if (act === "log") {
    const { data } = await fetchJSON(`/api/jobs/${id}/log`);
    alert(data.log || data.error || "no log");
    return;
  }
  loadJobs();
});

document.getElementById("refresh-sessions").addEventListener("click", loadSessions);

document.getElementById("cron-preset").addEventListener("change", (e) => {
  if (e.target.value) document.querySelector("input[name=cron]").value = e.target.value;
});

document.getElementById("job-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const errEl = document.getElementById("form-error");
  errEl.textContent = "";

  const targetType = f.target_type.value;
  let target;
  if (targetType === "existing") {
    const sel = f.session.value;
    if (!sel) { errEl.textContent = "Pick an existing chat or refresh the list."; return; }
    const { id, folder } = JSON.parse(sel);
    target = { type: "existing", session_id: id, session_folder: folder };
  } else {
    target = { type: "new", folder: f.folder.value.trim() };
  }

  const schedType = f.sched_type.value;
  const schedule = schedType === "once"
    ? { type: "once", run_at: f.run_at.value }
    : { type: "recurring", cron: f.cron.value.trim() };

  const { ok, data } = await fetchJSON("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: f.prompt.value, target, schedule }),
  });
  if (!ok) { errEl.textContent = data.error || "Failed to schedule."; return; }
  f.reset();
  loadJobs();
});

loadSessions();
loadJobs();
setInterval(loadJobs, 10000);
