import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Using inline translations for now to avoid JSON import issues

// For now, let's inline the translations to avoid JSON import issues
const zhCNTranslations = {
  "common": {
    "login": "登录",
    "register": "注册",
    "logout": "退出登录",
    "username": "用户名",
    "password": "密码",
    "loading": "加载中..."
  },
  "home": {
    "welcome": "欢迎，{username}！",
    "title": "ami.dev",
    "subtitle": "使用 AI 驱动的工具，快速创建、部署和管理您的智能代理应用",
    "dialogTitle": "对话框",
    "dialogSubtitle": "描述您想要创建的应用或功能，AI 将帮助您实现",
    "placeholder": "例如：创建一个待办事项管理应用，包含任务分类、优先级设置和进度跟踪功能...",
    "startBuilding": "开始构建",
    "quickGenerate": "按 {key} + Enter 快速生成",
    "tryExamples": "尝试这些示例：",
    "footer": "基于先进的 AI 技术构建",
    "examples": {
      "taskApp": "创建一个任务管理应用",
      "ecommerce": "设计一个电商网站首页",
      "chatbot": "构建一个聊天机器人",
      "dashboard": "开发一个数据分析dashboard"
    },
    "messages": {
      "pleaseLogin": "请先登录以使用对话功能",
      "enterRequirement": "请输入您的需求"
    }
  },
  "login": {
    "title": "ami.dev",
    "subtitle": "登录到您的账户",
    "usernameRequired": "请输入用户名",
    "passwordRequired": "请输入密码",
    "noAccount": "还没有账户？",
    "registerNow": "立即注册"
  },
  "nav": {
    "home": "首页",
    "workspace": "工作台",
    "dashboard": "控制台",
    "profile": "用户信息",
    "logout": "退出登录",
    "backToHome": "返回首页"
  }
};

const enUSTranslations = {
  "common": {
    "login": "Login",
    "register": "Register",
    "logout": "Logout",
    "username": "Username",
    "password": "Password",
    "loading": "Loading..."
  },
  "home": {
    "welcome": "Welcome, {username}!",
    "title": "ami.dev",
    "subtitle": "Use AI-powered tools to quickly create, deploy, and manage your intelligent agent applications",
    "dialogTitle": "Dialog",
    "dialogSubtitle": "Describe the application or feature you want to create, and AI will help you implement it",
    "placeholder": "For example: Create a todo management app with task categorization, priority settings, and progress tracking...",
    "startBuilding": "Start Building",
    "quickGenerate": "Press {key} + Enter to generate quickly",
    "tryExamples": "Try these examples:",
    "footer": "Built with advanced AI technology",
    "examples": {
      "taskApp": "Create a task management app",
      "ecommerce": "Design an e-commerce homepage",
      "chatbot": "Build a chatbot",
      "dashboard": "Develop a data analysis dashboard"
    },
    "messages": {
      "pleaseLogin": "Please login first to use the dialog feature",
      "enterRequirement": "Please enter your requirements"
    }
  },
  "login": {
    "title": "ami.dev",
    "subtitle": "Login to your account",
    "usernameRequired": "Please enter username",
    "passwordRequired": "Please enter password",
    "noAccount": "Don't have an account?",
    "registerNow": "Register now"
  },
  "nav": {
    "home": "Home",
    "workspace": "Workspace",
    "dashboard": "Dashboard",
    "profile": "Profile",
    "logout": "Logout",
    "backToHome": "Back to Home"
  }
};

const resources = {
  'zh-CN': {
    translation: zhCNTranslations
  },
  'en-US': {
    translation: enUSTranslations
  }
};

// Initialize i18n synchronously
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en-US',
    debug: import.meta.env.DEV, // Enable debug in development mode
    
    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      lookupLocalStorage: 'i18nextLng',
      caches: ['localStorage'],
    },

    interpolation: {
      escapeValue: false,
    },
    
    // Ensure synchronous initialization
    initImmediate: false,
  });

export default i18n;