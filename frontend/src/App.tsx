import { RouterProvider } from 'react-router'

import { createAppRouter } from './app/router'
import { useRealtime } from './ws/useRealtime'

const router = createAppRouter()

export default function App() {
  // 页面加载即建立事件/异常两条 WS 连接（§7.3），状态供顶栏指示灯消费。
  useRealtime()
  return <RouterProvider router={router} />
}
