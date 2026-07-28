# bili-rec 前端

Bilibili 直播录制器的 Web 控制台。React 19 + Vite 7 + TypeScript（strict），消费后端
OpenAPI 契约（`../docs/design/openapi.json`）。设计见 [`../docs/design/frontend-design.md`](../docs/design/frontend-design.md)。

## 开发

```bash
pnpm install
pnpm dev        # 开发服务器（/api、/ws 代理到本地后端 :2233，可用 VITE_BACKEND 覆盖）
```

## 常用脚本

| 脚本 | 说明 |
|---|---|
| `pnpm dev` | 开发服务器（HMR） |
| `pnpm build` | 类型检查 + 生产构建（输出 `dist/`） |
| `pnpm preview` | 预览生产构建 |
| `pnpm typecheck` | `tsc -b` 类型检查 |

> 工具链：Node ≥ 20.19，pnpm（`packageManager` 已锁定）。
