# Gift Scout

一个根据公开 Steam 游戏库推荐礼物的 Flask 网页应用。它不会保存个人资料链接或游戏库。

## 本地运行

```bash
cd /pct_ids/users/z005a7xf/steam-gift-recommender
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export STEAM_API_KEY="你的 Steam Web API 密钥"
flask --app app run
```

打开终端显示的本地地址，通常是 `http://127.0.0.1:5000`。

## 所需资料

1. 一个 Steam Web API 密钥：在 <https://steamcommunity.com/dev/apikey> 使用自己的 Steam 账号申请。
2. 待分析用户的公开 Steam 个人资料 URL 或 17 位 SteamID；其“游戏详情”也必须设置为公开。

本地个人使用时，也可在网页的密码输入框中临时填写密钥；服务不会保存它。对于公开部署，不应让访客提交自己的密钥，应由服务器通过环境变量 `STEAM_API_KEY` 管理。不要把密钥写入代码或提交到 Git。

## 商店候选缓存

用户查询只读取本地商店快照，所以点击推荐不会同步请求大量 Steam 商品详情。单独运行下面的更新器以生成或更新中国区候选池；它会低并发地读取当前热销，以及高评价、优惠和新品的多页搜索结果，并仅在成功获得至少 150 款有效候选时替换旧缓存。

```bash
cd /pct_ids/users/z005a7xf/steam-gift-recommender
. .venv/bin/activate
python update_catalog.py
```

可用 cron（Linux 定时任务）每天运行一次该命令。更新失败时，网站继续使用上一次成功的快照；还没有快照时会暂时使用内置候选目录。

## 公开部署

项目包含 `render.yaml`，可直接作为 Render Blueprint 部署。部署时在 Render 的 Environment 中新增私密变量 `STEAM_API_KEY`，填写一个新生成的 Steam Web API 密钥。生产页面会自动隐藏 API 密钥输入框，访问者只需输入公开 Steam 个人资料链接。

`.github/workflows/update-store-catalog.yml` 会在每天 UTC 03:15 自动运行目录更新器，并把更新后的 `data/store_catalog_cn.json` 提交回仓库。Render 看到这次提交后会重新部署，因此网站读取的中国区商店候选每天自动更新，无需手动运行命令。

## 当前范围与下一版

当前版本根据拥有游戏的名称推断偏好，在精选目录中排除已拥有游戏后推荐。下一版可接入 Steam Store 商品数据，将固定目录扩展为全量候选，并显示所在地区的实时价格和折扣。