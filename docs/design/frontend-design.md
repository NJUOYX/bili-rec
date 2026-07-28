# bili-rec 前端设计文档

## 文档信息

| 项 | 值 |
|---|---|
| 版本 | 0.2 |
| 状态 | **进行中（前端开发阶段已启动）** |
| 最近更新 | 2026-07-28 |

> 本文档与 [backend-design.md](./backend-design.md) 对齐，消费其导出的 API 契约 [openapi.json](./openapi.json)。契约为唯一事实来源；前端不得假设文档以外的字段或端点。

---

## 1. 概述

### 1.1 项目定位

bili-rec 的 Web 前端，为录制核心提供可视化管理界面：任务管理（增删改查、启停、录制器开关）、全局/任务级设置、扫码登录、磁盘/应用状态与实时事件展示。以单页应用（SPA）形态构建，由后端 FastAPI 以静态资源方式托管（见 §13）。

### 1.2 设计目标

- **契约驱动**：所有类型与请求由 `openapi.json` 自动生成，杜绝手写漂移。
- **实时优先**：任务运行态、下载/录制速率、后处理进度通过 WebSocket 事件驱动刷新，无需轮询。
- **可反代**：支持子路径部署（`<base href>` + SPA 路由回退），与后端 `BaseHrefMiddleware`/`RouteRedirectMiddleware` 协同。
- **可测试**：DT（组件/hook）+ ST（E2E）分层覆盖，CI 硬门禁。

### 1.3 非目标（本阶段不做）

- 移动端原生适配（仅响应式桌面优先）。
- 国际化多语言（预留结构，先中文）。
- 鉴权/多用户（后端已裁剪 security；单实例本地/内网使用）。
- 通知/webhook 配置界面（后端已裁剪对应能力）。

---

## 2. 技术栈选型

选型原则：与后端「取当时最新稳定版」一致，优先契约驱动、类型安全、生态成熟。

| 领域 | 选型 | 说明 |
|---|---|---|
| 语言 | TypeScript 5.x（`strict`） | 全量类型，禁用 `any` 逃逸 |
| 框架 | React 19 | 函数组件 + Hooks |
| 构建 | Vite 7 | 开发 HMR、生产 Rollup 打包 |
| 包管理 | pnpm | 锁定 `pnpm-lock.yaml` |
| 路由 | React Router 7（data router） | SPA 客户端路由 |
| 服务端状态 | TanStack Query v5 | 缓存/失效/重试，配合 WS 事件驱动失效 |
| 客户端状态 | Zustand | 轻量全局 UI 状态（连接状态、筛选器、主题） |
| HTTP/类型 | `openapi-typescript` + `openapi-fetch` | 由契约生成类型与类型安全客户端（§5） |
| UI 组件库 | Ant Design 5 | 表格/表单/抽屉/通知齐备，契合后台管理形态 |
| 图表 | 轻量 sparkline（按需，如 `@ant-design/plots` 或自绘 SVG） | 速率曲线，非首版必需 |
| 单元/组件测试 | Vitest + React Testing Library | 与 Vite 同源，快 |
| 接口 Mock | MSW（Mock Service Worker） | DT 阶段拦截 HTTP/WS，复用契约 |
| E2E 测试 | Playwright | 对接后端 fake 服务或真实后端 |
| 代码质量 | ESLint（typescript-eslint）+ Prettier | 与后端 ruff 对等的本地/CI 双门禁 |
| Git 钩子 | pre-commit（复用仓库现有配置）/ lint-staged | 提交即拦截 |

> 具体次版本号在 `package.json` 落地时取当时最新稳定版；本表锁定主版本与选型决策。

---

## 3. 架构与目录布局

单向数据流：**UI 组件 → hooks（TanStack Query / Zustand）→ 类型安全 API 客户端 → 后端**；实时事件反向：**WebSocket → 事件分发 → 使 Query 缓存失效/局部更新 → UI 刷新**。

```
frontend/
├── package.json
├── pnpm-lock.yaml
├── vite.config.ts
├── tsconfig.json
├── index.html                 # 含 <head>，供 BaseHrefMiddleware 注入 <base>
├── openapi.json               # 从 ../docs/design/openapi.json 同步的契约副本
├── scripts/
│   └── check-openapi-drift.ts # 校验本地契约与后端导出一致
├── src/
│   ├── main.tsx               # 应用入口，挂载 Router/QueryClient/AntdConfig
│   ├── app/
│   │   ├── router.tsx         # 路由表
│   │   ├── queryClient.ts     # TanStack Query 配置
│   │   └── providers.tsx      # 全局 Provider 组合
│   ├── api/
│   │   ├── schema.d.ts        # openapi-typescript 生成（勿手改）
│   │   ├── client.ts          # openapi-fetch 客户端 + ResponseMessage 拆包
│   │   └── endpoints/         # 按域封装的 hooks（tasks/settings/app/...）
│   ├── ws/
│   │   ├── useEventStream.ts  # /ws/v1/events 订阅 hook
│   │   ├── useExceptionStream.ts
│   │   └── reconnect.ts       # 指数退避重连 + 心跳处理
│   ├── stores/                # Zustand（连接状态、筛选、主题）
│   ├── pages/
│   │   ├── tasks/             # 任务列表 + 详情
│   │   ├── settings/          # 全局/任务级设置
│   │   ├── login/            # 扫码登录
│   │   └── about/             # 状态/版本/关于
│   ├── components/            # 通用组件（TaskCard/StatusBadge/RateGauge...）
│   └── lib/                   # 工具（格式化、单位换算、常量）
└── tests/
    ├── unit/                  # Vitest + RTL
    └── e2e/                   # Playwright
```

> 目录 `frontend/` 位于仓库根，与 `src/birec/` 并列；产物构建后由后端托管（§13）。

---

## 4. 与后端契约对接

- **基地址**：所有 REST 端点前缀 `/api/v1`；开发期通过 Vite `server.proxy` 将 `/api` 与 `/ws` 代理到后端（默认 `http://127.0.0.1:2233`）。
- **统一响应体**：后端返回 `ResponseMessage{ code:int=0, message:str, data?:object }`。客户端在 `api/client.ts` 统一拆包：`code !== 0` 抛出携带 `message` 的错误；成功则返回 `data`。
- **分页**：`GET /tasks/data` 接受 `page`/`size`/`select`，前端筛选器（all / 直播状态 / 任务状态 / 运行状态）映射为 `select` 参数。
- **错误码**：`404`/`403` 由后端异常处理器返回统一体；前端据 `code` 分类为「未找到 / 禁止 / 业务错误 / 网络错误」并弹 toast。
- **契约冻结点**：以 `openapi.json` 的 `info.version`（当前 `0.1.0`）为对接基线；后端契约变更须走 PR 并重新生成前端类型（§5）。

---

## 5. TypeScript 类型自动生成方案

**目标**：REST 请求路径、方法、参数、请求体、响应体全部由 `openapi.json` 派生，编译期即校验，禁止手写接口类型。

### 5.1 生成链路

1. `openapi-typescript` 读取 `openapi.json` → 生成 `src/api/schema.d.ts`（含 `paths` / `components.schemas` 全量类型）。
2. `openapi-fetch` 以 `schema.d.ts` 为泛型参数创建**类型安全客户端**：路径、method、`params`、`body`、`response` 全部受检。
3. 领域 hooks（`api/endpoints/*`）在客户端之上封装 TanStack Query 的 `useQuery`/`useMutation`，导出语义化 hook（如 `useTasks`、`useStartTask`、`useSettings`）。

### 5.2 npm scripts（package.json）

- `gen:api`：`openapi-typescript ./openapi.json -o src/api/schema.d.ts`
- `sync:openapi`：从 `../docs/design/openapi.json` 复制到 `frontend/openapi.json` 后执行 `gen:api`
- `check:openapi`：运行 `scripts/check-openapi-drift.ts`，比对 `frontend/openapi.json` 与 `../docs/design/openapi.json` 的规范化 JSON，不一致则非零退出（CI 用）

### 5.3 漂移防护

- `schema.d.ts` 与 `openapi.json` 一并提交并纳入版本控制；`schema.d.ts` 标注「生成物，勿手改」。
- CI 前端工作流执行 `check:openapi` + `gen:api` 后 `git diff --exit-code`，确保「契约↔类型↔提交」三者一致。
- 后端 `tests/system` 已有 OpenAPI 契约快照测试守护后端侧；前端侧校验消费侧同步。

---

## 6. 状态管理方案

分层管理，避免「一个大 store」：

### 6.1 服务端状态（TanStack Query v5）

- 所有后端数据（任务列表、任务详情、设置、应用状态、版本）走 Query 缓存。
- Query Key 约定：`['tasks', filters]`、`['task', roomId, 'data'|'param'|'metadata'|'profile'|'videos'|'danmakus']`、`['settings']`、`['settings', 'task', roomId]`、`['app','status'|'info']`、`['update','latest']`。
- 变更操作（start/stop/enable/disable/add/delete/patch-settings）用 `useMutation`，成功后 `invalidateQueries` 对应 Key。
- 默认 `staleTime` 较短的静态数据长、动态数据交由 WS 事件驱动失效（见 §7），减少轮询。

### 6.2 客户端状态（Zustand）

仅存放**非服务端**的 UI 状态：
- WebSocket 连接状态（`connecting`/`open`/`reconnecting`/`closed`）。
- 任务列表筛选器与分页选择。
- 主题（浅/深色）、抽屉/弹窗开合等瞬时 UI。

### 6.3 实时事件与缓存的联动

WebSocket 事件不直接渲染业务数据，而是作为**缓存失效/局部更新的信号源**（详见 §7.4），保证「事件 → Query 失效 → 重新拉取或乐观更新 → UI 一致」的单向流。

---

## 7. WebSocket 实时推送对接策略

### 7.1 端点

| 路径 | 来源 | 载荷 |
|---|---|---|
| `WS /ws/v1/events` | EventCenter | 事件对象 `model_dump(mode="json")`：`{ type, id, date, data }` |
| `WS /ws/v1/exceptions` | ExceptionCenter | `{ type, message, traceback }` |

两端点均在**空闲 30s** 时由后端发送 `{ "type": "ping" }` 保活；前端收到 `ping` 仅用于判活，不作业务处理。

### 7.2 事件类型（来自 `event/models.py`）

`VideoFileCreatedEvent` / `VideoFileCompletedEvent` / `DanmakuFileCreatedEvent` / `DanmakuFileCompletedEvent` / `RawDanmakuFileCreatedEvent` / `RawDanmakuFileCompletedEvent` / `CoverImageDownloadedEvent` / `VideoPostprocessingCompletedEvent` / `PostprocessingCompletedEvent` / `Error`。

多数事件 `data` 含 `room_id` 与 `path`（`PostprocessingCompletedEvent` 为 `files: string[]`；`Error` 为 `{ name, detail }`）。事件类型的 TS 联合类型由 `schema.d.ts` 的 `components.schemas` 派生，配合 `type` 字段做可辨识联合（discriminated union）。

### 7.3 连接管理

- 单例连接管理器，页面加载即建立两条连接；`reconnect.ts` 实现**指数退避**（如 1s→2s→…→上限 30s，带抖动）自动重连。
- 心跳：若超过 `ping` 间隔（>45s）未收到任何消息则主动断开并重连。
- 连接状态写入 Zustand，顶栏展示「实时连接」指示灯；断开期间对关键数据回退为定时 `refetch`。

### 7.4 事件 → UI 映射

| 事件 | 前端动作 |
|---|---|
| `VideoFile*` / `DanmakuFile*` / `RawDanmakuFile*` | 失效 `['task', room_id, 'videos'/'danmakus']` 与 `['task', room_id, 'data']` |
| `CoverImageDownloadedEvent` | 更新对应任务卡片封面 |
| `VideoPostprocessingCompletedEvent` / `PostprocessingCompletedEvent` | 失效 `['task', room_id, 'data']`，刷新后处理进度/产物 |
| `Error` | 弹错误 toast 并记入「事件/异常」面板 |
| `/ws/v1/exceptions` 消息 | 汇入全局异常面板（含 `traceback` 折叠展示） |

> 运行态高频字段（`dl_rate`/`rec_rate`/`rec_elapsed`/`postprocessing_progress`）由 `['task', room_id, 'data']` 承载；WS 事件触发其失效即可，避免为每个速率单独建立推送通道。

---

## 8. 页面与路由结构

| 路由 | 页面 | 后端端点 |
|---|---|---|
| `/` → `/dashboard` | 概览仪表盘（统计卡片 + 最近事件 + 录制中快捷卡片，见 §14.5） | `GET /app/status`、`GET /tasks/data`、`WS /ws/v1/events` |
| `/tasks` | 任务列表（卡片网格为主 + 筛选 + 批量操作，见 §14.6） | `GET /tasks/data`、批量 `start`/`stop`/`recorder/*`、`DELETE /tasks` |
| `/tasks/new` | 添加任务（房号，支持短号） | `POST /tasks/{room_id}` |
| `/tasks/:roomId` | 任务详情（状态/参数/元数据/Profile/视频/弹幕 + 单任务操作） | `GET /tasks/{room_id}/{data,param,metadata,profile,videos,danmakus}`、单任务 `start`/`stop`/`recorder/*`、`DELETE` |
| `/settings` | 全局设置（分组见 §8.1） | `GET/PATCH /settings` |
| `/settings/tasks/:roomId` | 任务级设置（`null` 回退全局） | `GET/PATCH /settings/tasks/{room_id}` |
| `/login` | 扫码登录（TV 二维码 + 轮询） | `GET /qrcode/login`、`POST /qrcode/login/poll` |
| `/about` | 关于/状态（应用信息、版本更新、目录校验） | `GET /app/{status,info}`、`GET /update/version/latest`、`POST /validation/dir`、`POST /app/{restart,exit}` |

### 8.1 设置分组（对应 `setting/models.py`）

BiliApi、Header、Danmaku、Recorder、Output、Postprocessing、Logging、Space、Task。全局设置页按分组渲染表单；任务级设置页展示 `TaskOptions`（可覆盖字段，留空/`null` 表示回退全局）。表单字段与校验由 `settings` schema 派生。

### 8.2 布局与通用组件

- 布局：左侧导航（概览/任务/设置/登录/关于，可折叠）+ 顶栏（实时连接指示灯、主题切换、添加任务、应用状态/重启/退出）。详见 §14.4。
- 通用组件：`TaskCard`、`StatusBadge`（monitor/recorder/running_status）、`RateGauge`（速率）、`RateSparkline`（速率曲线）、`ProgressBar`（后处理进度）、`StatCard`（概览统计）、`ConnectionIndicator`（实时连接）、`ThemeToggle`（主题切换）、`QrcodeLogin`、`EventLogPanel`、`SettingsForm`。

---

## 9. 错误处理与通知

- HTTP 层：`code !== 0` 或非 2xx 统一抛错，经 TanStack Query 的 `onError` / 全局错误边界转 Ant Design `notification`/`message`。
- WS 层：`Error` 事件与 `/ws/v1/exceptions` 汇入「事件/异常」面板，严重异常同时弹 toast。
- 断连降级：WS 断开时顶栏提示，并对关键查询启用定时 `refetch` 兜底，恢复后停用。
- 全局 React ErrorBoundary 兜底渲染异常，避免白屏。

---

## 10. 测试策略（DT / ST 覆盖）

沿用后端测试金字塔理念，前端分两层：

### 10.1 DT — 单元/组件（`tests/unit/`，Vitest + RTL + MSW）

- **hooks**：`api/endpoints/*` 的 Query/Mutation 逻辑（成功/`code!=0`/网络错误分支），用 MSW 依据 `openapi.json` 提供 Mock 响应。
- **WS**：`useEventStream`/`reconnect` 的连接、心跳、指数退避、事件→失效映射（Mock WebSocket）。
- **组件**：`TaskCard`/`StatusBadge`/`SettingsForm`/`QrcodeLogin` 的渲染与交互（筛选、启停按钮禁用态、表单校验、`null` 回退语义）。
- **纯逻辑**：单位换算/速率格式化/筛选器→`select` 映射。

### 10.2 ST — 端到端（`tests/e2e/`，Playwright）

- 对接**后端 fake Bilibili 服务**（`tests/system/fake_bili_server.py`）或本地真实后端，覆盖关键用户旅程：
  1. 添加任务 → 模拟开播 → 列表出现录制中 → WS 事件驱动文件出现 → 停止任务。
  2. 修改全局/任务级设置并回读一致。
  3. 扫码登录流程（Mock 轮询返回）。
  4. 断连重连：切断 WS 后指示灯变更、恢复后数据回到最新。

### 10.3 覆盖率与门禁

- 目标：语句/分支覆盖 **≥ 80%**；核心（`api/`、`ws/`、`pages/tasks`）**≥ 85%**。
- Vitest `--coverage` 作为 CI 硬门禁（`--coverage.thresholds`）。
- 确定性：禁用真实时间/随机（注入时钟/固定种子），网络一律走 MSW 或 fake 后端。

---

## 11. CI/CD 设计（GitHub Actions）

### 11.1 `frontend.yml`（PR + push 到任意分支）

```yaml
name: Frontend CI
on:
  push: { paths: ["frontend/**", "docs/design/openapi.json"] }
  pull_request: { paths: ["frontend/**", "docs/design/openapi.json"] }
jobs:
  quality:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: "pnpm", cache-dependency-path: frontend/pnpm-lock.yaml }
      - run: pnpm install --frozen-lockfile
      - run: pnpm check:openapi                 # 契约漂移校验
      - run: pnpm gen:api && git diff --exit-code # 生成类型无漂移
      - run: pnpm lint
      - run: pnpm typecheck                      # tsc --noEmit
      - run: pnpm test --coverage                # Vitest 门禁
      - run: pnpm build
```

### 11.2 E2E（可并入 `st.yml` 或独立）

- 启动后端 fake 服务 + `pnpm preview` 后运行 `pnpm e2e`（Playwright，安装浏览器）。
- 与后端一致：E2E 较慢，跑在 PR 与合并到 `main`。

### 11.3 质量基线

- ESLint + Prettier 与 CI 同规则，纳入仓库 `pre-commit`/lint-staged 本地拦截。
- 分支保护：`frontend.yml` 通过 + 契约同步 + 至少 1 名评审。

---

## 12. 构建与部署集成

- **产物托管**：`pnpm build` 输出到 `frontend/dist/`；构建时同步/内嵌进后端可分发的静态目录，由 FastAPI 静态挂载（`StaticFiles`）+ `RouteRedirectMiddleware` 实现 SPA 路由回退（非 `/api`、`/ws`、非静态资源的 404 → `index.html`）。
- **子路径反代**：`index.html` 保留 `<head>`，运行时由后端 `BaseHrefMiddleware` 注入 `<base href="/子路径/">`；前端资源使用相对路径，Router 读取 `<base>`/`--root-path` 前缀。
- **Docker**：在后端多阶段镜像中新增前端构建阶段（node + pnpm 构建 `dist`），拷贝至运行阶段静态目录；单镜像同时提供 API 与 UI。
- **开发**：`vite dev` + `server.proxy` 代理 `/api`、`/ws` 到本地后端（默认 `:2233`），前后端可独立热更。

---

## 13. 里程碑规划（前端）

| 里程碑 | 范围 |
|---|---|
| FM0 | 脚手架：Vite+React+TS、ESLint/Prettier、`frontend.yml`、`openapi-typescript` 生成链路与漂移校验 |
| FM1 | API 客户端层：`openapi-fetch` 封装、`ResponseMessage` 拆包、TanStack Query 接入、领域 hooks + DT |
| FM2 | WebSocket 层：事件/异常订阅、重连/心跳、事件→缓存失效映射 + DT |
| FM3 | 任务模块：列表（筛选/批量）+ 详情（状态/文件/操作）+ 实时刷新 |
| FM4 | 设置模块：全局 + 任务级（`null` 回退）表单与校验 |
| FM5 | 登录/关于：扫码登录、应用状态/版本/目录校验/重启退出 |
| FM6 | E2E（Playwright）对接 fake 后端、覆盖率门禁达标 |
| FM7 | 构建部署集成：静态托管、`<base href>`、Docker 多阶段前端构建 |

---

## 14. UI 视觉设计规范

> 基于 §8 已定的信息架构，仅做视觉与体验升级，不改动页面/路由骨架。设计基准为 blrec 原版（Angular + ng-zorro-antd，同 Ant Design 血统），在保留操作熟悉感的同时定制现代主题。

### 14.1 设计基调

- **定制现代主题**：在 Ant Design 5 的 design-token 架构上定制，气质从「默认后台」提升为「精致产品」——品牌主色、更大圆角、柔和多层阴影、更充裕留白。
- **品牌识别**：主色采用 Bilibili 标志性粉 `#FB7299`，强化直播录制工具的品牌关联。
- **双主题**：亮/暗双主题，跟随系统并可手动切换（§14.3）。

### 14.2 主题令牌（`ConfigProvider` theme）

| Token | 亮色 | 暗色 | 说明 |
|---|---|---|---|
| `colorPrimary` | `#FB7299` | `#FF85AB`（略提亮） | B站粉主色 |
| `borderRadius` | `8`（卡片 `12`） | 同 | 大圆角、柔和 |
| `colorBgLayout` | `#F5F6F8` | `#0F0F0F` | 内容区背景 |
| `colorBgContainer` | `#FFFFFF` | `#1A1A1A` | 卡片/表单底色 |
| `boxShadow` | 柔和多层阴影 | 弱化处理 | 卡片层次/悬浮 |
| `controlHeight` | `36` | 同 | 更大控件与内边距，呼吸感 |
| `fontFamily` | `Inter, "PingFang SC", "HarmonyOS Sans", system-ui, sans-serif` | 同 | 现代无衬线字体栈 |

- token 集中定义于 `app/theme.ts`，由 `providers.tsx` 的 `ConfigProvider` 注入；暗色叠加 `theme.darkAlgorithm`。
- 语义色（成功/警告/错误/信息）沿用 AntD 默认，仅在状态徽章处强化对比。

### 14.3 深色模式

- **三态**：`system` / `light` / `dark`，持久化于 `localStorage`，运行态存 Zustand（§3 主题 store）。
- `system` 态监听 `matchMedia('(prefers-color-scheme: dark)')` 的 `change` 事件实时切换。
- 顶栏提供主题切换控件（图标：跟随系统 / 太阳 / 月亮）。

### 14.4 布局与导航

- **左侧导航**（可折叠为图标栏）：顶部 logo；导航项 `概览 / 任务 / 设置 / 登录 / 关于`。
- **顶栏**：左侧页面标题/面包屑；右侧依次为 实时连接指示灯（绿=已连 / 黄=重连中 / 红=断开 + 文案，见 §7.3）、主题切换、`+ 添加任务`、更多菜单（应用状态 / 重启 / 退出）。
- **响应式**：`md` 以下左侧导航收起为抽屉（Drawer）；顶栏操作收敛进溢出菜单。

### 14.5 Dashboard 概览页（新增，路由 `/` → `/dashboard`）

blrec 原版无总览页；新增以「一眼掌握全局」：

- **统计卡片行**：录制中 / 监控中 / 总任务数；磁盘可用（进度环，来源 `GET /app/status` 与 Space 设置）；总下载速率 + 总录制速率（带 sparkline 迷你曲线）。
- **最近事件时间线**：复用 `EventLogPanel` 紧凑态，订阅 `/ws/v1/events`。
- **录制中快捷卡片**：正在录制的任务缩略卡，点击进详情。
- 数据来源以 `/tasks/data`（聚合）与 WS 事件为主；速率汇总在前端按任务累加。
- 交付节奏：随 FM3 任务模块一并落地（依赖任务数据与 WS 层）。

### 14.6 任务卡片网格（`/tasks` 首页核心，卡片网格为主）

响应式网格（`xxl:4 / xl:3 / md:2 / xs:1` 列），每张 `TaskCard`：

- **封面缩略图**（16:9）+ 左上角直播状态角标（直播中/闲置/轮播）；封面随 `CoverImageDownloadedEvent` 更新，缺失时用分区占位图。
- 主播头像 + 昵称、房间标题、房号、分区。
- **状态行**：`StatusBadge`（监控 / 录制器 / 运行态，颜色语义化）；录制中显示 `RateGauge`（下载/录制速率）与后处理 `ProgressBar`。
- **操作区**：启停（主按钮）、录制器开关、切割、更多菜单（详情 / 设置 / 删除）。
- **状态区分**：hover 抬升阴影；**录制中卡片**以主色微光/呼吸描边强化，一眼可辨。
- 展示字段以 `/tasks/data` 的 `TaskData`（`room_info` / `user_info` / `task_status`）为准；接入类型（FM1/FM3）时核对 `openapi.json`，缺失字段做降级。
- **大数据量**：任务数多时对网格启用虚拟化/分页（策略见 §15）。

### 14.7 其余页面视觉要点

- **任务详情**（`/tasks/:roomId`）：顶部信息头（封面/主播/状态大图）+ 标签页（状态·参数·元数据·Profile·视频·弹幕），主操作区固定于信息头。
- **设置**（`/settings`）：左侧分组锚点（§8.1 各分组）+ 右侧表单卡片；任务级设置留空=回退全局，用 placeholder 呈现继承值。
- **扫码登录**（`/login`）：居中卡片，二维码 + 轮询状态动效（待扫描 / 已扫描 / 已确认 / 过期）。

### 14.8 动效与微交互

- 加载用骨架屏（卡片/表格/表单各自骨架）；启停/开关用乐观更新 + 失败回滚。
- 状态切换、卡片 hover、主题切换均加克制过渡（≤200ms），不喧宾夺主。
- 尊重 `prefers-reduced-motion`，关闭非必要动画。

---

## 15. 待细化事项（TODO，随实现推进补充）

- 速率曲线的图表实现：Dashboard sparkline 与卡片速率曲线是否引入图表库（如 `@ant-design/plots`）或自绘 SVG。
- 任务卡片网格大数据量下的虚拟滚动/分页策略。
- 前端产物与后端镜像的集成方式最终形态（内嵌 wheel vs 运行时卷挂载）。
- i18n 结构是否预留。

---

## 变更记录

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| 0.0 | 2026-07-24 | 创建占位文档，明确前端阶段延后。 |
| 0.1 | 2026-07-28 | 启动前端设计：确立技术栈（React 19 + Vite 7 + TS）、契约驱动类型生成（openapi-typescript/openapi-fetch）、状态管理（TanStack Query + Zustand）、WebSocket 实时对接策略、页面/路由结构、DT/ST 测试与覆盖率门禁、CI/CD 与部署集成、前端里程碑规划。 |
| 0.2 | 2026-07-28 | 新增 §14 UI 视觉设计规范：定制现代主题（B站粉 #FB7299、大圆角、柔和阴影、更多留白）、亮/暗双主题跟随系统、新增 Dashboard 概览页、任务卡片网格为主；相应更新 §8 路由/布局/通用组件；原 §14 TODO 顺延为 §15 并解决 UI 组件库选型项。 |
