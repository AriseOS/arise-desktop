#!/usr/bin/env python3
"""
ScraperAgent 测试脚本

测试目标：
1. 初始化模式：使用笔记本电脑商品页面生成数据提取脚本并存储到KV
2. 执行模式：在冰箱商品页面从KV加载脚本执行数据提取
3. 脚本复用：使用相同脚本对不同冰箱商品页面进行数据提取
4. 验证脚本模式的"一次生成，多次使用"能力

测试流程：
- Initialize: https://allegro.pl/ -> laptopy -> Lenovo ThinkPad 商品页（生成脚本并存储到KV）
- Execute: https://allegro.pl/ -> lodówki -> 冰箱商品页（从KV加载脚本执行）

脚本模式逻辑：
- init阶段：生成数据提取脚本并存储到KV存储中
- exec阶段：从KV存储中加载脚本执行（可多次调用同一脚本）
"""

import asyncio
import json
import logging
from datetime import datetime
import sys
import os

# 添加 base_app 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'base_app'))

from base_app.base_agent.agents.scraper_agent import ScraperAgent
from base_app.base_agent.core.schemas import AgentContext
from base_app.base_agent.memory.memory_manager import MemoryManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('scraper_test.log')
    ]
)

logger = logging.getLogger(__name__)


class ScraperAgentTester:
    """ScraperAgent 测试器"""
    
    def __init__(self):
        self.agent = None
        self.memory_manager = None
        self.context = None
    
    async def setup(self):
        """初始化测试环境"""
        logger.info("初始化测试环境...")
        
        # 创建内存管理器
        self.memory_manager = MemoryManager()
        await self.memory_manager.initialize_storage()
        
        # 创建代理上下文
        self.context = AgentContext(
            workflow_id="test_scraper_workflow",
            step_id="test_step",
            memory_manager=self.memory_manager
        )
        
        # 创建 ScraperAgent (启用调试模式，使用脚本提取方式)
        self.agent = ScraperAgent(debug_mode=True, extraction_method='script')
        await self.agent.initialize(self.context)
        
        logger.info("测试环境初始化完成")
    
    async def test_initialize_mode(self):
        """测试初始化模式：生成脚本并存储到KV"""
        logger.info("=" * 60)
        logger.info("开始测试初始化模式")
        logger.info("=" * 60)
        
        # 初始化模式的输入数据
        initialize_data = {
            "mode": "initialize",
            "sample_path": [
                "https://allegro.pl/",
                "https://allegro.pl/kategoria/laptopy-491",
                "https://allegro.pl/oferta/ultrabook-lenovo-thinkpad-14-i5-8gb-500gb-win10-13486749942"
            ],
            "data_requirements": "product_name,price,sales_count_30d",  # 简化为字段列表
            "interaction_steps": [
                {
                    "action_type": "wait",
                    "parameters": {"seconds": 3},
                    "description": "等待页面加载完成"
                },
                {
                    "action_type": "scroll",
                    "parameters": {"down": True, "num_pages": 0.5},
                    "description": "向下滚动查看更多商品信息"
                }
            ]
        }
        
        try:
            # 验证输入数据
            is_valid = await self.agent.validate_input(initialize_data)
            logger.info(f"输入数据验证结果: {is_valid}")
            
            if not is_valid:
                logger.error("输入数据验证失败")
                return False
            
            # 执行初始化模式
            logger.info("执行初始化模式...")
            result = await self.agent.execute(initialize_data, self.context)
            
            # 输出结果
            logger.info("初始化模式执行结果:")
            self._print_result(result)
            
            if result.get('success'):
                logger.info("✅ 初始化模式测试通过")
                return True
            else:
                logger.error("❌ 初始化模式测试失败")
                return False
                
        except Exception as e:
            logger.error(f"初始化模式测试异常: {e}", exc_info=True)
            return False
    
    async def test_execute_mode_script(self):
        """测试执行模式：从KV加载脚本执行"""
        logger.info("=" * 60)
        logger.info("开始测试执行模式")
        logger.info("=" * 60)
        
        # 执行模式的输入数据 - 使用初始化阶段定义的方法
        execute_data = {
            "mode": "execute",
            "target_path": [
                "https://allegro.pl/",
                "https://allegro.pl/kategoria/agd-wolnostojace-lodowki-67430", 
                "https://allegro.pl/oferta/lodowka-mpm-285-kb-31-e-262-litry-40-db-180-cm-inox-szary-16597374181"
            ],
            "data_requirements": "product_name,price,sales_count_30d",
            "options": {
                "max_items": 1,  # 只提取一个商品的信息
                "timeout": 120   # 超时时间2分钟
            }
        }
        
        try:
            # 验证输入数据
            is_valid = await self.agent.validate_input(execute_data)
            logger.info(f"输入数据验证结果: {is_valid}")
            
            if not is_valid:
                logger.error("输入数据验证失败")
                return False
            
            # 执行执行模式
            logger.info("执行执行模式...")
            result = await self.agent.execute(execute_data, self.context)
            
            # 输出结果
            logger.info("执行模式执行结果:")
            self._print_result(result)
            
            # 验证提取的数据
            if result.get('success') and result.get('extracted_data'):
                logger.info("提取到的商品数据:")
                self._validate_extracted_data(result['extracted_data'])
                logger.info("✅ 执行模式测试通过")
                return True
            else:
                logger.error("❌ 执行模式测试失败")
                return False
                
        except Exception as e:
            logger.error(f"执行模式测试异常: {e}", exc_info=True)
            return False

    async def test_script_reuse(self):
        """测试脚本模式的重复使用能力"""
        logger.info("=" * 60)
        logger.info("开始测试脚本重复使用")
        logger.info("=" * 60)
        
        # 第二次执行，测试脚本复用
        execute_data_2 = {
            "mode": "execute",
            "target_path": [
                "https://allegro.pl/",
                "https://allegro.pl/kategoria/agd-wolnostojace-lodowki-67430", 
                "https://allegro.pl/oferta/lodowka-samsung-rb34t602dsa-ef-344l-60cm-srebrna-13486765234"  # 不同的冰箱商品
            ],
            "data_requirements": "product_name,price,sales_count_30d",
            "options": {
                "max_items": 1,
                "timeout": 120
            }
        }
        
        try:
            logger.info("第二次执行，测试脚本复用...")
            result = await self.agent.execute(execute_data_2, self.context)
            
            logger.info("脚本复用执行结果:")
            self._print_result(result)
            
            if result.get('success') and result.get('extracted_data'):
                logger.info("第二次提取到的商品数据:")
                self._validate_extracted_data(result['extracted_data'])
                logger.info("✅ 脚本复用测试通过")
                return True
            else:
                logger.error("❌ 脚本复用测试失败")
                return False
                
        except Exception as e:
            logger.error(f"脚本复用测试异常: {e}", exc_info=True)
            return False
    
    def _print_result(self, result):
        """格式化打印结果"""
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    def _validate_extracted_data(self, data):
        """验证提取的数据"""
        logger.info("数据验证:")
        
        if not isinstance(data, list):
            logger.warning("⚠️  提取的数据不是列表格式")
            data = [data] if isinstance(data, dict) else []
        
        for i, item in enumerate(data):
            logger.info(f"商品 {i+1}:")
            
            # 检查商品名称
            if 'product_name' in item:
                logger.info(f"  📝 商品名称: {item['product_name']}")
            else:
                logger.warning("  ⚠️  缺少商品名称")
            
            # 检查价格
            if 'price' in item:
                logger.info(f"  💰 价格: {item['price']}")
            else:
                logger.warning("  ⚠️  缺少价格信息")
            
            # 检查销售数量
            if 'sales_count_30d' in item:
                logger.info(f"  📊 30天销售数量: {item['sales_count_30d']}")
            else:
                logger.warning("  ⚠️  缺少销售数量信息")
            
            # 打印完整数据
            logger.info(f"  完整数据: {json.dumps(item, ensure_ascii=False)}")
    
    async def cleanup(self):
        """清理测试环境"""
        logger.info("清理测试环境...")
        if self.memory_manager:
            # 这里可以添加清理逻辑
            pass
        logger.info("测试环境清理完成")


async def run_tests():
    """运行所有测试"""
    print("🚀 开始 ScraperAgent 测试")
    print("=" * 80)
    
    tester = ScraperAgentTester()
    success_count = 0
    total_tests = 3  # 3个测试：init + exec + script_reuse
    
    try:
        # 设置测试环境
        await tester.setup()
        
        # 测试初始化模式
        if await tester.test_initialize_mode():
            success_count += 1
        
        # 等待一段时间再进行执行模式测试
        logger.info("等待5秒后继续执行模式测试...")
        await asyncio.sleep(5)
        
        # 测试执行模式 - 使用初始化阶段生成的脚本
        if await tester.test_execute_mode_script():
            success_count += 1
        
        # 等待一段时间再进行脚本复用测试
        logger.info("等待5秒后继续脚本复用测试...")
        await asyncio.sleep(5)
        
        # 测试脚本复用能力
        if await tester.test_script_reuse():
            success_count += 1
        
        # 清理
        await tester.cleanup()
        
        # 测试总结
        print("\n" + "=" * 80)
        print("🎯 测试总结")
        print("=" * 80)
        print(f"总测试数: {total_tests}")
        print(f"成功测试数: {success_count}")
        print(f"失败测试数: {total_tests - success_count}")
        print(f"成功率: {success_count/total_tests*100:.1f}%")
        
        if success_count == total_tests:
            print("🎉 所有测试通过！")
            return True
        else:
            print("❌ 部分测试失败")
            return False
            
    except Exception as e:
        logger.error(f"测试执行异常: {e}", exc_info=True)
        print("💥 测试执行异常")
        await tester.cleanup()
        return False


if __name__ == "__main__":
    print(f"测试开始时间: {datetime.now()}")
    
    # 运行测试
    result = asyncio.run(run_tests())
    
    print(f"测试结束时间: {datetime.now()}")
    
    # 退出码
    sys.exit(0 if result else 1)