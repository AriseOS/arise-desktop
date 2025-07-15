"""
OpenAI Provider for AgentBuilder
"""

import os
import asyncio
import logging
from typing import Optional
from openai import OpenAI
from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """OpenAI Provider 实现"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__(api_key, model)
        self.temperature = 0.7
        self.max_tokens = 4000
    
    async def _initialize_client(self):
        """初始化 OpenAI 客户端"""
        # 获取 API Key
        self.api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key 未设置")
        
        # 设置默认模型
        if not self.model:
            self.model = "gpt-4o"
        
        # 初始化客户端
        self._client = OpenAI(api_key=self.api_key)
        logger.info(f"OpenAI 客户端初始化完成，模型: {self.model}")
    
    async def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """生成响应"""
        if self._client is None:
            await self._initialize_client()
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            logger.info(f"OpenAI API 调用成功，模型: {self.model}")
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise