/**
 * 任务域测试样例数据：与后端 `_task_data_to_dict` 的运行时形态严格对齐
 * （task/__init__.py::TaskData dataclass asdict + RunningStatus 枚举值）。
 */

/** 单条 TaskData 原始载荷（可覆盖顶层字段与 task_status 字段）。 */
export function makeTaskDataRaw(
  overrides: Record<string, unknown> = {},
  statusOverrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    room_id: 23058,
    user_name: '3号直播间',
    room_title: '哔哩哔哩音悦台',
    area: '音乐',
    parent_area: '娱乐',
    live_status: true,
    task_status: {
      monitor_enabled: true,
      recorder_enabled: true,
      running_status: 'recording',
      stream_url: 'https://example.com/stream.flv',
      stream_host: 'example.com',
      dl_total: 1024 ** 2,
      dl_rate: 512 * 1024,
      rec_elapsed: 65.5,
      rec_total: 900 * 1024,
      rec_rate: 480 * 1024,
      danmu_total: 321,
      danmu_rate: 2.5,
      real_stream_format: 'flv',
      real_quality_number: 10000,
      recording_path: '/rec/23058.flv',
      postprocessor_status: 'remuxing',
      postprocessing_path: '/rec/23058.mp4',
      postprocessing_progress: 0.42,
      ...statusOverrides,
    },
    ...overrides,
  }
}

/** GET /tasks/data 的 ResponseMessage 成功载荷。 */
export function makeTasksPageResponse(
  tasks: Record<string, unknown>[],
  page = 1,
  size = 20,
): Record<string, unknown> {
  return {
    code: 0,
    message: '',
    data: { total: tasks.length, page, size, tasks },
  }
}
