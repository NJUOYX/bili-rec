# bili-rec 后端设计文档

## 文档信息

| 项 | 值 |
|---|---|
| 版本 | 0.1 |
| 状态 | 进行中（后端开发阶段） |
| 最近更新 | 2026-07-24 |
| 适用范围 | bili-rec 后端（不含前端；前端见 `frontend-design.md`） |
| 需求基线 | `../../blrec后端功能清单.md` §「最终功能范围（决策记录）」 |

---

## 1. 概述

### 1.1 项目定位
bili-rec 是一个面向 Bilibili 直播的**本地录制服务**：自动监控开播、录制音视频流（FLV，缺流时回退 fMP4）、采集弹幕、录后处理（Remux/元数据/字幕），并提供 Web API + WebSocket 供前端管理。设计上大量复用 blrec 的成熟逻辑（FLV 解析、弹幕协议、Rx 录制管道），在此之上以更现代的框架（FastAPI + Pydantic v2）重构，并**收敛功能范围**（移除通知/Webhook/鉴权/切分等）。

### 1.2 设计目标
- **正确稳定**：断流重连、时间戳校正、多域名容灾、磁盘保护，保证长时间无人值守录制。
- **可测试**：模块边界清晰、依赖可注入、外部 I/O 可 mock，满足 DT/ST 覆盖要求。
- **可演进**：分层解耦，新增录制格式/后处理步骤不影响上层。
- **易部署**：单进程、无外部数据库依赖，Docker 一键运行。

### 1.3 非目标（本阶段不做）
消息通知（6 渠道）、Webhook、Web 鉴权与 IP 防爆破、按大小/时长切分、手动切流、后处理章节生成、纯 HLS/ts 全量录制、Cookie 校验端点、前端实现。

---

## 2. 技术栈

| 层 | 选型 | 版本策略 | 说明 |
|---|---|---|---|
| 语言 | Python | 3.12+（CI 覆盖 3.12/3.13） | 复用 blrec 生态 |
| Web 框架 | FastAPI | 最新稳定 | 异步、自动 OpenAPI |
| ASGI 服务器 | uvicorn[standard] | 最新稳定 | |
| 数据校验/模型 | Pydantic v2 | 2.x | 替代 blrec 的 attrs+pydantic v1 |
| 配置 | pydantic-settings + TOML | 2.x + 标准库 `tomllib`(读)/`tomli-w`(写) | 环境变量 + TOML 文件 |
| 响应式管道 | reactivex (RxPY) | 4.x | 录制算子管道，沿用 blrec 模式 |
| HTTP 客户端 | aiohttp | 3.x | 流式下载 + API |
| HTML/XML | lxml | 最新稳定 | 弹幕 XML |
| 直播解压 | brotli / zlib(标准库) | 最新稳定 | 弹幕协议解码 |
| 媒体处理 | ffmpeg / ffprobe（外部二进制） | 系统提供 | Remux/探测；镜像内置 |
| 弹幕转字幕 | dmconvert | 最新稳定 | XML→ASS |
| CLI | Typer | 最新稳定 | |
| 日志 | loguru | 最新稳定 | |
| 重试 | tenacity | 最新稳定 | |
| 进度条 | tqdm | 最新稳定 | 可选 |
| 打包 | hatchling（PEP 517） + `pyproject.toml` | — | 现代打包 |
| 依赖/环境 | uv（首选）或 pip + venv | — | 快速可复现安装 |
| 测试 | pytest + pytest-asyncio + pytest-cov + respx/aioresponses | 最新稳定 | DT/ST |
| 质量 | ruff（lint+format）+ mypy | 最新稳定 | 取代 flake8/black/isort |
| CI/CD | GitHub Actions | — | |
| 容器 | Docker（多阶段） | — | |

> 版本锁定原则：`pyproject.toml` 用兼容区间声明，`uv.lock`/`requirements.lock` 锁定精确版本；实现启动时以当时最新稳定版为准并写入锁文件。

---

## 3. 系统架构

### 3.1 分层
```
┌─────────────────────────────────────────────────────────┐
│  接入层  Web (FastAPI routers) + WebSocket + CLI          │
├─────────────────────────────────────────────────────────┤
│  应用层  Application / RecordTaskManager                  │
├─────────────────────────────────────────────────────────┤
│  领域层  RecordTask · Recorder · Postprocessor            │
│         StreamRecorder(FLV/fMP4) · Danmaku · Cover        │
├─────────────────────────────────────────────────────────┤
│  管道层  reactivex operators (flv/hls/core.operators)     │
├─────────────────────────────────────────────────────────┤
│  适配层  bili(API/Live/LiveMonitor/DanmakuClient)         │
│         path · disk_space · logging · update              │
├─────────────────────────────────────────────────────────┤
│  基础设施 setting(TOML) · event(EventCenter/ExceptionCenter)│
└─────────────────────────────────────────────────────────┘
```

### 3.2 核心组件关系
```
Application
  ├── SettingsManager (TOML 读写, 环境变量叠加)
  ├── EventCenter / ExceptionCenter (reactivex Subject 总线)
  ├── SpaceMonitor + SpaceReclaimer (磁盘)
  └── RecordTaskManager
        └── RecordTask[room_id]
              ├── Live (房间抽象)
              ├── DanmakuClient (弹幕 WS)
              ├── LiveMonitor (事件驱动自动开停)
              ├── Recorder
              │     ├── StreamRecorder (FLV↔fMP4 门面)
              │     │     └── FLVImpl / HLSImpl (Rx 管道)
              │     ├── DanmakuReceiver + DanmakuDumper
              │     ├── RawDanmakuReceiver + RawDanmakuDumper
              │     └── CoverDownloader
              └── Postprocessor (Remux/注入/ASS)
```

### 3.3 关键数据流：一次完整录制
```
DanmakuClient 收到 LIVE 命令
  → LiveMonitor.emit(live_began) → 轮询流可用 → emit(live_stream_available)
  → Recorder 启动 StreamRecorder + Danmaku dumpers + CoverDownloader
  → StreamRecorder 选择 FLV/fMP4 实现，运行 Rx 管道：
       解析URL → 拉流 → 解析 → 处理(去碎片/校正/拼接) → 落盘
  → 落盘产生 video_file_completed 事件
  → Postprocessor 入队：Remux→MP4 / 注入元数据 / 弹幕→ASS → 删源(AUTO)
  → emit(postprocessing_completed)
DanmakuClient 收到 PREPARING → LiveMonitor.emit(live_ended) → Recorder 停止
所有事件经 EventCenter → WebSocket 推送前端
```

---

## 4. 项目布局

包名 `birec`（bili-rec）。目录结构（镜像 blrec，去除已裁剪模块）：

```
bili-rec/
├── pyproject.toml            # 打包/依赖/工具配置(ruff,mypy,pytest)
├── uv.lock                   # 锁定依赖
├── Dockerfile                # 多阶段构建(含 ffmpeg)
├── .github/workflows/        # CI/CD
│   ├── ci.yml                # lint+type+DT
│   ├── st.yml                # 系统测试(含 ffmpeg)
│   └── release.yml           # 构建+镜像发布
├── docs/design/              # 本设计目录
├── src/birec/
│   ├── __init__.py           # __version__
│   ├── application.py        # 应用装配与生命周期
│   ├── setting/              # 配置模型 + TOML 管理
│   ├── event/                # EventCenter/ExceptionCenter + 事件模型
│   ├── bili/                 # B站适配: api/live/live_monitor/danmaku_client/models
│   ├── core/                 # recorder/stream_recorder/*_impl/danmaku_*/cover/operators
│   ├── flv/                  # FLV 解析/封装 + operators
│   ├── hls/                  # fMP4/HLS 分片 + operators (仅回退所需)
│   ├── danmaku/              # 弹幕 XML 读写/合并
│   ├── postprocess/          # Postprocessor/remux/ffmpeg_metadata
│   ├── disk_space/           # SpaceMonitor/SpaceReclaimer
│   ├── task/                 # RecordTask/RecordTaskManager/models
│   ├── path/                 # 路径模板与旁车文件
│   ├── logging/              # loguru 配置 + 上下文
│   ├── update/               # PyPI 版本检查
│   ├── web/                  # FastAPI app/routers/middlewares
│   └── cli/                  # Typer 入口
└── tests/
    ├── unit/                 # DT: 单元测试(镜像 src 结构)
    ├── component/            # DT: 组件/管道测试
    ├── system/               # ST: 端到端(mock B站服务)
    ├── fixtures/             # 测试数据(样例FLV/m3u8/弹幕帧)
    └── conftest.py
```

---

## 5. 模块详细设计

> 约定：所有对外部（网络/文件/子进程）的访问都通过可注入的客户端/接口，便于测试 mock。异步优先（`async def`）。

### 5.1 setting（配置管理）
- **职责**：定义全部配置 Schema（Pydantic v2 模型），从 TOML 加载、合并环境变量、按需回写、提供全局/任务级读写。
- **模型**（`models.py`）：
  - `Settings`：顶层。`version`、`tasks: list[TaskSettings]`、`output`、`logging`、`bili_api`、`header`、`danmaku`、`recorder`、`postprocessing`、`space`。**移除**：所有 notification、webhooks、api_key。
  - 分区模型：`BiliApiSettings`、`HeaderSettings`、`DanmakuSettings`、`RecorderSettings`、`OutputSettings`、`PostprocessingSettings`、`LoggingSettings`、`SpaceSettings`、`TaskSettings`。
  - `TaskOptions`：任务级可选覆盖（字段全 `Optional`，`None` 表示回退全局）。
  - I/O 视图：`SettingsIn`/`SettingsOut`（partial）。
  - 命名：外部 camelCase 别名，内部 snake_case（Pydantic v2 `alias_generator` + `populate_by_name`）。
- **管理器**（`SettingsManager`）：`load()`/`dump()`（`tomllib`/`tomli-w`，dump 时剔除 None）、`get_settings()`、`apply_task_options()`。
- **环境变量**：`BIREC_CONFIG`、`BIREC_OUT_DIR`、`BIREC_LOG_DIR`、`BIREC_PROGRESS`、`BIREC_TRACE`、`BIREC_IPV4`、`BIREC_REC_TTL`、`BIREC_DANMAKU_PROTOCOL_VERSION`。（**移除** `BIREC_API_KEY`。）
- **配置项清单**：见 §11。

### 5.2 event（事件总线）
- **EventCenter / ExceptionCenter**：基于 `reactivex.Subject`，`emit(event)` / `events: Observable`。全局单例，供 WebSocket 订阅。
- **事件模型**（`models.py`）：`{type, id(uuid), date(UTC+8 ISO), data}`。保留事件类型：
  - `LiveBegan/LiveEnded/RoomChange`
  - `RecordingStarted/Finished/Cancelled`
  - `VideoFileCreated/Completed`、`DanmakuFileCreated/Completed`、`RawDanmakuFileCreated/Completed`
  - `CoverImageDownloaded`
  - `VideoPostprocessingCompleted`、`PostprocessingCompleted`
  - `SpaceNoEnough`
  - 异常经 ExceptionCenter 独立通道。
- **移除**：webhook/notifier 订阅者（仅 WebSocket 消费事件）。
- **提交器**：`LiveEventSubmitter`、`RecorderEventSubmitter`、`PostprocessorEventSubmitter`、`SpaceEventSubmitter`。

### 5.3 bili（B站适配层）
- `api.py`：`WebApi`/`AppApi`。多域名容灾请求、WBI 签名（-352 刷新）、App 签名、tenacity 重试、`getRoomPlayInfo`、房间/用户信息、`get_danmu_info`、`get_timestamp`、**TV 扫码登录** `request_tv_qrcode`/`poll_tv_qrcode`。
- `live.py`：`Live`。init/刷新、直播状态（API+HTML 兜底）、连通性 HEAD、**流地址解析**（格式/编码/画质 + 精确异常）、**CDN 主机优选**、**备用线路**、房间隐藏/锁定/加密检测；UA/Cookie/base URLs 热切换。
- `live_monitor.py`：`LiveMonitor`。解析 `LIVE/PREPARING/ROUND/ROOM_CHANGE`，状态去抖，流可用轮询（1s，上限 30min），定时兜底（~600s±60），**断线重连状态修复**。发射 `live_began/ended/stream_available/stream_reset/room_changed`。
- `danmaku_client.py`：`DanmakuClient`。WS 长连接握手、协议解码（NORMAL/DEFLATE/BROTLI）、30s 心跳、自动重连（主机轮换 + 退避 + 刷新弹幕信息）、消息广播、cookie 提取 uid/buvid、cookie/UA 变更重启。
- `models.py`/`typing.py`/`helpers.py`：`LiveStatus`、`RoomInfo`、`UserInfo`；`QualityNumber`、`StreamFormat`、`StreamCodec`、`ApiPlatform`；画质名称映射、二维码登录、cookie 拼装、共享 aiohttp 连接器。

### 5.4 core（录制协调）
- `recorder.py`：`Recorder`。响应监控事件自动开停；聚合并再发射文件生命周期事件；实时统计透传；构造 StreamRecorder + Danmaku(+Raw) + Cover。（**移除** `cut_stream`/`can_cut_stream`。）
- `stream_recorder.py`：`StreamRecorder` 门面。**FLV↔fMP4 自动回退**（无 FLV→fmp4；fmp4 超时→flv）+ 实现热切换；追踪真实格式/画质；独立线程运行 Rx 管道 + 按房间日志上下文；`malloc_trim`。
- `flv_stream_recorder_impl.py`：FLV Rx 管道（解析URL→拉流→录制监控→统计→解析→异常处理→process→注入/分析→落盘→统计）。**移除** Cutter、Limiter。
- `hls_stream_recorder_impl.py`：fMP4/HLS Rx 管道（拉播放列表→解析新分片→独立下载线程→拉分片→探测/分析→分片落盘→播放列表落盘）。**移除** Cutter、Limiter。
- 弹幕：`DanmakuReceiver`（解析 DANMU_MSG/SEND_GIFT/GUARD_BUY/SUPER_CHAT/USER_TOAST，有界队列 2000 丢旧）；`DanmakuDumper`（XML + 元数据头；礼物/免费礼物/上舰/SC/Toast 开关；含用户名开关；时间轴校正；重试）；`RawDanmaku*`（JSONL）。
- `cover_downloader.py`：下载 + sha1 去重 + 重试。
- 支撑：`MetadataProvider`、`PathProvider`、`StreamParamHolder`（画质回退/平台轮换/备用流）、`Statistics`；`models.py`（弹幕消息模型）。
- `operators/`：`StreamURLResolver`（缓存/HEAD 复用/画质回退/失败复查）、`StreamFetcher`、`StreamParser`、`RecordingMonitor`（中断/恢复）、`ConnectionErrorHandler`（600s 容忍）、`RequestExceptionHandler`、`ExceptionHandler`（磁盘满/房间异常优雅完成）、`ProgressBar`、`StreamStatistics/SizedStatistics`。

### 5.5 flv（FLV 引擎）
- 低层：models/io/avc/amf/scriptdata/format。
- `operators/`：`parse`；`process`=去碎片→切分→[排序]→过滤→校正→修复→拼接(JoinPoint)；`Analyser`（MetaData/关键帧索引）、`Injector`、`Prober`(ffprobe)、`JoinPointExtractor`、`Dumper`、`ProgressBar`；元数据落盘/分析/注入（后处理复用）。
- **移除**：`Cutter`、`Limiter`（不切分/切流）。JoinPoint 仍保留用于拼接与元数据，但**不再用于章节生成**。

### 5.6 hls（fMP4/HLS 引擎，仅回退所需）
- `operators/`：`PlaylistFetcher`、`PlaylistResolver`（新分片跟踪）、`SegmentFetcher`（init+媒体分片/重试/crc32/损坏检测）、`SegmentDumper`、`PlaylistDumper`（时长/序列/分片丢失检测）、`Prober`、`Analyser`；分片元数据 JSON 落盘。
- **移除**：`Cutter`、`Limiter`。不追求纯 HLS/ts 全量录制场景。

### 5.7 danmaku（弹幕文件工具）
- `DanmakuWriter/Reader`：B站兼容 XML（`<metadata>/<d>/<toast>/<gift>/<guard>/<sc>`、控制字符清洗、金/银瓜子序列化）。
- 合并/拼接：`DanmakuCombinator`（时间基 LIVE/RECORD）、`DanmakuConcatenator`（delta 偏移）、`merge_danmaku`、`has_danmu/clear_danmu/copy_damus`。

### 5.8 postprocess（后处理）
- `Postprocessor`：队列驱动异步 worker，**全局并发 1**（跨房间）。
- 能力（按范围裁剪）：
  - **Remux FLV→MP4**（`ffmpeg -codec copy` + `filter_units=remove_types=12` 去 filler）。
  - **Remux fMP4(.m4s)→MP4**（经生成的 m3u8）。
  - **FFmpeg 元数据文件注入**（Title/Artist/Date/Description(JSON)/Comment）。
  - **FLV 额外元数据注入**（不 remux 时，关键帧丢失重分析恢复）。
  - **FLV 有效性检查**（无效且 <1MB 跳过）。
  - **弹幕 XML→ASS**（dmconvert；字体/SC 字体/分辨率 X/Y 可配）。
  - **删源策略**：固定 **AUTO**（失败不删；成功删源 .flv/.m4s/.m3u8/.meta/.meta.json）。
  - 进度上报（解析 ffmpeg `size=`）、状态 WAITING/REMUXING/INJECTING、相关文件跟踪、发 `postprocessing_completed`。
- **移除**：删源策略的 SAFE/NEVER 分支简化为 AUTO 单策略；**章节生成**（`_make_chapters_*` 不实现）。

### 5.9 disk_space（磁盘）
- `SpaceMonitor`：周期轮询剩余空间（`check_interval`），低于 `space_threshold` 发 `space_no_enough`（含 total/used/free）。
- `SpaceReclaimer`：`recycle_records=true` 时，按 mtime/atime 升序删最旧文件（限定后缀集），带 **TTL 保护**（`rec_ttl`，默认 24h，`BIREC_REC_TTL` 可覆盖），`OSError` 重试。

### 5.10 task（任务管理）
- `RecordTask`：组合 Live+DanmakuClient+LiveMonitor+Recorder+Postprocessor+事件提交器。生命周期 setup/destroy；监控开关；录制开关（force）；运行状态机 STOPPED/WAITING/RECORDING/REMUXING/INJECTING；信息刷新/弹幕客户端重启；视频/弹幕文件明细。（**移除** cut。）
- `RecordTaskManager`：`Dict[room_id, RecordTask]`。加载全部/添加（重试+应用设置+可选自动启用+失败回滚）/移除/启停/监控录制粒度控制/查询（data/param/metadata/profile/videos/danmakus）/信息更新/设置应用（bili_api/header/output/danmaku/recorder/postprocessing）。
- `models.py`：`RunningStatus`、`TaskStatus`、`TaskParam`、`TaskData`、文件状态与明细模型。

### 5.11 path（路径）
- 旁车派生（.xml/.jsonl/.ass/.m3u8/.m4s/.jpg/.png/.meta/.meta.json）、`escape_path`、路径模板变量 `{roomid}{uname}{title}{area}{parent_area}{year}{month}{day}{hour}{minute}{second}`、自动建目录、自动去重 `_(n)`、模板正则校验。**移除** filesize/duration 相关。

### 5.12 logging
- loguru：控制台（级别可配，含 room_id 上下文）+ 文件（DEBUG/TRACE，每日 00:00 轮转，保留 backup_count 天，backtrace/diagnose）；`TqdmOutputStream`；按房间 `logger.contextualize(room_id=...)`。

### 5.13 update
- `PypiApi`：查询 PyPI 项目/发行版元数据（重试/超时）；`get_latest_version_string`。仅检查最新版本，不自动升级。

### 5.14 web（接入层）
- `main.py`：加载 Settings（TOML+env）、装配 FastAPI、注册路由、生命周期（startup→launch，shutdown→dump+exit）、静态托管 SPA（`.js` MIME、404→index.html）。
- 中间件：CORS、Brotli 压缩、`BaseHrefMiddleware`（反代子路径）、`RouteRedirectMiddleware`（前端路由回退）。**移除**：`security.py` 与全局 `authenticate` 依赖。
- 异常映射：NotFound→404、Forbidden→403、Exists→409、Validation→406；统一响应体 `{code,message,data}`。
- 路由见 §7。**移除**：`/tasks/{id}/cut`、`/validation/cookie`、settings 中的通知/webhook/apikey 分支。
- `cli/main.py`：Typer 启动 uvicorn，选项 `--version/-c/-o/--log-dir/--progress/--host/--port/--open/--ipv4/--root-path/--key-file/--cert-file`（**移除** `--api-key`）。

---

## 6. 数据模型（要点）

- **配置**：Pydantic v2 模型，见 §11 全量清单。
- **事件**：`Event{type:str, id:str, date:str, data:dict}`；`data` 依类型而定（见 §5.2）。
- **任务**：`TaskData{user_info, room_info, task_status}`；`TaskStatus{monitor_enabled, recorder_enabled, running_status, stream_url, stream_host, dl_total, dl_rate, rec_elapsed, rec_total, rec_rate, danmu_total, danmu_rate, real_stream_format, real_quality_number, recording_path, postprocessor_status, postprocessing_path, postprocessing_progress}`。
- **文件明细**：`VideoFileDetail{path,size,status}`、`DanmakuFileDetail{path,size,status}`。

---

## 7. API 设计

统一前缀 `/api/v1`，统一响应体 `ResponseMessage{code:int=0, message:str='', data?:dict}`。

### 7.1 任务 `/tasks`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/tasks/data` | 分页任务数据（`page`/`size`/`select`） |
| GET | `/tasks/{room_id}/data` | 单任务数据 |
| GET | `/tasks/{room_id}/param` | 任务参数 |
| GET | `/tasks/{room_id}/metadata` | 录制元数据 |
| GET | `/tasks/{room_id}/profile` | 当前流 ffprobe Profile |
| GET | `/tasks/{room_id}/videos` | 视频文件明细 |
| GET | `/tasks/{room_id}/danmakus` | 弹幕文件明细 |
| POST | `/tasks/info` · `/tasks/{room_id}/info` | 刷新信息 |
| POST | `/tasks/start` · `/tasks/{room_id}/start` | 启动 |
| POST | `/tasks/stop` · `/tasks/{room_id}/stop` | 停止（`force`/`background`） |
| POST | `/tasks/recorder/enable` · `/tasks/{room_id}/recorder/enable` | 启用录制器 |
| POST | `/tasks/recorder/disable` · `/tasks/{room_id}/recorder/disable` | 停用录制器 |
| POST | `/tasks/{room_id}` | 添加任务（支持短号，返回真实房号） |
| DELETE | `/tasks` · `/tasks/{room_id}` | 删除 |

过滤维度：all / 直播状态(preparing/living/rounding) / 任务状态(monitor·recorder 启停) / 运行状态(stopped/waiting/recording/remuxing/injecting)。**移除** cut 相关端点。

### 7.2 设置 `/settings`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/settings` | 全局设置（`include`/`exclude`） |
| PATCH | `/settings` | 修改全局设置（改 header 重连弹幕客户端） |
| GET | `/settings/tasks/{room_id}` | 任务级选项 |
| PATCH | `/settings/tasks/{room_id}` | 修改任务级选项（null 回退全局） |

### 7.3 应用 `/app` · 扫码 `/qrcode` · 校验 `/validation` · 更新 `/update`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/app/status` · `/app/info` | 运行状态 / 应用信息 |
| POST | `/app/restart` · `/app/exit` | 重启 / 退出 |
| GET | `/qrcode/login` | 请求 TV 登录二维码 |
| POST | `/qrcode/login/poll` | 轮询登录并写入 cookie |
| POST | `/validation/dir` | 目录可读写校验 |
| GET | `/update/version/latest` | PyPI 最新版本 |

### 7.4 WebSocket
| 路径 | 说明 |
|---|---|
| `WS /ws/v1/events` | 应用事件流（EventCenter） |
| `WS /ws/v1/exceptions` | 异常流（ExceptionCenter） |

> API 契约由 FastAPI 自动生成 OpenAPI，作为前端阶段的对接依据（导出到 `docs/design/openapi.json`）。

---

## 8. 并发与运行时模型

- 单进程 asyncio 事件循环承载所有任务的监控/弹幕/协调。
- 每个 `StreamRecorder` 在**独立线程**运行其 reactivex 管道（CPU/IO 密集的解析与落盘不阻塞事件循环）；HLS 分片下载再开独立下载线程。
- `Postprocessor` 全局 `Semaphore(1)` 串行，避免多房间同时 ffmpeg 争抢资源。
- 弹幕采用**有界队列（2000）溢出丢旧**，隔离弹幕洪峰对录制的影响。
- 优雅退出：SIGINT/SIGTERM → 停止所有任务 → dump 设置 → 关闭事件循环。

---

## 9. 错误处理与健壮性

- **多域名容灾**：base API 多地址并发/轮询。
- **画质自动回退**：无目标画质 → 回退原画(10000)。
- **备用 CDN 线路**：主机优选 + alternative 切换。
- **断线容忍**：连接错误等待至 `disconnection_timeout`（默认 600s）复查连通性。
- **断线重连状态修复**：WS 重连后复查状态补发事件（应对休眠）。
- **磁盘满**：`ENOSPC` 优雅完成当前文件并停止。
- **磁盘不足**：自动回收最旧录制（TTL 保护）。
- **流损坏**：FLV 去碎片、时间戳校正/修复、解析错切备用流。
- **重试**：网络/API/子进程用 tenacity 指数退避。
- 统一异常经 `ExceptionCenter` → WebSocket，便于前端呈现与排障。

---

## 10. 配置项清单（TOML）

顶层 `Settings`（`version` + `tasks[]` ≤100 + 各分区）。

| 分区 | 项（默认值） |
|---|---|
| bili_api | base_api_urls / base_live_api_urls / base_play_info_api_urls |
| header | user_agent(Chrome UA) / cookie |
| danmaku | danmu_uname(F) / record_gift_send(T) / record_free_gifts(T) / record_guard_buy(T) / record_super_chat(T) / record_toast(T) / save_raw_danmaku(F) |
| recorder | stream_format(flv) / recording_mode(standard\|raw) / quality_number(10000) / fmp4_stream_timeout(10) / read_timeout(3) / disconnection_timeout(600) / buffer_size(8192) / save_cover(T) / cover_save_strategy(dedup) |
| output | out_dir / path_template |
| postprocessing | remux_to_mp4(T) / inject_extra_metadata(T) / danmaku_to_ass(F) / ass_font_size(38) / ass_sc_font_size(38) / ass_resolution_x(1920) / ass_resolution_y(1080) |
| logging | log_dir / console_log_level(INFO) / backup_count(30) |
| space | check_interval(60) / space_threshold(1GB) / recycle_records(F) |
| task | room_id / enable_monitor(T) / enable_recorder(T) + 各分区可选覆盖(null 回退全局) |

**相较 blrec 的差异**：移除 `filesize_limit`/`duration_limit`（不切分）、`delete_source`（固定 AUTO）、全部通知/webhook/api_key 分区。默认值按本项目取舍调整（如 save_cover/remux 默认开、quality 默认原画）。

**环境变量**：`BIREC_CONFIG`/`BIREC_OUT_DIR`/`BIREC_LOG_DIR`/`BIREC_PROGRESS`/`BIREC_TRACE`/`BIREC_IPV4`/`BIREC_REC_TTL`/`BIREC_DANMAKU_PROTOCOL_VERSION`。

---

## 11. 测试策略（DT / ST 覆盖）

采用测试金字塔。**DT（Developer Test）= 单元 + 组件测试**；**ST（System Test）= 端到端/系统级测试**。工具：pytest + pytest-asyncio + pytest-cov；网络 mock 用 respx（httpx）/aioresponses（aiohttp）+ 自建 fake 服务器。

### 11.1 DT — 单元测试（`tests/unit/`）
覆盖纯逻辑与单类，全部 mock 外部 I/O：
- setting：TOML 加载/回写、env 叠加、任务级覆盖回退、别名往返、校验规则。
- bili：URL 解析（各画质/格式/编码/异常分支）、CDN 主机优选排序、WBI/App 签名、弹幕帧编解码（NORMAL/DEFLATE/BROTLI）、cookie 解析、画质名称映射。
- live_monitor：状态机去抖、事件发射序列（用假时钟/受控 Observable）。
- danmaku：XML 读写往返、控制字符清洗、合并/拼接时间基与 delta。
- path：模板渲染、转义、去重 `_(n)`、旁车派生、模板正则。
- disk_space：阈值判定、回收排序与 TTL 保护（用 tmp_path + 伪造 mtime/atime）。
- postprocess：`RemuxingResult` 分类（成功/警告/失败正则）、删源 AUTO 决策、ffmpeg 命令行拼装、`size=` 进度解析（不真跑 ffmpeg）。
- 事件模型序列化、任务模型状态推导。

### 11.2 DT — 组件测试（`tests/component/`）
在**真实 reactivex 管道**上用**合成数据**验证算子协作，不触网：
- FLV：喂入构造的 FLV 字节（fixtures），验证 parse→process（去碎片/切分/校正/修复/拼接）→Dumper 落盘正确、JoinPoint 生成、Analyser 关键帧索引、Injector 注入结果。
- HLS：用假 m3u8 + 假分片验证 PlaylistResolver 新分片跟踪、SegmentFetcher 重试/crc32、分片丢失检测。
- core.operators：注入可控异常验证 RecordingMonitor 中断/恢复、ConnectionErrorHandler 超时完成、ExceptionHandler 磁盘满/房间异常路径。
- StreamRecorder：FLV↔fMP4 回退切换逻辑（mock Live 的流可用性）。

### 11.3 ST — 系统测试（`tests/system/`）
以**假 Bilibili 服务**驱动真实全链路：
- **Fake B站服务器**（aiohttp）：提供房间/用户 API、getRoomPlayInfo、danmu_info、可控的 FLV 流端点（回放样例 FLV）、WebSocket 弹幕端点（可注入 LIVE/PREPARING/DANMU_MSG/GIFT/SC/GUARD 帧）。
- 场景：
  1. 添加任务→模拟开播→录制→模拟下播→产出视频/弹幕文件，断言文件与事件序列。
  2. 断流重连、画质回退、FLV→fMP4 回退在假服务下触发并恢复。
  3. 磁盘不足触发回收（临时小配额目录）。
  4. 后处理链路：对样例 FLV **真实调用 ffmpeg** 完成 Remux→MP4 + 弹幕→ASS，断言产物与删源（标记 `@pytest.mark.ffmpeg`，CI 安装 ffmpeg）。
- **API/WS 系统测试**：FastAPI `TestClient`/httpx `ASGITransport` 覆盖全部端点的正常/错误码路径；WebSocket 订阅收到事件；OpenAPI 契约快照测试。

### 11.4 覆盖率与门禁
- 目标：整体行覆盖 **≥ 80%**，核心模块（bili/core/flv/postprocess/task）**≥ 85%**。
- CI 中 `pytest --cov=birec --cov-report=xml --cov-fail-under=80` 作为**硬门禁**。
- 分层执行：PR 跑 DT（快）；ST（含 ffmpeg、较慢）在 `st.yml` 与合并到主干时跑。
- pytest markers：`unit`/`component`/`system`/`ffmpeg`/`slow`；`-m "not slow"` 用于快速反馈。
- 测试确定性：禁用真实时间/随机（注入时钟/种子），网络一律 mock 或走 fake 服务器。

---

## 12. CI/CD 设计（GitHub Actions）

### 12.1 触发与工作流
- `ci.yml`（PR + push 到任意分支）：质量门禁 + DT。
- `st.yml`（PR + push 到 `main`）：系统测试（安装 ffmpeg）。
- `release.yml`（打 `v*` tag）：构建 wheel + Docker 镜像并发布。

### 12.2 `ci.yml`（示意）
```yaml
name: CI
on: [push, pull_request]
jobs:
  quality:
    runs-on: ubuntu-latest
    strategy:
      matrix: { python-version: ["3.12", "3.13"] }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with: { python-version: ${{ matrix.python-version }} }
      - run: uv sync --frozen --extra dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -m "unit or component" --cov=birec --cov-report=xml --cov-fail-under=80
      - uses: codecov/codecov-action@v4   # 可选：覆盖率上报
```

### 12.3 `st.yml`（示意）
```yaml
name: System Test
on:
  pull_request:
  push: { branches: [main] }
jobs:
  system:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg
      - uses: astral-sh/setup-uv@v6
        with: { python-version: "3.12" }
      - run: uv sync --frozen --extra dev
      - run: uv run pytest -m system -v
```

### 12.4 `release.yml`（示意）
```yaml
name: Release
on:
  push: { tags: ["v*"] }
jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    permissions: { contents: write, packages: write }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv build                       # 生成 wheel/sdist
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}
      - uses: softprops/action-gh-release@v2   # 附带 wheel 到 Release
        with: { files: dist/* }
```

### 12.5 质量基线与 pre-commit
- `pre-commit`：ruff（lint+format）、mypy、末尾空白/大文件检查；与 CI 使用同一套规则，本地即拦截。
- 分支保护：`main` 要求 `ci.yml` + `st.yml` 通过、至少 1 名评审、设计文档变更需同步。
- 版本：`src/birec/__init__.py::__version__` 为准；tag `vX.Y.Z` 触发发布，语义化版本。

---

## 13. 部署

- **Docker 多阶段**：构建阶段 `uv sync` 装依赖、`uv build` 出 wheel；运行阶段基于 `python:3.12-slim`，`apt-get install ffmpeg`，装 wheel，暴露端口（默认 2233），`ENTRYPOINT ["birec"]`。
- 卷：录制输出目录、配置目录（`~/.birec`）、日志目录。
- 环境变量注入配置（见 §10）。
- 反代：支持 `--root-path` 子路径；`BaseHrefMiddleware` 处理静态资源基路径（前端阶段生效）。

---

## 14. 从 blrec 迁移说明

- **复用**：flv/hls/danmaku/bili 的解析与协议逻辑、reactivex 管道结构、路径与元数据逻辑，按新包名与 Pydantic v2 适配移植。
- **重构**：配置层由 attrs+pydantic v1 迁移到 Pydantic v2 + pydantic-settings；打包由 setuptools 迁移到 hatchling + uv；质量工具由 flake8/black/isort 迁移到 ruff。
- **裁剪**（删除代码）：`notification/`、`webhook/`、`web/security.py` 及鉴权依赖、flv/hls 的 `Cutter`/`Limiter`、postprocess 章节生成、settings 的通知/webhook/apikey/切分分支、`/cut` 与 `/validation/cookie` 端点。

---

## 15. 待细化事项（TODO，随实现推进补充）

- 路径模板变量是否精简（当前保留 11 个）。
- 录制画质默认值与前端可选档位。
- fMP4 回退超时/断线容忍/缓冲区等阈值的最终默认值与可配范围。
- OpenAPI 契约导出与前端对接节点。

---

## 变更记录

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| 0.1 | 2026-07-24 | 初稿：确立技术栈(Python+FastAPI / TOML / GitHub Actions)、架构分层、模块设计、API、并发模型、DT/ST 测试策略、CI/CD、部署与迁移说明。 |
