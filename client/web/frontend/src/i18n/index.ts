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
  },
  "workspace": {
    "title": "工作台",
    "agentOutput": "Agent输出框",
    "running": "运行中",
    "dialog": "对话框",
    "userRequirements": "用户描述新的修改需求：",
    "placeholder": "描述您想要创建或修改的功能，例如：创建一个待办事项应用，包含添加、删除、标记完成等功能...",
    "quickGenerate": "按{key}+Enter开始生成",
    "stop": "停止",
    "startGeneration": "开始生成",
    "userAgentDisplay": "User Agent展示",
    "frontend": "前端",
    "android": "Android",
    "preview": "预览区域",
    "previewDescription": "生成的{platform}将在这里展示",
    "frontendInterface": "前端界面",
    "androidApp": "Android应用",
    "frontendPreview": "前端预览",
    "androidSimulator": "Android模拟器",
    "waitingToStart": "等待开始生成...",
    "agentThinking": "Agent正在思考中...",
    "startAnalyzing": "开始分析用户需求：{input}",
    "generationStopped": "用户停止了生成过程",
    "generationComplete": "Agent生成功能开发中，敬请期待！",
    "steps": {
      "requirementAnalysis": "需求分析",
      "architectureDesign": "架构设计", 
      "codeGeneration": "代码生成",
      "testDeploy": "测试部署",
      "analyzing": "正在分析用户输入的需求...",
      "designingArchitecture": "设计应用架构和组件结构",
      "generatingCode": "生成相应的代码文件",
      "testingDeploying": "测试生成的代码并部署",
      "completed": "已完成",
      "inProgress": "进行中",
      "error": "出错",
      "waiting": "等待中"
    }
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
  },
  "workspace": {
    "title": "Workspace",
    "agentOutput": "Agent Output",
    "running": "Running",
    "dialog": "Dialog",
    "userRequirements": "Describe your new modification requirements:",
    "placeholder": "Describe the features you want to create or modify, for example: Create a todo management app with add, delete, and mark complete functions...",
    "quickGenerate": "Press {key}+Enter to start generation",
    "stop": "Stop",
    "startGeneration": "Start Generation",
    "userAgentDisplay": "User Agent Display",
    "frontend": "Frontend",
    "android": "Android",
    "preview": "Preview Area",
    "previewDescription": "Generated {platform} will be displayed here",
    "frontendInterface": "frontend interface",
    "androidApp": "Android application",
    "frontendPreview": "Frontend Preview",
    "androidSimulator": "Android Simulator",
    "waitingToStart": "Waiting to start generation...",
    "agentThinking": "Agent is thinking...",
    "startAnalyzing": "Starting to analyze user requirements: {input}",
    "generationStopped": "User stopped the generation process",
    "generationComplete": "Agent generation feature is under development, please stay tuned!",
    "steps": {
      "requirementAnalysis": "Requirement Analysis",
      "architectureDesign": "Architecture Design",
      "codeGeneration": "Code Generation", 
      "testDeploy": "Test & Deploy",
      "analyzing": "Analyzing user input requirements...",
      "designingArchitecture": "Designing application architecture and component structure",
      "generatingCode": "Generating corresponding code files",
      "testingDeploying": "Testing generated code and deploying",
      "completed": "Completed",
      "inProgress": "In Progress",
      "error": "Error",
      "waiting": "Waiting"
    }
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