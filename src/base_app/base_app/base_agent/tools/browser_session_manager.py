"""
浏览器会话管理器 - 基于browser-use库
支持多个Agent共享同一个浏览器会话
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

# 导入browser-use的组件
try:
    from browser_use import Tools
    from browser_use.browser.session import BrowserSession
    from browser_use.browser.profile import BrowserProfile
    BROWSER_USE_AVAILABLE = True
    Controller = Tools  # 向后兼容
except ImportError:
    BROWSER_USE_AVAILABLE = False
    BrowserSession = None
    BrowserProfile = None
    Controller = None

logger = logging.getLogger(__name__)


class BrowserSessionInfo:
    """浏览器会话信息

    Note: dom_service has been removed as we now use DOMWatchdog's cached enhanced_dom_tree
    instead of creating separate DomService instances.
    """
    def __init__(self, session: BrowserSession, controller: Controller):
        self.session = session
        self.controller = controller
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.reference_count = 0  # 引用计数，用于判断是否可以清理


class BrowserSessionManager:
    """
    全局浏览器会话管理器

    特点：
    1. 单例模式，整个应用共享一个管理器
    2. 基于workflow_id管理browser-use的BrowserSession
    3. 支持会话复用和自动清理
    4. 完全兼容browser-use的架构
    """

    _instance = None
    _lock = asyncio.Lock()

    def __init__(self):
        if not BROWSER_USE_AVAILABLE:
            raise ImportError("browser-use库未安装，请先安装: pip install browser-use")

        self._sessions: Dict[str, BrowserSessionInfo] = {}
        self._cleanup_task = None
        self._session_timeout = timedelta(minutes=30)  # 30分钟未使用自动清理

    @classmethod
    async def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    # 启动清理任务
                    cls._instance._start_cleanup_task()
        return cls._instance

    def _start_cleanup_task(self):
        """启动定期清理任务"""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(300)  # 每5分钟检查一次
                await self._cleanup_expired_sessions()

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def _cleanup_expired_sessions(self):
        """清理过期的会话"""
        now = datetime.now()
        expired_sessions = []

        for session_id, info in self._sessions.items():
            # 如果会话超过30分钟未使用且没有引用，则清理
            if (info.reference_count == 0 and
                now - info.last_accessed > self._session_timeout):
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            logger.info(f"清理过期会话: {session_id}")
            await self.close_session(session_id)

    async def get_or_create_session(
        self,
        session_id: str,
        config_service=None,
        headless: bool = False,
        keep_alive: bool = True,
        cdp_url: Optional[str] = None
    ) -> BrowserSessionInfo:
        """
        获取或创建browser-use会话

        Args:
            session_id: 会话ID（通常使用workflow_id）
            config_service: 配置服务，用于获取用户数据目录
            headless: 是否无头模式
            keep_alive: 是否保持会话
            cdp_url: CDP URL for connecting to existing browser (e.g., http://localhost:9222)

        Returns:
            BrowserSessionInfo: 包含session和controller
        """
        # 如果会话已存在，直接返回
        if session_id in self._sessions:
            info = self._sessions[session_id]
            info.last_accessed = datetime.now()
            info.reference_count += 1
            logger.info(f"复用现有浏览器会话: {session_id}, 引用计数: {info.reference_count}")
            return info

        # 创建新的browser-use会话
        logger.info(f"创建新的浏览器会话: {session_id}")

        # 如果提供了CDP URL，使用CDP连接模式
        if cdp_url:
            logger.info(f"🔗 使用CDP连接到现有浏览器: {cdp_url}")
            profile = BrowserProfile(
                cdp_url=cdp_url,
                is_local=True,  # Important for local Chrome
                headless=False,  # Existing browser is visible
                keep_alive=True,  # Don't close browser when done
            )
        else:
            # 传统模式：启动新浏览器
            # 获取用户数据目录
            if config_service:
                user_data_dir = str(config_service.get_path("data.browser_data"))
            else:
                import tempfile
                user_data_dir = tempfile.mkdtemp(prefix="browser_data_")
                logger.warning(f"未提供config_service，使用临时目录: {user_data_dir}")

            # 创建browser-use的BrowserProfile
            profile = BrowserProfile(
                headless=headless,
                user_data_dir=user_data_dir,
                keep_alive=keep_alive,  # 保持浏览器运行
                proxy=None  # 可以添加代理配置
            )

        # 创建BrowserSession
        session = BrowserSession(browser_profile=profile)

        # 启动浏览器
        await session.start()

        # 创建Controller（Tools）
        # Note: DomService is no longer needed as we use DOMWatchdog's cached enhanced_dom_tree
        controller = Controller()  # browser-use的Tools实例

        # 保存会话信息
        info = BrowserSessionInfo(session, controller)
        info.reference_count = 1
        self._sessions[session_id] = info

        logger.info(f"浏览器会话创建成功: {session_id}")
        return info

    def release_session(self, session_id: str):
        """
        释放会话引用（不关闭）

        当Agent完成使用会话时调用，减少引用计数
        """
        if session_id in self._sessions:
            info = self._sessions[session_id]
            info.reference_count = max(0, info.reference_count - 1)
            info.last_accessed = datetime.now()
            logger.info(f"释放会话引用: {session_id}, 剩余引用: {info.reference_count}")

    async def close_session(self, session_id: str, force: bool = False):
        """
        关闭会话

        Args:
            session_id: 会话ID
            force: 是否强制关闭（忽略引用计数）
        """
        if session_id not in self._sessions:
            logger.warning(f"会话不存在: {session_id}")
            return

        info = self._sessions[session_id]

        # 检查引用计数
        if not force and info.reference_count > 0:
            logger.warning(f"会话仍有{info.reference_count}个引用，不能关闭: {session_id}")
            return

        try:
            # 关闭browser-use会话
            await info.session.stop()
            logger.info(f"浏览器会话已关闭: {session_id}")
        except Exception as e:
            logger.error(f"关闭会话失败: {session_id}, 错误: {e}")
        finally:
            # 从管理器中移除
            del self._sessions[session_id]

    async def close_all_sessions(self):
        """关闭所有会话"""
        session_ids = list(self._sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id, force=True)

        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()

    def get_session_info(self, session_id: str) -> Optional[BrowserSessionInfo]:
        """获取会话信息（不创建新会话）"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> Dict[str, dict]:
        """列出所有会话的状态"""
        result = {}
        for session_id, info in self._sessions.items():
            result[session_id] = {
                "created_at": info.created_at.isoformat(),
                "last_accessed": info.last_accessed.isoformat(),
                "reference_count": info.reference_count,
                "is_active": info.session.context is not None  # 检查浏览器是否活跃
            }
        return result