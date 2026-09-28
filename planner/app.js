import { PLANNER_CONFIG } from "./config.js";
import { decryptCloudBlob } from "./crypto.js";

const STORAGE_KEY = "rici_planner_v1";
const SECRET_KEY = "rici_planner_secrets_v1";
const CATEGORY_LABEL = { life: "生活", work: "工作" };

const state = {
  tasks: [],
  holidayMap: new Map(),
  filter: "all",
  view: "list",
  month: startOfMonth(new Date()),
  selectedDate: formatDate(new Date()),
  timezone: "Asia/Shanghai",
  cloudUpdatedAt: "",
  passphrase: "",
  ntfyTopic: "",
};

const els = {
  unlockView: document.getElementById("unlockView"),
  appRoot: document.getElementById("appRoot"),
  passInput: document.getElementById("passInput"),
  ntfyInput: document.getElementById("ntfyInput"),
  unlockBtn: document.getElementById("unlockBtn"),
  unlockError: document.getElementById("unlockError"),
  syncBar: document.getElementById("syncBar"),
  listView: document.getElementById("listView"),
  calendarView: document.getElementById("calendarView"),
  taskList: document.getElementById("taskList"),
  upcomingBox: document.getElementById("upcomingBox"),
  calendarGrid: document.getElementById("calendarGrid"),
  monthLabel: document.getElementById("monthLabel"),
  dayDetail: document.getElementById("dayDetail"),
  dialog: document.getElementById("taskDialog"),
  form: document.getElementById("taskForm"),
  dialogTitle: document.getElementById("dialogTitle"),
  editId: document.getElementById("editId"),
  titleInput: document.getElementById("titleInput"),
  categoryInput: document.getElementById("categoryInput"),
  dateInput: document.getElementById("dateInput"),
  timeInput: document.getElementById("timeInput"),
  remindCheck: document.getElementById("remindCheck"),
  remindWrap: document.getElementById("remindWrap"),
  remindInput: document.getElementById("remindInput"),
  notesInput: document.getElementById("notesInput"),
  deleteBtn: document.getElementById("deleteBtn"),
};

boot();

async function boot() {
  bindUi();
  const saved = loadSecrets();
  if (saved?.passphrase) {
    els.passInput.value = saved.passphrase;
    els.ntfyInput.value = saved.ntfyTopic || "";
    await tryUnlock(saved.passphrase, saved.ntfyTopic || "");
  }
}

function bindUi() {
  els.unlockBtn.addEventListener("click", () => {
    tryUnlock(els.passInput.value.trim(), els.ntfyInput.value.trim());
  });
  els.passInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") els.unlockBtn.click();
  });

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view;
      document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("is-active", b === btn));
      els.listView.classList.toggle("is-active", state.view === "list");
      els.calendarView.classList.toggle("is-active", state.view === "calendar");
      render();
    });
  });

  document.querySelectorAll(".chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.filter = btn.dataset.filter;
      document.querySelectorAll(".chip").forEach((b) => b.classList.toggle("is-active", b === btn));
      renderList();
    });
  });

  document.getElementById("prevMonthBtn").addEventListener("click", () => {
    state.month = new Date(state.month.getFullYear(), state.month.getMonth() - 1, 1);
    renderCalendar();
  });
  document.getElementById("nextMonthBtn").addEventListener("click", () => {
    state.month = new Date(state.month.getFullYear(), state.month.getMonth() + 1, 1);
    renderCalendar();
  });

  document.getElementById("addOpenBtn").addEventListener("click", () => openDialog());
  document.getElementById("dialogCloseBtn").addEventListener("click", () => els.dialog.close());
  document.getElementById("exportIcsBtn").addEventListener("click", exportIcs);
  document.getElementById("refreshBtn").addEventListener("click", async () => {
    try {
      await loadCloud(state.passphrase);
      render();
      flashSync("已从云端刷新");
    } catch (err) {
      flashSync(`刷新失败：${err.message}`, true);
    }
  });

  els.remindCheck.addEventListener("change", () => {
    els.remindWrap.classList.toggle("is-hidden", !els.remindCheck.checked);
    if (els.remindCheck.checked && !els.remindInput.value) {
      els.remindInput.value = defaultRemindLocal(els.dateInput.value, els.timeInput.value);
    }
  });
  els.dateInput.addEventListener("change", syncRemindFromDateTime);
  els.timeInput.addEventListener("change", syncRemindFromDateTime);

  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    saveFromForm();
    els.dialog.close();
  });

  els.deleteBtn.addEventListener("click", () => {
    const id = els.editId.value;
    if (!id) return;
    if (!confirm("确定删除这条事项？")) return;
    state.tasks = state.tasks.filter((t) => t.id !== id);
    persistLocal();
    els.dialog.close();
    render();
  });
}

async function tryUnlock(passphrase, ntfyTopic) {
  els.unlockError.hidden = true;
  if (!passphrase) {
    showUnlockError("请输入口令");
    return;
  }
  try {
    await loadHolidays();
    await loadCloud(passphrase);
    state.passphrase = passphrase;
    state.ntfyTopic = ntfyTopic;
    saveSecrets({ passphrase, ntfyTopic });
    els.unlockView.classList.add("is-hidden");
    els.appRoot.classList.remove("is-hidden");
    render();
    flashSync(ntfyTopic ? `已解锁 · 推送主题 ${ntfyTopic}` : "已解锁 · 尚未设置推送主题");
  } catch (err) {
    showUnlockError(err.message || "解锁失败");
  }
}

function showUnlockError(msg) {
  els.unlockError.hidden = false;
  els.unlockError.textContent = msg;
}

async function loadHolidays() {
  const payload = await loadJson("./data/holidays.json");
  state.holidayMap = new Map();
  if (!payload?.years) return;
  for (const year of Object.values(payload.years)) {
    for (const item of [...(year.holidays || []), ...(year.workdays || [])]) {
      state.holidayMap.set(item.date, item);
    }
  }
}

async function loadCloud(passphrase) {
  const cacheBust = `./data/tasks.cloud.json?t=${Date.now()}`;
  const url = PLANNER_CONFIG.cloudUrl.includes("?")
    ? PLANNER_CONFIG.cloudUrl
    : cacheBust;
  const blob = await loadJson(url);
  if (!blob) throw new Error("无法读取云端清单，请检查网络或稍后重试");
  const payload = await decryptCloudBlob(blob, passphrase);
  state.timezone = payload.timezone || "Asia/Shanghai";
  state.cloudUpdatedAt = payload.updatedAt || "";
  const cloudTasks = (payload.items || []).map(normalizeTask);

  // 合并本机未同步的本地改动（按 id，本机 updated 字段没有则以本机 done/title 覆盖展示）
  const local = loadLocal();
  const map = new Map(cloudTasks.map((t) => [t.id, t]));
  for (const t of local?.items || []) {
    if (!map.has(t.id)) map.set(t.id, normalizeTask(t));
  }
  // 对本机有、云端也有的：保留本机的 done 状态（方便手机勾选）
  for (const t of local?.items || []) {
    const cur = map.get(t.id);
    if (cur && t.done !== cur.done) cur.done = t.done;
  }
  state.tasks = [...map.values()].sort(sortTasks);
  persistLocal();
}

async function loadJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`读取失败 (${res.status})`);
  return res.json();
}

function normalizeTask(raw) {
  return {
    id: raw.id || uid(),
    title: String(raw.title || "").trim(),
    category: raw.category === "work" ? "work" : "life",
    date: raw.date || null,
    time: raw.time || null,
    remindAt: raw.remindAt || null,
    notes: raw.notes || "",
    done: Boolean(raw.done),
    createdAt: raw.createdAt || nowIso(),
  };
}

function persistLocal() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      timezone: state.timezone,
      updatedAt: nowIso(),
      cloudUpdatedAt: state.cloudUpdatedAt,
      items: state.tasks,
    })
  );
}

function loadLocal() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  } catch {
    return null;
  }
}

function saveSecrets(secrets) {
  localStorage.setItem(SECRET_KEY, JSON.stringify(secrets));
}

function loadSecrets() {
  try {
    return JSON.parse(localStorage.getItem(SECRET_KEY) || "null");
  } catch {
    return null;
  }
}

function flashSync(text, isError = false) {
  els.syncBar.textContent = text;
  els.syncBar.classList.toggle("is-error", isError);
}

function render() {
  const ntfy = state.ntfyTopic
    ? `推送：ntfy.sh/${state.ntfyTopic}`
    : "未设置推送主题";
  flashSync(`云端更新：${state.cloudUpdatedAt || "未知"} · ${ntfy} · 共 ${state.tasks.length} 项`);
  if (state.view === "list") renderList();
  else renderCalendar();
}

function filteredTasks() {
  return state.tasks.filter((t) => {
    if (state.filter === "life") return t.category === "life";
    if (state.filter === "work") return t.category === "work";
    if (state.filter === "open") return !t.done;
    return true;
  });
}

function renderList() {
  const upcoming = state.tasks
    .filter((t) => !t.done && t.date)
    .sort(sortTasks)
    .slice(0, 3);

  els.upcomingBox.innerHTML = upcoming.length
    ? `<div class="upcoming-card"><h3>即将到来</h3><ul>${upcoming
        .map(
          (t) =>
            `<li><strong>${escapeHtml(t.title)}</strong> · ${formatWhen(t)} · ${CATEGORY_LABEL[t.category]}</li>`
        )
        .join("")}</ul></div>`
    : "";

  const items = filteredTasks().sort(sortTasks);
  if (!items.length) {
    els.taskList.innerHTML =
      `<div class="empty">还没有事项。<br />直接在对话里告诉我，或点右上角「添加」。</div>`;
    return;
  }

  els.taskList.innerHTML = items
    .map(
      (t) => `
      <article class="task-item ${t.done ? "is-done" : ""}" data-id="${t.id}">
        <input class="task-check" type="checkbox" ${t.done ? "checked" : ""} aria-label="完成" />
        <div>
          <p class="task-title">${escapeHtml(t.title)}</p>
          <p class="task-meta">
            <span class="badge ${t.category}">${CATEGORY_LABEL[t.category]}</span>
            ${escapeHtml(formatWhen(t))}
            ${t.remindAt ? ` · 提醒 ${escapeHtml(formatDateTime(t.remindAt))}` : ""}
            ${t.notes ? `<br />${escapeHtml(t.notes)}` : ""}
          </p>
        </div>
      </article>`
    )
    .join("");

  els.taskList.querySelectorAll(".task-item").forEach((node) => {
    const id = node.dataset.id;
    node.querySelector(".task-check").addEventListener("click", (e) => {
      e.stopPropagation();
      const task = state.tasks.find((t) => t.id === id);
      if (!task) return;
      task.done = !task.done;
      persistLocal();
      render();
    });
    node.addEventListener("click", () => openDialog(id));
  });
}

function renderCalendar() {
  const year = state.month.getFullYear();
  const month = state.month.getMonth();
  els.monthLabel.textContent = `${year}年${month + 1}月`;

  const first = new Date(year, month, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const gridStart = new Date(year, month, 1 - startOffset);
  const cells = [];

  for (let i = 0; i < 42; i += 1) {
    const d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
    const key = formatDate(d);
    const meta = state.holidayMap.get(key);
    const dayTasks = state.tasks.filter((t) => t.date === key && !t.done);
    const inMonth = d.getMonth() === month;
    const classes = [
      "day-cell",
      inMonth ? "" : "is-muted",
      key === formatDate(new Date()) ? "is-today" : "",
      key === state.selectedDate ? "is-selected" : "",
      meta?.type === "holiday" ? "is-holiday" : "",
      meta?.type === "workday" ? "is-workday" : "",
    ]
      .filter(Boolean)
      .join(" ");

    cells.push(`
      <button type="button" class="${classes}" data-date="${key}">
        <span class="day-num">${d.getDate()}</span>
        ${meta ? `<span class="day-flag">${escapeHtml(shortHolidayName(meta))}</span>` : ""}
        <span class="day-dots">${dayTasks
          .slice(0, 3)
          .map((t) => `<i class="${t.category}"></i>`)
          .join("")}</span>
      </button>`);
  }

  els.calendarGrid.innerHTML = cells.join("");
  els.calendarGrid.querySelectorAll(".day-cell").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedDate = btn.dataset.date;
      renderCalendar();
    });
  });
  renderDayDetail();
}

function renderDayDetail() {
  const key = state.selectedDate;
  const meta = state.holidayMap.get(key);
  const dayTasks = state.tasks.filter((t) => t.date === key).sort(sortTasks);
  const holidayLine = meta
    ? meta.type === "holiday"
      ? `放假：${meta.name}`
      : `调休上班：${meta.name}`
    : "工作日 / 周末（无法定安排）";

  els.dayDetail.innerHTML = `
    <h3>${key} · ${holidayLine}</h3>
    ${
      dayTasks.length
        ? `<ul>${dayTasks
            .map(
              (t) =>
                `<li><button type="button" class="linkish" data-id="${t.id}"><strong>${escapeHtml(t.title)}</strong> · ${CATEGORY_LABEL[t.category]}${t.done ? "（已完成）" : ""}</button></li>`
            )
            .join("")}</ul>`
        : "<p class='task-meta'>这一天还没有事项。</p>"
    }
    <p style="margin:12px 0 0">
      <button type="button" class="ghost-btn" id="addForDayBtn">为这天添加</button>
    </p>`;

  els.dayDetail.querySelectorAll("[data-id]").forEach((btn) => {
    btn.addEventListener("click", () => openDialog(btn.dataset.id));
  });
  document.getElementById("addForDayBtn").addEventListener("click", () => openDialog(null, key));
}

function openDialog(id = null, presetDate = null) {
  const task = id ? state.tasks.find((t) => t.id === id) : null;
  els.dialogTitle.textContent = task ? "编辑事项" : "添加事项";
  els.editId.value = task?.id || "";
  els.titleInput.value = task?.title || "";
  els.categoryInput.value = task?.category || "life";
  els.dateInput.value = task?.date || presetDate || "";
  els.timeInput.value = task?.time || "";
  els.notesInput.value = task?.notes || "";
  const hasRemind = Boolean(task?.remindAt);
  els.remindCheck.checked = hasRemind;
  els.remindWrap.classList.toggle("is-hidden", !hasRemind);
  els.remindInput.value = task?.remindAt ? toLocalInput(task.remindAt) : "";
  els.deleteBtn.classList.toggle("is-hidden", !task);
  els.dialog.showModal();
  els.titleInput.focus();
}

function saveFromForm() {
  const id = els.editId.value || uid();
  const existing = state.tasks.find((t) => t.id === id);
  const date = els.dateInput.value || null;
  const time = els.timeInput.value || null;
  let remindAt = null;
  if (els.remindCheck.checked) {
    remindAt = els.remindInput.value
      ? fromLocalInput(els.remindInput.value)
      : date
        ? fromLocalInput(defaultRemindLocal(date, time))
        : null;
  }

  const next = {
    id,
    title: els.titleInput.value.trim(),
    category: els.categoryInput.value === "work" ? "work" : "life",
    date,
    time,
    remindAt,
    notes: els.notesInput.value.trim(),
    done: existing?.done || false,
    createdAt: existing?.createdAt || nowIso(),
  };
  if (!next.title) return;
  if (existing) Object.assign(existing, next);
  else state.tasks.push(next);
  state.tasks.sort(sortTasks);
  persistLocal();
  render();
}

function syncRemindFromDateTime() {
  if (!els.remindCheck.checked || !els.dateInput.value) return;
  els.remindInput.value = defaultRemindLocal(els.dateInput.value, els.timeInput.value);
}

function defaultRemindLocal(date, time) {
  if (!date) return "";
  return time ? `${date}T${time}` : `${date}T09:00`;
}

function exportIcs() {
  const events = state.tasks.filter((t) => !t.done && (t.remindAt || t.date));
  if (!events.length) {
    alert("没有可导出的未完成事项。");
    return;
  }

  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Rici Planner//CN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
  ];

  for (const t of events) {
    const stamp = icsStamp(new Date());
    let dtStart;
    let dtEnd;
    let alarmTrigger = "-PT30M";

    if (t.remindAt) {
      const start = new Date(t.remindAt);
      const end = new Date(start.getTime() + 30 * 60 * 1000);
      dtStart = `DTSTART:${icsStamp(start)}`;
      dtEnd = `DTEND:${icsStamp(end)}`;
      alarmTrigger = "PT0S";
    } else if (t.date && t.time) {
      const start = new Date(`${t.date}T${t.time}:00+08:00`);
      const end = new Date(start.getTime() + 60 * 60 * 1000);
      dtStart = `DTSTART:${icsStamp(start)}`;
      dtEnd = `DTEND:${icsStamp(end)}`;
    } else {
      const day = t.date.replaceAll("-", "");
      dtStart = `DTSTART;VALUE=DATE:${day}`;
      dtEnd = `DTEND;VALUE=DATE:${addDaysYmd(t.date, 1).replaceAll("-", "")}`;
    }

    lines.push(
      "BEGIN:VEVENT",
      `UID:${t.id}@rici-planner`,
      `DTSTAMP:${stamp}`,
      dtStart,
      dtEnd,
      `SUMMARY:${icsEscape(`[${CATEGORY_LABEL[t.category]}] ${t.title}`)}`,
      t.notes ? `DESCRIPTION:${icsEscape(t.notes)}` : "DESCRIPTION:",
      "BEGIN:VALARM",
      "ACTION:DISPLAY",
      `DESCRIPTION:${icsEscape(t.title)}`,
      `TRIGGER:${alarmTrigger}`,
      "END:VALARM",
      "END:VEVENT"
    );
  }

  lines.push("END:VCALENDAR");
  const blob = new Blob([lines.join("\r\n")], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `rici-reminders-${formatDate(new Date())}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}

function sortTasks(a, b) {
  if (a.done !== b.done) return a.done ? 1 : -1;
  const ad = a.date || "9999-99-99";
  const bd = b.date || "9999-99-99";
  if (ad !== bd) return ad.localeCompare(bd);
  const at = a.time || "99:99";
  const bt = b.time || "99:99";
  if (at !== bt) return at.localeCompare(bt);
  return (a.createdAt || "").localeCompare(b.createdAt || "");
}

function formatWhen(t) {
  if (!t.date) return "未定日期";
  return t.time ? `${t.date} ${t.time}` : t.date;
}

function formatDateTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${hh}:${mm}`;
}

function shortHolidayName(meta) {
  if (meta.type === "workday") return "班";
  const name = meta.name || "假";
  return name.length > 2 ? name.slice(0, 2) : name;
}

function startOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function formatDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDaysYmd(ymd, days) {
  const [y, m, d] = ymd.split("-").map(Number);
  return formatDate(new Date(y, m - 1, d + days));
}

function nowIso() {
  return new Date().toISOString();
}

function uid() {
  return `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function toLocalInput(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day}T${hh}:${mm}`;
}

function fromLocalInput(local) {
  return `${local}:00+08:00`;
}

function icsStamp(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  const ss = String(date.getUTCSeconds()).padStart(2, "0");
  return `${y}${m}${d}T${hh}${mm}${ss}Z`;
}

function icsEscape(text) {
  return String(text)
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\n/g, "\\n");
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const style = document.createElement("style");
style.textContent = `.linkish{border:0;background:none;padding:0;color:inherit;cursor:pointer;text-align:left;font:inherit}.linkish:hover{color:var(--sea-mid)}`;
document.head.appendChild(style);
