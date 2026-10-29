# 游戏资料平台 · 第一步：IGDB 2025 数据采集

每日采集、Hermes 监督、GitHub 数据包发布与客户端自动更新见 [docs/DATA_UPDATES.md](DATA_UPDATES.md)。

目标：Windows 本地开发，整个项目使用 Git。当前只实现数据采集；网页、桌面、Steam、AI 后续逐步加入。

## 年份口径与评分

本阶段“2025 年游戏”指 IGDB `first_release_date` 位于 UTC 的 2025-01-01（含）到 2026-01-01（不含）。
包括 IGDB 在这一范围内的所有游戏条目，不按评分、游戏类型、平台、知名度过滤。
未评分条目照常保存，评分空值不转换成 0。
它不等于“任何平台在2025年推出过的版本”；这种口径要另用发售记录定义，后续添加。
IGDB 自身缺失发售日期或未收录的游戏不能通过本次查询补齐。

保留六个评分字段：

| 字段 | 作用 |
|---|---|
| `rating` | IGDB 用户评分，保留原数值 |
| `rating_count` | 对应用户评分人数 |
| `aggregated_rating` | 媒体聚合评分 |
| `aggregated_rating_count` | 媒体评分数量 |
| `total_rating` | IGDB 提供的综合评分 |
| `total_rating_count` | 对应评分数量 |

评分按 IGDB 的 0–100 数值保存，不换算成 IGN 0–10 分。
同时保存游戏完整原始 JSON，以及展开的平台、类型、封面、公司和发售记录，便于未来增加字段。
“完整原始 JSON”指本次 API 查询返回的内容；其他关联实体的完整资料仍需分别查询。

## Windows 开始使用

将完整项目解压到 `F:\Projects\game-platform`。ZIP 包含 `.git` 目录及已创建的提交，请保持目录结构。
原来的 `F:\Projects\game-data` 保留，不覆盖。

先安装 Git for Windows（如果还没有）：https://git-scm.com/downloads/win

```powershell
cd "F:\Projects\game-platform"
git --version
git status
git log --oneline
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

如果你安装的是另一个 Python 版本，替换创建环境的 `3.14`。支持 Python 3.12 及以上。
依赖安装需要网络；采集运行只需要 Python，不需要 Node、浏览器或 OpenClaw。

## 获取 IGDB 凭据

IGDB 使用 Twitch 的 Client ID 和 Client Secret 获取 app access token。

1. 打开 https://dev.twitch.tv/console/apps ，登录 Twitch。
2. 注册应用。按当前控制台要求填写应用名称、类别以及本地 OAuth Redirect URL，例如 `http://localhost`。
3. 本阶段使用后端 Client Credentials 流程；如果控制台要求选择客户端类型，选能生成 Secret 的 Confidential 类型。
4. 在应用管理中取得 Client ID，生成 Client Secret。
5. 在项目目录运行本地配置脚本：

```powershell
.\.venv\Scripts\python.exe .\scripts\configure_igdb.py
```

Secret 输入不显示。凭据写入本机 `.env`；Git 默认忽略它。不要上传 `.env` 或把 Secret 发到聊天中。
脚本不会永久保存 access token。Twitch 控制台字段可能调整，以实际界面为准。

## 先验证，再采全年

先抓取一页验证认证和字段：

```powershell
.\.venv\Scripts\python.exe -m game_platform.collect_igdb --year 2025 --page-size 20 --max-pages 1
```

测试完成会标记 paused，因为只读了一页，不会宣称全年完成。
接着运行全年采集（不加 max-pages）：

```powershell
.\.venv\Scripts\python.exe -m game_platform.collect_igdb --year 2025
```

默认自动恢复中断或失败的采集。每页事务提交；重跑不会重复插入同一 IGDB ID。
达到空页后检查计数；不会仅凭短页就提前停止。
Ctrl+C 暂停后重跑同一命令继续。

已经完成后再次运行会建立新扫描并更新评分。也可显式重新开始：

```powershell
.\.venv\Scripts\python.exe -m game_platform.collect_igdb --year 2025 --fresh
```

## 输出

- `data\igdb.sqlite3`：结构化字段、评分索引、原始 JSON、采集批次与进度。
- `data\exports\igdb_2025.csv`：可用 Excel 打开的 UTF-8 表格，含六个评分字段。
- `data\exports\igdb_2025.jsonl`：本次采集的原始 JSON，每行一个游戏。
- `data\reports\igdb_2025_report.json`：年份范围、计数校验、评分覆盖和停止状态。

CSV 中评分字段空白表示来源没有评分，不代表零分。
每次导出以该扫描的 ID 清单为准，不把旧扫描的多余记录混入结果。
数据文件和凭据均不进入 Git。

报告 `status=completed` 且 `count_check_passed=true` 表示本次所设年份、最大ID范围的接口计数与本地去重数量一致。
这不是对“世界上2025年全部电子游戏”的完整性证明。来源同时更新时可能需要重扫核验。
`needs_reconciliation` 表示数量变化或不一致；不要把这种结果当成完成。

## Git 工作方式

当前主分支是 main。首次提交作者是生成项目的 Codex；后续设置你自己的仓库身份：

```powershell
git config user.name "你的名字"
git config user.email "你的邮箱"
```

修改代码并检查测试后：

```powershell
.\.venv\Scripts\python.exe -m pytest
git status
git add src tests docs README.md pyproject.toml scripts .gitignore .gitattributes .env.example
git commit -m "描述本次修改"
```

当前仓库不绑定 GitHub，也不会自动上传。后续需要远程备份时再添加 remote。
整个产品继续在此仓库开发；旧 IGN 脚本后续迁入来源模块。

## 后续评分筛选示例

数据库已保存原始评分和评分人数，可使用：

```sql
SELECT igdb_id, name, rating, rating_count
FROM igdb_games
WHERE rating >= 80 AND rating_count >= 10
ORDER BY rating DESC;
```

最低评分人数是筛选条件，不是采集条件。

## 验证范围与文档

自动化测试覆盖完整分页、未评分游戏、零分、评分更新、断点续跑、页内原子性、计数不一致和认证错误隐藏密钥。
未使用你的实际凭据，真实认证及全年采集需要在本机运行验证。

官方文档：
- https://api-docs.igdb.com/
- https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#client-credentials-grant-flow
# 分类字段升级（v02）

全年采集完成后，执行本地字段迁移与分类字典同步：

```powershell
.\.venv\Scripts\python.exe -m game_platform.classify_games --year 2025 --sync-types
```

数据库先自动备份，再从已有原始 JSON 回填分类。不重新采集游戏。默认展示规则、字段含义和查询命令见 [docs/CLASSIFICATION.md](CLASSIFICATION.md)。
资料库统一为一个入口；后续 IGN 评测作为对应游戏的详情内容，见 [docs/ARCHITECTURE.md](ARCHITECTURE.md)。

## FastAPI 游戏列表（v03）

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn game_platform.api:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://127.0.0.1:8000/docs。游戏列表、筛选参数和验收地址见 [docs/API.md](API.md)。

详情接口 v04：GET /api/v1/games/{igdb_id}，返回简介、封面链接、别名、公司及版本关联。更新后重启服务即可，不需要数据库迁移。

## Vue 3 页面（v05）

已实现炭灰深色、蓝色强调、封面卡片的本地游戏目录和详情页。启动后端后，在frontend目录执行：

```powershell
npm.cmd ci
npm.cmd run dev
```

浏览器打开 http://127.0.0.1:5173/ 。Node安装、筛选操作和构建说明见 [docs/FRONTEND.md](FRONTEND.md)。

## IGN 评测关联（v06）

已有IGN评测可以导入同一SQLite数据库，确认对应IGDB游戏后在详情页逐篇显示评分和文章链接。
原始IGDB评分不变，多篇IGN评测不合成为一个分数。导入和确认前自动备份，支持重复导入、人工改绑与解除。
操作、候选规则和数据结构见 [docs/IGN.md](IGN.md)。
