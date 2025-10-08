"""
用户行为监控测试脚本
使用SimpleBrowserUseTool进行浏览器控制，并启用用户行为监控
"""
import asyncio
import sys
import os
import logging
import json
from datetime import datetime
from pathlib import Path

# 添加 src 目录到路径
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../src'))
sys.path.insert(0, src_path)

from browser_use.browser.session import BrowserSession
from browser_use.browser.profile import BrowserProfile
from base_app.base_app.base_agent.tools.browser_use.user_behavior.monitor import SimpleUserBehaviorMonitor
from base_app.base_app.server.core.config_service import ConfigService


async def test_behavior_monitoring():
    """用户行为监控测试"""

    # 启用调试日志
    logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

    print("=== 用户行为监控测试 ===")
    print("这个脚本只会打开浏览器，不执行任何自动化操作")
    print("请手动在浏览器中进行操作，所有操作将在控制台实时显示")
    print()

    # 创建操作记录列表
    operation_list = []

    # 加载测试配置
    test_config_path = Path(__file__).parent.parent.parent.parent / "test_config.yaml"
    print(f"test_config_path: {test_config_path}")
    config_service = ConfigService(config_path=str(test_config_path))

    # 从配置获取浏览器用户数据目录
    user_data_dir = str(config_service.get_path("data.browser_data"))
    
    # 创建浏览器配置
    profile = BrowserProfile(
        headless=False,  # 有头模式
        keep_alive=True,  # 保持浏览器运行
        user_data_dir=user_data_dir  # 使用指定的用户数据目录
    )
    
    # 创建浏览器会话
    browser_session = BrowserSession(browser_profile=profile)
    
    # 创建用户行为监控器，传入操作列表
    behavior_monitor = SimpleUserBehaviorMonitor(operation_list=operation_list)
    
    try:
        print("正在启动浏览器...")
        
        # 启动浏览器
        await browser_session.start()
        print("✅ 浏览器已打开！")
        
        # 设置用户行为监控
        print("正在设置用户行为监控...")
        await behavior_monitor.setup_monitoring(browser_session)
        
        print("\n🎯 用户行为监控已启用")
        print("\n请手动在浏览器中进行操作:")
        print("  • 点击页面元素")
        print("  • 输入文字")  
        print("  • 提交表单")
        print("  • 滚动页面")
        print("  • 按键盘按键")
        print()
        print("👀 监控输出将在下方实时显示...")
        print("=" * 60)
        
        print("\n🔄 等待用户操作...")
        print("提示: 请在打开的浏览器窗口中进行操作")
        print("按 Ctrl+C 可以结束测试")
        
        try:
            # 持续等待用户操作和监控输出
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n用户中断测试...")
        except Exception as e:
            print(f"\n程序异常: {e}")
        
    except Exception as e:
        print(f"❌ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        try:
            print("\n🧹 正在清理资源...")
            
            # Stop monitoring first
            await behavior_monitor.stop_monitoring()
            
            # Stop browser session with timeout
            try:
                await asyncio.wait_for(browser_session.stop(), timeout=5.0)
                print("✅ 浏览器会话已停止")
            except asyncio.TimeoutError:
                print("⚠️  浏览器会话停止超时，强制继续")
            except Exception as e:
                print(f"⚠️  停止浏览器会话时出错: {e}")
            
            print("✅ 清理完成")
            
            # 将操作记录写入文件
            if operation_list:
                filename = f"user_operations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                filepath = Path(__file__).parent / filename
                
                print(f"\n💾 保存 {len(operation_list)} 条操作记录到文件: {filename}")
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump({
                        'session_info': {
                            'start_time': datetime.now().isoformat(),
                            'total_operations': len(operation_list)
                        },
                        'operations': operation_list
                    }, f, indent=2, ensure_ascii=False)
                print(f"✅ 操作记录已保存到: {filepath}")
            else:
                print("\n📝 没有操作记录需要保存")
                
        except Exception as e:
            print(f"⚠️  清理时出错: {e}")
    
    print("\n🏁 测试结束")


if __name__ == "__main__":
    print("🚀 开始用户行为监控测试...")
    print("📋 需要环境变量: OPENAI_API_KEY 或 ANTHROPIC_API_KEY")
    print()
    
    asyncio.run(test_behavior_monitoring())
