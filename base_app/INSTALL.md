# BaseApp 安装指南

## 📦 安装方式

### 1. 基础安装
```bash
pip install baseapp
```

### 2. 完整安装 (推荐)
```bash
pip install 'baseapp[all]'
```

### 3. 分模块安装
```bash
# 仅浏览器功能
pip install 'baseapp[browser]'

# 仅开发工具
pip install 'baseapp[dev]'

# 仅Web功能
pip install 'baseapp[web]'
```

## 🌐 浏览器工具设置

使用browser-use工具需要安装Chromium浏览器：

### 方法1: 使用CLI命令 (推荐)
```bash
# 安装browser依赖和Chromium
baseapp install browser

# 或仅安装Chromium
baseapp install chromium

# 检查安装状态
baseapp install check
```

### 方法2: 手动安装
```bash
# 先安装browser依赖
pip install 'baseapp[browser]'

# 再安装Chromium
python -m playwright install chromium --with-deps
```

### 方法3: 使用安装脚本
```bash
# 运行安装后处理脚本
baseapp-install-chromium
```

## 🔧 环境变量配置

创建 `.env` 文件：
```bash
# OpenAI API Key (必需)
OPENAI_API_KEY=your_openai_api_key

# Anthropic API Key (可选)
ANTHROPIC_API_KEY=your_anthropic_api_key
```

## 🚀 快速验证

验证安装是否成功：
```bash
# 检查依赖状态
baseapp install check

# 启动Web服务
baseapp serve

# 命令行聊天
baseapp chat
```

## 🐛 常见问题

### 1. Chromium安装失败
```bash
# 检查网络连接，使用国内镜像
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com

# 重新安装
baseapp install chromium --force
```

### 2. 权限问题 (Linux/Mac)
```bash
# 使用用户安装
pip install --user 'baseapp[all]'

# 或使用虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install 'baseapp[all]'
```

### 3. 依赖冲突
```bash
# 升级pip
pip install --upgrade pip

# 清理缓存
pip cache purge

# 重新安装
pip install --force-reinstall 'baseapp[all]'
```

## 📋 系统要求

- **Python**: 3.8+
- **操作系统**: Windows, macOS, Linux
- **内存**: 建议 2GB+
- **磁盘**: 500MB+ (包含Chromium)

## 🔄 更新

```bash
# 更新到最新版本
pip install --upgrade 'baseapp[all]'

# 更新Chromium
baseapp install chromium --force
```

## 📚 下一步

- 查看 [配置文档](docs/CONFIGURATION.md)
- 阅读 [API文档](docs/API.md)
- 运行 [示例项目](examples/)