# 本地游戏列表 API（v03）

## 安装与启动

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn game_platform.api:app --host 127.0.0.1 --port 8000
```

预期55 passed。新版 Starlette 可能提示 httpx 测试客户端弃用警告，当前不影响测试结果或 API 运行。
保持该终端运行，浏览器打开 http://127.0.0.1:8000/docs 。点击接口、Try it out、Execute 查看响应。
按 Ctrl+C 停止服务。端口占用时把 --port 改为8001，对应网页地址也改为8001。
默认只监听本机，不需要配置 Twitch 凭据，不发起 IGDB 请求。
Swagger UI 默认从 CDN 加载资源；若文档页面加载失败，可直接访问下面的 JSON 地址检查接口。

## 接口

| GET 路径 | 返回 |
|---|---|
| /health | 数据库可读状态、schema_version、read_only |
| /api/v1/games | 筛选后总数、页码、页大小、总页数、has_next、items |
| /api/v1/filters | 本地年份、条目类别、平台、玩法类型和模式选项及数量 |
| /api/v1/games/{igdb_id} | 单个游戏详情，不受默认列表范围限制 |

完整参数说明及返回结构在 /docs 和 /openapi.json 中。

### 游戏列表参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| year | 2025 | IGDB 全球首次发售 UTC 年份，1950～2100 |
| scope | default | default / all / unknown，沿用分类规则 |
| page | 1 | 1～1,000,000；超出实际页数返回空 items，total 保持真实总数 |
| page_size | 20 | 1～100 |
| sort | release_desc | release_desc / release_asc / name_asc / rating_desc / rating_asc |
| q | 无 | 名称包含文本，最多100字符；空白忽略，%和_不作通配符 |
| game_type | 无 | 稳定分类键，例如 main_game、remake、dlc_addon、pack |
| platform_id | 无 | 按平台ID精确匹配；从 /filters 获取选项 |
| genre_id | 无 | 按玩法类型ID精确匹配 |
| mode_id | 无 | 按游玩模式ID精确匹配 |
| min_rating | 无 | 最低 IGDB 用户评分，0～100 |
| min_rating_count | 无 | 最低 IGDB 用户评分人数，非负整数 |

条件之间为 AND。game_type 与 scope 取交集，查看 DLC / 内容包时需 scope=all。
不默认限制评分或评分人数；主动指定最低评分时不包含无评分记录。
评分排序始终把 NULL 放在最后，真实0不当作缺失；排序最后用 igdb_id 打破并列，保证静态数据分页稳定。
名称搜索大小写转换依赖 SQLite 内建 lower，主要支持 ASCII 字母；原样中文文本可以包含匹配。
这是 offset 分页；采集程序同时修改数据时，不同请求间的页序可能变化。每个请求内的总数与条目使用同一读取事务。

### 返回字段

items 含 igdb_id、name、first_release_date_utc、game_type、game_type_label、platforms、genres、game_modes，以及全部六个评分/评分人数字段。

`first_release_date_utc` 在来源撤回具体发售日期时可为 `null`；此类游戏保留记录及关联，在年份列表中不再沿用旧日期，详情仍可按 ID 查询。

## 数据更新

`GET /api/v1/data-updates` 查询当前版本、自动更新开关、仓库、检查间隔、状态与结果时间。状态响应不包含 Token 或本机备份路径。

`POST /api/v1/data-updates/check` 触发一次本机后台检查，返回202；自动更新未启用时返回409，跨站调用返回403。进行中的重复请求复用同一个任务。更新失败继续使用原有本地数据库。

`/health` 的 `read_only` 指资料查询连接；后台数据更新会另开写入事务，并在安装前备份。
平台、类型、模式以 `{id,name}` 对象列表返回，名称缺失为null；评分缺失为null，前端显示“暂无评分”。
列表不返回简介、原始 JSON 和长文内容。详情接口单独读取该游戏原始资料，IGN 评测关联后续加入。

/filters 的 game_types 数量统计对应年份的全部条目，让可选类别也能被发现。
其 platforms / genres / game_modes 的数量统计对应年份和scope；并非结合列表所有条件的动态分面计数。
分类缺失/模式缺失仍保留在游戏资料中，不虚构标签。

### 本地验收地址

- http://127.0.0.1:8000/health
- http://127.0.0.1:8000/api/v1/games?year=2025 （预期total=21964）
- http://127.0.0.1:8000/api/v1/games?year=2025&scope=all （预期total=25476）
- http://127.0.0.1:8000/api/v1/games?scope=all&game_type=pack （预期total=664）
- http://127.0.0.1:8000/api/v1/games?scope=all&min_rating=0 （预期total=473）
- http://127.0.0.1:8000/api/v1/games?platform_id=6&min_rating=70&min_rating_count=10
- http://127.0.0.1:8000/api/v1/filters

上述预期数量来自已确认的2025分类报告，只适用于尚未更新的该批数据。按实际接口结果核验。

## 错误与实现约束

- 不合法查询参数返回422，错误字段明确指出失败参数。
- 数据库不存在返回503 + DATABASE_NOT_FOUND，不会偷偷创建空数据库。
- 尚未完成分类迁移返回503 + SCHEMA_NOT_READY。
- 数据库暂时无法读取返回503 + DATABASE_UNAVAILABLE；详细错误记在本地终端。
- SQLite 连接使用 mode=ro 和 query_only；接口不迁移、不修改游戏和评分。
- 不跨线程复用SQLite连接；每次请求打开并关闭自己的只读连接。
- SQL用参数化过滤与排序白名单，分页在数据库执行；每页只批量查询该页的标签。

以后加入 Vue 时再配置明确的本地 CORS 来源；当前 /docs 与 API 同源。
用户资料和 IGN 评测的写入接口将在相应阶段新增，不改变“统一资料库”的产品入口。

## 游戏详情（v04）

接口 GET /api/v1/games/{igdb_id}；ID 为正整数。没有该 ID 时返回404和 GAME_NOT_FOUND；ID格式错误返回422。
不限制年份、评分或类别：只要本地 igdb_games 有对应记录即可读取，包括 DLC 和内容包。

除列表已有的评分、平台、类别等字段，增加：

| 字段 | 内容 |
|---|---|
| summary | 简介，源于本地数据库，不自动翻译 |
| storyline | 故事简介，源于原始 JSON |
| cover_url | 原始封面 URL；// 前缀补为 https: |
| igdb_url | IGDB 游戏页面来源链接 |
| alternative_names | 已采集的别名，按原顺序去重 |
| companies | 已采集的公司 ID、名称及开发/发行角色；未知角色为null |
| parent_game | 本体/合集关联：igdb_id、name、available_locally |
| version_parent | 特别版本对应的游戏关联，同上 |
| version_title | 如 Gold Edition 的版本名称；没有则为null |
| fetched_at | 上次采集资料的 UTC 时间 |

缺失文本或链接为null；没有公司或别名时返回空列表。缺失记录不通过网络补查。
公司角色只有原始 JSON 明确提供时才返回 true/false，不通过公司名称猜测。
关联目标未被当前本地目录收录时，保留ID，name=null、available_locally=false，后续网页显示“本地未收录”。
没有关联时整个关联字段为null；与“有关联但目标未收录”不同。
封面只返回已有合法HTTP(S)来源链接，不下载图片；显示远程封面需要网络。当前可能是缩略图尺寸。
原始 JSON 格式异常返回503和 SOURCE_DATA_INVALID；不返回内部原始内容。
此阶段未导入 IGN 关联，不返回伪造评分或伪装为空的 IGN 评测结果。

更新后关闭旧服务并重启；/docs 显示版本0.4.0。测试预期55 passed。
可打开 http://127.0.0.1:8000/api/v1/games/8948 检查已采集的 Routine 详情；也可从列表复制其他 igdb_id。
源码测试在开发环境通过，Windows/Python3.14仍需本机执行验证。不需要重新迁移或采集数据库。

日志 GET /favicon.ico 返回404表示浏览器请求的图标尚未提供，与数据接口是否正常无关。

## Vue 前端适配（v05）

列表items新增cover_url，格式和详情一致。每页仅从已选中的记录raw_json提取封面，不联网、不改库。
API版本0.5.0；更新后需重启服务。Vue页面通过Vite本地代理读取这些API，操作说明见FRONTEND.md。

## IGN 关联（v06）

API版本0.6.0。详情增加ign_reviews，每篇有review_id、score（0～10）、scope、review_date、reviewed_on、review_url、title、verdict。
未初始化IGN时为null，初始化后无确认关联时为[]。仅确认过的游戏关联会返回评测，候选不返回到详情。
游戏列表和IGDB评分字段不变；导入与确认通过本地CLI，HTTP接口仍只读。操作说明见IGN.md。

参考：https://fastapi.tiangolo.com/tutorial/query-params-str-validations/
