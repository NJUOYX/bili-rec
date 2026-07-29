/**
 * 添加任务页（frontend-design.md §8）。
 *
 * 输入房间号（支持短号）→ POST /tasks/{room_id}（useAddTask），
 * 成功后回到任务列表。表单校验：必填、正整数。
 */
import { App as AntdApp, Button, Card, Form, InputNumber, Space } from 'antd'
import { useNavigate } from 'react-router'

import { useAddTask } from '../../api/endpoints/tasks'

interface AddTaskForm {
  room_id: number
}

export function NewTaskPage() {
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()
  const [form] = Form.useForm<AddTaskForm>()
  const addTask = useAddTask()

  const onFinish = (values: AddTaskForm) => {
    addTask.mutate(values.room_id, {
      onSuccess: () => {
        message.success('任务已添加')
        navigate('/tasks')
      },
    })
  }

  return (
    <Card title="添加任务" style={{ maxWidth: 480 }}>
      <Form form={form} layout="vertical" onFinish={onFinish}>
        <Form.Item
          name="room_id"
          label="房间号"
          rules={[
            { required: true, message: '请输入房间号' },
            {
              type: 'number',
              min: 1,
              message: '房间号需为正整数',
            },
          ]}
          extra="支持直播间短号，添加后自动解析真实房号。"
        >
          <InputNumber
            style={{ width: '100%' }}
            placeholder="例如 23058"
            controls={false}
          />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button
              type="primary"
              htmlType="submit"
              loading={addTask.isPending}
            >
              添加
            </Button>
            <Button onClick={() => navigate('/tasks')}>取消</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  )
}
