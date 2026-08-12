import json
import os
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

STEAM_API_BASE = "https://api.steampowered.com"
STEAM_STORE_BASE = "https://store.steampowered.com"
STORE_HEADERS = {"User-Agent": "Gift Scout/1.0 (+local Steam gift recommender)"}
STORE_CACHE_SECONDS = 1800
CATALOG_SNAPSHOT_PATH = Path(app.root_path) / "data" / "store_catalog_cn.json"
store_catalog_cache = {"modified_at": None, "games": []}
SEARCH_PAGE_COUNT = 3
SEARCH_PAGE_SIZE = 50
MIN_CATALOG_SIZE = 150
CATALOG = [
    {"app_id": 413150, "name": "Stardew Valley", "genres": ["indie", "simulation", "rpg"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/413150/header.jpg"},
    {"app_id": 1245620, "name": "ELDEN RING", "genres": ["action", "rpg"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/header.jpg"},
    {"app_id": 1145360, "name": "Hades", "genres": ["action", "indie", "rpg"], "price_note": "中等价位", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1145360/header.jpg"},
    {"app_id": 413410, "name": "Doom", "genres": ["action"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/413410/header.jpg"},
    {"app_id": 1091500, "name": "Cyberpunk 2077", "genres": ["action", "rpg"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1091500/header.jpg"},
    {"app_id": 1150690, "name": "OMORI", "genres": ["indie", "rpg"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1150690/header.jpg"},
    {"app_id": 1086940, "name": "Baldur's Gate 3", "genres": ["adventure", "rpg", "strategy"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1086940/header.jpg"},
    {"app_id": 526870, "name": "Satisfactory", "genres": ["simulation", "strategy"], "price_note": "中等价位", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/526870/header.jpg"},
    {"app_id": 367520, "name": "Hollow Knight", "genres": ["action", "indie"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/367520/header.jpg"},
    {"app_id": 359550, "name": "Tom Clancy's Rainbow Six Siege", "genres": ["action", "multiplayer"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/359550/header.jpg"},
    {"app_id": 292030, "name": "The Witcher 3: Wild Hunt", "genres": ["adventure", "rpg"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/292030/header.jpg"},
    {"app_id": 1222670, "name": "The Sims 4", "genres": ["simulation"], "price_note": "可免费开始体验", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1222670/header.jpg"},
    {"app_id": 239140, "name": "Dying Light", "genres": ["action", "rpg"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/239140/header.jpg"},
    {"app_id": 105600, "name": "Terraria", "genres": ["action", "indie", "simulation"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/105600/header.jpg"},
    {"app_id": 620, "name": "Portal 2", "genres": ["adventure", "puzzle"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/620/header.jpg"},
    {"app_id": 271590, "name": "Grand Theft Auto V", "genres": ["action", "multiplayer"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/271590/header.jpg"},
    {"app_id": 440, "name": "Team Fortress 2", "genres": ["action", "multiplayer"], "price_note": "可免费开始体验", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/440/header.jpg"},
    {"app_id": 255710, "name": "Cities: Skylines", "genres": ["simulation", "strategy"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/255710/header.jpg"},
    {"app_id": 881100, "name": "Noita", "genres": ["action", "indie"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/881100/header.jpg"},
    {"app_id": 1174180, "name": "Red Dead Redemption 2", "genres": ["action", "adventure"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1174180/header.jpg"},
    {"app_id": 1222140, "name": "Detroit: Become Human", "genres": ["adventure", "story"], "price_note": "中等价位", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1222140/header.jpg"},
    {"app_id": 632360, "name": "Risk of Rain 2", "genres": ["action", "indie", "multiplayer"], "price_note": "中等价位", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/632360/header.jpg"},
]

GENRE_NAMES = {
    "动作": "action", "action": "action", "角色扮 演": "rpg", "角色扮演": "rpg", "rpg": "rpg",
    "模拟": "simulation", "simulation": "simulation", "策略": "strategy", "strategy": "strategy",
    "独立": "indie", "indie": "indie", "冒险": "adventure", "adventure": "adventure",
    "多人": "multiplayer", "大型多人在线": "multiplayer", "massively multiplayer": "multiplayer",
}


def extract_steam_id(profile_input):
    value = profile_input.strip()
    if re.fullmatch(r"\d{17}", value):
        return value

    parsed = urlparse(value if "://" in value else f"https://{value}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "profiles" and re.fullmatch(r"\d{17}", parts[1]):
        return parts[1]
    if len(parts) >= 2 and parts[0] == "id":
        return {"vanity": parts[1]}
    raise ValueError("请输入 17 位 SteamID，或 steamcommunity.com/id/... / profiles/... 个人资料链接。")


def steam_get(path, params):
    response = requests.get(f"{STEAM_API_BASE}{path}", params=params, timeout=12)
    response.raise_for_status()
    return response.json()


def resolve_steam_id(profile_input, api_key):
    identifier = extract_steam_id(profile_input)
    if isinstance(identifier, str):
        return identifier
    payload = steam_get(
        "/ISteamUser/ResolveVanityURL/v1/",
        {"key": api_key, "vanityurl": identifier["vanity"]},
    )
    steam_id = payload.get("response", {}).get("steamid")
    if not steam_id:
        raise ValueError("无法找到该 Steam 个人资料。请确认链接或 SteamID 是否正确。")
    return steam_id


def get_profile_and_library(steam_id, api_key):
    profile_data = steam_get(
        "/ISteamUser/GetPlayerSummaries/v2/", {"key": api_key, "steamids": steam_id}
    )
    players = profile_data.get("response", {}).get("players", [])
    if not players:
        raise ValueError("无法读取该 Steam 个人资料。")
    if players[0].get("communityvisibilitystate") != 3:
        raise ValueError("此个人资料不是公开状态，Steam 不允许读取其拥有的游戏。")

    library_data = steam_get(
        "/IPlayerService/GetOwnedGames/v1/",
        {"key": api_key, "steamid": steam_id, "include_appinfo": "true", "include_played_free_games": "true"},
    )
    games = library_data.get("response", {}).get("games")
    if games is None:
        raise ValueError("Steam 未返回游戏库；请确认该用户的“游戏详情”隐私设置为公开。")
    return players[0], games


def format_price(price_in_fen):
    return f"¥{price_in_fen / 100:.2f}"


def store_json(path, params):
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(f"{STEAM_STORE_BASE}{path}", params=params, headers=STORE_HEADERS, timeout=12)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            raise ValueError("Steam 返回的不是 JSON 对象。")
        except (requests.RequestException, ValueError, TypeError) as error:
            last_error = error
            if attempt < 2:
                sleep(0.5 * (attempt + 1))
    raise requests.RequestException(f"Steam 商店请求失败：{last_error}")


def get_store_game_details(item, source, category_id, include_reviews=True):
    app_id = item["id"]
    payload = store_json("/api/appdetails", {"appids": app_id, "cc": "cn", "l": "schinese"})
    entry = payload.get(str(app_id), {})
    data = entry.get("data", {}) if entry.get("success") else {}
    genres = [GENRE_NAMES.get(genre["description"].lower(), genre["description"].lower()) for genre in data.get("genres", [])]
    if not genres:
        return None
    price_overview = data.get("price_overview", {})
    original_price = item.get("original_price", price_overview.get("initial", 0))
    final_price = item.get("final_price", price_overview.get("final", 0))
    if not final_price:
        return None
    discount_percent = item.get("discount_percent", price_overview.get("discount_percent", 0))
    review_count = 0
    positive_rate = None
    if include_reviews:
        review_summary = store_json(
            f"/appreviews/{app_id}", {"json": 1, "language": "schinese", "purchase_type": "all", "num_per_page": 0}
        ).get("query_summary", {})
        review_count = review_summary.get("total_reviews", 0)
        positive_rate = round(100 * review_summary.get("total_positive", 0) / review_count) if review_count else None
    price_note = f"中国区现价 {format_price(final_price)}"
    if discount_percent:
        price_note += f"，限时 {discount_percent}% 折扣（原价 {format_price(original_price)}）"
    return {
        "app_id": app_id,
        "name": data.get("name", item.get("name", f"Steam App {app_id}")),
        "genres": genres,
        "price_note": price_note,
        "image": item.get("header_image", data.get("header_image", "")),
        "store_source": source,
        "store_category": category_id,
        "release_date": data.get("release_date", {}).get("date", "发售日期待定"),
        "positive_rate": positive_rate,
        "review_count": review_count,
    }


def get_store_search_items(search_params):
    app_ids = []
    for page in range(SEARCH_PAGE_COUNT):
        payload = store_json(
            "/search/results/",
            {
                "query": "", "start": page * SEARCH_PAGE_SIZE, "count": SEARCH_PAGE_SIZE,
                "dynamic_data": "", "infinite": 1, "cc": "cn", **search_params,
            },
        )
        page_ids = re.findall(r'data-ds-appid=\\?"(\d+)', payload.get("results_html", ""))
        app_ids.extend(page_ids)
        if len(page_ids) < SEARCH_PAGE_SIZE:
            break
    return [{"id": int(app_id)} for app_id in dict.fromkeys(app_ids)]


def build_store_catalog():
    data = store_json("/api/featuredcategories/", {"cc": "cn", "l": "schinese"})
    source_names = {"top_sellers": "中国区热销", "specials": "中国区优惠", "new_releases": "中国区新品"}
    candidates = {}
    for category_id, source in source_names.items():
        for item in data.get(category_id, {}).get("items", []):
            if item.get("type") in (0, "app"):
                candidates.setdefault(item["id"], (item, source, category_id, True))
    backup_sources = [
        ("highly_rated", "高评价精选", {"sort_by": "Reviews_DESC", "supportedlang": "schinese"}),
        ("specials", "中国区优惠", {"specials": 1}),
        ("new_releases", "中国区新品", {"sort_by": "Released_DESC"}),
    ]
    for category_id, source, search_params in backup_sources:
        for item in get_store_search_items(search_params):
            candidates.setdefault(item["id"], (item, source, category_id, False))
    games = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(get_store_game_details, item, source, category_id, include_reviews)
            for item, source, category_id, include_reviews in candidates.values()
        ]
        for future in as_completed(futures):
            try:
                game = future.result()
                if game:
                    games.append(game)
            except (requests.RequestException, ValueError, TypeError, AttributeError):
                continue
    return games


def refresh_store_catalog():
    games = build_store_catalog()
    if len(games) < MIN_CATALOG_SIZE:
        raise RuntimeError(f"只获取到 {len(games)} 个有效商店条目，保留现有缓存。")
    CATALOG_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {"generated_at": datetime.now(timezone.utc).isoformat(), "games": games}
    temporary_path = CATALOG_SNAPSHOT_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(CATALOG_SNAPSHOT_PATH)
    store_catalog_cache.update(modified_at=CATALOG_SNAPSHOT_PATH.stat().st_mtime, games=games)
    return snapshot


def get_store_catalog():
    if not CATALOG_SNAPSHOT_PATH.exists():
        return CATALOG
    modified_at = CATALOG_SNAPSHOT_PATH.stat().st_mtime
    if store_catalog_cache["modified_at"] == modified_at:
        return store_catalog_cache["games"]
    try:
        snapshot = json.loads(CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        games = snapshot.get("games", [])
        if len(games) < MIN_CATALOG_SIZE:
            return CATALOG
        store_catalog_cache.update(modified_at=modified_at, games=games)
        return games
    except (OSError, ValueError, TypeError):
        return CATALOG


def build_preference_profile(games):
    ranked_games = sorted(games, key=lambda game: game.get("playtime_forever", 0), reverse=True)
    played_games = [game for game in ranked_games if game.get("playtime_forever", 0) >= 120]
    preference_games = played_games[:25]
    signals = Counter()
    evidence = {}
    genre_keywords = {
        "rpg": ["elder", "witcher", "fallout", "persona", "final fantasy", "baldur", "cyberpunk", "divinity"],
        "action": ["doom", "counter", "call of duty", "souls", "devil may cry", "monster hunter", "yakuza"],
        "simulation": ["farm", "city", "simulator", "tycoon", "valley", "factorio", "house flipper"],
        "strategy": ["civilization", "total war", "strategy", "crusader", "xcom", "age of empires", "rimworld"],
        "indie": ["hollow knight", "terraria", "undertale", "celeste", "dead cells", "slay the spire"],
        "multiplayer": ["counter-strike", "dota", "apex", "overwatch", "rainbow six", "left 4 dead", "payday"],
        "adventure": ["tomb raider", "uncharted", "life is strange", "resident evil", "assassin"],
    }
    for rank, owned_game in enumerate(preference_games, start=1):
        name = owned_game.get("name", "")
        minutes = owned_game.get("playtime_forever", 0)
        weight = max(1, 8 - rank // 4) + min(6, minutes // 600)
        for genre, keywords in genre_keywords.items():
            if any(keyword in name.lower() for keyword in keywords):
                signals[genre] += weight
                evidence.setdefault(genre, []).append({
                    "app_id": owned_game["appid"], "name": name, "hours": round(minutes / 60, 1)
                })
    return signals, evidence, len(preference_games)


def choose_evidence(evidence, genres, evidence_use_counts):
    selected = []
    for genre in genres:
        options = [game for game in evidence.get(genre, []) if game["app_id"] not in {item["app_id"] for item in selected}]
        if options:
            weights = [1 / (1 + evidence_use_counts.get(game["app_id"], 0)) for game in options]
            selected.append(random.choices(options, weights=weights, k=1)[0])
    return selected[:2]


def recommend(games, excluded_ids=None, evidence_use_counts=None, priority="balanced", candidates=None):
    owned_ids = {game["appid"] for game in games}
    excluded_ids = set(excluded_ids or [])
    evidence_use_counts = Counter(evidence_use_counts or {})
    signals, evidence, preference_sample_size = build_preference_profile(games)

    results = []
    for game in candidates or CATALOG:
        if game["app_id"] in owned_ids or game["app_id"] in excluded_ids:
            continue
        matched_genres = [genre for genre in game["genres"] if signals[genre] > 0]
        score = sum(signals[genre] for genre in game["genres"])
        if priority != "balanced" and game.get("store_category") == priority:
            score += 30
        if matched_genres:
            reason = ""
        else:
            reason = f"这款{game['store_source'] if game.get('store_source') else '评价稳定的'}{game['genres'][0]}游戏，能为现有游戏库补上一种新体验；{game['price_note']}。"
        results.append({**game, "score": score, "reason": reason, "matched_genres": matched_genres, "evidence_app_ids": []})
    ranked = sorted(results, key=lambda game: -game["score"])
    if not ranked:
        if priority == "top_sellers":
            raise ValueError("热销和高评价精选中都没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        raise ValueError("当前商店候选已全部看过。请稍后再试，或重新开始一次查询。")
    # Hot sellers are a shallow live storefront list. Once it is exhausted, fall
    # back to the deeper high-rated pool without relabeling those games as hot.
    if priority == "top_sellers":
        pool = [game for game in ranked if game.get("store_category") == priority]
        if not pool:
            pool = [game for game in ranked if game.get("store_category") == "highly_rated"]
        if not pool:
            raise ValueError("热销和高评价精选中都没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        pool = pool[:12]
    elif priority != "balanced":
        pool = [game for game in ranked if game.get("store_category") == priority]
        if not pool:
            raise ValueError("该商店分类中没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        pool = pool[:12]
    else:
        established = [game for game in ranked if game.get("store_category") in {"top_sellers", "specials", "highly_rated"}]
        new_releases = [game for game in ranked if game.get("store_category") == "new_releases"]
        using_new_release_fallback = not established
        if using_new_release_fallback:
            # Some large libraries already contain every mature candidate. Offer a
            # small discovery batch instead of failing the first search outright.
            pool = new_releases[:12]
        else:
            # New releases are exploratory in balanced mode: no more than one per batch.
            pool = established[:12] + new_releases[:6]
    target_count = min(2, len(pool)) if priority == "balanced" and using_new_release_fallback else (min(4, len(established) + min(1, len(new_releases))) if priority == "balanced" else min(4, len(pool)))
    weights = [
        max(1, game["score"] + 2) * (0.22 if priority == "balanced" and game.get("store_category") == "new_releases" else 1)
        for game in pool
    ]
    selection = []
    new_release_count = 0
    while pool and len(selection) < target_count:
        chosen = random.choices(pool, weights=weights, k=1)[0]
        if chosen["matched_genres"]:
            reason_evidence = choose_evidence(evidence, chosen["matched_genres"], evidence_use_counts)
            labels = "、".join(chosen["matched_genres"])
            if reason_evidence:
                examples = "、".join(f"{item['name']}（{item['hours']} 小时）" for item in reason_evidence)
                chosen["reason"] = f"高游玩时长游戏《{examples}》显示他偏好{labels}体验；{chosen['price_note']}。"
            else:
                chosen["reason"] = f"他的高游玩时长游戏整体偏好{labels}体验；{chosen['price_note']}。"
            chosen["evidence_app_ids"] = [item["app_id"] for item in reason_evidence]
            evidence_use_counts.update(chosen["evidence_app_ids"])
        selection.append(chosen)
        if priority == "balanced" and chosen.get("store_category") == "new_releases":
            new_release_count += 1
        index = pool.index(chosen)
        pool.pop(index)
        weights.pop(index)
        if priority == "balanced" and not using_new_release_fallback and new_release_count >= 1:
            pool_and_weights = [(game, weight) for game, weight in zip(pool, weights) if game.get("store_category") != "new_releases"]
            pool = [game for game, _ in pool_and_weights]
            weights = [weight for _, weight in pool_and_weights]
    return selection, preference_sample_size


@app.get("/")
def index():
    return render_template("index.html", server_managed_api_key=bool(os.environ.get("STEAM_API_KEY")))


@app.post("/api/recommendations")
def recommendations():
    payload = request.get_json(silent=True, force=True) or {}
    api_key = os.environ.get("STEAM_API_KEY") or payload.get("api_key", "").strip()
    if not api_key:
        return jsonify(error="请填写 Steam Web API 密钥，或在服务器设置 STEAM_API_KEY。"), 400

    profile_input = payload.get("profile", "")
    try:
        steam_id = resolve_steam_id(profile_input, api_key)
        profile, games = get_profile_and_library(steam_id, api_key)
        excluded_ids = [int(app_id) for app_id in payload.get("exclude_app_ids", []) if str(app_id).isdigit()]
        evidence_use_counts = {
            int(app_id): int(count) for app_id, count in payload.get("evidence_use_counts", {}).items()
            if str(app_id).isdigit() and isinstance(count, int) and count >= 0
        }
        priority = payload.get("priority", "balanced")
        if priority not in {"balanced", "new_releases", "specials", "top_sellers"}:
            priority = "balanced"
        try:
            candidates = get_store_catalog()
        except requests.RequestException:
            candidates = CATALOG
        recommendations, preference_sample_size = recommend(games, excluded_ids, evidence_use_counts, priority, candidates)
        return jsonify(
            profile={"name": profile.get("personaname", "Steam 玩家"), "avatar": profile.get("avatarfull", "")},
            library_size=len(games),
            preference_sample_size=preference_sample_size,
            recommendations=recommendations,
        )
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except requests.RequestException:
        return jsonify(error="连接 Steam 时发生问题，请稍后重试。"), 502


if __name__ == "__main__":
    app.run(debug=True)
