/**
 * 契约漂移校验：比对 frontend/openapi.json 与后端导出的
 * docs/design/openapi.json（规范化后深比较）。不一致则非零退出。
 *
 * 用于 CI 与本地门禁：前端消费的契约副本必须与后端唯一事实来源保持一致。
 * 同步方式：`pnpm sync:openapi`（复制 + 重新生成类型）。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const localPath = resolve(here, '../openapi.json')
const backendPath = resolve(here, '../../docs/design/openapi.json')

/** 递归排序对象键，消除键序差异带来的伪差异。 */
function normalize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(normalize)
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>)
        .sort()
        .map((key) => [
          key,
          normalize((value as Record<string, unknown>)[key]),
        ]),
    )
  }
  return value
}

function load(path: string): string {
  return JSON.stringify(normalize(JSON.parse(readFileSync(path, 'utf-8'))))
}

const local = load(localPath)
const backend = load(backendPath)

if (local !== backend) {
  console.error(
    '✗ 契约漂移：frontend/openapi.json 与 docs/design/openapi.json 不一致。\n' +
      '  运行 `pnpm sync:openapi` 同步契约并重新生成类型后提交。',
  )
  process.exit(1)
}

console.log(
  '✓ 契约一致：frontend/openapi.json 与 docs/design/openapi.json 相同。',
)
