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
const preferenceConfirmation = document.querySelector("#preference-confirmation");
const preferenceTags = document.querySelector("#preference-tags");
const applyPreferencesButton = document.querySelector("#apply-preferences");
const preferenceLimit = document.querySelector("#preference-limit");
const preferenceTitle = document.querySelector("#preference-title");
const modeGiftButton = document.querySelector("#mode-gift");
const modeSeedButton = document.querySelector("#mode-seed");
const modeNote = document.querySelector("#mode-note");
const profileLabel = document.querySelector("#profile-label");
const introTitle = document.querySelector("#intro-title");
const introEyebrow = document.querySelector("#intro-eyebrow");
const introLede = document.querySelector("#intro-lede");
const ownerProfileRow = document.querySelector("#owner-profile-row");
const ownerProfileInput = document.querySelector("#owner-profile");
const priorityFieldset = document.querySelector(".priority");
const scoreLookup = document.querySelector("#score-lookup");
const scoreQueryInput = document.querySelector("#score-query");
const scoreSuggest = document.querySelector("#score-suggest");
const scoreCheckButton = document.querySelector("#score-check");
const scoreMessage = document.querySelector("#score-message");
const scoreResult = document.querySelector("#score-result");
const categoryState = {};
let seedMode = false;
let wishlistGames = [];
let loadingTimer;
let giftMessageIndex = -1;
let activePriority = null;
let availablePreferenceTags = [];
let activeTagIds = new Set();
let excludedTagIds = new Set();

// Game and tag names come from Steam and are interpolated into card markup.
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));

// Bias which owned games get cited as evidence, without excluding lighter ones.
const EVIDENCE_DISPLAY_EXPONENT = 2;

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
  "正在贿赂仓鼠加班...",
  "正在把挂机时长挤干...",
  "正在请教一位云玩家...",
  "正在给标签排座位...",
  "正在偷看 TA 的愉快周末...",
  "正在抖掉库存里的灰...",
  "正在和推荐算法讨价还价...",
  "正在撑开券商的钱包...",
  "正在排除那些吃灰的建议...",
  "正在捕捉一闪而过的灵感...",
  "正在给礼物系上蝴蝶结...",
  "正在向气泡水请教手感...",
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

function renderPreferenceTags(tags, appliedTagIds, appliedExcludedIds = []) {
  availablePreferenceTags = tags;
  activeTagIds = new Set(appliedTagIds);
  excludedTagIds = new Set(appliedExcludedIds);
  preferenceConfirmation.hidden = tags.length === 0;
  const updatePreferenceSelectionStatus = () => {
    const parts = [];
    if (activeTagIds.size) parts.push(`想要 ${activeTagIds.size}/3`);
    if (excludedTagIds.size) parts.push(`排除 ${excludedTagIds.size}`);
    preferenceLimit.textContent = parts.length ? `${parts.join("　")}　⌄` : "点一下想要，再点一下排除　可选　⌄";
    applyPreferencesButton.disabled = activeTagIds.size === 0 && excludedTagIds.size === 0;
    applyPreferencesButton.textContent = parts.length ? `应用（${parts.join("，")}）` : "应用偏好";
  };
  const groups = ["和谁玩", "最近玩", "爱玩的"];
  preferenceTags.replaceChildren(...groups.map((group) => {
    const board = document.createElement("section");
    board.className = "preference-board";
    const title = document.createElement("p");
    title.textContent = group;
    const tagList = document.createElement("div");
    tagList.className = "preference-tag-list";
    const groupTags = tags.filter((tag) => tag.ui_group === group);
    tagList.replaceChildren(...groupTags.map((tag) => {
      // One control, three states: neutral, wanted, excluded.
      const button = document.createElement("button");
      button.type = "button";
      button.className = "preference-tag";
      const mark = document.createElement("span");
      mark.className = "preference-mark";
      const text = document.createElement("span");
      text.textContent = tag.name;
      button.append(mark, text);
      const paint = () => {
        const wanted = activeTagIds.has(tag.tag_id);
        const excluded = excludedTagIds.has(tag.tag_id);
        button.classList.toggle("is-wanted", wanted);
        button.classList.toggle("is-excluded", excluded);
        mark.textContent = wanted ? "✓" : excluded ? "✕" : "＋";
        button.setAttribute("aria-label", `${tag.name}：${wanted ? "想要" : excluded ? "排除" : "未选"}`);
      };
      button.addEventListener("click", () => {
        if (activeTagIds.has(tag.tag_id)) {
          activeTagIds.delete(tag.tag_id);
          excludedTagIds.add(tag.tag_id);
        } else if (excludedTagIds.has(tag.tag_id)) {
          excludedTagIds.delete(tag.tag_id);
        } else if (activeTagIds.size >= 3) {
          preferenceLimit.textContent = "最多只能选 3 个想要的标签　⌄";
          return;
        } else {
          activeTagIds.add(tag.tag_id);
        }
        paint();
        updatePreferenceSelectionStatus();
      });
      paint();
      return button;
    }));
    board.append(title, tagList);
    return board;
  }));
  updatePreferenceSelectionStatus();
}

function startLoading() {
  // Shuffled so a slow lookup does not replay the same script every time.
  const script = loadingMessages.slice(1).sort(() => Math.random() - 0.5);
  script.unshift(loadingMessages[0]);
  let messageIndex = 0;
  setStatus(script[messageIndex]);
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    messageIndex = (messageIndex + 1) % script.length;
    setStatus(script[messageIndex]);
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

// Loot-rarity tiers: finding a great match should feel like pulling a rare drop.
// The server decides the tier from how deep the match actually is, so the same
// game keeps its rarity no matter what else happened to be on the page.
const MATCH_TIER_KEYS = { UR: "ur", SSR: "ssr", SR: "sr", R: "rare", N: "common" };

function matchBadge(game, label = "匹配分") {
  const value = Math.max(0, Math.min(100, Number(game.match_percent) || 0));
  const name = game.match_tier || "N";
  const key = MATCH_TIER_KEYS[name] || "common";
  return `<span class="match-badge tier-${key}" title="${esc(game.match_tier_note || "")}"><b>${value}</b><i>${label}</i><em>${esc(name)}</em></span>`;
}

function formatReviewSummary(game) {
  if (!game.review_count || game.positive_rate === null || game.positive_rate === undefined) {
    return '<span class="review-summary review-unknown"><b>评测数据暂缺</b></span>';
  }
  let label = "褒贬不一";
  let tone = "mixed";
  if (game.positive_rate >= 95) { label = "好评如潮"; tone = "overwhelming"; }
  else if (game.positive_rate >= 80) { label = "特别好评"; tone = "very-positive"; }
  else if (game.positive_rate >= 70) { label = "多半好评"; tone = "positive"; }
  else if (game.positive_rate < 40) { label = "多半差评"; tone = "negative"; }
  return `<span class="review-summary review-${tone}"><b>★ ${label}</b><i>${game.positive_rate}% 好评 · ${game.review_count.toLocaleString("zh-CN")} 篇</i></span>`;
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

function showBatch(state, index) {
  const batch = state.batches[index];
  if (!batch) return;
  state.batchIndex = index;
  gameList.replaceChildren(...batch.cards);
  player.innerHTML = batch.player;
  librarySize.textContent = batch.librarySize;
  previousBatchButton.hidden = index <= 0;
  results.hidden = false;
  setStatus("");
  window.scrollTo({ top: results.offsetTop - 20, behavior: "smooth" });
}

async function findGifts(refresh = false) {
  const profile = profileInput.value.trim();
  const apiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
  const priority = document.querySelector('input[name="priority"]:checked').value;
  const minPrice = Number(minPriceInput.value || 0);
  const maxPrice = Number(maxPriceInput.value || 9999);
  const state = categoryState[priority] || { shownAppIds: [], evidenceUseCounts: {}, batches: [], batchIndex: -1 };
  categoryState[priority] = state;
  if (!refresh) {
    state.shownAppIds = [];
    state.evidenceUseCounts = {};
    state.batches = [];
    state.batchIndex = -1;
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
  if (seedMode && !ownerProfileInput.value.trim()) {
    setStatus("种草模式需要你自己的 Steam 个人资料，才能从你的游戏库里挑游戏。", true);
    ownerProfileInput.focus();
    return;
  }
  if (minPrice < 0 || maxPrice < minPrice) {
    setStatus("请填写有效的预算范围。", true);
    return;
  }
  searchButton.disabled = true;
  refreshButton.disabled = true;
  previousBatchButton.disabled = true;
  if (!refresh) results.hidden = true;
  startLoading();
  try {
    const response = await fetch(seedMode ? "/api/seed-recommendations" : "/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, ...(seedMode ? { owner_profile: ownerProfileInput.value.trim() } : {}), ...(apiKey ? { api_key: apiKey } : {}), exclude_app_ids: state.shownAppIds, evidence_use_counts: state.evidenceUseCounts, active_tag_ids: [...activeTagIds], excluded_tag_ids: [...excludedTagIds], priority, min_price: minPrice, max_price: maxPrice }),
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
    preferenceTitle.textContent = `${data.profile.name} 喜欢玩的游戏标签`;
    renderPreferenceTags(data.preference_tags || [], data.applied_tag_ids || [], data.applied_excluded_tag_ids || []);
    player.innerHTML = seedMode
      ? `${data.profile.avatar ? `<img src="${esc(data.profile.avatar)}" alt="" />` : ""}<h2 class="seed-heading"><span class="seed-from">从 <b>${esc(data.owner?.name || "你")}</b> 的游戏库</span><span class="seed-arrow">→</span><span class="seed-to">种草给 <b>${esc(data.profile.name)}</b></span></h2>`
      : `${data.profile.avatar ? `<img src="${esc(data.profile.avatar)}" alt="" />` : ""}<h2>${esc(data.profile.name)} 的礼物清单</h2>`;
    librarySize.textContent = seedMode
      ? `从你玩过、且 ${data.profile.name} 还没有的 ${data.owner?.playable_count ?? 0} 款游戏中挑选，对照 TA 的 ${data.preference_sample_size} 款代表游戏`
      : `分析了 ${data.library_size} 款拥有游戏中的 ${data.preference_sample_size} 款代表游戏`;
    const batchCards = data.recommendations.map((game, index) => {
      const item = document.createElement("article");
      item.className = "game";
      item.style.animationDelay = `${index * 70}ms`;
      const score = game.confidence === "基础偏好"
        ? `<span class="metadata-basic">匹配类型：${esc((game.matched_genres || []).join(" / ") || "待补充")}</span>`
        : matchBadge(game);
      const level3Details = game.matched_label_details?.level_3 || [];
      const coreDetails = game.matched_label_details?.level_2_core || [];
      const generalDetails = game.matched_label_details?.level_1 || [];
      const formatTags = (labels, emoji) => labels.map((label) => `<span class="tag-chip">${emoji} ${esc(label.name)}</span>`).join("");
      const evidenceById = new Map();
      [...level3Details, ...coreDetails, ...generalDetails].forEach((label) => {
        const source = label.source_game;
        if (!evidenceById.has(source.app_id)) evidenceById.set(source.app_id, { game: source, tags: [] });
        const entry = evidenceById.get(source.app_id);
        if (!entry.tags.includes(label.name)) entry.tags.push(label.name);
      });
      // Weighted rather than sorted: deeply played games should be cited most
      // often, but a niche corner of the library still deserves its share of the
      // spotlight instead of being excluded outright.
      const evidencePool = [...evidenceById.values()];
      const evidenceEntries = [];
      while (evidencePool.length && evidenceEntries.length < 3) {
        const weights = evidencePool.map((entry) => Math.max(0.1, entry.game.engagement_score ?? 1) ** EVIDENCE_DISPLAY_EXPONENT);
        let threshold = Math.random() * weights.reduce((sum, weight) => sum + weight, 0);
        let index = 0;
        while (index < evidencePool.length - 1 && threshold > weights[index]) {
          threshold -= weights[index];
          index += 1;
        }
        evidenceEntries.push(evidencePool.splice(index, 1)[0]);
      }
      const formatEvidence = ({ game: match, tags }) => {
        const signals = [`${match.hours} 小时`];
        if (match.achievement_percent !== null) signals.push(`${match.achievement_percent}% 成就`);
        if (match.recently_played) signals.push("最近游玩");
        // Idle games and desktop pets bank hours while nobody is playing them.
        const passiveNote = match.passive_playtime
          ? `<span class="evidence-note" title="挂机、桌面宠物类应用在后台也会计时，所以时长已按 20% 折算">挂机时长已折算</span>`
          : "";
        const matchedTags = tags.slice(0, 3).map((tag) => `<em>${esc(tag)}</em>`).join("");
        return `<li><strong>《${esc(match.name)}》</strong><span>${signals.join(" · ")}</span>${passiveNote}<div class="evidence-tags">${matchedTags}</div></li>`;
      };
      const generalTags = generalDetails.map((label) => `<div class="general-tag"><strong>${esc(label.name)}</strong><small>第 ${label.candidate_tag_rank} 位</small></div>`).join("");
      const gapTags = (game.match_gaps || [])
        .map((gap) => `<div class="gap-tag"><strong>${esc(gap.name)}</strong><small>第 ${gap.rank} 位</small></div>`)
        .join("");
      const matchSections = [
        level3Details.length ? `<section class="match-block level-3-block"><p>定向偏好</p><div class="tag-list">${formatTags(level3Details, "◆")}</div></section>` : "",
        coreDetails.length ? `<section class="match-block"><p>核心偏好</p><div class="tag-list">${formatTags(coreDetails, "✦")}</div></section>` : "",
        generalDetails.length ? `<section class="match-block"><p>一般偏好</p><div class="general-tag-list">${generalTags}</div></section>` : "",
        gapTags ? `<section class="match-block gap-block"><p>TA 似乎不感兴趣</p><div class="gap-list">${gapTags}</div></section>` : "",
      ].join("");
      const evidenceSection = evidenceEntries.length
        ? `<section class="evidence-block"><p>推荐依据 · TA 玩过的游戏</p><ul>${evidenceEntries.map(formatEvidence).join("")}</ul></section>`
        : "";
      const currentPrice = getCurrentPrice(game);
      const priceDisplay = currentPrice === null ? game.price_note : formatPrice(currentPrice);
      const discountPercent = getDiscountPercent(game);
      const originalPrice = getOriginalPrice(game);
      const discount = discountPercent ? `-${discountPercent}%` : "当前价";
      const originalPriceDisplay = originalPrice === null || !discountPercent ? "" : `<del>${formatPrice(originalPrice)}</del>`;
      const storeInfo = priority === "new_releases" && !seedMode
        ? `<span class="review-summary release-date"><b>发售 ${esc(game.release_date)}</b></span>`
        : formatReviewSummary(game);
      const contentWarning = game.content_warning ? `<p class="content-warning">${game.content_warning_text}</p>` : "";
      const saved = wishlistGames.some((entry) => entry.app_id === game.app_id);
      const ownerNote = seedMode && game.owner_hours !== undefined ? `<p class="owner-note">你玩过 ${game.owner_hours} 小时</p>` : "";
      item.innerHTML = `<aside class="game-rail"><img src="${game.image}" alt="${esc(game.name)}" />${matchSections}</aside><div class="game-content"><p class="game-number">${seedMode ? "种草" : "推荐"} ${String(batchStartNumber + index).padStart(2, "0")}${game.store_source ? ` / ${esc(game.store_source)}` : ""}</p><h3>${esc(game.name)}</h3><p class="metadata">${score}</p>${ownerNote}${contentWarning}${evidenceSection}<section class="price-block">${storeInfo}<div class="price-value"><strong>${priceDisplay}</strong><em>${discount}</em>${originalPriceDisplay}</div><a href="https://steamdb.info/app/${game.app_id}/" target="_blank" rel="noreferrer" title="在 SteamDB 查看价格历史；数据可能不覆盖中国区">历史价 ↗</a></section><div class="card-actions"><a href="https://store.steampowered.com/app/${game.app_id}/?cc=cn" target="_blank" rel="noreferrer">Steam ↗</a><button type="button" class="save-game" ${saved ? "disabled" : ""} aria-label="加入待购买清单">${saved ? "已加入" : "♡"}</button></div></div>`;
      item.querySelector(".save-game").addEventListener("click", () => { wishlistGames.push(game); renderWishlist(); item.querySelector(".save-game").textContent = "已加入"; item.querySelector(".save-game").disabled = true; });
      return item;
    });
    state.batches.push({ cards: batchCards, player: player.innerHTML, librarySize: librarySize.textContent });
    state.batchIndex = state.batches.length - 1;
    gameList.replaceChildren(...batchCards);
    previousBatchButton.hidden = state.batchIndex <= 0;
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

function setMode(useSeedMode) {
  seedMode = useSeedMode;
  document.body.dataset.mode = seedMode ? "seed" : "gift";
  modeGiftButton.classList.toggle("is-active", !seedMode);
  modeSeedButton.classList.toggle("is-active", seedMode);
  modeGiftButton.setAttribute("aria-selected", String(!seedMode));
  modeSeedButton.setAttribute("aria-selected", String(seedMode));
  ownerProfileRow.hidden = !seedMode;
  priorityFieldset.hidden = seedMode;
  profileLabel.innerHTML = seedMode
    ? '<span class="role-tag role-target">TA</span>要种草的对象（TA 的 Steam 个人资料）'
    : "Steam 个人资料";
  introTitle.innerHTML = seedMode ? '送 TA 一款<br /><em>你想种草</em>的游戏 🌱' : "给 TA 挑一款<br />游戏礼物 🎁";
  introEyebrow.textContent = seedMode
    ? "把你玩过并认可的游戏，推荐给合适的那个人"
    : "从 TA 的游戏库里，挑一份刚好合口味的礼物";
  introLede.textContent = seedMode
    ? "输入你和 TA 的公开 Steam 个人资料，从你玩过的游戏里挑出最合 TA 口味的几款。"
    : "输入公开 Steam 个人资料，看看哪些游戏更像一份会让 TA 开心的礼物。";
  modeNote.textContent = seedMode
    ? "从你自己玩过的游戏里，挑 TA 还没有、又合 TA 口味的推荐给 TA。"
    : "从 Steam 商店目录里，挑 TA 还没有的游戏作为礼物。";
  searchButton.innerHTML = seedMode ? '种草推荐 <span aria-hidden="true">→</span>' : '寻找礼物 <span aria-hidden="true">→</span>';
  Object.keys(categoryState).forEach((key) => delete categoryState[key]);
  activePriority = null;
  results.hidden = true;
  setStatus("");
}

function renderScoreResult(data) {
  const game = data.game;
  const chips = (labels) => labels.map((label) => `<span class="tag-chip">${esc(label)}</span>`).join("");
  const matched = (group) => (game.matched_label_details?.[group] || []).map((label) => label.name);
  const owned = data.already_owned ? '<p class="score-owned">⚠ TA 已经拥有这款游戏了，不适合再作为礼物。</p>' : "";
  const gated = game.blocked_combination
    ? '<p class="score-gated">这款游戏的标签组合被列为不适合作为礼物（例如真人影像的恋爱向作品），因此永远不会出现在推荐结果里。下面的匹配分仅供你自行判断。</p>'
    : (game.audience_gated ? '<p class="score-gated">这款游戏面向特定受众（如乙女向或男性向恋爱作品）。TA 的游戏库里没有同类作品，因此系统不会主动把它推荐出来 —— 下面的匹配分仅供你自行判断。</p>' : "");
  const scoreLine = game.match_percent === undefined
    ? '<p class="score-headline"><em>暂无匹配分</em></p>'
    : `<p class="score-headline">${matchBadge(game)}${game.match_rank ? `<span class="score-rank">在 ${game.match_total.toLocaleString("zh-CN")} 款候选中排第 <b>${game.match_rank.toLocaleString("zh-CN")}</b></span>` : ""}</p>`;
  const currentPrice = getCurrentPrice(game);
  const discountPercent = getDiscountPercent(game);
  const originalPrice = getOriginalPrice(game);
  const priceLine = currentPrice === null
    ? esc(game.price_note || "价格暂缺")
    : `<strong>${formatPrice(currentPrice)}</strong>${discountPercent ? `<em>-${discountPercent}%</em><del>${formatPrice(originalPrice)}</del>` : ""}`;
  const ownTags = (game.tag_labels || []).slice(0, 8);
  // Only non-empty layers are shown, so an empty row never reads as a failure.
  const matchRows = [
    ["定向偏好", matched("level_3")],
    ["核心偏好", matched("level_2_core")],
    ["一般偏好", matched("level_1")],
  ].filter(([, labels]) => labels.length)
    .map(([title, labels]) => `<p><span>${title}</span>${chips(labels)}</p>`).join("");
  const matchBlock = matchRows
    ? `<div class="score-rows score-matched"><p class="score-section">与 TA 口味重合的标签</p>${matchRows}</div>`
    : '<p class="score-nomatch">这款游戏的标签与 TA 的偏好画像没有重合。画像只包含 TA 实际玩过的游戏所带的标签，所以某个标签没出现，通常说明 TA 还没玩过这类游戏。</p>';
  scoreResult.innerHTML = `
    <div class="score-card">
      ${game.image ? `<img src="${esc(game.image)}" alt="" />` : ""}
      <div>
        <h4>${esc(game.name)}</h4>
        ${scoreLine}
        ${owned}
        ${gated}
        <div class="score-rows">
          <p><span>当前价格</span><span class="score-price">${priceLine}</span></p>
          <p><span>玩家评测</span>${formatReviewSummary(game)}</p>
          ${ownTags.length ? `<p><span>本作标签</span>${chips(ownTags)}</p>` : ""}
        </div>
        ${matchBlock}
        <p class="score-links">
          <a href="https://store.steampowered.com/app/${game.app_id}/?cc=cn" target="_blank" rel="noreferrer">Steam 商店 ↗</a>
          <a href="https://steamdb.info/app/${game.app_id}/" target="_blank" rel="noreferrer">历史价 ↗</a>
        </p>
      </div>
    </div>`;
  scoreResult.hidden = false;
}

let suggestTimer;
let suggestItems = [];
let suggestIndex = -1;

function closeSuggestions() {
  scoreSuggest.hidden = true;
  scoreSuggest.replaceChildren();
  scoreQueryInput.setAttribute("aria-expanded", "false");
  suggestItems = [];
  suggestIndex = -1;
}

function applySuggestion(item) {
  scoreQueryInput.value = item.name;
  scoreQueryInput.dataset.appId = item.app_id;
  scoreQueryInput.dataset.appIdName = item.name;
  closeSuggestions();
  checkGameScore();
}

function highlightSuggestion(nextIndex) {
  const options = [...scoreSuggest.children];
  if (!options.length) return;
  suggestIndex = (nextIndex + options.length) % options.length;
  options.forEach((option, index) => option.classList.toggle("is-active", index === suggestIndex));
  options[suggestIndex].scrollIntoView({ block: "nearest" });
}

async function loadSuggestions() {
  const query = scoreQueryInput.value.trim();
  if (query.length < 1) {
    closeSuggestions();
    return;
  }
  try {
    const response = await fetch(`/api/game-suggest?q=${encodeURIComponent(query)}`);
    const data = await response.json();
    suggestItems = data.suggestions || [];
    if (!suggestItems.length) {
      closeSuggestions();
      return;
    }
    scoreSuggest.replaceChildren(...suggestItems.map((item) => {
      const option = document.createElement("li");
      option.role = "option";
      option.innerHTML = `${item.image ? `<img src="${esc(item.image)}" alt="" />` : ""}<span>${esc(item.name)}</span>${item.review_count ? `<em>${item.review_count.toLocaleString("zh-CN")} 篇评测</em>` : ""}`;
      option.addEventListener("mousedown", (event) => { event.preventDefault(); applySuggestion(item); });
      return option;
    }));
    scoreSuggest.hidden = false;
    scoreQueryInput.setAttribute("aria-expanded", "true");
    suggestIndex = -1;
  } catch {
    closeSuggestions();
  }
}

async function checkGameScore() {
  const query = scoreQueryInput.value.trim();
  closeSuggestions();
  scoreResult.hidden = true;
  if (!query) {
    scoreMessage.textContent = "请输入游戏名称、Steam 商店链接或 App ID。";
    scoreQueryInput.focus();
    return;
  }
  const profile = profileInput.value.trim();
  if (!profile) {
    scoreMessage.textContent = "请先在上方填写要查询的 Steam 个人资料。";
    return;
  }
  // A picked suggestion carries its App ID so identical names stay unambiguous.
  const lookup = scoreQueryInput.dataset.appId && scoreQueryInput.value === scoreQueryInput.dataset.appIdName
    ? scoreQueryInput.dataset.appId
    : query;
  const apiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
  scoreCheckButton.disabled = true;
  scoreMessage.textContent = "正在计算匹配度…";
  try {
    const response = await fetch("/api/game-score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, query: lookup, ...(apiKey ? { api_key: apiKey } : {}) }),
    });
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : {};
    if (!contentType.includes("application/json")) throw new Error("服务器返回了非预期响应，请稍后重试。");
    if (data.suggestions?.length) {
      scoreMessage.innerHTML = `${esc(data.error)}<span class="score-suggestions">${data.suggestions.map((item) => `<button type="button" data-app-id="${item.app_id}">${esc(item.name)}</button>`).join("")}</span>`;
      scoreMessage.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
        scoreQueryInput.value = button.dataset.appId;
        checkGameScore();
      }));
      return;
    }
    if (!response.ok && !data.game) throw new Error(data.error || "暂时无法查询匹配度。");
    scoreMessage.textContent = data.error || "";
    renderScoreResult(data);
  } catch (error) {
    scoreMessage.textContent = error.message;
  } finally {
    scoreCheckButton.disabled = false;
  }
}

const feedbackMessage = document.querySelector("#feedback-message");
const feedbackImage = document.querySelector("#feedback-image");
const feedbackFilename = document.querySelector("#feedback-filename");
const feedbackAnonymous = document.querySelector("#feedback-anonymous");
const feedbackSubmit = document.querySelector("#feedback-submit");
const feedbackStatus = document.querySelector("#feedback-status");

feedbackImage.addEventListener("change", () => {
  const file = feedbackImage.files?.[0];
  feedbackFilename.textContent = file ? `${file.name}（${(file.size / 1024 / 1024).toFixed(1)} MB）` : "";
});

feedbackSubmit.addEventListener("click", async () => {
  const message = feedbackMessage.value.trim();
  if (!message) {
    feedbackStatus.textContent = "请先写下你的反馈内容。";
    feedbackMessage.focus();
    return;
  }
  const payload = new FormData();
  payload.append("message", message);
  payload.append("anonymous", String(feedbackAnonymous.checked));
  if (feedbackImage.files?.[0]) payload.append("image", feedbackImage.files[0]);
  feedbackSubmit.disabled = true;
  feedbackStatus.textContent = "正在提交…";
  try {
    const response = await fetch("/api/feedback", { method: "POST", body: payload });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "提交失败，请稍后重试。");
    feedbackStatus.textContent = "已收到，谢谢你的反馈！";
    feedbackMessage.value = "";
    feedbackImage.value = "";
    feedbackFilename.textContent = "";
  } catch (error) {
    feedbackStatus.textContent = error.message;
  } finally {
    feedbackSubmit.disabled = false;
  }
});

searchButton.addEventListener("click", findGifts);
refreshButton.addEventListener("click", () => findGifts(true));
applyPreferencesButton.addEventListener("click", () => findGifts(false));
backgroundSwatches.forEach((swatch) => swatch.addEventListener("click", () => setBackground(swatch.dataset.background)));
setBackground(localStorage.getItem("gift-scout-background") || "mint");
modeGiftButton.addEventListener("click", () => setMode(false));
modeSeedButton.addEventListener("click", () => setMode(true));
scoreCheckButton.addEventListener("click", checkGameScore);
scoreQueryInput.addEventListener("input", () => {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(loadSuggestions, 160);
});
scoreQueryInput.addEventListener("blur", () => setTimeout(closeSuggestions, 120));
scoreQueryInput.addEventListener("keydown", (event) => {
  if (!scoreSuggest.hidden && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
    event.preventDefault();
    highlightSuggestion(suggestIndex + (event.key === "ArrowDown" ? 1 : -1));
    return;
  }
  if (event.key === "Escape") { closeSuggestions(); return; }
  if (event.key === "Enter") {
    if (!scoreSuggest.hidden && suggestIndex >= 0) applySuggestion(suggestItems[suggestIndex]);
    else checkGameScore();
  }
});
ownerProfileInput.addEventListener("keydown", (event) => { if (event.key === "Enter") findGifts(); });
previousBatchButton.addEventListener("click", () => {
  const state = categoryState[activePriority];
  if (!state || state.batchIndex <= 0) return;
  showBatch(state, state.batchIndex - 1);
});
shuffleGiftMessageButton.addEventListener("click", shuffleGiftMessage);
copyGiftMessageButton.addEventListener("click", copyGiftMessage);
backButton.addEventListener("click", () => {
  if (window.history.length > 1) window.history.back();
  else { results.hidden = true; profileInput.focus(); window.scrollTo({ top: 0, behavior: "smooth" }); }
});
profileInput.addEventListener("keydown", (event) => { if (event.key === "Enter") findGifts(); });
if (apiKeyInput) apiKeyInput.addEventListener("keydown", (event) => { if (event.key === "Enter") findGifts(); });