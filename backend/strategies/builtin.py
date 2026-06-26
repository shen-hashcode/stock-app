"""
内置选股策略集合（7 个：涨幅回调 / 放量突破 / 均线金叉 / 连续上涨 / 涨停开板 / 稳步上涨 / 神奇九转）。

每个策略函数接收股票元信息字典，返回 True/False 表示是否符合条件。

stock_info 结构：
    code: 股票代码 (如 "000001")
    name: 股票名称
    market: 市场 (sh=上海, sz=深圳)
    market_cap: 总市值(亿元)
"""

from stock_service import get_kline_data


def strategy_rise_pullback(stock_info, days=3, rise_pct=13, market_cap_min=50):
    """
    策略1: 涨幅回调
    
    逻辑: 前N个交易日累计涨幅超过阈值，当日出现回调(收盘价低于开盘价)
    适用场景: 追踪强势股的回调买入机会
    
    参数:
        stock_info: 股票信息字典
        days: 上涨天数，默认3天
        rise_pct: 涨幅阈值(%)，默认13%
        market_cap_min: 最低市值(亿)，默认50亿
    
    返回: bool - 符合条件返回True
    """
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    # 市值过滤：排除小盘股
    if market_cap < market_cap_min:
        return False

    # 获取K线数据(需要days+2根K线来计算)
    klines = get_kline_data(code, market, days=days+2)
    if not klines or len(klines) < days + 1:
        return False

    # 取最近days+1根K线
    klines = klines[-(days+1):]
    
    # 计算前N日累计涨幅: (第N日收盘价 - 第1日开盘价) / 第1日开盘价
    open_day1 = klines[0]['open']
    close_day_n = klines[days-1]['close']
    cumulative_gain = (close_day_n - open_day1) / open_day1 * 100

    # 判断当日是否回调: 收盘价 < 开盘价
    today_close = klines[days]['close']
    today_open = klines[days]['open']

    # 满足: 累计涨幅超过阈值 且 当日回调
    return cumulative_gain > rise_pct and today_close < today_open


def strategy_volume_breakout(stock_info, days=20, volume_ratio=2.0, market_cap_min=50):
    """
    策略2: 放量突破
    
    逻辑: 今日成交量是过去N日平均成交量的X倍，且价格上涨
    适用场景: 捕捉主力资金介入的突破行情
    
    参数:
        stock_info: 股票信息字典
        days: 均量计算天数，默认20天
        volume_ratio: 量比阈值，默认2.0倍
        market_cap_min: 最低市值(亿)，默认50亿
    
    返回: bool - 符合条件返回True
    """
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    # 市值过滤
    if market_cap < market_cap_min:
        return False

    # 获取K线数据
    klines = get_kline_data(code, market, days=days+1)
    if not klines or len(klines) < days + 1:
        return False

    # 计算过去N日平均成交量(排除今日)
    avg_volume = sum(k['volume'] for k in klines[-days-1:-1]) / days
    today_volume = klines[-1]['volume']

    # 避免除零错误
    if avg_volume == 0:
        return False

    # 判断今日是否上涨
    today_close = klines[-1]['close']
    yesterday_close = klines[-2]['close']

    # 满足: 放量(今日成交量 > 均量 * 倍数) 且 上涨
    return today_volume > avg_volume * volume_ratio and today_close > yesterday_close


def strategy_ma_golden_cross(stock_info, short_ma=5, long_ma=20, market_cap_min=50):
    """
    策略3: 均线金叉
    
    逻辑: 短期均线从下方上穿长期均线，形成金叉信号
    适用场景: 趋势转多的买入信号
    
    参数:
        stock_info: 股票信息字典
        short_ma: 短期均线周期，默认5日
        long_ma: 长期均线周期，默认20日
        market_cap_min: 最低市值(亿)，默认50亿
    
    返回: bool - 符合条件返回True
    """
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    # 市值过滤
    if market_cap < market_cap_min:
        return False

    # 获取足够计算长期均线的K线数据
    klines = get_kline_data(code, market, days=long_ma + 2)
    if not klines or len(klines) < long_ma + 2:
        return False

    # 提取收盘价序列
    closes = [k['close'] for k in klines]

    # 计算移动平均线
    def ma(data, period):
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    # 计算昨日和今日的短期/长期均线
    ma_short_yesterday = ma(closes[:-1], short_ma)
    ma_long_yesterday = ma(closes[:-1], long_ma)
    ma_short_today = ma(closes, short_ma)
    ma_long_today = ma(closes, long_ma)

    # 检查均线数据是否有效
    if None in (ma_short_yesterday, ma_long_yesterday, ma_short_today, ma_long_today):
        return False

    # 金叉条件: 昨日短期均线 <= 长期均线，今日短期均线 > 长期均线
    return ma_short_yesterday <= ma_long_yesterday and ma_short_today > ma_long_today


def strategy_consecutive_rise(stock_info, days=3, market_cap_min=50):
    """
    策略4: 连续上涨
    
    逻辑: 连续N个交易日收盘价均高于前一日收盘价
    适用场景: 追踪强势连涨股票
    
    参数:
        stock_info: 股票信息字典
        days: 连续上涨天数，默认3天
        market_cap_min: 最低市值(亿)，默认50亿
    
    返回: bool - 符合条件返回True
    """
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    # 市值过滤
    if market_cap < market_cap_min:
        return False

    # 获取K线数据
    klines = get_kline_data(code, market, days=days+1)
    if not klines or len(klines) < days + 1:
        return False

    # 检查每日收盘价是否递增
    recent = klines[-(days+1):]
    for i in range(1, days + 1):
        if recent[i]['close'] <= recent[i-1]['close']:
            return False

    return True


def strategy_limit_up_open(stock_info, market_cap_min=50):
    """
    策略5: 涨停开板
    
    逻辑: 昨日涨停(涨幅>=9.8%)，今日开板(收盘价>开盘价)
    适用场景: 捕捉涨停后开板的机会
    
    参数:
        stock_info: 股票信息字典
        market_cap_min: 最低市值(亿)，默认50亿
    
    返回: bool - 符合条件返回True
    """
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    # 市值过滤
    if market_cap < market_cap_min:
        return False

    # 获取最近3根K线
    klines = get_kline_data(code, market, days=3)
    if not klines or len(klines) < 3:
        return False

    # 计算昨日涨幅
    yesterday_close = klines[-2]['close']
    day_before_close = klines[-3]['close']
    yesterday_change = (yesterday_close - day_before_close) / day_before_close * 100

    # 今日行情
    today_open = klines[-1]['open']
    today_close = klines[-1]['close']

    # 判断: 昨日涨停(涨幅>=9.8%) 且 今日开板(收盘>开盘)
    is_limit_up = yesterday_change >= 9.8
    is_open_low = today_open < today_close

    return is_limit_up and is_open_low


def strategy_steady_rise(stock_info, days=6, min_pct=0, max_pct=3, market_cap_min=50):
    """
    策略6: 稳步上涨

    逻辑: 最近N个交易日每日涨幅都在 (min_pct, max_pct) 区间内
    适用场景: 寻找稳步上涨、波动较小的股票

    参数:
        stock_info: 股票信息字典
        days: 检查的交易日天数，默认6天
        min_pct: 最小涨幅(%)，默认0%（即允许平盘以上）
        max_pct: 最大涨幅(%)，默认3%（避免暴涨）
        market_cap_min: 最低市值(亿)，默认50亿

    返回: bool - 符合条件返回True
    """
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    # 市值过滤
    if market_cap < market_cap_min:
        return False

    # 需要 days+1 根 K 线才能计算 days 天的涨幅
    klines = get_kline_data(code, market, days=days + 1)
    if not klines or len(klines) < days + 1:
        return False

    recent = klines[-(days + 1):]
    for i in range(1, days + 1):
        prev_close = recent[i - 1]['close']
        curr_close = recent[i]['close']
        if prev_close == 0:
            return False
        change_pct = (curr_close - prev_close) / prev_close * 100
        # 必须严格在 (min_pct, max_pct) 区间内，区间外有任意一日就不符合
        if change_pct <= min_pct or change_pct >= max_pct:
            return False

    return True


def strategy_nine_turns(stock_info, direction="down", market_cap_min=50):
    """
    策略7: 神奇九转

    逻辑: 最近9个交易日，每日收盘价均低于（或高于）4天前的收盘价，
          形成TD Sequential结构9，预示趋势衰竭反转。

    下跌九转(down): 连续9天收盘价 < 4天前收盘价 → 潜在底部买入信号
    上涨九转(up):   连续9天收盘价 > 4天前收盘价 → 潜在顶部卖出信号

    参数:
        stock_info: 股票信息字典
        direction: 九转方向，"down"=下跌九转(底部信号)，"up"=上涨九转(顶部信号)
        market_cap_min: 最低市值(亿)，默认50亿

    返回: bool - 符合条件返回True
    """
    code = stock_info['code']
    market = stock_info['market']
    market_cap = stock_info['market_cap']

    if market_cap < market_cap_min:
        return False

    klines = get_kline_data(code, market, days=13)
    if not klines or len(klines) < 13:
        return False

    recent = klines[-13:]

    for i in range(9):
        curr_close = recent[12 - i]['close']
        prev_close = recent[8 - i]['close']
        if direction == "up":
            if curr_close <= prev_close:
                return False
        else:
            if curr_close >= prev_close:
                return False

    return True


"""
策略注册表

所有内置策略的配置信息，格式为:
{
    "策略key": {
        "name": "策略名称",
        "description": "策略描述",
        "func": 策略函数,
        "params": {
            "参数名": {
                "type": "参数类型(int/float/str)",
                "default": 默认值,
                "label": "参数显示名称"
            }
        }
    }
}

可通过 STRATEGIES["策略key"]["func"](stock_info, **params) 调用策略
"""

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
    },
    "steady_rise": {
        "name": "稳步上涨",
        "description": "最近N个交易日每日涨幅在 (min_pct, max_pct) 区间内",
        "func": strategy_steady_rise,
        "params": {
            "days": {"type": "int", "default": 6, "label": "交易日天数"},
            "min_pct": {"type": "float", "default": 0, "label": "最小涨幅(%)"},
            "max_pct": {"type": "float", "default": 3, "label": "最大涨幅(%)"},
            "market_cap_min": {"type": "float", "default": 50, "label": "最低市值(亿)"}
        }
    },
    "nine_turns": {
        "name": "神奇九转",
        "description": "连续9天收盘价低于（或高于）4天前收盘价，预示趋势反转",
        "func": strategy_nine_turns,
        "params": {
            "direction": {"type": "str", "default": "down", "label": "九转方向(down=下跌九转/up=上涨九转)"},
            "market_cap_min": {"type": "float", "default": 50, "label": "最低市值(亿)"}
        }
    }
}
