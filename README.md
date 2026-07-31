# bili-rec

一个本地化的哔哩哔哩（Bilibili）直播流录制工具。自动监控开播、录制音视频流、采集弹幕，并提供 Web 管理界面与 REST API。

## 特性

- **自动录制** — 监控直播间开播状态，自动开始/停止录制，支持断流重连与多域名容灾
- **多格式支持** — 默认录制 FLV 流，缺流时自动回退 fMP4
- **弹幕采集** — 实时接收弹幕/礼物/SC/舰长购买等事件，保存为 XML 或原始 JSONL
- **录后处理** — 自动 Remux 为 MP4、注入元数据、弹幕转 ASS 字幕
- **Web 管理** — 内置 React SPA 前端，通过浏览器管理录制任务
- **REST API + WebSocket** — 完整的 API 接口，支持实时事件推送
- **扫码登录** — 支持 Bilibili TV 端扫码登录获取 Cookie
- **Docker 部署** — 单镜像同时提供 API 与 Web UI，一键运行

## 环境要求

| 依赖 | 版本 |
|------|------|
| Python | ≥ 3.12 |
| ffmpeg / ffprobe | 系统 PATH 可用（Remux/元数据注入需要） |
| Node.js（仅前端开发） | ≥ 20.19 |
| pnpm（仅前端开发） | ≥ 9 |

弹幕转 ASS 由 [dmconvert](https://pypi.org/project/dmconvert/) 完成。它是纯 Python 包并已声明为项目依赖，`uv sync` / `pip install` / Docker 构建都会自动装上，无需单独安装外部二进制。

## 安装

> **关于 Web 界面**：界面是一份需要编译的 React 应用，不随源码入库。
> 从 [Releases](https://github.com/OuYax/bili-rec/releases) 下载的 wheel 和
> Docker 镜像都已内置界面；直接从**源码**安装（下面的方式一、二）则不含界面，
> 服务只提供 REST API，根路径会返回 404。源码安装若需要界面，见
> [自行构建前端](#自行构建前端)。

### 方式一：使用 uv（推荐）

```bash
# 克隆仓库
git clone https://github.com/OuYax/bili-rec.git
cd bili-rec

# 创建虚拟环境并安装
uv sync

# 验证安装
uv run birec --version
```

### 方式二：使用 pip

```bash
git clone https://github.com/OuYax/bili-rec.git
cd bili-rec

python3.12 -m venv .venv
source .venv/bin/activate

pip install .

# 验证安装
birec --version
```

### 方式三：Docker

```bash
# 构建镜像
docker build -t birec .

# 运行容器
docker run -d \
  --name birec \
  -p 2233:2233 \
  -v ./recordings:/rec \
  -v ./config:/root/.birec \
  -v ./logs:/var/log/birec \
  birec
```

容器启动后访问 `http://localhost:2233` 即可打开 Web 管理界面。

## 使用

### 启动服务

```bash
# 最简启动（默认监听 0.0.0.0:2233）
birec

# 指定配置文件和输出目录
birec --config /path/to/config.toml --output /path/to/recordings

# 指定端口
birec --port 8080

# 启用 HTTPS
birec --key-file server.key --cert-file server.crt
```

### CLI 参数

| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--config` | `-c` | `config.toml` | 配置文件路径 |
| `--output` | `-o` | `./recordings` | 录制输出目录 |
| `--log-dir` | | `./logs` | 日志目录 |
| `--host` | | `0.0.0.0` | 绑定地址 |
| `--port` | | `2233` | 绑定端口 |
| `--open` | | `false` | 启动后自动打开浏览器 |
| `--ipv4` | | `false` | 强制使用 IPv4 |
| `--root-path` | | `""` | 反向代理子路径 |
| `--key-file` | | — | SSL 密钥文件 |
| `--cert-file` | | — | SSL 证书文件 |
| `--version` | `-V` | — | 显示版本号 |

### Web 管理界面

使用发布的 wheel 或 Docker 镜像时，服务启动后浏览器访问
`http://<host>:<port>` 即可进入 Web 管理界面，支持：

- 添加/删除录制任务（直播间）
- 启动/停止监控与录制
- 查看任务状态与录制详情
- 修改全局/任务级设置
- 扫码登录 Bilibili 账号
- 实时 WebSocket 事件推送

<a id="自行构建前端"></a>

#### 自行构建前端（源码安装）

源码安装的树里没有编译好的界面。自己构建一份并放到应用会去找的位置：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..

# 应用默认在 birec/web/static 下寻找界面
cp -r frontend/dist src/birec/web/static
```

也可以把产物放在任意目录，用环境变量指过去：

```bash
export BIREC_STATIC_DIR=/path/to/dist
```

前端开发时不必这样做——`pnpm dev` 起的开发服务器会把 API 请求代理到后端。

### REST API

API 基础路径为 `/api/v1`，主要端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/app/status` | 应用运行状态 |
| GET | `/api/v1/app/info` | 应用版本信息 |
| GET | `/api/v1/settings` | 获取全局设置 |
| PUT | `/api/v1/settings` | 更新全局设置 |
| GET | `/api/v1/tasks` | 获取所有任务列表 |
| POST | `/api/v1/tasks` | 添加录制任务 |
| DELETE | `/api/v1/tasks/{room_id}` | 删除任务 |
| POST | `/api/v1/tasks/{room_id}/start` | 启动录制 |
| POST | `/api/v1/tasks/{room_id}/stop` | 停止录制 |
| WS | `/api/v1/ws` | WebSocket 实时事件 |

完整的 OpenAPI 文档见 [docs/design/openapi.json](docs/design/openapi.json)，服务启动后也可访问 `/docs`（Swagger UI）。

## 配置

配置文件为 TOML 格式，默认路径 `config.toml`。主要配置段：

```toml
version = "1.0"

# 录制任务列表（通过 Web UI 添加后自动写入）
tasks = []

[output]
# 输出路径模板，支持变量：{roomid} {uname} {year} {month} {day} {hour} {minute} {second}
pathTemplate = "{roomid} - {uname}/blive_{roomid}_{year}-{month}-{day}-{hour}{minute}{second}"
outDir = "recordings"

[logging]
logDir = "logs"
consoleLogLevel = "INFO"
backupCount = 30

[header]
userAgent = "Mozilla/5.0 ..."
cookie = ""              # Bilibili 登录 Cookie（也可通过扫码登录设置）

[danmaku]
recordGiftSend = true    # 记录礼物
recordSuperChat = true   # 记录 SuperChat
recordGuardBuy = true    # 记录舰长购买
saveRawDanmaku = false   # 保存原始弹幕 JSONL

[recorder]
streamFormat = "flv"     # 流格式：flv / fmp4
qualityNumber = 10000    # 画质（10000 = 原画）
disconnectionTimeout = 600  # 断流超时（秒）
saveCover = true         # 保存封面

[postprocessing]
remuxToMp4 = true        # 录制完成后 Remux 为 MP4
injectExtraMetadata = true  # 注入元数据
danmakuToAss = false     # 弹幕转 ASS 字幕

[space]
checkInterval = 60       # 磁盘空间检查间隔（秒）
spaceThreshold = 1073741824  # 磁盘空间阈值（字节，默认 1GB）
```

### 环境变量

以下环境变量可覆盖对应配置：

| 变量 | 说明 |
|------|------|
| `BIREC_CONFIG` | 配置文件路径 |
| `BIREC_OUT_DIR` | 录制输出目录 |
| `BIREC_LOG_DIR` | 日志目录 |
| `BIREC_STATIC_DIR` | 前端静态文件目录 |
| `BIREC_BASE_HREF` | 反向代理子路径（如 `/birec`） |

## 开发

### 后端

```bash
# 安装开发依赖
uv sync --extra dev

# 运行单元测试
uv run pytest tests/unit -q

# 运行系统测试
uv run pytest tests/system -q

# 代码检查
uv run ruff check src tests
uv run mypy src
```

### 前端

```bash
cd frontend

# 安装依赖
pnpm install

# 开发模式（热更新）
pnpm dev

# 构建
pnpm build

# 运行单元测试
pnpm test

# 运行 E2E 测试
pnpm e2e
```

### 项目结构

```
src/birec/
├── bili/          # Bilibili API 适配层（直播、弹幕、WBI 签名）
├── cli/           # CLI 入口（Typer）
├── core/          # 录制核心逻辑（Recorder、弹幕、封面、路径）
├── danmaku/       # 弹幕解析与写入（XML/ASS）
├── event/         # 事件中心（EventCenter）
├── exception/     # 异常中心（ExceptionCenter）
├── flv/           # FLV 流解析与处理管道
├── hls/           # HLS/fMP4 流处理
├── logging/       # 日志配置
├── postprocess/   # 录后处理（Remux、元数据、弹幕转字幕）
├── setting/       # 配置管理（TOML + 环境变量）
├── task/          # 任务编排（RecordTask、TaskManager）
├── web/           # FastAPI Web 层（路由、中间件、WebSocket）
└── application.py # 应用组装与生命周期管理

frontend/          # React SPA 前端（Ant Design + TanStack Query）
```

## 已知限制

当前版本以 FLV 录制为主线，以下几处功能尚未接通，会在后续版本补齐：

| 限制 | 表现 | 影响 |
|---|---|---|
| **fMP4/HLS 录制未接通** | `stream_format` 设为 `fmp4` 时设置会被接受并回读，但实际仍以 FLV 录制 | 录制正常，只是格式不是所选的那个 |
| **磁盘空间无人看管** | 磁盘写满前没有告警，也不会自动回收旧录像 | 长期挂机需自行留意剩余空间 |
| **备用 CDN 未启用** | 接口给出多个 CDN 时只会使用第一个，它不可达则重试同一地址直至放弃 | 少数 CDN 故障场景下该场直播录不到 |
| **弹幕计数不更新** | 面板上的"弹幕总数"恒为 0 | 仅显示问题，弹幕本身完整写入 XML |
| **广播心跳无应答校验** | 服务端停止响应心跳时，客户端不会察觉并重连 | 极少数半开连接下该房间会静默收不到弹幕，重启任务可恢复 |

另有两处设计上有意不做（见 `blrec后端功能清单.md`）：通知系统与 Webhook、
按大小/时长自动切分文件。一场直播输出单个文件。

## 许可证

[GPL-3.0-or-later](LICENSE)
