# Vue 3 本地资料库（v05）

## 第一版页面

用户已选择：炭灰深色背景、蓝色强调色、默认封面卡片。

- 游戏目录：名称搜索、年份、范围、条目类别、平台、玩法类型、模式、评分和评分人数筛选。
- 日期、名称和用户评分排序；分页展示，不一次加载全部游戏。
- 游戏详情：封面、简介、平台、玩法类型、模式、三种IGDB评分、公司、相关版本及来源链接。
- 搜索和筛选条件保存在哈希路由的网址中，进入详情后返回或刷新仍可恢复。
- 加载占位、无结果、后端不可用、重试、图片不可用占位。
- 桌面显示侧栏筛选；窄窗口折叠筛选面板。支持键盘操作、可见焦点和减少动画偏好。

没有添加未实现的收藏、Steam登录、AI推荐或IGN评分按钮。下一阶段按实际需求扩展。
数据保持来源原文，尚未翻译类型、平台和简介。公司角色缺失时仅展示公司名称，不猜测开发/发行角色。
列表有些不同ID的同名游戏仍分别展示，遵循当前分类和身份规则。

## 环境

Python沿用已有虚拟环境。前端另外需要Node.js和npm，推荐Node.js24 LTS。
最低要求Node.js22.12.0；官方安装页面 https://nodejs.org/en/download 。
Windows选择Windows Installer (.msi)，按安装向导完成并重新打开PowerShell。
项目和node_modules默认放在F盘的项目路径，不需要重新安装Playwright浏览器。

```powershell
node --version
npm.cmd --version
```

这里使用npm.cmd，避免PowerShell把npm命令解析为受执行策略限制的npm.ps1。

## 安装与验证

在项目根目录完成补丁更新后执行：

```powershell
cd "F:\Projects\game-platform"
.\.venv\Scripts\python.exe -m pytest -q
cd .\frontend
npm.cmd ci
npm.cmd test
npm.cmd run build
```

预期Python55 passed（可能有现有Starlette测试客户端弃用警告）；前端4项测试通过；Vite构建成功。
package-lock.json记录确切依赖；npm ci根据锁文件安装，不要删除锁文件。无需新增Python依赖。
源码、依赖锁和测试进入Git，node_modules和dist继续由现有.gitignore忽略。

## 两个终端启动

终端1（后端；如果旧服务还在运行，先Ctrl+C再启动以载入封面字段更新）：

```powershell
cd "F:\Projects\game-platform"
.\.venv\Scripts\python.exe -m uvicorn game_platform.api:app --host 127.0.0.1 --port 8000
```

终端2（前端）：

```powershell
cd "F:\Projects\game-platform\frontend"
npm.cmd run dev
```

浏览器打开 http://127.0.0.1:5173/ 。保留两个终端运行，各自Ctrl+C停止。
前端/API只监听本机。前端把/api请求代理到8000，不需要增加CORS或Twitch凭据。
如果后端改为8001，需同时修改frontend/vite.config.js中server和preview两处代理地址。
如果5173被占用，停止旧前端或在脚本中明确改端口；不会静默换端口。

build生成静态文件用于后续集成或桌面包装，当前不要求用户直接双击dist/index.html。
要验收构建产物，在后端运行的前提下执行npm.cmd run preview，仍打开5173。

## 页面验收

1. 默认年份2025、范围“主要游戏”，结果数量应为21,964（当前采集批次未更新时）。
2. 点击“全部条目”再“应用筛选”，应显示25,476。
3. 在全部范围选择“内容包”，应用后应显示664。
4. 搜索Routine，点击对应卡片，确认简介、平台和评分显示。
5. 从详情返回目录，确认Routine搜索仍保留；刷新也保留。
6. 设置最低评分和评分人数，应用后检查范围；不设评分门槛时仍保留暂无评分的游戏。
7. 缩小窗口，展开/收起筛选，确认没有横向溢出。

封面仍来自IGDB远程图片链接，需要网络；图片缺失或访问失败时显示“暂无可用封面”。
只对images.igdb.com的t_thumb链接切换至官方cover_big_2x尺寸，其他来源链接保持原样。
接口新增列表cover_url字段，仅从该页记录的raw_json提取，不重新采集或修改数据库。

开发验收使用临时样本数据库和测试封面，已在真实Chromium中验证分页、搜索、详情、URL恢复、类别筛选、空结果、重试和390px窄窗口。
这些浏览器测试没有将样本数据写入用户数据库，也没有把测试封面加入产品。实际Windows数据仍需本机验收。
Windows使用系统字体（Segoe UI、Microsoft YaHei等），不依赖在线字体服务。

## 代码分工

- frontend/src/pages/CatalogPage.vue：目录和筛选。
- frontend/src/pages/DetailPage.vue：详情。
- frontend/src/components/CoverImage.vue：封面加载和错误占位。
- frontend/src/api.js：HTTP请求、分数格式和图片尺寸。
- frontend/src/catalog.js：筛选状态和网址转换。
- frontend/src/style.css：配色、组件样式和响应布局。
- frontend/vite.config.js：Vue编译和本地API代理。

异步请求通过AbortController取消旧请求，页面卸载时取消请求；不让旧响应覆盖新查询。
Vue插值展示来源文本，不使用v-html。API参数验证仍由后端执行。

## 简约界面调整（v05.1）

用户确认保留炭灰深色与蓝色强调，要求去除装饰性小字、重复说明并集中展示信息。
目录直接展示搜索、筛选、结果数量和卡片；移除顶部宣传语、独立统计、英文副标题和页脚口号。
卡片不再叠加类别浮标和悬浮文案，平台、日期与评分保持统一可读字号。
详情将类别、日期、平台、类型、模式和公司合并到基本信息；评分集中在同一区域，来源标签仍明确区分。
简介使用统一正文区；别名、ID和采集时间放入默认收起的“更多资料”，原始数据不删除。
“更多资料”使用原生details/summary，支持鼠标和键盘展开。
筛选必要标签、无数据和失败提示保留，移除筛选描述小字、重复条件摘要和页数说明。
此更新仅涉及前端，不改变API、数据库、评分、分页或URL状态。
构建与现有4项前端测试通过；真实浏览器使用临时样本验证搜索、分页、详情返回、内容包筛选和窄窗口布局。
设计约定见UI_STYLE.md；后续界面按此偏好扩展。
