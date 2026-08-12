const profileInput = document.querySelector("#profile");
const apiKeyInput = document.querySelector("#api-key");
const searchButton = document.querySelector("#search");
const refreshButton = document.querySelector("#refresh");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const player = document.querySelector("#player");
const librarySize = document.querySelector("#library-size");
const gameList = document.querySelector("#game-list");
let shownAppIds = [];
let evidenceUseCounts = {};
let loadingTimer;
const loadingMessages = [
  "正在读取公开游戏库...",
  "正在翻看中国区热销游戏...",
  "正在检查优惠和折扣...",
  "正在挑选适合送礼的游戏...",
  "正在确认 Steam 商店链接...",
  "正在让推荐结果少一点套路...",
];

function setStatus(message, isError = false) {
  status.textContent = message;
  status.className = isError ? "status error" : "status";
}

function startLoading() {
  let messageIndex = 0;
  setStatus(loadingMessages[messageIndex]);
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    messageIndex = (messageIndex + 1) % loadingMessages.length;
    setStatus(loadingMessages[messageIndex]);
  }, 1200);
}

function stopLoading() {
  clearInterval(loadingTimer);
  loadingTimer = undefined;
}

async function findGifts(refresh = false) {
  const profile = profileInput.value.trim();
  const apiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
  const priority = document.querySelector('input[name="priority"]:checked').value;
  if (!refresh) {
    shownAppIds = [];
    evidenceUseCounts = {};
  }
  if (!profile) {
    setStatus("请先输入 Steam 个人资料链接或 17 位 SteamID。", true);
    profileInput.focus();
    return;
  }
  if (apiKeyInput && !apiKey) {
    setStatus("请填写 Steam Web API 密钥。", true);
    apiKeyInput.focus();
    return;
  }
  searchButton.disabled = true;
  refreshButton.disabled = true;
  if (!refresh) results.hidden = true;
  startLoading();
  try {
    const response = await fetch("/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, ...(apiKey ? { api_key: apiKey } : {}), exclude_app_ids: shownAppIds, evidence_use_counts: evidenceUseCounts, priority }),
    });
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : {};
    if (!contentType.includes("application/json")) throw new Error("服务器返回了非预期响应，请稍后重试。");
    if (!response.ok) throw new Error(data.error || "暂时无法生成推荐。");
    shownAppIds.push(...data.recommendations.map((game) => game.app_id));
    data.recommendations.flatMap((game) => game.evidence_app_ids).forEach((appId) => { evidenceUseCounts[appId] = (evidenceUseCounts[appId] || 0) + 1; });
    player.innerHTML = `${data.profile.avatar ? `<img src="${data.profile.avatar}" alt="" />` : ""}<h2>${data.profile.name} 的礼物清单</h2>`;
    librarySize.textContent = `分析了 ${data.library_size} 款拥有游戏中的 ${data.preference_sample_size} 款高游玩时长游戏`;
    gameList.replaceChildren(...data.recommendations.map((game, index) => {
      const item = document.createElement("article");
      item.className = "game";
      item.style.animationDelay = `${index * 70}ms`;
      const metadata = game.store_category === "new_releases" ? `发售：${game.release_date} / 好评率：${game.positive_rate ?? "暂无"}%` : ["top_sellers", "highly_rated"].includes(game.store_category) ? `好评率：${game.positive_rate ?? "暂无"}% / ${game.review_count.toLocaleString()} 篇评测`: "";
      item.innerHTML = `<img src="${game.image}" alt="${game.name}" /><div><p class="game-number">推荐 ${String(index + 1).padStart(2, "0")}${game.store_source ? ` / ${game.store_source}` : ""}</p><h3>${game.name}</h3>${metadata ? `<p class="metadata">${metadata}</p>` : ""}<p class="reason">${game.reason}</p><a href="https://store.steampowered.com/app/${game.app_id}/?cc=cn" target="_blank" rel="noreferrer">在 Steam 中国区查看 <span aria-hidden="true">↗</span></a></div>`;
      return item;
    }));
    results.hidden = false;
    setStatus("");
  } catch (error) {
    stopLoading();
    setStatus(error.message, true);
  } finally {
    stopLoading();
    searchButton.disabled = false;
    refreshButton.disabled = false;
  }
}

searchButton.addEventListener("click", findGifts);
refreshButton.addEventListener("click", () => findGifts(true));
profileInput.addEventListener("keydown", (event) => { if (event.key === "Enter") findGifts(); });
if (apiKeyInput) apiKeyInput.addEventListener("keydown", (event) => { if (event.key === "Enter") findGifts(); });
