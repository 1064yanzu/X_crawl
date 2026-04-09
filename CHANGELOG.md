# Changelog

## [2026-04-09] 微博搜索翻页反爬优化（V3）：点击翻页 + CDP 死亡恢复 + 间隔修正

### 问题
微博搜索每次翻到第 9 页左右就会触发反爬风控，页面卡住无法继续。浏览器显示页面已正常加载，但爬虫卡死无法继续。

### 根因（共 6 个问题）
1. **URL 直接导航被识别为机器人**：爬虫通过构造完整 URL（`page=N`）跳转到每一页
2. **翻页间隔被截断**：虽然微博配置间隔为 12 秒，但 `jittered_sleep` 中的自适应等待将其截断为 `crawler_page_interval_max=6.0` 秒
3. **分段切换无间隔**：日期分段之间 0 秒间隔
4. **CDP 连接死亡**（核心问题）：点击"下一页"后 `wait.load_start()` 在页面已加载完毕情况下等待下一个永不到来的加载事件，阻塞 CDP WebSocket 管道 30+ 秒
5. **`run_js()` 轮询超时**（V1 bug）：CDP 上下文销毁后所有 JS 执行超时
6. **回退导航叠加卡死**：点击已触发导航 + URL 导航冲突

### 修复

#### `backend/crawler/weibo/pagination.py`（V3 重写）
- **去掉 `wait.load_start()` 和 `wait.doc_loaded()`**——这两个方法在页面已加载完毕时会等待下一个永不到来的事件，阻塞 CDP 管道
- 改用 **`sleep(1.5)` + 短超时轮询**：通过 `tab.url` 和 `tab.html`（原生属性）验证页面
- 新增 **CDP_DEAD 标记**：连续 3 次 tab 属性读取失败时返回 `CDP_DEAD:` 前缀错误，调用方据此重建 tab

#### `backend/crawler/weibo/searcher.py`
- **CDP 死亡自动恢复**：检测到 `CDP_DEAD` 标记后自动重建 tab，用 URL 导航继续
- **绕过自适应等待**：不使用 `jittered_sleep`（会被 `crawler_page_interval_max=6s` 截断），改用 `interruptible_sleep` + 手动 ±20% 抖动
- 前 5 页预热间隔（1.2~1.5 倍基础值）
- 日期分段切换间隔（1.0~1.5 倍基础值）

#### `backend/config.py`
- `weibo_search_page_interval` 默认值从 6.0 提高到 **12.0 秒**

### 效果
| 维度 | 修复前 | 修复后 |
|------|--------|--------|
| 导航方式 | URL 直接跳转 | 点击"下一页"按钮 |
| 前 5 页间隔 | 3.0~4.8s（被截断） | 14~18s |
| 第 6 页起间隔 | 3.0~4.8s（被截断） | 10~14s |
| CDP 死亡恢复 | 卡死 30+ 秒 | 自动重建 tab 继续 |

## [2026-04-09] 修复微博搜索翻页间隔过短触发风控

### 问题
微博搜索前几页翻页间隔只有 3-5 秒，远低于配置的 6 秒，导致第 9 页左右就触发微博反爬风控。

### 根因
1. `jittered_sleep(page_interval, fast_mode=True)` 中 `fast_mode=True` 将间隔缩短为配置值的 50-80%（6s → 3.0~4.8s）
2. 前几页没有预热间隔——新建搜索会话后立刻高频翻页，而微博对新会话初期最敏感
3. 日期分段切换时完全没有间隔——前一个分段的最后一页到下一个分段的第一页秒切

### 修复

#### `backend/crawler/weibo/searcher.py`
- 移除 `fast_mode=True`，改用 `fast_mode=False` 使用完整配置间隔（6s ± 20% 抖动 ≈ 4.8~7.2s）
- 新增前 3 页预热间隔：使用 1.3~1.6 倍基础间隔（约 8~10 秒），模拟真人首次浏览
- 新增日期分段间间隔：1.0~1.5 倍基础间隔（约 6~9 秒），避免分段切换时无间隔连续请求

### 效果
| 阶段 | 修复前 | 修复后 |
|------|--------|--------|
| 前 3 页 | 3.0~4.8s | 7.8~9.6s（预热） |
| 第 4 页起 | 3.0~4.8s | 4.8~7.2s（正常） |
| 分段切换 | 0s（无间隔） | 6.0~9.0s |

## [2026-04-09] 修复任务队列自动推进失效——前序任务完成后后续任务不自动启动

### 问题
任务队列中排在第 1 位的任务爬取完成后，后续排队的任务（队列位置 2、3…）不会自动启动，一直卡在"任务已恢复，队列等待中"状态。

### 根因
`task_queue_manager.notify_task_terminal()` 在任务到达终态时，只处理了两种场景：
1. 所有任务都已完成 → 标记队列为 `completed`
2. 状态残留任务（running/pending 但线程已死）→ 仅在并发模式（`max_concurrent > 1`）下重新入队

**缺失的关键逻辑**：
- 没有检查队列中是否有**尚未启动的等待任务**（status 为 `stopped` 且 `result_count=0` 的初始化等待任务）
- 串行模式（`max_concurrent=1`）下，状态残留的恢复逻辑也被跳过（由 `if max_concurrent > 1` 门控）
- 这些等待中的任务被 `_TERMINAL_STATUSES` 判定为"已完成"，导致队列被误标为 `completed`

### 修复

#### `backend/api/services/task_queue_manager.py`
- `notify_task_terminal()` 新增 `waiting_ids` 收集逻辑：
  - 识别 `stopped` 且 `result_count=0` 的未启动等待任务
  - 识别 `pending` 但线程未启动的遗留任务
  - 这两类任务不再被视为"已完成"，队列不会被误标为 `completed`
- 移除 `max_concurrent > 1` 的门控限制：无论串行还是并发模式，都通过 `crawl_service.start_crawler_thread()` → 调度器统一控制并发
- 新增自动调度逻辑：
  1. 恢复状态残留的任务（running/pending 但线程已死）→ 直接提交调度器
  2. 调度尚未启动的等待任务 → 先 `resume_finished_task` 重置状态再提交调度器

### 效果
队列中的任务按顺序自动推进：第 1 个任务完成后，第 2 个自动启动；第 2 个完成后，第 3 个自动启动，以此类推。


## [2026-04-09] Watchdog 优化：搜索任务零产出检测与自动恢复

### 问题
微博/X 搜索任务（`task_kind == "search"`）长时间卡住不动（爬取数量长时间为 0）时，watchdog 完全无感知，无法自动恢复。原有 watchdog 仅监控 `comment_backfill` 和 `comment_backfill_group` 两类任务。

### 根本原因
- Watchdog `maybe_heal_stale_active_tasks` 主循环只过滤和处理上述两种 task_kind，搜索任务完全在监控盲区之外
- 微博搜索 `_safe_get_html` 在 JS 导航或 `tab.get()` 阶段可能长时间阻塞，且内部重试不更新 telemetry 事件，导致 `idle_sec` 暴增

### 改动

#### `backend/api/services/task_watchdog.py`（重写）
- 新增 `_check_search_task_stall()`：扫描所有 `status == "running"` 的搜索任务，利用 telemetry `idle_sec`（优先）+ `last_event_at`（回退）双重方式判断空闲时长
- **分级告警策略**：
  - 空闲 ≥ `crawler_search_stall_warn_sec`（默认 5 分钟）：更新任务 phase 发出警告，暂不干预
  - 空闲 ≥ `crawler_search_stall_timeout_sec`（默认 10 分钟）：执行自愈重启（停止线程 → 保存已有数据 → 重新排队）
- 带冷却机制：同一任务警告间隔 3 分钟、自愈间隔 5 分钟，防止反复干预
- `_heal_stale_task` 新增防御：`search` 任务重启前自动补全缺失的 `product` 字段，避免 `_build_worker_payload` KeyError
- `clear_rate_samples` 同步清理搜索任务的冷却状态

#### `backend/crawler/weibo/searcher.py`
- 在翻页重试循环中（每次 `_safe_get_html` 调用前）发送 `weibo_page_attempt` telemetry 心跳，让 watchdog 能区分「正在重试」和「完全死锁」
- 每次翻页成功完成时发送 `weibo_page_done` 心跳（含本页新增推文数），更准确反映进度

#### `backend/crawler/x_searcher.py`
- 已有充足的 telemetry 心跳（`search_wait_packet` 每页开始前都会触发），无需修改

#### `backend/config.py`
- 新增 `crawler_search_stall_timeout_sec`（默认 600 秒 / 10 分钟）：搜索任务自愈阈值
- 新增 `crawler_search_stall_warn_sec`（默认 300 秒 / 5 分钟）：搜索任务警告阈值

#### `backend/api/routers/crawler_config.py`
- `CrawlerConfig` schema 新增两个字段（含合法性约束）
- GET / PUT 端点同步支持读写和持久化新配置项
- 修复 PUT 端点返回值遗漏 `crawler_active_task_watchdog_*` 三个原有字段的问题

#### `backend/tests/test_task_watchdog.py`
新增 3 个测试用例（共 5 个全部通过）：
- `test_watchdog_warns_on_stalling_search_task`：空闲超过 warn 阈值时仅告警，不自愈
- `test_watchdog_heals_stuck_search_task`：空闲超过 stall 阈值时正确执行自愈重启
- `test_watchdog_search_task_heal_cooldown`：冷却机制防止同一任务被重复自愈

### 效果
搜索任务（X 或微博）卡住后：
- 5 分钟后：watchdog 在日志中发出 WARNING，并在 UI 的任务 phase 中显示提示
- 10 分钟后：watchdog 自动停止卡死任务，保存已有数据，重新排队继续爬取



### 问题
微博搜索爬虫在翻到第 4 页时频繁卡住/超时，即使浏览器中搜索结果已正常加载。

### 根因
`_safe_get_html()` 使用两阶段导航策略：先 JS 导航（`window.location.href`），失败后回退 `tab.get()`。问题在于：

1. JS 导航 `window.location.href = url` **已触发浏览器导航**，页面开始加载
2. 导航后旧 CDP 执行上下文被销毁，`tab.run_js()` 轮询因上下文切换全部超时
3. 12 秒 deadline 到期后，代码回退到 `tab.get(url)` 对同一 URL **重复导航**
4. 双重请求可能触发微博反爬，且浪费了已加载好的页面

前 3 页因页面较轻，JS 轮询在 12 秒内赶上了新执行上下文建立；第 4 页稍重，刚好错过窗口。

### 修复
- `backend/crawler/weibo/searcher.py`
  - JS 导航已触发但 `run_js()` 提取失败时，插入一步 `tab.html` 等待读取（DrissionPage 原生属性能正确处理 CDP 上下文切换），避免 `tab.get()` 双重导航
  - JS 导航轮询 deadline 从 12 秒加长到 15 秒，`run_js()` 超时从 2 秒增加到 3 秒
  - 当 `tab.html` 在 4 秒内成功读取已加载页面时，直接返回，完全跳过 `tab.get()` 路径

### 附带改进（X 搜索）
- `backend/crawler/x_searcher.py`
  - 从 `early_exit_check` 回调中移除 `detect_end_of_timeline`，避免在 API 响应到达前误判”时间线到底”
- `backend/crawler/page_state.py`
  - `detect_end_of_timeline` 阈值从 ≤10 降到 ≤3，新增 loading indicator 选择器

## [2026-04-08] 修正微博搜索页 timeout 误判为”浏览器卡住”

### 问题
微博搜索过程中出现 `Page.stopLoading timeout` 时，日志会写成“超时，可能是浏览器卡了”。但实际场景里浏览器进程、标签页和页面渲染可能都还正常，只是 DevTools 的停止加载调用没在超时内返回。

### 修复
- `backend/crawler/weibo/searcher.py`
  - `_safe_get_html()` 在导航 timeout 后，先检查当前 tab 的 URL 和 DOM 是否已可用；若页面其实已经加载出来，则直接复用当前 HTML，不再误判为失败。
  - timeout 错误文案调整为“页面导航超时（浏览器/标签页可能仍在线）”，不再把 page-level timeout 误写成浏览器卡死。
  - 搜索重试日志同步调整为“tab 仍在线，未判定浏览器卡死”。
  - 修复 timeout 诊断链路的回归：当 `tab.url` / `tab.html` 自身也发生 CDP timeout 时，只把诊断信息拼进错误文案，不再抛出二次异常导致任务直接失败。
  - 新增微博搜索页 JS 导航快速路径：当页面肉眼已加载、但 `tab.get()` 迟迟不返回时，优先通过 `window.location.href` + 轻量 DOM 就绪探测拿到 HTML，避免卡在 DrissionPage 的 `Page.stopLoading` 等待上。
- `backend/tests/test_weibo_searcher_timeout_handling.py`
  - 新增回归测试，覆盖“stopLoading timeout 但 DOM 已就绪”“timeout 且 DOM 未就绪”“timeout 后诊断读取再次 timeout”“搜索页优先走 JS 快速导航”四条路径。

## [2026-04-08] 修复浏览器首次启动误报“连接失败”

### 问题
macOS 下独立启动 Chrome 时，程序会优先尝试复用真实用户数据目录。某些多 Profile 场景中，即便启动前未检测到 `SingletonLock`，DrissionPage 仍可能在初始化阶段卡住并抛出“浏览器连接失败”。

### 根因
- 现有逻辑只在“目录已被占用”时回退到爬虫专用 Profile。
- 对“真实用户目录未显式上锁，但启动仍失败”的情况，没有在浏览器初始化层即时兜底。
- 导致第一次失败被抛到上层 `searcher` 的 tab 重试流程里，额外消耗一轮约 30 秒等待。

### 修复
- `backend/crawler/browser.py`
  - 新增浏览器启动 helper，统一处理启动、超时配置与会话状态同步。
  - 当真实用户目录启动失败时，在同一次 `_create_browser()` 调用里立即回退到 `~/.xcrawl-browser-profile` 并重试。
- `backend/tests/test_browser_user_data_preference.py`
  - 新增回归测试，覆盖“真实用户目录失败 -> 隔离 Profile 自动接管”的恢复链路。
- `frontend/src/components/features/settings/EngineConfigCard.tsx`
  - 调整设置说明，明确“稳定复用真实登录态”更推荐调试端口接管模式。
- `frontend/src/components/features/BrowserSelector.tsx`
  - 调整自动模式说明，明确独立启动失败会自动回退隔离 Profile。
- `docs/api.md`
  - 更新浏览器管理文档，补充推荐策略说明。

## [2026-04-06] 新增用户认证状态字段（X + 微博）

### 背景
做数据分析时需要区分官方媒体、自媒体网红、企业账号等用户类型。原始 API 响应中有丰富的认证字段但未被解析和导出。

### 变更内容

#### X (Twitter) — 新增字段
- `professional_type`: 专业账号类型（Business / Creator）
- `professional_category`: 专业账号行业分类（如 Science & Technology）
- `affiliate_label`: 关联标签（自动化账号、机构关联等）

#### 微博 — 新增/统一字段
- `verified_type` (数字): -1=无, 0=个人黄V, 1=企业蓝V, 2=媒体, 3=其他
- `verified_type_str`: 认证类型文字（yellow/blue/media/other）
- `verified_reason`: 认证原因说明（帖子和评论统一拥有此字段）
- `mbtype`: 微博会员类型
- `mbrank`: 微博会员等级（0-6）

#### 导出层
- 新增 3 列：「认证类型」「认证说明」「专业账号」
- 「认证状态」列增强：微博区分黄V/蓝V，X 区分蓝标/官方/关联标签

#### 前端展示
- 新增 `VerifiedBadge` 组件，区分不同认证类型徽标颜色
  - X 蓝标：蓝色 ✓ | X 官方 (Business/Government)：金色 ✓
  - 微博黄V：金色 ✓ | 微博蓝V：蓝色 ✓
- TweetCard 和 ReplyCard 均显示认证徽标，hover 可看认证详情

### 文件变更
- `backend/crawler/parser.py` — 新增 `_extract_professional`、`_extract_affiliate_label`
- `backend/api/schemas/user.py` — 新增 `professional_type`、`professional_category`、`affiliate_label` 字段
- `backend/crawler/weibo/models.py` — WeiboPost/WeiboComment 新增 verified_type_num/verified_type_str/verified_reason/mbtype/mbrank
- `backend/crawler/weibo/comment_fetcher.py` — 评论解析补充 verified_type/mbtype/mbrank，新增 `_map_weibo_verified_type`
- `backend/crawler/weibo/html_parser.py` — HTML 解析补充 verified_type_num 近似映射
- `backend/api/routers/export.py` — 导出新增 3 列，新增 `_format_verified_status`、`_format_verified_type`
- `backend/api/routers/batch_export.py` — 同步更新列宽
- `frontend/src/components/features/VerifiedBadge.tsx` — 新增认证徽标组件
- `frontend/src/components/features/TweetCard.tsx` — 引用 VerifiedBadge，ReplyCard 也加上徽标

---

## [2026-04-06] 修复微博评论导出丢失 BUG

### 问题
微博搜索任务在特定代码路径下，评论数据被存储在 `"comments"` 键下而非统一的 `"replies"` 键，导致导出（CSV/Excel）时评论被静默丢弃。

### 根因
1. **`searcher.py:581`**（日期分割统一评论抓取路径）：`new_dict["comments"] = [c.__dict__ ...]`
   - 使用了错误的键名 `"comments"` 而非 `"replies"`
   - 同时使用 `__dict__` 进行序列化，导致子评论（`WeiboComment` 对象）无法被正确递归序列化
2. **`pipeline.py:636`**（`WeiboCommentPipeline` dict 分支）：`post_dict["comments"] = comment_result.comments`
   - 同样使用了错误的键名
   - 未对 `WeiboComment` 对象调用 `.to_dict()` 进行序列化

### 修复
- `searcher.py:581` → 改用 `"replies"` 键 + `.to_dict()` 序列化
- `pipeline.py:636` → 改用 `"replies"` 键 + `.to_dict()` 序列化

### 验证结论
- **X/Twitter 侧**：导出功能本身完整，已包含评论和评论补采任务导出，无 bug
- **微博侧**：仅上述两个代码路径存在键名不一致，其余路径（`WeiboPost.to_dict()`、评论补采 runner 等）均正确使用 `"replies"`

### 文件变更
- `backend/crawler/weibo/searcher.py` — 修复评论键名和序列化方式
- `backend/crawler/pipeline.py` — 修复 WeiboCommentPipeline 评论键名和序列化方式

---

## [2026-04-05] 并发爬取性能深度优化 + Watchdog 速率监控

### 问题
3 路并发模式下 7 个 Chrome 进程把 MacBook Air 打爆：
- 大量 30s 导航超时（`Page.stopLoading timeout`）
- 错误页面连续出现（浏览器卡死/响应慢）
- scroll 操作频繁超时
- "连续 2 页无新评论" 过早放弃热门推文（覆盖率仅 4-9%）
- 并发反而比单路更慢

### 性能优化措施
1. **`crawler_timeout` 30s → 15s**：快速失败快速重试，不在超时上浪费时间
2. **DrissionPage 内部超时 30s → 15s**：`browser.set.timeouts(base=10, page_load=15)` 在浏览器实例创建后设置
3. **scroll 超时 4s → 2s**：scroll_safe 模块更快回退到 JS 方式
4. **空页判断放宽**：不再 `min(max_empty, 2)` 激进终止，改用 `_dynamic_max_empty_pages` 完整阈值（预期>2000条 → 允许连续 12 页空才放弃）
5. **每 Pipeline reply worker 1 → 3**：3 Pipeline × 3 worker = 9 并发 tab，充分利用 CPU 和带宽
6. **浏览器预热间隔 2s → 1s**：加快初始化

### Watchdog 速率监控（新增）
- 每 30s 采样一次运行中 `comment_backfill_group` 任务的 `replies_fetched`
- 计算 replies/min 速率，低于 `crawler_watchdog_min_reply_rate`（默认 1000 条/分）时告警
- 速率 > 0 但低于阈值：更新任务 phase 提示用户，不自动重启
- 速率 == 0 且超过 5 分钟：判定卡死，自动 stop + 重排任务
- 告警冷却 120s 防止刷屏
- 新增配置项 `crawler_watchdog_min_reply_rate`

### 文件变更
- `backend/config.py` — `crawler_timeout` 15s、新增 `crawler_watchdog_min_reply_rate`
- `backend/crawler/scroll_safe.py` — `_SCROLL_TIMEOUT_SEC` 4s → 2s
- `backend/crawler/browser_pool.py` — 浏览器实例创建后设置 `set.timeouts()`
- `backend/crawler/reply_fetcher.py` — 空页判断放宽，使用完整 `max_empty_pages` 阈值
- `backend/crawler/parallel_backfill_coordinator.py` — `reply_worker_count_per_pipeline` 1→3、预热间隔 2s→1s
- `backend/api/services/task_watchdog.py` — 新增速率监控 `_check_group_reply_rates` + 自愈逻辑

---

## [2026-04-05] 任务详情页并发数选择器

### 背景
评论补采任务组的并发数调整之前只能在任务列表页的恢复操作中设置，不够直观。
用户希望在任务详情页随时可见、随时可调。

### 新增功能
- **独立并发数更新接口**：`PATCH /tasks/{id}/concurrency` — 任何状态下均可修改，不必等到恢复时才调整
- **任务详情页并发选择器**：`comment_backfill_group` 任务的详情页头部 4 宫格最后一格，显示 1-5 并发按钮组，点击即时保存
- **前端 API 新增 `updateConcurrency`**：调用 PATCH 接口，支持 toast 反馈
- **resume 自动携带并发数**：`useTaskControls` 在恢复 `comment_backfill_group` 时自动将当前 `concurrency` 传递给 resume API，确保带上正确的并发配置
- **运行中提示**：并发选择器在任务运行中时显示"修改将在下次恢复时生效"，引导用户在恢复前设置

### 文件变更
- `backend/api/routers/tasks.py` — 新增 `PATCH /{task_id}/concurrency` 端点
- `frontend/src/services/api/index.ts` — 新增 `tasks.updateConcurrency()` 方法
- `frontend/src/components/features/task-detail/TaskDetailHeader.tsx` — 新增 `ConcurrencySelector` 组件 + 新 props (`savingConcurrency`, `onConcurrencyChange`)
- `frontend/src/app/tasks/[id]/page.tsx` — 新增 `handleConcurrencyChange` 回调，透传到 Header
- `frontend/src/hooks/useTaskControls.ts` — resume 时自动传递 `comment_backfill_group` 的 concurrency

---

## [2026-04-05] 恢复任务组时支持动态修改并发数

### 背景
已运行的评论补采任务组（comment_backfill_group）恢复时无法修改并发数，只能沿用创建时的设置。
老任务甚至没有 concurrency 字段，恢复后只能走单路模式。

### 新增功能
- **后端 resume 接口扩展**：`POST /tasks/{id}/resume` 接受可选 body `{ concurrency: N }`，恢复前动态更新 task dict
- **DB 持久化**：`concurrency` 列写入 SQLite，服务重启后也能保留设置
- **内嵌并发选择器**：在任务卡片（Comfortable 布局）和预览面板中，`comment_backfill_group` 可恢复时直接显示 1-5 并发按钮组，选好后点「继续」即带上新并发数
- **任务标签优化**：任务列表中 `comment_backfill_group` 显示为「评论补采组(N路)」，直观反映并发配置
- **task_manager 新增 `update_task_field`**：通用的单字段更新 + 持久化方法

### 文件变更

**修改文件**
- `backend/api/schemas/task.py` — 新增 `TaskResumeRequest` schema + `TaskOut.concurrency` 字段
- `backend/api/routers/tasks.py` — resume 接口接受可选 body + 动态更新 concurrency
- `backend/api/services/task_manager.py` — 新增 `update_task_field()` 方法
- `backend/api/services/task_db.py` — 新增 `concurrency` 列（ensure_column + summary_params + upsert）
- `frontend/src/services/api/index.ts` — `resume()` 支持可选 `{ concurrency }` body + `TaskOut.concurrency`
- `frontend/src/app/tasks/page.tsx` — `handleResume` 支持透传 concurrency
- `frontend/src/components/features/tasks/TaskListCard.tsx` — Comfortable 布局内嵌并发按钮组
- `frontend/src/components/features/tasks/TaskPreview.tsx` — 预览面板内嵌并发按钮组
- `frontend/src/lib/task-ui.ts` — `getTaskKindLabel` 识别任务组并显示并发数

---

## [2026-04-05] 评论补采任务组支持多路并发

### 背景
评论补采任务组（comment_backfill_group）原先只使用 1 个浏览器 + 1 个账号，吞吐量受限于单进程性能。
即使系统有多个可用账号和浏览器资源，也无法并行利用。

### 新增功能
- **多 Pipeline 并发**：用户创建任务组时可指定并发数（1-5），每路使用独立账号 + 独立 L1/L2 浏览器
- **Round-robin 负载均衡**：推文按评论数排序后交错分配到各 Pipeline，确保负载均匀
- **线程安全进度聚合**：所有 Pipeline 共享回调，统一更新任务进度
- **信号自动传播**：N 个 Pipeline 共用同一 task_id，pause/resume/stop 零改动即生效
- **向后兼容**：旧任务无 concurrency 字段时默认 1，走原有单 Pipeline 路径

### 文件变更

**新增文件**
- `backend/crawler/parallel_backfill_coordinator.py` — 并行协调器，WorkerResource 数据结构，chunk 分块，N Pipeline 生命周期管理

**修改文件**
- `backend/config.py` — 新增 `comment_backfill_group_max_concurrency` 配置项（默认 3）
- `backend/api/schemas/task.py` — `CommentBackfillGroupRequest` 新增 `concurrency` 字段
- `backend/api/services/task_manager.py` — `create_task()` 存储 concurrency 到 task dict
- `backend/api/routers/comment_backfill_group.py` — 透传 `concurrency` 到 create_task
- `backend/api/services/crawl_service.py` — 多账号分配 + 多组 aux 浏览器获取/Cookie 注入/释放
- `backend/crawler/account_dispatcher.py` — 新增 `assign_multiple_accounts` / `release_multiple_accounts` 方法
- `backend/crawler/comment_backfill_runner.py` — 新增 `worker_resources` 参数，路由到 ParallelBackfillCoordinator
- `frontend/.../CommentBackfillGroupDialog.tsx` — 并发数选择器 UI（1-5 按钮组）
- `frontend/src/services/api/index.ts` — API 传参新增 concurrency
- `docs/api.md` — POST /api/v1/comment-backfill/group 接口文档更新

---

## [2026-04-05] 修复任务组断点续跑报错 source_task_ids 为空

### 根因
任务组（comment_backfill_group）恢复执行时，`run_comment_backfill_group_task` 的逻辑是：
**先校验 `source_task_ids` → 再检查已有 tweets**。
对于断点续跑的旧任务（DB 中 `source_task_ids_json` 为默认空值 `'[]'`），校验直接失败抛错，
尽管任务已有 46817 条 tweets 可以直接续跑，根本不需要重新合并源任务。

### 修复

**`comment_backfill_runner.py`** — 调换检查顺序：
1. 先尝试从任务已有数据加载 tweets（断点续跑路径，**不需要** `source_task_ids`）
2. 仅当无已有 tweets 时（首次执行），才校验 `source_task_ids` 并从源任务合并
3. 增加断点续跑时的 INFO 日志，明确标识跳过了合并

**`crawl_service.py`**
- `run_search_task`: 直接透传 `source_task_ids` 给 runner（不再强制转空列表）
- `start_crawler_thread`: 新增任务组调度诊断日志

## [2026-04-05] 修复 comment_backfill_group source_task_ids 传递链路

### 问题
任务组（comment_backfill_group）在执行时报错 "任务组没有配置源任务 ID（source_task_ids 为空）"。
虽然 DB 层已补充了 `source_task_ids_json` 列（上一轮修复），但调度链路中 `source_task_ids` 仍存在丢失风险：
1. Python 的 `or` 运算符对空列表 `[]`（falsy）的处理导致 fallback 路径异常
2. runner 的 fallback 逻辑没有同时尝试 task dict（DB 加载值）兜底
3. `run_search_task` 将 `source_task_ids or []` 传给 runner，空列表直接触发报错而不尝试 DB 回源

### 修复

**`comment_backfill_runner.py`**
- 改用 `if source_task_ids` 替代 `source_task_ids or`，外部传入为空/None 时回退到 `task.get("source_task_ids")`（来自 DB）
- 增加 ERROR 级别诊断日志：同时打印外部传入值和 task dict 中的值，方便定位根因

**`crawl_service.py`**
- `run_search_task`: 不再用 `source_task_ids or []` 强制空列表，直接透传给 runner，让 runner 自己 fallback
- `start_crawler_thread`: 新增任务组调度诊断日志，打印 task.source_task_ids 和 payload.source_task_ids

## [2026-04-05] 修复 comment_backfill_group source_task_ids 丢失

### 根因
`source_task_ids`（任务组的源任务列表）从未被写入 SQLite DB（`task_db.py` 缺少对应列），也未在任务加载时反序列化。服务重启后从 DB 重载任务时，该字段缺失，`run_comment_backfill_group_task` 读到空列表就抛出 "source_task_ids 为空" 错误。

### 修复

**`task_db.py`（DB 层）**
- `_ensure_column` — 补充 `source_task_ids_json TEXT DEFAULT '[]'` 列（自动迁移旧 DB）
- `_summary_params` — 将 `source_task_ids` 序列化为 JSON 字符串持久化
- `_upsert_task_summary` INSERT / ON CONFLICT UPDATE — 加入 `source_task_ids_json`
- `load_all_tasks` SELECT + 反序列化 — 读取并解析 `source_task_ids_json` → `source_task_ids`

**`task_manager.py`（内存加载）**
- `_ensure_db` — 补充 `task.setdefault("source_task_ids", [])` 对历史任务兼容

**`comment_backfill_runner.py`（执行层兜底）**
- `run_comment_backfill_group_task` 新增 `source_task_ids: Optional[list[str]] = None` 参数
- 优先使用外部直传值（来自 scheduler payload，100% 可靠），再 fallback 到任务 dict

**`crawl_service.py`（调用层）**
- `run_search_task` 的 `comment_backfill_group` 分支：显式传 `source_task_ids=source_task_ids`

## [2026-04-05] 错误页账号切换修复 + 任务组 UI 优化

### 修复

#### 全页 "Something went wrong" 不再阻断评论补采
- **问题**：`navigate_with_retry` 遇到全页 `TRANSIENT_ERROR`（即 X 显示"Something went wrong. Try reloading."）时，内部重试（Retry 按钮点击 + 刷新）全部失败后只是 `return False`，`fetch_replies` 收到后直接放弃本帖并记录失败，**从未尝试切换账号**。
- **修复**（`reply_fetcher.py`）：初始导航 `navigate_with_retry` 返回 `False` 后，在放弃之前先调用 `_try_inject_pool_account_cookies` 尝试从号池轮换到下一个账号（最多切换 `_REPLY_MAX_ACCOUNT_SWITCHES` 次），切换成功后重新导航（`max_retries=2`）；仍失败才最终跳过。
- **效果**：单账号遇到错误页时，系统自动轮换到号池中下一个账号继续采集，不因账号临时异常丢失进度。

### 优化

#### 评论补采任务组对话框
- **去掉"最大评论数"配置项**：该参数用户无需控制（始终不限制），从 UI 中移除；API 调用固定传 `max_replies_per_tweet=0`。
- **源任务进度标注**（新增"已采 / 待采"明细 + 进度条）：
  - 有 `comment_backfill_progress` 数据的任务显示：绿色"已采 N 条"、粗体"待采 M 条"或"已全部采集"、小字"共 T 条"
  - 每行附带细进度条（已采比例 → 紫色；全部采完 → 绿色）
  - 已全部采集的任务：`opacity-50` 淡化 + 绿色勾图标，一眼识别"不会再补采"

## [2026-04-05] 评论补采任务组：L1/L2 完全解耦 + 多任务合并高效爬取

### 背景
评论补采任务中，二级评论（L2）的爬取与一级评论（L1）争抢同一个 Chrome 进程，导致 CDP 命令串行化，L1 被 L2 严重拖慢、进度迟迟不更新。此外，多个独立的 `comment_backfill` 任务各自持有一批帖子，浏览器槽位分散，整体吞吐远低于理论值。

### 新功能

#### 评论补采任务组（`comment_backfill_group`）
- **后端** `comment_backfill_group_service.py`（新文件）— 加载多个源任务的待补采帖子，全局去重（by `tweet_id`），按评论数降序排列
- **后端** `comment_backfill_group.py`（新路由）— `POST /api/v1/comment-backfill/group`，将多个 `comment_backfill` 任务合并为一个 `comment_backfill_group` 大任务并立即启动
- **后端** `comment_backfill_runner.py` — 新增 `run_comment_backfill_group_task()`，使用 `reply_worker_count=3` 最大化 L1 并行度
- **后端** `crawl_service.py` — 为 `comment_backfill_group` 任务额外申请独立 `nested_browser_instance`（L2 专用 aux 进程）
- **前端** `CommentBackfillGroupDialog.tsx`（新组件）— 展示源任务列表、剩余帖数、配置采集深度和最大评论数、生成任务组
- **前端** `TaskBatchActions.tsx` — 新增"合并为任务组"按钮（紫色风格），仅在选中 ≥2 个 `comment_backfill` 任务时可点击
- **前端** `tasks/page.tsx` — 接线 `CommentBackfillGroupDialog`，创建成功后自动跳转至新任务组详情页

#### L1/L2 浏览器完全解耦（惠及所有深度>1的评论补采任务）
- **`pipeline.py`** — 新增 `nested_browser_instance` 参数；`_nested_worker` 优先使用专属 L2 浏览器实例，与 L1 `reply_worker` 完全隔离
- **`pipeline.py`** — `on_reply_done` 回调在 L1 阶段完成后**立即触发**（不再等待 L2 完成），前端进度实时可见；L2 完成后再次触发以更新完整 replies 数据
- **`crawl_service.py`** — 对所有 X 平台深度>1 的 `comment_backfill` 任务自动申请 `nested_reply` aux 浏览器槽位

### schema 变更
- `task.py` — `TaskKind` 新增 `"comment_backfill_group"`；`TaskOut` 新增 `source_task_ids?: list[str]`
- `task.py` — 新增 `CommentBackfillGroupRequest`、`CommentBackfillGroupResponse`、`CommentBackfillGroupSourceSummary`
- `api/index.ts` — 对应前端类型同步更新；`commentBackfill.createGroup()` 方法

### 效果
- 任务组模式下 L1 × 3 worker + 独立 L2 专用浏览器，理论峰值吞吐是原单任务的 2-3 倍
- 多个 `comment_backfill` 任务合并后全局去重，同一帖子不再被重复补采

## [2026-04-05] 浏览器实例严格控制 + 并发爬取效率全面优化

### 问题
1. **浏览器实例数失控**：5 个并发任务却开了 10+ 个 Chrome 进程。原因：跨平台并发开启时浏览器池大小翻倍（5×2=10），且每个需要抓评论的任务还会额外创建辅助浏览器进程
2. **恢复任务卡顿**：暂停恢复后 check_signal 轮询间隔 1s，调度器 dispatch loop 空闲等待 0.5s，恢复延迟明显
3. **爬取效率低下**：单账号翻页间隔 15-26s，加上模拟阅读、微休息、小憩、长休息等额外等待，实际吞吐很低

### 修复

#### 浏览器池大小严格等于并发任务数
- `browser_pool.py` — `compute_pool_max_size()` 不再因跨平台并发翻倍，pool 主 slot 数 = `crawler_max_concurrent_tasks`
- **效果**：5 个并发任务 = 5 个主浏览器 slot（需抓评论时会按需创建 aux 辅助实例）

#### 恢复任务立即开始
- `utils.py` — check_signal 暂停轮询间隔从 1.0s 降到 0.3s，恢复信号最快 300ms 内响应
- `task_scheduler.py` — dispatch loop 空闲等待从 0.5s 降到 0.2s，空转间隔从 0.1s 降到 0.05s
- **效果**：恢复后 ~0.3s 内开始爬取，体感几乎无延迟

#### 并发模式全速爬取
- `account_pool.py` — 动态翻页间隔区间缩短（0.55x~0.85x safe_interval），单账号约 8-12s，多账号约 2-4s
- `x_searcher.py` — 并发模式（pool_mode）下完全跳过模拟阅读和休息节律
- `x_searcher.py` — 单任务模式下休息节律也大幅缩减：微休息 1%/1-2s、小憩 2000条/5-10s、长休息 6h/30-60s
- **效果**：并发爬取吞吐提升约 3-5 倍

#### 测试更新
- `test_browser_pool.py` — 更新池大小计算和 pool_mode 启用判断的测试
- `test_crawl_service_comment_backfill.py` — 验证评论补采任务正确申请 aux 辅助浏览器实例
- `test_crawler_config_and_recovery_policy.py` — 更新 mock 函数签名

## [2026-04-05] 修复浏览器实例误判"卡死/断连" + 评论补采跳过首页导航

### 问题
1. **浏览器实例被误判为卡死/断连**：Round 1 优化中将搜索和回复共用同一 Chrome 进程（删除 aux 辅助实例），导致 CDP 命令串行化——多 tab 共享一个 WebSocket 连接，并发 CDP 调用互相阻塞，引发 `tab.cookies()` 超时、`Page.reload` 超时、导航超时等连锁问题。实际浏览器进程完全正常，但 CDP 层面已无法正常通信。
2. **评论补采任务卡在"准备中"**：`comment_backfill` 任务启动流程缺少中间阶段提示，用户只看到"正在准备 X 评论补采任务..."长时间不变。
3. **不必要的首页导航**：回复/评论 tab 在浏览器池模式下仍走完整的登录验证流程（导航到 x.com/home），浪费 5-15 秒。

### 修复

#### 恢复独立 aux 辅助浏览器实例（修复 CDP 串行化）
- `crawl_service.py` — 搜索和回复/评论恢复使用独立 Chrome 进程（`pool.acquire_aux()`），彻底消除 CDP 命令串行化
- `browser_pool.py` — `BrowserInstance.is_alive` 改用 `psutil.pid_exists()` 优先检测进程是否存活，避免 CDP 繁忙时误判为断连
- **效果**：搜索和回复各自独立运行，不再相互阻塞

#### 评论补采中间阶段提示
- `comment_backfill_runner.py` — pipeline 启动前添加"正在启动评论抓取引擎（共 N 条帖子待处理）..."阶段提示
- `pipeline.py` — reply worker 进入主循环后更新"浏览器就绪，开始抓取评论..."

#### 浏览器池模式跳过首页导航
- `reply_fetcher.py` — `_ensure_reply_session_ready()` 在池模式下直接注入浏览器实例 Cookie 并标记登录缓存，跳过 `ensure_x_domain_context()` 首页导航
- `auth.py` — 全链路 `time.sleep()` 从 ~3.5s 缩减到 ~1.2s：`ensure_x_domain_context` 0.5→0.2s，`ensure_login_detailed` 0.5→0.2s/1.0→0.3s，`_refresh_x_home` 已在 x.com 域时改用 `tab.refresh()` 代替全量导航

### 验证
- `pytest tests/test_browser_pool.py tests/test_crawl_service_comment_backfill.py tests/test_crawler_config_and_recovery_policy.py tests/test_comment_backfill_runner.py -v`
- 结果：`21 passed`

## [2026-04-05] 修复 X/微博评论抓取阶段浏览器卡死放大

### 问题
1. **评论补采浏览器复用策略过于激进**：`comment_backfill` 任务不再申请 `aux` 评论浏览器实例后，X 评论补采内部多个 worker、登录校验、页面恢复逻辑被压到同一个 Chromium 实例，导致 `Page.stopLoading` / `Page.reload` / `Network.getCookies` 连锁超时
2. **Cookie 超时误判为登录丢失**：`tab.cookies()` 超时时旧逻辑直接返回空 Cookie，随后触发更多登录恢复、页面跳转与刷新，进一步放大浏览器阻塞
3. **微博评论页打开超时直接失败**：微博评论详情页 `tab.get()` 超时会直接冒泡，使整条评论补采记录为 0 条

### 修复

#### `backend/api/services/crawl_service.py`
- 浏览器池模式下，`comment_backfill` 任务重新申请独立 `aux` 评论浏览器实例
- 微博评论补采优先使用 `aux` 实例执行实际抓取，降低与共享 slot 的互相影响

#### `backend/crawler/comment_backfill_runner.py`
- X 评论补采固定为单 `reply_worker` 稳定模式，避免同一 Chromium 进程内堆叠多个一级评论 worker

#### `backend/crawler/auth.py`
- 新增短期 Cookie 缓存
- `Network.getCookies` 超时时优先回退最近缓存，避免把浏览器忙死误判成登录丢失

#### `backend/crawler/weibo/comment_fetcher.py`
- 评论详情页打开流程改为返回明确失败原因：`navigation_timeout` 或 `http_418_cooldown_exhausted`
- `tab.get()` 超时不再直接炸穿整条微博评论补采

#### 测试
- 新增/更新：
  - `backend/tests/test_crawl_service_comment_backfill.py`
  - `backend/tests/test_comment_backfill_runner.py`
  - `backend/tests/test_auth_cookie_cache.py`
  - `backend/tests/test_weibo_comment_fetcher.py`

### 验证
- `backend/.venv/bin/python -m py_compile backend/api/services/crawl_service.py backend/crawler/comment_backfill_runner.py backend/crawler/auth.py backend/crawler/weibo/comment_fetcher.py backend/tests/test_crawl_service_comment_backfill.py backend/tests/test_comment_backfill_runner.py backend/tests/test_auth_cookie_cache.py backend/tests/test_weibo_comment_fetcher.py`
- `PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/test_crawl_service_comment_backfill.py backend/tests/test_comment_backfill_runner.py backend/tests/test_auth_cookie_cache.py backend/tests/test_reply_session_sync.py backend/tests/test_weibo_comment_fetcher.py`
- 结果：`15 passed`

## [2026-04-05] 修复评论补采任务卡在"准备中" + 批量导出性能和体验优化

### 问题
1. **评论补采任务永远显示"准备中"**：Watchdog 将 `pending` 状态（排队等待调度）的评论补采任务误判为"僵死"任务，15分钟后自动 stop 再重新入队，形成无限的停止-重启循环
2. **评论补采任务被搜索任务无条件压低优先级**：调度器排序逻辑让搜索任务永远排在评论补采前面，即使没有搜索任务在运行，评论补采仍被饿死
3. **批量导出慢**：后端 async 处理函数内做大量同步阻塞操作（SQLite 读取、JSON 反序列化、deepcopy、CSV/Excel 构建），阻塞 FastAPI 事件循环；批量任务串行加载
4. **批量导出用户体验差**：无进度指示、无数据量预估、导出中无法取消

### 修复

#### `backend/api/services/task_watchdog.py`
- `_is_stale_comment_backfill()` 不再将 `pending` 状态纳入 stale 检测，仅检查 `running` 状态——排队中的任务没有运行线程，不应被判为僵死

#### `backend/api/services/task_scheduler.py`
- `_try_dispatch_pending()` 改为条件优先级排序：只有队列中同时存在搜索任务时，搜索才优先；纯评论补采队列中任务平等调度

#### `backend/api/services/task_manager.py`
- 新增 `get_task_export_payload_readonly()` 方法：导出专用只读接口，不做 `copy.deepcopy()`，大幅降低内存开销
- 新增 `get_export_estimate()` 方法：返回导出预估信息（行数、推文数、评论数、预估文件大小）

#### `backend/api/routers/export.py`
- CSV/Excel 导出路由使用 `asyncio.run_in_executor()` 将同步阻塞操作移入线程池，不再阻塞事件循环
- 使用只读加载接口减少内存拷贝

#### `backend/api/routers/batch_export.py`
- 批量导出使用 `ThreadPoolExecutor` 并行加载多个任务数据（最多 4 并发），替代串行循环
- CSV/Excel 构建使用独立线程池 `_export_pool`，通过 `run_in_executor` 异步执行
- 新增 `POST /api/v1/export/batch/estimate` 预估接口
- 使用只读加载接口

#### `frontend/src/services/api/index.ts`
- 新增 `ExportEstimateResponse` 类型和 `batchEstimate()` API 方法
- `downloadPostBlob()` 支持 `AbortSignal` 取消和 `onProgress` 进度回调（基于 ReadableStream）
- `batchDownloadCsv()` / `batchDownloadExcel()` 增加可选的 `options` 参数传递取消和进度

#### `frontend/src/components/features/tasks/BatchExportDialog.tsx`
- 对话框打开时自动调用预估 API，展示数据量（推文数、评论数、总行数、预估文件大小）
- 导出中显示进度条（有 Content-Length 时显示百分比，否则显示已下载字节数）
- 支持取消导出（基于 AbortController）
- 导出中禁用格式选择，防止误操作

#### `docs/api.md`
- 补充 `POST /api/v1/export/batch/estimate` 接口文档

## [2026-04-04] 修复 X/微博评论卡住、翻页空转、watchdog 反复重排等问题

### 问题
1. **X 评论翻页空转**：当评论区数据达到 API 返回上限后，继续翻页拿到的全是重复数据（新增 0 条），但爬虫要等连续 3-12 页空数据才放弃，浪费大量时间
2. **X 翻页硬恢复丢失 cursor**：`_wait_reply_packet_with_recovery` 在第 2 页及之后的翻页数据包超时时，执行硬恢复（重新导航到推文 URL），导致丢失翻页 cursor，回到第 1 页数据（全重复），进一步延长空转
3. **watchdog 反复重排不恢复**：评论补采任务 pending + 线程死亡后，watchdog 每 15 分钟检测到 stale → stop → resume_queue，但新调度的任务 `last_event_at` 仍是很久以前的创建时间，导致下一轮又被判定为 stale，形成无限循环
4. **任务线程崩溃不释放调度槽**：浏览器池获取、账号分配等初始化异常在 `try` 块之外抛出，导致 `scheduler.mark_done()` 和 `task_queue_manager.notify_task_terminal()` 永远不会被调用，调度槽永久占用

### 修复

#### `backend/crawler/reply_fetcher.py`
- 已有数据时将连续空页退出阈值从 `max_empty_pages`(3-12) 降低为 2：如果已经抓到至少 1 条评论，连续 2 页无新数据就立即停止翻页
- 翻页场景（`page_num > 1`）跳过硬恢复：避免重新导航丢失 cursor 带来的全重复数据空转

#### `backend/api/services/task_watchdog.py`
- 新增 `_touch_queue_pending_tasks()`：watchdog 重排任务时，同步刷新队列内所有 pending/running 任务的 `last_event_at`，防止下一个检查周期误判

#### `backend/api/services/crawl_service.py`
- 将浏览器池获取 (`pool.acquire`) 和账号分配 (`LoginRequiredPause`) 代码移入 `try` 块内，确保任何异常都能触发 `finally` 中的 `scheduler.mark_done()` 和资源清理

#### `backend/api/services/task_scheduler.py`
- `_cleanup_dead_threads()` 添加调试日志，便于追踪线程异常死亡

## [2026-04-04] 导出已有任务检索词并按平台分类

### 改动

#### `docs/task_keywords_export_2026-04-04.md`
- 新增导出说明文档，记录数据来源、统计口径、平台分类结果和输出文件路径

#### `docs/exports/task_keywords_by_platform_all_tasks.csv`
- 导出当前任务库中全部任务的检索词
- 按 `platform` 分类，并按 `(platform, keyword)` 去重
- 保留每个检索词对应的任务数、首次创建时间和最后创建时间

#### `docs/exports/task_keywords_by_platform_search_tasks.csv`
- 导出仅 `task_kind='search'` 的主搜索任务检索词
- 便于与评论补采类关键词分离复用

### 结果
- 使用的有效任务库：`backend/tasks.db`
- 全部任务数：67
- 平台分布：`weibo=27`，`x=40`
- 全部任务去重后关键词数：`weibo=22`，`x=40`
- 仅主搜索任务去重后关键词数：`weibo=17`，`x=21`

## [2026-04-04] 修复评论补采任务假运行占槽导致队列卡死

### 问题
X 评论补采队列中存在一种“假运行”状态：任务仍显示为 `running`，但 `last_event_at` 长时间不再更新，界面停在“正在准备 X 评论补采任务...”，同时继续占用调度并发槽，导致同队列后续补采任务一直不动。

### 改动

#### `backend/api/services/task_watchdog.py`
- 新增活跃任务 watchdog，专门巡检 `comment_backfill` 任务
- 当任务处于 `running/pending` 且长时间无事件时，自动执行：
  - 发送 `stop` 信号
  - 释放线程登记与调度器运行槽
  - 将任务标记为 `stopped`
  - 自动重新加入调度队列

#### `backend/api/services/task_manager.py`
- 在任务列表、任务摘要、任务详情读取前触发轻量 watchdog 巡检
- 避免用户已在刷新页面，但卡死任务始终无人处理

#### `backend/config.py`
- 新增配置：
  - `crawler_active_task_watchdog_enabled`
  - `crawler_active_task_stale_timeout_sec`
  - `crawler_active_task_watchdog_interval_sec`

#### `backend/api/routers/crawler_config.py`
- 将上述配置纳入 `/api/v1/crawler-config` 的读写与持久化

#### `frontend/src/components/features/settings/CrawlerConfigCard.tsx`
- 设置页新增“任务卡死巡检”开关
- 新增“卡死判定阈值”“卡死巡检间隔”两个可调参数

#### `docs/api.md`
- 补充评论补采卡死自愈相关配置字段说明

## [2026-04-04] 修复评论区卡住不切换 + 提升爬取效率

### 问题
1. **评论区卡住不切换**：当推文评论区已加载完毕（无更多数据）或遇到"显示可能的垃圾信息"边界时，爬虫卡在当前推文上无法切换，长达 60-90 秒。根本原因：
   - `bottom_cursor=None` 时会继续触发额外滚动并等待数据包，但 X 不再发包，每次等包超时需 27s+
   - 硬重试会重新导航到推文页，再加 30s+
   - `ShowMoreThreads` cursor 通过 entryId 兜底检测有漏网情况
2. **整体效率低**：每次等包的 compensation_probe_timeout 设置过长（最大 12s），软重试次数过多

### 改动

#### `backend/crawler/wait_policy.py`
- `quick_probe_timeout`：上限从 3s 降至 2s，系数从 0.2 降至 0.12
- `compensation_probe_timeout`：上限从 12s 降至 8s，系数从 0.65 降至 0.4
- 单次等包总超时从约 27s 降至约 18s（-33%）

#### `backend/crawler/reply_fetcher.py`
- `_wait_reply_packet_with_recovery`：
  - 硬重试次数从 `min(2, policy)` 降至 `min(1, policy)`，避免不必要重新导航
  - 软重试循环中：当页面状态正常（PageState.OK）且连续 2 次无包时，立即退出软重试（不再继续等待），显著减少评论区到底时的等待时间
- `fetch_replies`：
  - `bottom_cursor=None` 时**立即 break**，不再尝试额外滚动（之前会多等 1-2 个 compensation timeout）
  - `packet=None` 时简化为直接 break，去掉冗余的"额外滚动后再等包"逻辑

#### `backend/crawler/reply_parser.py`
- `parse_tweet_detail_response`：新增通过 `entryId` 检测 `ShowMoreThreads`（兜底），防止 X API 结构变化导致垃圾信息边界漏检

---

## [2026-04-04] 评论区"出错了。请尝试重新加载。"自动重试并换账号

### 问题
X 评论区偶发局部加载错误（显示"出错了。请尝试重新加载。"和"重试"按钮），此时整页框架正常，`detect_page_state` 返回 OK，爬虫无法感知该错误，导致在等待数据包超时后才进入重试流程，效率低且无法换账号。

### 改动

#### `backend/crawler/page_state.py`
- `_RETRY_PAGE_MARKERS` 新增"请尝试重新加载"中文标记
- 新增 `detect_reply_area_error(tab)` 函数：检测评论区局部加载错误（区别于整页错误）
- 新增 `click_reply_retry_button(tab)` 函数：专门点击评论区"重试"按钮（含 CSS 选择器 + 文字匹配兜底）

#### `backend/crawler/reply_fetcher.py`
- 导入 `detect_reply_area_error`、`click_reply_retry_button`、`SplashTimeoutSignal`
- `_wait_reply_packet_with_recovery` 新增参数 `on_reply_area_error_switch_account`（可选换账号回调）
- 软恢复阶段（每次数据包超时后）新增流程：
  1. 调用 `detect_reply_area_error` 检测评论区局部错误
  2. 若检测到，调用 `click_reply_retry_button` 点击"重试"后等待数据包
  3. 连续点击达到阈值（3 次）时抛出 `SplashTimeoutSignal`
- `fetch_replies` 新增换账号计数器（上限 2 次）
- 主循环捕获 `SplashTimeoutSignal`：调用 `_try_inject_pool_account_cookies` 注入下一个账号 Cookie，成功后重新导航并继续采集；无可用备用账号时放弃本推文评论

---

## [2026-04-04] 爬虫遭遇 X 黑屏启动画面时自动刷新并切换账号

### 问题
X/Twitter 页面有时会出现黑屏+X logo 的启动画面（splash screen），即 SPA 框架已加载但内容尚未渲染。原有逻辑无法识别此状态，导致爬虫卡在黑屏页面上无法继续，也不会尝试切换账号。

### 改动

#### `backend/crawler/crawl_signals.py`
- 新增 `SplashTimeoutSignal`：X 黑屏状态持续超过阈值时抛出，向上传递换账号信号

#### `backend/crawler/page_state.py`
- `PageState` 枚举新增 `SPLASH = "splash"` 状态
- 新增 `_is_splash_loading()` 函数：检测页面是否为黑屏启动状态（JS 已执行但 SPA 未渲染）
  - 特征：可见文本极少（≤200字符）、不是 noscript 空壳页、URL 是 x.com、HTML 含 `react-root` 挂载点
- `detect_page_state()` 在现有检测链末尾追加 splash 检测

#### `backend/crawler/page_health.py`
- 引入 `SplashTimeoutSignal`
- `navigate_with_retry()` 新增 `splash_hits` 计数器
- 检测到 `PageState.SPLASH` 时的处理流程：
  1. 先等待（5s→10s→15s 递增），给 SPA 更多时间加载
  2. 等待后重检，若恢复正常则继续
  3. 等待无效则执行刷新再检测
  4. 若 `splash_hits` 达到阈值（默认 3 次，由配置 `crawler_splash_switch_threshold` 控制）则抛出 `SplashTimeoutSignal`

#### `backend/crawler/x_searcher.py`
- 导入 `SplashTimeoutSignal`
- 初始导航时（第4步）：捕获 `SplashTimeoutSignal`，调用 `_try_rotate_account()` 切换账号，切换成功后重新导航
- 主采集循环（while True）：捕获 `SplashTimeoutSignal`，切换账号后重启监听并重新导航搜索页继续采集；无可用备用账号时记录警告并继续等待

---

## [2026-04-03] 修复 BrowserPool 实例启动时恢复历史标签页的问题

### 问题
微博（及 X）爬虫并发运行时，浏览器实例（BrowserPool）启动后会显示大量历史标签页。根本原因：
1. `_reset_profile_dir` 在 profile 目录无法完全清除时（有锁定文件），Chrome 会读到旧的 Session 文件，自动恢复上次崩溃/异常退出时的所有标签页
2. `~/.xcrawl-browser-instances/` 下积累了 80+ 个历次服务启动遗留的 worker profile 目录，每次新服务启动时旧 profile 仍然存在

### 改动

#### `backend/crawler/browser_pool.py`
- `_create_browser` 新增启动参数 `--no-restore-last-session`、`--disable-session-crashed-bubble`，彻底阻止 Chrome 恢复历史会话
- 新增 `_clear_session_files()` 方法：在 profile 无法完全清除时，主动删除 `Default/Last Session`、`Last Tabs`、`Current Session`、`Current Tabs`、`Session Storage` 等会话文件
- `_reset_profile_dir` profile 部分清理后调用 `_clear_session_files`；`os.makedirs` 之后也再次调用，确保新建目录不残留旧会话
- 新增 `_cleanup_stale_worker_dirs()`：BrowserPool 初始化时清理 `~/.xcrawl-browser-instances/` 下非当前进程的所有旧 worker 目录
- `get_browser_pool()` 初始化时调用 `_cleanup_stale_worker_dirs()`

---

## [2026-04-03] 评论补采任务调度按推文数量降序排列

### 需求
多个评论补采任务同时存在（或恢复）时，应优先执行推文数量多的任务，这样能更早采集到大量评论，整体效率更高。

### 改动

#### `backend/api/services/task_scheduler.py`
- `ScheduledTask` 新增 `result_count: int = 0` 字段
- `enqueue()` 方法新增 `result_count` 参数，存入 `ScheduledTask`
- `_try_dispatch_pending()` 排序 key 从单维（task_kind）改为双维：主键 task_kind（search 优先），次键 `-result_count`（同为 comment_backfill 时推文多的先调度）

#### `backend/api/services/task_queue_manager.py`
- `_sort_task_ids_by_priority()` 同样升级为双维排序：task_kind 主键 + result_count 降序次键
- `resume_queue()` 内联排序代码改为复用 `_sort_task_ids_by_priority()`，消除重复逻辑

#### `backend/api/services/crawl_service.py`
- `start_crawler_thread()` 调用 `scheduler.enqueue()` 时传入 `result_count=task.get("result_count")`

---

## [2026-04-03] 修复评论区到底时继续等待的问题

### 问题
当评论区加载到底部、没有更多评论时（图片中空白情况），API 返回的包里 `bottom_cursor` 为空、`new_replies` 也为空。之前的代码会继续执行滚动，进入下一轮 `_wait_reply_packet_with_recovery`，等待直到超时（最长约 15 秒），才能放弃。如果评论区只有少量评论且覆盖率不足 50%，这个无效等待还可能重复多次。

### 改动

**`backend/crawler/reply_fetcher.py`**：  
修改 `not bottom_cursor` 分支的判断条件：
- **之前**：覆盖率不足 50% 时一律继续滚动重试
- **之后**：仅当本页实际有新数据（`new_replies > 0`）但没有 cursor 时才继续滚动；本页没有新数据且无 cursor，说明评论区真的到底了，**立即停止**，不再触发下一轮超时等待

---

## [2026-04-03] 修复一级评论第一页无效等待问题

### 问题
`fetch_replies` 导航到推文详情页后，直接进入 while 循环调用 `_wait_reply_packet_with_recovery` 等待数据包，**没有先主动滚动**。X 评论区的 TweetDetail API 完全由滚动触发——不滚动就不会发出网络请求，导致 `quick_probe_timeout`（最长3秒）白白空等，然后才触发补偿滚动。

### 改动

**`backend/crawler/reply_fetcher.py`**：
- `navigate_with_retry` 的 `post_load_wait` 从 `0.3` 改为 `0.0`（滚动本身就能触发加载，无需额外等待）
- 导航成功后、进入 while 循环之前，立即调用一次 `_scroll_incremental()`，主动触发第一批评论数据包
- 这样第1页与后续翻页行为一致：先滚动→再等包，消除无效等待

---

## [2026-04-03] 评论补采任务改用 CrawlPipeline，一/二级评论并行抓取

### 问题
X 评论补采任务（`comment_backfill`）调用 `fetch_replies_batch`，每条推文按串行顺序处理：一级评论抓完后立即在同一线程内等待二级评论全部抓完，才进入下一条推文的一级评论。即：
```
tweet1一级 → tweet1二级 → tweet2一级 → tweet2二级 → ...（完全串行）
```
而主搜索流程已通过 `CrawlPipeline` 实现了一级/二级解耦并行，补采任务却未使用这个已有机制。

### 改动

#### 1. `backend/api/services/crawl_service.py`
- 调整 aux 浏览器分配条件：`comment_backfill` 任务在 pool 模式下也分配独立的 `_reply_browser_instance`（供 pipeline nested_worker 使用）
- 调用 `run_comment_backfill_task` 时新增传入 `reply_browser_instance=_reply_browser_instance`

#### 2. `backend/crawler/comment_backfill_runner.py`
- `run_comment_backfill_task` 和 `_run_x_comment_backfill` 新增 `reply_browser_instance=None` 参数
- `_run_x_comment_backfill` 核心逻辑从 `fetch_replies_batch` 改为 `CrawlPipeline`：
  - `reply_worker` 独立线程只抓一级评论，完成即推入 `nested_queue`
  - `nested_worker` 独立线程消费二级评论，与 `reply_worker` 真正并行
  - `on_reply_done` 回调语义与原 `_on_progress` 完全一致（二级全部完成后触发）
  - 通过 `pipeline.check_error()` 正确透传 `StopSignal` / `ChallengeSignal`

#### 3. `backend/tests/test_crawl_service_comment_backfill.py`
- 重命名并更新测试：补采任务现在**应该**申请 aux 浏览器，断言调整为验证 `reply_browser_instance` 被正确传入

---

## [2026-04-03] 评论爬虫识别"显示可能的垃圾信息"边界，提前停止翻页

### 问题
X 评论区一级评论列表末尾会出现 `ShowMoreThreads` 类型的 cursor，对应 UI 上的 **"Show probable spam"（显示可能的垃圾信息）** 按钮。出现该按钮说明所有正常评论已加载完毕，后面仅剩垃圾/疑似垃圾内容。之前爬虫无法识别这个信号，会继续滚动触发翻页、等待下一批数据包，造成不必要的等待和网络请求。

### 改动

#### 1. `backend/crawler/reply_parser.py`
- `parse_tweet_detail_response` 返回值新增第五项 `has_spam_boundary: bool`
- 解析 entries 时检测 `cursorType == "ShowMoreThreads"` 的 cursor，标记 `has_spam_boundary = True`
- 日志中会记录检测到垃圾信息边界的 debug 信息

#### 2. `backend/crawler/reply_fetcher.py`
- `fetch_replies` 解包 `parse_tweet_detail_response` 返回的新字段 `has_spam_boundary`
- 每页解析后，若 `has_spam_boundary` 为 True，立即停止翻页并记录 telemetry 事件 `reply_spam_boundary`
- 检测时机在空页计数更新之后、快速退出逻辑之前，确保当前页有效评论已被收集

---

## [2026-04-03] 修复微博 tab 泄漏 + X 评论翻页等待过慢

### 问题

1. **微博爬虫持续新开 tab 页，浏览器中 tab 越来越多**：`searcher.py` 在 Tab 崩溃/超时后调用 `_rebuild_weibo_tab()` 重建 tab，但原来的旧 tab 没有关闭，导致每次崩溃后都泄漏一个 tab，时间一长浏览器里积累大量残留 tab 页。
2. **X 一级评论翻页后等待很久才收到下一页数据包**：`_wait_reply_packet_with_recovery` 在快速探测超时后，软重试循环中调用的 `soft_recover_for_packet` 只做了小步 `scroll.down(280)`，不足以触发 X 评论区懒加载。真正触发下一批评论加载需要完整的渐进式滚动（多步 + scroll_to_bottom），因此软重试阶段白白等待 `compensation_probe_timeout` × N 次（累积可达 30+ 秒）才进入硬刷新，而硬刷新后反而正常拿到数据。

### 改动

#### 1. 修复微博 tab 泄漏
- **`backend/crawler/weibo/searcher.py`**：重建 tab 前先调用 `tab.close()` 关闭旧 tab，覆盖三处泄漏点：
  - Tab 崩溃/断开连接重试时
  - HTTP 418 冷却后重建时
  - 最终失败后连接断开时的兜底重建

#### 2. 加速 X 评论翻页等待
- **`backend/crawler/reply_fetcher.py`**：重写 `_wait_reply_packet_with_recovery` 软重试逻辑：移除 `soft_recover_for_packet` 小步滚动，改为每次快探超时后立即调用 `_scroll_incremental()`（完整渐进式滚动 + scroll_to_bottom），再等 `compensation_probe_timeout`。这样滚动能有效触发 X 评论懒加载，绝大多数情况下第一次补滚动即可拿到包，避免多轮无效等待。同时移除对 `soft_recover_for_packet` 的导入（已不再使用）。

---

## [2026-04-02] 爬虫性能优化：调度优先级修复 + 回复抓取效率提升

### 问题
1. `create_queue` 创建任务队列时不做优先级排序，评论补采任务可能先于普通搜索任务被调度执行
2. 调度器 `_pending_items` 暂缓队列无优先级排序，槽位释放后评论补采任务可能先于普通搜索任务被分发
3. 每条推文回复抓取都重新验证登录 + 导航 x.com/home，大量浪费时间（日志中 3000 行出现 53 次域切换）
4. 回复翻页硬恢复最多 3 次、退避 cap=35s，单次触发浪费 50-75 秒
5. 大评论量推文（如 3912 条）与小评论量推文使用相同的"连续空页退出阈值=3"，导致覆盖率仅 9%

### 改动

#### 1. `create_queue` 添加任务优先级排序
- **`backend/api/services/task_queue_manager.py`**：新增 `_sort_task_ids_by_priority()` 函数，`create_queue()` 在提交任务给调度器前先排序，普通搜索任务优先于评论补采任务入队。与 `resume_queue()` 逻辑保持一致。

#### 1.5. 调度器 pending 队列优先级排序
- **`backend/api/services/task_scheduler.py`**：`ScheduledTask` 新增 `task_kind` 字段，`_try_dispatch_pending()` 每次分发前按 task_kind 排序（search 优先于 comment_backfill）。
- **`backend/api/services/crawl_service.py`**：`start_crawler_thread()` 传入 `task_kind` 给调度器。

#### 2. 登录验证 TTL 缓存
- **`backend/crawler/reply_fetcher.py`**：新增 `_login_cache` 线程安全缓存机制（TTL=120s），`_ensure_reply_session_ready()` 在 TTL 内跳过重复的登录检查和域切换。登录失败（ChallengeSignal、浏览器断连）时自动使缓存失效。

#### 3. 回复硬恢复策略优化
- **`backend/crawler/reply_fetcher.py`**：回复翻页场景下硬恢复次数从 `policy.refresh_max_retries`（默认 3）降为 `min(2, policy)`，退避 cap 从 35s 降为 12s。单次硬恢复循环时间从 50-75s 降至约 20-30s。

#### 4. 动态空页退出阈值
- **`backend/crawler/reply_fetcher.py`**：新增 `_dynamic_max_empty_pages()` 根据 expected_count 动态计算阈值：≤50 条→3，≤500→5，≤2000→8，>2000→12。大评论量推文有更多机会触发有效翻页。同时"无 cursor 但覆盖率不足"的额外滚动也纳入空页计数，避免无限循环。

---

## [2026-04-02] 评论补采优先级、效率与进度展示优化

### 改动

#### 1. 批量恢复任务优先级排序
- **`backend/api/routers/tasks.py`**：新增 `_sort_tasks_by_priority()`，`_do_resume_tasks()` 中先按 task_kind 排序，普通搜索任务优先入队，评论补采任务排后。
- **`backend/api/services/task_queue_manager.py`**：`resume_queue()` 恢复队列时同样按 task_kind 排序，普通搜索优先于评论补采。

#### 2. 评论补采按评论数降序采集
- **`backend/crawler/comment_backfill_runner.py`**：新增 `_sort_tweets_by_reply_count()`，X 和微博评论补采均按推文预期评论数从高到低排序，优先采集高价值推文，即使中断也能最大化产出。

#### 3. 前端评论补采进度条展示
- **`frontend/src/lib/task-ui.ts`**：新增 `getCommentBackfillPercent()` 计算百分比；`getCommentBackfillSummary()` 增加失败数显示。
- **`frontend/src/components/features/tasks/TaskListCard.tsx`**：Comfortable 和 Compact 模式评论补采任务显示进度条 + 百分比 + 文字摘要。
- **`frontend/src/components/features/tasks/TaskPreview.tsx`**：快速预览面板评论补采任务显示进度条。
- **`frontend/src/components/features/task-detail/TaskDetailHeader.tsx`**：任务详情页评论补采任务显示进度条。

---

## [2026-04-02] 修复 X 回复链路空白页与误导性 `about:blank` 日志

### 问题
- 排查 `backend/logs/xcrawl.log` 发现，`2026-04-02 13:53` 到 `13:55` 这段实际只有微博任务在跑，没有新的 X 搜索日志。
- 但 X 侧更早的日志里反复出现：
  - `url=about:blank | missing=['auth_token', 'twid'] | cookies=[]`
- 这会让用户看到 Chrome 里挂着几个 `about:blank` 空白标签页，误以为 X 主搜索页没有正常导航。

### 根因
- `backend/crawler/reply_fetcher.py`
  - 评论/回复抓取 tab 在还停留 `about:blank` 时，就先做了 `check_login()` 快速校验，导致先打出“未登录”的误导性日志。
- `backend/crawler/pipeline.py`
  - X 的 reply worker 会在真正消费队列前就预创建 reply tab。
  - 微博 comment worker 也有同类“预开 tab”的副作用，而且那个 tab 实际没有参与评论抓取。
- `backend/crawler/reply_fetcher.py`
  - batch 共享回复 tab 也是在批次一开始就创建，即使后续推文被跳过或去重，也会留下可见空白页。

### 修复
- `backend/crawler/auth.py`
  - 抽出并公开 `ensure_x_domain_context()`，统一负责把 tab 先带入 `x.com` 域。
- `backend/crawler/reply_fetcher.py`
  - 回复抓取前先建立 X 域上下文，再做快速登录检查。
  - batch 共享 reply tab 改为按需创建，不再一进批次就开空白页。
- `backend/crawler/pipeline.py`
  - X 的 reply worker tab 改为首次真正消费任务时再创建。
  - 微博 comment worker 删除无实际用途的预开 tab 副作用。
- 测试
  - `backend/tests/test_reply_session_sync.py`
  - `backend/tests/test_pipeline.py`

### 验证
- `python3 -m py_compile backend/crawler/auth.py backend/crawler/reply_fetcher.py backend/crawler/pipeline.py`
- `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_reply_session_sync.py backend/tests/test_pipeline.py -q`
- 结果：`9 passed`

## [2026-04-01] 修复 Cloudflare 验证页等待时间过短

### 问题
X 爬虫命中 Cloudflare 验证页时，虽然会提示用户去浏览器手动处理，但主抓取恢复链路仍按普通 challenge 的短冷却执行。结果就是几秒内就继续刷新，五秒盾甚至还没完全展示出来就被打断。

### 修复
- `backend/api/routers/crawler_config.py`：补齐 `crawler_cloudflare_wait_seconds` 的读取、更新和持久化
- `backend/crawler/recovery_policy.py`：新增 Cloudflare 专用等待配置与统一 challenge 等待计划
- `backend/crawler/x_searcher.py` / `backend/crawler/reply_fetcher.py`：命中 Cloudflare 时改走长等待，不再快速刷新
- `frontend/src/hooks/useCrawlerConfig.ts`：补上 `crawler_cloudflare_wait_seconds` 默认值
- `backend/tests/test_crawler_config_and_recovery_policy.py`：补充回归测试

### 结果
- Cloudflare 验证页会为用户保留更充足的手动验证时间
- 普通 challenge 仍保持原有短冷却，不影响其他恢复路径

## [2026-03-31] 复爬任务移除 `max_count` 限制

### 问题
复爬任务会复用原任务的 `max_count`。当旧结果数、检查点聚合数正好已经达到这个上限时，任务一恢复就直接判定完成，表现为浏览器不断启动/关闭，但几乎不真正继续爬取。

### 修复
- `backend/api/routers/tasks.py`：复爬入口不再继承原任务的 `max_count`，统一以 `0`（无上限）重跑
- `backend/tests/test_task_recrawl.py`：补充回归断言，确保 X / 微博复爬都不会再带回旧上限
- `docs/api.md`：同步记录“复爬不再沿用原 `max_count`”的接口语义

### 结果
- 新发起的复爬任务不会再因为历史结果数等于旧上限而秒完成
- 服务重启后恢复同一复爬任务时，也会继续按“抓到当前查询耗尽”为止执行

## [2026-03-31] 全面移除任务级 `max_count`

### 变更
- 删除搜索任务、任务队列、并发搜索、批量导入等对外接口中的 `max_count`
- 删除前端创建任务、批量导入、任务详情、任务预览中的数量上限输入和展示
- X / 微博搜索执行链路统一改为“抓到当前结果耗尽为止”，不再基于任务级数量上限提前结束
- 文档同步更新，不再示例或说明 `max_count`

### 兼容说明
- SQLite 旧表中的 `max_count` 列暂时保留，仅用于兼容历史数据读取；新逻辑已不再依赖该列驱动任务执行

## [2026-03-30] 修复 recrawl 任务秒完成问题

### 问题
Recrawl 任务（`is_recrawl=True`）在断点恢复时秒完成，原因：
1. 断点有旧数据但无 cursor → 代码判定"搜索已完成"直接返回
2. 即使进入搜索，旧推文都被去重 → 连续空页 → 2 页后退出

### 修复
1. **断点恢复逻辑**：recrawl 模式下无 cursor 也继续搜索（找新推文）
2. **空页容忍度**：recrawl 从头搜索时提高到 10 页（旧推文去重是正常的）

---

## [2026-03-30] 修复"到底"检测误判问题

### 问题
`detect_end_of_timeline` 函数在页面刚加载时就误判为"已到底"，导致任务秒完成。

### 修复
- 新增 `fetched_count` 参数传入 `_wait_search_packet_with_recovery`
- 只有当 **已获取推文数 > 0** 时才启用"到底"检测
- 确保至少拿到过一页数据才会判定时间线到底

---

## [2026-03-30] X 搜索无结果快速跳过

### 修复
`wait_for_target_packet` 新增 `early_exit_check` 参数，在等待期间检测 "No results for ..." 页面，检测到后立即跳到下一个时间段（不再傻等 45 秒）。

---

## [2026-03-30] 撤销浏览器窗口隐藏修改

### 问题
之前添加的 `--window-position=-32000,-32000` 把浏览器窗口移到屏幕外，导致点击 Dock 栏的 Chrome 图标后看不到任何窗口。

### 修复
- 移除 `browser.py` 和 `browser_pool.py` 中的窗口位置偏移参数
- 移除相关的焦点恢复辅助函数
- 浏览器窗口现在会正常显示

### 说明
浏览器启动时会短暂抢焦点，这是 Chrome 的默认行为。如果你需要后台运行且不想看到浏览器窗口，可以：
1. 在设置中开启 `browser_headless`（无头模式）—— 但这样 Cloudflare 验证时无法手动操作
2. 或者接受当前行为：浏览器正常显示，需要手动处理验证时可以直接操作

---

## [2026-03-30] 并发爆炸 + profile 目录清理修复

### 问题1：任务队列触发几十个浏览器实例

**根因**：`notify_task_terminal` 在检测到"状态为 running/pending 但线程已死"的残留任务时，直接调用 `crawl_service.start_crawler_thread()`，完全**绕过调度器并发限制**。每个任务完成时都会触发，导致所有残留任务同时启动，并发数暴涨。

**修复**（`backend/api/services/task_queue_manager.py`）：
- 改为 `scheduler.enqueue(tid, t, platform=platform)`，让任务走正常调度队列
- 调度器会按 `crawler_max_concurrent_tasks` 上限控制实际启动数量

### 问题2：profile 目录清理失败 `[Errno 66] Directory not empty`

**根因**：旧进程的 Chrome 锁定了 `Default` 目录，`shutil.rmtree` 直接报错，导致警告日志刷屏

**修复**（`backend/crawler/browser_pool.py`）：
- 改用 `shutil.rmtree(ignore_errors=True)`
- 删除后若目录仍存在，逐个子项尝试清理
- 日志级别从 `WARNING` 降为 `DEBUG`，不再刷屏

### 修改文件
- `backend/api/services/task_queue_manager.py`
- `backend/crawler/browser_pool.py`

---

## [2026-03-30] 浏览器实例后台运行 + 关闭时无限重建修复

### 问题1：浏览器实例启动时抢夺系统焦点

**根因**：Chrome macOS 启动时默认激活窗口，`--no-startup-window` 和 `--window-position=-32000,-32000` 均未设置

**修复**（`browser_pool.py` + `browser.py`）：
- 启动参数加 `--no-startup-window`（Chrome 启动时不弹出窗口激活）
- 启动参数加 `--window-position=-32000,-32000`（浏览器窗口移到屏幕外，彻底不可见）
- 两个文件（浏览器池实例和单例浏览器）均已加上

### 问题2：关闭后端时浏览器实例无限重建

**根因**：`main.py` lifespan 关闭时调用 `close_all()` 杀掉所有浏览器进程，但任务线程仍在运行，`new_tab` 遭遇断连后触发重建逻辑，重建完成后再次被 `close_all` 杀掉，无限循环直到 Ctrl+C

**修复**：
- `browser_pool.py` 新增全局 `_shutting_down` 标志和 `set_shutting_down()` 函数
- `new_tab` 断连重试逻辑：`if _retried or _shutting_down: raise`（关闭期间直接放弃重建）
- `main.py` lifespan 关闭入口最先调用 `set_shutting_down()`，再关闭浏览器

### 修改文件
- `backend/crawler/browser_pool.py`
- `backend/crawler/browser.py`
- `backend/api/main.py`

---

## [2026-03-30] 账号僵尸占用根本原因修复

### 问题
5个账号、并发5，但仍然报"无可用账号"。

**根因**：`crawl_service.py` 的 `finally` 块只在 `done/failed/stopped` 时释放账号，**`paused` 状态不释放账号**。任何导致任务暂停的事件（登录失败、Cloudflare 验证、无账号可用）都会让账号继续被占用，下一批任务来时账号全部"僵尸占用"，`assign_account` 始终返回 `None`。

同时，`_x_account_worker_limit` 用 `active_assignments - running_x` 估算"暂停但占用账号的任务数"，僵尸占用会让此值虚高，导致调度器可用槽位变为 0，停止启动新任务。

**修复**（`backend/api/services/crawl_service.py`）：
- `finally` 条件改为 `final_status in ("done", "failed", "stopped", "paused")`
- 任务暂停时也释放账号，让其他任务可以立即复用

### 修改文件
- `backend/api/services/crawl_service.py`

---

## [2026-03-30] 爬虫并发稳定性三项修复

### 问题1：账号池全占用时任务崩溃（RuntimeError）

**根因**：并发任务数 > 账号数时，`assign_account` 返回 `None`，直接抛 `RuntimeError` 导致任务线程崩溃，状态标记为 `failed`，且会触发调度器重启循环

**修复**（`backend/api/services/crawl_service.py`）：
- 将 `raise RuntimeError(...)` 改为 `raise LoginRequiredPause(..., reason="no_account_available")`
- 任务进入 `paused` 状态等待账号释放，用户可手动继续，不再崩溃标记 `failed`

### 问题2：新浏览器实例启动时抢夺系统焦点

**根因**：`auth.py` 的 `_finalize_login_result` 在**任何**登录失败时都调用 `promote_browser_for_manual_interaction`（触发 `osascript activate` 把 Chrome 拉到前台）。但浏览器池初始化阶段 Cookie 还没注入，登录必然失败，错误地触发焦点抢夺

**修复**（`backend/crawler/auth.py`）：
- 只在 `result.reason == "challenge_required"` 时才调用 `promote_browser_for_manual_interaction`
- 普通登录失败（未登录、Cookie 过期）不抢夺焦点

### 问题3：Cloudflare 验证时自动刷新循环

**根因**：`navigate_with_retry` 在 `raise_on_risk=False`（默认）且 challenge 重试次数耗尽时，执行 `continue` 继续下一轮循环（会 `tab.refresh()`），形成"刷新 → 触发 CF → 再次超限 → 再次刷新"死循环

**修复**（`backend/crawler/page_health.py`）：
- challenge 重试耗尽时，**无论** `raise_on_risk` 为何值，都立即抛 `ChallengeSignal`，任务进入暂停状态并通知用户在浏览器完成验证
- 彻底移除"challenge 超限后继续刷新"的分支逻辑

### 修改文件
- `backend/api/services/crawl_service.py`
- `backend/crawler/auth.py`
- `backend/crawler/page_health.py`

---

## [2026-03-30] 时间分片状态 + 评论爬虫登录稳定性修复（深度修复）

### 问题1：时间分段未完成却显示"任务完成"

**根因（更深层）**：之前的修复只生成了正确的 `status_val`，但代码流程为：
1. 先调用 `update_task_result()`（内部强制写入 `status=done` + 发出 `task_done` 遥测事件）
2. 再判断 `segment_complete`，若为 `False` 再调用 `update_task_stopped()`
3. `final_status` 永远赋值为 `"done"`，`"stopped"` 分支根本不触发账号释放和队列通知

**修复（`backend/api/services/crawl_service.py`）**：
- 将 `segment_complete` 判断**提前到** `update_task_result` 之前
- 分段完成 → 调用 `update_task_result()`，触发正常 `done` 流程
- 分段未完成 → 跳过 `update_task_result()`，直接调用 `update_task_phase` + `update_task_stopped()`，避免发出错误的 `task_done` 遥测事件
- `final_status = status_val`（`"done"` 或 `"stopped"`），确保 `finally` 块中账号释放、浏览器池归还、队列通知均能正确执行

### 问题2：评论爬虫有时处于未登录状态

**根因**：`reply_fetcher.py` 的 `_ensure_reply_session_ready` 在 `check_login` 失败后走 `ensure_login_detailed(tab)`，这个函数只处理默认全局 Cookie，完全不感知账号池绑定账号。当回复浏览器实例与搜索浏览器实例为独立 Chrome 进程时，登录态同步不可靠。

**修复（`backend/crawler/reply_fetcher.py`）**：
- 新增 `_try_inject_pool_account_cookies(tab, task_id)` 函数：优先读取任务绑定账号（`get_task_account`），回退到 `pick_next_account()`，调用 `ensure_login_with_pool_detailed` 注入账号 Cookie
- `_ensure_reply_session_ready` 在浏览器实例 Cookie 注入失败后，**优先尝试账号池绑定账号**，再走 `ensure_login_detailed` 兜底
- 登录恢复链路：`check_login` → 浏览器实例 Cookie 注入 → 账号池绑定账号注入 → 默认 `ensure_login_detailed`

### 修改文件
- `backend/api/services/crawl_service.py`
- `backend/crawler/reply_fetcher.py`

---

## [2026-03-30] X 任务完成判断逻辑修复（时间分片未爬完不应标记完成）

### 问题
任务只要 crawler 返回结果就直接标记为 `done`，即使时间分片只爬了一部分。这是导致"明明没爬完却显示完成"的根本原因。

### 修复
在 `crawl_service.py` 中，crawler 返回后增加时间分片完成度检查：
```python
segment_progress = task_summary.get("segment_progress", {})
if segment_progress.get("enabled") and segment_progress.get("total_segments"):
    completed = segment_progress.get("completed_segments", 0)
    total = segment_progress.get("total_segments", 0)
    segment_complete = completed >= total

status_val = "done" if segment_complete else "stopped"
```

### 修改文件
- `backend/api/services/crawl_service.py`

### 效果
- 时间分片全部完成 → 状态 `done`
- 时间分片未完成 → 状态 `stopped`，显示实际进度，可恢复继续爬取

---

## [2026-03-30] X 评论爬虫 Cookie 注入修复（真正解决未登录问题）

### 问题：X 评论爬虫依旧是未登录状态

**根因**：`_inject_account_cookies`（`crawl_service.py`）的实现方式完全错误：
1. 开临时 tab → 注入 cookie → 关闭 tab
2. DrissionPage 的 `tab.set.cookies()` 是 tab 级操作，只在当前 tab 生效
3. 临时 tab 关闭后 cookie 全部丢失，后续 `reply_browser_instance.new_tab()` 开的新 tab 根本没有 cookie

**修复方案**：在 `BrowserInstance` 层级实现 cookie 继承机制

1. `backend/crawler/browser_pool.py`：
   - `BrowserInstance` 新增 `_cookies_to_inject` 列表，存储待注入的 cookie
   - 新增 `set_cookies(cookies)` 方法，设置实例级 cookie
   - 新增 `_inject_cookies_to_tab(tab)` 方法，将 cookie 注入指定 tab
   - `new_tab()` 方法在创建 tab 后**自动调用** `_inject_cookies_to_tab`，确保所有新 tab 都带有预设 cookie

2. `backend/api/services/crawl_service.py`：
   - 重写 `_inject_account_cookies`，不再开临时 tab
   - 直接调用 `browser_instance.set_cookies(account.cookies)` 设置到实例
   - 后续所有 `new_tab()` 自动继承这些 cookie

**效果**：
- X 搜索浏览器和评论浏览器各自独立设置 cookie，互不干扰
- 评论浏览器每开一个新 tab（每条推文一个 tab）都自动带上登录态
- 彻底解决"评论爬虫未登录"问题

## [2026-03-30] 翻页结束逻辑审查 + X 错误页 Retry 按钮点击

### 审查结论

**微博搜索翻页** — 逻辑完整，无需修改：
- `parse_search_page`（`html_parser.py`）返回 `has_next`（检测 `<a class="next">` / "下一页" 链接）和 `total_pages`（从 `ul.s-scroll` 分页器提取）
- `searcher.py` 第 806 行 `if not has_next: break` 正确结束循环
- 另有保底：`if not posts: break`（当前页无帖子时立即终止）

**X 搜索翻页** — 结束逻辑完整，补充 Retry 按钮处理：
- `bottom_cursor` 为空 → `break` ✅
- 连续 N 页无新推文 → `break` ✅
- `No results` 哨兵 → `break` ✅
- Retry 按钮 → **原来缺失，本次补充** ✅

### 新增：X 错误页 Retry 按钮检测与点击

X 的 "Something went wrong. Try again." 错误页面带有 Retry 按钮，
点击可触发内容重新加载，比刷新整页更轻量。

**修改文件**：

1. `backend/crawler/page_state.py`：新增 `click_retry_button_if_present(tab)` 函数
   - 先检测页面文本是否有错误特征（避免误触正常页面按钮）
   - 按优先级尝试 CSS 选择器（`data-testid="errorButton"`、`error-detail` 区域按钮、`:contains("Retry")` 等）
   - 兜底遍历所有 `<button>` 文字匹配（retry / try again / 重试）

2. `backend/crawler/recovery_policy.py`：`soft_recover_for_packet` 优先尝试点击 Retry 按钮
   - 点击成功后等待 1.5s 直接返回，不再做滚动+等待

3. `backend/crawler/page_health.py`：`navigate_with_retry` 的 `TRANSIENT_ERROR` 分支
   - 先尝试点击 Retry 按钮并等待 2s 重新检测
   - 若点击后页面恢复 OK，直接返回成功；否则继续原有刷新重试流程

## [2026-03-30] 时间分片搜索阻塞与 X 回复未登录 bug 修复

### 问题1：时间分片搜完一片后卡住等评论/回复，不继续下一片
**根因**：`_search_with_time_splits`（X）和微博分段搜索循环均对每个分片调用 `search(fetch_replies/comments=True)`，
而 `search()` 的 `finally` 块会 `pipeline.join()` 等待全部回复/评论抓完再返回，
导致每个分片的搜索+回复/评论串行执行，下一分片要等上一分片所有回复全部完成才开始。

**修复**：
- `backend/crawler/x_searcher.py`：`_search_with_time_splits` 分片循环改为 `fetch_replies=False`，
  全部分片推文搜完后统一调用 `_fetch_replies_for_tweets` 一次性抓回复
- `backend/crawler/weibo/searcher.py`：分段搜索循环改为 `fetch_comments=False`，
  全部分段搜完后统一遍历帖子逐条抓评论（同步模式，支持 telemetry 实时上报）

### 问题2：X 回复浏览器实例未注入账号 Cookie，导致未登录状态拿不到回复数据
**根因**：`crawl_service.py` 只对搜索用的 `_browser_instance` 注入了账号 Cookie，
`_reply_browser_instance`（通过 `acquire_aux` 独立创建）完全没有注入 Cookie，
导致所有回复抓取都是匿名未登录状态。

**修复**：
- `backend/api/services/crawl_service.py`：Cookie 注入逻辑扩展，
  `account_id` 存在时同时对 `_reply_browser_instance` 注入相同账号的 Cookie

## [2026-03-30] 实时速率面板「推文/分、评论/分全为 0」bug 修复

### 根因
1. `update_preview_tweets`（`task_manager.py`）计算了 `delta_replies` 但调用 `telemetry.record_event` 时**漏传**了 `delta_replies` 参数，导致评论速率在 telemetry 中始终为 0
2. 微博 `WeiboCommentPipeline` 初始化时未注入 `on_comment_done` 回调，评论并发抓取完成后没有任何 telemetry 事件，评论速率无法实时上报
3. 微博同步评论模式下，评论抓完后也没有上报 telemetry delta_replies（第一个 `weibo_comment_done` 事件是后来加的，但 `import` 位置错误，实际未生效）
4. `live-rates` API 的 `task_rates` 缺少 `idle_sec` 字段，前端 `TaskRateRow` 只靠速率 > 0 判断任务活跃，导致「翻页间隙/无结果分段」期间脉冲灯误灭

### 修复
- `backend/api/services/task_manager.py`：`update_preview_tweets` 补传 `delta_replies=delta_replies_telemetry` 给 `telemetry.record_event`
- `backend/crawler/weibo/searcher.py`：
  - `WeiboCommentPipeline` 初始化时注入 `on_comment_done` 回调，每条帖子评论完成后实时上报 `delta_replies`
  - 同步模式下评论抓完后增加 `telemetry.record_event(..., delta_replies=tree_stats.total_count)`
- `backend/api/routers/analytics.py`：`task_rates` 中加入 `idle_sec` 字段
- `frontend/src/services/api/index.ts`：`TaskRateItem` 类型加入 `idle_sec: number`
- `frontend/src/components/features/analytics/LiveRatesPanel.tsx`：`TaskRateRow.isActive` 改为 `idle_sec < 30` 优先判断，避免「暂时无新数据但任务仍在运行」时脉冲灯熄灭

## [2026-03-29] 浏览器并发面板加减号基准修复

### 修复
- 修复任务列表页“浏览器并发”面板把“实际浏览器池槽位上限”误当成“用户配置并发上限”来做 `+/-` 运算的问题
- 在开启跨平台并发时，面板现在会明确区分：
  - `configured_max_size`：单平台并发上限，也是加减按钮真正修改的值
  - `max_size`：跨平台扩容后的实际浏览器池槽位上限
- 前端面板文案同步调整，避免“点减号反而变大”的认知与交互错位

### 文档
- `docs/api.md`、`docs/施工文档.md`、`docs/changelog.md` 已同步追加说明

## [2026-03-29] X 搜索翻页误停与评论流水线队列修复

### 修复
- `backend/crawler/packet_guard.py` 新增 SearchTimeline 内容判定，只接受真正包含推文实体的数据包，忽略仅包含 top/bottom cursor 的空壳包
- `backend/crawler/x_searcher.py` 改为等待“有推文实体”的搜索包；若偶发收到仅游标包，会继续等待当前页真实结果，不再误计为空页并提前停止翻页
- `backend/crawler/x_searcher.py` 在执行翻页滚动前同步更新任务阶段文案，任务详情页现在会明确显示“正在滚动进入第 N 页”
- `backend/crawler/pipeline.py` 统一 `CrawlPipeline` 与 `WeiboCommentPipeline` 的队列确认逻辑，移除分支里的重复 `task_done()`，修复评论 worker / reply worker 反复触发 `task_done() called too many times`
- `frontend/src/components/features/analytics/LiveRatesPanel.tsx` 补充实时速率说明，明确 15s/60s 窗口值是采集速率，不是累计结果数

### 测试
- 新增 `backend/tests/test_packet_guard.py`
- 新增 `backend/tests/test_pipeline.py`

### 文档
- `docs/施工文档.md`、`docs/changelog.md` 已追加本次排查与修复记录

## [2026-03-29] 前端任务列表 UI 类型修复

### 修复
- 修复 `frontend/src/app/tasks/page.tsx` 中引用的 `TaskListCard` 组件 `busyAction` 属性的 TypeScript 类型不匹配问题，添加了遗漏的 `batchPause` 和 `merge` 类型定义，确保 `npm run build` 成功。
## [2026-03-29] 环境配置：Git SSH 代理修复

### 修复
- 修复并清理本地 `~/.ssh/config`，配置通过本地代理 (127.0.0.1:7890) 连接 Github SSH 协议的规则，解决了国内网络由于默认 22 端口阻断导致 `git push` 时无限卡死（挂起）的问题。


## [2026-03-29] 并发爬取串行化修复

### 修复
- `backend/crawler/browser_pool.py` 改为“独占 slot 优先、跨平台共享兜底”，避免 X 和微博任务在仍有容量时被强制挤进同一浏览器实例
- 新增统一的浏览器池容量计算；开启 `crawler_cross_platform_concurrent` 时，浏览器池会按总任务数自动扩容，而不是只按单个平台并发数创建实例
- `backend/api/routers/crawler_config.py` 与 `backend/api/routers/browser_pool.py` 统一按同一规则 resize 浏览器池，避免运行中把池子错误缩回去
- `backend/api/services/crawl_service.py` 的 `_inject_account_cookies()` 现会在 `finally` 中关闭临时 tab，修复 Cookie 注入阶段的 tab 泄漏
- `is_pool_mode_enabled()` 改为按实际可能并发任务数判断，修复 `crawler_max_concurrent_tasks=1` 但开启跨平台并发时仍误走共享浏览器链路的问题

### 测试
- 新增 / 扩展 `backend/tests/test_browser_pool.py`
- 新增 `backend/tests/test_crawl_service.py`
- 定向回归测试 `10 passed`

### 文档
- `docs/api.md` 已补充“单个平台并发上限”与“实际浏览器池上限”的语义说明
- `docs/施工文档.md`、`docs/changelog.md` 已追加本次修复记录

## [2026-03-29] 任务合并兼容历史空覆盖统计

### 修复
- 修复任务合并时 `time_coverage.*_ts_count = null` 导致后端 `500` 的问题
- `backend/api/services/task_manager.py` 新增安全整型转换，历史脏数据在覆盖范围合并时按 `0` 处理，不再因 `int(None)` 中断
- 新增 `backend/tests/test_merge_service.py` 回归用例，覆盖合并历史空统计字段场景

### 文档
- `docs/施工文档.md` 追加本次排查与修复记录
- `docs/changelog.md` 追加本次兼容性修复记录

## [2026-03-29] 复爬统一复用原任务

### 修复
- X 复爬不再创建新的派生任务，改为和微博一致，直接回源到最初任务并在原任务上重跑
- 对历史“复爬任务”再次复爬时，会自动回到根任务，避免任务数继续翻倍
- X 搜索链路新增 `seed_tweets` 支持，复爬时会保留旧结果并继续累加新结果，不会覆盖历史数据
- 前端复爬提示同步改为“原任务重跑”，不再提示“已创建新任务”

### 文档
- `docs/api.md`、`docs/施工文档.md`、`docs/changelog.md` 已同步更新

## [2026-03-29] X / 微博统一周分割

### 修复
- X 长跨度任务不再按月分割，统一改为固定 `7` 天窗口
- X 复爬不再使用旧的 `3` 天专用窗口，普通任务与复爬任务统一按固定 `7` 天窗口处理
- 微博长跨度时间范围不再按月拆段，统一改为固定 `7` 天窗口
- `x_time_split_max_segments` 不再用于静默截断计划；超出安全上限时会显式失败
- 新增微博时间分段配置：`weibo_time_split_window_days`、`weibo_time_split_max_segments`

### 持久化与恢复
- 任务摘要持久化新增 `is_recrawl` / `exclude_count`
- 服务重启后恢复 X 复爬任务时，会根据 `source_task_id` 重建 `exclude_tweet_ids`
- 修复恢复 / 继续任务后可能退回旧时间分片逻辑的问题

### 前端与文档
- 设置页改为展示“固定周窗口 / 安全上限”语义，不再出现“按月分割”旧描述
- 创建任务提示文案同步改为固定 `7` 天窗口
- `docs/api.md` 与 `docs/施工文档.md` 已同步更新

### 验证
- 后端相关测试：
  - `backend/tests/test_time_splitters.py`
  - `backend/tests/test_task_recrawl.py`
  - `backend/tests/test_task_storage_paths.py`
  - `backend/tests/test_weibo_resume_recovery.py`
  - `backend/tests/test_weibo_segment_tab_reuse.py`
  - 合计 `19 passed`
- 前端定向 ESLint 通过
- 额外补跑 `backend/tests/test_concurrent_crawl.py` 时发现 3 个与本次改动无关的历史失败，未在本次一并处理
		
## [2026-03-28] 浏览器池 profile 脏状态修复

### 修复
- 浏览器池实例启动前会强制重建自己的 `instance-*` profile 目录
- 不再复用异常退出后残留的脏 profile / 锁文件 / 偏好文件
- 降低 Chrome 启动时弹出“打开您的个人资料时出了点问题”的概率

## [2026-03-28] 清理历史微博复爬派生任务

### 运维处理
- 备份数据库为 `backend/tasks.pre-weibo-recrawl-cleanup-20260328T232531.db`
- 删除 `45` 条历史错误生成的微博复爬派生任务
- 清理 `5` 个对应的微博 checkpoint 文件
- 对仍存在的 `17` 个微博原任务重新发起复爬
- `3` 个派生任务因源任务已不存在，未能回源复爬

## [2026-03-28] 微博复爬复用原任务

### 修复
- 微博复爬不再创建新任务，改为直接复用原 `task_id` 重跑
- 保留原任务已采集结果，并作为本次复爬的提速种子和去重基线
- `backend/crawler/weibo/searcher.py` 新增 `seed_posts` 支持，最终结果会合并“旧结果 + 新结果”
- X 复爬仍保持新建增量任务，避免破坏现有语义
- 前端复爬提示和 `docs/api.md` 已同步更新

## [2026-03-28] 任务覆盖时间一次性回填

### 修复
- 撤回前端覆盖时间兜底逻辑，恢复为仅展示真实 `time_coverage`
- 备份主任务库为 `backend/tasks.coverage-backup-20260328T223514.db`
- 将 `backend/tasks.db` 里现有 `63` 条任务的 `time_coverage_json` 全量统一改为 `2022 年 6 月 - 2026 年 3 月`
- 抽样核验 `combined_start_at / combined_end_at` 已全部生效

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

## 2026-03-28

### 修复
- 修复任务合并过度：`merge_service.py` 现在仅忽略关键词大小写与多余空格，并把 `product / task_kind` 纳入分组键，避免不同时间范围或不同搜索类型的任务被错误合并。
- 新增 `scripts/restore_tasks_from_raw_responses.py`，支持从 `backend/raw_responses/` + `backend/checkpoints/` 恢复被误删的 X 任务，并在写库前自动备份 `backend/tasks.db`。
- 新增回归测试 `backend/tests/test_merge_service.py`，覆盖“不同 since/until 不合并”的关键场景。

### 运维
- 已根据本地保存的原始响应恢复缺失的 X 任务到 `backend/tasks.db`。
- 若后端服务正在运行，需要重启一次后端，以重新加载恢复后的任务数据。

### 调整
- 任务合并规则已改为“同平台 + 同任务类型下，只要关键词核心 token 有交集即可合并”；关键词更少的任务会优先并入关键词更完整的任务。
- 微博任务现已支持增量复爬，复爬时会自动排除原任务中已有的帖子 ID。

### 修复
- 微博复爬不再把展示用的 `since:/until:` 文本直接带回搜索关键词；时间范围改为继续走 `start_date/end_date`。
- 微博默认开启顶层 `OR` 自动拆分，降低 `A OR B` 直传微博搜索导致结果不稳定的风险。
- 复爬一个“复爬任务”时会自动回到最初源任务，避免链式复爬。

## 2026-03-28

### 修复
- 浏览器池现在会在任务结束后自动关闭空闲实例，避免桌面长期堆积多个空白 Chromium 窗口。
- 缩减并发上限时，会自动回收多余的空闲浏览器 slot，不影响正在运行的任务。
- 新增 `browser_pool_auto_close_idle` 配置，并在设置页提供“空闲实例自动关闭”开关。
- 新增回归测试 `backend/tests/test_browser_pool.py`，覆盖空闲实例回收与缩容回收场景。
- Chrome 有界面模式下不再携带 `AutomationControlled` 启动参数，减少每个新窗口顶部的警告提示。

### 新增
- 任务中心新增“批量改采评模式”：可把符合条件的 X 历史帖子采集任务，批量切到“采集评论（二级评论）”或切回“不采集评论”。
- 后端新增 `POST /api/v1/tasks/reply-collection/batch-update`，统一校验任务类型 / 平台 / 状态，并批量更新 `fetch_replies` 与 `reply_depth`。
- 前端新增 `BatchReplyCollectionDialog` 弹窗与批量入口，支持在任务列表内直接完成双向切换与结果反馈。
- 文档已同步更新：`docs/api.md`、`docs/施工文档.md`。

### 调整
- 批量改采评模式现已支持微博历史帖子任务，不再仅限 X。
- 相关文案已改为通用“采集评论 / 不采集评论”；其中 X 开启后仍按二级评论模式执行。

## 2026-03-29

### 运维
- 已检查并清理本地 `8000` 端口对应的后端进程；操作完成后二次校验确认该端口当前无占用。
- 已同步追加施工记录到 `docs/施工文档.md`。

## 2026-03-30

### 排查
- 已核查“任务突然都停了、任务未完成”的现场日志、运行进程与主任务库 `backend/tasks.db`。
- 确认本次主因是后端以 `uvicorn ... --reload` 运行，`WatchFiles` 监听到源码变动后触发热重启；`backend/crawler/x_searcher.py` 的修改时间与 `backend/logs/xcrawl.log` 中 `2026-03-30 04:45:43` 的 shutdown 时间完全一致。
- 确认重启后任务没有自动继续，是因为启动加载任务时会把残留的 `running / pending / paused` 任务统一落成 `stopped`，因此这一批未完成 X 任务都在 `2026-03-30 04:45:48` 前后被写成了 `stopped`。
- 另外识别出两类独立异常：X 账号轮换链路存在 `ensure_login_with_pool` 未定义报错；部分微博任务存在 `_comment_pipeline` 局部变量未绑定导致的失败。
- 已把完整排查过程、受影响任务范围和结论追加到 `docs/施工文档.md`。

### 修复
- 修复 X 评论/回复抓取时登录态没有同步到评论专用浏览器实例的问题；搜索侧确认可用的 Cookie 现在会同步给评论浏览器，账号轮换后也会同步更新。
- 评论抓取前新增登录兜底：会先补注入浏览器实例 Cookie，再校验/恢复 X 登录态；如果仍不可用，会按登录失效或挑战直接暂停，不再以游客态继续抓空评论。
- 修复 `backend/crawler/pipeline.py` 中 reply/comment worker 收到结束哨兵后不退出的问题，避免评论流水线线程卡死。
- 新增回归测试 `backend/tests/test_reply_session_sync.py`，并复跑 `backend/tests/test_reply_session_sync.py`、`backend/tests/test_pipeline.py`、`backend/tests/test_browser_pool.py`，共 `13 passed`。

## 2026-04-02

### 修复
- 浏览器池主实例和回复/评论辅助实例现在会在借出时立即预热拉起，避免并发任务已开始但浏览器进程仍停留在懒启动状态，导致体感上像“只占用一个实例”。
- `/api/v1/browser-pool/status` 新增总实例数、存活实例数、辅助实例数统计；任务页浏览器并发面板同步展示“主 slot + 辅助实例”的真实结构。

### 新增
- 新增 `browser_block_videos` 配置，并在设置页提供“无视频模式”开关。
- 新增统一资源策略模块 `backend/crawler/browser_resource_policy.py`，把禁图与禁视频集中接到主浏览器和浏览器池新 tab 的创建流程里。

### 验证
- 已执行后端编译检查与回归测试：`backend/tests/test_browser_pool.py`、`backend/tests/test_browser_resource_policy.py`，结果 `13 passed`。
- 已执行前端 `tsc --noEmit` 与目标文件 `eslint` 检查，通过。

### 修复补充
- 修复 Chrome 复用真实用户目录时未指定具体 profile 的问题：现在会自动读取 `Local State.profile.last_used`，并补上 `--profile-directory`，避免启动后卡在“谁在使用 Chrome?” 的 profile 选择页。
- 浏览器池隔离实例固定使用 `Default` profile，避免新实例落入 Chrome 首次 profile 选择流程。
- 辅助评论浏览器不再在借出时立即预热启动，减少并发任务一开始就唤醒过多 Chrome 实例。
- 浏览器实例现在会显式绑定账号；回复链路恢复登录态时优先使用实例绑定账号，不再在同一个实例里回退尝试其他账号。
- 修复 `reply_fetcher` 在 challenge/异常收尾阶段调用 `tab.listen.stop()` 时的空指针问题，避免 `'NoneType' object has no attribute 'stop'`。

### 修复补充：微博 418 冷却恢复与评论补采浏览器实例收口
- 新增 `backend/crawler/weibo/http_418_guard.py`，统一识别微博浏览器错误页 `HTTP ERROR 418`，并在搜索页/评论页命中后执行长冷却等待。
- `backend/crawler/weibo/searcher.py` 与 `backend/crawler/weibo/comment_fetcher.py` 接入 418 冷却恢复逻辑；默认冷却 `600` 秒，结束后自动重试当前页。
- `backend/config.py`、`backend/api/routers/crawler_config.py`、`frontend/src/hooks/useCrawlerConfig.ts`、`frontend/src/services/api/index.ts`、`frontend/src/components/features/settings/CrawlerConfigCard.tsx` 新增 `weibo_http_418_cooldown_seconds` 配置链路，设置页可直接调整。
- `backend/api/services/crawl_service.py` 修正 `comment_backfill` 任务的浏览器池借出策略：补采任务不再额外申请 reply/comment 辅助实例。
- `backend/crawler/comment_backfill_runner.py` 改为显式复用上层传入的浏览器实例执行 X/微博评论补采，避免浏览器池借出和实际抓取脱节。
- 新增回归测试：`backend/tests/test_comment_backfill_runner.py`、`backend/tests/test_crawl_service_comment_backfill.py`、`backend/tests/test_crawler_config_and_recovery_policy.py`。
- 已验证：
  - `backend/.venv/bin/python -m py_compile crawler/comment_backfill_runner.py api/services/crawl_service.py crawler/weibo/searcher.py crawler/weibo/comment_fetcher.py crawler/weibo/http_418_guard.py`
  - `backend/.venv/bin/pytest tests/test_comment_backfill_runner.py tests/test_crawl_service_comment_backfill.py tests/test_crawler_config_and_recovery_policy.py`
  - `frontend/./node_modules/.bin/tsc --noEmit`
  - `frontend/./node_modules/.bin/eslint src/components/features/settings/CrawlerConfigCard.tsx src/hooks/useCrawlerConfig.ts src/services/api/index.ts`
  - 结果：后端 `10 passed in 0.53s`，前端静态检查通过。
