/**
 * 扫码登录页（frontend-design.md §8）。居中卡片承载 QrcodeLogin。
 */
import { Card, Flex, Typography } from 'antd'

import { QrcodeLogin } from '../components/QrcodeLogin'

export function LoginPage() {
  return (
    <Flex justify="center" style={{ paddingTop: 32 }}>
      <Card style={{ width: 360 }}>
        <Typography.Title level={4} style={{ textAlign: 'center' }}>
          扫码登录
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ textAlign: 'center' }}>
          登录后 Cookie 将写入全局设置，用于访问受限接口。
        </Typography.Paragraph>
        <QrcodeLogin />
      </Card>
    </Flex>
  )
}
