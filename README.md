# X_crawl - X/Twitter 推文采集系统

X_crawl 是一个全栈架构的高性能推文采集系统。前端采用 **Next.js 16 (App Router) + React 19 + Tailwind CSS v4** 构建现代化控制台，后端基于 **FastAPI + DrissionPage** 驱动真实的 Chromium 浏览器进行网络请求拦截与数据采集。

系统支持关键词搜索采集、评论抓取、断点续传、实时任务监控，并提供跨平台一键启动脚本。

> **请在使用前仔细阅读本文件末尾的 [免责声明](#免责声明)。**

---

## 功能特性

- **真实浏览器驱动** — 基于 DrissionPage 操控 Chromium，通过网络请求拦截获取数据，无需逆向 API
- **断点续传** — 支持任务中断后从断点恢复，避免重复采集
- **实时监控** — 任务状态实时轮询，展示采集进度、速率、资源占用等指标
- **数据导出** — 支持 CSV、Excel 格式导出采集结果
- **多维度过滤** — 支持综合/最新/含图片/含视频等搜索维度
- **评论抓取** — 支持对已采集推文进行评论回复的深度抓取
- **自动节流** — 根据系统资源压力动态调整采集速率，防止服务卡死
- **跨平台** — 提供 macOS / Linux / Windows 启动脚本

---

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Node.js | >= 18.17 | 运行前端 |
| Python | >= 3.10 | 运行后端 |
| npm | 随 Node.js 安装 | 前端包管理 |
| pip | 随 Python 安装 | 后端包管理 |
| Chromium 浏览器 | Chrome / Edge / Brave 等 | 后端自动检测路径 |

---

## 快速开始

### 1. 克隆项目

```bash
git clone <repository-url> X_crawl
cd X_crawl
```

### 2. 后端启动

```bash
# 进入后端目录
cd backend

# 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 根据需要编辑 .env 文件

# 启动开发服务器
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问 `http://localhost:8000/docs` 查看 Swagger API 文档。

### 3. 前端启动

新开一个终端窗口：

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

启动后访问 `http://localhost:3721` 进入采集控制台。

### 4. 一键启动脚本（推荐）

项目提供跨平台启动脚本，自动处理环境检测与配置：

**macOS / Linux：**

```bash
# 开发模式
./run/start-backend.sh
./run/start-frontend.sh

# 生产模式
./run/start-backend.sh --prod
./run/start-frontend.sh --prod
```

**Windows PowerShell：**

```powershell
# 开发模式
./run/start-backend.ps1
./run/start-frontend.ps1

# 生产模式
./run/start-backend.ps1 --prod
./run/start-frontend.ps1 --prod
```

---

## 桌面应用首次启动（打包版）

桌面安装包采用 ad-hoc 签名（未做 Apple 公证 / Windows EV 证书），首次打开会被系统拦一次，确认后续不再提示。

### macOS

1. 双击 `.dmg`，将 **X_crawl** 拖入「应用程序」。
2. **首次右键点击 → 打开**（不要直接双击），在弹窗里再点「打开」即可绕过 Gatekeeper；
   或前往 **系统设置 → 隐私与安全性**，找到被拦提示点「仍要打开」。
3. 一次确认后，后续可正常双击启动。

### Windows

1. 运行 `.exe` 安装；安装程序会尝试写入防火墙入站规则（用于本地环回通信），若 UAC 弹窗请允许。
2. 首次启动若被 **SmartScreen** 拦截，点「更多信息 → 仍要运行」。
3. 若防火墙规则未成功写入，首次启动会有中文提示，按引导手动允许即可。

### 校验安装包完整性（SHA256）

每个 Release 产物旁都有同名 `.sha256` 文件：

```bash
# macOS
shasum -a 256 -c X_crawl-0.3.0-mac.dmg.sha256

# Windows (PowerShell)
Get-FileHash X_crawl-0.3.0-win.exe -Algorithm SHA256
```

> 桌面端遇到启动失败时，错误弹窗会保留「打开日志目录」按钮；也可在 **设置 → 关于·诊断 → 导出诊断包** 生成 zip 附在反馈里。

---

## 使用指南

### 创建采集任务

1. 打开前端控制台 (`http://localhost:3721`)
2. 在首页「新建任务」区域填写搜索关键词
3. 设置采集数量上限
4. 选择搜索维度（综合、最新、仅图片、仅视频等）
5. 可选：开启「断点续传」，遇到异常中断后可无缝恢复
6. 点击开始采集

### 任务管理

- **任务列表** (`/tasks`) — 查看所有任务的状态（等待中 / 采集中 / 完成 / 失败 / 暂停），支持暂停、恢复、停止、删除操作
- **任务详情** (`/tasks/[id]`) — 查看具体采集结果，推文以卡片形式展示，包含博主信息、互动指标、媒体内容等
- **断点管理** (`/checkpoints`) — 查看所有可恢复的断点，手动触发断点续传

### 数据导出

在任务详情页可选择导出格式：
- **CSV** — `GET /api/v1/export/{task_id}/csv`
- **Excel** — `GET /api/v1/export/{task_id}/excel`

### Cookie 管理

系统通过浏览器 Cookie 维持登录态：
- 支持手动上传 Cookie
- 支持通过浏览器自动捕获 Cookie
- Cookie 存储在 `~/.xcrawl-cookies.json`

---

## 生产部署

### 后端

生产环境不使用 `--reload`，且**必须使用单 worker**（任务调度和浏览器实例依赖进程内状态）：

```bash
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 前端

```bash
npm run build
npm run start
```

### Linux 无头服务器

若服务器无图形界面（无 `DISPLAY` 环境变量），系统会自动启用无头模式。可在设置页配置以下参数：

- `--no-sandbox`
- `--disable-dev-shm-usage`
- `--disable-gpu`
- `--disable-setuid-sandbox`

---

## 配置说明

### 后端环境变量 (`backend/.env`)

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BROWSER_EXEC_PATH` | Chromium 浏览器可执行文件路径 | 自动检测 |
| `BROWSER_USER_DATA_PATH` | 浏览器用户数据目录 | 自动检测 |
| `BROWSER_PROXY` | 代理地址 | 无 |
| `BROWSER_HEADLESS` | 无头模式 | `false` |
| `API_PORT` | 后端端口 | `8000` |

### 前端环境变量 (`frontend/.env.local`)

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `NEXT_PUBLIC_API_URL` | 后端 API 地址 | `http://localhost:8000` |

### 运行时配置

通过前端设置页面可动态调整以下参数（无需重启服务）：

- `crawler_auto_throttle_enabled` — 自动节流开关
- `crawler_dynamic_concurrency_enabled` — 动态并发调整
- `crawler_memory_pressure_warn_pct` — 内存压力警告阈值
- `crawler_memory_pressure_critical_pct` — 内存压力临界阈值
- `crawler_resource_throttle_max_factor` — 资源节流最大因子
- `crawler_live_push_interval_ms` — 实时数据推送间隔

---

## 项目结构

```
X_crawl/
├── frontend/                # Next.js 16 前端
│   ├── src/
│   │   ├── app/            # App Router 页面
│   │   ├── components/     # UI 组件 (ui/ + features/)
│   │   └── services/       # API 客户端
│   └── package.json
├── backend/                 # FastAPI 后端
│   ├── api/
│   │   ├── main.py         # 应用入口
│   │   ├── routers/        # REST 路由 (/api/v1/*)
│   │   ├── services/       # 任务调度、爬取服务
│   │   └── schemas/        # Pydantic 数据模型
│   ├── crawler/            # 爬虫核心
│   │   ├── x_searcher.py   # 采集编排器
│   │   ├── parser.py       # GraphQL 响应解析
│   │   ├── browser.py      # Chromium 浏览器管理
│   │   └── checkpoint.py   # 断点保存/恢复
│   ├── config.py           # 配置管理
│   └── requirements.txt
├── docs/                    # 接口文档与参考资料
├── run/                     # 启动脚本
└── README.md
```

---

## API 路由一览

所有接口前缀为 `/api/v1/`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/search` | 创建采集任务 |
| GET | `/search/{task_id}` | 查询任务状态与结果 |
| GET | `/tasks` | 列出所有任务 |
| POST | `/tasks/{id}/pause` | 暂停任务 |
| POST | `/tasks/{id}/resume` | 恢复任务 |
| POST | `/tasks/{id}/stop` | 停止任务 |
| DELETE | `/tasks/{id}` | 删除任务 |
| GET | `/checkpoints` | 列出可恢复断点 |
| DELETE | `/checkpoints/{id}` | 删除断点 |
| GET | `/export/{id}/csv` | 导出 CSV |
| GET | `/export/{id}/excel` | 导出 Excel |
| GET | `/cookies` | 获取 Cookie |
| POST | `/cookies` | 设置 Cookie |
| POST | `/cookies/capture` | 自动捕获 Cookie |
| DELETE | `/cookies` | 删除 Cookie |
| GET | `/crawler-config` | 获取运行时配置 |
| PUT | `/crawler-config` | 更新运行时配置 |

---

## 常见问题

**Q: 激活虚拟环境时提示路径错误？**

如果项目路径包含空格，需要用引号包裹路径：
```bash
source "/path with spaces/backend/.venv/bin/activate"
```

**Q: 采集失败并提示浏览器配置异常？**

确保本机安装了基于 Chromium 内核的浏览器（Chrome、Edge、Brave 等）。系统会自动检测浏览器路径，也可在 `.env` 中手动指定 `BROWSER_EXEC_PATH`。

**Q: 任务突然中断了怎么办？**

如果创建任务时开启了「断点续传」，前往 `/checkpoints` 页面找到对应断点，点击恢复即可从断点继续采集。

**Q: Linux 无头服务器上启动失败？**

确认已安装 Chromium 及其依赖。脚本会自动启用无头模式，如果仍有问题，在设置页开启 `--no-sandbox` 和 `--disable-dev-shm-usage` 参数。

**Q: 前端无法连接后端？**

检查后端是否已启动并运行在 8000 端口。如端口不同，在 `frontend/.env.local` 中设置 `NEXT_PUBLIC_API_URL` 指向正确的后端地址。

---

## 免责声明

### 1. 仅供学习与研究用途

本项目（X_crawl）是一个**技术研究与学习工具**，旨在帮助开发者了解网络爬虫、浏览器自动化、前后端全栈开发等技术原理。本项目**不得用于任何商业用途或非法目的**。

### 2. 遵守法律法规

使用者在使用本项目时，必须遵守所在国家和地区的法律法规，包括但不限于：

- 《中华人民共和国网络安全法》
- 《中华人民共和国数据安全法》
- 《中华人民共和国个人信息保护法》
- 《计算机信息网络国际联网安全保护管理办法》
- 以及使用者所在司法管辖区的相关法律法规

任何利用本项目进行的违法违规行为，均由使用者自行承担全部法律责任。

### 3. 遵守平台规则

X/Twitter 及其关联平台拥有自身的服务条款（Terms of Service）和使用政策。使用者应当：

- 在使用本项目前，仔细阅读并遵守 X/Twitter 的服务条款
- 不得过度频繁地请求平台接口，避免对平台正常运营造成影响
- 不得采集、存储、传播涉及他人隐私的个人信息
- 尊重内容创作者的知识产权

### 4. 数据使用责任

- 使用者通过本项目采集的数据，其使用方式和用途由使用者自行负责
- **严禁**将采集的数据用于骚扰、诈骗、身份盗用、垃圾信息发送等违法行为
- **严禁**将采集的数据用于未经当事人同意的商业营销活动
- 使用者应确保对采集数据的处理符合相关数据保护法规的要求

### 5. 免责条款

- 本项目按**「现状」**提供，不附带任何形式的明示或暗示保证，包括但不限于适销性、特定用途适用性和不侵权的保证
- 项目作者及贡献者**不对**因使用或无法使用本项目而导致的任何直接、间接、偶然、特殊或后果性损害承担责任，包括但不限于数据丢失、业务中断、利润损失等
- 项目作者及贡献者**不对**使用者使用本项目所进行的任何违法行为承担连带责任
- 本项目不保证持续维护和更新，不保证功能的完整性和稳定性

### 6. 知识产权

- 本项目代码采用开源协议发布，使用者应遵守相应协议条款
- 通过本项目采集的内容版权归原作者和/或 X/Twitter 平台所有
- 使用者不得将采集内容用于侵犯他人知识产权的行为

### 7. 最终声明

**使用本项目即表示您已阅读、理解并同意上述全部条款。如果您不同意上述任何条款，请立即停止使用并删除本项目的所有副本。**

本项目的作者保留随时修改本免责声明的权利，修改后的条款将在项目仓库中更新后立即生效。

---

## 许可证

本项目采用 **[Business Source License 1.1 (BSL 1.1)](LICENSE)**，核心条款：

- 仅允许**非商业用途**（个人学习、学术研究、教育评估）
- **禁止**任何形式的商业使用，包括但不限于付费服务、商用产品集成、以采集数据牟利
- 源码可供查看、修改和再分发，但必须保留许可证和署名
- **变更日期**：2029-05-12 — 届时自动转为 MIT License，届时将完全开源

详情请阅读 [LICENSE](LICENSE) 文件全文。
