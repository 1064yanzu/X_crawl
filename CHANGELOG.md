# Changelog

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
