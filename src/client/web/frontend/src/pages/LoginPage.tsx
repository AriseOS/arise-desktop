import React, { useEffect } from 'react';
import { Form, Input, Button, Card, message, Typography } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RootState } from '../store';
import { login, clearError } from '../store/authSlice';
import LanguageSwitcher from '../components/LanguageSwitcher';

const { Title } = Typography;

const LoginPage: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const { loading, error } = useSelector((state: RootState) => state.auth);

  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);

  useEffect(() => {
    if (error) {
      message.error(error);
    }
  }, [error]);

  const onFinish = (values: { username: string; password: string }) => {
    dispatch(login(values) as any);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="absolute top-4 right-4">
        <LanguageSwitcher />
      </div>
      <Card className="w-full max-w-md">
        <div className="text-center mb-8">
          <Title level={2}>{t('login.title')}</Title>
          <p className="text-gray-600">{t('login.subtitle')}</p>
        </div>
        
        <Form
          name="login"
          onFinish={onFinish}
          layout="vertical"
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: t('login.usernameRequired') }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={t('common.username')}
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: t('login.passwordRequired') }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('common.password')}
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              className="w-full"
            >
              {t('common.login')}
            </Button>
          </Form.Item>

          <div className="text-center">
            <span className="text-gray-600">{t('login.noAccount')}</span>
            <Link to="/register" className="text-blue-600 hover:text-blue-800 ml-1">
              {t('login.registerNow')}
            </Link>
          </div>
        </Form>
      </Card>
    </div>
  );
};

export default LoginPage;