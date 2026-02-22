# Changelog

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
