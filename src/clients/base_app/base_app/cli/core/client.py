"""
API客户端 - 与BaseApp服务器通信
"""
import requests
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin


class APIClient:
    """BaseApp API客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8888"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送HTTP请求"""
        url = urljoin(self.base_url, endpoint)
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"API request failed: {e}")
    
    def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """GET请求"""
        return self._request("GET", endpoint, **kwargs)
    
    def post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """POST请求"""
        return self._request("POST", endpoint, **kwargs)
    
    def put(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """PUT请求"""
        return self._request("PUT", endpoint, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """DELETE请求"""
        return self._request("DELETE", endpoint, **kwargs)
    
    # Chat API
    def send_message(self, message: str, session_id: str = None, user_id: str = "cli_user") -> Dict[str, Any]:
        """发送消息"""
        data = {
            "message": message,
            "user_id": user_id
        }
        if session_id:
            data["session_id"] = session_id
        
        return self.post("/api/v1/chat/message", json=data)
    
    def create_session(self, user_id: str = "cli_user", title: str = None) -> Dict[str, Any]:
        """创建会话"""
        data = {"user_id": user_id}
        if title:
            data["title"] = title
        
        return self.post("/api/v1/chat/session", json=data)
    
    def get_sessions(self, user_id: str = "cli_user") -> Dict[str, Any]:
        """获取会话列表"""
        return self.get("/api/v1/chat/sessions", params={"user_id": user_id})
    
    def get_session_history(self, session_id: str, limit: int = 50) -> Dict[str, Any]:
        """获取会话历史"""
        return self.get(f"/api/v1/chat/sessions/{session_id}/history", 
                       params={"limit": limit})
    
    def delete_session(self, session_id: str, user_id: str = "cli_user") -> Dict[str, Any]:
        """删除会话"""
        return self.delete(f"/api/v1/chat/sessions/{session_id}", 
                          params={"user_id": user_id})
    
    # Agent API
    def get_agent_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return self.get("/api/v1/agent/status")
    
    def get_agent_config(self) -> Dict[str, Any]:
        """获取Agent配置"""
        return self.get("/api/v1/agent/config")
    
    def restart_agent(self) -> Dict[str, Any]:
        """重启Agent"""
        return self.post("/api/v1/agent/restart")
    
    def get_agent_tools(self) -> Dict[str, Any]:
        """获取Agent工具"""
        return self.get("/api/v1/agent/tools")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取内存统计"""
        return self.get("/api/v1/agent/memory/stats")
    
    def clear_memory(self) -> Dict[str, Any]:
        """清理内存"""
        return self.post("/api/v1/agent/memory/clear")
    
    # System API
    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        return self.get("/api/v1/system/health")
    
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return self.get("/api/v1/system/info")
    
    def get_system_config(self, key: str = None) -> Dict[str, Any]:
        """获取系统配置"""
        params = {"key": key} if key else {}
        return self.get("/api/v1/system/config", params=params)
    
    def get_logs(self, level: str = "INFO", limit: int = 100, tail: bool = True) -> Dict[str, Any]:
        """获取系统日志"""
        params = {
            "level": level,
            "limit": limit,
            "tail": tail
        }
        return self.get("/api/v1/system/logs", params=params)