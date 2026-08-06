/**
 * 路径模板预置与预览（#37）。
 *
 * 与后端保持一致：预置列表镜像 birec.path.PATH_TEMPLATE_PRESETS，校验规则镜像
 * setting/models.py 的 _PATH_TEMPLATE_PATTERN，渲染逻辑镜像 render_template。
 */

/** 设置界面提供的路径模板预置（首项 = 新部署默认，末项 = 旧版扁平布局）。 */
export const PATH_TEMPLATE_PRESETS: string[] = [
  '{roomid} - {uname}/{year}-{month}/{year}-{month}-{day}_{hour}{minute}{second}/blive_{roomid}',
  '{uname}/{year}-{month}/{year}-{month}-{day}_{hour}{minute}{second}/blive_{roomid}',
  '{roomid} - {uname}/blive_{roomid}_{year}-{month}-{day}-{hour}{minute}{second}',
]

const TEMPLATE_VARS = [
  'roomid',
  'uname',
  'title',
  'area',
  'parent_area',
  'year',
  'month',
  'day',
  'hour',
  'minute',
  'second',
] as const

export type TemplateVar = (typeof TEMPLATE_VARS)[number]

/**
 * 模板合法性校验（镜像后端 _PATH_TEMPLATE_PATTERN）：以 / 分隔的每一段都必须
 * 至少含一个已知变量，且不得出现 \ / : * ? " < > | 制表符或花括号等字符。
 */
const PATH_TEMPLATE_PATTERN = new RegExp(
  `^(?:[^\\\\/:*?"<>|\\t\\n\\r\\f\\v{}]*?` +
    `\\{(?:${TEMPLATE_VARS.join('|')})\\}` +
    `[^\\\\/:*?"<>|\\t\\n\\r\\f\\v{}]*?)+?` +
    `(?:/(?:[^\\\\/:*?"<>|\\t\\n\\r\\f\\v{}]*?` +
    `\\{(?:${TEMPLATE_VARS.join('|')})\\}` +
    `[^\\\\/:*?"<>|\\t\\n\\r\\f\\v{}]*?)+?)*$`,
)

export function isValidPathTemplate(template: string): boolean {
  return PATH_TEMPLATE_PATTERN.test(template)
}

/** 路径中不安全的字符（镜像后端 escape_path 的 _UNSAFE_CHARS）。 */
// 控制字符区间的剥离是刻意镜像后端行为（escape_path），故豁免 no-control-regex。
// eslint-disable-next-line no-control-regex
const UNSAFE_CHARS = /[<>:"/\\|?*\u0000-\u001f]/g

function escapePath(text: string): string {
  let escaped = text.replace(UNSAFE_CHARS, '_')
  while (escaped.startsWith('.') || escaped.startsWith(' '))
    escaped = escaped.slice(1)
  while (escaped.endsWith('.') || escaped.endsWith(' '))
    escaped = escaped.slice(0, -1)
  return escaped
}

/** 预览用的示例变量（固定值 + 注入日期，保证确定性）。 */
const SAMPLE_VALUES: Record<TemplateVar, string> = {
  roomid: '123456',
  uname: '示例主播',
  title: '示例直播标题',
  area: '示例分区',
  parent_area: '示例父分区',
  year: '2025',
  month: '01',
  day: '02',
  hour: '20',
  minute: '00',
  second: '00',
}

const pad = (n: number): string => String(n).padStart(2, '0')

/**
 * 按后端 render_template 的规则渲染模板，用于客户端实时预览：
 * 变量替换后对取值做 escape_path 转义；未提供的日期变量取 now。
 */
export function renderPathTemplatePreview(
  template: string,
  now: Date = new Date(),
): string {
  const values: Record<string, string> = {
    ...SAMPLE_VALUES,
    year: String(now.getFullYear()),
    month: pad(now.getMonth() + 1),
    day: pad(now.getDate()),
    hour: pad(now.getHours()),
    minute: pad(now.getMinutes()),
    second: pad(now.getSeconds()),
  }
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? escapePath(values[key]) : match,
  )
}
