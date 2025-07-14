import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Provider } from 'react-redux';
import { ConfigProvider } from 'antd';
import { useTranslation } from 'react-i18next';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { store } from './store';
import { useAuth } from './hooks/useAuth';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import Dashboard from './pages/Dashboard';
import WorkspacePage from './pages/WorkspacePage';
import AgentContainer from './pages/AgentContainer';
import AgentTestPage from './pages/AgentTestPage';
import AgentManagePage from './pages/AgentManagePage';
import './App.css';

const AppContent: React.FC = () => {
  const { user, loading } = useAuth();
  const { t } = useTranslation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg">{t('common.loading', 'Loading...')}</div>
      </div>
    );
  }

  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <div className="App">
        <Routes>
          <Route 
            path="/" 
            element={<HomePage />} 
          />
          <Route 
            path="/login" 
            element={user ? <Navigate to="/dashboard" /> : <LoginPage />} 
          />
          <Route 
            path="/register" 
            element={user ? <Navigate to="/dashboard" /> : <RegisterPage />} 
          />
          <Route 
            path="/dashboard" 
            element={user ? <Dashboard /> : <Navigate to="/login" />} 
          />
          <Route 
            path="/workspace" 
            element={user ? <WorkspacePage /> : <Navigate to="/login" />} 
          />
          <Route 
            path="/users/:userId/agents/:agentId/*" 
            element={<AgentContainer />} 
          />
          <Route 
            path="/agent-test" 
            element={user ? <AgentTestPage /> : <Navigate to="/login" />} 
          />
          <Route 
            path="/agent-manage" 
            element={user ? <AgentManagePage /> : <Navigate to="/login" />} 
          />
        </Routes>
      </div>
    </Router>
  );
};

const AppWithI18n: React.FC = () => {
  const { i18n } = useTranslation();
  const antdLocale = i18n.language === 'zh-CN' ? zhCN : enUS;
  
  return (
    <ConfigProvider locale={antdLocale}>
      <AppContent />
    </ConfigProvider>
  );
};

const App: React.FC = () => {
  return (
    <Provider store={store}>
      <AppWithI18n />
    </Provider>
  );
};

export default App;