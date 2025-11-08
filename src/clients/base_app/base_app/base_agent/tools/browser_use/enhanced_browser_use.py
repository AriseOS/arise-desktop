from typing import Optional, Any, Dict
from .browser_use import BrowserTool
from .user_behavior.monitor import SimpleUserBehaviorMonitor

class SimpleBrowserUseTool:
    """Simplified Browser-Use tool - only monitors and prints user behavior"""
    
    def __init__(self, enable_behavior_monitoring: bool = True, **browser_use_kwargs):
        # Initialize original Browser-Use tool
        self.browser_tool = BrowserTool(**browser_use_kwargs)
        
        # Initialize user behavior monitoring
        self.behavior_monitoring_enabled = enable_behavior_monitoring
        self.behavior_monitor: Optional[SimpleUserBehaviorMonitor] = None
        
        if enable_behavior_monitoring:
            self.behavior_monitor = SimpleUserBehaviorMonitor()
    
    async def execute(self, action: str, params: Dict[str, Any], **kwargs) -> Any:
        """Execute browser task with monitoring setup"""
        # Execute original Browser-Use functionality  
        result = await self.browser_tool.execute(action, params, **kwargs)
        
        # Set up user behavior monitoring after agent is created
        if (self.behavior_monitoring_enabled and self.behavior_monitor and 
            self.browser_tool.current_agent and hasattr(self.browser_tool.current_agent, 'browser_session')):
            try:
                await self.behavior_monitor.setup_monitoring(
                    self.browser_tool.current_agent.browser_session
                )
            except Exception as e:
                print(f"❌ Failed to set up behavior monitoring: {e}")
        
        return result
    
    async def cleanup(self) -> Any:
        """Cleanup browser and user behavior monitoring"""
        # Stop user behavior monitoring
        if self.behavior_monitor:
            await self.behavior_monitor.stop_monitoring()
        
        # Cleanup original Browser-Use functionality
        return await self.browser_tool._cleanup()
    
    # Proxy all Browser-Use original methods
    def __getattr__(self, name):
        """Proxy to original Browser-Use tool"""
        return getattr(self.browser_tool, name)