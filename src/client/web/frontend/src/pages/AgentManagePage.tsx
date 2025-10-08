/**
 * Agent管理页面
 * 提供完整的Agent管理功能：查看、创建、启动、停止、删除
 */

import React, { useState, useEffect } from 'react';
import { 
  Layout, Card, Table, Button, Typography, Space, Tag, Dropdown, 
  Modal, Form, Input, Select, message, Popconfirm, Row, Col, Statistic,
  Tooltip, Alert
} from 'antd';
import { 
  PlusOutlined, PlayCircleOutlined, StopOutlined, DeleteOutlined,
  MoreOutlined, EditOutlined, EyeOutlined, ReloadOutlined,
  RobotOutlined, SettingOutlined, ApiOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { agentService, AgentInfo, CreateAgentRequest } from '../services/agentAPI';

const { Header, Content } = Layout;
const { Title, Text } = Typography;
const { Option } = Select;

const AgentManagePage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  
  // 状态管理
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [systemStats, setSystemStats] = useState<any>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  // 加载数据
  const loadAgents = async () => {
    if (!user) return;
    
    setLoading(true);
    try {
      const userAgents = await agentService.getUserAgents(user.id.toString());
      setAgents(userAgents);
      
      // 加载系统统计
      const stats = await agentService.getSystemStats();
      setSystemStats(stats);
      
    } catch (error: any) {
      message.error(`加载Agent列表失败: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAgents();
  }, [user]);

  // 创建Agent
  const handleCreateAgent = async (values: CreateAgentRequest) => {
    if (!user) return;
    
    try {
      await agentService.createAgent(user.id.toString(), values);
      message.success('Agent创建成功');
      setCreateModalVisible(false);
      createForm.resetFields();
      loadAgents();
    } catch (error: any) {
      message.error(`创建Agent失败: ${error.message}`);
    }
  };

  // 启动Agent
  const handleStartAgent = async (agent: AgentInfo) => {
    if (!user) return;
    
    try {
      await agentService.startAgent(user.id.toString(), agent.agent_id);
      message.success(`Agent ${agent.name} 启动成功`);
      loadAgents();
    } catch (error: any) {
      message.error(`启动Agent失败: ${error.message}`);
    }
  };

  // 停止Agent
  const handleStopAgent = async (agent: AgentInfo) => {
    if (!user) return;
    
    try {
      await agentService.stopAgent(user.id.toString(), agent.agent_id);
      message.success(`Agent ${agent.name} 停止成功`);
      loadAgents();
    } catch (error: any) {
      message.error(`停止Agent失败: ${error.message}`);
    }
  };

  // 删除Agent
  const handleDeleteAgent = async (agent: AgentInfo) => {
    if (!user) return;
    
    try {
      await agentService.deleteAgent(user.id.toString(), agent.agent_id);
      message.success(`Agent ${agent.name} 删除成功`);
      loadAgents();
    } catch (error: any) {
      message.error(`删除Agent失败: ${error.message}`);
    }
  };

  // 编辑Agent
  const handleEditAgent = async (values: Pick<AgentInfo, 'name' | 'config'>) => {
    if (!user || !selectedAgent) return;
    
    try {
      await agentService.updateAgent(user.id.toString(), selectedAgent.agent_id, values);
      message.success('Agent更新成功');
      setEditModalVisible(false);
      setSelectedAgent(null);
      editForm.resetFields();
      loadAgents();
    } catch (error: any) {
      message.error(`更新Agent失败: ${error.message}`);
    }
  };

  // 查看Agent
  const handleViewAgent = (agent: AgentInfo) => {
    navigate(`/users/${user?.id}/agents/${agent.agent_id}`);
  };

  // 获取状态颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'green';
      case 'stopped': return 'default';
      case 'error': return 'red';
      default: return 'default';
    }
  };

  // 获取状态文本
  const getStatusText = (status: string) => {
    switch (status) {
      case 'running': return '运行中';
      case 'stopped': return '已停止';
      case 'error': return '错误';
      default: return '未知';
    }
  };

  // 表格列定义
  const columns = [
    {
      title: 'Agent名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: AgentInfo) => (
        <div>
          <div className="font-medium">{name}</div>
          <div className="text-xs text-gray-500">{record.agent_id}</div>
        </div>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => (
        <Tag color={type === 'baseapp' ? 'blue' : 'purple'}>
          {type === 'baseapp' ? 'BaseApp' : '自定义'}
        </Tag>
      ),
    },
    {
      title: '端口',
      dataIndex: 'port',
      key: 'port',
      render: (port: number) => <Text code>{port}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={getStatusColor(status)}>
          {getStatusText(status)}
        </Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record: AgentInfo) => {
        const menuItems = [
          {
            key: 'view',
            icon: <EyeOutlined />,
            label: '查看详情',
            onClick: () => handleViewAgent(record),
          },
          {
            key: 'edit',
            icon: <EditOutlined />,
            label: '编辑',
            onClick: () => {
              setSelectedAgent(record);
              editForm.setFieldsValue({
                name: record.name,
                config: JSON.stringify(record.config || {}, null, 2)
              });
              setEditModalVisible(true);
            },
            disabled: record.agent_id === 'baseapp',
          },
          { type: 'divider' as const },
          {
            key: 'delete',
            icon: <DeleteOutlined />,
            label: '删除',
            danger: true,
            disabled: record.agent_id === 'baseapp',
          },
        ];

        return (
          <Space>
            {record.status === 'stopped' ? (
              <Tooltip title="启动Agent">
                <Button
                  type="primary"
                  size="small"
                  icon={<PlayCircleOutlined />}
                  onClick={() => handleStartAgent(record)}
                />
              </Tooltip>
            ) : (
              <Tooltip title="停止Agent">
                <Button
                  size="small"
                  icon={<StopOutlined />}
                  onClick={() => handleStopAgent(record)}
                  disabled={record.agent_id === 'baseapp'}
                />
              </Tooltip>
            )}
            
            <Dropdown 
              menu={{ 
                items: menuItems.map(item => 
                  item.key === 'delete' 
                    ? {
                        ...item,
                        onClick: undefined,
                        label: (
                          <Popconfirm
                            title="确认删除"
                            description={`确定要删除Agent "${record.name}" 吗？此操作不可恢复。`}
                            onConfirm={() => handleDeleteAgent(record)}
                            okText="确认"
                            cancelText="取消"
                          >
                            <span className="text-red-600">删除</span>
                          </Popconfirm>
                        )
                      }
                    : item
                )
              }}
              trigger={['click']}
            >
              <Button size="small" icon={<MoreOutlined />} />
            </Dropdown>
          </Space>
        );
      },
    },
  ];

  return (
    <Layout className="min-h-screen bg-gray-50">
      <Header className="bg-white shadow-sm">
        <div className="flex items-center justify-between">
          <Title level={3} className="m-0 text-blue-600">
            <RobotOutlined className="mr-2" />
            Agent管理
          </Title>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadAgents}>
              刷新
            </Button>
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              onClick={() => setCreateModalVisible(true)}
            >
              创建Agent
            </Button>
          </Space>
        </div>
      </Header>

      <Content className="p-6">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* 统计信息 */}
          {systemStats && (
            <Row gutter={16}>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="总Agent数"
                    value={systemStats.totalAgents}
                    prefix={<RobotOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="运行中"
                    value={agents.filter(a => a.status === 'running').length}
                    valueStyle={{ color: '#3f8600' }}
                    prefix={<PlayCircleOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="已分配端口"
                    value={systemStats.portUsage?.allocated?.length || 0}
                    suffix={`/ ${systemStats.portUsage?.total || 20}`}
                    prefix={<ApiOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="可用端口"
                    value={systemStats.portUsage?.available?.length || 0}
                    prefix={<SettingOutlined />}
                  />
                </Card>
              </Col>
            </Row>
          )}

          {/* Agent列表 */}
          <Card title="Agent列表">
            <Table
              columns={columns}
              dataSource={agents}
              rowKey="agent_id"
              loading={loading}
              pagination={{
                pageSize: 10,
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => `共 ${total} 个Agent`,
              }}
            />
          </Card>
        </div>
      </Content>

      {/* 创建Agent对话框 */}
      <Modal
        title="创建新Agent"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          createForm.resetFields();
        }}
        footer={null}
      >
        <Alert
          message="创建Agent"
          description="新创建的Agent将自动分配一个可用端口，默认状态为停止。创建后可以通过操作按钮启动Agent。"
          type="info"
          showIcon
          className="mb-4"
        />
        
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateAgent}
        >
          <Form.Item
            name="name"
            label="Agent名称"
            rules={[{ required: true, message: '请输入Agent名称' }]}
          >
            <Input placeholder="例如：我的聊天机器人" />
          </Form.Item>

          <Form.Item
            name="type"
            label="Agent类型"
            rules={[{ required: true, message: '请选择Agent类型' }]}
            initialValue="custom"
          >
            <Select>
              <Option value="custom">自定义Agent</Option>
              <Option value="baseapp" disabled>BaseApp (系统保留)</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="config"
            label="配置 (JSON格式)"
          >
            <Input.TextArea
              rows={4}
              placeholder='{"key": "value"}'
            />
          </Form.Item>

          <Form.Item className="mb-0">
            <Space className="w-full justify-end">
              <Button onClick={() => setCreateModalVisible(false)}>
                取消
              </Button>
              <Button type="primary" htmlType="submit">
                创建
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑Agent对话框 */}
      <Modal
        title="编辑Agent"
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false);
          setSelectedAgent(null);
          editForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleEditAgent}
        >
          <Form.Item
            name="name"
            label="Agent名称"
            rules={[{ required: true, message: '请输入Agent名称' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="config"
            label="配置 (JSON格式)"
          >
            <Input.TextArea rows={6} />
          </Form.Item>

          <Form.Item className="mb-0">
            <Space className="w-full justify-end">
              <Button onClick={() => setEditModalVisible(false)}>
                取消
              </Button>
              <Button type="primary" htmlType="submit">
                保存
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  );
};

export default AgentManagePage;