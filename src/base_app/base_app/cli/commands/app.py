"""
应用管理命令
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path
import click
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..core.client import APIClient
from ..core.utils import format_uptime, get_pid_file


console = Console()


@click.group()
def app_commands():
    """应用管理命令"""
    pass


@app_commands.command()
@click.option("--port", "-p", default=8888, help="服务端口")
@click.option("--host", "-h", default="0.0.0.0", help="绑定主机")
@click.option("--config", "-c", help="配置文件路径")
@click.option("--daemon", "-d", is_flag=True, help="后台运行")
@click.option("--reload", is_flag=True, help="开发模式，代码变更自动重载")
@click.option("--log-level", default="INFO", help="日志级别")
def start(port, host, config, daemon, reload, log_level):
    """启动 BaseApp 服务"""
    
    # 检查是否已经在运行
    if is_running():
        console.print("[red]✗[/red] BaseApp 已经在运行中")
        sys.exit(1)
    
    console.print("[blue]🚀 正在启动 BaseApp...[/blue]")
    
    # 构建启动命令
    cmd = [
        sys.executable, "-m", "base_app.server.main",
        "--host", host,
        "--port", str(port),
        "--log-level", log_level
    ]
    
    if config:
        cmd.extend(["--config", config])
    
    if reload:
        cmd.append("--reload")
    
    try:
        if daemon:
            # 后台运行
            console.print(f"[green]📁[/green] 配置文件: {config or '默认配置'}")
            console.print(f"[green]🌐[/green] 服务地址: http://{host}:{port}")
            
            # 启动进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # 保存PID
            save_pid(process.pid, port)
            
            # 等待服务启动
            if wait_for_service(host, port):
                console.print("[green]✅ BaseApp 启动成功！[/green]")
                console.print(f"[dim]进程ID: {process.pid}[/dim]")
                console.print(f"[dim]使用 'baseapp stop' 停止服务[/dim]")
            else:
                console.print("[red]✗ BaseApp 启动失败[/red]")
                sys.exit(1)
        else:
            # 前台运行
            console.print(f"[green]📁[/green] 配置文件: {config or '默认配置'}")
            console.print(f"[green]🌐[/green] 服务地址: http://{host}:{port}")
            console.print("[green]✅ BaseApp 启动成功！[/green]")
            console.print("[dim]按 Ctrl+C 停止服务[/dim]")
            
            subprocess.run(cmd)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]👋 BaseApp 已停止[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ 启动失败: {e}[/red]")
        sys.exit(1)


@app_commands.command()
@click.option("--force", "-f", is_flag=True, help="强制停止")
@click.option("--timeout", default=30, help="停止超时时间（秒）")
def stop(force, timeout):
    """停止 BaseApp 服务"""
    
    pid_info = get_pid_info()
    if not pid_info:
        console.print("[yellow]⚠️  BaseApp 未在运行[/yellow]")
        return
    
    pid = pid_info["pid"]
    console.print(f"[blue]🛑 正在停止 BaseApp (PID: {pid})...[/blue]")
    
    try:
        if force:
            # 强制停止
            os.kill(pid, signal.SIGKILL)
            console.print("[green]✅ BaseApp 已强制停止[/green]")
        else:
            # 优雅停止
            os.kill(pid, signal.SIGTERM)
            
            # 等待进程结束
            for _ in range(timeout):
                try:
                    os.kill(pid, 0)  # 检查进程是否存在
                    time.sleep(1)
                except OSError:
                    break
            else:
                # 超时后强制停止
                console.print("[yellow]⚠️  优雅停止超时，强制停止...[/yellow]")
                os.kill(pid, signal.SIGKILL)
            
            console.print("[green]✅ BaseApp 已停止[/green]")
        
        # 清理PID文件
        remove_pid_file()
        
    except OSError:
        console.print("[yellow]⚠️  进程可能已经停止[/yellow]")
        remove_pid_file()
    except Exception as e:
        console.print(f"[red]✗ 停止失败: {e}[/red]")
        sys.exit(1)


@app_commands.command()
def restart():
    """重启 BaseApp 服务"""
    
    console.print("[blue]🔄 正在重启 BaseApp...[/blue]")
    
    # 获取当前配置
    pid_info = get_pid_info()
    old_port = pid_info.get("port", 8000) if pid_info else 8000
    
    # 停止服务
    if is_running():
        stop.callback(force=False, timeout=30)
        time.sleep(2)
    
    # 启动服务
    start.callback(
        port=old_port,
        host="0.0.0.0", 
        config=None,
        daemon=True,
        reload=False,
        log_level="INFO"
    )


@app_commands.command()
@click.option("--json", "output_json", is_flag=True, help="JSON 格式输出")
@click.option("--verbose", "-v", is_flag=True, help="显示详细信息")
def status(output_json, verbose):
    """查看 BaseApp 状态"""
    
    if not is_running():
        if output_json:
            click.echo('{"status": "stopped"}')
        else:
            console.print("[red]🔴 BaseApp 未运行[/red]")
        return
    
    try:
        # 获取状态信息
        client = APIClient()
        health = client.get_system_health()
        agent_status = client.get_agent_status()
        
        if output_json:
            import json
            status_data = {
                "status": "running",
                "health": health,
                "agent": agent_status
            }
            click.echo(json.dumps(status_data, indent=2))
        else:
            # 创建状态表格
            table = Table(title="📊 BaseApp 状态")
            table.add_column("项目", style="cyan")
            table.add_column("状态", style="green")
            table.add_column("详情", style="dim")
            
            # 基本状态
            table.add_row("🟢 服务", "运行中", f"PID: {get_pid_info()['pid']}")
            table.add_row("🌐 URL", "可访问", f"http://localhost:{get_pid_info().get('port', 8000)}")
            table.add_row("⏱️ 运行时间", "正常", format_uptime(agent_status.get("uptime", 0)))
            
            # Agent状态
            table.add_row("🤖 Agent", agent_status.get("status", "unknown"), 
                         agent_status.get("agent_name", "Unknown"))
            table.add_row("💭 活跃会话", "正常", str(agent_status.get("active_sessions", 0)))
            table.add_row("🧠 内存", 
                         "启用" if agent_status.get("memory_enabled") else "禁用", "")
            table.add_row("🔧 工具", "已加载", 
                         f"{len(agent_status.get('tools', []))} 个")
            
            if verbose:
                table.add_row("📈 总对话", "统计", 
                             str(agent_status.get("total_conversations", 0)))
            
            console.print(table)
            
            if verbose:
                # 显示工具详情
                tools = agent_status.get("tools", [])
                if tools:
                    console.print("\n[bold]🔧 已加载工具:[/bold]")
                    for tool in tools:
                        console.print(f"  • {tool}")
    
    except requests.exceptions.ConnectionError:
        if output_json:
            click.echo('{"status": "unreachable"}')
        else:
            console.print("[red]🔴 BaseApp 服务无法访问[/red]")
    except Exception as e:
        if output_json:
            click.echo(f'{{"status": "error", "error": "{str(e)}"}}')
        else:
            console.print(f"[red]✗ 获取状态失败: {e}[/red]")


def is_running() -> bool:
    """检查服务是否运行"""
    pid_info = get_pid_info()
    if not pid_info:
        return False
    
    try:
        os.kill(pid_info["pid"], 0)
        return True
    except OSError:
        return False


def save_pid(pid: int, port: int):
    """保存PID信息"""
    pid_file = get_pid_file()
    pid_file.parent.mkdir(exist_ok=True)
    
    pid_info = {
        "pid": pid,
        "port": port,
        "start_time": time.time()
    }
    
    import json
    with open(pid_file, 'w') as f:
        json.dump(pid_info, f)


def get_pid_info() -> dict:
    """获取PID信息"""
    pid_file = get_pid_file()
    if not pid_file.exists():
        return {}
    
    try:
        import json
        with open(pid_file, 'r') as f:
            return json.load(f)
    except:
        return {}


def remove_pid_file():
    """删除PID文件"""
    pid_file = get_pid_file()
    if pid_file.exists():
        pid_file.unlink()


def wait_for_service(host: str, port: int, timeout: int = 30) -> bool:
    """等待服务启动"""
    import time
    import socket
    
    for _ in range(timeout):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                return True
        except:
            pass
        
        time.sleep(1)
    
    return False
