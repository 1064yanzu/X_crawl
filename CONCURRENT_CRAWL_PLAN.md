# 并发爬取功能升级方案

## 概述

实现多账号并发爬取功能，支持用户配置多个 Cookie 账号，系统自动分配任务到不同账号并发执行，提高爬取效率。

## 核心设计

### 1. 任务分配策略

**分配模式**：按任务队列分配
- 用户创建多个搜索任务，系统自动将任务分配给不同的可用账号
- 每个账号同时执行一个任务，多账号可并发执行多个任务
- 任务完成后，账号自动释放，可被分配新任务

**账号选择算法**：
- 优先选择未被占用的账号
- 如果所有账号都被占用，等待任何账号释放
- 考虑账号的速率限制状态，跳过被限速的账号
- 轮询分配，避免某个账号过载

### 2. 架构变更

#### 新增模块

1. **`crawler/account_dispatcher.py`** - 账号分配器
   - 管理账号与任务的绑定关系
   - 实现账号选择和释放逻辑
   - 跟踪每个账号的当前任务

2. **`api/services/concurrent_task_manager.py`** - 并发任务管理器
   - 扩展现有 task_manager，支持账号绑定
   - 记录任务使用的账号
   - 提供账号释放接口

#### 修改现有模块

1. **`api/services/crawl_service.py`**
   - 修改 `run_search_task` 支持指定账号
   - 在爬虫执行前注入指定账号的 Cookie

2. **`crawler/x_searcher.py`**
   - 支持使用指定账号的 Cookie 进行搜索

3. **`api/services/task_manager.py`**
   - 新增字段：`assigned_account_id`、`account_alias`
   - 新增方法：`bind_account`、`release_account`

## 实现步骤

### Phase 1: 账号分配器（核心）
- [ ] 创建 `account_dispatcher.py`
- [ ] 实现账号选择算法
- [ ] 实现账号释放逻辑

### Phase 2: 任务管理器扩展
- [ ] 扩展 `task_manager.py` 支持账号绑定
- [ ] 添加账号相关的任务字段

### Phase 3: 爬虫集成
- [ ] 修改 `crawl_service.py` 支持账号注入
- [ ] 修改 `x_searcher.py` 使用指定账号

### Phase 4: API 层
- [ ] 创建并发搜索路由
- [ ] 实现批量任务创建

### Phase 5: 测试与优化
- [ ] 集成测试
- [ ] 性能测试

## 关键技术点

### 账号注入机制
- 在爬虫启动前，将指定账号的 Cookie 注入到浏览器
- 使用现有的 `cookie_manager.py` 和 `auth.py` 模块

### 并发控制
- 利用现有的 `task_scheduler.py` 的并发限制
- 每个账号最多同时执行一个任务

### 速率限制处理
- 账号被限速时，自动跳过该账号
- 使用 `rate_tracker.py` 的现有机制

## 配置项

新增配置（`config.py`）：
- `concurrent_crawl_enabled`: 是否启用并发爬取（默认 True）
- `account_assignment_strategy`: 账号分配策略（"round_robin" / "least_used"）

## 数据库变更

### tasks 表新增字段
- `assigned_account_id`: 分配的账号 ID
- `account_alias`: 账号别名

## 向后兼容性

- 现有 API 保持不变
- 单账号场景自动降级为原有行为
- 不影响现有的任务队列功能
