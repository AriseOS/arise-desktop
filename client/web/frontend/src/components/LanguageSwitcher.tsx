import React from 'react';
import { Select } from 'antd';
import { GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Option } = Select;

const LanguageSwitcher: React.FC = () => {
  const { i18n } = useTranslation();

  const handleLanguageChange = (language: string) => {
    i18n.changeLanguage(language);
  };

  const languages = [
    { code: 'zh-CN', name: '中文' },
    { code: 'en-US', name: 'English' }
  ];

  return (
    <Select
      value={i18n.language}
      onChange={handleLanguageChange}
      size="small"
      style={{ width: 100 }}
      suffixIcon={<GlobalOutlined />}
    >
      {languages.map(lang => (
        <Option key={lang.code} value={lang.code}>
          {lang.name}
        </Option>
      ))}
    </Select>
  );
};

export default LanguageSwitcher;