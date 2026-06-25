async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}

function fmt(dt) { return dt ? dt.replace("T", " ") : "—"; }

function fmtEpoch(secs) {
  return secs ? new Date(secs * 1000).toLocaleString() : "—";
}

async function loadSessions() {
  const { data } = await fetchJSON("/api/sessions");
  const select = document.querySelector("select[name=session]");
  const list = document.getElementById("sessions-list");
  select.innerHTML = "";
  list.innerHTML = "";
  data.forEach((s) => {
    const when = fmtEpoch(s.last_used);

    const opt = document.createElement("option");
    opt.value = JSON.stringify({ id: s.session_id, folder: s.cwd });
    opt.textContent = `${s.name}  —  ${when}`;
    select.appendChild(opt);

    const li = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = s.name;
    const meta = document.createElement("span");
    meta.className = "muted";
    meta.textContent = `${when} · ${s.cwd}`;
    li.append(name, document.createElement("br"), meta);
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

// --- Folder browser ---
let browserPath = null;

async function openBrowser(path) {
  const { data } = await fetchJSON(`/api/browse?path=${encodeURIComponent(path || "")}`);
  browserPath = data.path;
  document.getElementById("browser-path").textContent = data.path;
  const ul = document.getElementById("browser-list");
  ul.innerHTML = "";
  const addRow = (label, dirPath) => {
    const li = document.createElement("li");
    li.textContent = label;
    li.dataset.path = dirPath;
    ul.appendChild(li);
  };
  if (data.parent) addRow("📁 ..", data.parent);
  data.dirs.forEach((d) => addRow("📁 " + d.name, d.path));
  if (!data.dirs.length && !data.parent) addRow("(no sub-folders)", "");
}

document.getElementById("browse-btn").addEventListener("click", () => {
  document.getElementById("browser").hidden = false;
  openBrowser(document.querySelector("input[name=folder]").value.trim());
});

document.getElementById("browser-list").addEventListener("click", (e) => {
  const li = e.target.closest("li");
  if (li && li.dataset.path) openBrowser(li.dataset.path);
});

document.getElementById("browser-select").addEventListener("click", () => {
  if (browserPath) {
    document.querySelector("input[name=folder]").value = browserPath;
    document.querySelector("input[name=target_type][value=new]").checked = true;
  }
  document.getElementById("browser").hidden = true;
});

document.getElementById("browser-cancel").addEventListener("click", () => {
  document.getElementById("browser").hidden = true;
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
