# 真实 Bilibili 直播间验证测试

`tests/realbili/` 是一组针对**真实 Bilibili 直播间**的端到端验证测试，用于确认录制链路对线上服务仍然可用。它们会发起真实网络请求，因此**默认关闭**，不进入常规质量门禁（`-m "unit or component"`），也不在 PR 上运行——仅通过定时/手动的独立 CI（`.github/workflows/real-bili.yml`）和本地手动执行。

## 四层测试

| 层 | 文件 | 验证点 |
|----|------|--------|
| ① API 连通性 | `test_api_connectivity.py` | room/user info、`live_status`、play_infos 有可播流、danmu_info 有 host + token、nav 有 WBI 密钥 |
| ② 拉流 + 产物校验 | `test_stream_pull.py` | FLV URL 可解析、CDN 可达、拉 512KB、`FlvReader` 能解析出 header + ≥3 个 tag |
| ③ 弹幕 WebSocket | `test_danmaku_ws.py` | `DanmakuClient` 建立鉴权长连接（硬断言），观察 8s 收弹幕（尽力而为） |
| ④ Web API E2E | `test_web_e2e.py` | 经 HTTP：加任务 → 列表 → 刷新 info → 单任务数据（主播名回填）→ 删除，信封 `code == 0` |

## 环境变量

| 变量 | 是否必需 | 作用 |
|------|----------|------|
| `BIREC_REALBILI` | **必需** | 设为 `1` 才会运行；否则整套跳过 |
| `BIREC_TEST_ROOM_ID` | 可选 | 锁定一个"确定在播"的房间号，结果最稳定 |
| `BIREC_BILI_COOKIE` | 可选 | 登录 cookie（如 `SESSDATA=...; bili_jct=...`），降低风控概率 |

- **不设 `BIREC_TEST_ROOM_ID`**：自动从 B 站推荐位（`getMoreRecList` / `index/getList`）发现一个在播房间。方便，但发现到的房间不保证 24/7 在播，可能出现"非 LIVE → 部分层跳过"。
- **设了 `BIREC_TEST_ROOM_ID`**：所有用例锁定该房间，结果最稳定。推荐用你信任的 24/7 房间号。

## 执行命令

```bash
cd /path/to/bili-rec

# 跑完整四层（推荐）
BIREC_REALBILI=1 uv run pytest tests/realbili -v

# 只跑某一层
BIREC_REALBILI=1 uv run pytest tests/realbili/test_api_connectivity.py -v   # ① API 连通性
BIREC_REALBILI=1 uv run pytest tests/realbili/test_stream_pull.py -v        # ② 拉流 + 校验
BIREC_REALBILI=1 uv run pytest tests/realbili/test_danmaku_ws.py -v         # ③ 弹幕 WebSocket
BIREC_REALBILI=1 uv run pytest tests/realbili/test_web_e2e.py -v            # ④ Web API E2E

# 锁定房间 + 携带 cookie
BIREC_REALBILI=1 BIREC_TEST_ROOM_ID=<房间号> BIREC_BILI_COOKIE="SESSDATA=...; bili_jct=..." \
  uv run pytest tests/realbili -v
```

> `uv run pytest` 与 `.venv/bin/python -m pytest` 等价。整套约 **60–90 秒**（含弹幕 WS 观察 8s、拉流 512KB）。

## 预期现象

**① 开启且房间在播（正常路径）** —— 全绿：

```
tests/realbili/test_api_connectivity.py ...... (6) PASSED
tests/realbili/test_danmaku_ws.py ........... (1) PASSED
tests/realbili/test_stream_pull.py .......... (2) PASSED
tests/realbili/test_web_e2e.py .............. (1) PASSED
======================== 10 passed in ~75s ========================
```

**② 开启但房间不在播** —— 优雅跳过（不算失败）：

```
test_stream_pull ... SKIPPED (room X is not LIVE)
test_danmaku_ws  ... SKIPPED (room X is not LIVE)
# API 层与 Web E2E 仍会运行（不依赖 LIVE）
```

**③ 完全没发现在播房间**（网络受限 / 风控）—— 全部跳过：

```
SKIPPED (no live Bilibili room available for verification)
```

**④ 忘记设 `BIREC_REALBILI`（默认）** —— 全部跳过（正确的隔离行为）：

```
ssssssssss  ->  10 skipped
```

## 注意事项

- **风控**：匿名连打同一房间较多请求偶发被限流（返回 `-352`）。设置 `BIREC_BILI_COOKIE` 或减少请求量可缓解；CI 里通过 secret cookie 降低概率。
- **只读 `/tmp` 环境**（如某些沙箱）：拉流测试需要写临时文件，追加 `--basetemp=./.realbili_tmp` 把 pytest 临时目录指到工作区即可。
- **与常规门禁隔离**：这套测试不进入 PR 门禁，也不影响 `uv run pytest -m "unit or component"` 的常规单元/组件测试。
