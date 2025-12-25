"""
配置管理命令
"""
import os
import subprocess
import tempfile
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from ..core.client import APIClient
from ..core.utils import get_default_editor, safe_json_loads


console = Console()


@click.group()
def config_commands():
    """配置管理命令"""
    pass


@config_commands.command()
@click.argument("key", required=False)
def show(key):
    """显示配置"""
    try:
        client = APIClient()
        config_data = client.get_system_config(key)
        
        if key:
            # 显示特定配置
            value = config_data.get("value")
            console.print(f"[bold cyan]{key}:[/bold cyan] {value}")
        else:
            # 显示所有配置
            console.print("[bold]📋 BaseApp 配置[/bold]\n")
            _display_config_tree(config_data)
    
    except Exception as e:
        console.print(f"[red]✗ 获取配置失败: {e}[/red]")


@config_commands.command()
@click.argument("key")
@click.argument("value")
def set(key, value):
    """设置配置值"""
    console.print(f"[yellow]⚠️  暂不支持动态设置配置[/yellow]")
    console.print(f"[dim]请使用 'baseapp config edit' 编辑配置文件[/dim]")


@config_commands.command()
@click.argument("key")
def unset(key):
    """删除配置值"""
    console.print(f"[yellow]⚠️  暂不支持动态删除配置[/yellow]")
    console.print(f"[dim]请使用 'baseapp config edit' 编辑配置文件[/dim]")


@config_commands.command()
def edit():
    """编辑配置文件"""
    # 查找配置文件
    config_paths = [
        "./baseapp.yaml",
        "./config/baseapp.yaml",
        Path.home() / ".baseapp" / "config.yaml",
        "/etc/baseapp/config.yaml"
    ]
    
    config_file = None
    for path in config_paths:
        if Path(path).exists():
            config_file = Path(path)
            break
    
    if not config_file:
        # 创建默认配置文件
        config_file = Path("./config/baseapp.yaml")
        config_file.parent.mkdir(exist_ok=True)
        _create_default_config(config_file)
        console.print(f"[green]✅ 创建了默认配置文件: {config_file}[/green]")
    
    # 编辑配置文件
    editor = get_default_editor()
    console.print(f"[blue]📝 使用 {editor} 编辑配置文件: {config_file}[/blue]")
    
    try:
        subprocess.run([editor, str(config_file)])
        console.print("[green]✅ 配置文件编辑完成[/green]")
        console.print("[dim]使用 'baseapp config validate' 验证配置[/dim]")
    except Exception as e:
        console.print(f"[red]✗ 编辑失败: {e}[/red]")


@config_commands.command()
def validate():
    """验证配置"""
    console.print("[blue]🔍 验证配置文件...[/blue]")
    
    try:
        # 这里可以添加配置验证逻辑
        # 暂时只检查YAML格式
        config_paths = [
            "./baseapp.yaml",
            "./config/baseapp.yaml",
            Path.home() / ".baseapp" / "config.yaml"
        ]
        
        config_file = None
        for path in config_paths:
            if Path(path).exists():
                config_file = Path(path)
                break
        
        if not config_file:
            console.print("[red]✗ 未找到配置文件[/red]")
            return
        
        # 验证YAML格式
        with open(config_file, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        
        console.print(f"[green]✅ 配置文件格式正确: {config_file}[/green]")
        
        # 如果服务在运行，获取验证结果
        try:
            client = APIClient()
            health = client.get_system_health()
            if health.get("status") == "healthy":
                console.print("[green]✅ 服务配置验证通过[/green]")
            else:
                console.print("[yellow]⚠️  服务配置可能有问题[/yellow]")
        except:
            console.print("[dim]💡 启动服务以获取完整验证结果[/dim]")
    
    except yaml.YAMLError as e:
        console.print(f"[red]✗ YAML格式错误: {e}[/red]")
    except Exception as e:
        console.print(f"[red]✗ 验证失败: {e}[/red]")


@config_commands.command()
def create():
    """创建默认配置文件"""
    config_file = Path("./config/baseapp.yaml")
    
    if config_file.exists():
        console.print(f"[yellow]⚠️  配置文件已存在: {config_file}[/yellow]")
        if not click.confirm("是否覆盖现有配置文件？"):
            return
    
    config_file.parent.mkdir(exist_ok=True)
    _create_default_config(config_file)
    
    console.print(f"[green]✅ 创建默认配置文件: {config_file}[/green]")
    console.print("[dim]💡 使用 'baseapp config edit' 编辑配置[/dim]")


def _display_config_tree(config: dict, prefix: str = "", level: int = 0):
    """显示配置树"""
    if level > 3:  # 限制显示深度
        return
    
    for key, value in config.items():
        if isinstance(value, dict):
            console.print(f"{prefix}[bold cyan]{key}:[/bold cyan]")
            _display_config_tree(value, prefix + "  ", level + 1)
        else:
            # 隐藏敏感信息
            if any(sensitive in key.lower() for sensitive in ["key", "password", "secret", "token"]):
                display_value = "***HIDDEN***" if value else None
            else:
                display_value = value
            
            console.print(f"{prefix}[cyan]{key}:[/cyan] {display_value}")


def _create_default_config(config_path: Path):
    """创建默认配置文件"""
    default_config = {
        "app": {
            "name": "BaseApp",
            "version": "1.0.0",
            "host": "0.0.0.0",
            "port": 8000,
            "debug": False
        },
        "agent": {
            "name": "BaseApp Agent",
            "memory": {
                "enabled": True,
                "provider": "mem0",
                "config": {
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-4o-mini"
                    },
                    "vector_store": {
                        "provider": "chroma",
                        "path": "./data/chroma_db"
                    }
                }
            },
            "llm": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "${OPENAI_API_KEY}"
            },
            "tools": {
                "enabled": ["browser", "memory"],
                "browser": {
                    "headless": True,
                    "timeout": 30
                }
            }
        },
        "database": {
            "type": "sqlite",
            "url": "./data/baseapp.db"
        },
        "logging": {
            "level": "INFO",
            "file": "./logs/baseapp.log",
            "max_size": "10MB",
            "backup_count": 5
        }
    }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)