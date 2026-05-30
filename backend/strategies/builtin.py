"""
内置策略模板
stock_info: dict, 包含 code, name, market, market_cap
返回 True/False
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_service import get_kline_data, get_realtime_quote


def strategy_rise_pullback(stock_info, days=3, rise_pct=13, market_cap_min=50):
    """前N日涨幅>X%，当日回调"""
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    if market_cap < market_cap_min:
        return False

    klines = get_kline_data(code, market, days=days+2)
    if not klines or len(klines) < days + 1:
        return False

    klines = klines[-(days+1):]
    open_day1 = klines[0]['open']
    close_day_n = klines[days-1]['close']
    cumulative_gain = (close_day_n - open_day1) / open_day1 * 100

    today_close = klines[days]['close']
    today_open = klines[days]['open']

    return cumulative_gain > rise_pct and today_close < today_open


def strategy_volume_breakout(stock_info, days=20, volume_ratio=2.0, market_cap_min=50):
    """放量突破：今日成交量是过去N日均量的X倍"""
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    if market_cap < market_cap_min:
        return False

    klines = get_kline_data(code, market, days=days+1)
    if not klines or len(klines) < days + 1:
        return False

    avg_volume = sum(k['volume'] for k in klines[-days-1:-1]) / days
    today_volume = klines[-1]['volume']

    if avg_volume == 0:
        return False

    today_close = klines[-1]['close']
    yesterday_close = klines[-2]['close']

    return today_volume > avg_volume * volume_ratio and today_close > yesterday_close


def strategy_ma_golden_cross(stock_info, short_ma=5, long_ma=20, market_cap_min=50):
    """均线金叉：短期均线上穿长期均线"""
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    if market_cap < market_cap_min:
        return False

    klines = get_kline_data(code, market, days=long_ma + 2)
    if not klines or len(klines) < long_ma + 2:
        return False

    closes = [k['close'] for k in klines]

    def ma(data, period):
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    ma_short_yesterday = ma(closes[:-1], short_ma)
    ma_long_yesterday = ma(closes[:-1], long_ma)
    ma_short_today = ma(closes, short_ma)
    ma_long_today = ma(closes, long_ma)

    if None in (ma_short_yesterday, ma_long_yesterday, ma_short_today, ma_long_today):
        return False

    return ma_short_yesterday <= ma_long_yesterday and ma_short_today > ma_long_today


def strategy_consecutive_rise(stock_info, days=3, market_cap_min=50):
    """连涨N天"""
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    if market_cap < market_cap_min:
        return False

    klines = get_kline_data(code, market, days=days+1)
    if not klines or len(klines) < days + 1:
        return False

    recent = klines[-(days+1):]
    for i in range(1, days + 1):
        if recent[i]['close'] <= recent[i-1]['close']:
            return False

    return True


def strategy_limit_up_open(stock_info, market_cap_min=50):
    """涨停开板：昨日涨停，今日开板"""
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    if market_cap < market_cap_min:
        return False

    klines = get_kline_data(code, market, days=3)
    if not klines or len(klines) < 3:
        return False

    yesterday_close = klines[-2]['close']
    day_before_close = klines[-3]['close']
    yesterday_change = (yesterday_close - day_before_close) / day_before_close * 100

    today_open = klines[-1]['open']
    today_close = klines[-1]['close']

    is_limit_up = yesterday_change >= 9.8
    is_open_low = today_open < today_close

    return is_limit_up and is_open_low


STRATEGIES = {
    "rise_pullback": {
        "name": "涨幅回调",
        "description": "前N日累计涨幅超过阈值，当日出现回调",
        "func": strategy_rise_pullback,
        "params": {
            "days": {"type": "int", "default": 3, "label": "上涨天数"},
            "rise_pct": {"type": "float", "default": 13, "label": "涨幅阈值(%)"},
            "market_cap_min": {"type": "float", "default": 50, "label": "最低市值(亿)"}
        }
    },
    "volume_breakout": {
        "name": "放量突破",
        "description": "成交量突然放大，且价格上涨",
        "func": strategy_volume_breakout,
        "params": {
            "days": {"type": "int", "default": 20, "label": "均量天数"},
            "volume_ratio": {"type": "float", "default": 2.0, "label": "量比阈值"},
            "market_cap_min": {"type": "float", "default": 50, "label": "最低市值(亿)"}
        }
    },
    "ma_golden_cross": {
        "name": "均线金叉",
        "description": "短期均线上穿长期均线",
        "func": strategy_ma_golden_cross,
        "params": {
            "short_ma": {"type": "int", "default": 5, "label": "短期均线"},
            "long_ma": {"type": "int", "default": 20, "label": "长期均线"},
            "market_cap_min": {"type": "float", "default": 50, "label": "最低市值(亿)"}
        }
    },
    "consecutive_rise": {
        "name": "连续上涨",
        "description": "连续N天收阳线",
        "func": strategy_consecutive_rise,
        "params": {
            "days": {"type": "int", "default": 3, "label": "连续天数"},
            "market_cap_min": {"type": "float", "default": 50, "label": "最低市值(亿)"}
        }
    },
    "limit_up_open": {
        "name": "涨停开板",
        "description": "昨日涨停，今日开板低开",
        "func": strategy_limit_up_open,
        "params": {
            "market_cap_min": {"type": "float", "default": 50, "label": "最低市值(亿)"}
        }
    }
}
