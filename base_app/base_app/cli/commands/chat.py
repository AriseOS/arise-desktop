"""
对话交互命令
"""
import sys
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from ..core.client import APIClient


console = Console()


@click.group()
def chat_commands():
    """对话交互命令"""
    pass


@chat_commands.command()
@click.option("--session-id", help="指定会话ID")
@click.option("--user-id", default="cli_user", help="指定用户ID")
def interactive(session_id, user_id):
    """交互式对话"""
    console.print(Panel.fit(
        "[bold blue]🤖 BaseApp 交互式对话[/bold blue]\n"
        "输入 'exit' 退出，'help' 查看帮助",
        title="欢迎使用 BaseApp"
    ))
    
    try:
        client = APIClient()
        
        # 创建或使用现有会话
        if not session_id:
            session_info = client.create_session(user_id, "CLI 交互对话")
            session_id = session_info["session_id"]
            console.print(f"[dim]会话ID: {session_id}[/dim]\n")
        
        # 开始对话循环
        while True:
            try:
                # 获取用户输入
                user_input = Prompt.ask("[bold green]You[/bold green]")
                
                if user_input.lower() in ['exit', 'quit', '退出']:
                    console.print("\n[yellow]👋 再见！感谢使用 BaseApp！[/yellow]")
                    break
                
                if user_input.lower() == 'help':
                    _show_chat_help()
                    continue
                
                if user_input.lower() == 'clear':
                    console.clear()
                    continue
                
                if user_input.lower() == 'history':
                    _show_session_history(client, session_id)
                    continue
                
                if not user_input.strip():
                    continue
                
                # 发送消息
                console.print("[dim]Agent 正在思考...[/dim]")
                
                with console.status("[bold green]Processing...") as status:
                    response = client.send_message(user_input, session_id, user_id)
                
                if response["success"]:
                    agent_message = response["assistant_message"]["content"]
                    processing_time = response["processing_time"]
                    
                    # 显示Agent回复
                    console.print(f"\n[bold blue]Agent[/bold blue]: {agent_message}")
                    console.print(f"[dim]({processing_time:.2f}秒)[/dim]\n")
                else:
                    console.print(f"[red]✗ 错误: {response.get('error', '未知错误')}[/red]\n")
            
            except KeyboardInterrupt:
                console.print("\n[yellow]👋 再见！感谢使用 BaseApp！[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]✗ 发生错误: {e}[/red]\n")
    
    except Exception as e:
        console.print(f"[red]✗ 无法连接到 BaseApp 服务: {e}[/red]")
        console.print("[dim]请确保 BaseApp 服务正在运行[/dim]")
        sys.exit(1)


@chat_commands.command()
@click.argument("message")
@click.option("--session-id", help="指定会话ID")
@click.option("--user-id", default="cli_user", help="指定用户ID")
@click.option("--timeout", default=30, help="响应超时时间")
def send(message, session_id, user_id, timeout):
    """发送单条消息"""
    try:
        client = APIClient()
        
        # 发送消息
        console.print(f"[blue]📤 发送消息:[/blue] {message}")
        
        with console.status("[bold green]Processing...") as status:
            response = client.send_message(message, session_id, user_id)
        
        if response["success"]:
            agent_message = response["assistant_message"]["content"]
            processing_time = response["processing_time"]
            session_id = response["session_id"]
            
            console.print(f"\n[bold blue]🤖 Agent 回复:[/bold blue]")
            console.print(agent_message)
            console.print(f"\n[dim]会话ID: {session_id}[/dim]")
            console.print(f"[dim]处理时间: {processing_time:.2f}秒[/dim]")
        else:
            console.print(f"[red]✗ 错误: {response.get('error', '未知错误')}[/red]")
            sys.exit(1)
    
    except Exception as e:
        console.print(f"[red]✗ 发送消息失败: {e}[/red]")
        sys.exit(1)


@chat_commands.command()
@click.argument("session_id", required=False)
@click.option("--user-id", default="cli_user", help="指定用户ID")
@click.option("--limit", default=20, help="显示消息数量")
@click.option("--format", "output_format", default="text", 
              type=click.Choice(["text", "json"]), help="输出格式")
def history(session_id, user_id, limit, output_format):
    """查看对话历史"""
    try:
        client = APIClient()
        
        if session_id:
            # 显示特定会话历史
            history_data = client.get_session_history(session_id, limit)
            messages = history_data["messages"]
            
            if output_format == "json":
                import json
                click.echo(json.dumps(history_data, indent=2, ensure_ascii=False))
            else:
                console.print(f"[bold]📜 会话历史 (ID: {session_id})[/bold]\n")
                
                if not messages:
                    console.print("[dim]暂无对话记录[/dim]")
                    return
                
                for msg in messages:
                    role = "🧑 用户" if msg["role"] == "user" else "🤖 Agent"
                    timestamp = msg["timestamp"][:19].replace("T", " ")
                    content = msg["content"]
                    
                    console.print(f"[cyan]{timestamp}[/cyan] {role}:")
                    console.print(f"  {content}\n")
        else:
            # 显示所有会话列表
            sessions_data = client.get_sessions(user_id)
            sessions = sessions_data["sessions"]
            
            if output_format == "json":
                import json
                click.echo(json.dumps(sessions_data, indent=2, ensure_ascii=False))
            else:
                console.print(f"[bold]📋 对话会话列表 (用户: {user_id})[/bold]\n")
                
                if not sessions:
                    console.print("[dim]暂无会话记录[/dim]")
                    return
                
                table = Table()
                table.add_column("会话ID", style="cyan")
                table.add_column("标题", style="green")
                table.add_column("消息数", style="yellow")
                table.add_column("更新时间", style="dim")
                
                for session in sessions:
                    table.add_row(
                        session["session_id"][:8] + "...",
                        session["title"],
                        str(session["message_count"]),
                        session["updated_at"][:19].replace("T", " ")
                    )
                
                console.print(table)
                console.print(f"\n[dim]使用 'baseapp chat history <session_id>' 查看具体对话[/dim]")
    
    except Exception as e:
        console.print(f"[red]✗ 获取历史失败: {e}[/red]")
        sys.exit(1)


@chat_commands.command()
@click.argument("session_id")
@click.option("--user-id", default="cli_user", help="指定用户ID")
def clear(session_id, user_id):
    """清理对话历史"""
    try:
        client = APIClient()
        
        # 确认删除
        console.print(f"[yellow]⚠️  即将删除会话: {session_id}[/yellow]")
        if not click.confirm("确定要删除此会话吗？"):
            console.print("[dim]操作已取消[/dim]")
            return
        
        # 删除会话
        result = client.delete_session(session_id, user_id)
        
        if result["success"]:
            console.print("[green]✅ 会话已删除[/green]")
        else:
            console.print(f"[red]✗ 删除失败: {result.get('message', '未知错误')}[/red]")
    
    except Exception as e:
        console.print(f"[red]✗ 删除会话失败: {e}[/red]")
        sys.exit(1)


def _show_chat_help():
    """显示对话帮助"""
    help_text = """
[bold]💡 对话帮助[/bold]

[cyan]基本命令:[/cyan]
• exit, quit, 退出    - 退出对话
• help               - 显示此帮助
• clear              - 清屏
• history            - 显示当前会话历史

[cyan]对话技巧:[/cyan]
• 可以进行自然语言对话
• 支持多轮上下文对话
• Agent 会记住之前的对话内容

[cyan]示例:[/cyan]
• "现在几点了？"
• "帮我分析一下这段代码"
• "你能做什么？"
"""
    console.print(Panel(help_text, title="帮助信息"))


def _show_session_history(client: APIClient, session_id: str):
    """显示会话历史"""
    try:
        history_data = client.get_session_history(session_id, 10)
        messages = history_data["messages"]
        
        if not messages:
            console.print("[dim]当前会话暂无历史记录[/dim]")
            return
        
        console.print("\n[bold]📜 最近10条对话:[/bold]")
        for msg in messages[-10:]:
            role = "🧑" if msg["role"] == "user" else "🤖"
            content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            console.print(f"{role} {content}")
        console.print()
    
    except Exception as e:
        console.print(f"[red]获取历史失败: {e}[/red]")