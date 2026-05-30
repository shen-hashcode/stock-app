-- ========================================
-- 智能选股助手 - 数据库初始化脚本 (MySQL)
-- ========================================
--
-- JSON字段格式说明:
--   strategies.conditions:
--     内置策略: {"type":"rise_pullback","params":{"days":3,"rise_pct":13}}
--     自定义策略: {"type":"custom","description":"前3天涨幅超15%"}
--
--   strategy_results.stocks_json:
--     [{"code":"600519","name":"贵州茅台","market":"sh","quote":{"price":1680,"change_pct":1.25}}]
--

-- 创建数据库（如不存在）
CREATE DATABASE IF NOT EXISTS stock_app DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE stock_app;

-- ----------------------------------------
-- 用户表：存储微信用户信息
-- ----------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '用户唯一标识，自增主键',
    openid VARCHAR(100) UNIQUE NOT NULL COMMENT '微信用户唯一标识，用于登录验证',
    nickname VARCHAR(50) COMMENT '用户昵称',
    phone VARCHAR(20) COMMENT '手机号码',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    is_active TINYINT(1) DEFAULT 1 COMMENT '账号状态：1=启用, 0=禁用',
    INDEX idx_users_openid (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ----------------------------------------
-- 策略表：存储用户创建的选股策略
-- ----------------------------------------
CREATE TABLE IF NOT EXISTS strategies (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '策略唯一标识，自增主键',
    user_id INT NOT NULL COMMENT '所属用户ID，关联users表',
    name VARCHAR(100) COMMENT '策略名称',
    description TEXT COMMENT '策略描述说明',
    conditions TEXT COMMENT '策略条件，JSON格式存储',
    script_code TEXT COMMENT 'AI生成的Python脚本代码（自定义策略专用）',
    is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用：1=启用, 0=禁用',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间，修改时自动更新',
    INDEX idx_strategies_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略表';

-- ----------------------------------------
-- 策略结果表：存储策略执行后的筛选结果
-- ----------------------------------------
CREATE TABLE IF NOT EXISTS strategy_results (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '结果唯一标识，自增主键',
    strategy_id INT NOT NULL COMMENT '所属策略ID，关联strategies表',
    run_date VARCHAR(20) COMMENT '执行日期，格式：YYYY-MM-DD',
    stocks_json TEXT COMMENT '筛选结果，JSON数组格式',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    INDEX idx_strategy_results_strategy_id (strategy_id),
    INDEX idx_strategy_results_date (strategy_id, run_date),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略结果表';
