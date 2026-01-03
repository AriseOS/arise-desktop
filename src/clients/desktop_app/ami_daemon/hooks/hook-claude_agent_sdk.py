# PyInstaller hook for claude_agent_sdk
# Collects the bundled Claude Code CLI binary

from PyInstaller.utils.hooks import collect_data_files

# Collect _bundled directory which contains the claude CLI binary
datas = collect_data_files('claude_agent_sdk', subdir='_bundled')
