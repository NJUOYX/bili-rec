/**
 * 单测：resolveBasename —— 从运行时 <base href> 解析 Router basename（§12）。
 */
import { afterEach, describe, expect, it } from 'vitest'

import { resolveBasename } from '../../../src/app/router'

function setBaseHref(href: string | null): void {
  document.querySelector('base')?.remove()
  if (href !== null) {
    const el = document.createElement('base')
    el.setAttribute('href', href)
    document.head.appendChild(el)
  }
}

describe('resolveBasename', () => {
  afterEach(() => {
    setBaseHref(null)
  })

  it('无 <base> 时返回 undefined（根路径部署）', () => {
    setBaseHref(null)
    expect(resolveBasename()).toBeUndefined()
  })

  it('base href="/" 归一化为 undefined', () => {
    setBaseHref('/')
    expect(resolveBasename()).toBeUndefined()
  })

  it('子路径 base href="/birec/" → "/birec"', () => {
    setBaseHref('/birec/')
    expect(resolveBasename()).toBe('/birec')
  })

  it('多级子路径 base href="/a/b/" → "/a/b"', () => {
    setBaseHref('/a/b/')
    expect(resolveBasename()).toBe('/a/b')
  })

  it('无尾斜杠子路径 base href="/birec" → "/birec"', () => {
    setBaseHref('/birec')
    expect(resolveBasename()).toBe('/birec')
  })
})
