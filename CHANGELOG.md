# Changelog

## [2026-03-28] 任务列表视图密度优化

### 优化
- 任务列表新增三种密度模式：**舒展**（原有大卡片）、**紧凑**（行式布局，操作浮现）、**极简**（表格行式，一行一任务）
- 紧凑模式：将任务卡片从"左内容+右操作栏"改为单行布局，操作按钮在 hover 时浮现，每个任务高度约降低 60%
- 极简模式：以极简表格行展示任务，仅显示核心信息（状态、平台、关键词、结果数、更新时间），全屏列表无右侧预览面板
- `TaskStatusBadge` 新增 `xs` 尺寸，适配极简模式

### 涉及文件
- `frontend/src/components/features/tasks/TaskListCard.tsx` — 重构为三密度模式（Comfortable / Compact / Mini），解耦为独立子组件
- `frontend/src/components/features/tasks/TaskFiltersBar.tsx` — 密度切换新增"极简"按钮
- `frontend/src/hooks/useTaskListState.ts` — DensityMode 类型新增 `mini`，localStorage 恢复兼容
- `frontend/src/app/tasks/page.tsx` — 按密度模式调整列表间距和右侧预览面板显隐
- `frontend/src/components/features/task-detail/TaskStatusBadge.tsx` — 新增 `xs` 尺寸支持

## [2026-03-28] 全局看板 UI 入口 + 实时采集速率面板

### 新增
- `GET /api/v1/analytics/live-rates`：运行中任务实时速率汇总端点（全局聚合 + 每任务速率明细，含 15s/60s/每小时三级窗口）
- 前端「实时采集速率」面板（`LiveRatesPanel`）：看板页顶部展示全局速率卡片 + 每任务速率明细行，带脉冲动画和 15s/60s 趋势对比
- 前端「实时采集」卡片（`DashboardLiveRates`）：控制台首页新增看板入口，精简展示推文/评论每分钟·每小时速率，一键跳转完整看板
- 5 秒自动轮询，数据实时刷新

### 涉及文件
- `backend/api/routers/analytics.py` — 新增 live-rates 端点
- `frontend/src/components/features/analytics/LiveRatesPanel.tsx` — **新建**
- `frontend/src/components/features/DashboardLiveRates.tsx` — **新建**
- `frontend/src/hooks/useAnalytics.ts` — 新增 `useLiveRates` hook
- `frontend/src/services/api/index.ts` — 新增 `LiveRatesResponse` / `TaskRateItem` 类型 + API 方法
- `frontend/src/app/analytics/page.tsx` — 插入 LiveRatesPanel
- `frontend/src/app/page.tsx` — 插入 DashboardLiveRates
- `docs/api.md` — 新增 live-rates 接口文档

## [2026-03-28] 修复并发任务串行化问题

### 问题
- 配置 3 个并发浏览器实例时，任务表现为串行执行（一个操作，其他两个等待）
- 根因 1：`page_health.py` 中的**全局错误计数器** `_consecutive_errors` 被所有并发任务共享，任务 A 的错误会累加到全局计数，导致任务 B/C 的冷却时间被错误升级（从 8s 快速升级到 30s、60s）
- 根因 2：`rate_tracker.py` 中的**全局速率限制追踪器**被所有并发任务共享，不同 slot/账号的 API 配额互相覆盖，导致一个账号的低配额倍增所有任务的等待时间

### 修复
- **`page_health.py`**：将全局 `_consecutive_errors` 计数器改为 `_per_task_errors: dict[task_id, count]`，每个任务独立追踪错误次数和冷却等级
- **`rate_tracker.py`**：将内部状态键从 `endpoint_type` 改为 `(task_id, endpoint_type)` 复合键，每个任务独立追踪 API 配额和速率倍数
- **`crawl_service.py`**：任务结束时清理该任务的速率状态，防止内存泄漏
- 所有调用方（`x_searcher.py`、`reply_fetcher.py`、`nested_reply_fetcher.py`）已传入 `task_id` 参数

### 涉及文件
- `backend/crawler/page_health.py` — 错误计数按任务隔离
- `backend/crawler/rate_tracker.py` — 速率追踪按任务隔离
- `backend/crawler/x_searcher.py` — 传递 task_id 到 rate tracker
- `backend/crawler/reply_fetcher.py` — 传递 task_id 到 rate tracker
- `backend/crawler/nested_reply_fetcher.py` — 传递 task_id 到 rate tracker
- `backend/api/services/crawl_service.py` — 任务结束时清理状态

## [2026-03-28] 复爬数据展示 + 数据分析看板

### 新增
- `GET /api/v1/analytics/overview`：全局数据聚合统计端点（推文/评论总量、每日趋势、平台分布、关键词排行）
- 前端「数据看板」页（`/analytics`）：汇总统计卡片 + 每日采集趋势 Area Chart + 平台分布 bar + 关键词排行表
- 侧栏导航新增「数据看板」菜单项

### 优化
- `TaskOut` 新增 `exclude_count` 字段：复爬任务显示原始推文数量
- 前端 TaskListCard / TaskPreview / DashboardTasks：复爬任务显示「原始 N 条 · 新增 M 条」

### 涉及文件
- `backend/api/routers/analytics.py` — **新建**
- `backend/api/schemas/task.py` — +`exclude_count`
- `backend/api/services/task_manager.py` — 存储 exclude_count
- `backend/api/main.py` — 挂载 analytics router
- `frontend/src/app/analytics/page.tsx` — **新建**
- `frontend/src/components/features/analytics/` — 4 个组件 **新建**
- `frontend/src/hooks/useAnalytics.ts` — **新建**
- `frontend/src/services/api/index.ts` — +字段 +API
- `frontend/src/components/layout/app-shell-config.ts` — +导航

## [2026-03-28] 复爬模式深度优化

### 优化
- 复爬模式自动检测（`exclude_ids` 非空时启用），强制使用 3 天时间窗口替代月级分割，提高数据覆盖率
- `x_time_splitter.py`：新增 `force_window` 参数，复爬时跳过自适应按月升级
- 连续空页容忍度 5→2（复爬模式），遇到已爬取页面快速跳过
- 段落级快跳：时间分段内 0 条新增推文时直接跳到下一段
- 复爬模式跳过模拟阅读、微休息、小憩、长休息，全速推进

### 涉及文件
- `backend/crawler/x_searcher.py` — 复爬模式全链路优化
- `backend/crawler/x_time_splitter.py` — force_window 参数

## [2026-03-27] 增量复爬 + 搜索结果数量提升 + 流程优化

### 新增
- `POST /api/v1/tasks/{task_id}/recrawl`：增量复爬已完成任务，自动排除原始推文（原始数据不动，增量存入独立新任务）
- `POST /api/v1/tasks/recrawl-batch`：批量增量复爬，选中多个任务一键操作
- 前端任务卡片和预览面板新增「增量复爬」按钮
- 前端批量操作栏新增「批量复爬」按钮

### 优化
- `SearchRequest.product` 默认值从 `Top` 改为 `Latest`（Latest 支持无限深度分页，显著提升搜索结果数量）
- `config.py`：时间分割触发阈值 30→7 天，窗口宽度 14→7 天（更细的时间窗口覆盖更多推文）
- `x_searcher.py`：checkpoint 保存节流（每 3 秒最多写一次，DFS 模式减少 I/O 约 80%）
- `scroll_safe.py`：二步滚动合并为一步（去掉冗余 JS 预滚动 + 0.3s sleep）

### 修改文件
- `backend/api/routers/tasks.py` — 新增 recrawl 端点
- `backend/api/schemas/task.py` — product 默认值改为 Latest
- `backend/api/services/task_manager.py` — 支持 exclude_tweet_ids
- `backend/api/services/crawl_service.py` — 传递 exclude_tweet_ids 到 search()
- `backend/crawler/x_searcher.py` — exclude_ids 预填 seen_ids + checkpoint 节流
- `backend/config.py` — 时间分割参数调优
- `backend/crawler/scroll_safe.py` — 单步滚动
- `frontend/src/services/api/index.ts` — 新增 recrawl/recrawlBatch API 方法
- `frontend/src/lib/task-ui.ts` — 新增 canRecrawlTask 判断函数
- `frontend/src/components/features/tasks/TaskBatchActions.tsx` — 批量复爬按钮
- `frontend/src/components/features/tasks/TaskListCard.tsx` — 任务卡片复爬按钮
- `frontend/src/components/features/tasks/TaskPreview.tsx` — 预览面板复爬按钮
- `frontend/src/app/tasks/page.tsx` — 复爬处理函数与状态管理

## [2026-03-27] X 爬虫性能深度优化

### 参数调优
- `config.py`：微休息概率 15%→5%，小憩阈值 250→500 条推文
- `account_pool.py`：安全系数 1.15→1.05（单账号），上界倍数 1.25→1.15
- `human_scroll.py`：翻页步数 3-5→2-4，长停顿概率 12%→6%，回滚概率 18%→10%
- `x_searcher.py`：连续空页容忍 3→5 页，微休息 8-20→5-12s，小憩 60-120→30-60s

### 结构性流程优化
- `x_searcher.py`：删除 DFS 回复期间无实际价值的 idle_scroll；所有搜索页 post_load_wait 从 3.0→1.5s
- `reply_fetcher.py`：实现 batch 级共享 tab 复用（消除每条推文开/关 tab 开销 ~1-2s/条）；post_load_wait 3.0→1.5s；导航延迟补偿 3→5s
- `human_scroll.py`：关闭翻页末尾冗余 `scroll_to_bottom`（`finish_at_bottom=False`）
- `nested_reply_fetcher.py`：绕过 jittered_sleep 重复约束，直接用 interruptible_sleep 计算真实间隔

### 修改文件
- `backend/config.py`
- `backend/crawler/account_pool.py`
- `backend/crawler/human_scroll.py`
- `backend/crawler/x_searcher.py`
- `backend/crawler/reply_fetcher.py`
- `backend/crawler/nested_reply_fetcher.py`

## [2026-03-27] X 搜索结果偏少日志定位

### 排查结论
- 结合 `backend/tasks.db`、`backend/logs/xcrawl.log*` 与原始响应，确认“结果偏少”不是 parser 漏解析
- 多个典型任务（如 `AIGC` / `Claude` / `ChatGPT` 裸关键词）都表现为：
  - 第 1 页约 19 条，`bottomCursor=有`
  - 第 2 页约 20 条，`bottomCursor=无`
  - 随后按既有逻辑正常停止

### 根因判断
- 问题集中在 **`product=Top` + 裸关键词 + 无时间范围** 的搜索策略组合
- 当前实际搜索 URL 为 `https://x.com/search?q=<keyword>&src=typed_query`，未切到 `Latest`
- 高结果量任务普遍自带 `since:/until:` 时间范围，因此覆盖面远大于裸词 Top 搜索

### 文档
- 更新 `docs/施工文档.md`

## [2026-03-27] X 搜索原始响应解析核查与 parser 兼容性加固

### 核查结论
- 新增 `scripts/audit_x_raw_search_parser.py`，用于逐个原始响应文件核对“原始可见推文 ID”与 `parse_search_response()` 输出
- 已对本地 `backend/raw_responses` 全量审计：`1302` 个 SearchTimeline 文件、`21311` 条原始可见推文、`21311` 条解析输出、`0` 个不一致文件
- 结论：当前保存下来的 X 搜索原始响应中，**主结果推文不存在 parser 漏解析**

### 加固
- `backend/crawler/parser.py` 兼容 `TimelineReplaceEntry`
- `backend/crawler/parser.py` 新增对 `TimelineTimelineModule` 中 tweet item 的解析支持，提升对 X 响应结构变动的韧性

### 测试
- 新增 `backend/tests/test_x_parser.py`
- 覆盖 `TimelineReplaceEntry` cursor、module tweet item、非 tweet item 忽略逻辑

## [2026-03-25] 批量导出稳定性与轻量读取优化

### 修复
- 修复批量导出在评论数据 `reply_to=null` 时触发 `TypeError: 'NoneType' object does not support item assignment` 的问题
- 评论递归整理时改为先归一化 `reply_to` 字段，避免脏数据直接导致整次导出 500

### 优化
- 新增 `task_manager.get_task_export_payload()` 轻量导出读取接口
- 单任务导出与批量导出不再走 `get_task_full()` 的完整运行态装饰流程，减少批量导出时的额外 CPU 开销

### 测试与文档
- 为 `reply_to=None` 场景新增导出回归测试
- 为批量导出轻量读取路径新增测试
- 更新 `docs/施工文档.md`

## [2026-03-25] 修复任务暂停状态前端不可见问题

### 问题
- 后端 `pause_task()` 正确设置 `status=paused`，但 `crawl_phase` 仍保留暂停前的活跃文字（如"正在抓取..."），导致用户感知任务仍在运行
- 前端 Dashboard 将 paused 和 running 合并在"进行中"分组，无法区分
- 任务列表页 stat cards 将"运行中 / 暂停"合并计数

### 修复
- **后端** `pause_task()`：暂停时保存原始 `crawl_phase`，替换为"任务已暂停，等待继续信号"
- **后端** `resume_task()`：恢复时还原暂停前的 `crawl_phase`
- **前端** Dashboard：运行中 / 已暂停 / 已完成三组分别展示（已暂停使用琥珀色标识）
- **前端** 任务列表页：stat cards 从 3 列变 4 列，独立显示"运行中"和"已暂停"计数

### 修改文件
- `backend/api/services/task_manager.py`
- `frontend/src/components/features/DashboardTasks.tsx`
- `frontend/src/hooks/useTaskListState.ts`
- `frontend/src/app/tasks/page.tsx`

---

## [2026-03-25] 一键恢复排除已完成任务

### 修复
- `resume_queue()`：队列恢复时跳过 `done` 状态任务，不再重启已完成的采集
- `_do_resume_tasks()`：独立任务恢复同样排除 `done`，仅恢复 `stopped` / `failed` / `paused`

### 修改文件
- `backend/api/services/task_queue_manager.py`
- `backend/api/routers/tasks.py`

## [2026-03-24] 一键暂停 + 智能恢复

### 新增
- 新增 `POST /api/v1/tasks/pause-all`，一键暂停所有活跃任务（running → paused, pending → stopped）
- 任务列表页新增"一键暂停全部"按钮（琥珀色主题），与"一键恢复全部"成对使用

### 优化
- `POST /api/v1/tasks/resume-all` 升级为智能恢复，自动区分三种场景：
  - `user_paused`：恢复用户主动暂停的任务
  - `risk_control`：恢复因风控暂停/失败的任务
  - `mixed`：两种混合时全部恢复
- 恢复后 toast 根据场景显示对应提示文案

### 修改文件
- `backend/api/routers/tasks.py`
- `frontend/src/services/api/index.ts`
- `frontend/src/components/features/tasks/TaskBatchActions.tsx`
- `frontend/src/components/features/tasks/TaskListCard.tsx`
- `frontend/src/app/tasks/page.tsx`
- `backend/tests/test_resume_all_and_export_dedup.py`

---

## [2026-03-21] 浏览器并发状态面板

### 新增
- 后端新增 `GET /api/v1/browser-pool/status` 和 `PUT /api/v1/browser-pool/resize` 端点
- 前端任务列表页新增浏览器并发状态面板（`BrowserPoolPanel`）
- 面板实时展示各 slot 状态（平台、task_id、alive 指示灯）
- 支持 `+` / `−` 按钮动态调整并发数，范围 1–10

### 修改文件
- `backend/api/routers/browser_pool.py`（新增）
- `backend/api/main.py`
- `frontend/src/services/api/index.ts`
- `frontend/src/hooks/useBrowserPool.ts`（新增）
- `frontend/src/components/features/tasks/BrowserPoolPanel.tsx`（新增）
- `frontend/src/app/tasks/page.tsx`

---

## [2026-03-21] 回复抓取性能优化

### 问题
- 爬虫在回复抓取阶段大量时间浪费在等待和重试上，而非实际的网络请求
- 低评论推文（预期 1-2 条）首页返回 0 条后进入昂贵的 3 轮空页重试+硬刷新，单次耗时约 2-3 分钟
- 一级评论和二级评论各自叠加完整的动态间隔等待（5-9s × 2），实际导航已占 3-4s
- 快速完成条件仅在第一页生效，后续页达标后仍继续不必要的翻页

### 优化
- `reply_fetcher.py`：
  - 低评论推文（≤3 条）首页无数据时直接跳过，避免 3 分钟级重试循环
  - 快速完成条件由仅第一页扩展到所有页，任何页达到预期数量即停止
  - Batch 级动态间隔扣除导航延迟补偿（~3s），缩短有效等待约 50%
- `nested_reply_fetcher.py`：嵌套评论间隔缩减至原来的 40-50%，因导航本身已贡献延迟
- `wait_policy.py`：翻页前 DOM 稳定等待从 0.2-0.6s 缩至 0.1-0.3s
- `recovery_policy.py`：软恢复退避基值从 0.8s 降至 0.5s，上限从 4.0s 降至 2.5s

### 修改文件
- `backend/crawler/reply_fetcher.py`
- `backend/crawler/nested_reply_fetcher.py`
- `backend/crawler/wait_policy.py`
- `backend/crawler/recovery_policy.py`

---

## [2026-03-21] 任务一键恢复与批量导出去重

### 新增
- 新增 `POST /api/v1/tasks/resume-all`，可一键恢复 `paused / stopped / failed` 任务
- 任务列表页新增“一键恢复全部”按钮
- 批量导出弹窗新增“导出时去重”选项

### 优化
- 批量导出在合并模式下支持跨任务全局去重，分 Sheet 模式下支持各任务独立去重
- 单任务导出 `CSV / Excel` 同步支持 `deduplicate` 参数
- 暂停任务现在也会在任务列表卡片和快速预览中显示“继续”入口

### 修复
- 修复任务列表 `busyAction` 类型未覆盖 `resumeAll` 导致的前端类型不一致问题
- 修复一键恢复队列任务时仅记录首个失败任务的问题，现会聚合整队列失败项

### 测试与文档
- 新增 `backend/tests/test_resume_all_and_export_dedup.py`
- 更新 `docs/api.md` 与 `docs/施工文档.md`

---

## [2026-03-20] 搜索无结果时间段快速跳过

### 问题
- X 搜索某个时间段返回 "No results for ..." 时，爬虫在等待 SearchTimeline 数据包
- X 的 "No results" 页面可能不触发 SearchTimeline GraphQL 请求，导致爬虫在等不到数据包后进入软重试 → 硬刷新的完整恢复流程，白白浪费数分钟
- 此外，当 API 返回了数据包但推文列表为空（0 条新推文）且仍带有 bottom_cursor 时，搜索循环会继续无意义翻页

### 修复
- `page_state.py`：新增 `detect_no_results()` 函数，检测页面可见文本是否包含 "No results for" 等无结果标记
- `x_searcher.py`：
  - 新增 `_NO_RESULTS_SENTINEL` 哨兵常量
  - `_wait_search_packet_with_recovery`：在软重试和硬刷新超时后，立即检测页面是否为无结果页，是则返回哨兵跳过后续重试
  - `search()` 主循环：识别哨兵后立即 break，让时间分段循环跳到下一个段
  - `search()` 主循环：新增连续空页计数器（`_consecutive_empty_pages`），连续 3 页无新推文即停止当前时间段搜索

### 修改文件
- `backend/crawler/page_state.py` - 新增 `detect_no_results()` 函数
- `backend/crawler/x_searcher.py` - 无结果快速跳过 + 连续空页检测

---

## [2026-03-20] JS 未执行空壳页检测

### 问题
- 爬取 X 时偶尔出现页面只显示 "JavaScript is not available" 的降级文本
- 原因是 X.com 为纯 SPA，JS 未执行时页面只剩 `<noscript>` 标签内的降级内容
- 可能由网络不稳定、CDN 拦截、页面加载超时等原因导致

### 修复
- `page_state.py`：新增 `_is_js_not_executed()` 检测函数，当可见文本极少（<80字符）且原始 HTML 包含 "javascript is not available" 时，判定为 `TRANSIENT_ERROR`，触发自动刷新重试
- `page_health.py`：更新二次验证逻辑，当 reason 包含 "JS 未执行" 时跳过 noscript 误判修正，确保空壳页不会被错误放行

### 修改文件
- `backend/crawler/page_state.py` - 新增空壳页检测逻辑
- `backend/crawler/page_health.py` - 二次验证兼容性修正

---

## [2025-03-18] 配置字段缺失修复

### 问题
- 后端启动时报错：`'Settings' object has no attribute 'crawler_cross_platform_concurrent'`
- `crawler_config.py` 中使用了该字段，但 `config.py` 中未定义

### 修复
- 在 `config.py` 的 `Settings` 类中添加 `crawler_cross_platform_concurrent` 字段
- 默认值为 `True`，允许 X 和微博任务跨平台并发执行

---

## [2025-03-18] 多账号 Cookie 管理修复

### 问题
- X 和微博的多账号并发功能存在 Cookie 覆盖问题
- 输入新账号的 cookie 后，会直接覆盖上一个账号，而不是增加新账号

### 根本原因
1. **X Cookie 管理** (`cookie_manager.py`)
   - `save_cookies()` 的合并逻辑按 `(name, domain)` 作为唯一键
   - 导致不同账号的同名 Cookie（如 `auth_token`）相互覆盖

2. **微博 Cookie 管理** (`weibo/cookie_manager.py`)
   - `save_cookies()` 直接覆盖整个文件，没有合并逻辑
   - 每次保存新 cookie 都会清除旧账号的 cookie

3. **账号分组逻辑** (`cookie_account_sync.py`)
   - `group_cookies_by_account()` 的分组策略不够精确
   - 多账号 cookie 混乱分配

### 修复方案

#### 1. X Cookie 管理 - 按账号分组保存
- 修改 `save_cookies()` 的合并键从 `(name, domain)` 改为 `(user_id, name, domain)`
- `user_id` 从 `twid` Cookie 中提取
- 同账号同名 cookie 才会覆盖，不同账号的 cookie 保留

#### 2. 微博 Cookie 管理 - 添加合并模式
- 为 `save_cookies()` 添加 `merge` 参数（默认 `True`）
- 合并模式：按 `(SUB, name)` 作为唯一键（SUB 是微博账号标识）
- 覆盖模式：用于清空操作
- 更新 API 路由调用时使用 `merge=True`

#### 3. 账号分组逻辑优化
- 改进 `group_cookies_by_account()` 的分组策略
- 先收集所有 twid cookie，建立账号映射
- 再分配其他 cookie 到对应账号

### 修改文件
- `backend/crawler/cookie_manager.py` - X Cookie 管理
- `backend/crawler/weibo/cookie_manager.py` - 微博 Cookie 管理
- `backend/api/routers/weibo_cookies.py` - 微博 API 路由
- `backend/crawler/cookie_account_sync.py` - 账号分组逻辑

### 测试建议
1. 添加第一个 X 账号的 cookie，验证保存成功
2. 添加第二个 X 账号的 cookie，验证两个账号都存在
3. 查看 `GET /api/v1/cookies` 确认按账号分组显示
4. 对微博重复相同测试
5. 验证账号池中两个账号都能正确识别

## 2026-03-21

### 运维
- 已停止占用 `3721` 端口的前端进程
- 已停止占用 `8000` 端口的后端进程
- 复查确认两个端口当前均已释放
