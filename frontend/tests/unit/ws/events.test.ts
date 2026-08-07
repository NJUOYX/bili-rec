/**
 * WS 消息解析守卫测试（frontend-design.md §7.1/§7.2）。
 *
 * 覆盖：合法事件解析、ping 判活、异常通道消息、畸形载荷拒绝。
 */
import {
  isPing,
  parseEventMessage,
  parseExceptionMessage,
  type AppEvent,
} from '../../../src/ws/events'

/** 构造后端 model_dump(mode="json") 形态的事件对象。 */
function makeEvent(type: string, data: Record<string, unknown>) {
  return {
    type,
    id: 'f81d4fae-7dec-11d0-a765-00a0c91e6bf6',
    date: '2026-07-28T12:00:00+08:00',
    data,
  }
}

describe('parseEventMessage', () => {
  it.each([
    'VideoFileCreatedEvent',
    'VideoFileCompletedEvent',
    'DanmakuFileCreatedEvent',
    'DanmakuFileCompletedEvent',
    'RawDanmakuFileCreatedEvent',
    'RawDanmakuFileCompletedEvent',
    'CoverImageDownloadedEvent',
    'VideoPostprocessingCompletedEvent',
  ] as const)('解析文件类事件 %s（room_id + path）', (type) => {
    const raw = makeEvent(type, { room_id: 123, path: '/rec/a.flv' })
    const parsed = parseEventMessage(raw)
    expect(parsed).not.toBeNull()
    const event = parsed as AppEvent
    expect(event.type).toBe(type)
    expect(event.data).toEqual({ room_id: 123, path: '/rec/a.flv' })
  })

  it('解析 PostprocessingCompletedEvent（room_id + files 列表）', () => {
    const raw = makeEvent('PostprocessingCompletedEvent', {
      room_id: 456,
      files: ['/rec/a.mp4', '/rec/a.xml'],
    })
    const parsed = parseEventMessage(raw)
    expect(parsed).toMatchObject({
      type: 'PostprocessingCompletedEvent',
      data: { room_id: 456, files: ['/rec/a.mp4', '/rec/a.xml'] },
    })
  })

  it('解析 TaskRefreshedEvent（仅 room_id，房间信息已刷新，#40）', () => {
    const raw = makeEvent('TaskRefreshedEvent', { room_id: 42 })
    const parsed = parseEventMessage(raw)
    expect(parsed).toMatchObject({
      type: 'TaskRefreshedEvent',
      data: { room_id: 42 },
    })
  })

  it('解析 Error 事件（name + detail）', () => {
    const raw = makeEvent('Error', { name: 'RuntimeError', detail: 'boom' })
    const parsed = parseEventMessage(raw)
    expect(parsed).toMatchObject({
      type: 'Error',
      data: { name: 'RuntimeError', detail: 'boom' },
    })
  })

  it('解析 ping 保活消息（仅判活，不作业务处理）', () => {
    const parsed = parseEventMessage({ type: 'ping' })
    expect(parsed).toEqual({ type: 'ping' })
    expect(parsed && isPing(parsed)).toBe(true)
  })

  it('事件消息不是 ping', () => {
    const raw = makeEvent('Error', { name: 'E', detail: 'd' })
    const parsed = parseEventMessage(raw)
    expect(parsed && isPing(parsed)).toBe(false)
  })

  it.each([
    [null],
    ['str'],
    [42],
    [{}],
    [{ type: 'UnknownEvent', id: 'x', date: 'y', data: {} }],
    [{ type: 'VideoFileCreatedEvent' }], // 缺 data
    [{ type: 'VideoFileCreatedEvent', id: 'x', date: 'y', data: { path: 1 } }],
    [
      {
        type: 'PostprocessingCompletedEvent',
        id: 'x',
        date: 'y',
        data: { room_id: 1, files: 'not-a-list' },
      },
    ],
    [{ type: 'Error', id: 'x', date: 'y', data: { name: 'E' } }], // 缺 detail
    [
      {
        type: 'TaskRefreshedEvent',
        id: 'x',
        date: 'y',
        data: { room_id: 'nope' },
      },
    ], // room_id 非数字
  ])('拒绝畸形载荷并返回 null：%j', (raw) => {
    expect(parseEventMessage(raw)).toBeNull()
  })
})

describe('parseExceptionMessage', () => {
  it('解析异常消息 {type, message, traceback}', () => {
    const raw = {
      type: 'RuntimeError',
      message: 'boom',
      traceback: 'Traceback ...',
    }
    expect(parseExceptionMessage(raw)).toEqual(raw)
  })

  it('解析 ping 保活消息', () => {
    const parsed = parseExceptionMessage({ type: 'ping' })
    expect(parsed).toEqual({ type: 'ping' })
    expect(parsed && isPing(parsed)).toBe(true)
  })

  it.each([[null], ['x'], [{}], [{ type: 'E', message: 'm' }]])(
    '拒绝畸形载荷并返回 null：%j',
    (raw) => {
      expect(parseExceptionMessage(raw)).toBeNull()
    },
  )
})
