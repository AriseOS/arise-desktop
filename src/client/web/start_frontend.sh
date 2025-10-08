#!/bin/bash
# 启动前端开发服务器

cd frontend

# 检查是否已安装 Node.js
if ! command -v node &> /dev/null; then
    echo "错误: 请先安装 Node.js"
    exit 1
fi

# 检查是否已安装 npm
if ! command -v npm &> /dev/null; then
    echo "错误: 请先安装 npm"
    exit 1
fi

# 安装依赖
if [ ! -d "node_modules" ]; then
    echo "正在安装前端依赖..."
    npm install
fi

# 启动开发服务器
echo "启动前端开发服务器..."
npm start