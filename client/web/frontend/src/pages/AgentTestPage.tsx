/**
 * Agent架构测试页面
 * 用于验证新的统一路由和API转发机制
 */

import React, { useState, useEffect } from 'react';
import { Layout, Card, Button, Typography, Space, Alert, Spin, Descriptions, message } from 'antd';
import { 
  ExperimentOutlined, ApiOutlined, CheckCircleOutlined, 
  CloseCircleOutlined, ReloadOutlined 
} from '@ant-design/icons';
import { agentService } from '../services/agentAPI';
import { agentRegistry } from '../services/agentRegistry';

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;

interface TestResult {
  name: string;
  status: 'success' | 'error' | 'pending';
  message: string;
  details?: any;
}

const AgentTestPage: React.FC = () => {
  const [testResults, setTestResults] = useState<TestResult[]>([]);
  const [testing, setTesting] = useState(false);

  const runTests = async () => {
    setTesting(true);
    setTestResults([]);
    
    const tests: TestResult[] = [];

    // 测试1: Agent注册表初始化
    try {
      await agentRegistry.initialize();
      const stats = await agentRegistry.getStats();
      tests.push({
        name: 'Agent注册表初始化',
        status: 'success',
        message: `成功初始化，发现 ${stats.totalAgents} 个Agent`,
        details: stats
      });
    } catch (error: any) {
      tests.push({
        name: 'Agent注册表初始化',
        status: 'error',
        message: error.message,
        details: error
      });
    }

    setTestResults([...tests]);

    // 测试2: 获取BaseApp Agent信息
    try {
      const baseappInfo = await agentService.getAgentInfo('1', 'baseapp');
      tests.push({
        name: '获取BaseApp Agent信息',
        status: 'success',
        message: `成功获取BaseApp信息，端口: ${baseappInfo.port}`,
        details: baseappInfo
      });
    } catch (error: any) {
      tests.push({
        name: '获取BaseApp Agent信息',
        status: 'error',
        message: error.message,
        details: error
      });
    }

    setTestResults([...tests]);

    // 测试3: 获取用户所有Agent
    try {
      const userAgents = await agentService.getUserAgents('1');
      tests.push({
        name: '获取用户所有Agent',
        status: 'success',
        message: `成功获取 ${userAgents.length} 个Agent`,
        details: userAgents
      });
    } catch (error: any) {
      tests.push({
        name: '获取用户所有Agent',
        status: 'error',
        message: error.message,
        details: error
      });
    }

    setTestResults([...tests]);

    // 测试4: BaseApp健康检查 (通过网关)
    try {
      const healthResponse = await agentService.proxyAgentRequest('1', 'baseapp', '/health', 'GET');
      tests.push({
        name: 'BaseApp健康检查 (通过网关)',
        status: 'success',
        message: '网关转发成功，BaseApp响应正常',
        details: healthResponse
      });
    } catch (error: any) {
      tests.push({
        name: 'BaseApp健康检查 (通过网关)',
        status: 'error',
        message: `网关转发失败: ${error.message}`,
        details: error
      });
    }

    setTestResults([...tests]);

    // 测试5: 网关状态检查
    try {
      const gatewayHealth = await agentService.getGatewayHealth();
      tests.push({
        name: '网关状态检查',
        status: 'success',
        message: '网关运行正常',
        details: gatewayHealth
      });
    } catch (error: any) {
      tests.push({
        name: '网关状态检查',
        status: 'error',
        message: error.message,
        details: error
      });
    }

    setTestResults([...tests]);

    // 测试6: Agent状态检查
    try {
      const agentStatus = await agentService.getAgentStatus('baseapp');
      tests.push({
        name: 'BaseApp状态检查',
        status: agentStatus.status === 'running' ? 'success' : 'error',
        message: `Agent状态: ${agentStatus.status}`,
        details: agentStatus
      });
    } catch (error: any) {
      tests.push({
        name: 'BaseApp状态检查',
        status: 'error',
        message: error.message,
        details: error
      });
    }

    setTestResults([...tests]);
    setTesting(false);
    
    // 显示测试完成消息
    const successCount = tests.filter(t => t.status === 'success').length;
    const totalCount = tests.length;
    
    if (successCount === totalCount) {
      message.success(`所有测试通过! (${successCount}/${totalCount})`);
    } else {
      message.warning(`测试完成: ${successCount}/${totalCount} 个测试通过`);
    }
  };

  useEffect(() => {
    // 页面加载时自动运行测试
    runTests();
  }, []);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircleOutlined className="text-green-500" />;
      case 'error':
        return <CloseCircleOutlined className="text-red-500" />;
      default:
        return <Spin size="small" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'border-green-200 bg-green-50';
      case 'error':
        return 'border-red-200 bg-red-50';
      default:
        return 'border-gray-200 bg-gray-50';
    }
  };

  return (
    <Layout className="min-h-screen bg-gray-50">
      <Header className="bg-white shadow-sm">
        <div className="flex items-center justify-between">
          <Title level={3} className="m-0 text-blue-600">
            <ExperimentOutlined className="mr-2" />
            Agent架构测试
          </Title>
          <Button 
            type="primary" 
            icon={<ReloadOutlined />}
            loading={testing}
            onClick={runTests}
          >
            重新测试
          </Button>
        </div>
      </Header>

      <Content className="p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* 测试说明 */}
          <Card>
            <Alert
              message="Agent架构测试说明"
              description={
                <div>
                  <Paragraph>
                    这个页面用于测试新的Agent架构组件是否正常工作，包括：
                  </Paragraph>
                  <ul className="list-disc list-inside space-y-1 text-sm">
                    <li>Agent注册表服务 - 管理Agent与端口的映射关系</li>
                    <li>API网关转发 - 统一路由和请求转发机制</li>
                    <li>BaseApp集成 - 验证现有BaseApp在新架构下的兼容性</li>
                    <li>健康检查 - 确保所有服务组件运行正常</li>
                  </ul>
                </div>
              }
              type="info"
              showIcon
            />
          </Card>

          {/* 测试结果 */}
          <Card title={
            <span>
              <ApiOutlined className="mr-2" />
              测试结果 ({testResults.filter(t => t.status === 'success').length}/{testResults.length})
            </span>
          }>
            <div className="space-y-4">
              {testResults.length === 0 && testing && (
                <div className="text-center py-8">
                  <Spin size="large" />
                  <div className="mt-4 text-gray-600">正在运行测试...</div>
                </div>
              )}

              {testResults.map((result, index) => (
                <div 
                  key={index}
                  className={`border rounded-lg p-4 ${getStatusColor(result.status)}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-3">
                      {getStatusIcon(result.status)}
                      <div>
                        <div className="font-medium">{result.name}</div>
                        <div className="text-sm text-gray-600 mt-1">{result.message}</div>
                        
                        {result.details && (
                          <details className="mt-2">
                            <summary className="text-xs text-blue-600 cursor-pointer">
                              查看详细信息
                            </summary>
                            <pre className="text-xs bg-gray-100 p-2 rounded mt-2 overflow-auto">
                              {JSON.stringify(result.details, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* 测试总结 */}
          {testResults.length > 0 && !testing && (
            <Card title="测试总结">
              <Descriptions column={2}>
                <Descriptions.Item label="总测试数">
                  {testResults.length}
                </Descriptions.Item>
                <Descriptions.Item label="成功数">
                  <Text type="success">
                    {testResults.filter(t => t.status === 'success').length}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="失败数">
                  <Text type="danger">
                    {testResults.filter(t => t.status === 'error').length}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="成功率">
                  <Text strong>
                    {Math.round((testResults.filter(t => t.status === 'success').length / testResults.length) * 100)}%
                  </Text>
                </Descriptions.Item>
              </Descriptions>
            </Card>
          )}
        </div>
      </Content>
    </Layout>
  );
};

export default AgentTestPage;