import { useRealtime } from './ws/useRealtime'

export default function App() {
  // 页面加载即建立事件/异常两条 WS 连接（§7.3），状态供顶栏指示灯消费。
  useRealtime()
  return (
    <main className="app-shell">
      <h1>bili-rec</h1>
      <p>Bilibili 直播录制器 · Web 控制台</p>
    </main>
  )
}
