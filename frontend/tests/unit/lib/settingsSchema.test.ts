/**
 * M31 DT：设置分组描述与纯函数（§8.1）。
 */
import { describe, expect, it } from 'vitest'

import {
  SETTINGS_GROUPS,
  TASK_SETTINGS_GROUPS,
  buildPatchBody,
  getGroupValues,
} from '../../../src/lib/settingsSchema'

describe('SETTINGS_GROUPS', () => {
  it('覆盖 8 个全局分组（对应 SettingsIn）', () => {
    const keys = SETTINGS_GROUPS.map((g) => g.key)
    expect(keys).toEqual([
      'biliApi',
      'header',
      'danmaku',
      'recorder',
      'output',
      'postprocessing',
      'logging',
      'space',
    ])
  })

  it('每个分组至少含一个字段且字段键唯一', () => {
    for (const g of SETTINGS_GROUPS) {
      expect(g.fields.length).toBeGreaterThan(0)
      const keys = g.fields.map((f) => f.key)
      expect(new Set(keys).size).toBe(keys.length)
    }
  })

  it('select 类型字段必带 options', () => {
    for (const g of SETTINGS_GROUPS) {
      for (const f of g.fields) {
        if (f.type === 'select') expect(f.options?.length).toBeGreaterThan(0)
      }
    }
  })
})

describe('output.pathTemplate 字段（#37）', () => {
  it('使用专用 pathTemplate 控件且任务级可覆盖', () => {
    const output = SETTINGS_GROUPS.find((g) => g.key === 'output')
    const field = output?.fields.find((f) => f.key === 'pathTemplate')
    expect(field?.type).toBe('pathTemplate')
    expect(field?.taskOverridable).toBe(true)
  })
})

describe('TASK_SETTINGS_GROUPS', () => {
  it('仅含 taskOverridable 字段，且不含纯全局字段 outDir', () => {
    const allFields = TASK_SETTINGS_GROUPS.flatMap((g) => g.fields)
    expect(allFields.every((f) => f.taskOverridable)).toBe(true)
    const output = TASK_SETTINGS_GROUPS.find((g) => g.key === 'output')
    expect(output?.fields.map((f) => f.key)).toContain('pathTemplate')
    expect(output?.fields.map((f) => f.key)).not.toContain('outDir')
  })

  it('不含无可覆盖字段的分组（biliApi/logging/space）', () => {
    const keys = TASK_SETTINGS_GROUPS.map((g) => g.key)
    expect(keys).not.toContain('biliApi')
    expect(keys).not.toContain('logging')
    expect(keys).not.toContain('space')
  })
})

describe('getGroupValues', () => {
  it('取出分组对象，缺省返回空对象', () => {
    expect(
      getGroupValues({ recorder: { streamFormat: 'ts' } }, 'recorder'),
    ).toEqual({
      streamFormat: 'ts',
    })
    expect(getGroupValues(undefined, 'recorder')).toEqual({})
    expect(getGroupValues({ recorder: 'bad' }, 'recorder')).toEqual({})
  })
})

describe('buildPatchBody', () => {
  it('包裹为 { [group]: values }', () => {
    expect(buildPatchBody('space', { recycleRecords: true })).toEqual({
      space: { recycleRecords: true },
    })
  })
})
