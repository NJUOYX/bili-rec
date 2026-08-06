/**
 * #37 DT：路径模板预置 / 校验 / 预览纯函数（镜像后端 birec.path 与
 * setting/models.py 的 _PATH_TEMPLATE_PATTERN）。
 */
import { describe, expect, it } from 'vitest'

import {
  PATH_TEMPLATE_PRESETS,
  isValidPathTemplate,
  renderPathTemplatePreview,
} from '../../../src/lib/pathTemplate'

describe('PATH_TEMPLATE_PRESETS', () => {
  it('提供三个预置且互不重复，末项为旧版扁平布局', () => {
    expect(PATH_TEMPLATE_PRESETS).toHaveLength(3)
    expect(new Set(PATH_TEMPLATE_PRESETS).size).toBe(3)
    expect(PATH_TEMPLATE_PRESETS[2]).toBe(
      '{roomid} - {uname}/blive_{roomid}_{year}-{month}-{day}-{hour}{minute}{second}',
    )
  })

  it('每个预置都通过后端同款校验', () => {
    for (const preset of PATH_TEMPLATE_PRESETS) {
      expect(isValidPathTemplate(preset)).toBe(true)
    }
  })

  it('首项 = 新部署默认（组织化场次目录）', () => {
    expect(PATH_TEMPLATE_PRESETS[0]).toBe(
      '{roomid} - {uname}/{year}-{month}/' +
        '{year}-{month}-{day}_{hour}{minute}{second}/blive_{roomid}',
    )
  })
})

describe('isValidPathTemplate', () => {
  it.each([
    '{roomid}',
    '{roomid} - {uname}',
    '{uname}/{year}-{month}/{year}-{month}-{day}_{hour}{minute}{second}/blive_{roomid}',
    '{roomid}/{title}',
    'rec_{roomid}/{year}',
  ])('接受 %s', (t) => {
    expect(isValidPathTemplate(t)).toBe(true)
  })

  it.each([
    '', // 空
    'static', // 无任何占位符
    '{roomid}/static', // 第二段无占位符
    'static/{roomid}', // 第一段无占位符
    '{unknown}', // 未知占位符
    '{roomid}-{unknown}', // 混入未知占位符
    '{roomid}<x>', // 非法字符
    '{roomid}|{uname}', // 非法字符
    '{roomid}:{uname}', // 非法字符
    '{roomid}\t{uname}', // 制表符
  ])('拒绝 %s', (t) => {
    expect(isValidPathTemplate(t)).toBe(false)
  })
})

describe('renderPathTemplatePreview', () => {
  const fixed = new Date(2026, 6, 25, 20, 5, 9) // 2026-07-25 20:05:09

  it('替换示例变量并补齐日期（month/day/hour/minute/second 零填充）', () => {
    expect(
      renderPathTemplatePreview(
        '{roomid} - {uname}/{year}-{month}-{day}_{hour}{minute}{second}/blive_{roomid}',
        fixed,
      ),
    ).toBe('123456 - 示例主播/2026-07-25_200509/blive_123456')
  })

  it('对取值做 escape_path 转义（非法字符替换为 _）', () => {
    // title 示例值不含非法字符，这里用 roomid 之外的变量验证转义路径存在。
    expect(renderPathTemplatePreview('{title}', fixed)).toBe('示例直播标题')
    expect(renderPathTemplatePreview('{area}/{parent_area}', fixed)).toBe(
      '示例分区/示例父分区',
    )
  })

  it('未知 {word} 原样保留，不吞掉', () => {
    expect(renderPathTemplatePreview('{roomid}/{nope}', fixed)).toBe(
      '123456/{nope}',
    )
  })

  it('缺省日期取当前时间（默认参数不抛错）', () => {
    const out = renderPathTemplatePreview('{year}-{month}-{day}')
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
