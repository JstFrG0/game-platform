# 本地资料库分类（schema v2）

目标：保留全部来源记录，让默认游戏列表更适合浏览。迁移从 igdb_games.raw_json 回填，不重抓游戏，不修改评分和原始 JSON。

## 字段分工

| 字段/表 | 含义 | 规则 |
|---|---|---|
| game_type_id | 新版 IGDB 条目类别 ID | 不用旧 category 编号解释，查 igdb_game_types 字典 |
| legacy_category | 旧 category 枚举 | 仅 game_type 缺失时用于兼容分类；0 是本体，不是空值 |
| game_type_key | 本地稳定分类键 | 如 main_game、remake；未确认为 unknown |
| classification_source | 分类依据 | 字典、嵌入类别名称、旧枚举、缺失或未解析 |
| genres_json / game_tags(kind=genre) | RPG、冒险等玩法类型 | 可以多个，不据此推断本体/DLC |
| platforms_json / game_tags(kind=platform) | 平台 | 名称用于显示，ID 用于精确筛选 |
| game_modes_json / game_tags(kind=mode) | 单人、多人、合作等模式 | 缺失表示未知；支持单人不等于只能单人 |
| parent_game_id | 所属本体或合集的来源 ID | 对应游戏可能不在 2025 年采集范围，不强制外键存在 |
| version_parent_id | 特别版本所对应的来源游戏 ID | 不自动合并记录 |
| game_status_id / legacy_status | 新/旧发售状态 | 保留来源值，当前不加入默认筛选；新版状态 ID 还未做字典解释 |
| rating / rating_count | IGDB 用户评分及人数 | 评分0～100，缺失为 NULL，真实0保留 |
| aggregated_rating / aggregated_rating_count | 媒体汇总评分及数量 | 与用户评分、IGN 评分分别展示 |
| total_rating / total_rating_count | IGDB 综合评分及数量 | 不作为 IGN 评分 |

原来的平台、类型名称 JSON 保留；新增 game_tags 提供有索引的按 ID 查询。不把分号拼接文字用于筛选。

## 默认与可选展示

- default：main_game（本体）、remake（重制）、remaster（高清复刻）、standalone_expansion（独立扩展）。
- all：全部条目，包括 DLC、扩展包、合集、模组、章节、季、扩充版、移植、分支、内容包、更新和待分类。
- unknown：仅待分类；始终保留，可单独检查。

v02.1：IGDB 字典名称 `Pack / Addon` 对应 `pack`（内容包），归入可选展示。
重新运行迁移会用当前映射规则重新解析已保存的字典，不需要 --sync-types 或网络请求。

移植、扩充版等目前属于可选展示。这是可调整的浏览规则，不代表这些条目不是游戏。
default 不设置评分、评分人数或平台门槛。最低用户评分和评分人数仅在用户主动指定时应用。
指定最低评分会排除 NULL；不把无评分变成0。指定最低评分人数时也要求 rating 存在。
当前查询以 IGDB first_release_date 的 UTC 年份为准，不推断各平台发售年。

## 执行

关闭采集程序后，在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m game_platform.classify_games --year 2025 --sync-types
```

每次自动用 SQLite backup API 创建 data/backups/igdb_before_classification_*.sqlite3（包含 WAL 中已提交数据）。
结构变更、回填和 schema_versions 注册为事务；失败回滚。迁移可重复执行。
--sync-types 只请求分类字典 /game_types，不重新请求 /games。
字典分页完整获取后才更新；失败保留已有字典。迁移成功但字典同步失败时可以原命令重试。
不加 --sync-types 可以完全离线迁移；现代 ID 没有字典时可能大量显示待分类。
如果原始数据没有 game_type 和 category，两者都缺失则仍是待分类；不能仅通过字典补出不存在的来源事实。

输出：
- data/reports/igdb_2025_classification_report.json
- data/exports/igdb_2025_classified.csv（完整条目，不仅默认展示条目）

原来的采集报告和 CSV 不覆盖。数据库评分、采集断点、run_members 保持原样。
升级后继续采集也会同步写入分类字段和标签索引。

```powershell
# 默认列表预览，输出总匹配数量和前20条
.\.venv\Scripts\python.exe -m game_platform.query_games --year 2025
# 全部 / 待分类
.\.venv\Scripts\python.exe -m game_platform.query_games --scope all
.\.venv\Scripts\python.exe -m game_platform.query_games --scope unknown
# 查看可用的平台、玩法类型、游玩模式 ID
.\.venv\Scripts\python.exe -m game_platform.query_games --tags
# 示例：Windows 平台 + 用户评分至少70 + 评分人数至少10
.\.venv\Scripts\python.exe -m game_platform.query_games --platform-id 6 --min-rating 70 --min-rating-count 10
```

query_games 用只读连接，不修改数据库。select_games 是后续 FastAPI 可复用的查询入口。

来源文档：https://api-docs.igdb.com/（Games、Game Type）。新版 game_type 是引用 ID，category 已弃用。
