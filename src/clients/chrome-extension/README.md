# AgentCrafter Chrome 插件

AgentCrafter 工作流自动化平台的 Chrome 浏览器插件。

## 功能特性

- 📸 **页面捕获**: 捕获当前页面数据，包括 HTML、文本、链接、图片和表单
- ▶️ **工作流执行**: 直接从浏览器运行 AgentCrafter 工作流
- 🤖 **悬浮操作按钮**: 在任何页面快速访问插件功能
- 🔍 **元素交互**: 高亮、点击和填充网页元素
- 💾 **数据存储**: 本地存储捕获的数据和用户偏好设置

## 安装方法

### 开发模式

1. **克隆仓库**（如果还没有）：
   ```bash
   cd /Users/liuyihua/Code/AgentCrafter
   ```

2. **创建插件图标**（必需）：
   需要在 `client/web/chrome-extension/icons/` 目录下添加图标文件：
   - `icon16.png` - 16x16 像素
   - `icon48.png` - 48x48 像素
   - `icon128.png` - 128x128 像素

   可以使用任何图片编辑器创建简单的图标，或使用占位符图标。

3. **在 Chrome 中加载插件**：
   - 打开 Chrome 浏览器，访问 `chrome://extensions/`
   - 开启右上角的**开发者模式**
   - 点击**加载已解压的扩展程序**
   - 选择文件夹：`/Users/liuyihua/Code/AgentCrafter/client/web/chrome-extension`

4. **固定插件**（可选）：
   - 点击 Chrome 工具栏的拼图图标
   - 找到"AgentCrafter Extension"
   - 点击图钉图标将其固定显示

## 使用方法

### 1. 打开插件弹窗

点击 Chrome 工具栏中的插件图标打开弹窗界面。

### 2. 主要功能

#### 捕获当前页面
- 点击 **"📸 Capture Current Page"** 按钮
- 插件将捕获：
  - 页面 URL 和标题
  - 完整的 HTML 内容
  - 提取的文本
  - 链接和图片
  - 表单结构
  - 视口信息

#### 运行工作流
- 点击 **"▶️ Run Workflow"** 按钮
- 通过 AgentCrafter 后端执行配置的工作流
- 显示状态消息（运行中、成功、错误）

#### 打开控制台
- 点击 **"🏠 Open Dashboard"** 按钮
- 在 `http://localhost:3000` 打开 AgentCrafter Web 界面

### 3. 悬浮操作按钮

在任何网页上，你会在右下角看到一个悬浮的机器人图标（🤖）：
- 悬停查看动画效果
- 点击访问插件功能

### 4. 内容脚本功能

插件可以与网页交互：
- **高亮元素**: 可视化高亮特定元素
- **点击元素**: 程序化点击按钮/链接
- **填充表单**: 自动填充输入字段

## 配置

### API 端点

默认值：`http://localhost:8000`

更改 API 端点，使用 Chrome 存储：
```javascript
chrome.storage.local.set({ apiEndpoint: 'http://your-api-endpoint' });
```

### 自动捕获

启用页面加载时自动捕获：
```javascript
chrome.storage.local.set({ autoCapture: true });
```

### 身份认证

存储用户凭证用于 API 调用：
```javascript
chrome.storage.local.set({
  userToken: 'your-jwt-token',
  userId: 'your-user-id'
});
```

## 文件结构

```
chrome-extension/
├── manifest.json          # 插件配置文件
├── popup.html            # 弹窗界面 HTML
├── popup.js              # 弹窗逻辑
├── content.js            # 内容脚本（在网页中运行）
├── background.js         # 后台服务工作线程
├── icons/                # 插件图标
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md            # 本文件
```

## 权限说明

插件请求以下权限：
- **activeTab**: 访问当前标签页信息
- **storage**: 存储设置和捕获的数据
- **scripting**: 向网页注入脚本
- **host_permissions**: 访问本地主机 API（开发环境）

## 开发

### 重新加载插件

修改代码后：
1. 访问 `chrome://extensions/`
2. 点击 AgentCrafter Extension 卡片上的重新加载图标

### 调试插件

- **弹窗**: 右键点击插件图标 → "检查弹出窗口"
- **后台脚本**: 在插件页面点击"检查视图: service worker"
- **内容脚本**: 在任何页面使用常规开发者工具

### 查看控制台日志

- 后台脚本日志: `chrome://extensions/` → 检查 service worker
- 内容脚本日志: 常规开发者工具控制台
- 弹窗日志: 右键弹窗 → 检查

## 故障排除

### 插件无法加载
- 确保所有必需文件存在
- 检查 manifest.json 语法
- 如果缺少图标文件，创建占位符图标

### API 调用失败
- 验证后端运行在 `http://localhost:8000`
- 检查后端的 CORS 设置
- 确保用户已认证

### 内容脚本不工作
- 检查脚本是否允许在该页面上运行
- 验证 manifest.json 中的权限
- 重新加载插件

## 与 AgentCrafter 集成

插件集成以下组件：
- **后端 API** (`http://localhost:8000`): 执行工作流，管理 Agent
- **Web 控制台** (`http://localhost:3000`): 完整的平台界面
- **BaseApp**: Agent 执行引擎

## 未来增强

- [ ] 设置页面用于配置
- [ ] 工作流历史查看器
- [ ] 实时执行状态更新
- [ ] 多工作流支持
- [ ] 截图标注工具
- [ ] 导出捕获数据
- [ ] OAuth 认证流程

## 许可证

与 AgentCrafter 项目相同

## 支持

如有问题和疑问，请参考 AgentCrafter 主仓库。