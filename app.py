import json
import math
import os
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

STEAM_API_BASE = "https://api.steampowered.com"
STEAM_STORE_BASE = "https://store.steampowered.com"
STORE_HEADERS = {"User-Agent": "Gift Scout/1.0 (+local Steam gift recommender)"}
STORE_CACHE_SECONDS = 1800
CATALOG_SNAPSHOT_PATH = Path(app.root_path) / "data" / "store_catalog_cn.json"
LABEL_POLICY_PATH = Path(app.root_path) / "golden_labels" / "label_policy.json"
APP_TAG_CACHE_PATH = Path(app.root_path) / "data" / "steam_app_tag_cache.json"
store_catalog_cache = {"modified_at": None, "games": []}
live_top_seller_cache = {"updated_at": 0, "app_ids": set()}
SEARCH_PAGE_SIZE = 50
SEARCH_PAGE_DELAY_SECONDS = 1.5
TOP_SELLER_PAGE_COUNT = 8
POPULAR_NEW_PAGE_COUNT = 7
RECENT_RELEASE_PAGE_COUNT = 12
SPECIALS_PAGE_COUNT = 4
MIN_CATALOG_SIZE = 150
MIN_NEW_RELEASE_CATALOG_SIZE = 150
NEW_RELEASE_WINDOW_DAYS = 31
PREFERENCE_GAME_LIMIT = 60
MIN_PREFERENCE_PLAYTIME_MINUTES = 120
MAX_LABELS_PER_REPRESENTATIVE_GAME = 3
CORE_TAG_RANK_LIMIT = 5
SOFT_TAG_RANK_LIMIT = 10
ACHIEVEMENT_CACHE_SECONDS = 3600
REVIEW_CACHE_SECONDS = 21600
achievement_cache = {}
review_cache = {}
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


def get_game_price(game):
    if "final_price" in game:
        return game["final_price"] / 100
    match = re.search(r"¥([0-9.]+)", game.get("price_note", ""))
    return float(match.group(1)) if match else None


def parse_release_date(release_date):
    for date_format in ("%d %b, %Y", "%b %d, %Y", "%Y 年 %m 月 %d 日", "%Y年%m月%d日"):
        try:
            return datetime.strptime(release_date, date_format).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def is_recent_release(release_date, now=None):
    released_at = parse_release_date(release_date)
    if not released_at:
        return False
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=NEW_RELEASE_WINDOW_DAYS) <= released_at <= now + timedelta(days=1)


def store_json(path, params):
    last_error = None
    for attempt in range(5):
        try:
            response = requests.get(f"{STEAM_STORE_BASE}{path}", params=params, headers=STORE_HEADERS, timeout=12)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            raise ValueError("Steam 返回的不是 JSON 对象。")
        except (requests.RequestException, ValueError, TypeError) as error:
            last_error = error
            if attempt < 4:
                sleep(1.5 * (attempt + 1))
    raise requests.RequestException(f"Steam 商店请求失败：{last_error}")


def get_store_game_details(item, source, category_id, include_reviews=True, store_categories=None):
    app_id = item["id"]
    tag_ids = item.get("tag_ids") or fetch_app_tag_ids(app_id)
    payload = store_json("/api/appdetails", {"appids": app_id, "cc": "cn", "l": "schinese"})
    entry = payload.get(str(app_id), {})
    data = entry.get("data", {}) if entry.get("success") else {}
    if data.get("type") != "game":
        return None
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
    release_date = data.get("release_date", {}).get("date", "发售日期待定")
    categories = set(store_categories or [category_id])
    if "new_releases" in categories and not is_recent_release(release_date):
        categories.remove("new_releases")
    if not categories:
        return None
    primary_category = category_id if category_id in categories else sorted(categories)[0]
    return {
        "app_id": app_id,
        "name": data.get("name", item.get("name", f"Steam App {app_id}")),
        "game_type": data["type"],
        "genres": genres,
        "tag_ids": tag_ids,
        "final_price": final_price,
        "original_price": original_price,
        "discount_percent": discount_percent,
        "price_note": price_note,
        "image": item.get("header_image", data.get("header_image", "")),
        "store_source": source,
        "store_category": primary_category,
        "store_categories": sorted(categories),
        "release_date": release_date,
        "positive_rate": positive_rate,
        "review_count": review_count,
    }


def get_store_search_items(search_params, page_count):
    items = {}
    for page in range(page_count):
        if page:
            sleep(SEARCH_PAGE_DELAY_SECONDS)
        payload = store_json(
            "/search/results/",
            {
                "query": "", "start": page * SEARCH_PAGE_SIZE, "count": SEARCH_PAGE_SIZE,
                "dynamic_data": "", "infinite": 1, "cc": "cn", **search_params,
            },
        )
        page_items = re.findall(
            r'data-ds-appid=\\?"(\d+)"[^>]*data-ds-tagids=\\?"(\[[^\"]+\])',
            payload.get("results_html", ""),
        )
        for app_id, tag_ids in page_items:
            items.setdefault(int(app_id), {"id": int(app_id), "tag_ids": json.loads(tag_ids)})
    return list(items.values())


def get_live_top_seller_ids():
    if monotonic() - live_top_seller_cache["updated_at"] < STORE_CACHE_SECONDS:
        return live_top_seller_cache["app_ids"]
    try:
        app_ids = {item["id"] for item in get_store_search_items({"filter": "topsellers"}, 1)}
    except requests.RequestException:
        return live_top_seller_cache["app_ids"]
    live_top_seller_cache.update(updated_at=monotonic(), app_ids=app_ids)
    return app_ids


def build_store_catalog():
    data = store_json("/api/featuredcategories/", {"cc": "cn", "l": "schinese"})
    source_names = {"top_sellers": "中国区热销", "specials": "中国区优惠", "new_releases": "中国区新品"}
    candidates = {}

    def add_candidate(item, source, category_id, include_reviews):
        existing = candidates.get(item["id"])
        if existing:
            existing["categories"].add(category_id)
            existing["include_reviews"] = existing["include_reviews"] or include_reviews
            existing["item"].setdefault("tag_ids", item.get("tag_ids", []))
            return
        candidates[item["id"]] = {
            "item": item,
            "source": source,
            "primary_category": category_id,
            "categories": {category_id},
            "include_reviews": include_reviews,
        }

    for category_id, source in source_names.items():
        for item in data.get(category_id, {}).get("items", []):
            if item.get("type") in (0, "app"):
                add_candidate(item, source, category_id, True)
    backup_sources = [
        ("top_sellers", "中国区热销", {"filter": "topsellers"}, TOP_SELLER_PAGE_COUNT),
        ("highly_rated", "高评价精选", {"sort_by": "Reviews_DESC", "supportedlang": "schinese"}, SPECIALS_PAGE_COUNT),
        ("specials", "中国区优惠", {"specials": 1}, SPECIALS_PAGE_COUNT),
        ("new_releases", "中国区热门新品", {"filter": "popularnew", "sort_by": "Released_DESC", "os": "win"}, POPULAR_NEW_PAGE_COUNT),
        ("new_releases", "中国区最新发售", {"sort_by": "Released_DESC", "os": "win"}, RECENT_RELEASE_PAGE_COUNT),
    ]
    for category_id, source, search_params, page_count in backup_sources:
        for item in get_store_search_items(search_params, page_count):
            add_candidate(item, source, category_id, False)
    games = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                get_store_game_details,
                candidate["item"],
                candidate["source"],
                candidate["primary_category"],
                candidate["include_reviews"],
                sorted(candidate["categories"]),
            )
            for candidate in candidates.values()
        ]
        for future in as_completed(futures):
            try:
                game = future.result()
                if game and game.get("tag_ids"):
                    games.append(game)
            except (requests.RequestException, ValueError, TypeError, AttributeError):
                continue
    return games


def refresh_store_catalog():
    games = build_store_catalog()
    if len(games) < MIN_CATALOG_SIZE:
        raise RuntimeError(f"只获取到 {len(games)} 个有效商店条目，保留现有缓存。")
    new_release_count = sum("new_releases" in game.get("store_categories", [game.get("store_category")]) for game in games)
    if new_release_count < MIN_NEW_RELEASE_CATALOG_SIZE:
        raise RuntimeError(f"只获取到 {new_release_count} 个新品条目，低于最低要求 {MIN_NEW_RELEASE_CATALOG_SIZE}，保留现有缓存。")
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


def load_label_policy():
    with LABEL_POLICY_PATH.open(encoding="utf-8") as policy_file:
        return json.load(policy_file)


def load_tag_cache():
    try:
        return json.loads(APP_TAG_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def fetch_app_tag_ids(app_id):
    page = requests.get(
        f"{STEAM_STORE_BASE}/app/{app_id}/",
        params={"cc": "cn", "l": "schinese"},
        headers=STORE_HEADERS,
        timeout=12,
    )
    page.raise_for_status()
    match = re.search(r'data-ds-tagids="\[([0-9,]+)\]', page.text)
    return [int(tag_id) for tag_id in match.group(1).split(",")] if match else []


def fetch_achievement_summary(api_key, steam_id, app_id):
    payload = steam_get(
        "/ISteamUserStats/GetPlayerAchievements/v1/",
        {"key": api_key, "steamid": steam_id, "appid": app_id},
    )
    achievements = payload.get("playerstats", {}).get("achievements", [])
    if not achievements:
        return None
    completed = sum(achievement.get("achieved", 0) for achievement in achievements)
    total = len(achievements)
    return {"completed": completed, "total": total, "ratio": completed / total}


def get_achievement_summary(api_key, steam_id, app_id):
    cache_key = (steam_id, app_id)
    cached = achievement_cache.get(cache_key)
    if cached and monotonic() - cached["updated_at"] < ACHIEVEMENT_CACHE_SECONDS:
        return cached["summary"]
    try:
        summary = fetch_achievement_summary(api_key, steam_id, app_id)
    except requests.RequestException:
        summary = None
    achievement_cache[cache_key] = {"updated_at": monotonic(), "summary": summary}
    return summary


def get_review_summary(app_id):
    cached = review_cache.get(app_id)
    if cached and monotonic() - cached["updated_at"] < REVIEW_CACHE_SECONDS:
        return cached["summary"]
    try:
        query_summary = store_json(
            f"/appreviews/{app_id}", {"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0}
        ).get("query_summary", {})
        review_count = query_summary.get("total_reviews", 0)
        summary = {
            "review_count": review_count,
            "positive_rate": round(100 * query_summary.get("total_positive", 0) / review_count) if review_count else None,
        }
    except requests.RequestException:
        summary = None
    review_cache[app_id] = {"updated_at": monotonic(), "summary": summary}
    return summary


def select_engagement_candidates(games):
    eligible_games = [game for game in games if game.get("playtime_forever", 0) >= MIN_PREFERENCE_PLAYTIME_MINUTES]
    by_time = sorted(eligible_games, key=lambda game: game.get("playtime_forever", 0), reverse=True)[:40]
    mid_length = sorted(
        [game for game in eligible_games if 600 <= game.get("playtime_forever", 0) <= 7200],
        key=lambda game: game.get("playtime_forever", 0),
        reverse=True,
    )[:30]
    short_length = sorted(
        [game for game in eligible_games if MIN_PREFERENCE_PLAYTIME_MINUTES <= game.get("playtime_forever", 0) < 600],
        key=lambda game: game.get("playtime_forever", 0),
        reverse=True,
    )[:30]
    recent = sorted(eligible_games, key=lambda game: game.get("rtime_last_played", 0), reverse=True)[:20]
    candidates = {game["appid"]: game for game in by_time + mid_length + short_length + recent}
    return list(candidates.values())


def select_representative_games(games):
    buckets = [
        (lambda game: game.get("playtime_forever", 0) > 7200, 20),
        (lambda game: 600 <= game.get("playtime_forever", 0) <= 7200, 25),
        (lambda game: MIN_PREFERENCE_PLAYTIME_MINUTES <= game.get("playtime_forever", 0) < 600, 15),
    ]
    selected = []
    selected_ids = set()
    for predicate, limit in buckets:
        bucket = sorted(
            (game for game in games if predicate(game) and game["appid"] not in selected_ids),
            key=lambda game: game["engagement_score"],
            reverse=True,
        )[:limit]
        selected.extend(bucket)
        selected_ids.update(game["appid"] for game in bucket)
    if len(selected) < PREFERENCE_GAME_LIMIT:
        remaining = sorted(
            (game for game in games if game["appid"] not in selected_ids),
            key=lambda game: game["engagement_score"],
            reverse=True,
        )[:PREFERENCE_GAME_LIMIT - len(selected)]
        selected.extend(remaining)
    return selected


def calculate_engagement(game, achievement_summary, now):
    hours = game.get("playtime_forever", 0) / 60
    completion = 0
    if achievement_summary:
        reliability = min(1, achievement_summary["total"] / 20)
        completion = achievement_summary["ratio"] * reliability
    last_played = game.get("rtime_last_played", 0)
    days_since_played = max(0, (now - last_played) / 86400) if last_played else 3650
    recency = math.exp(-days_since_played / 180)
    return math.log1p(hours) + 2 * completion + recency


def enrich_preference_games_with_tags(games):
    preference_games = games[:PREFERENCE_GAME_LIMIT]
    cache = load_tag_cache()
    # Empty entries were commonly written during transient Steam rate limits.
    # Retry them on later requests rather than treating a failed fetch as data.
    missing_ids = [game["appid"] for game in preference_games if not cache.get(str(game["appid"]))]
    if missing_ids:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(fetch_app_tag_ids, app_id): app_id for app_id in missing_ids}
            for future in as_completed(futures):
                app_id = futures[future]
                try:
                    tag_ids = future.result()
                    if tag_ids:
                        cache[str(app_id)] = tag_ids
                except requests.RequestException:
                    continue
        APP_TAG_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        APP_TAG_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    for game in preference_games:
        game["tag_ids"] = cache.get(str(game["appid"]), [])
    return preference_games


def build_label_profile(games, policy, steam_id=None, api_key=None):
    candidate_games = select_engagement_candidates(games)
    now = datetime.now(timezone.utc).timestamp()
    if steam_id and api_key:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(get_achievement_summary, api_key, steam_id, game["appid"]): game
                for game in candidate_games
            }
            for future in as_completed(futures):
                game = futures[future]
                game["achievement_summary"] = future.result()
    for game in candidate_games:
        game["engagement_score"] = calculate_engagement(game, game.get("achievement_summary"), now)
    preference_games = select_representative_games(candidate_games)
    preference_games = enrich_preference_games_with_tags(preference_games)
    policy_groups = {
        "level_1": {int(tag_id): name for tag_id, name in policy["level_1"].items()},
        "level_2_core": {int(tag_id): name for tag_id, name in policy["level_2_core"].items()},
        "soft_preference": {int(tag_id): name for tag_id, name in policy["soft_preference"].items()},
    }
    profile = {group: {} for group in policy_groups}
    for game in preference_games:
        achievement_summary = game.get("achievement_summary")
        completion_percent = round(100 * achievement_summary["ratio"]) if achievement_summary else None
        evidence = {
            "app_id": game["appid"],
            "name": game["name"],
            "hours": round(game.get("playtime_forever", 0) / 60, 1),
            "recently_played": bool(game.get("rtime_last_played", 0) and now - game["rtime_last_played"] <= 30 * 86400),
            "achievement_percent": completion_percent,
            "achievement_completed": achievement_summary["completed"] if achievement_summary else None,
            "achievement_total": achievement_summary["total"] if achievement_summary else None,
            "engagement_score": round(game["engagement_score"], 2),
        }
        labels_contributed = 0
        for group in ("level_2_core", "level_1", "soft_preference"):
            labels = policy_groups[group]
            tag_limit = CORE_TAG_RANK_LIMIT if group == "level_2_core" else SOFT_TAG_RANK_LIMIT
            for rank, tag_id in enumerate(game.get("tag_ids", [])[:tag_limit], start=1):
                if tag_id in labels and labels_contributed < MAX_LABELS_PER_REPRESENTATIVE_GAME:
                    profile[group].setdefault(tag_id, []).append({**evidence, "tag_rank": rank})
                    labels_contributed += 1
    return profile, policy_groups, len(preference_games)


def build_preference_profile(games):
    ranked_games = sorted(games, key=lambda game: game.get("playtime_forever", 0), reverse=True)
    played_games = [game for game in ranked_games if game.get("playtime_forever", 0) >= MIN_PREFERENCE_PLAYTIME_MINUTES]
    preference_games = played_games[:PREFERENCE_GAME_LIMIT]
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


def recommend(games, excluded_ids=None, evidence_use_counts=None, priority="balanced", candidates=None, steam_id=None, api_key=None):
    owned_ids = {int(game["appid"]) for game in games if str(game.get("appid", "")).isdigit()}
    excluded_ids = set(excluded_ids or [])
    evidence_use_counts = Counter(evidence_use_counts or {})
    signals, evidence, preference_sample_size = build_preference_profile(games)
    policy = load_label_policy()
    label_profile, policy_groups, tagged_preference_sample_size = build_label_profile(games, policy, steam_id, api_key)
    excluded_candidate_tags = {int(tag_id) for tag_id in policy["exclude_from_candidates"]}
    has_label_profile = any(label_profile[group] for group in label_profile)

    results = []
    for game in candidates or CATALOG:
        if int(game["app_id"]) in owned_ids or int(game["app_id"]) in excluded_ids:
            continue
        candidate_tags = set(game.get("tag_ids", []))
        if candidate_tags & excluded_candidate_tags:
            continue
        label_matches = {}
        for group in ("level_1", "level_2_core", "soft_preference"):
            tag_limit = CORE_TAG_RANK_LIMIT if group == "level_2_core" else SOFT_TAG_RANK_LIMIT
            candidate_tag_set = set(game.get("tag_ids", [])[:tag_limit])
            label_matches[group] = [tag_id for tag_id in label_profile[group] if tag_id in candidate_tag_set]
        label_sources = {group: {} for group in ("level_1", "level_2_core", "soft_preference")}
        for group in ("level_2_core", "level_1", "soft_preference"):
            for tag_id in label_matches[group]:
                evidence_options = label_profile[group][tag_id]
                if isinstance(evidence_options, dict):
                    evidence_options = [evidence_options]
                evidence_weights = [1 / (1 + evidence_use_counts.get(item["app_id"], 0)) for item in evidence_options]
                label_sources[group][tag_id] = random.choices(evidence_options, weights=evidence_weights, k=1)[0]
        matched_label_details = {
            group: [
                {
                    "name": policy_groups[group][tag_id],
                    "source_game": label_sources[group][tag_id],
                    "candidate_tag_rank": game.get("tag_ids", []).index(tag_id) + 1,
                }
                for tag_id in label_matches[group]
            ]
            for group in ("level_1", "level_2_core", "soft_preference")
        }
        evidence_group = "level_2_core" if label_matches["level_2_core"] else ("level_1" if label_matches["level_1"] else "soft_preference")
        match_evidence = []
        for tag_id in label_matches[evidence_group]:
            source_game = label_sources[evidence_group][tag_id]
            if source_game["app_id"] not in {item["app_id"] for item in match_evidence}:
                match_evidence.append(source_game)
        match_evidence = match_evidence[:2]
        use_label_score = has_label_profile and bool(candidate_tags)
        if use_label_score:
            score = (
                policy["scoring"]["level_2_core_weight"] * len(label_matches["level_2_core"])
                + policy["scoring"]["soft_preference_weight"] * len(label_matches["soft_preference"])
                + policy["scoring"]["level_1_weight"] * len(label_matches["level_1"])
            )
            matched_genres = []
            core_matches = len(label_matches["level_2_core"])
            level_1_matches = len(label_matches["level_1"])
            if core_matches >= policy["scoring"]["high_confidence_min_level_2_core_matches"]:
                confidence = "高"
            elif core_matches == policy["scoring"]["medium_confidence"]["level_2_core_matches"] and level_1_matches >= policy["scoring"]["medium_confidence"]["min_level_1_matches"]:
                confidence = "中"
            else:
                confidence = "低"
        else:
            matched_genres = [genre for genre in game["genres"] if signals[genre] > 0]
            score = sum(signals[genre] for genre in game["genres"])
            label_matches = {"level_1": [], "level_2_core": [], "soft_preference": []}
            match_evidence = []
            matched_label_details = {"level_1": [], "level_2_core": [], "soft_preference": []}
            confidence = "基础偏好"
        if matched_genres:
            reason = ""
        else:
            reason = f"这款{game['store_source'] if game.get('store_source') else '评价稳定的'}{game['genres'][0]}游戏，能为 TA 的游戏库补上一种新体验；{game['price_note']}。"
        results.append({
            **game,
            "score": score,
            "reason": reason,
            "matched_genres": matched_genres,
            "label_matches": label_matches,
            "matched_label_details": matched_label_details,
            "match_evidence": match_evidence[:2],
            "confidence": confidence,
            "evidence_app_ids": [],
        })
    ranked = sorted(results, key=lambda game: -game["score"])
    confident_ranked = [game for game in ranked if game["confidence"] != "低"]
    if confident_ranked:
        # Preserve the quality bar for the first batch, but keep lower-confidence
        # related games available after a narrow priority pool is exhausted.
        ranked = confident_ranked + [game for game in ranked if game["confidence"] == "低"]
    if not ranked:
        if priority == "top_sellers":
            raise ValueError("热销和高评价精选中都没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        raise ValueError("当前商店候选已全部看过。请稍后再试，或重新开始一次查询。")
    # Hot sellers are a shallow live storefront list. Once it is exhausted, fall
    # back to the deeper high-rated pool without relabeling those games as hot.
    def is_in_category(game, categories):
        return bool(set(game.get("store_categories", [game.get("store_category")])) & categories)

    def is_new_release(game):
        return is_recent_release(game.get("release_date"))

    def is_recent_top_seller(game):
        return is_new_release(game) and (
            is_in_category(game, {"top_sellers"}) or game["app_id"] in live_top_seller_ids
        )

    if priority == "top_sellers":
        pool = [game for game in ranked if is_in_category(game, {"top_sellers", "highly_rated"})]
        if not pool:
            raise ValueError("热销和高评价精选中都没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        pool = pool[:12]
    elif priority == "new_releases":
        live_top_seller_ids = get_live_top_seller_ids()
        top_seller_new_releases = [game for game in ranked if is_recent_top_seller(game)]
        other_new_releases = [game for game in ranked if is_new_release(game) and not is_recent_top_seller(game)]
        pool = top_seller_new_releases[:12] + other_new_releases[:12]
        if not pool:
            raise ValueError("最近 31 天内没有更多未展示的新品。请重新开始本分类或选择其他优先级。")
        pool = pool[:12]
    elif priority != "balanced":
        pool = [game for game in ranked if is_in_category(game, {priority})]
        if not pool:
            raise ValueError("该商店分类中没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        pool = pool[:12]
    else:
        established = [game for game in ranked if is_in_category(game, {"top_sellers", "specials", "highly_rated"})]
        new_releases = [game for game in ranked if is_new_release(game)]
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
    new_release_top_seller_ids = {game["app_id"] for game in top_seller_new_releases} if priority == "new_releases" else set()
    while pool and len(selection) < target_count:
        if priority == "new_releases":
            selected_top_sellers = sum(game["app_id"] in new_release_top_seller_ids for game in selection)
            if selected_top_sellers == 0:
                eligible_indices = [index for index, game in enumerate(pool) if game["app_id"] in new_release_top_seller_ids]
            elif selected_top_sellers >= 2:
                eligible_indices = [index for index, game in enumerate(pool) if game["app_id"] not in new_release_top_seller_ids]
            else:
                eligible_indices = list(range(len(pool)))
            if not eligible_indices:
                eligible_indices = list(range(len(pool)))
            eligible_games = [pool[index] for index in eligible_indices]
            eligible_weights = [weights[index] for index in eligible_indices]
            chosen = random.choices(eligible_games, weights=eligible_weights, k=1)[0]
        else:
            chosen = random.choices(pool, weights=weights, k=1)[0]
        if chosen["label_matches"]["level_2_core"] or chosen["label_matches"]["level_1"] or chosen["label_matches"]["soft_preference"]:
            def names(group):
                return "、".join(policy_groups[group][tag_id] for tag_id in chosen["label_matches"][group]) or "无"

            chosen["reason"] = (
                f"标签匹配分 {chosen['score']}（核心 {len(chosen['label_matches']['level_2_core'])}，"
                f"软偏好 {len(chosen['label_matches']['soft_preference'])}，一级 {len(chosen['label_matches']['level_1'])}）；"
                f"核心：{names('level_2_core')}；{chosen['price_note']}。"
            )
        elif chosen["matched_genres"]:
            reason_evidence = choose_evidence(evidence, chosen["matched_genres"], evidence_use_counts)
            labels = "、".join(chosen["matched_genres"])
            if reason_evidence:
                examples = "、".join(f"{item['name']}（{item['hours']} 小时）" for item in reason_evidence)
                chosen["reason"] = f"高游玩时长游戏《{examples}》显示 TA 偏好{labels}体验；{chosen['price_note']}。"
            else:
                chosen["reason"] = f"TA 的代表游戏整体偏好{labels}体验；{chosen['price_note']}。"
            chosen["evidence_app_ids"] = [item["app_id"] for item in reason_evidence]
            evidence_use_counts.update(chosen["evidence_app_ids"])
        selection.append(chosen)
        if priority == "balanced" and is_in_category(chosen, {"new_releases"}):
            new_release_count += 1
        index = pool.index(chosen)
        pool.pop(index)
        weights.pop(index)
        if priority == "balanced" and not using_new_release_fallback and new_release_count >= 1:
            pool_and_weights = [(game, weight) for game, weight in zip(pool, weights) if not is_in_category(game, {"new_releases"})]
            pool = [game for game, _ in pool_and_weights]
            weights = [weight for _, weight in pool_and_weights]
    return selection, tagged_preference_sample_size or preference_sample_size


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
        min_price = max(0, float(payload.get("min_price", 0)))
        max_price = max(min_price, float(payload.get("max_price", 9999)))
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
        candidates = [
            game for game in candidates
            if (price := get_game_price(game)) is not None and min_price <= price <= max_price
        ]
        recycled = False
        try:
            recommendations, preference_sample_size = recommend(
                games, excluded_ids, evidence_use_counts, priority, candidates, steam_id, api_key
            )
        except ValueError:
            if not excluded_ids:
                raise
            recommendations, preference_sample_size = recommend(
                games, [], evidence_use_counts, priority, candidates, steam_id, api_key
            )
            recycled = True
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(get_review_summary, game["app_id"]): game for game in recommendations}
            for future in as_completed(futures):
                summary = future.result()
                if summary:
                    futures[future].update(summary)
        return jsonify(
            profile={"name": profile.get("personaname", "Steam 玩家"), "avatar": profile.get("avatarfull", "")},
            library_size=len(games),
            preference_sample_size=preference_sample_size,
            recommendations=recommendations,
            recycled=recycled,
        )
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except requests.RequestException:
        return jsonify(error="连接 Steam 时发生问题，请稍后重试。"), 502


if __name__ == "__main__":
    app.run(debug=True)