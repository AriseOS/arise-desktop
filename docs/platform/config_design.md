# 简单配置管理设计

## 概述

本文档描述了 BaseApp 的简单配置管理方案，用于统一管理数据存储路径、网络端口等配置项，避免硬编码问题。

## 配置结构

### 1. 主配置文件 (`base_app/config/baseapp.yaml`)

```yaml
# 应用配置
app:
  name: BaseApp
  version: 1.0.0
  host: 0.0.0.0
  port: 8000
  debug: false

# 数据存储配置
data:
  # 数据文件根目录（使用标准目录）
  root: ~/.local/share/baseapp

  # 数据库文件
  databases:
    sessions: ${data.root}/sessions.db    # 会话存储
    kv: ${data.root}/agent_kv.db          # 键值存储

  # 向量数据库目录
  chroma_db: ${data.root}/chroma_db

  # 浏览器相关目录（使用缓存目录）
  browser_data: ~/.cache/baseapp/browser_data   # 浏览器用户数据
  debug: ${data.root}/debug                     # 调试输出

# 日志配置
logging:
  level: INFO
  file: ${data.root}/logs/baseapp.log
  max_size: 10MB
  backup_count: 5
```

### 2. 配置文件查找顺序

ConfigService 按以下优先级查找配置文件：

1. **`BASEAPP_CONFIG_PATH` 环境变量** - 明确指定的配置文件路径
2. **命令行参数** - 程序启动时传入的配置文件路径
3. **项目默认配置** - `base_app/config/baseapp.yaml`（基于代码位置）
4. **用户配置** - `~/.baseapp/config.yaml`
5. **系统配置** - `/etc/baseapp/config.yaml` 和 `/usr/local/etc/baseapp/config.yaml`

如果找不到任何配置文件，程序将报错退出。

### 3. 配置引用语法

- `${data.root}`: 引用配置内部的其他值
- `${OPENAI_API_KEY}`: 引用环境变量
- 支持相对路径、绝对路径、`~` 用户目录

## ConfigService 增强

### 配置文件发现机制

```python
def _find_config_file(self, config_path: Optional[str] = None) -> str:
    """查找配置文件"""
    # 1. 环境变量最高优先级
    if env_path := os.environ.get('BASEAPP_CONFIG_PATH'):
        ...

    # 2. 命令行参数
    if config_path:
        ...

    # 3. 项目默认配置（基于代码位置）
    code_dir = Path(__file__).parent.parent.parent  # base_app目录
    default_config = code_dir / 'config' / 'baseapp.yaml'

    # 4. 用户和系统配置
    search_paths = [
        Path.home() / '.baseapp' / 'config.yaml',
        Path('/etc/baseapp/config.yaml'),
        ...
    ]
```

### 路径解析功能

```python
class ConfigService:
    def resolve_path(self, path: str) -> Path:
        """
        解析路径，支持:
        - 绝对路径: 直接使用
        - ~ 用户目录: 展开为用户主目录
        - 环境变量: 自动展开
        - 相对路径: 基于配置文件所在目录
        """
        path = os.path.expanduser(path)  # 展开 ~
        path = os.path.expandvars(path)  # 展开环境变量

        if not os.path.isabs(path):
            # 相对路径相对于配置文件所在目录
            config_dir = Path(self.config_path).parent
            path = config_dir / path

        return Path(path).resolve()

    def get_path(self, key: str, create_parent: bool = True) -> Path:
        """
        获取路径配置并确保父目录存在
        """
        path_str = self.get(key)
        if not path_str:
            raise ValueError(f"Path config not found: {key}")

        path = self.resolve_path(str(path_str))

        if create_parent:
            path.parent.mkdir(parents=True, exist_ok=True)

        return path
```

## 代码改动

### 1. 数据库存储类

所有存储类现在必须接收 `config_service` 参数：

```python
# SQLiteSessionStorage
class SQLiteSessionStorage(SessionStorage):
    def __init__(self, config_service):
        self.database_path = config_service.get_path("data.databases.sessions")

# SQLiteKVStorage
class SQLiteKVStorage:
    def __init__(self, config_service):
        self.database_path = config_service.get_path("data.databases.kv")
```

### 2. Memory Manager

```python
class MemoryManager:
    def __init__(self, ..., config_service=None):
        if enable_kv_storage and config_service:
            self.kv_storage = SQLiteKVStorage(config_service=config_service)
```

### 3. Mem0Memory

```python
class Mem0Memory:
    def __init__(self, ..., config_service=None):
        if config_service:
            chroma_path = str(config_service.get_path("data.chroma_db"))
```

### 4. ScraperAgent

```python
class ScraperAgent:
    def __init__(self, ..., config_service=None):
        self.config_service = config_service

    def _create_browser_session(self):
        user_data_dir = str(self.config_service.get_path("data.browser_data"))

    async def _save_dom_to_file(self, ...):
        debug_dir = self.config_service.get_path("data.debug")
```

### 5. System API

```python
async def get_system_logs(request: Request, ...):
    config_service = get_config_service(request)
    log_file = config_service.get_path("logging.file", create_parent=False)
```

## 使用示例

### 1. 初始化服务

```python
# 创建配置服务
config_service = ConfigService()

# 初始化存储
storage = SQLiteSessionStorage(config_service=config_service)

# 初始化Agent服务
agent_service = AgentService(config_service)
```

### 2. 获取配置值

```python
# 获取普通配置
port = config_service.get("app.port", 8000)

# 获取路径配置
db_path = config_service.get_path("data.databases.sessions")

# 获取路径但不创建目录
log_file = config_service.get_path("logging.file", create_parent=False)
```

### 3. 环境变量覆盖

可以通过环境变量覆盖任何配置：

```bash
# 覆盖端口
export BASEAPP_APP_PORT=9000

# 覆盖数据目录
export BASEAPP_DATA_ROOT=/var/lib/baseapp

# 覆盖日志级别
export BASEAPP_LOGGING_LEVEL=DEBUG
```

## 优势

1. **无硬编码**: 所有路径和配置都从配置文件读取
2. **标准目录结构**: 遵循系统标准，数据在 `~/.local/share`，缓存在 `~/.cache`
3. **基于代码位置**: 默认配置相对于代码位置查找，不依赖工作目录
4. **灵活配置**: 支持环境变量覆盖、用户配置、系统配置
5. **配置引用**: 支持配置内部引用，减少重复
6. **自动创建目录**: 使用路径时自动创建父目录

## 迁移注意事项

### 破坏性变更

以下类的构造函数签名已更改，必须传入 `config_service`:

- `SQLiteSessionStorage(config_service)`
- `SQLiteKVStorage(config_service)`
- `ScraperAgent(..., config_service=config_service)`

### 配置文件要求

必须在配置文件中定义以下路径：

- `data.databases.sessions`: 会话数据库路径
- `data.databases.kv`: KV存储数据库路径
- `data.chroma_db`: 向量数据库目录
- `data.browser_data`: 浏览器数据目录
- `data.debug`: 调试输出目录
- `logging.file`: 日志文件路径

## 测试配置

测试时可以使用独立的配置文件：

```python
# 测试配置
test_config = ConfigService(config_path="test_config.yaml")

# 使用测试配置初始化
storage = SQLiteSessionStorage(config_service=test_config)
```

## 总结

这个简单的配置管理方案解决了硬编码问题，提供了统一的配置管理机制，同时保持了实现的简单性。所有的数据存储路径和关键配置都通过配置文件管理，提高了系统的可维护性和灵活性。