#!/usr/bin/env python3
"""
安装Chromium的后钩子脚本
在安装browser-use依赖后自动安装Chromium
"""
import subprocess
import sys
import os
from pathlib import Path


def check_playwright_installed():
    """检查playwright是否已安装"""
    try:
        import playwright
        return True
    except ImportError:
        return False


def install_chromium():
    """安装Chromium浏览器"""
    if not check_playwright_installed():
        print("⚠️ Playwright未安装，跳过Chromium安装")
        return False
    
    try:
        print("🔧 开始安装Chromium...")
        
        # 执行playwright install chromium --with-deps
        result = subprocess.run([
            sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print("✅ Chromium安装成功！")
            return True
        else:
            print(f"❌ Chromium安装失败: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Chromium安装超时")
        return False
    except Exception as e:
        print(f"❌ Chromium安装出错: {e}")
        return False


def main():
    """主函数"""
    print("🚀 BaseApp 安装后处理...")
    
    # 检查是否安装了browser依赖
    try:
        import browser_use
        print("📦 检测到browser-use，准备安装Chromium")
        install_chromium()
    except ImportError:
        print("ℹ️ 未安装browser-use，跳过Chromium安装")
    
    print("✨ 安装后处理完成！")


if __name__ == "__main__":
    main()