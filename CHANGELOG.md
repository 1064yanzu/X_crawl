# Changelog

## 2026-03-04

### 🐛 修复：搜索无结果时微博热门推荐被误解析为搜索结果

**问题**：当日期子段内关键词无结果时（如 2022 年 6 月搜索"ChatGPT"——该词 2022 年 11 月才诞生），微博不返回空白页，而是展示"热门微博/大家都在搜"推荐。这些推荐帖的 HTML 结构与正常搜索结果完全一致，导致解析器误将贾乃亮、曾舜晞等无关内容当作搜索结果存入数据库。

**修复**：
- `html_parser.py`：在 `parse_search_page` 开头新增"无结果"检测（`card-no-result` / `noresult_tit` 元素 + 文本关键词 "未找到/没有找到" 兜底），命中时直接返回空列表。
- `searcher.py`：`_safe_get_html` 新增 URL 重定向检测，若目标为 `s.weibo.com` 但实际被重定向到其他域名，立即返回错误而非解析错误页面。

### 🐛 修复：评论抓取被硬限制在 50 条以内，无法翻页获取全部评论

**问题**：帖子元数据显示有几百条评论，但实际抓取仅得到几十条。
**根因**：`comment_fetcher.py` 中 `max_comments` 默认值为 50，`max_pages` 为 10。对于评论过百的热帖，抓到 50 条就被截断了。
**修复**：
- `max_comments` 从 50 提升至 **500**，`max_pages` 从 10 提升至 **50**（每页 20 条，最多可抓 1000 条）。
- 新增配置 `weibo_max_comments_per_post`，可在设置页面调整每帖最大评论抓取数。
- `searcher.py` 调用时读取配置值并传入。
- URL 参数顺序严格按照抓包真实请求还原：`flow=0&is_reload=1&id&is_show_bulletin=2&is_mix=0&max_id&count=20&uid&fetch_level=0&locale=zh-CN`，补充 `server-version`、`cache-control`、`pragma` 等缺失请求头。
- 重新加回 `uid`（帖子作者 UID）参数。之前为修复评论错配曾完全移除 `uid`，但抓包证实：缺少 `uid` 时，API 在 2-3 页后提前返回 `max_id=0` 截断分页。现在从 `post.author_id`（HTML 解析器已可靠提取）安全传入。

### 🐛 修复：大跨度时段（如数年）无限制搜索时，数据量意外极低（被 50 页截断）

**问题**：执行无上限（`max_count=0`）的 4 年跨度热门词搜索，最终却仅导出 1000 多条结果。
**根因**：两重限制叠加导致数据丢失：
1. `config.py` 中的 `weibo_max_pages` 默认值为 10，每次搜索到达第 10 页即刻停止（微博真实限制为 50 页）。
2. `date_splitter.py` 遇到超过 1 年的时间跨度时，固定硬编码「每 3 个月」切分一段。
这导致 4 年时间被切分为 16 段，每段只能抓取 10 页（约 90 条），16 段总计约 1400 条，完全错过了由于大热度产生的海量页数。

**修复**：
- 取消单次小范围阈值：将 `config.py` 中的 `weibo_max_pages` 默认提升至微博原生上限 **50** 页。
- 增强动态日期切分：大幅细化 `date_splitter.py` 的切片粒度。在用户选择无上限抓取（`max_count=0`）时，若总天数超 1 年，强制按**周**切分；若超 2 个月，按 3 天切分；否则**按天**切分。这通过密集的小时间窗，确保任何时间段内的数据都能在 50 页的窗口内被完整装下而不被截断。

### 🐛 修复：微博分段搜索时前端预览数据丢失 + 评论与帖子不匹配

**问题 1 — 子任务切换时前端数据重置**：
- **根因**：日期范围分段搜索时，每个子段内部的 `search()` 调用 `update_preview_tweets()` 仅传入当前子段数据，覆盖了之前子段的累积数据
- **修复** (`searcher.py`)：新增 `_parent_accumulated` 内部参数，子段递归调用时传入父级已累积数据；`update_preview_tweets` 合并父级 + 当前段数据后推送前端

**问题 2 — 评论预览与帖子内容不匹配**：
- **根因**：`comment_fetcher.py` 评论 API 携带 `uid` 参数，该参数来自 HTML 解析的 `author_id`，解析失败时为空字符串，导致 API 返回错误数据
- **修复** (`comment_fetcher.py`)：移除不必要的 `uid` 参数（`buildComments` API 只需 `mid` 即可正确获取评论）
- **修复** (`html_parser.py`)：增强用户 ID 提取正则，支持 `//weibo.com/u/数字` 格式

### ✨ 增强：微博爬虫随机时间扰动（反爬优化）

为微博爬虫的所有等待点引入随机时间扰动，使行为更接近人类操作：

- `searcher.py`：翻页间隔改用 `jittered_sleep`（±20% 随机浮动 + 资源节流 + 可中断），重试等待改用 `interruptible_sleep`（可响应暂停/停止信号）
- `comment_fetcher.py`：评论翻页间隔改用 `jittered_sleep`，Cookie 注入后的等待加入 `random.uniform` 扰动

### 🐛 修复：评论 API JS 请求返回空值（DrissionPage async 兼容性）

**问题**：`tab.run_js()` 执行 async IIFE（`(async () => { ... })()`）时返回 `None`，导致所有评论请求都被判定为"返回空值"。
**根因**：DrissionPage 4.x 的 `run_js` 不支持 async 函数返回值——async 函数返回的是 Promise 对象，而 `run_js` 无法等待 Promise resolve，直接返回 `None`。
**修复**：将 `async fetch()` 替换为 **async fetch + DOM 桥接**方案——JS 端用 `fetch` 发请求并将结果写入隐藏 DOM 元素，Python 端轮询读取。同步 XMLHttpRequest 在页面未完全加载或跨域时会触发 `NetworkError: Failed to execute 'send'`。

### 🐛 修复：评论覆盖范围和评论计数在前端显示为 0

**问题**：后端成功抓取到评论（179 条），但前端"评论覆盖"时间范围为空，`replies_fetched` 始终为 0。
**根因**：`task_insights.py` 的 `_parse_iso()` 解析微博帖子的中文日期（如 `2023年12月31日 22:57`）返回 **naive datetime**（无时区），而解析评论的英文日期（如 `Fri Aug 26 15:05:50 +0800 2022`）返回 **aware datetime**（带时区 `+08:00`）。合并推文和评论时间范围时 `min(tweet_min, reply_min)` 触发 `TypeError: can't compare offset-naive and offset-aware datetimes`，被 `_summarize_tweets` 的 `except Exception` 静默吞掉，返回 `0, {}`。
**修复**：`task_insights.py` 的 `_parse_iso()` 统一返回 timezone-aware datetime —— 无时区信息的日期默认视为 CST（UTC+8）。

## 2026-03-03

### 🐛 修复：微博评论始终抓取 0 条 + 暂停按钮对微博爬取不生效

**问题 1 — 评论始终返回 0 条**：
- **根因**：搜索和评论共用同一 tab，域名在 `s.weibo.com` ↔ `weibo.com` 间切换导致 Cookie/XSRF-TOKEN 状态混乱；API 返回异常时被静默跳过无日志
- **修复** (`comment_fetcher.py`)：
  - 域切换后重注入 Cookie 并刷新页面，确保 XSRF-TOKEN 可用
  - JS fetch 改为捕获 HTTP 状态码和完整响应体，API 异常时打印详细日志
  - 补充 `client-version` 请求头
  - XSRF-TOKEN 获取失败时自动从 Cookie 文件加载重试

**问题 2 — 暂停按钮不生效**：
- **根因**：`searcher.py` 只检查 `stop` 信号（`get_signal() == "stop"`），完全忽略 `pause` 信号
- **修复** (`searcher.py`)：
  - 用 `check_signal()` + `StopSignal` 异常机制替代简单的 stop 检查
  - `check_signal()` 支持 pause（轮询等待）+ stop（抛异常终止）+ run（正常继续）
  - 日期分段循环和主搜索循环都加入暂停检查
  - 评论抓取传入 `task_id` 支持暂停/停止

## 2026-03-03

### ✨ 优化：前端展示按平台分门别类整理（可扩展架构）

将爬虫配置、预览、历史记录等按平台（X / 微博）分类展示，并预留可扩展性，新增平台只需在注册中心追加一行。

**新增文件**：
- `frontend/src/lib/platformRegistry.ts`：平台注册中心，统一管理平台元数据（名称、颜色、图标、样式），导出 `getPlatformMeta()` / `getPlatformsWithAll()` 工具函数
- `frontend/src/components/ui/platform-tabs.tsx`：可复用的 PlatformTabs 分段控制器组件，支持图标、名称和计数 Badge

**任务列表页**（`tasks/page.tsx`）：
- 顶部新增平台 Tab 切换器（全部 / 𝕏 Twitter / 微博），实时过滤
- 每个任务卡片左侧新增平台色条指示器 + 平台 Badge
- 空态文案根据当前过滤平台动态切换

**仪表盘**（`DashboardTasks.tsx`）：
- 正在运行和历史任务按平台分组展示
- 每组带平台色点 + 名称标题 + 数量统计
- 单平台时保持紧凑布局，多平台时分组显示

**设置页**（`settings/page.tsx`）：
- 使用 Tab 将设置项分为三个区域：通用设置 / 𝕏 Twitter / 微博
- 通用设置：浏览器选择、引擎参数、代理、归档、安全操作
- X Tab：Cookie 管理 + 多账号池
- 微博 Tab：Cookie 管理
- Tab 切换带 fade-in 动画

**任务详情页**（`tasks/[id]/page.tsx`）：
- 标题行新增平台 Badge 标识

**性能优化**：
- 设置页拆分为 3 个独立子路由（`/settings`、`/settings/x`、`/settings/weibo`），共享 `layout.tsx` 导航
- 每个子页面只导入自己需要的组件，避免 dev 模式 Turbopack 一次性编译所有组件导致 OOM
- `start-frontend.sh` 新增自动内存检测：可用内存不足 1GB 时自动切换 production 模式运行

## 2026-03-03

### 🐛 修复：微博前端不显示时间覆盖范围 + 评论导出为空 + 总页数提取 + 50页扩容

**问题 1 — 前端不显示时间覆盖范围**：`_parse_iso()` 只支持 ISO 格式，无法解析微博中文日期（如 "2023年12月31日 22:57"）
- `task_insights.py`：扩展 `_parse_iso` 支持中文日期、英文日期（评论 API）、短日期等多种格式

**问题 2 — 总页数不显示**：搜索结果 HTML 中分页器包含总页数但未提取
- `html_parser.py`：从 `ul.s-scroll > li` 提取总页数，返回签名改为三元组 `(posts, has_next, total_pages)`

**问题 3 — 50 页限制扩容**：微博搜索最多返回 50 页，大时间范围数据不足
- [NEW] `date_splitter.py`：自动按月/周/天分割日期范围
- `searcher.py`：日期跨度大时自动分段搜索，递归合并结果

**问题 4 — 评论返回 0 条**：`comment_fetcher.py` 导航 `weibo.com/{uid}/{数字mid}` 无效，且评论后未回搜索域名
- `comment_fetcher.py`：改为导航 `weibo.com` 首页确保域名正确
- `searcher.py`：每页评论抓取后导航回 `s.weibo.com`

### ✨ 增强：微博数据全面采集（帖子+评论字段完整提取）

对照微博抓包数据，全面重写解析逻辑，确保所有可提取信息无遗漏：

**帖子新增字段**（`html_parser.py` + `models.py`）：
- `source`：来源设备（微博网页版、NIO Phone Android 等）
- `verified` + `verified_type`：认证标识（蓝V企业/黄V个人）
- `hashtags`：话题标签列表
- `is_repost` + `repost_text/author/metrics`：转发微博的原微博完整信息

**评论新增字段**（`comment_fetcher.py` + `models.py`）：
- `source`：IP 属地（来自四川 等）
- `avatar_url`：评论者头像
- `is_author`：是否博主
- `verified` + `verified_reason`：评论者认证信息
- `gender` / `location` / `followers_count`：性别/地区/粉丝数
- `sub_comments` + `sub_comments_count`：楼中楼子评论（递归解析）
- `reply_to_user`：回复目标用户名
- 优先使用 `text_raw` 获取纯文本，避免 HTML 清理损失

### 🐛 修复：微博帖子缺少互动数据 + 评论未抓取

**问题 1**：微博帖子的转发、评论、点赞数始终显示 0。
**原因**：`html_parser.py` 未解析互动数据，`models.py` 硬编码 `metrics` 为 0。
**修复**：
- `html_parser.py`：新增 `_extract_metrics()` 从 `div.card-act` 提取转发/评论/赞数（支持万/亿单位）
- `models.py`：新增 `reposts_count`/`comments_count`/`likes_count` 字段

**问题 2**：用户开启了评论抓取但微博评论未被获取。
**原因**：`_run_weibo_task()` 没有传递 `fetch_replies` 参数给 `weibo_search` 的 `fetch_comments`。
**修复**：
- `crawl_service.py`：传递 `fetch_replies` → 微博的 `fetch_comments`
- `comment_fetcher.py`：评论前先导航到帖子页面（解决跨域问题），增加 likes 解析和 HTML 清理
- `searcher.py`：评论条件简化为 `fetch_comments and comments_count > 0`

### 🐛 修复：微博爬虫搜索超时（Cookie 注入时序错误 + 缺乏崩溃恢复）

**问题**：微博搜索任务报 `DOM.getOuterHTML timeout`（超时 30s），随后 `Target crashed`，导致爬虫完全无法获取搜索结果。

**根本原因**（4 重问题）：
1. **Cookie 注入时序错误**：在 `about:blank` 页上注入 `.weibo.com` 域的 Cookie，浏览器可能不接受
2. **关键 Cookie 缺失**：`normalize_cookies()` 只保留 name/value/domain/path 四个字段，丢失了 httpOnly/secure/sameSite 等属性
3. **搜索域名 Cookie 未准备**：auth 验证走 `weibo.com`，搜索走 `s.weibo.com`，Cookie 上下文断裂
4. **Tab 崩溃无恢复**：`Target crashed` 后没有重建 tab，后续所有 DOM 操作全部超时

**修复**：
- `crawler/weibo/cookie_manager.py`：`normalize_cookies()` 改为保留所有原始字段，只补全缺失的 domain/path 默认值
- `crawler/weibo/auth.py`：重构为正确时序（先导航到域名 → 注入 Cookie → 刷新验证），新增 `ensure_search_cookies()` 为 `s.weibo.com` 预注入 Cookie
- `crawler/weibo/searcher.py`：
  - 搜索前调用 `ensure_search_cookies()` 确保搜索域 Cookie 就位
  - 新增 `_safe_get_html()` 带重试的安全页面获取
  - 新增 `_check_anti_crawl()` 检测验证码/登录跳转/安全验证
  - Tab 崩溃后自动重建 tab 并重新注入 Cookie
  - 连续 3 页失败自动终止，避免无限循环

## 2026-03-03

### ✨ 新增：高级搜索功能（完整对齐 X 原生高级搜索面板）

### 🐛 修复：搜索页面被误判为错误页（noscript 标签误匹配）

**问题**：所有搜索任务（包括普通搜索和高级搜索）均因页面被反复检测为 `transient_error` 而失败，实际页面已正常加载（侧边栏可见、用户已登录），只是内容区在加载中。

**根本原因**：X 的 HTML 始终包含 `<noscript><h1>JavaScript is not available.</h1></noscript>` 作为无 JS 浏览器的降级提示。`_normalize_visible_text` 的正则表达式（使用 `\1` 反向引用）未能正确移除该 noscript 块，导致 `detect_page_state` 将 `"javascript is not available"` 匹配到 `_TRANSIENT_ERROR_MARKERS`，**所有页面加载都被误判为临时错误**。

**修复**：`crawler/page_state.py`
- 从 `_TRANSIENT_ERROR_MARKERS` 中移除 `"javascript is not available"` 条目（X 的 noscript 固有内容）
- 重写 `_normalize_visible_text` 正则：将 `\1` 反向引用拆分为三次独立的 `re.sub`（分别处理 script/style/noscript）
- 额外兜底：`text.replace("javascript is not available", "")` 确保任何残留都被清除

**背景**：X 平台在搜索结果页提供了一个强大的高级搜索面板，支持 16 种筛选条件。本次将其完整集成到爬虫项目中，让用户能够精确控制爬取范围。

**核心原理**：X 的高级搜索本质是将表单字段转换为搜索操作符（如 `from:user`, `min_faves:100`, `"exact phrase"`, `-excluded`）追加到 query 字符串中。后端的 `_build_search_url` 已正确 URL-encode keyword，因此不需要改后端搜索逻辑。

**前端改动**：
- **重写 `AdvancedSearchPanel.tsx`**：
  - Words 区域：全部这些词、精确短语、任意这些词、排除这些词、指定 Hashtag
  - Language：完整语言列表（34+ 种语言，对齐 X 原始支持）
  - Accounts 区域：来自账号（from:）、发给账号（to:）、提及账号（@）
  - Filters 区域：回复筛选（三态：关闭/包含/仅显示）、链接筛选（三态）
  - Engagement 区域：最低回复数、最低点赞数、最低转发数
  - Dates 区域：起始日期（since:）、结束日期（until:）
  - 导出 `buildAdvancedQuery()` 函数：将表单参数转换为搜索操作符字符串
  - 活跃条件数量徽章，便于用户一眼看出是否有筛选
- **更新 `CrawlerTaskBuilder.tsx`**：
  - 移除旧版简单 filter chips（`lang:zh`, `min_faves:500`）
  - 集成新版 `AdvancedSearchPanel`
  - `buildFinalKeyword()` 改为组合主关键词 + 高级搜索操作符
  - 底部预览区实时显示编译后的完整搜索指令

**后端改动**：
- **新增 `crawler/query_builder.py`**：Python 版搜索操作符构建工具，与前端逻辑一致，支持全部 16 种高级搜索参数
- **新增 `tests/test_query_builder.py`**：27 组单元测试，覆盖所有搜索操作符和边界情况

## 2026-03-03

### 🐛 修复：服务启动时 Cookie 文件有账号但账号池为空

**问题**：Cookie 文件（`~/.xcrawl-cookies.json`）中已有完整登录凭证（auth_token + twid），但账号池文件（`~/.xcrawl-accounts.json`）为空数组，导致号池显示 0 个账号。

**根本原因**：`AccountPool._load()` 启动时只从 `~/.xcrawl-accounts.json` 文件读取账号，不会检查 Cookie 文件。而 `sync_cookies_to_pool()` 仅在用户通过 API 操作 Cookie 时才触发（POST/DELETE/capture）。如果账号池文件被清空或丢失，重启后两者不一致。

**修复**：`crawler/account_pool.py`
- 新增 `_try_sync_from_cookies()` 方法：在 `_load()` 加载完成后，若账号池为空，自动从全局 Cookie 文件提取 `twid` 用户 ID，校验 `auth_token` 存在后创建 `AccountEntry` 并持久化
- 避免调用 `sync_cookies_to_pool()`（会通过 `get_pool()` 单例死锁），改为内联同步逻辑



### 🐛 修复：Cookie 注入后登录验证失败（缺少 secure/httpOnly 属性）

**问题**：持久化 Cookie 文件中有 `auth_token` 和 `twid`，注入也显示成功（16 条），但刷新页面后检测不到登录状态，报「缺少 auth_token、twid」。

**根本原因**（三重问题）：
1. **Cookie 属性丢失**：`inject_cookies_to_tab` 只传递了 `name/value/domain`，但 X 的 `auth_token`、`ct0`、`twid` 是 **Secure + HttpOnly** Cookie。缺少 `secure: true` 属性后，浏览器不会在 HTTPS 请求中发送这些 Cookie
2. **注入时机错误**：注入 Cookie 时浏览器可能不在 `x.com` 域下，导致 Cookie 无法正确绑定到目标域
3. **缺少等待时间**：注入后立即刷新页面，浏览器未充分处理 Cookie

**修复**：
- `crawler/cookie_manager.py`：
  - 新增 `_build_cookie_dict()` 函数，构建包含完整属性（path, secure, httpOnly）的 Cookie 字典
  - 新增 `_SECURE_COOKIES` 集合：自动为 `auth_token/ct0/twid/kdt/_twitter_sess` 设置 `secure=True`
  - `inject_cookies_to_tab` 注入前自动导航到 `x.com`，确保 Cookie 绑定到正确域
- `crawler/auth.py`（v4）：
  - `ensure_login` / `ensure_login_with_pool`：注入后等待 1s 处理 + 刷新后等待 2s 加载
  - `inject_account_cookies`：使用 `_build_cookie_dict` 构建完整属性
  - `check_login` 增加调试日志，输出实际检测到的 Cookie 名称和 URL
- 一次性修复已保存的 Cookie 文件（`~/.xcrawl-cookies.json`）中 `secure: false` 的记录

### ✨ 优化：Cookie 管理 — 以账号为单位展示 + 支持删除特定 Cookie

**问题**：Cookie 列表以扁平方式展示 16 条独立 Cookie，无法一眼看出归属哪个账号，也无法删除单条过期 Cookie。

**改进**：
- **后端** (`api/routers/cookies.py`)：
  - `GET /api/v1/cookies` 返回新增 `accounts` 字段，按账号分组，从 `twid` 提取用户 ID
  - 新增 `DELETE /api/v1/cookies/{cookie_name}` 接口：按名称删除特定 Cookie（可选 domain 精确匹配）
  - Cookie 列表每条新增 `category`（auth/session/other）和 `is_critical` 标记
- **前端** (`CookieManager.tsx`)：
  - Cookie 以账号卡片形式展示：显示用户 ID、Cookie 数量、登录状态标签
  - 点击展开查看该账号下的具体 Cookie 明细
  - 支持一键清除整个账号的 Cookie
- **接口文档** (`docs/api.md`)：同步更新 Cookie 管理章节

## 2026-02-27

### ✨ 新增：Cookie 导出功能

- 新增 `GET /api/v1/cookies/export`：以 JSON 文件形式下载完整 Cookie 列表（未脱敏），可用于备份或迁移
- 新增 `GET /api/v1/cookies/export/string`：以 `document.cookie` 格式文本文件下载，方便粘贴到浏览器控制台或其他工具
- 前端 Cookie 管理面板新增「导出 JSON」和「导出文本」两个按钮，有存储 Cookie 时才显示

### 🧹 清理：移除前端目录多余的 Git 仓库

- **操作**：删除了 `frontend/` 目录下误创建的 `.git` 文件夹，避免嵌套 Git 仓库导致的提交追踪问题。

### 🐛 修复：恢复爬取后贴文变少（Checkpoint 恢复失败）

**问题**：无限模式（`max_count=0`）任务完成后点击「继续爬取」，搜索从头开始而非断点续爬，导致贴文数量远少于此前累积的数量。

**根本原因**（三重致命链路）：
1. `x_searcher.py` 的 `finally` 安全兜底保存以 `next_cursor=None` 覆盖了有效 checkpoint，丢失了翻页位置
2. `max_count=0` 时 `not max_count` 为 True，搜索完成后无条件删除 checkpoint 文件
3. 恢复搜索时 checkpoint 不存在，`从断点=False`，全部从头开始

**修复**：`crawler/x_searcher.py`
- 新增 `_last_bottom_cursor` 变量，追踪最后有效翻页 cursor，兜底保存时使用此值而非 None
- 无限模式（`max_count=0`）搜索完成后**不再删除** checkpoint，保留推文历史供恢复使用
- 无 cursor 的无限模式恢复：保留旧推文用于去重，开始新搜索拾取新内容（而非直接返回旧数据）

### 🐛 修复：前端 React key 重复警告

**问题**：控制台报错 `Encountered two children with the same key`，重复 key 来自嵌套评论抓取时返回的相同 reply ID。

**修复**：
- `TweetCard.tsx`：reply 列表 key 改为 `${reply.id}-${idx}`（始终包含索引）
- `tasks/[id]/page.tsx`：推文列表 key 改为 `${tweet.id}-${index}`（始终包含索引）

## 2026-02-26

### ⚡ 性能优化：极速档吞吐提升（数据完整优先）

- 新增 `backend/api/services/performance_tuner.py`，服务启动自动收敛过慢参数并持久化（不改爬虫特征面）。
- `backend/config.py` 新增：
  - `crawler_checkpoint_flush_interval_sec`
  - `crawler_checkpoint_reply_batch`
  - `log_level` 默认调为 `INFO`
- `backend/crawler/reply_fetcher.py` 接入 `backend/crawler/wait_policy.py`，实现“快速抢包 + 补偿等待”，移除冗余长等待链路。
- 新增 `backend/crawler/checkpoint_buffer.py`，DFS 回复阶段检查点改为批次/时间窗刷新；`backend/crawler/checkpoint.py` 改为紧凑 JSON + 原子写入。
- `backend/api/services/task_db.py` 新增 `save_task_summary()`；`backend/api/services/task_manager.py` 高频持久化改为摘要写入，终态/强制点仍全量写入。
- API 轮询减载：
  - `GET /api/v1/search/{task_id}` 新增 `include_tweets`
  - `GET /api/v1/tasks` 新增 `include_payload`
- `backend/api/routers/crawler_config.py` 扩展配置字段：
  - `save_raw_responses`
  - `raw_responses_max_pages`
  - `crawler_checkpoint_flush_interval_sec`
  - `crawler_checkpoint_reply_batch`
- `backend/crawler/response_saver.py` raw JSON 写入改紧凑格式。
- `backend/api/routers/raw_responses.py` 新增 `DELETE /api/v1/raw-responses/all`（一键清理归档）。
- 前端设置与轮询闭环：
  - `frontend/src/hooks/useTask.ts` 运行中轮询轻量模式，终态补拉完整 tweets
  - `frontend/src/hooks/useTasks.ts` 任务列表默认摘要轮询
  - `frontend/src/components/features/settings/RawResponseStorageCard.tsx` 增加归档开关、页数上限、按任务清理、全部清理
  - `frontend/src/components/features/settings/CrawlerConfigCard.tsx` 增加 checkpoint 刷新参数
- 新增测试：
  - `backend/tests/test_api_payload_optimization.py`
  - `backend/tests/test_checkpoint_buffer.py`
  - `backend/tests/test_task_db_summary.py`
  - `backend/tests/test_reply_recovery.py` 增补快速抢包场景
- 验证通过：
  - `PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests`（19 passed）
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`

## 2026-02-26

### 📦 新增：结构化日志系统

- 新增 `crawler/log_config.py`：双输出日志（控制台 INFO + 文件 DEBUG），RotatingFileHandler（10MB × 5 份）
- `config.py` 新增 4 个日志配置项：`log_dir` / `log_level` / `log_max_bytes` / `log_backup_count`
- `api/main.py`：`logging.basicConfig` 替换为 `setup_logging()`

### 🔧 修复：回复翻页策略（v5 重写）

**问题**：v3/v4 中添加的 `_click_show_more()` 按钮点击逻辑基于错误假设。

**抓包分析发现**：X 评论区翻页实际是**纯滚动触发**同一个 `TweetDetail` API（带 `cursor` 参数）。二级评论则是导航到新页面（`focalTweetId` = 一级评论 ID），而非在评论区内展开。

**修复**：`crawler/reply_fetcher.py`（v5）
- 删除 `_SHOW_MORE_TEXTS` 常量和 `_click_show_more()` 函数（约 60 行冗余代码）
- 翻页策略简化为：渐进式滚动 → 等待 TweetDetail 数据包 → 解析
- 恢复逻辑和 no-cursor 分支中也移除了按钮点击调用
- 日志级别调整：高频翻页日志从 INFO 调为 DEBUG

### ✨ 新增：二级评论递归抓取

- 新增 `crawler/nested_reply_fetcher.py`：递归抓取评论的子评论（自动对 `reply_count > 0` 的评论导航到新页面获取子评论）
- 新增 `reply_depth` 参数（默认 2）：1=仅一级评论，2=含二级评论
- 参数贯穿整条调用链：`SearchRequest` → `task_manager` → `crawl_service` → `x_searcher` → `reply_fetcher` → `nested_reply_fetcher`
- 前端 `CrawlerTaskBuilder` 新增「评论抓取深度」选项（仅一级 / 含二级）
- 导出模块 `export.py` 已原生支持嵌套 `reply["replies"]` 结构

### 🐛 修复：DFS 模式下前端预览数据全部为 0

**问题**：DFS 策略抓取时，`crawl_phase` 显示正在抓取回复（如"正在抓取第 3/19 条推文的回复"），但前端 `result_count = 0`、`preview_tweets` 为空，数据库中 `tweets_json` 也为空。

**根本原因**：`x_searcher.py` DFS 分支中 `_on_reply_progress` 回调使用 `_dfs_new_tweets_ref` 过滤原始推文列表中 `replies is not None` 的条目来构建 `interim_tweets`。然而 `fetch_replies_batch` 对每条推文做了 `dict()` 浅拷贝后才设置 `replies`，原始列表中的推文对象始终没有 `replies` 字段，过滤结果始终为空。`update_task_progress` 被调用时用空列表覆盖了之前 `update_preview_tweets` 设置的数据。

**修复**：`crawler/x_searcher.py`
- 改用 `_dfs_processed` 共享可变列表 + `_dfs_tweet_index` 索引
- `_on_reply_progress` 回调中通过 `tweet_id` 从索引查找原始推文，合并 `replies` 后追加到已处理列表
- `interim_tweets` 改为 `_dfs_all_tweets_ref + _dfs_processed`，确保增量数据正确传递

### 🔒 修复：任务中断时已采集数据全部丢失

**问题**：任务被中断（停止/崩溃/异常）后已采集的全部推文数据均丢失，`result_count` 归零。

**根本原因**：三条数据丢失路径：
1. `update_preview_tweets` 不更新 `tweets` 字段也不持久化，中断时内存/DB中 `tweets` 为空
2. `crawl_service.py` 异常处理从未保存已有推文
3. `search()` 的 `finally` 块没有保存进度

**修复**：
- `api/services/task_manager.py`：`update_preview_tweets` 增加 `tweets` 字段同步 + 节流持久化
- `api/services/crawl_service.py`：`Exception` 处理中先保存已有推文再标记错误
- `crawler/x_searcher.py`：DFS 回复抓取前保存 checkpoint + `finally` 块安全兜底保存

## 2026-02-26

### ✨ 重构：前后端深度优化（调度队列 + UI/UX 升级 + 设置闭环）

**后端（FastAPI + Crawler）**
- 新增 `api/services/task_scheduler.py`：内置内存队列调度器，统一任务入队执行，预留 Redis 后端扩展接口。
- `api/services/crawl_service.py` 改为调度器驱动：`start_crawler_thread()` 从直启线程改为入队；任务结束统一回写并清理调度状态。
- 新增 `crawler/runtime_metrics.py`：运行指标采集（超时、软重试、硬刷新、风控命中、空页等）。
- `crawler/x_searcher.py`、`crawler/reply_fetcher.py`、`crawler/page_health.py` 接入运行指标上报。
- `crawler/utils.py` 新增 `interruptible_sleep()`，长等待可响应 `pause/stop`，并将 `jittered_sleep()` 升级为可中断 + 自适应区间约束。
- `api/services/task_manager.py` 重写为线程安全版本：统一锁保护、节流持久化、新增质量状态与事件时间字段。
- `api/services/task_db.py` 轻量补列迁移：新增 `quality_state`、`runtime_metrics_json`、`last_event_at`。
- `api/routers/search.py` 创建任务改为统一入队语义（返回 `pending`）。
- `api/routers/crawler_config.py` 新增配置并持久化：
  - `scheduler_backend`
  - `crawler_adaptive_wait_enabled`
  - `crawler_page_interval_min`
  - `crawler_page_interval_max`
  - `crawler_interrupt_poll_ms`

**前端（Next.js 16 + React 19）**
- 引入 `@tanstack/react-query`，新增 `AppProviders`，统一任务/健康状态轮询数据层。
- 新增全局 Toast 与确认弹层组件（`toast.tsx`、`confirm-dialog.tsx`），移除阻塞式 `alert/confirm`。
- `tasks/[id]` 页面重构：接入 React Query 条件轮询、拆分任务状态/告警/运行指标子组件，修复不稳定 key（移除 `Math.random()`）。
- `settings` 页面拆分：
  - 新增 `useCrawlerConfig` Hook
  - 新增 `features/settings/*` 组件化卡片
  - 新增调度与自适应等待配置 UI，形成设置闭环
- `SearchForm` 合并为 `CrawlerTaskBuilder` 兼容包装，消除重复实现分叉。
- `CookieManager` 重写，清理历史重复片段并改为非阻塞确认流程。
- `globals.css` 重建设计 token（中性色 + 蓝色强调 + 琥珀预警），新增 Skip Link、focus 可视化与 `prefers-reduced-motion` 降级。

**测试与验证**
- 新增测试：`backend/tests/test_task_scheduler.py`
- 更新测试：`backend/tests/test_search_api_concurrency.py`（并发超限 409 语义改为入队 `pending`）
- 通过：`PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests`（13 passed）
- 通过：`frontend npm run lint`
- 通过：`frontend npm run build`

## 2026-02-23

### ✨ 新增：浏览器切换功能 + SPA 优化

**浏览器管理**
- 重构 `browser_detector.py`：支持检测 13 种主流浏览器（Chrome/Edge/Brave/Arc/Firefox/Safari 等）
- 新增 `browser_selector.py` 路由：3 个 API 接口（列出/选择/查询已选浏览器）
- `config.py` 新增 `browser_selected_id` 持久化字段
- `browser.py` 新增 `_resolve_browser_paths()` 三级优先级浏览器解析

**前端**
- 新增 `BrowserSelector.tsx`：浏览器选择卡片组件（自动检测、持久化选择、不兼容标记）
- 设置页新增「浏览器选择」卡片
- API 服务层新增 browsers 和 rawResponses 命名空间
- SPA 优化：统一使用 API 服务层，消除内联 fetch() 调用

## 2026-02-23

### 🐛 修复：每个帖子仅获取约 10 条评论（翻页失效）

**问题**：每个推文下明明有几十甚至上百条评论，却每次只获取约 10 条。

**根本原因**：`reply_fetcher.py` 的翻页机制使用 `tab.scroll.to_bottom()` 来加载更多评论，但 X 的推文详情页实际上需要**点击 "Show more replies" 按钮**才能触发新的 TweetDetail API 请求。简单滚动只能捕获第一批评论。

**修复**：`crawler/reply_fetcher.py`（v3 重写）
- 新增 `_click_show_more(tab)` 函数：检测并点击 "Show more replies" / "显示更多回复" 等按钮（多语言兼容 + CSS 选择器兜底）
- 新增 `_scroll_incremental(tab)` 函数：渐进式多步滚动（每步 500px × 5 步），替代简单的 `scroll.to_bottom()`
- 翻页策略由「直接滚动」改为「优先点击按钮 → 兜底渐进式滚动」
- 利用推文元数据 `metrics.replies`（reply_count）作为预期评论数参考，超时但远未达预期时自动重试
- 连续空页计数器（默认 3 次）自动停止，防止无限循环

**修复**：`crawler/x_searcher.py`
- DFS 模式 `_fetch_replies_for_tweets_with_tab` 从推文 `metrics.replies` 提取预期评论数并传递给 `fetch_replies()`
- 阶段提示增加预期评论数显示

## 2026-02-22

### ✨ 优化：将 GitHub 仓库连接方式改为 SSH

**目标**：提高与 GitHub 仓库关联的稳定性。

**变更**：把 Git remote URL 从 HTTPS (`https://github.com/1064yanzu/X_crawl.git`) 修改为 SSH 格式 (`git@github.com:1064yanzu/X_crawl.git`)。

## 2026-02-22

### 🐛 修复：DFS 模式下前端实时预览不显示数据

**问题**：搜索策略为 DFS（深度优先）时，后端终端日志显示第1页已成功解析，但前端"实时数据流"始终停在"等待第1页数据包..."，`result_count = 0`，无法看到任何推文预览。

**根本原因**：`crawler/x_searcher.py` 中，DFS 模式会在每页推文搜到后**立即进入回复抓取**，而 `update_task_progress()`（负责更新 `preview_tweets`）在回复全部抓完后才被调用。如果每条推文的回复很多（需翻多页），这中间可能长达数分钟，前端拿到的 `preview_tweets` 始终为空。

**修复**：`crawler/x_searcher.py`
- DFS 回复抓取**开始前**，先调用 `update_task_progress()` 将已搜到的推文（含未附回复的版本）写入 `preview_tweets`，前端轮询后立即可见
- 同步更新 `crawl_phase` 为 `"第 N 页已解析 X 条，正在抓取回复..."` 告知用户当前阶段
- `_fetch_replies_for_tweets_with_tab` 新增 `progress_callback` 参数，每条推文回复抓完后触发回调更新 `replies_fetched` 计数
- 函数内部新增 `crawl_phase` 实时更新，显示"正在抓取第 X/N 条推文的回复 (@用户名)..."

## 2026-02-22

### ✨ 新增：任务历史持久化（SQLite）

**问题**：任务数据存储在进程内存中，每次后端重启历史记录全部丢失。

**实现**：内存缓存 + SQLite 磁盘持久化双层架构，零额外依赖（Python 内置 `sqlite3`）。

#### 后端改动

**新增 `api/services/task_db.py`**
- `init_db(path)`: 建库建表
- `save_task(task_dict)`: INSERT OR REPLACE 写入/更新记录
- `load_all_tasks()`: 启动时从 DB 加载全部历史任务
- `delete_task(task_id)`: 删除记录
- 推文数据以 JSON 字符串存储在 `tweets_json` / `preview_json` 列

**修改 `api/services/task_manager.py`** (v5)
- 模块加载时自动 `init_db()` + 加载历史记录到内存
- 历史任务中若状态为 `running`/`pending`（未正常结束），重启后自动变为 `stopped`
- `create_task / update_task_* / delete_task` 均同步持久化到 SQLite
- `update_task_phase`（极高频阶段描述）不写库，避免写入风暴

**修改 `config.py`**
- 新增 `TASKS_DB_PATH` 配置项，默认 `tasks.db`（backend 目录下）

## 2026-02-22

### 🐛 修复：暂停后无法继续任务（事件循环阻塞）

**问题**：点击"继续任务"后任务仍然停留在暂停状态，后端日志持续打印"等待继续信号..."，resume API 请求无任何响应。

**根本原因**：爬虫任务通过 FastAPI `BackgroundTasks` 启动，但爬虫本身是同步阻塞代码（`time.sleep` 轮询等待控制信号）。`BackgroundTasks` 运行同步函数时会占用 uvicorn 事件循环线程，导致整个 API 服务器完全无法处理任何新的 HTTP 请求（包括 resume/pause/stop），控制信号永远无法被写入。

**修复**：`api/routers/search.py`
- 将 `BackgroundTasks.add_task()` 替换为 `threading.Thread(daemon=True)`
- 爬虫任务在独立线程中运行，事件循环不再被阻塞，控制 API 可正常响应

## 2026-02-22

### ✨ 新增：爬取过程中实时数据预览 + 精确阶段状态

**目标**：在爬虫运行期间，除显示状态外，同步在页面展示已爬取的推文预览，让用户更踏实。

#### 前端改动

**新增 `src/components/features/LiveCrawlPreview.tsx`**
- 独立组件，负责运行中/暂停中任务的数据展示
- 无数据时：展示来自后端的精确阶段状态（如"等待第1页数据包..."）+ 旋转动画
- 有数据时：顶部紧凑状态 banner（含精确阶段、数量、进度%）+ 下方推文预览卡片
- 新增 tweet 时有 slide-in-from-top 飞入动效
- 暂停状态：Pause banner + 已有数据正常展示

**修改 `src/app/tasks/[id]/page.tsx`**
- 运行中/暂停中：使用 `<LiveCrawlPreview>` 组件替换原有静态动画
- 完成/终止后：展示全量 `tweets` 列表
- 区域标题从"数据流快照"改为"实时数据流 (Live Stream)"/"采集结果 (Results)"

**修改 `src/services/api/index.ts`**
- `TaskOut` 接口新增 `crawl_phase: string` 字段

#### 后端改动

**修改 `api/services/task_manager.py`**
- 新增 `crawl_phase` 字段（`create_task` 初始化为空字符串）
- 新增 `update_task_phase(task_id, phase)` 方法，供爬虫在关键节点实时更新

**修改 `api/schemas/task.py`**
- `TaskOut` 新增 `crawl_phase: str` 字段

**修改 `crawler/x_searcher.py`**
- 在"等待第N页数据包"节点调用 `update_task_phase()`
- 在"完成第N页"节点调用 `update_task_phase()`（同时包含已获取总数）

## 2026-02-26

### 稳定性与反识别一体化改造（全量）

- 新增：`backend/crawler/page_state.py`、`recovery_policy.py`、`packet_guard.py`、`crawl_signals.py`
- 重构：`x_searcher.py` / `reply_fetcher.py` 恢复链路，支持软重试、硬恢复、挑战页冷却重试
- 新增：风控暂停状态 `risk_state`，并在 `crawl_service` 中实现 challenge 自动转 `paused`
- 新增：搜索创建并发上限（超限返回 `409`）
- 新增配置：
  - `crawler_packet_soft_retries`
  - `crawler_refresh_max_retries`
  - `crawler_challenge_retry_times`
  - `crawler_challenge_cooldown`
  - `crawler_max_concurrent_tasks`
  - `browser_load_mode`
  - `browser_block_images`
- 浏览器策略更新：默认 `normal` 加载模式、默认不禁图，增强启动参数反识别
- 前端更新：设置页高级反风控参数、任务详情风控暂停提示、创建任务 409 友好提示
- 文档更新：`docs/api.md`、`docs/施工文档.md`、`docs/changelog.md`
- 测试新增：`backend/tests/*`（5 组），验证通过 `11 passed`

## 2026-02-26

### 实时可观测与资源保护升级
- 新增任务实时信息：`live_metrics` 扩展硬件占用（主机/进程内存、CPU）、压力状态、节流倍数、调度摘要。
- 新增 `time_coverage`：推文/评论覆盖时间起止与跨度（后端实时计算并持久化）。
- SSE 优化：`/api/v1/tasks/{task_id}/stream` 增加断连退出，快照改为轻量 payload（不推全量 `tweets`）。
- 资源保护：新增 `resource_guard`，按内存/CPU压力自动放慢抓取节奏，并在高压下动态收敛并发。
- 设置闭环：`CrawlerConfig` 新增资源保护参数（自动节流、动态并发、采样间隔、内存/CPU阈值、最大节流倍数）。
- 前端增强：任务详情页新增覆盖时间卡片与硬件指标展示；首页和任务列表补充覆盖时间/内存摘要。
- 跨平台脚本：新增 `scripts/start-backend.sh/.ps1` 与 `scripts/start-frontend.sh/.ps1`。

### 测试
- 后端：`PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests` → `28 passed`。
- 前端：`npm --prefix frontend run build` 通过。
- 前端：`npm --prefix frontend run lint` 0 error（保留历史 warning 4 条）。
