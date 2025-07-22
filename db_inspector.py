#!/usr/bin/env python3
"""
数据库检查脚本 - 快速查看 AgentCrafter 数据库内容
"""
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 添加client/web/backend到Python路径
backend_path = os.path.join(os.path.dirname(__file__), 'client', 'web', 'backend')
sys.path.insert(0, backend_path)

from database import (
    User, UserSession, ChatHistory, AgentBuild, 
    AgentBuildSession, GeneratedAgent
)
from config import get_database_url, get_database_config

def create_db_session():
    """创建数据库连接"""
    db_config = get_database_config()
    engine = create_engine(
        db_config["url"],
        connect_args=db_config.get("connect_args", {})
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal(), engine

def print_separator(title):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def check_users(session):
    """检查用户表"""
    print_separator("用户信息 (Users)")
    users = session.query(User).all()
    
    if not users:
        print("❌ 暂无用户数据")
        return
    
    print(f"📊 总用户数: {len(users)}")
    print("\n用户列表:")
    for user in users:
        status = "🟢 活跃" if user.is_active else "🔴 禁用"
        admin = "👑 管理员" if user.is_admin else "👤 普通用户"
        last_login = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "从未登录"
        
        print(f"  ID: {user.id:2d} | {user.username:15s} | {user.email:25s}")
        print(f"       {status} | {admin} | 最后登录: {last_login}")
        print()

def check_sessions(session):
    """检查用户会话"""
    print_separator("用户会话 (User Sessions)")
    sessions = session.query(UserSession).all()
    
    if not sessions:
        print("❌ 暂无会话数据")
        return
    
    print(f"📊 总会话数: {len(sessions)}")
    active_sessions = [s for s in sessions if s.is_active and s.expires_at > datetime.utcnow()]
    print(f"🟢 活跃会话: {len(active_sessions)}")
    
    print("\n最近会话:")
    recent_sessions = sorted(sessions, key=lambda x: x.created_at, reverse=True)[:5]
    for sess in recent_sessions:
        status = "🟢 活跃" if sess.is_active and sess.expires_at > datetime.utcnow() else "🔴 过期"
        created = sess.created_at.strftime("%Y-%m-%d %H:%M")
        expires = sess.expires_at.strftime("%Y-%m-%d %H:%M")
        
        print(f"  用户ID: {sess.user_id:2d} | {status} | 创建: {created} | 过期: {expires}")

def check_chat_history(session):
    """检查聊天历史"""
    print_separator("聊天历史 (Chat History)")
    chats = session.query(ChatHistory).all()
    
    if not chats:
        print("❌ 暂无聊天记录")
        return
    
    print(f"📊 总聊天记录: {len(chats)}")
    
    # 按用户统计
    user_stats = {}
    for chat in chats:
        user_stats[chat.user_id] = user_stats.get(chat.user_id, 0) + 1
    
    print("\n用户聊天统计:")
    for user_id, count in sorted(user_stats.items()):
        print(f"  用户ID {user_id:2d}: {count:3d} 条记录")
    
    print("\n最近聊天记录:")
    recent_chats = sorted(chats, key=lambda x: x.created_at, reverse=True)[:3]
    for chat in recent_chats:
        time_str = chat.created_at.strftime("%Y-%m-%d %H:%M")
        message_preview = chat.message[:50] + "..." if len(chat.message) > 50 else chat.message
        print(f"  用户ID {chat.user_id} | {time_str} | {message_preview}")

def check_agent_builds(session):
    """检查Agent构建记录"""
    print_separator("Agent构建记录 (Agent Builds)")
    builds = session.query(AgentBuild).all()
    
    if not builds:
        print("❌ 暂无Agent构建记录")
        return
    
    print(f"📊 总构建记录: {len(builds)}")
    
    # 状态统计
    status_stats = {}
    for build in builds:
        status_stats[build.status] = status_stats.get(build.status, 0) + 1
    
    print("\n构建状态统计:")
    for status, count in status_stats.items():
        emoji = {"building": "🔄", "completed": "✅", "failed": "❌"}.get(status, "❓")
        print(f"  {emoji} {status}: {count} 个")
    
    print("\n最近构建记录:")
    recent_builds = sorted(builds, key=lambda x: x.started_at, reverse=True)[:3]
    for build in recent_builds:
        time_str = build.started_at.strftime("%Y-%m-%d %H:%M")
        desc_preview = build.user_description[:40] + "..." if len(build.user_description) > 40 else build.user_description
        status_emoji = {"building": "🔄", "completed": "✅", "failed": "❌"}.get(build.status, "❓")
        
        print(f"  {build.build_id[:8]}... | 用户ID {build.user_id} | {status_emoji} {build.status}")
        print(f"    {time_str} | {desc_preview}")
        if build.current_step:
            print(f"    当前步骤: {build.current_step}")
        print()

def check_generated_agents(session):
    """检查生成的Agent"""
    print_separator("生成的Agent (Generated Agents)")
    agents = session.query(GeneratedAgent).all()
    
    if not agents:
        print("❌ 暂无生成的Agent")
        return
    
    print(f"📊 总Agent数: {len(agents)}")
    
    # 状态统计
    status_stats = {}
    for agent in agents:
        status_stats[agent.status] = status_stats.get(agent.status, 0) + 1
    
    print("\n Agent状态统计:")
    for status, count in status_stats.items():
        emoji = {"active": "🟢", "inactive": "🟡", "deleted": "🔴"}.get(status, "❓")
        print(f"  {emoji} {status}: {count} 个")
    
    print("\n最近生成的Agent:")
    recent_agents = sorted(agents, key=lambda x: x.created_at, reverse=True)[:3]
    for agent in recent_agents:
        time_str = agent.created_at.strftime("%Y-%m-%d %H:%M")
        status_emoji = {"active": "🟢", "inactive": "🟡", "deleted": "🔴"}.get(agent.status, "❓")
        
        print(f"  {agent.agent_id[:8]}... | {agent.name[:20]}")
        print(f"    用户ID {agent.user_id} | {status_emoji} {agent.status} | {time_str}")
        if agent.description:
            desc_preview = agent.description[:50] + "..." if len(agent.description) > 50 else agent.description
            print(f"    描述: {desc_preview}")
        print()

def check_database_info(engine):
    """检查数据库基本信息"""
    print_separator("数据库信息")
    database_url = get_database_url()
    print(f"📍 数据库地址: {database_url}")
    
    try:
        with engine.connect() as conn:
            if "sqlite" in database_url:
                result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                tables = [row[0] for row in result]
                print(f"📊 数据表数量: {len(tables)}")
                print(f"📋 数据表列表: {', '.join(tables)}")
            else:
                result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
                tables = [row[0] for row in result]
                print(f"📊 数据表数量: {len(tables)}")
                print(f"📋 数据表列表: {', '.join(tables)}")
    except Exception as e:
        print(f"❌ 获取数据库信息失败: {e}")

def main():
    """主函数"""
    print("🔍 AgentCrafter 数据库检查工具")
    print(f"⏰ 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        session, engine = create_db_session()
        
        # 检查数据库基本信息
        check_database_info(engine)
        
        # 检查各个表的数据
        check_users(session)
        check_sessions(session)
        check_chat_history(session)
        check_agent_builds(session)
        check_generated_agents(session)
        
        session.close()
        
        print_separator("检查完成")
        print("✅ 数据库检查完成！")
        
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        print("💡 请确保数据库文件存在且路径正确")
        sys.exit(1)

if __name__ == "__main__":
    main()