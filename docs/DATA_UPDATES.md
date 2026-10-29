# 每日采集、Hermes 监督与 GitHub 数据更新

已实现链路：Hermes 定时调用 → IGDB 独立采集 → 每个年份完成并通过计数校验 → 生成 ZIP 和清单 → GitHub 草稿 Release → 两个附件均上传成功后发布 → 软件后台下载、验证、备份并合并 SQLite。

## 本机已启用的每日任务（2026-10-26）

每日 **06:00（Asia/Taipei）**，由 `D:\hermes` 的 Hermes Gateway 调用确定性的 Python 脚本：

- 任务：`game-catalog-daily`，ID `3a835759f55f`，无限重复。
- 配置：项目内 `data/daily-settings.json`，IGDB `years: [2026]` 按游戏全球首次发售年份；IGN `ign_review_years: [2026]` 按评测发布日期。仓库为 `JstFrG0/game-release-data`。两个来源都每天06:00执行。
- IGN：复用 `F:\Projects\game-data` 的既有采集器，扫描最新评测目录。至少回看14天，停机超过14天时从上次成功前2天补抓；近期文章重新抓取，以同步评分与摘要修订。
- IGDB：完整扫描选定年份，核对每年的预期条数与实际条数。此前发布过、后来改期的游戏会另行刷新并作为修正条目保留。
- 关联：保留已有人工关联；仅唯一精确名称/别名、平台相交、发售日期差不超过7天且类别合格的未关联游戏自动关联。其余写入每轮 `ign-matching.json` 等待人工核对，仍随包保留来源资料。
- 采集与打包在独立暂存 SQLite 中进行，不直接修改软件正在使用的数据库。
- 发布：先创建草稿 Release，上传 ZIP 和清单后才发布；任何采集、条数校验或上传失败都会停止，不用旧包冒充本轮结果。
- 保留策略：`release_retention_count: 31`。每次成功发布后，完整读取仓库发布列表，按正式发布时间保留最新31个完整游戏数据 Release，超出的从最旧开始删除，连同其附件及专属 `data-<时间戳>` 标签。仅处理同时含两个标准附件的正式数据包；草稿、预发布和其他软件 Release 不参与计数。清理失败单独写入本轮 `retention`，Hermes 将该轮标为失败以便排查；已成功发布的包保持有效。
- Hermes 使用 `no-agent` 脚本任务，无需每日消耗模型额度。入口核验本轮报告时间、退出码、发布状态和计数校验；结果保存在 Hermes 本地执行记录，无外部消息推送。
- 网关已通过 Windows 启动文件夹安装登录自启。**电脑需保持开机、登录且未休眠，代理 `127.0.0.1:7897` 也需可用。** 关机或休眠期间无法执行；登录自启不等于未登录时开机运行。

检查和手动触发：

```powershell
D:\hermes\hermes.cmd cron status
D:\hermes\hermes.cmd cron list
D:\hermes\hermes.cmd cron runs 3a835759f55f
D:\hermes\hermes.cmd cron run 3a835759f55f
```

查看本轮结构化报告：`data/daily/latest-report.json`。历史记录及日志位于 `data/daily/<运行编号>/`；上次成功版本位于 `data/daily/last-success.json`。失败报告中的 `stage` 指出失败阶段，详细 IGN 日志保存在该轮目录。成功发布后删除本轮临时数据库，保留 ZIP、清单与日志；失败时保留暂存数据库供排查。这些文件不进入 Git。

脱离 Hermes 手动执行同一入口：

```powershell
cd F:\Projects\game-platform
.\.venv\Scripts\python.exe -u -m game_platform.daily_release
# 仅验证采集和打包，不发布：
.\.venv\Scripts\python.exe -u -m game_platform.daily_release --build-only
# 仅预览 GitHub 清理计划，不删除：
.\.venv\Scripts\python.exe -m game_platform.data_retention --dry-run
# 单独检查并执行31个版本保留策略，不重新采集：
.\.venv\Scripts\python.exe -m game_platform.data_retention
```

需要修改年份时编辑 `data/daily-settings.json`；需要修改时间时使用 `hermes cron edit`。Hermes 入口源文件在 `scripts/hermes_daily_catalog.py`，安装副本在 `D:\hermes\data\scripts\game_catalog_daily.py`，更改源文件后须同步副本。

以下为底层工具说明及其他主机的接入模板；本机每日任务使用上面的组合入口，不使用仅采集 IGDB 的旧入口。

## 采集与发布

采集环境需要 Python 3.12+ 和项目依赖。IGDB 凭据沿用项目根目录 `.env` 中的 `IGDB_CLIENT_ID`、`IGDB_CLIENT_SECRET`。发布凭据仅从进程环境变量 `GITHUB_TOKEN` 读取；令牌需有目标仓库 Contents 写权限，不能放进客户端或数据包。

Windows 上可先通过隐藏输入保存发布令牌：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File F:\Projects\game-platform\scripts\configure_github_token.ps1 -Purpose Publish
```

脚本使用 Windows 当前账户的 DPAPI 加密，保存到 Git 忽略的 `data/credentials/github-publish.dpapi`。此步骤仅保存，不验证 GitHub 权限，也不会自动把凭据注入已经运行的 Gateway。后续执行入口需要由同一 Windows 用户在同一台机器上解密，再临时提供给发布进程。不要将该文件作为软件更新包附件。

先生成一个数据包，下面年份仅为命令示例：

```powershell
cd F:\Projects\game-platform
.\.venv\Scripts\python.exe -m game_platform.daily_catalog --years 2025 2026 2027
```

确认范围后，采集并上传到自己的仓库：

```powershell
.\.venv\Scripts\python.exe -m game_platform.daily_catalog --years 2025 2026 2027 --publish --repository OWNER/REPO
```

默认输出位于 `data/published/`，不进入 Git：

- `catalog-data.zip`：仅含 `games.jsonl`，保存选定年份的 IGDB 来源资料。
- `catalog-manifest.json`：格式版本、UTC 时间版本、数量、压缩及原始大小、SHA-256。
- `daily-report.json`：本轮状态和每个年份的核验结果，供 Hermes 判断成功与否。

这是一份选定年份的来源快照，每天完整扫描所选年份；客户端可以跳过中间日期直接安装最新包。它不是仅包含当天变化的差分包。空数据、采集中断或数量不一致不会进入发布步骤。每轮使用临时数据库，不写用户正在使用的数据库。

Release tag 使用 `data-<UTC时间>`，上传时先创建草稿。附件上传失败会保留草稿供排查，客户端忽略草稿。发布失败后重新执行会建立另一份草稿/Release，不会覆盖历史版本。若网络在发布响应时中断，应先检查 GitHub，确认是否已发布，再决定重跑。

## Hermes 监督

本接入针对 NousResearch Hermes Agent。项目无需安装或导入 Hermes Python 包；Hermes 调用稳定的采集命令并读取结构化报告。定时任务每轮会开启独立会话，因此任务说明必须包含工作目录、Python 路径、年份、仓库、报告路径及判断规则。

参考 [Hermes 定时任务官方文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)。在 Hermes 能访问项目、运行 Python 并继承采集及发布环境变量的主机上，准备好具体命令后，通过 `hermes cron create` 或 Hermes 的定时任务工具创建任务。可用以下 PowerShell 模板（替换仓库、年份与执行时间后运行）：

```powershell
$catalogPrompt = @'
在 F:\Projects\game-platform 执行每日游戏资料任务。
运行 .\.venv\Scripts\python.exe -m game_platform.daily_catalog --years 2025 2026 2027 --publish --repository OWNER/REPO。
凭据由进程环境和项目 .env 提供，不读取、打印或复制密钥内容。
等待命令完成，检查退出码及 data/published/daily-report.json。
只有退出码为0、报告属于本轮运行、status为published，且每年count_check_passed均为true时，才报告成功。
成功报告版本、年份、各年记录数及GitHub Release链接。
失败时报告阶段与错误类型；如涉及发布，先只读核对GitHub是否已经发布。
不把旧报告当成本轮结果，不以旧包替代失败采集，不修改数据冒充校验通过。
不自动改代码、改年份、扩大权限或放宽校验。失败保留现场供排查。
'@
hermes cron create "0 4 * * *" $catalogPrompt --name "game-catalog-daily"
hermes cron list
hermes cron status
```

执行时间需在 Hermes 所在主机核对为期望的 Asia/Taipei 时间。Gateway 必须持续运行，否则任务不会按时执行；可按其官方文档使用 `hermes gateway` 或适合主机的服务方式运行。Windows/WSL/Linux 部署时分别使用对应的实际路径和 Python；不要将上面的 Windows 路径直接用于 WSL。

目前没有做记录数相对前日突降的阈值阻断，也没有实现自动修复或异常消息推送。Hermes 负责根据报告监督、总结异常；可重复执行的采集、校验、打包与发布由 Python 完成。

## 软件自动下载

支持公开和私有 GitHub 仓库。本机软件现在会自动读取 `data/update-settings.json`，不需要每次手动设置环境变量。当前已启用 `JstFrG0/game-release-data` 的启动检查与每6小时检查。

配置示例：

```json
{
  "enabled": true,
  "repository": "JstFrG0/game-release-data",
  "interval_seconds": 21600,
  "credential": "auto"
}
```

`credential: auto` 优先读取本机加密的 `data/credentials/github-read.dpapi`；没有只读凭据时，复用本机已有的 `github-publish.dpapi`。需要由保存凭据的同一 Windows 账户启动后端，后端私下解密，Token 不进入前端或状态响应。该设置文件和凭据目录均被 Git 忽略。把 `enabled` 改为 `false` 后重启后端即可停用自动检查。

如需单独配置只读凭据，可运行 `scripts/configure_github_token.ps1 -Purpose Read`，使用仅有目标仓库 Contents 读取权限的 Token。本机复用发布凭据仅适用于当前用户自己使用；向其他电脑分发软件时，应分别配置只读凭据，不分发发布令牌或凭据文件。

公开仓库可设置 `credential: none`。仍支持用进程环境变量 `GAME_DATA_GITHUB_TOKEN` 提供下载凭据，优先级高于加密文件；`GAME_DATA_REPOSITORY` 和 `GAME_DATA_UPDATE_INTERVAL_SECONDS` 可覆盖文件中的仓库和检查间隔。发布端仍单独使用 `GITHUB_TOKEN`（Contents 写权限）。

当前目标仓库为 `JstFrG0/game-release-data`，保持 Private，已存在初始提交与正式数据 Release。

私有下载通过 GitHub Release Asset API 认证，支持直接返回附件或跳转到临时下载地址。令牌仅发送给 GitHub API 的初次请求，重定向请求不携带令牌。配置示例（PowerShell 隐藏输入，不把令牌写进命令历史）：

```powershell
$catalogReadToken = Read-Host '输入该仓库的只读 Token' -AsSecureString
$env:GAME_DATA_GITHUB_TOKEN = [System.Net.NetworkCredential]::new('', $catalogReadToken).Password
Remove-Variable catalogReadToken
```

该设置仅对当前窗口及其后续启动的子进程生效。需在同一个窗口中启动软件后端；重开窗口需要重新设置，不能依赖这个临时变量作为 Gateway 重启后的持久凭据配置。令牌不进入数据库、更新包、API 状态响应或任务报告。权限不足、过期或私有仓库未配置令牌时，本轮检查失败，保留本地资料。

当前配置已保存在本机，直接使用原来的 FastAPI 启动命令即可：

```powershell
cd F:\Projects\game-platform
.\.venv\Scripts\python.exe -m uvicorn game_platform.api:app --host 127.0.0.1 --port 8000
```

服务启动后立即后台检查，此后默认每6小时检查一次，最短间隔60秒。网络或校验失败会保留本地数据库，并在下一轮继续检查。软件关闭期间不检查；多 worker 部署可能重复下载，但合并由进程锁串行保护。当前是单用户本地程序，建议使用单 worker。

软件顶部显示更新状态，并提供“检查更新”按钮。手动检查与自动检查共用一个任务，多次点击不会重复下载或并发安装。更新完成后，当前列表、详情与筛选字典自动刷新；同版本不会重新下载数据包或再做备份。

`GET /api/v1/data-updates` 提供公开状态：`disabled`、`idle`、`checking`、`downloading`、`installing`、`updated`、`up_to_date`、`no_release`、`configuration_error` 或 `failed`，以及当前版本和检查时间。`POST /api/v1/data-updates/check` 返回202并触发后台检查；跨站来源被拒绝。凭据、内部备份路径和请求异常原文不通过状态接口返回。

环境变量要设置在服务进程环境中；本项目 `.env` 加载器只加载 IGDB 凭据，不会自动加载这些客户端设置。

客户端检查最近100个 Release，选择其中发布时间最新、tag 以 `data-` 开头的正式版本，避免与软件自身的 Release 混淆。下载前检查附件地址属于指定仓库，流式下载有大小限制。SHA-256 用于完整性校验，来源信任依赖 HTTPS 和 GitHub 仓库权限；当前没有离线签名验证。

独立检查或离线安装：

```powershell
.\.venv\Scripts\python.exe -m game_platform.data_updates update --repository OWNER/REPO
.\.venv\Scripts\python.exe -m game_platform.data_updates apply --bundle-dir .\data\published
```

两条命令默认更新 `game-platform/data/igdb.sqlite3`，可通过 `--database` 指定其他文件。

## 数据保留和范围

格式 v2 支持同时分发 IGDB 和 IGN：ZIP 内包含 `games.jsonl` 与 `ign-reviews.jsonl`，清单分别记录两类数据的数量、大小和 SHA-256。IGN 内容包含逐篇评分、日期、平台、摘要和已核验的 IGDB 关联；未核验的记录可以保留为待处理条目，不按模糊名称自动关联。

年份包可以附带原属目标年份、现已改期或撤回具体日期的游戏修正。`release_snapshot package --supplemental-jsonl <文件>` 会将这些已按 ID 重新抓取的事实一起打包；待定日期使用 `null`，不伪造日期，也不删除游戏及其 IGN 关联。报告分别统计年份主体条目与补充修正条目。

客户端在同一事务内更新游戏、评测、分发关联和版本回执。已有人工游戏关联、文章关联、组合关联均优先于分发关联。格式 v1 仍可安装；旧版客户端会拒绝 v2，需要先更新客户端代码。

一次性年份更新可用 `python -m game_platform.release_snapshot prepare` 将已校验的 IGDB 暂存数据库与本地确认过的 IGN 关联、最新 IGN 导出合并，输出 `snapshot-review.json`；审核候选后，用同模块 `package` 子命令生成包及 `snapshot-report.json`。该模块不执行网络抓取，也不会自动确认候选。发布入口 `scripts/publish_catalog_bundle.ps1 -BundleDirectory <包目录>` 可由保存凭据的同一 Windows 用户运行，临时解密 DPAPI Token 并注入发布子进程，结束后恢复环境。

更新只按 `igdb_id` 新增或更新 IGDB 来源字段，重建这些游戏的分类标签，不删除缺席的游戏，不修改 IGN 评测、人工关联或其他用户表。所有游戏合并及版本回执处于同一事务，失败整批回滚；初次安装可能先创建或迁移空数据库结构。同版本重复安装不写入，更旧版本会拒绝。

更新前通过 SQLite backup 保存到 `data/backups/igdb_before_data_update_*.sqlite3`，可处理 WAL 中的数据；当前保留全部更新备份，需按磁盘容量另定保留周期。

沿用现有采集器的年份定义：IGDB `first_release_date` 的全球首次发售 UTC 年份。不是“任一平台在该年份发售”，也不覆盖没有首次发售时间的待定游戏。完整 `release_dates` 会作为原始 JSON 一起同步，但尚未新增按平台发售日的页面和查询接口。未选年份的游戏不会每天刷新；来源将游戏日期改到所选范围以外时，本次扫描可能看不到该游戏，因此需要根据最终业务范围增加按 `updated_at` 或已知 ID 的补充同步。

IGN 网络采集脚本仍位于相邻 `game-data` 目录。目录发现支持 `--headless`、`--proxy` 和 `--http`，文章刷新脚本也支持显式代理及公共 HTTP 连接。它们保留抓取快照、备份与逐篇结果；认证拒绝或限流时停止请求。当前每日定时入口尚未自动串联 IGN 刷新及候选审核，一次性采集与完整每日无人值守工作流应分别验收。

GitHub Release 协议参考：[GitHub Releases REST API](https://docs.github.com/en/rest/releases/releases)。
