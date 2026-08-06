/**
 * #37 DT：路径模板字段组件（预置下拉 + 自定义 + 预览 + 行内校验）。
 * 受控组件，直接以 value/onChange 驱动，验证各状态与交互。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PathTemplateField } from '../../../src/components/PathTemplateField'
import { PATH_TEMPLATE_PRESETS } from '../../../src/lib/pathTemplate'

const PRESET_0 = PATH_TEMPLATE_PRESETS[0]
const CUSTOM_VALID = '{roomid}/rec_{year}'
const CUSTOM_INVALID = 'static/{roomid}' // 第一段无占位符

function openSelect() {
  fireEvent.mouseDown(screen.getByRole('combobox'))
}

describe('PathTemplateField', () => {
  it('预置值：下拉呈现预置，不展开输入框、无错误', () => {
    render(<PathTemplateField value={PRESET_0} onChange={() => {}} />)
    expect(screen.getByRole('combobox')).toBeTruthy()
    expect(screen.queryByTestId('path-template-input')).toBeNull()
    expect(screen.queryByTestId('path-template-error')).toBeNull()
    // 预置合法 → 有预览
    expect(screen.getByTestId('path-template-preview')).toBeTruthy()
  })

  it('空的合法自定义值：展开输入框并显示预览', () => {
    render(<PathTemplateField value={CUSTOM_VALID} onChange={() => {}} />)
    const input = screen.getByTestId('path-template-input')
    expect((input as HTMLInputElement).value).toBe(CUSTOM_VALID)
    expect(screen.getByTestId('path-template-preview')).toBeTruthy()
    expect(screen.queryByTestId('path-template-error')).toBeNull()
  })

  it('非法自定义值：展开输入框并显示错误、无预览', () => {
    render(<PathTemplateField value={CUSTOM_INVALID} onChange={() => {}} />)
    expect(screen.getByTestId('path-template-input')).toBeTruthy()
    expect(screen.getByTestId('path-template-error')).toBeTruthy()
    expect(screen.queryByTestId('path-template-preview')).toBeNull()
  })

  it('空值：显示占位提示，不展开输入框', () => {
    render(
      <PathTemplateField
        value={undefined}
        onChange={() => {}}
        placeholder="继承全局"
      />,
    )
    expect(screen.queryByTestId('path-template-input')).toBeNull()
    expect(screen.queryByTestId('path-template-error')).toBeNull()
    expect(screen.queryByTestId('path-template-preview')).toBeNull()
  })

  it('选择「自定义」展开输入框（不立即触发 onChange）', () => {
    const onChange = vi.fn()
    render(<PathTemplateField value={undefined} onChange={onChange} />)
    openSelect()
    fireEvent.click(screen.getByText('自定义…'))
    expect(screen.getByTestId('path-template-input')).toBeTruthy()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('选择预置触发 onChange 并收起输入框', () => {
    const onChange = vi.fn()
    render(<PathTemplateField value={undefined} onChange={onChange} />)
    openSelect()
    // 选项以 title 属性承载模板文案；预置 2 为旧版扁平布局。
    fireEvent.click(screen.getByTitle(PATH_TEMPLATE_PRESETS[2]))
    expect(onChange).toHaveBeenCalledWith(PATH_TEMPLATE_PRESETS[2])
  })

  it('清空（allowClear）触发 onChange(undefined)', () => {
    const onChange = vi.fn()
    render(<PathTemplateField value={PRESET_0} onChange={onChange} />)
    const clear = document.querySelector('.ant-select-clear')
    expect(clear).toBeTruthy()
    // rc-select 的清空图标监听 mousedown（useAllowClear）。
    fireEvent.mouseDown(clear as Element)
    expect(onChange).toHaveBeenCalledWith(undefined)
  })

  it('自定义输入触发 onChange（空串归一为 undefined）', () => {
    const onChange = vi.fn()
    render(<PathTemplateField value="{roomid}" onChange={onChange} />)
    // 当前值非预置 → 已展开输入框
    const input = screen.getByTestId('path-template-input') as HTMLInputElement
    fireEvent.change(input, { target: { value: '{uname}/{year}' } })
    expect(onChange).toHaveBeenCalledWith('{uname}/{year}')
    fireEvent.change(input, { target: { value: '' } })
    expect(onChange).toHaveBeenCalledWith(undefined)
  })
})
