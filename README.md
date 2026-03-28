# X_crawl 极速推文采集系统

X_crawl 是一个全栈架构的高性能自动化采集控制台。系统采用目前最先进的 **Next.js 15 (App Router) + Tailwind CSS v4** 作为现代化前端界面，以及底层的 **FastAPI + DrissionPage** 构筑稳健且隐蔽的后端爬行与解析引擎。

本项目同时支持实时队列管控与断点续存（Resume），并提供极高拟合度的高级 UI 显示和全面的异常状态恢复机制。


你自己启动用这两条就行：
# 后端（终端1）
cd /develop/X_crawl
./scripts/start-backend.sh
# 前端（终端2）
cd /develop/X_crawl
./scripts/start-frontend.sh

如果你要生产模式：
./scripts/start-backend.sh --prod
./scripts/start-frontend.sh --prod



---

## 环境准备与前置要求

- **Node.js**: v18.17 及以上（运行并编译 Next.js 前端）
- **Python**: 3.10 及以上（运行后端爬虫与 API 接口）
- **包管理器**: `npm` 和 `pip`
- **浏览器环境**: 本机需要安装 Chrome/Edge/Chromium 或类似浏览器，系统默认开启了自动寻找执行路径与持久化用户会话（User Data）的支持机制。

---

## 🚀 后端 (Backend) 启动指南

后端负责响应前端的发号施令并将爬取任务入列执行。

### 1. 初始化及依赖安装

请在终端进入后端目录：

```bash
# 1. 切换到项目后端目录 (如果路径包含空格请加引号)
cd "/Volumes/external disk/develop/X_crawl/backend"

# 2. 创建一个虚拟环境（推荐将其命名为 .venv）
python -m venv .venv

# 3. 激活虚拟环境 (MacOS / Linux)
source .venv/bin/activate
# 注意：如果您在上级或者外部目录，需要加引号，例如：
# source "/Volumes/external disk/develop/X_crawl/backend/.venv/bin/activate"

# 4. 安装对应的 Python 依赖
pip install -r requirements.txt
```

### 2. 本地开发环境启动

```bash
# 确保在已激活的 .venv 环境下，在 backend 目录运行：
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```
启动后可以在 `http://localhost:8000/docs` 查看由 FastAPI 自动生成的 Swagger API 文档。

### 3. 生产环境部署启动

生产环境中不需要 `--reload` 并且建议结合 `gunicorn` 或直接使用 `uvicorn` 多 workers。

```bash
# 单节点生产推荐命令
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

*(注意：若采用 DrissionPage 进行实际浏览器调度，过多的 worker 可能会竞争浏览器资源，请根据实际机器和队列并发策略调整 worker 数量。目前单例模式建议默认 worker 或者利用任务队列)*

---

## 🎨 前端 (Frontend) 启动指南

前端提供了拥有卓越视觉与控制感的一站式管理大盘 (`Dashboard`)，所有操作可视化。

### 1. 初始化配置与安装

新开一个终端窗口，并在终端进入前端目录：

```bash
# 1. 切换到项目前端目录
cd "/Volumes/external disk/develop/X_crawl/frontend"

# 2. 安装所有的 Node.js 依赖
npm install
```

前端环境变量（可选）：可以复制 `.env.example` 创建 `.env.local` 并在里面设置 `NEXT_PUBLIC_API_URL=http://localhost:8000` (如果后端不使用默认的 8000 端口的话)。目前代码已实现默认回退代理逻辑。

### 2. 本地开发环境启动

```bash
# 启动具备模块热替换(HMR)特性的开发服务器
npm run dev
```

启动之后，访问 [http://localhost:3721](http://localhost:3721) 即可看到高级现代化的采集工作台。

### 3. 构建与生产环境启动

为了获取最优性能，强烈并建议在面向最终使用时进行生产级构建。

```bash
# 1. 在 frontend 目录下先执行构建
npm run build

# 2. 启动生产服务器
npm run start
```

---

## 💡 使用指南及核心机制说明

1. **一站式控制台 (Dashboard)**
   - 首页即可观测到后端 API 以及探活浏览器系统的实时挂载健康度。
   - 可以在 “新建任务” 区填写关键词、抓取数量并选型 (如综合、最新、包含图片/视频的独立过滤维度)。
   - **智能断点续传（推荐）：** 请勾选启动，如遇网路异常导致服务或页面丢失，重启即可无缝从中断点提取后续数据。

2. **采集任务队列 (`/tasks`)**
   - 查看所有已派发任务的历史周期。任务具备 `等待中 (Pending)`、`采集中 (Running)`、`完成 (Done)` 等状态。点击卡片均可直达具体细节抓取列表。
   - 随时可执行强制终止（删除）并清退云端存档。

3. **数据快照与结构化查看 (`/tasks/[id]`)**
   - 提供真实推文数据的流式复刻 UI 板块（`TweetCard`），自适应呈现博主验证体系、指标以及自适应矩阵排列的图文/高清视频回填显示。

4. **断点提取与灾备 (`/checkpoints`)**
   - 若系统被意外关闭而保存有 `Cursor` 及内存持久化数据，进入“断点续传”页面，您可以随时找到该断点，并手动一键传达命令恢复采集流继续抓取。

---

## 常见问题 (FAQ)

- **为什么激活虚拟环境时提示 `command not found` 或者路径错误？**
  如果您所在系统的目录名称带有空格（如 `external disk`），很多命令需要将整个路径加上双引号，或者尽量相对路径进入文件夹后，再执行 `source .venv/bin/activate`。
- **采集失败并提示配置异常？**
  本引擎利用 DrissionPage 操控真实浏览器。请确保您本机拥有一款主流基于 Chromium 内核的浏览器（例如 Google Chrome，Microsoft Edge，Brave 等）。后台启动已加入了自动查找检测探针。

---

## 跨平台一键启动脚本（macOS / Linux / Windows）

本仓库新增了原生启动脚本，优先作为部署与联调入口：

- macOS / Linux
  - 后端：`./scripts/start-backend.sh`
  - 前端：`./scripts/start-frontend.sh`
- Windows PowerShell
  - 后端：`./scripts/start-backend.ps1`
  - 前端：`./scripts/start-frontend.ps1`

支持参数：

- `--prod`：生产模式启动（后端禁用 reload；前端先 build 再 start）

示例：

```bash
./scripts/start-backend.sh --prod
./scripts/start-frontend.sh
```

## Linux 无头服务器注意事项

1. 若 Linux 环境没有 `DISPLAY`，脚本会默认开启 `BROWSER_HEADLESS=true`（可手动覆盖）。
2. 后端可开启 Linux 无头加固参数（设置页可配置）：
   - `--no-sandbox`
   - `--disable-dev-shm-usage`
   - `--disable-gpu`
   - `--disable-setuid-sandbox`
3. 推荐保留真实浏览器会话与自然请求头，不手工伪造核心鉴权头。

## 实时可观测与资源保护

新增能力：

1. 任务详情实时展示动作流、速率、风控/重试健康、主机与进程资源占用、推文/评论覆盖时间范围。
2. 在资源紧张时自动放慢抓取节奏，并在高压下动态收敛并发，降低服务卡死风险。
3. SSE 通道采用轻量快照（不推全量 tweets）+ 轮询兜底，兼顾实时性与性能。

对应可配置项（设置页可见）：

- `crawler_auto_throttle_enabled`
- `crawler_dynamic_concurrency_enabled`
- `crawler_memory_pressure_warn_pct`
- `crawler_memory_pressure_critical_pct`
- `crawler_resource_throttle_max_factor`
- 以及 `crawler_live_push_interval_ms`
