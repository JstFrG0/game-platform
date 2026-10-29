# 游戏发售数据信息库

基于 Vue 3、FastAPI 和 SQLite 的本地游戏资料库，提供 IGDB 游戏目录、筛选、搜索、评分和详情，以及 IGN 评测关联。

## 已实现

- 前端目录、封面卡片、详情页与年份、平台、类型、模式、评分筛选。
- IGDB 来源采集、原始资料保存与年份计数校验。
- IGN 评测导入、人工关联与严格精确匹配；保留人工确认结果。
- GitHub 数据更新包发布、SHA-256 验证、数据库备份合并及软件内检查更新。
- Hermes 每日任务：当前两个来源均限定2026年，每天06:00（Asia/Taipei）执行；错过执行时间后补跑一次。
- 新数据包成功发布后，GitHub 仅保留最新31个完整数据 Release。

## 源码与数据分离

本仓库保存源码、测试、依赖锁和配置示例。游戏数据库、采集结果、更新 ZIP、密钥、DPAPI 凭据、虚拟环境、node_modules、dist、旧补丁及临时安装目录不随源码上传。

运行数据仓库：`JstFrG0/game-release-data`。本仓库不包含实际游戏数据库；首次使用需自行采集或从获授权的数据仓库安装更新。私有仓库令牌由使用者在本机配置。

## 开发环境

- Windows、Python 3.12+、Node.js 22.12+
- PowerShell 以下命令使用 `npm.cmd`。

```powershell
git clone https://github.com/JstFrG0/game-platform.git
cd game-platform
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd frontend
npm.cmd ci
```

在项目根目录配置 IGDB 凭据并采集数据：

```powershell
.\.venv\Scripts\python.exe scripts/configure_igdb.py
.\.venv\Scripts\python.exe -m game_platform.collect_igdb --year 2026
.\.venv\Scripts\python.exe -m game_platform.classify_games --help
```

采集完成后按分类工具说明初始化分类与筛选字段。两个终端分别启动后端和前端：

```powershell
# 项目根目录
.\.venv\Scripts\python.exe -m uvicorn game_platform.api:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm.cmd run dev
```

打开 http://127.0.0.1:5173 。

## 每日采集与更新配置

`config/` 仅提供无密钥示例，复制到本机 `data/` 后按实际路径调整：

```powershell
New-Item -ItemType Directory data -Force
Copy-Item config/daily-settings.example.json data/daily-settings.json
Copy-Item config/update-settings.example.json data/update-settings.json
```

IGN 采集器源码位于 `collectors/ign/`；已部署的电脑仍可继续使用原来的相邻 `game-data` 目录。每日入口读取配置中的 `ign_root`，要求该目录存在独立 `.venv` 和 IGN 来源归档数据库 `data/games.sqlite3`。新机器需单独安装采集依赖和 Playwright 浏览器，并通过采集器初始化/恢复自己的来源归档；真实归档与浏览器数据不在源码仓库中。

```powershell
py -m venv collectors/ign/.venv
.\collectors\ign\.venv\Scripts\python.exe -m pip install -r collectors/ign/requirements.txt
.\collectors\ign\.venv\Scripts\python.exe -m playwright install chromium
```

采集器的浏览器路径默认沿用本机 `F:\PlaywrightBrowsers`，迁移机器时应显式设置 `PLAYWRIGHT_BROWSERS_PATH`，或安装浏览器到该路径。Hermes 执行入口中的项目路径也需按新机器实际位置调整。

完整部署、令牌配置、定时任务和更新协议见 [数据更新说明](docs/DATA_UPDATES.md)。IGN 导入与人工关联见 [IGN 说明](docs/IGN.md)。早期采集教程保留在 [历史说明](docs/IGDB_SETUP_HISTORY.md)，其中的2025年为示例。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd test
npm.cmd run build
```
