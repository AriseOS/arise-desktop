import React, { useState } from 'react';
import { Handle, Position, NodeProps, useUpdateNodeInternals } from 'reactflow';
import { Modal, Typography, Card, Input, Button, Space, Form } from 'antd';

const { Text, Title } = Typography;
const { TextArea } = Input;

interface CustomNodeData {
  label: string;
  description?: string;
  type?: string;
  [key: string]: any; // 其他可能的属性
}

const CustomNode: React.FC<NodeProps<CustomNodeData>> = ({ data, id, className }) => {
  const [visible, setVisible] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [tempData, setTempData] = useState({ ...data });
  const updateNodeInternals = useUpdateNodeInternals();

  const showModal = () => {
    setVisible(true);
  };

  const handleCancel = () => {
    setVisible(false);
    setIsEditing(false);
  };

  const handleEdit = () => {
    setIsEditing(true);
    setTempData({ ...data });
  };

  const handleSave = () => {
    // 更新节点数据
    Object.assign(data, tempData);
    updateNodeInternals(id);
    setIsEditing(false);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setTempData({ ...data });
  };

  const handleFieldChange = (field: string, value: any) => {
    setTempData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  // 根据节点类型设置样式
  const getNodeStyle = () => {
    if (className?.includes('start-node')) {
      return 'border-2 border-green-500 bg-green-50';
    } else if (className?.includes('end-node')) {
      return 'border-2 border-red-500 bg-red-50';
    }
    return 'border-2 border-stone-400 bg-white';
  };

  return (
    <>
      <div 
        className={`px-4 py-2 shadow-md rounded-md transition-all duration-200 hover:shadow-lg cursor-pointer ${getNodeStyle()}`}
        onClick={showModal}
      >
        <Handle type="target" position={Position.Top} />
        <div className="flex items-center">
          <div className="flex-grow">
            <div className="font-bold text-sm">{data.label}</div>
            {data.type && (
              <div className="text-xs text-gray-500">{data.type}</div>
            )}
          </div>
        </div>
        <Handle type="source" position={Position.Bottom} />
      </div>

      <Modal
        title={<Title level={4}>{data.label} 详细信息</Title>}
        open={visible}
        onCancel={handleCancel}
        footer={null}
        width={600}
      >
        <Card size="small" className="mb-4">
          {isEditing ? (
            <Form layout="vertical">
              {Object.entries(tempData).map(([key, value]) => (
                <Form.Item key={key} label={key.charAt(0).toUpperCase() + key.slice(1)}>
                  {key === 'description' ? (
                    <TextArea 
                      value={value as string || ''} 
                      onChange={(e) => handleFieldChange(key, e.target.value)} 
                      autoSize={{ minRows: 2, maxRows: 6 }}
                    />
                  ) : (
                    <Input 
                      value={value as string || ''} 
                      onChange={(e) => handleFieldChange(key, e.target.value)} 
                    />
                  )}
                </Form.Item>
              ))}
            </Form>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(data).map(([key, value]) => (
                <React.Fragment key={key}>
                  <Text strong>{key.charAt(0).toUpperCase() + key.slice(1)}:</Text>
                  <Text className="col-span-2">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </Text>
                </React.Fragment>
              ))}
            </div>
          )}
          
          <div className="mt-4 flex justify-end">
            {isEditing ? (
              <Space>
                <Button onClick={handleCancelEdit}>取消</Button>
                <Button type="primary" onClick={handleSave}>保存</Button>
              </Space>
            ) : (
              <Button type="primary" onClick={handleEdit}>编辑节点</Button>
            )}
          </div>
        </Card>
      </Modal>
    </>
  );
};

export default CustomNode;