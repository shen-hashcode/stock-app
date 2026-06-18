-- ========================================
-- 智能选股助手 - 数据库初始化脚本 (MySQL)
-- ========================================
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
    password_hash VARCHAR(128) COMMENT '密码哈希值（bcrypt）',
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
    script_code TEXT COMMENT 'AI生成的Python脚本代码',
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
    user_id INT COMMENT '所属用户ID，关联users表',
    run_date VARCHAR(20) COMMENT '执行日期，格式：YYYY-MM-DD',
    stocks_json TEXT COMMENT '筛选结果，JSON数组格式',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    INDEX idx_strategy_results_strategy_id (strategy_id),
    INDEX idx_strategy_results_user_id (user_id),
    INDEX idx_strategy_results_date (strategy_id, run_date),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略结果表';

-- ----------------------------------------
-- 订阅套餐表：定义可购买的套餐
-- ----------------------------------------
CREATE TABLE IF NOT EXISTS subscription_packages (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '套餐ID',
    name VARCHAR(50) NOT NULL COMMENT '套餐名称',
    description VARCHAR(200) COMMENT '套餐描述',
    price_cents INT NOT NULL COMMENT '价格（单位：分）',
    duration_days INT DEFAULT 30 COMMENT '有效期天数',
    strategy_limit INT NOT NULL COMMENT '可创建的自定义策略数量上限',
    is_active TINYINT(1) DEFAULT 1 COMMENT '是否上架：1=上架, 0=下架',
    sort_order INT DEFAULT 0 COMMENT '排序权重，越小越靠前',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订阅套餐表';

-- 初始套餐数据
INSERT INTO subscription_packages (name, description, price_cents, duration_days, strategy_limit, sort_order) VALUES
('内置策略套餐', '查看每日热门策略结果，不可创建自定义策略', 990, 30, 0, 1),
('定制策略套餐', '可创建1个自定义策略，同时可查看每日热门策略结果', 2990, 30, 1, 2);

-- ----------------------------------------
-- 用户订阅记录表：记录用户的订阅订单
-- ----------------------------------------
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
    user_id INT NOT NULL COMMENT '用户ID',
    package_id INT NOT NULL COMMENT '套餐ID',
    order_no VARCHAR(64) UNIQUE NOT NULL COMMENT '系统订单号',
    transaction_id VARCHAR(64) COMMENT '微信支付交易号',
    amount_cents INT NOT NULL COMMENT '实付金额（单位：分）',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '状态：pending/paid/expired/refunded',
    started_at DATETIME COMMENT '订阅开始时间',
    expired_at DATETIME COMMENT '订阅过期时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    paid_at DATETIME COMMENT '支付完成时间',
    INDEX idx_user_sub_user (user_id),
    INDEX idx_user_sub_order (order_no),
    INDEX idx_user_sub_status (user_id, status),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (package_id) REFERENCES subscription_packages(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户订阅记录表';
