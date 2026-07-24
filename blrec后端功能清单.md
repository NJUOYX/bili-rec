# blrec 后端功能清单（开发目标基线）

> 本文档基于对 `blrec`（Bilibili 直播录制器，version `2.0.0-beta.5`）后端源码 `src/blrec/` 的逐模块梳理，并结合 `.qoder/repowiki` 中的仓库 Wiki 编写。
> 目的：把 blrec 现有的**全部后端功能**详细列出，作为本项目（bili-rec）后续开发的目标清单。你可在此基础上**酌情删改**功能范围。
>
> 图例：每条功能后可自行标记 —— `[保留]` / `[删除]` / `[改造]` / `[待定]`。

---

## 0. 技术栈与整体架构

- **语言/运行时**：Python ≥ 3.8，异步（asyncio + ReactiveX/`reactivex`）。
- **Web 框架**：FastAPI（`0.88.x`）+ uvicorn，Brotli 压缩，CORS。
- **配置持久化**：TOML（`toml`），Pydantic 风格模型 + 驼峰别名。
- **流处理**：自研 FLV 解析/封装 + `m3u8`（HLS），`ffmpeg`/`ffprobe`（后处理与探测）。
- **弹幕**：WebSocket 长连接（zlib/brotli 解压），lxml 生成 XML，`dmconvert`（转 ASS）。
- **日志**：loguru（按天轮转 + 保留天数）。
- **CLI**：Typer。
- **前端**：Angular（构建产物由后端作为静态资源托管，本清单不展开）。

**分层**：平台适配（B站 API）→ 流媒体处理（FLV/HLS）→ 录制引擎 → 任务与配置管理 → Web/事件/通知层。以**任务**为中心，通过**事件中心（EventCenter）+ 异常中心（ExceptionCenter）** 这一响应式总线驱动 WebSocket、通知、Webhook。

```
浏览器 → Angular 前端 → Web(FastAPI) → 任务管理器
   任务管理器 → B站直播监控 / 录制器 / 设置 / 事件中心 / 磁盘监控 / 后处理
   录制器 → FLV实现 / HLS实现 / 弹幕接收+转储 / 封面下载
   事件中心 → 通知服务 / Webhook / WebSocket
```

---

## 1. B站平台适配层（`bili/`）

### 1.1 HTTP API 客户端（`api.py`：`AppApi` / `WebApi`）
- **多域名容灾请求**：对 `base_api_urls` / `base_live_api_urls` / `base_play_info_api_urls` 逐个或并发请求，取首个成功结果。
- **WBI 签名**（Web 端）：自动在错误码 `-352` 时刷新 WBI key。
- **App 端签名**：appkey/appsec + MD5。
- **重试与退避**：tenacity（`stop_after_delay` + 指数退避）。
- **获取直播流播放信息**（`getRoomPlayInfo`）：支持协议（http_stream/http_hls）、格式（flv/ts/fmp4）、编码（avc/hevc）、杜比、画质 `qn`。
- **房间/用户信息**：`get_info_by_room`、`get_info`、`room_init`、`get_user_info`。
- **弹幕服务器信息**：`get_danmu_info`（WS 主机列表 + token）。
- **服务器时间戳**：`get_timestamp`。
- **TV 扫码登录**：`request_tv_qrcode` / `poll_tv_qrcode`。
- 可配置：请求超时（默认 10s）、请求头（UA/Referer/Cookie）。

### 1.2 直播房间抽象（`live.py`：`Live`）
- **初始化/刷新**：加载房间+用户信息，探测是否存在 FLV 流。
- **直播状态查询**：API 查询 + HTML 页面兜底解析。
- **连通性检测**：HEAD 请求。
- **流地址解析**：按格式/编码/画质选择，校验可用性并抛出精确异常（无流/无该格式/无该编码/无该画质/无备用线路）。
- **CDN 主机优选**：优先 `gotcha` 系列主机，降权 `mcdn`、`cn-*`。
- **备用线路选择**：`select_alternative`。
- **房间状态检测**：隐藏 / 锁定 / 加密房间的异常识别。
- 属性热切换：UA、Cookie、各类 base API 地址。

### 1.3 直播事件监控（`live_monitor.py`：`LiveMonitor`）— 事实上的"自动调度器"
- **自动开播/关播/轮播/换房事件**：解析弹幕命令 `LIVE`/`PREPARING`/`ROUND`/`ROOM_CHANGE`。
- **状态去抖**：首个 LIVE→开播；连续多次 LIVE→流重置（`live_stream_reset`）。
- **流可用性轮询**：开播后每秒轮询（最长 30 分钟），触发 `on_live_stream_available`。
- **定时状态轮询兜底**：约每 600s（±60 抖动）复查，防止漏事件。
- **断线重连状态修复**：重连后复查状态并补发开播/关播/重置事件（应对休眠等）。

### 1.4 弹幕 WebSocket 客户端（`danmaku_client.py`：`DanmakuClient`）
- **WS 长连接**：`wss://…/sub`，携带 uid/roomid/buvid/token/protover 握手鉴权。
- **协议解码**：支持 NORMAL(0) / DEFLATE(2, zlib) / BROTLI(3)；可由环境变量 `BLREC_DANMAKU_PROTOCOL_VERSION` 控制。
- **心跳保活**：每 30s。
- **自动重连**：主机列表轮换、`max_retries`（默认 60）、指数退避、耗尽主机后刷新弹幕信息。
- **消息分发**：向监听器广播原始弹幕字典。
- **cookie 解析**：提取 uid/buvid。
- 支持 cookie/UA 变更后的重启。

### 1.5 数据模型与辅助
- **模型**：`LiveStatus`、`RoomInfo`（含标题/分区/封面/标签/描述，HTML 清洗）、`UserInfo`。
- **画质名称映射**：20000=4K、10000=原画、401=蓝光杜比、400=蓝光、250=超清、150=高清、80=流畅。
- **类型**：`QualityNumber`、`StreamFormat`(flv/ts/fmp4)、`StreamCodec`(avc/hevc)、`ApiPlatform`(web/android)。
- 二维码登录、Cookie 拼装、共享 aiohttp 连接器等辅助。

---

## 2. 录制协调层（`core/`）

### 2.1 录制总协调器（`recorder.py`：`Recorder`）
- **自动开始/停止录制**：响应监控事件（开播→启动、关播→停止、流可用→启动流录制、流重置→重启）。
- **文件生命周期事件聚合**：录制开始/完成/取消、视频文件创建/完成、弹幕文件创建/完成、原始弹幕文件创建/完成、封面下载完成。
- **手动切割**：`can_cut_stream` / `cut_stream`。
- **录制文件枚举**：视频/弹幕文件列表。
- **实时统计透传**：下载总量/速率、录制时长/速率、弹幕总量/速率。
- 构造子组件：流录制器、弹幕接收+转储、原始弹幕接收+转储、封面下载器。

### 2.2 流录制器门面（`stream_recorder.py`）
- **格式自动回退**：
  - 无 FLV 流且选 flv → 回退 fmp4；
  - 选 fmp4 时等待 fmp4 可用（`fmp4_stream_timeout`），超时 → 回退 flv；
  - 实现热切换（保留可用时间戳）。
- **内存回收**（`malloc_trim`）。
- 追踪真实流格式、真实画质、流可用时间。
- 独立线程运行 Rx 管道，按房间绑定日志上下文。

### 2.3 FLV 录制实现（`flv_stream_recorder_impl.py`）
- 构建 FLV Rx 管道：`解析流地址 → 拉流 → 录制监控 → 统计 → 解析 → 连接/请求异常处理 → FLV处理(排序) → 切割 → 限制 → 连接点提取 → 探测 → 注入 → 分析 → 落盘 → 统计 → 进度条 → 异常处理`。
- 元数据落盘（关键帧 + 连接点）。

### 2.4 HLS/fMP4 录制实现（`hls_stream_recorder_impl.py`）
- 构建 HLS Rx 管道：`解析流地址 → 拉取播放列表 → 录制监控 → 异常处理 → 解析新分片 → 独立下载线程 → 拉取分片 → 统计 → 探测 → 分析 → 切割 → 限制 → 分片落盘 → 统计 → 进度条 → 播放列表落盘`。
- 分片元数据 JSON 落盘。

### 2.5 弹幕接收与写入
- **弹幕接收器**（`DanmakuReceiver`）：解析 `DANMU_MSG`/`SEND_GIFT`/`GUARD_BUY`/`SUPER_CHAT_MESSAGE`/`USER_TOAST_MSG` 为类型化消息；有界队列（2000，溢出丢旧）。
- **弹幕转储器**（`DanmakuDumper`）：
  - 按视频文件写 XML，含元数据头（录制器/房间/用户/标题/分区/时间）。
  - **礼物 / 免费礼物 / 上舰 / 醒目留言 / 用户提示** 记录开关。
  - **弹幕含用户名** 开关。
  - **时间轴校正**：对齐录制起始时间，处理中断/恢复偏移。
  - HTML 转义、失败重试（3 次）、每分钟弹幕统计。
- **原始弹幕接收/转储**：逐条写原始 JSON 行（`save_raw_danmaku`）。

### 2.6 封面下载（`cover_downloader.py`）
- **封面图下载**（视频完成时触发）。
- **去重策略**（DEFAULT / DEDUP，sha1 去重）。
- 重试 + 刷新房间信息取最新封面。

### 2.7 支撑组件
- **元数据提供器**：构建视频元数据（主播/标题/分区/房间号/开播时间/推流时间/录播起始/流主机/流格式/流画质/程序版本，时区 +8）。
- **路径提供器**：按模板渲染输出路径，转义非法字符、自动建目录、自动去重 `_(n)`。
- **流参数持有者**：画质回退、API 平台轮换、备用流开关。
- **统计器**：速率/计数/耗时。

### 2.8 录制管道算子（`core/operators/`）
- **StreamURLResolver**：解析+缓存流地址，HEAD 复用有效 URL，画质回退，多次失败后触发状态复查。
- **StreamFetcher**：HTTP 流式拉取（`read_timeout`）。
- **StreamParser**：封装 FLV 解析，出错重试/切备用流。
- **RecordingMonitor**：检测录制中断/恢复。
- **ConnectionErrorHandler**：连接错误时等待至 `disconnection_timeout`（默认 600s）复查连通性。
- **RequestExceptionHandler / ExceptionHandler**：请求异常重试；磁盘满/房间隐藏锁定加密时优雅完成。
- **ProgressBar**：tqdm 进度（`BLREC_PROGRESS`）。
- **StreamStatistics / SizedStatistics**：下载速率与总量。

---

## 3. FLV 引擎（`flv/`）

- **低层工具**：模型（Header/Tag/Audio/Video/Script）、`io`（读写）、`avc`、`amf`、`scriptdata`、`format`。
- **管道算子**（`flv/operators/`）：
  - `parse`：解析 FLV 流（可配 `ignore_eof`/`complete_on_eof`/时间戳备份恢复）。
  - `process`：`去碎片 → 切分 → [排序] → 过滤 → 校正 → 修复 → 拼接`。
    - **去碎片**：丢弃碎片流；**切分**：AV 参数变化时切；**GOP 排序**；**时间戳校正/修复**；**无缝拼接**（生成 JoinPoint，含 crc32/时间戳）。
  - `Cutter`：手动切流（关键帧对齐，重插头/元数据/序列头）。
  - `Limiter`：按大小/时长自动切分（关键帧感知，预测式）。
  - `Analyser`：分析生成 MetaData（分辨率/时长/关键帧索引，yamdi 风格）。
  - `Injector`：注入/丰富元数据。
  - `Prober`：ffprobe 探测 → StreamProfile。
  - `JoinPointExtractor`、`Dumper`（文件开合、大小/时间戳事件）、`ProgressBar`。
  - 元数据落盘 / 分析 / 注入（后处理复用）。

---

## 4. HLS 引擎（`hls/`）

- **管道算子**（`hls/operators/`）：
  - `PlaylistFetcher`：拉取 m3u8。
  - `PlaylistResolver`：仅产出新分片（按媒体序列号跟踪）。
  - `SegmentFetcher`：下载 init 段 + 媒体分片，重试、损坏检测、crc32 校验。
  - `SegmentDumper`：写 fMP4 文件（开合事件、大小跟踪、ffprobe）。
  - `PlaylistDumper`：维护时长/序列，检测**分片丢失**。
  - `Cutter`：按播放列表时长手动切流。
  - `Limiter`：按大小/时长切分（分片时长预测）。
  - `Prober` / `Analyser`：探测与元数据生成。
  - 分片元数据 JSON 落盘。

---

## 5. 任务管理系统（`task/`）

> 无基于时间的调度器；"调度"= 事件驱动的自动开停 + 手动/API 控制。

### 5.1 单房间录制任务（`task.py`：`RecordTask`）
- **组合**：`Live` + `DanmakuClient` + `LiveMonitor` + `Recorder` + `Postprocessor` + 事件提交器。
- **生命周期**：`setup` / `destroy`。
- **监控开关**：启/停（含弹幕客户端 + 直播监控）。
- **录制开关**：启/停（含后处理器 + 录制器；停止支持 `force` 控制顺序）。
- **运行状态机**：STOPPED / WAITING / RECORDING / REMUXING / INJECTING。
- **信息刷新 / 弹幕客户端重启**（cookie/UA 变更）。
- **手动切流**。
- **文件明细**：视频文件（录制中/混流中/注入中/已完成/缺失/未知）、弹幕文件（含 mp4/xml 回退路径）。
- 暴露约 40 个可热更新属性，覆盖 API 地址、请求头、弹幕、录制、输出、后处理选项。

### 5.2 任务管理器（`task_manager.py`：`RecordTaskManager`）
- **加载全部任务**（从配置）；**添加任务**（重试 + 应用各类设置 + 可选自动启用监控/录制，失败回滚）。
- **移除任务 / 移除全部**（强制停用 + 销毁 + 内存回收）。
- **启动/停止任务（单个/全部）**。
- **监控/录制粒度控制**（单个/全部）。
- **查询**：任务数据、参数、元数据、流 Profile、视频文件明细、弹幕文件明细。
- **切流**（按房间）。
- **信息更新**（单个/全部）。
- **设置应用**：bili_api / header（UA/cookie 变更重启弹幕客户端）/ output / danmaku / recorder / postprocessing。

### 5.3 任务数据模型（`models.py`）
- `RunningStatus`、`TaskStatus`（监控/录制开关、运行状态、流地址/主机、下载/录制/弹幕统计、真实格式/画质、录制路径、后处理状态/路径/进度）。
- `TaskParam`（全部配置快照）、`TaskData`（用户+房间+任务状态）、文件状态与明细模型。

---

## 6. Web 服务层（`web/`）

### 6.1 应用装配（`main.py`）
- 加载 `Settings`（TOML，`BLREC_CONFIG` / `~/.blrec/settings.toml`），叠加环境变量。
- **可选 API-Key 鉴权**：设 `BLREC_API_KEY` 时全路由 `Depends(authenticate)`。
- 中间件：`BaseHrefMiddleware`、`BrotliMiddleware`、`CORSMiddleware`（放行 `http://localhost:4200`）、`RouteRedirectMiddleware`。
- 异常映射：NotFound→404、Forbidden→403、Exists→409、Validation→406；统一响应体 `{code,message,data}`。
- 生命周期：启动→`app.launch()`；关闭→保存设置 + `app.exit()`。
- SPA 静态托管（`/`），`.js` 强制 MIME，404 回退 `index.html`。

### 6.2 中间件
- **BaseHrefMiddleware**：反代子路径部署时重写 `<base href>`。
- **RouteRedirectMiddleware**：前端路由（`/tasks|/settings|/about`）301 回 `/`。

### 6.3 安全（`security.py`）
- 请求头 `X-API-Key`；缺失→401。
- **按客户端 IP 的暴力破解防护**：白/黑名单，尝试计数；3 次错误→黑名单（403）；`secrets.compare_digest` 常量时间比较；成功加白名单。
- API key 正则 `[a-zA-Z\d\-]{8,80}`。

### 6.4 REST API 端点（前缀 `/api/v1`）

#### 任务 `/tasks`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/tasks/data` | 分页列出所有任务数据（`page`/`size`/`select` 过滤） |
| GET | `/tasks/{room_id}/data` | 单任务数据 |
| GET | `/tasks/{room_id}/param` | 任务参数 |
| GET | `/tasks/{room_id}/metadata` | 录制元数据 |
| GET | `/tasks/{room_id}/profile` | 当前流 ffprobe Profile |
| GET | `/tasks/{room_id}/videos` | 视频文件明细 |
| GET | `/tasks/{room_id}/danmakus` | 弹幕文件明细 |
| POST | `/tasks/info` / `/tasks/{room_id}/info` | 刷新全部/单个任务信息 |
| GET/POST | `/tasks/{room_id}/cut` | 查询是否可切流 / 触发切流 |
| POST | `/tasks/start` / `/tasks/{room_id}/start` | 启动全部/单个 |
| POST | `/tasks/stop` / `/tasks/{room_id}/stop` | 停止全部/单个（`force`/`background`） |
| POST | `/tasks/recorder/enable` / `/tasks/{room_id}/recorder/enable` | 启用录制器 |
| POST | `/tasks/recorder/disable` / `/tasks/{room_id}/recorder/disable` | 停用录制器（`force`/`background`） |
| POST | `/tasks/{room_id}` | 添加任务（支持短号，返回真实房号） |
| DELETE | `/tasks` / `/tasks/{room_id}` | 删除全部/单个 |

任务过滤维度：全部 / 直播状态（preparing/living/rounding）/ 任务状态（监控启停、录制启停）/ 运行状态（stopped/waiting/recording/remuxing/injecting）。

#### 设置 `/settings`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/settings` | 获取全局设置（`include`/`exclude` 键集） |
| PATCH | `/settings` | 修改全局设置（改请求头会重连所有弹幕客户端） |
| GET | `/settings/tasks/{room_id}` | 获取任务级选项 |
| PATCH | `/settings/tasks/{room_id}` | 修改任务级选项（置 null 则回退全局） |

#### 应用 `/app`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/app/status` | 运行状态 |
| GET | `/app/info` | 应用信息（版本等） |
| POST | `/app/restart` | 重启应用 |
| POST | `/app/exit` | 退出（发 SIGINT） |

#### 扫码登录 `/qrcode`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/qrcode/login` | 请求 TV 登录二维码（url + auth_code） |
| POST | `/qrcode/login/poll` | 轮询登录，成功后写入 cookie 设置 |

#### 校验 `/validation`
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/validation/dir` | 校验目录存在且可读写 |
| POST | `/validation/cookie` | 通过 nav API 校验 cookie |

#### 更新 `/update`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/update/version/latest` | 最新发布版本号 |

### 6.5 WebSocket 端点
| 路径 | 说明 |
|---|---|
| `WS /ws/v1/events` | 推送所有应用事件（EventCenter 流） |
| `WS /ws/v1/exceptions` | 推送格式化异常（ExceptionCenter 流） |

---

## 7. 事件与通知

### 7.1 事件中心 / 异常中心
- 单一响应式总线，同时供给 WebSocket、通知器、Webhook。
- 事件序列化：`{type, id(uuid1), date(UTC+8 ISO), data}`。

### 7.2 事件类型与载荷（`event/models.py`）
| 事件 | 载荷 |
|---|---|
| LiveBegan / LiveEnded | user_info, room_info |
| RoomChange | room_info |
| RecordingStarted / Finished / Cancelled | room_info |
| VideoFileCreated / Completed | room_id, path |
| DanmakuFileCreated / Completed | room_id, path |
| RawDanmakuFileCreated / Completed | room_id, path |
| CoverImageDownloaded | room_id, path |
| VideoPostprocessingCompleted | room_id, path |
| PostprocessingCompleted | room_id, files[] |
| SpaceNoEnough | path, threshold, usage |
| Error | name, detail |

### 7.3 通知系统（`notification/`）
**渠道（provider）**：
| 渠道 | 传输 | 配置 | 消息类型 |
|---|---|---|---|
| 邮件 Email | SMTP over SSL（回退 STARTTLS） | src/dst/auth_code/smtp_host(默认 163)/port(465) | text/html |
| ServerChan | POST sctapi.ftqq.com | sendkey | markdown |
| PushDeer | POST pushdeer | server/pushkey | text/markdown |
| PushPlus | POST pushplus.plus | token/topic | text/markdown/html |
| Telegram | POST bot sendMessage | token/chatid/server | markdown/html |
| Bark | POST day.app | server/pushkey | text/markdown |

**触发事件**（各自可开关）：
| 开关 | 触发 |
|---|---|
| notify_began | 开播 |
| notify_ended | 下播 |
| notify_space | 磁盘空间不足 |
| notify_error | 任意异常 |

> 通知器**不**响应录制/文件/后处理事件（这些只走 Webhook）。

**模板**：Liquid 模板引擎，自定义过滤器（intcomma/naturalsize/datetimestring），内置模板兜底（began/ended/space/error 各含 markdown/html/text）；异步发送 + tenacity 重试（`stop_after_delay(300)`，配置错误不重试）。

### 7.4 Webhook 系统（`webhook/`）
- 每个 Webhook：一个 `url` + 17 个事件开关（默认全开）+ 是否接收异常。
- **WebHookEmitter**：事件匹配则 POST `event.asdict()` JSON；异常 POST 错误载荷；`User-Agent: {prog}/{version}`；tenacity 重试（`stop_after_delay(180)`）+ `raise_for_status`。
- 支持的事件开关：live_began/ended、room_change、recording_started/finished/cancelled、video_file_created/completed、danmaku_file_created/completed、raw_danmaku_file_created/completed、cover_image_downloaded、video_postprocessing_completed、postprocessing_completed、space_no_enough、error_occurred。

---

## 8. 后处理系统（`postprocess/`）

核心 `Postprocessor`：队列驱动的异步 worker，**全局仅并发 1 个后处理任务**（跨所有房间）。

- **Remux FLV → MP4**：`ffmpeg -codec copy`（不重编码）+ 元数据注入。
- **Remux HLS/fMP4(.m4s) → MP4**：经生成的 m3u8 播放列表混流。
- **移除 filler NAL 单元**（remux 时固定开启 `-bsf:v filter_units=remove_types=12`）。
- **FFmpeg 元数据文件注入**：Title/Artist/Date/Description(JSON)/Comment。
- **章节生成**：
  - FLV：按连接点（非无缝处）切章节。
  - HLS：按播放列表 discontinuity 生成章节。
- **FLV 额外元数据注入**（不 remux 时）：直接注入 FLV；关键帧丢失时重新分析恢复。
- **FLV 有效性检查**：无效且 < 1MB 则跳过。
- **质量检查/结果分类**：成功 / 警告（Non-monotonous DTS）/ 失败（返回码非 0 或命中错误关键词 error|missing|invalid|corrupt|illegal|overflow|out of range）。
- **删除源文件策略**（`DeleteStrategy`）：
  - `AUTO`：除失败外都删；
  - `SAFE`：非失败且非警告才删；
  - `NEVER`：从不删。
  - m4s 场景连带删除 .m4s/.m3u8/.meta.json/.meta；调试模式不删。
- **中间元数据文件清理**（.meta.json / .meta）。
- **弹幕 XML → ASS 字幕**（`dmconvert`）：可配字体大小、SC 字体大小、分辨率 X/Y。
- **进度上报**：从 ffmpeg `size=` 实时解析；状态 WAITING/REMUXING/INJECTING。
- **相关文件跟踪**：.xml/.ass/.jsonl/.jpg/.png/.m3u8，完成后发 `postprocessing_completed`。

---

## 9. 磁盘空间监控与回收（`disk_space/`）

- **周期性剩余空间轮询**（`check_interval`，默认 60s）。
- **阈值检测**（`space_threshold`，默认 1GB），不足时发 `space_no_enough`（含 total/used/free 快照）。
- **自动清理**（`SpaceReclaimer`，需开启 `recycle_records`）：
  - 扫描录制目录（限定后缀 .flv/.mp4/.ts/.m4s/.m3u8/.xml/.json/.meta/.jsonl/.jpg/.png）。
  - **按 mtime/atime 升序删除最旧文件**直至空间足够。
  - **TTL 保护**（`rec_ttl`，默认 24h，可由 `BLREC_REC_TTL` 覆盖）：只删 mtime 与 atime 均超过 TTL 的文件。
  - `OSError` 重试（3 次）。
- `check_interval <= 0` 自动禁用监控。

---

## 10. 弹幕文件工具（`danmaku/`）

- **DanmakuWriter / DanmakuReader**：读写 B站兼容的弹幕 XML（含 `<metadata>`、`<d>`、`<toast>`、`<gift>`、`<guard>`、`<sc>`；控制字符清洗；金/银瓜子序列化）。
- **合并/拼接工具**：
  - `DanmakuCombinator`：多文件合并，按共同时间基（LIVE / RECORD）重定时。
  - `DanmakuConcatenator`：按各自 delta 偏移拼接。
  - `merge_danmaku`：src 合并进 dst（前插/后接），清空 src 并原子替换 dst。
  - `has_danmu` / `clear_danmu` / `copy_damus` 等辅助。

---

## 11. 路径模板与文件命名（`path/` + `core/path_provider.py`）

- **旁车文件路径派生**（按后缀切换）：.xml（弹幕）、.ass、.jsonl（原始弹幕）、.m3u8、.m4s、.jpg/.png（封面）、.meta.json（额外/记录元数据）、.meta（ffmpeg 元数据）。
- **非法字符转义** `escape_path`（去 `\ / : * ? " < > |`）。
- **路径模板变量**：`{roomid} {uname} {title} {area} {parent_area} {year} {month} {day} {hour} {minute} {second}`。
- 默认模板：`{roomid} - {uname}/blive_{roomid}_{year}-{month}-{day}-{hour}{minute}{second}`。
- **自动去重**：文件已存在时追加 `_(1)`、`_(2)`…
- 模板校验正则（仅允许已知变量，禁止非法字符）。

---

## 12. 版本检查（`update/`）

- **PyPI 查询**（`pypi.org/pypi`）：项目/发行版元数据，指数退避重试，超时返回 None。
- `get_latest_version_string`：读取 PyPI `info.version`。
- Web 暴露 `GET /api/v1/update/version/latest`；仅**检查最新版本**，后端不自动下载/安装。

---

## 13. 日志系统（`logging/`）

- **loguru** 配置：
  - 控制台：级别可配（默认 INFO），彩色格式含 `{room_id}`。
  - 文件：DEBUG（`BLREC_TRACE` 时 TRACE），异步，**每日 00:00 轮转**，保留 `backup_count` 天，含 backtrace/diagnose。
- **TqdmOutputStream**：日志与进度条不打架。
- **按房间日志上下文**：`logger.contextualize(room_id=...)`。

---

## 14. 命令行接口（`cli/`）

单命令（Typer）启动 FastAPI/uvicorn。选项：

| 选项 | 默认 | 说明 |
|---|---|---|
| `--version` | | 打印版本 |
| `-c/--config` | | 配置文件路径 → `BLREC_CONFIG` |
| `-o/--out-dir` | | 输出目录 → `BLREC_OUT_DIR` |
| `--log-dir` | | 日志目录 → `BLREC_LOG_DIR` |
| `--progress/--no-progress` | True | 进度条 → `BLREC_PROGRESS` |
| `--host` | localhost | 绑定地址 |
| `--port` | 2233 | 端口 |
| `--open` | False | 打开浏览器 |
| `--ipv4` | False | 仅 IPv4 → `BLREC_IPV4` |
| `--root-path` | '' | ASGI root path（反代） |
| `--key-file`/`--cert-file` | | HTTPS 证书 |
| `--api-key` | | Web API key → `BLREC_API_KEY` |

- uvicorn：`proxy_headers=True`、`forwarded_allow_ips='*'`、`access_log=False`。
- `main()` 捕获 KeyboardInterrupt/SystemExit（返回 1）与异常（返回 2）。

---

## 15. 配置项总表（`setting/models.py`）

**全局 `Settings`（TOML，版本 1.0）** 顶层：`tasks[]`(≤100)、`output`、`logging`、`bili_api`、`header`、`danmaku`、`recorder`、`postprocessing`、`space`、六类通知、`webhooks[]`(≤50)。

| 分区 | 关键项（默认值） |
|---|---|
| **BiliApi** | base_api_urls / base_live_api_urls / base_play_info_api_urls |
| **Header** | user_agent（Chrome UA）、cookie |
| **Danmaku** | danmu_uname(False)、record_gift_send(T)、record_free_gifts(T)、record_guard_buy(T)、record_super_chat(T)、save_raw_danmaku(F) |
| **Recorder** | stream_format(flv)、recording_mode(standard/raw)、quality_number(20000)、fmp4_stream_timeout(10)、read_timeout(3)、disconnection_timeout(600)、buffer_size(8192)、save_cover(F)、cover_save_strategy(default) |
| **Output** | out_dir、path_template、filesize_limit(0=无限)、duration_limit(0=无限) |
| **Postprocessing** | remux_to_mp4(F)、inject_extra_metadata(T)、delete_source(AUTO)、danmaku_to_ass(F)、ass_font_size(38)、ass_sc_font_size(38)、ass_resolution_x(1920)、ass_resolution_y(1080) |
| **Logging** | log_dir、console_log_level(INFO)、backup_count(30) |
| **Space** | check_interval(60)、space_threshold(1GB)、recycle_records(F) |
| **Task** | room_id、enable_monitor(T)、enable_recorder(T) + 各分区可选覆盖（置 null 回退全局） |
| **Notification（每渠道）** | 渠道字段 + enabled(F) + 4 类开关 + 消息模板（类型/标题/内容） |
| **WebHook** | url + 17 事件开关(默认全开) |

**环境变量**：`BLREC_CONFIG`、`BLREC_API_KEY`、`BLREC_OUT_DIR`、`BLREC_LOG_DIR`、`BLREC_IPV4`、`BLREC_PROGRESS`、`BLREC_TRACE`、`BLREC_REC_TTL`、`BLREC_DANMAKU_PROTOCOL_VERSION`。

---

## 16. 健壮性特性汇总（跨模块）

- 格式自动回退（flv ↔ fmp4）、画质回退（→ 原画）、备用 CDN 线路、流 URL 复用。
- 断线容忍（默认 600s）、断线重连状态修复、请求重试与退避。
- 磁盘满优雅完成、磁盘不足自动清理（TTL 保护）。
- FLV 去碎片、时间戳校正/修复、无缝拼接（连接点）。
- 每文件元数据落盘（供后处理）、后处理全局串行（避免资源争用）。
- 弹幕异步有界队列（溢出丢旧，不阻塞录制）。
- API Key 鉴权 + IP 暴力破解防护。

---

## 附：最终功能范围（决策记录）

> 经四轮逐项确认，本项目（bili-rec）后端开发目标如下。上文第 1–16 节为 blrec 全量能力参考；下表为**实际取舍**，与上文冲突处以本表为准。

### ✅ 保留（开发目标）

| 领域 | 保留内容 | 备注 |
|---|---|---|
| **录制格式** | FLV + fMP4 自动回退 | 保留 flv↔fmp4 回退；fMP4 复用 HLS 分片管道所需部分 |
| **直播监控/自动开停** | 弹幕事件驱动开播/关播/换房、流可用轮询、定时兜底、断线重连状态修复 | 核心 |
| **弹幕 WS 客户端** | 长连接、协议解码(zlib/brotli)、心跳、自动重连 | 核心 |
| **弹幕记录类型** | 普通弹幕、礼物(含免费礼物)、SC、上舰、用户提示 Toast | |
| **弹幕附加** | 原始弹幕 JSONL、弹幕含用户名 | |
| **弹幕文件** | XML 读写、时间轴校正、合并/拼接工具 | |
| **封面下载** | 下载 + sha1 去重 | |
| **后处理** | Remux 转 MP4、FLV 元数据注入、弹幕转 ASS 字幕 | 删源策略固定 **AUTO** |
| **磁盘管理** | 空间监控 + 自动回收（删最旧，带 TTL 保护） | |
| **实时推送** | WebSocket 事件 + 异常推送（供前端实时 UI） | 保留事件中心/异常中心 |
| **任务管理** | 任务增删改查、生命周期、状态机、监控/录制粒度控制 | |
| **任务配置** | 支持**任务级覆盖全局**（null 回退全局） | |
| **登录** | TV 扫码登录（自动写入 cookie） | Cookie 仍是基础设置项 |
| **健壮性** | 多域名容灾、画质自动回退、备用 CDN 线路、断线重连修复 | 全保留 |
| **辅助端点** | 目录校验、应用重启/退出、版本检查(PyPI) | |
| **基础设施** | 设置持久化(TOML)、日志系统(loguru)、路径模板、CLI(全部选项) | CLI 含 HTTPS/root-path/IPv4/open |

### ❌ 移除（不做）

| 领域 | 移除内容 | 影响 |
|---|---|---|
| **通知系统** | 全部 6 渠道(Email/ServerChan/PushDeer/PushPlus/Telegram/Bark) + notify_* 开关 + 消息模板 | 删除 `notification/`、6 个通知配置分区 |
| **Webhook** | WebHookEmitter + 17 事件开关 | 删除 `webhook/`、`webhooks[]` 配置 |
| **Web 鉴权** | API Key 校验 + IP 防爆破 | 删除 `security.py`、`api_key` 配置、`X-API-Key` |
| **文件切分** | 按大小/时长自动切分(Limiter) | 删除 `filesize_limit`/`duration_limit` 配置 |
| **手动切流** | Cutter + `/tasks/{id}/cut` 端点 | 一场直播输出单文件 |
| **后处理章节** | FLV 连接点/HLS 断点章节生成 | Remux 时不生成章节 |
| **纯 HLS/ts 全支持** | 独立完整 HLS/ts 录制（仅保留 fMP4 回退所需） | 录制格式收敛为 FLV+fMP4 |
| **Cookie 校验端点** | `/validation/cookie` | 保留目录校验 |

### 待细化（后续开发时再定）

- 路径模板变量集合（当前默认 11 个变量是否精简）。
- 录制画质默认值与可选档位（4K/原画/…）。
- 日志保留天数、控制台级别默认值。
- fMP4 回退超时、断线容忍时长等阈值默认值。
