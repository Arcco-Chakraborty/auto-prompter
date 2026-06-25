async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}

function fmt(dt) {
  if (!dt) return "—";
  const parsed = new Date(dt);
  return Number.isNaN(parsed.getTime())
    ? dt.replace("T", " ")
    : parsed.toLocaleString();
}

function fmtEpoch(secs) {
  return secs ? new Date(secs * 1000).toLocaleString() : "—";
}

const sessionsById = new Map();

function selectedSession() {
  const id = document.querySelector("select[name=session]").value;
  return sessionsById.get(id);
}

function updateSessionSettingsPreview() {
  const preview = document.getElementById("session-settings-preview");
  if (!preview) return;
  const session = selectedSession();
  if (!session) {
    preview.textContent = "Select an existing chat to detect its permission mode and model.";
    return;
  }
  const settings = session.settings || {};
  const detected = [];
  if (settings.permission_mode) detected.push(`permission: ${settings.permission_mode}`);
  if (settings.model) detected.push(`model: ${settings.model}`);
  preview.textContent = detected.length
    ? `Detected from this chat: ${detected.join(" · ")}`
    : "This chat does not contain reusable permission or model metadata.";
}

function applySelectedSessionSettings() {
  const session = selectedSession();
  updateSessionSettingsPreview();
  if (!session) return;
  const settings = session.settings || {};
  const form = document.getElementById("job-form");
  const permissionMode = form.elements.namedItem("permission_mode");
  const model = form.elements.namedItem("model");
  if (permissionMode) permissionMode.value = settings.permission_mode || "";
  if (model) model.value = settings.model || "";
}

async function loadSessions() {
  const { ok, data } = await fetchJSON("/api/sessions");
  const select = document.querySelector("select[name=session]");
  const list = document.getElementById("sessions-list");
  select.replaceChildren();
  list.replaceChildren();
  sessionsById.clear();
  if (!ok || !Array.isArray(data)) {
    updateSessionSettingsPreview();
    return;
  }
  data.forEach((s) => {
    sessionsById.set(s.session_id, s);
    const when = fmtEpoch(s.last_used);

    const opt = document.createElement("option");
    opt.value = s.session_id;
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
  updateSessionSettingsPreview();
  const form = document.getElementById("job-form");
  const inherit = form.elements.namedItem("inherit_session_settings");
  if (inherit?.checked &&
      form.target_type.value === "existing") {
    applySelectedSessionSettings();
  }
}

async function loadJobs() {
  const { ok, data } = await fetchJSON("/api/jobs");
  const tbody = document.querySelector("#jobs-table tbody");
  tbody.replaceChildren();
  if (!ok || !Array.isArray(data)) return;
  data.forEach((j) => {
    const tr = document.createElement("tr");
    const target = j.target.type === "new"
      ? `new · ${j.target.folder || ""}`
      : `resume · ${j.target.session_id}`;
    const values = [
      (j.prompt || "").slice(0, 60),
      target,
      fmt(j.next_run_at),
      j.enabled ? j.status : "disabled",
      fmt(j.last_run_at),
    ];
    values.forEach((value, index) => {
      const td = document.createElement("td");
      td.textContent = value;
      if (index === 3) td.className = `status-${j.status}`;
      tr.appendChild(td);
    });
    const actions = document.createElement("td");
    [
      ["toggle", j.enabled ? "Disable" : "Enable"],
      ["log", "Log"],
      ["delete", "Delete"],
    ].forEach(([act, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.act = act;
      button.dataset.id = j.id;
      button.textContent = label;
      actions.appendChild(button);
    });
    tr.appendChild(actions);
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
document.querySelector("select[name=session]").addEventListener("change", () => {
  updateSessionSettingsPreview();
  const form = document.getElementById("job-form");
  const inherit = form.elements.namedItem("inherit_session_settings");
  if (inherit?.checked) applySelectedSessionSettings();
});
document.getElementById("apply-session-settings")
  ?.addEventListener("click", applySelectedSessionSettings);
document.querySelectorAll("input[name=target_type]").forEach((radio) => {
  radio.addEventListener("change", () => {
    const form = document.getElementById("job-form");
    const inherit = form.elements.namedItem("inherit_session_settings");
    if (radio.value === "existing" && radio.checked &&
        inherit?.checked) {
      applySelectedSessionSettings();
    }
  });
});

document.getElementById("cron-preset").addEventListener("change", (e) => {
  if (e.target.value) document.querySelector("input[name=cron]").value = e.target.value;
});

// --- Folder browser ---
let browserPath = null;

function closeBrowser() {
  document.getElementById("browser").hidden = true;
}

async function openBrowser(path) {
  const { data } = await fetchJSON(`/api/browse?path=${encodeURIComponent(path || "")}`);
  browserPath = data.path;
  document.getElementById("browser-path").textContent = data.path;

  // Render drive shortcuts
  const drivesEl = document.getElementById("browser-drives");
  drivesEl.replaceChildren();
  if (data.drives && data.drives.length) {
    data.drives.forEach((d) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "drive-chip";
      chip.textContent = d.name;
      chip.dataset.path = d.path;
      // Highlight current drive
      if (data.path.toUpperCase().startsWith(d.path.toUpperCase().replace(/\\$/, ""))) {
        chip.classList.add("active");
      }
      chip.addEventListener("click", () => openBrowser(d.path));
      drivesEl.appendChild(chip);
    });
  }

  const ul = document.getElementById("browser-list");
  ul.replaceChildren();
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
  closeBrowser();
});

document.getElementById("browser-cancel").addEventListener("click", closeBrowser);
document.getElementById("browser-close").addEventListener("click", closeBrowser);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeBrowser();
});

document.getElementById("job-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const errEl = document.getElementById("form-error");
  errEl.textContent = "";

  const targetType = f.target_type.value;
  let target;
  if (targetType === "existing") {
    const session = selectedSession();
    if (!session) { errEl.textContent = "Pick an existing chat or refresh the list."; return; }
    target = {
      type: "existing",
      session_id: session.session_id,
      session_folder: session.cwd,
    };
  } else {
    target = { type: "new", folder: f.folder.value.trim() };
  }

  // Gather CLI settings
  const settings = { timeout_seconds: Number(f.timeout_seconds.value) };
  const permissionMode = f.permission_mode.value;
  if (permissionMode) settings.permission_mode = permissionMode;
  if (f.verbose.checked) settings.verbose = true;
  const model = f.model.value.trim();
  if (model) settings.model = model;
  const extraFlags = f.extra_flags.value.trim();
  if (extraFlags) settings.extra_flags = extraFlags;

  const schedType = f.sched_type.value;
  let schedule;
  if (schedType === "once") {
    const runAt = new Date(f.run_at.value);
    if (Number.isNaN(runAt.getTime())) {
      errEl.textContent = "Choose a valid future date and time.";
      return;
    }
    schedule = { type: "once", run_at: runAt.toISOString() };
  } else {
    schedule = {
      type: "recurring",
      cron: f.cron.value.trim(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
  }

  const { ok, data } = await fetchJSON("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: f.prompt.value, target, schedule, settings }),
  });
  if (!ok) { errEl.textContent = data.error || "Failed to schedule."; return; }
  f.reset();
  updateSessionSettingsPreview();
  loadJobs();
});

loadSessions();
loadJobs();
setInterval(loadJobs, 10000);
