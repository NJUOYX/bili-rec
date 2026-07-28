#!/usr/bin/env bash
#
# 前端质量门禁 —— 与 .github/workflows/frontend.yml 严格对齐。
# 本地在提交/发起 PR 前运行，任一步骤失败即整体失败（set -e）。
#
# 用法：
#   bash frontend/scripts/gate.sh            # 从仓库根
#   ./scripts/gate.sh                        # 从 frontend/
#
# 前置：已安装 Node（>=20.19）与 pnpm（见 package.json packageManager）。
#
set -euo pipefail

# 切到 frontend/（脚本位于 frontend/scripts/）
cd "$(dirname "$0")/.."

step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$1"; }

step "install（--frozen-lockfile，校验锁文件一致）"
pnpm install --frozen-lockfile

step "check:openapi（契约漂移：frontend/openapi.json ↔ 后端契约）"
pnpm check:openapi

step "gen:api 幂等（重新生成类型后不应产生 diff）"
pnpm gen:api
git diff --exit-code -- src/api/schema.d.ts

step "lint（eslint + typescript-eslint）"
pnpm lint

step "format:check（prettier）"
pnpm format:check

step "typecheck（tsc -b）"
pnpm typecheck

step "test + coverage（vitest，覆盖率硬门禁）"
pnpm test:coverage

step "build（vite）"
pnpm build

printf '\n\033[1;32m✅ 前端质量门禁全部通过\033[0m\n'
