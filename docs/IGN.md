# IGN 评测与 IGDB 关联（v06）

资料库仍为一个入口。IGDB游戏ID是详情主键，IGN评测作为关联来源逐篇展示。
此阶段不重新抓取IGN，不下载全文，不自动翻译；仅导入已有评分、日期、分项、平台和链接。

## 数据与迁移

新增schema版本3：ign_reviews保存评测，ign_links保存确认后的IGN游戏页到IGDB ID映射，ign_link_events记录关联、改绑、解除历史。
同一游戏可有多篇评测；每篇按规范化评测URL唯一，重复导入更新该篇记录而不重复建立记录。
保留0分、缺失评分null、来源原始行JSON。评分为0～10，IGDB三种评分及人数完全不修改。
Tabletop为唯一平台的行排除；缺少平台不被当作桌游，也不满足精确候选确认条件。
写操作先通过SQLite backup API备份到data/backups/igdb_before_ign_*.sqlite3。
分类迁移必须已完成；不删除或重建igdb_games。IGN结构创建与版本登记为事务；导入与关联批次也各自使用事务。

## 导入

支持此前生成的ign_2025.xlsx的“IGN评测”表、ign_2025_games.xlsx中的“评测明细”表，以及ign_2025_video_reviews.csv。
不要导入“游戏清单”汇总表，汇总表可能把多篇评分折叠，无法表达文章关联。
读取XLSX只使用Python标准库，不需要新增Excel依赖。支持共享字符串、内联字符串、Excel日期序号和1904日期系统。
支持English CSV字段name、score、review_url、game_url/ign_game_url、platforms、us_release_date、review_date、reviewed_on、scope。
title和verdict为可选字段；没有来源值时不编造文章标题或评价摘要。

```powershell
.\.venv\Scripts\python.exe -m game_platform.ign_reviews import .\data\imports\ign_2025.xlsx
```

导入验证整份输入后再写入；无效URL、评分或日期会拒绝该次导入。原输入文件不修改。
更新包中的输入表是之前用户提供的2025快照；解析应得到175篇电子游戏评测、171个IGN游戏页，11篇桌游排除。
源表按美区首次发售年份筛选，与IGDB全球首次发售年份不同。部分IGN游戏可能不在当前本地库中，保持未关联。

## 匹配与确认

```powershell
# 重新生成候选（不修改关联）
.\.venv\Scripts\python.exe -m game_platform.ign_reviews match
```

输出：data/reports/ign_link_report.json、data/exports/ign_match_candidates.csv、data/exports/ign_link_confirmations_template.csv。
报告中matches包含候选和证据；linked_igdb_id仅表示已经确认的关联，不是模型猜测。
候选同时参考IGDB名称/原始别名、平台交集、日期差和条目类别。
eligible_exact要求唯一精确名称/别名候选、平台交集、已知日期差不超过7天、IGDB类别属于默认四类。
这个标记是可批量确认的候选条件，不等同于正确性保证；仍应先检查报告。
模糊匹配只给最多5个候选，不自动确认。编号、特别版名称不强行删除，不把重制版与旧版合并。
每个IGN游戏页只关联一个具体IGDB记录，同页不同分项的多篇文章随该关联展示。

检查精确候选后，可明确执行批量确认命令：

```powershell
.\.venv\Scripts\python.exe -m game_platform.ign_reviews approve-exact
```

只确认当前仍满足条件且尚未关联的游戏；不覆盖人工关联、不确认模糊候选。
想逐条确认时复制模板为ign_link_confirmations.csv，在igdb_id填入核实的目标ID，在decision填写link或“关联”；跳过留空或写skip。

```powershell
.\.venv\Scripts\python.exe -m game_platform.ign_reviews confirm .\data\exports\ign_link_confirmations.csv
```

改绑到不同ID需显式加--replace。解除关联用decision=unlink或“解除”，igdb_id可留空。
确认文件整批校验后才写入；缺失游戏ID或重复IGN游戏行拒绝整个批次。
报告每次重新生成候选模板，所以编辑时使用模板副本，避免后续操作覆盖未完成的编辑。

## 页面与API

重启后端使API版本显示0.6.0，前端刷新即可。
GET /api/v1/games/{igdb_id}新增ign_reviews：未初始化IGN功能时为null，初始化后没有已确认文章为[]，有文章时逐篇返回。
返回review_id、score、scope、review_date、reviewed_on、review_url、title、verdict；只有确认关联才展示。
IGN区域放在详情评分之后，集中显示分项、评分、日期和阅读链接。明确标注10分制，IGDB区域仍为100分制。
没有关联时不显示空的IGN区域；不自动取最高分、不计算跨评测平均分。
未确认只影响IGN区域，原来的目录、筛选、详情、评分和SQLite读取保持可用。
后端API仍只读；所有导入和关联确认在本地CLI进行。

代码验证包括70项Python测试、4项现有前端测试和构建。Windows实际关联数量需导入后核对本地报告。
