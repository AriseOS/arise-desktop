import React from 'react';
import { Provider } from 'react-redux';
import { simpleStore } from './SimpleStore';

const SimpleContent: React.FC = () => {
  return (
    <div style={{ padding: '20px', backgroundColor: '#f0f0f0', minHeight: '100vh' }}>
      <h1>Simple App with Auth Redux Only</h1>
      <p>如果你看到这个页面，说明 Auth Redux slice 配置正常。</p>
      <p>If you see this page, Auth Redux slice is working correctly.</p>
    </div>
  );
};

const SimpleApp: React.FC = () => {
  return (
    <Provider store={simpleStore}>
      <SimpleContent />
    </Provider>
  );
};

export default SimpleApp;