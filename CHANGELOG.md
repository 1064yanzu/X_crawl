# Changelog

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
