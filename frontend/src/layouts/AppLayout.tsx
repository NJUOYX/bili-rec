/**
 * 应用布局外壳（frontend-design.md §14.4/§8.2）。
 *
 * 以 AntD Layout/Sider/Header 组件为骨架（最小化自定义 CSS）：
 * - 左侧可折叠导航：概览/任务/设置/登录/关于；
 * - 顶栏：页面标题 + 实时连接指示灯 + 主题切换 + 添加任务 + 更多菜单
 *   （应用状态 → 关于页；重启/退出随 M32 接线）。
 */
import {
  DashboardOutlined,
  InfoCircleOutlined,
  LoginOutlined,
  MoreOutlined,
  PlusOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  SettingOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Button, Dropdown, Layout, Menu, Typography, theme } from 'antd'
import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'

import { ConnectionIndicator } from '../components/ConnectionIndicator'
import { ThemeToggle } from '../components/ThemeToggle'

/** 左侧导航项（key 即路由路径）。 */
export const NAV_ITEMS = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '概览' },
  { key: '/tasks', icon: <VideoCameraOutlined />, label: '任务' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
  { key: '/login', icon: <LoginOutlined />, label: '登录' },
  { key: '/about', icon: <InfoCircleOutlined />, label: '关于' },
]

/** 由当前路径解析选中的导航项（前缀匹配，缺省概览）。 */
export function activeNavKey(pathname: string): string {
  return (
    NAV_ITEMS.map((item) => item.key).find(
      (key) => pathname === key || pathname.startsWith(`${key}/`),
    ) ?? '/dashboard'
  )
}

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()

  const selectedKey = activeNavKey(location.pathname)
  const title =
    NAV_ITEMS.find((item) => item.key === selectedKey)?.label ?? '概览'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="light"
        breakpoint="md"
        data-testid="app-sider"
      >
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: token.colorPrimary,
            fontWeight: 700,
            fontSize: collapsed ? 14 : 18,
          }}
        >
          {collapsed ? 'brec' : 'bili-rec'}
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={NAV_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            paddingInline: 24,
            background: token.colorBgContainer,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0, flex: 1 }}>
            {title}
          </Typography.Title>
          <ConnectionIndicator />
          <ThemeToggle />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate('/tasks/new')}
          >
            添加任务
          </Button>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'app-status',
                  icon: <InfoCircleOutlined />,
                  label: '应用状态',
                },
                {
                  key: 'restart',
                  icon: <ReloadOutlined />,
                  label: '重启',
                  disabled: true, // M32 接线
                },
                {
                  key: 'exit',
                  icon: <PoweroffOutlined />,
                  label: '退出',
                  disabled: true, // M32 接线
                },
              ],
              onClick: ({ key }) => {
                if (key === 'app-status') navigate('/about')
              },
            }}
          >
            <Button icon={<MoreOutlined />} aria-label="更多操作" />
          </Dropdown>
        </Layout.Header>
        <Layout.Content style={{ padding: 24 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  )
}
