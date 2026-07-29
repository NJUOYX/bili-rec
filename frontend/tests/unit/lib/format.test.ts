import {
  formatBytes,
  formatDuration,
  formatRate,
  formatTimestamp,
  toPercent,
} from '../../../src/lib/format'

describe('formatBytes', () => {
  it('0/负数/非法值 → 0 B', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(-5)).toBe('0 B')
    expect(formatBytes(Number.NaN)).toBe('0 B')
    expect(formatBytes(Number.POSITIVE_INFINITY)).toBe('0 B')
  })

  it('B 级取整', () => {
    expect(formatBytes(512)).toBe('512 B')
  })

  it('KB/MB/GB/TB 保留 1 位小数', () => {
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(1024 ** 2 * 2.25)).toBe('2.3 MB')
    expect(formatBytes(1024 ** 3)).toBe('1.0 GB')
    expect(formatBytes(1024 ** 4 * 3)).toBe('3.0 TB')
  })

  it('超过 TB 不再进位', () => {
    expect(formatBytes(1024 ** 5)).toBe('1024.0 TB')
  })
})

describe('formatRate', () => {
  it('速率追加 /s 后缀', () => {
    expect(formatRate(1024 ** 2)).toBe('1.0 MB/s')
    expect(formatRate(0)).toBe('0 B/s')
  })
})

describe('formatDuration', () => {
  it('秒数 → HH:MM:SS', () => {
    expect(formatDuration(0)).toBe('00:00:00')
    expect(formatDuration(61)).toBe('00:01:01')
    expect(formatDuration(3661.9)).toBe('01:01:01')
    expect(formatDuration(360000)).toBe('100:00:00')
  })

  it('负数/非法值按 0 处理', () => {
    expect(formatDuration(-1)).toBe('00:00:00')
    expect(formatDuration(Number.NaN)).toBe('00:00:00')
  })
})

describe('toPercent', () => {
  it('0..1 → 0..100 取整', () => {
    expect(toPercent(0)).toBe(0)
    expect(toPercent(0.5)).toBe(50)
    expect(toPercent(0.876)).toBe(88)
    expect(toPercent(1)).toBe(100)
  })

  it('越界裁剪与非法值归 0', () => {
    expect(toPercent(-0.5)).toBe(0)
    expect(toPercent(1.5)).toBe(100)
    expect(toPercent(Number.NaN)).toBe(0)
  })
})

describe('formatTimestamp', () => {
  it('Unix 秒 → 本地日期时间', () => {
    const seconds = new Date(2026, 6, 29, 14, 5, 3).getTime() / 1000
    expect(formatTimestamp(seconds)).toBe('2026-07-29 14:05:03')
  })

  it('0/负数/非法值 → 占位符', () => {
    expect(formatTimestamp(0)).toBe('—')
    expect(formatTimestamp(-1)).toBe('—')
    expect(formatTimestamp(Number.NaN)).toBe('—')
  })
})
