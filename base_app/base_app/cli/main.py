"""
BaseApp CLI 主入口
"""
import click
from .commands.app import app_commands
from .commands.config import config_commands
from .commands.chat import chat_commands


@click.group()
@click.version_option(version="1.0.0", prog_name="baseapp")
@click.help_option("--help", "-h")
def cli():
    """
    BaseApp - AI Agent Assistant
    
    BaseApp 是一个基于 Agent 的应用程序，提供 Web UI、CLI 和 API 三种交互方式。
    """
    pass


# 注册命令组和单独命令
# 从 app_commands 组中提取各个命令
for command_name, command in app_commands.commands.items():
    cli.add_command(command, name=command_name)

cli.add_command(config_commands, name="config")
cli.add_command(chat_commands, name="chat")


if __name__ == "__main__":
    cli()