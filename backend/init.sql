-- ========================================
-- 智能选股助手 - 数据库初始化脚本
-- ========================================

-- ----------------------------------------
-- 用户表：存储微信用户信息
-- ----------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 用户唯一标识，自增主键
    openid VARCHAR(100) UNIQUE NOT NULL,   -- 微信用户唯一标识，用于登录验证
    nickname VARCHAR(50),                  -- 用户昵称
    phone VARCHAR(20),                     -- 手机号码
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 注册时间
    is_active BOOLEAN DEFAULT 1            -- 账号状态：1=启用, 0=禁用
);

-- openid索引：加速微信登录查询
CREATE INDEX IF NOT EXISTS idx_users_openid ON users(openid);

-- ----------------------------------------
-- 策略表：存储用户创建的选股策略
-- ----------------------------------------
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 策略唯一标识，自增主键
    user_id INTEGER NOT NULL,              -- 所属用户ID，关联users表
    name VARCHAR(100),                     -- 策略名称
    description TEXT,                      -- 策略描述说明
    conditions TEXT,                       -- 策略条件，JSON格式存储
                                         -- 内置策略示例: {"type":"rise_pullback","params":{"days":3}}
                                         -- 自定义策略示例: {"type":"custom","description":"前3天涨幅超15%"}
    script_code TEXT,                      -- AI生成的Python脚本代码（自定义策略专用）
    is_active BOOLEAN DEFAULT 1,           -- 是否启用：1=启用, 0=禁用
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 更新时间，修改时自动更新
    FOREIGN KEY (user_id) REFERENCES users(id)  -- 外键约束，关联用户表
);

-- user_id索引：加速查询用户的策略列表
CREATE INDEX IF NOT EXISTS idx_strategies_user_id ON strategies(user_id);

-- ----------------------------------------
-- 策略结果表：存储策略执行后的筛选结果
-- ----------------------------------------
CREATE TABLE IF NOT EXISTS strategy_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 结果唯一标识，自增主键
    strategy_id INTEGER NOT NULL,          -- 所属策略ID，关联strategies表
    run_date VARCHAR(20),                  -- 执行日期，格式：YYYY-MM-DD
    stocks_json TEXT,                      -- 筛选结果，JSON数组格式
                                         -- 示例: [{"code":"600519","name":"贵州茅台","market":"sh","quote":{...}}]
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 记录创建时间
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)  -- 外键约束，关联策略表
);

-- strategy_id索引：加速查询策略的历史结果
CREATE INDEX IF NOT EXISTS idx_strategy_results_strategy_id ON strategy_results(strategy_id);
