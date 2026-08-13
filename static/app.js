const profileInput = document.querySelector("#profile");
const apiKeyInput = document.querySelector("#api-key");
const searchButton = document.querySelector("#search");
const refreshButton = document.querySelector("#refresh");
const previousBatchButton = document.querySelector("#previous-batch");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const player = document.querySelector("#player");
const librarySize = document.querySelector("#library-size");
const gameList = document.querySelector("#game-list");
const minPriceInput = document.querySelector("#min-price");
const maxPriceInput = document.querySelector("#max-price");
const wishlist = document.querySelector("#wishlist");
const wishlistList = document.querySelector("#wishlist-list");
const wishlistCount = document.querySelector("#wishlist-count");
const wishlistTotal = document.querySelector("#wishlist-total");
const backButton = document.querySelector("#back");
const giftMessageText = document.querySelector("#gift-message-text");
const shuffleGiftMessageButton = document.querySelector("#shuffle-gift-message");
const copyGiftMessageButton = document.querySelector("#copy-gift-message");
const backgroundSwatches = document.querySelectorAll(".background-swatch");
const categoryState = {};
let wishlistGames = [];
let loadingTimer;
let giftMessageIndex = -1;
let activePriority = null;
const giftMessageTemplates = [
  "这是我在 Gift Scout 里为你挑的礼物，希望你会喜欢。",
  "看到这些游戏时第一个想到的就是你，愿它们给你带来一点新乐趣。",
  "给你的游戏库添几款新冒险，慢慢玩，不着急通关。",
  "我认真研究了你的游戏口味，挑了这些送给你。希望正中下怀。",
  "愿这份小礼物，刚好落在你想开始下一局的时候。",
  "不是随机挑的，是按你的游戏偏好选出来的。收下吧。",
  "希望这些游戏能陪你度过一些舒服又投入的晚上。",
  "给你留了几段新的故事、地图和挑战，祝你玩得开心。",
  "这是我为你选的一份游戏礼物。愿每一次启动都值得期待。",
  "愿这几款游戏，成为你近期最想点开的那几个图标。",
];
const loadingMessages = [
  "正在读取公开游戏库...",
  "正在寻找 TA 真正喜欢的游戏...",
  "正在读取游戏成就...",
  "正在计算游玩投入度...",
  "正在整理 TA 的代表游戏...",
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

function setBackground(background) {
  document.body.dataset.background = background;
  localStorage.setItem("gift-scout-background", background);
  backgroundSwatches.forEach((swatch) => {
    swatch.setAttribute("aria-pressed", String(swatch.dataset.background === background));
  });
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

function getCurrentPrice(game) {
  if (Number.isFinite(game.final_price)) return game.final_price / 100;
  const match = game.price_note?.match(/¥([0-9.]+)/);
  return match ? Number(match[1]) : null;
}

function getDiscountPercent(game) {
  if (Number.isFinite(game.discount_percent)) return game.discount_percent;
  const match = game.price_note?.match(/限时\s*(\d+)%\s*折扣/);
  return match ? Number(match[1]) : 0;
}

function getOriginalPrice(game) {
  if (Number.isFinite(game.original_price)) return game.original_price / 100;
  const match = game.price_note?.match(/原价\s*¥([0-9.]+)/);
  return match ? Number(match[1]) : null;
}

function formatPrice(price) {
  return `¥${price.toFixed(2)}`;
}

function formatReviewSummary(game) {
  if (!game.review_count || game.positive_rate === null || game.positive_rate === undefined) return "评测数据暂缺";
  let label = "褒贬不一";
  if (game.positive_rate >= 95) label = "好评如潮";
  else if (game.positive_rate >= 80) label = "特别好评";
  else if (game.positive_rate >= 70) label = "多半好评";
  else if (game.positive_rate < 40) label = "多半差评";
  return `★ ${label}（${game.review_count.toLocaleString("zh-CN")} 篇评测 · ${game.positive_rate}% 好评）`;
}

function buildGiftMessage() {
  const gameNames = wishlistGames.slice(0, 3).map((game) => `《${game.name}》`);
  const selection = gameNames.length ? `我选了${gameNames.join("、")}${wishlistGames.length > 3 ? "等游戏，" : "，"}` : "";
  return `${selection}${giftMessageTemplates[giftMessageIndex]}`;
}

function shuffleGiftMessage() {
  if (!wishlistGames.length) return;
  let nextIndex = giftMessageIndex;
  while (nextIndex === giftMessageIndex) nextIndex = Math.floor(Math.random() * giftMessageTemplates.length);
  giftMessageIndex = nextIndex;
  giftMessageText.textContent = buildGiftMessage();
}

async function copyGiftMessage() {
  try {
    await navigator.clipboard.writeText(giftMessageText.textContent);
  } catch {
    const input = document.createElement("textarea");
    input.value = giftMessageText.textContent;
    document.body.append(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  copyGiftMessageButton.textContent = "已复制";
  setTimeout(() => { copyGiftMessageButton.textContent = "复制"; }, 1400);
}

function renderWishlist() {
  wishlist.hidden = wishlistGames.length === 0;
  wishlistCount.textContent = `${wishlistGames.length} 款`;
  const prices = wishlistGames.map(getCurrentPrice).filter((price) => price !== null);
  const total = prices.reduce((sum, price) => sum + price, 0);
  wishlistTotal.textContent = prices.length === wishlistGames.length ? `现价合计 ${formatPrice(total)}` : `已知现价合计 ${formatPrice(total)}`;
  if (giftMessageIndex < 0) giftMessageIndex = 0;
  giftMessageText.textContent = buildGiftMessage();
  wishlistList.replaceChildren(...wishlistGames.map((game) => {
    const item = document.createElement("article");
    item.className = "wishlist-item";
    item.innerHTML = `<img src="${game.image}" alt="" /><span>${game.name}</span><span>${game.price_note}</span><a href="https://store.steampowered.com/app/${game.app_id}/?cc=cn" target="_blank" rel="noreferrer">Steam ↗</a><button type="button" aria-label="移除 ${game.name}">×</button>`;
    item.querySelector("button").addEventListener("click", () => { wishlistGames = wishlistGames.filter((entry) => entry.app_id !== game.app_id); renderWishlist(); });
    return item;
  }));
}

async function findGifts(refresh = false) {
  const profile = profileInput.value.trim();
  const apiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
  const priority = document.querySelector('input[name="priority"]:checked').value;
  const minPrice = Number(minPriceInput.value || 0);
  const maxPrice = Number(maxPriceInput.value || 9999);
  const state = categoryState[priority] || { shownAppIds: [], evidenceUseCounts: {}, previousResultBatches: [] };
  categoryState[priority] = state;
  if (!refresh) {
    state.shownAppIds = [];
    state.evidenceUseCounts = {};
    state.previousResultBatches = [];
    previousBatchButton.hidden = true;
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
  if (minPrice < 0 || maxPrice < minPrice) {
    setStatus("请填写有效的预算范围。", true);
    return;
  }
  searchButton.disabled = true;
  refreshButton.disabled = true;
  previousBatchButton.disabled = true;
  if (refresh && activePriority === priority && !results.hidden && gameList.children.length) {
    state.previousResultBatches.push({
      cards: Array.from(gameList.children),
      player: player.innerHTML,
      librarySize: librarySize.textContent,
    });
  }
  if (!refresh) results.hidden = true;
  startLoading();
  try {
    const response = await fetch("/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, ...(apiKey ? { api_key: apiKey } : {}), exclude_app_ids: state.shownAppIds, evidence_use_counts: state.evidenceUseCounts, priority, min_price: minPrice, max_price: maxPrice }),
    });
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : {};
    if (!contentType.includes("application/json")) throw new Error("服务器返回了非预期响应，请稍后重试。");
    if (!response.ok) throw new Error(data.error || "暂时无法生成推荐。");
    let batchStartNumber = state.shownAppIds.length + 1;
    if (data.recycled) {
      state.shownAppIds = [];
      state.evidenceUseCounts = {};
      batchStartNumber = 1;
      setStatus("这一分类的未展示游戏已用完，已重新开始本分类。", false);
    }
    state.shownAppIds.push(...data.recommendations.map((game) => game.app_id));
    data.recommendations.flatMap((game) => game.evidence_app_ids).forEach((appId) => { state.evidenceUseCounts[appId] = (state.evidenceUseCounts[appId] || 0) + 1; });
    activePriority = priority;
    player.innerHTML = `${data.profile.avatar ? `<img src="${data.profile.avatar}" alt="" />` : ""}<h2>${data.profile.name} 的礼物清单</h2>`;
    librarySize.textContent = `分析了 ${data.library_size} 款拥有游戏中的 ${data.preference_sample_size} 款代表游戏`;
    gameList.replaceChildren(...data.recommendations.map((game, index) => {
      const item = document.createElement("article");
      item.className = "game";
      item.style.animationDelay = `${index * 70}ms`;
      const score = game.confidence === "基础偏好" ? `匹配类型：${(game.matched_genres || []).join(" / ") || "待补充"}` : `匹配标签分：${game.score}（${game.confidence}置信）`;
      const coreDetails = game.matched_label_details?.level_2_core || [];
      const generalDetails = game.matched_label_details?.level_1 || [];
      const formatTags = (labels, emoji) => labels.map((label) => `<span class="tag-chip">${emoji} ${label.name}</span>`).join("") || "<span class=\"empty-evidence\">暂无</span>";
      const evidenceById = new Map();
      [...coreDetails, ...generalDetails].forEach((label) => evidenceById.set(label.source_game.app_id, label.source_game));
      const evidenceGames = [...evidenceById.values()].slice(0, 3);
      const formatEvidence = (match) => {
        const signals = [`${match.hours} 小时`];
        if (match.achievement_percent !== null) signals.push(`${match.achievement_percent}% 成就`);
        if (match.recently_played) signals.push("最近游玩");
        return `<li><strong>《${match.name}》</strong><span>${signals.join(" · ")}</span></li>`;
      };
      const evidence = evidenceGames.length ? evidenceGames.map(formatEvidence).join("") : "<li class=\"empty-evidence\">当前没有足够的代表游戏标签证据</li>";
      const generalTags = generalDetails.map((label) => `<div class="general-tag"><strong>${label.name}</strong><small>第 ${label.candidate_tag_rank} 位</small></div>`).join("") || "<span class=\"empty-evidence\">暂无</span>";
      const currentPrice = getCurrentPrice(game);
      const priceDisplay = currentPrice === null ? game.price_note : formatPrice(currentPrice);
      const discountPercent = getDiscountPercent(game);
      const originalPrice = getOriginalPrice(game);
      const discount = discountPercent ? `-${discountPercent}%` : "当前价";
      const originalPriceDisplay = originalPrice === null || !discountPercent ? "" : `<del>${formatPrice(originalPrice)}</del>`;
      const storeInfo = priority === "new_releases" ? `发售 ${game.release_date}` : formatReviewSummary(game);
      const storeInfoClass = priority === "new_releases" ? "release-date" : "review-summary";
      const saved = wishlistGames.some((entry) => entry.app_id === game.app_id);
      item.innerHTML = `<aside class="game-rail"><img src="${game.image}" alt="${game.name}" /><section class="match-block"><p>核心偏好</p><div class="tag-list">${formatTags(coreDetails, "✦")}</div></section><section class="match-block"><p>一般偏好</p><div class="general-tag-list">${generalTags}</div></section></aside><div class="game-content"><p class="game-number">推荐 ${String(batchStartNumber + index).padStart(2, "0")}${game.store_source ? ` / ${game.store_source}` : ""}</p><h3>${game.name}</h3><p class="metadata">${score}</p><section class="evidence-block"><p>像 TA 玩过的</p><ul>${evidence}</ul></section><section class="price-block"><span class="${storeInfoClass}">${storeInfo}</span><div class="price-value"><strong>${priceDisplay}</strong><em>${discount}</em>${originalPriceDisplay}</div><a href="https://steamdb.info/app/${game.app_id}/" target="_blank" rel="noreferrer" title="在 SteamDB 查看价格历史；数据可能不覆盖中国区">历史价 ↗</a></section><div class="card-actions"><a href="https://store.steampowered.com/app/${game.app_id}/?cc=cn" target="_blank" rel="noreferrer">Steam ↗</a><button type="button" class="save-game" ${saved ? "disabled" : ""} aria-label="加入待购买清单">${saved ? "已加入" : "♡"}</button></div></div>`;
      item.querySelector(".save-game").addEventListener("click", () => { wishlistGames.push(game); renderWishlist(); item.querySelector(".save-game").textContent = "已加入"; item.querySelector(".save-game").disabled = true; });
      return item;
    }));
    previousBatchButton.hidden = state.previousResultBatches.length === 0;
    results.hidden = false;
    if (!data.recycled) setStatus("");
  } catch (error) {
    stopLoading();
    setStatus(error.message, true);
  } finally {
    stopLoading();
    searchButton.disabled = false;
    refreshButton.disabled = false;
    previousBatchButton.disabled = false;
  }
}

searchButton.addEventListener("click", findGifts);
refreshButton.addEventListener("click", () => findGifts(true));
backgroundSwatches.forEach((swatch) => swatch.addEventListener("click", () => setBackground(swatch.dataset.background)));
setBackground(localStorage.getItem("gift-scout-background") || "paper");
previousBatchButton.addEventListener("click", () => {
  const state = categoryState[activePriority];
  const previous = state?.previousResultBatches.pop();
  if (!previous) return;
  gameList.replaceChildren(...previous.cards);
  player.innerHTML = previous.player;
  librarySize.textContent = previous.librarySize;
  previousBatchButton.hidden = state.previousResultBatches.length === 0;
  window.scrollTo({ top: results.offsetTop - 20, behavior: "smooth" });
});
shuffleGiftMessageButton.addEventListener("click", shuffleGiftMessage);
copyGiftMessageButton.addEventListener("click", copyGiftMessage);
backButton.addEventListener("click", () => {
  if (window.history.length > 1) window.history.back();
  else { results.hidden = true; profileInput.focus(); window.scrollTo({ top: 0, behavior: "smooth" }); }
});
profileInput.addEventListener("keydown", (event) => { if (event.key === "Enter") findGifts(); });
if (apiKeyInput) apiKeyInput.addEventListener("keydown", (event) => { if (event.key === "Enter") findGifts(); });