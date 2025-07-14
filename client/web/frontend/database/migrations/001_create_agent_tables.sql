-- Agent后端架构数据库表创建脚本
-- 创建时间: 2025-07-14
-- 说明: 在现有用户数据库基础上增加Agent管理相关表

-- ⭐ 新增：agents 表
CREATE TABLE agents (
    agent_id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER NOT NULL,           -- 关联到 users.id
    port INTEGER UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    type ENUM('baseapp', 'custom') NOT NULL,
    status ENUM('running', 'stopped', 'error') DEFAULT 'stopped',
    config JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 外键约束，确保数据一致性
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    INDEX idx_user_id (user_id),
    INDEX idx_port (port),
    INDEX idx_status (status)
);

-- ⭐ 新增：端口分配表 (用于管理端口池)
CREATE TABLE port_allocation (
    port INTEGER PRIMARY KEY,
    agent_id VARCHAR(255),
    allocated_at TIMESTAMP,
    status ENUM('available', 'allocated') DEFAULT 'available',
    
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE SET NULL,
    INDEX idx_agent_id (agent_id),
    INDEX idx_status (status)
);

-- ⭐ 新增：Agent 会话表 (支持多会话)
CREATE TABLE agent_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    user_id INTEGER NOT NULL,
    title VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    INDEX idx_agent_id (agent_id),
    INDEX idx_user_id (user_id)
);

-- ⭐ 预置端口池数据 (开发阶段端口范围: 5001-5020)
INSERT INTO port_allocation (port, status) VALUES 
(5001, 'available'), (5002, 'available'), (5003, 'available'),
(5004, 'available'), (5005, 'available'), (5006, 'available'),
(5007, 'available'), (5008, 'available'), (5009, 'available'),
(5010, 'available'), (5011, 'available'), (5012, 'available'),
(5013, 'available'), (5014, 'available'), (5015, 'available'),
(5016, 'available'), (5017, 'available'), (5018, 'available'),
(5019, 'available'), (5020, 'available');

-- ⭐ 预置 BaseApp Agent (假设用户ID为1，端口 8888)
-- 注意: 实际部署时需要根据真实用户ID调整
INSERT INTO agents (agent_id, user_id, port, name, type, status) VALUES 
('baseapp', 1, 8888, 'BaseApp Chat Agent', 'baseapp', 'running');

-- 标记端口8888为已分配
INSERT INTO port_allocation (port, agent_id, allocated_at, status) VALUES 
(8888, 'baseapp', CURRENT_TIMESTAMP, 'allocated');