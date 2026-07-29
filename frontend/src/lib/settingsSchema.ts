/**
 * 设置分组声明式描述（frontend-design.md §8.1，字段派生自 setting/models.py）。
 *
 * 后端 GET/PATCH /settings 契约为不透明 object（openapi 仅 additionalProperties），
 * 故此处以「唯一来源」形式集中声明各分组字段、类型与校验约束，驱动表单渲染与
 * 校验。键名一律 camelCase（后端 model_dump(by_alias=True) 输出/接受 camelCase）。
 */

export type FieldType =
  'text' | 'textarea' | 'switch' | 'number' | 'select' | 'stringList'

export interface SelectOption {
  value: string | number
  label: string
}

export interface FieldDescriptor {
  /** 分组内字段键（camelCase）。 */
  key: string
  label: string
  type: FieldType
  options?: SelectOption[]
  min?: number
  max?: number
  step?: number
  multipleOf?: number
  placeholder?: string
  help?: string
  /** 任务级设置可覆盖（TaskOptions 中存在的可空字段）。 */
  taskOverridable?: boolean
}

export interface GroupDescriptor {
  /** 顶层分组键（camelCase），对应 SettingsIn / TaskOptions 的字段。 */
  key: string
  title: string
  fields: FieldDescriptor[]
}

// —— 后端约束枚举（setting/models.py）——
const TIMEOUT_VALUES = [3, 5, 10, 30, 60, 180, 300, 600]
const DISCONNECTION_VALUES = [180, 300, 600, 900, 1200, 1800]
const CHECK_INTERVAL_VALUES = [0, 10, 30, 60, 180, 300, 600]
const GB = 1024 ** 3
const SPACE_THRESHOLD_VALUES = [1, 3, 5, 10, 20].map((n) => n * GB)

const secOpts = (vals: number[]): SelectOption[] =>
  vals.map((v) => ({ value: v, label: `${v}s` }))

export const QUALITY_OPTIONS: SelectOption[] = [
  { value: 20000, label: '4K' },
  { value: 10000, label: '原画' },
  { value: 401, label: '蓝光(杜比)' },
  { value: 400, label: '蓝光' },
  { value: 250, label: '超清' },
  { value: 150, label: '高清' },
  { value: 80, label: '流畅' },
]

export const LOG_LEVEL_OPTIONS: SelectOption[] = [
  'TRACE',
  'DEBUG',
  'INFO',
  'SUCCESS',
  'WARNING',
  'ERROR',
  'CRITICAL',
].map((v) => ({ value: v, label: v }))

/** 全局设置分组（对应 SettingsIn 的 8 个组）。 */
export const SETTINGS_GROUPS: GroupDescriptor[] = [
  {
    key: 'biliApi',
    title: 'BiliApi',
    fields: [
      { key: 'baseApiUrls', label: 'API 域名', type: 'stringList' },
      { key: 'baseLiveApiUrls', label: '直播 API 域名', type: 'stringList' },
      {
        key: 'basePlayInfoApiUrls',
        label: '播放信息 API 域名',
        type: 'stringList',
      },
    ],
  },
  {
    key: 'header',
    title: 'Header',
    fields: [
      {
        key: 'userAgent',
        label: 'User-Agent',
        type: 'textarea',
        taskOverridable: true,
      },
      {
        key: 'cookie',
        label: 'Cookie',
        type: 'textarea',
        taskOverridable: true,
      },
    ],
  },
  {
    key: 'danmaku',
    title: 'Danmaku',
    fields: [
      {
        key: 'danmuUname',
        label: '记录用户名',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'recordGiftSend',
        label: '记录礼物',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'recordFreeGifts',
        label: '记录免费礼物',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'recordGuardBuy',
        label: '记录上舰',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'recordSuperChat',
        label: '记录醒目留言',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'recordToast',
        label: '记录续费提示',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'saveRawDanmaku',
        label: '保存原始弹幕',
        type: 'switch',
        taskOverridable: true,
      },
    ],
  },
  {
    key: 'recorder',
    title: 'Recorder',
    fields: [
      {
        key: 'streamFormat',
        label: '流格式',
        type: 'select',
        taskOverridable: true,
        options: [
          { value: 'flv', label: 'FLV' },
          { value: 'ts', label: 'TS' },
          { value: 'fmp4', label: 'fMP4' },
        ],
      },
      {
        key: 'recordingMode',
        label: '录制模式',
        type: 'select',
        taskOverridable: true,
        options: [
          { value: 'standard', label: '标准' },
          { value: 'raw', label: '原始' },
        ],
      },
      {
        key: 'qualityNumber',
        label: '画质',
        type: 'select',
        taskOverridable: true,
        options: QUALITY_OPTIONS,
      },
      {
        key: 'fmp4StreamTimeout',
        label: 'fMP4 流超时',
        type: 'select',
        taskOverridable: true,
        options: secOpts(TIMEOUT_VALUES),
      },
      {
        key: 'readTimeout',
        label: '读取超时',
        type: 'select',
        taskOverridable: true,
        options: secOpts(TIMEOUT_VALUES),
      },
      {
        key: 'disconnectionTimeout',
        label: '断连超时',
        type: 'select',
        taskOverridable: true,
        options: secOpts(DISCONNECTION_VALUES),
      },
      {
        key: 'bufferSize',
        label: '缓冲区大小(字节)',
        type: 'number',
        taskOverridable: true,
        min: 4096,
        max: 1024 ** 2 * 512,
        multipleOf: 2,
        step: 2,
      },
      {
        key: 'saveCover',
        label: '保存封面',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'coverSaveStrategy',
        label: '封面保存策略',
        type: 'select',
        taskOverridable: true,
        options: [
          { value: 'default', label: '默认' },
          { value: 'dedup', label: '去重' },
        ],
      },
    ],
  },
  {
    key: 'output',
    title: 'Output',
    fields: [
      { key: 'outDir', label: '输出目录', type: 'text' },
      {
        key: 'pathTemplate',
        label: '路径模板',
        type: 'text',
        taskOverridable: true,
        help: '支持 {roomid} {uname} {year} 等占位符',
      },
    ],
  },
  {
    key: 'postprocessing',
    title: 'Postprocessing',
    fields: [
      {
        key: 'remuxToMp4',
        label: '转封装 MP4',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'injectExtraMetadata',
        label: '注入元数据',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'danmakuToAss',
        label: '弹幕转 ASS',
        type: 'switch',
        taskOverridable: true,
      },
      {
        key: 'assFontSize',
        label: 'ASS 字号',
        type: 'number',
        taskOverridable: true,
        min: 1,
        max: 200,
      },
      {
        key: 'assScFontSize',
        label: 'ASS SC 字号',
        type: 'number',
        taskOverridable: true,
        min: 1,
        max: 200,
      },
      {
        key: 'assResolutionX',
        label: 'ASS 分辨率 X',
        type: 'number',
        taskOverridable: true,
        min: 1,
        max: 7680,
      },
      {
        key: 'assResolutionY',
        label: 'ASS 分辨率 Y',
        type: 'number',
        taskOverridable: true,
        min: 1,
        max: 4320,
      },
    ],
  },
  {
    key: 'logging',
    title: 'Logging',
    fields: [
      { key: 'logDir', label: '日志目录', type: 'text' },
      {
        key: 'consoleLogLevel',
        label: '控制台日志级别',
        type: 'select',
        options: LOG_LEVEL_OPTIONS,
      },
      {
        key: 'backupCount',
        label: '日志保留数',
        type: 'number',
        min: 0,
        max: 90,
      },
    ],
  },
  {
    key: 'space',
    title: 'Space',
    fields: [
      {
        key: 'checkInterval',
        label: '检查间隔',
        type: 'select',
        options: secOpts(CHECK_INTERVAL_VALUES),
      },
      {
        key: 'spaceThreshold',
        label: '空间阈值',
        type: 'select',
        options: SPACE_THRESHOLD_VALUES.map((v) => ({
          value: v,
          label: `${v / GB}GB`,
        })),
      },
      { key: 'recycleRecords', label: '回收记录', type: 'switch' },
    ],
  },
]

/**
 * 任务级设置分组：取全局分组中标记 taskOverridable 的字段（对应 TaskOptions），
 * 留空 = 回退全局（placeholder 呈现继承值）。
 */
export const TASK_SETTINGS_GROUPS: GroupDescriptor[] = SETTINGS_GROUPS.filter(
  (g) => g.fields.some((f) => f.taskOverridable),
).map((g) => ({
  ...g,
  fields: g.fields.filter((f) => f.taskOverridable),
}))

/** 从设置对象取分组值（缺省返回空对象）。 */
export function getGroupValues(
  settings: Record<string, unknown> | undefined,
  groupKey: string,
): Record<string, unknown> {
  const group = settings?.[groupKey]
  if (group && typeof group === 'object')
    return group as Record<string, unknown>
  return {}
}

/** 构建全局 PATCH body：{ [groupKey]: values }。 */
export function buildPatchBody(
  groupKey: string,
  values: Record<string, unknown>,
): Record<string, unknown> {
  return { [groupKey]: values }
}
