"""
智能选股助手 - 稳步上涨策略模块

本模块实现"稳步上涨"选股策略：
- 逻辑：最近N个交易日每日涨幅在指定范围内
- 适用场景：寻找稳步上涨、波动较小的股票

策略特点：
- 每日涨幅控制在0%~3%之间（可配置）
- 避免暴涨暴跌的股票
- 适合稳健型投资者

使用方式：
    from strategies.steady_rise import strategy_steady_rise
    
    stock_info = {'code': '600519', 'market': 'sh', 'market_cap': 21000}
    result = strategy_steady_rise(stock_info, days=5, min_pct=0, max_pct=3)
"""

# ============================================================
# 第一部分：导入依赖
# ============================================================

import sys
import os

# 添加父目录到模块搜索路径，以便导入stock_service
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_service import get_kline_data


# ============================================================
# 第二部分：策略函数定义
# ============================================================

def strategy_steady_rise(stock_info, days=6, min_pct=0, max_pct=3, market_cap_min=50):
    """
    稳步上涨策略
    
    筛选最近N个交易日每日涨幅在指定范围内的股票
    要求股票稳步上涨，避免大幅波动
    
    参数:
        stock_info: 股票信息字典
            - code: 股票代码（如 "600519"）
            - market: 市场（"sh" 或 "sz"）
            - market_cap: 总市值（亿元）
        days: 检查的交易日天数，默认6天
        min_pct: 最小涨幅(%)，默认0%（即允许平盘）
        max_pct: 最大涨幅(%)，默认3%（避免暴涨）
        market_cap_min: 最低市值(亿)，默认50亿（过滤小盘股）
    
    返回:
        bool: True=符合条件（每日涨幅在范围内），False=不符合
    
    筛选逻辑：
        1. 市值过滤：排除市值小于market_cap_min的股票
        2. 获取K线数据：需要days+1根K线来计算days天的涨幅
        3. 逐日计算涨幅：(今日收盘-昨日收盘)/昨日收盘*100
        4. 判断范围：所有涨幅必须 > min_pct 且 < max_pct
    
    示例：
        # 筛选最近5天每日涨幅在0%~3%之间的股票
        result = strategy_steady_rise(stock_info, days=5, min_pct=0, max_pct=3)
    """
    # 提取股票信息
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    # 第一步：市值过滤
    # 排除小盘股，降低风险
    if market_cap < market_cap_min:
        return False

    # 第二步：获取K线数据
    # 需要days+1根K线来计算days天的涨幅
    klines = get_kline_data(code, market, days=days + 1)
    if not klines or len(klines) < days + 1:
        return False  # 数据不足，跳过

    # 取最近days+1根K线
    recent = klines[-(days + 1):]
    
    # 第三步：逐日计算涨幅
    for i in range(1, days + 1):
        prev_close = recent[i - 1]['close']  # 前一日收盘价
        curr_close = recent[i]['close']      # 当日收盘价
        
        # 避免除零错误
        if prev_close == 0:
            return False
        
        # 计算当日涨幅百分比
        change_pct = (curr_close - prev_close) / prev_close * 100
        
        # 判断涨幅是否在范围内
        # 必须大于min_pct（默认0%）且小于max_pct（默认3%）
        if change_pct <= min_pct or change_pct >= max_pct:
            return False  # 有一天不符合就返回False

    # 所有天数都符合条件
    return True


# ============================================================
# 第三部分：策略注册表
# ============================================================

STRATEGIES = {
    "steady_rise": {
        "name": "稳步上涨",
        "description": "最近N个交易日每日涨幅在0%~3%之间",
        "func": strategy_steady_rise,
        "params": {
            "days": {
                "type": "int",
                "default": 6,
                "label": "交易日天数"
            },
            "min_pct": {
                "type": "float",
                "default": 0,
                "label": "最小涨幅(%)"
            },
            "max_pct": {
                "type": "float",
                "default": 3,
                "label": "最大涨幅(%)"
            },
            "market_cap_min": {
                "type": "float",
                "default": 50,
                "label": "最低市值(亿)"
            }
        }
    }
}
