// XS 量化積木腳本集 — popup 邏輯
// 資料來源：data/scripts.json（由 tools/build-index.mjs 從 repo 內的 .xs 產生）
console.log("This is a popup!");

const REPO_BLOB = "https://github.com/mmmMmmmM444/XS_Blocks/blob/main/";
const MAX_RESULTS = 300;

const $ = (id) => document.getElementById(id);
const els = {
  q: $("q"),
  cat: $("cat"),
  list: $("list"),
  status: $("status"),
  count: $("count"),
  listView: $("list-view"),
  detailView: $("detail-view"),
  back: $("back"),
  copy: $("copy"),
  detailId: $("detail-id"),
  detailName: $("detail-name"),
  detailDisplay: $("detail-display"),
  detailFreq: $("detail-freq"),
  detailLink: $("detail-link"),
  detailCode: $("detail-code"),
};

let all = [];
let results = [];
let activeIndex = -1;
let current = null;

// ---------- 載入資料 ----------
async function load() {
  try {
    const res = await fetch(chrome.runtime.getURL("data/scripts.json"));
    const data = await res.json();
    all = data.items;
    els.status.textContent = "";
    els.count.textContent = `共 ${data.count} 條腳本（${data.generated}）`;
    restoreState();
    search();
  } catch (err) {
    console.error(err);
    els.status.textContent = "載入 data/scripts.json 失敗，請先執行 node tools/build-index.mjs";
  }
}

// ---------- 搜尋 ----------
function normalize(s) {
  return (s || "").toLowerCase();
}

function search() {
  const terms = normalize(els.q.value).split(/\s+/).filter(Boolean);
  const cat = els.cat.value;
  results = [];
  for (const it of all) {
    if (cat && it.cat !== cat) continue;
    if (terms.length) {
      const hay = normalize(`${it.id} ${it.name} ${it.display} ${it.group} ${it.sub}`);
      if (!terms.every((t) => hay.includes(t))) continue;
    }
    results.push(it);
    if (results.length >= MAX_RESULTS) break;
  }
  renderList();
  saveState();
}

function renderList() {
  els.list.textContent = "";
  activeIndex = results.length ? 0 : -1;
  const frag = document.createDocumentFragment();
  results.forEach((it, i) => {
    const li = document.createElement("li");
    li.dataset.index = i;
    if (i === activeIndex) li.classList.add("active");

    const id = document.createElement("span");
    id.className = "id";
    id.textContent = it.id;

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = it.name;
    const tag = document.createElement("span");
    tag.className = `tag ${it.type}`;
    tag.textContent = it.cat.replace("腳本", "");
    name.appendChild(tag);

    const display = document.createElement("span");
    display.className = "display";
    display.textContent = it.display;
    display.title = it.display;

    li.append(id, name, display);
    frag.appendChild(li);
  });
  els.list.appendChild(frag);
  const suffix = results.length >= MAX_RESULTS ? `（只顯示前 ${MAX_RESULTS} 筆，請縮小關鍵字）` : "";
  els.status.textContent = results.length ? "" : "沒有符合的腳本";
  els.count.textContent = `${results.length} 筆結果${suffix}`;
}

function setActive(i) {
  if (!results.length) return;
  activeIndex = Math.max(0, Math.min(results.length - 1, i));
  els.list.querySelectorAll("li.active").forEach((n) => n.classList.remove("active"));
  const li = els.list.children[activeIndex];
  if (li) {
    li.classList.add("active");
    li.scrollIntoView({ block: "nearest" });
  }
}

// ---------- 詳細頁 ----------
function openDetail(it) {
  current = it;
  els.detailId.textContent = it.id;
  els.detailName.textContent = it.name;
  els.detailDisplay.textContent = it.display || "—";
  els.detailFreq.textContent = it.freq || "—";
  els.detailLink.textContent = it.path;
  els.detailLink.href = REPO_BLOB + it.path.split("/").map(encodeURIComponent).join("/");
  els.detailCode.textContent = it.code;
  els.copy.classList.remove("done");
  els.copy.textContent = "複製程式碼";
  els.listView.hidden = true;
  els.detailView.hidden = false;
  els.copy.focus();
}

function closeDetail() {
  current = null;
  els.detailView.hidden = true;
  els.listView.hidden = false;
  els.q.focus();
}

async function copyCode() {
  if (!current) return;
  try {
    await navigator.clipboard.writeText(current.code);
    els.copy.textContent = "已複製 ✓";
    els.copy.classList.add("done");
    setTimeout(() => {
      els.copy.textContent = "複製程式碼";
      els.copy.classList.remove("done");
    }, 1500);
  } catch (err) {
    console.error("clipboard write failed", err);
    els.copy.textContent = "複製失敗";
  }
}

// ---------- 記住上次的搜尋 ----------
function saveState() {
  try {
    localStorage.setItem("xs-blocks:q", els.q.value);
    localStorage.setItem("xs-blocks:cat", els.cat.value);
  } catch (_) { /* ignore */ }
}
function restoreState() {
  try {
    els.q.value = localStorage.getItem("xs-blocks:q") || "";
    els.cat.value = localStorage.getItem("xs-blocks:cat") || "";
  } catch (_) { /* ignore */ }
}

// ---------- 事件 ----------
els.q.addEventListener("input", search);
els.cat.addEventListener("change", search);
els.list.addEventListener("click", (e) => {
  const li = e.target.closest("li");
  if (li) openDetail(results[Number(li.dataset.index)]);
});
els.back.addEventListener("click", closeDetail);
els.copy.addEventListener("click", copyCode);

document.addEventListener("keydown", (e) => {
  if (current) {
    if (e.key === "Escape") { e.preventDefault(); closeDetail(); }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); copyCode(); }
    return;
  }
  if (e.key === "ArrowDown") { e.preventDefault(); setActive(activeIndex + 1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); setActive(activeIndex - 1); }
  else if (e.key === "Enter" && activeIndex >= 0) { e.preventDefault(); openDetail(results[activeIndex]); }
  else if (e.key === "Escape" && els.q.value) { e.preventDefault(); els.q.value = ""; search(); }
});

load();
