/**
 * M30 DT：通用展示组件（frontend-design.md §8.2/§10.1）。
 */
import { render, screen } from '@testing-library/react'

import { ProgressBar } from '../../../src/components/ProgressBar'
import { RateGauge } from '../../../src/components/RateGauge'
import {
  RateSparkline,
  toPolylinePoints,
} from '../../../src/components/RateSparkline'
import { StatCard } from '../../../src/components/StatCard'
import {
  RUNNING_STATUS_COLORS,
  StatusBadge,
} from '../../../src/components/StatusBadge'
import { RUNNING_STATUSES } from '../../../src/lib/task'

describe('StatusBadge', () => {
  it('监控/录制器开启 + 录制中', () => {
    render(
      <StatusBadge
        status={{
          monitor_enabled: true,
          recorder_enabled: true,
          running_status: 'recording',
        }}
      />,
    )
    expect(screen.getByText('监控中')).toBeTruthy()
    expect(screen.getByText('录制器开')).toBeTruthy()
    expect(screen.getByText('录制中')).toBeTruthy()
  })

  it('监控/录制器关闭 + 已停止', () => {
    render(
      <StatusBadge
        status={{
          monitor_enabled: false,
          recorder_enabled: false,
          running_status: 'stopped',
        }}
      />,
    )
    expect(screen.getByText('监控关')).toBeTruthy()
    expect(screen.getByText('录制器关')).toBeTruthy()
    expect(screen.getByText('已停止')).toBeTruthy()
  })

  it('颜色映射覆盖全部运行状态', () => {
    for (const status of RUNNING_STATUSES) {
      expect(RUNNING_STATUS_COLORS[status]).toBeTruthy()
    }
  })
})

describe('RateGauge', () => {
  it('格式化展示下载/录制速率', () => {
    render(<RateGauge dlRate={1024 * 512} recRate={1024 * 256} />)
    expect(screen.getByTestId('rate-gauge').textContent).toContain('512.0 KB/s')
    expect(screen.getByTestId('rate-gauge').textContent).toContain('256.0 KB/s')
  })
})

describe('RateSparkline / toPolylinePoints', () => {
  it('空序列 → 空 points', () => {
    expect(toPolylinePoints([], 120, 32)).toBe('')
  })

  it('单点 → 基线段', () => {
    expect(toPolylinePoints([5], 120, 32)).toBe('2,30 118,30')
  })

  it('归一化：最大值贴顶、零值贴底', () => {
    const points = toPolylinePoints([0, 10], 120, 32)
    expect(points).toBe('2,30 118,2')
  })

  it('全零序列绘制基线', () => {
    const points = toPolylinePoints([0, 0, 0], 120, 32)
    expect(points.split(' ').every((p) => p.endsWith(',30'))).toBe(true)
  })

  it('渲染可访问的 SVG', () => {
    render(<RateSparkline values={[1, 2, 3]} label="总下载速率" />)
    expect(screen.getByRole('img', { name: '总下载速率' })).toBeTruthy()
  })
})

describe('ProgressBar', () => {
  it('比例转百分比渲染', () => {
    render(<ProgressBar ratio={0.42} label="混流中" />)
    expect(screen.getByText('混流中')).toBeTruthy()
    expect(screen.getByTestId('progress-bar').textContent).toContain('42%')
  })

  it('无标签时省略标签行', () => {
    render(<ProgressBar ratio={1} />)
    expect(screen.getByTestId('progress-bar').textContent).not.toContain(
      '混流中',
    )
  })
})

describe('StatCard', () => {
  it('渲染标题/数值/扩展区', () => {
    render(
      <StatCard title="录制中" value={3} extra={<span>extra-area</span>} />,
    )
    expect(screen.getByText('录制中')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
    expect(screen.getByText('extra-area')).toBeTruthy()
  })
})
