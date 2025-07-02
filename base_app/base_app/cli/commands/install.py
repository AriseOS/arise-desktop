"""
安装相关命令
"""
import click
import subprocess
import sys
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@click.group()
def install_commands():
    """安装相关命令"""
    pass


@install_commands.command()
@click.option("--force", is_flag=True, help="强制重新安装")
def chromium(force):
    """安装Chromium浏览器 (用于browser-use工具)"""
    
    # 检查playwright是否已安装
    try:
        import playwright
    except ImportError:
        console.print("❌ Playwright未安装，请先安装browser依赖:", style="red")
        console.print("   pip install 'baseapp[browser]'", style="cyan")
        return
    
    # 检查browser-use是否已安装
    try:
        import browser_use
    except ImportError:
        console.print("❌ browser-use未安装，请先安装browser依赖:", style="red")
        console.print("   pip install 'baseapp[browser]'", style="cyan")
        return
    
    console.print("🔧 开始安装Chromium浏览器...", style="blue")
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("正在下载和安装Chromium...", total=None)
            
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            if not force:
                cmd.append("--with-deps")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10分钟超时
            )
            
            progress.update(task, completed=True)
        
        if result.returncode == 0:
            console.print("✅ Chromium安装成功！", style="green")
            console.print("🎉 现在可以使用browser-use工具了", style="green")
        else:
            console.print(f"❌ Chromium安装失败:", style="red")
            console.print(result.stderr, style="red")
            
    except subprocess.TimeoutExpired:
        console.print("❌ 安装超时，请检查网络连接", style="red")
    except KeyboardInterrupt:
        console.print("\n⚠️ 安装被用户取消", style="yellow")
    except Exception as e:
        console.print(f"❌ 安装出错: {e}", style="red")


@install_commands.command()
def browser():
    """安装完整的browser依赖包 (包括Chromium)"""
    console.print("🔧 开始安装browser依赖...", style="blue")
    
    try:
        # 安装browser依赖
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "baseapp[browser]"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            console.print("❌ browser依赖安装失败:", style="red")
            console.print(result.stderr, style="red")
            return
        
        console.print("✅ browser依赖安装成功", style="green")
        
        # 自动安装Chromium
        console.print("🔧 正在安装Chromium...", style="blue")
        chromium.callback(force=False)
        
    except Exception as e:
        console.print(f"❌ 安装出错: {e}", style="red")


@install_commands.command()
def check():
    """检查安装状态"""
    console.print("🔍 检查BaseApp依赖安装状态...\n", style="blue")
    
    # 检查核心依赖
    deps = [
        ("pydantic", "核心数据验证"),
        ("fastapi", "Web框架"),
        ("click", "CLI框架"),
        ("rich", "终端美化"),
        ("openai", "OpenAI客户端"),
        ("anthropic", "Anthropic客户端"),
        ("mem0ai", "记忆管理"),
        ("browser_use", "浏览器自动化"),
        ("playwright", "浏览器驱动"),
    ]
    
    for package, desc in deps:
        try:
            __import__(package)
            console.print(f"✅ {package:<15} - {desc}", style="green")
        except ImportError:
            console.print(f"❌ {package:<15} - {desc} (未安装)", style="red")
    
    # 检查Chromium
    try:
        import playwright
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            if p.chromium.executable_path:
                console.print("✅ Chromium         - 浏览器 (已安装)", style="green")
            else:
                console.print("❌ Chromium         - 浏览器 (未安装)", style="red")
                console.print("   运行: baseapp install chromium", style="cyan")
    except:
        console.print("❌ Chromium         - 浏览器 (未安装)", style="red")
    
    console.print("\n💡 安装建议:", style="blue")
    console.print("   基础功能: pip install baseapp", style="cyan")
    console.print("   完整功能: pip install 'baseapp[all]'", style="cyan")
    console.print("   浏览器功能: pip install 'baseapp[browser]'", style="cyan")