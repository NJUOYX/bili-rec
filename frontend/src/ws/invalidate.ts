/**
 * 事件 → Query 缓存失效映射（frontend-design.md §7.4/§6.3）。
 *
 * WS 事件不直接渲染业务数据，而是作为缓存失效信号源：
 * 事件 → invalidateQueries（queryKeys 键工厂，M28）→ 重新拉取 → UI 一致。
 *
 * | 事件                                   | 失效键                                        |
 * |----------------------------------------|-----------------------------------------------|
 * | VideoFile*                              | ['task', room, 'videos'] + ['task', room, 'data'] |
 * | DanmakuFile* / RawDanmakuFile*          | ['task', room, 'danmakus'] + ['task', room, 'data'] |
 * | CoverImageDownloadedEvent               | ['tasks'] 前缀（卡片封面）+ ['task', room, 'data'] |
 * | VideoPostprocessingCompletedEvent       | ['task', room, 'data']（后处理进度/产物）      |
 * | PostprocessingCompletedEvent            | 同上                                           |
 * | Error                                   | 无缓存动作（汇入事件/异常面板，§9）            |
 *
 * 运行态高频字段（dl_rate/rec_rate/…）由 ['task', room, 'data'] 承载，
 * 事件触发其失效即可，不为每个速率建推送通道。
 */
import type { QueryClient } from '@tanstack/react-query'

import { queryKeys } from '../api/queryKeys'
import type { AppEvent } from './events'

/** 失效指定房间的任务子资源 + 状态数据。 */
function invalidateTaskPart(
  queryClient: QueryClient,
  roomId: number,
  part: 'videos' | 'danmakus',
): void {
  void queryClient.invalidateQueries({
    queryKey: queryKeys.task(roomId, part),
  })
  void queryClient.invalidateQueries({
    queryKey: queryKeys.task(roomId, 'data'),
  })
}

/**
 * 把单个业务事件映射为缓存失效（§7.4）。
 * Error 事件无缓存动作（由事件日志 store / toast 处理）。
 */
export function applyEventToCache(
  queryClient: QueryClient,
  event: AppEvent,
): void {
  switch (event.type) {
    case 'VideoFileCreatedEvent':
    case 'VideoFileCompletedEvent':
      invalidateTaskPart(queryClient, event.data.room_id, 'videos')
      break
    case 'DanmakuFileCreatedEvent':
    case 'DanmakuFileCompletedEvent':
    case 'RawDanmakuFileCreatedEvent':
    case 'RawDanmakuFileCompletedEvent':
      invalidateTaskPart(queryClient, event.data.room_id, 'danmakus')
      break
    case 'CoverImageDownloadedEvent':
      // 封面展示在任务卡片（列表查询）与详情中：失效列表前缀 + 详情数据
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      void queryClient.invalidateQueries({
        queryKey: queryKeys.task(event.data.room_id, 'data'),
      })
      break
    case 'VideoPostprocessingCompletedEvent':
    case 'PostprocessingCompletedEvent':
      void queryClient.invalidateQueries({
        queryKey: queryKeys.task(event.data.room_id, 'data'),
      })
      break
    case 'Error':
      break // 无缓存动作
  }
}
