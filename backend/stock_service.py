"""
股票数据服务模块。

职责：
- 拉取沪深 A 股全量股票列表（带 1 小时内存缓存）
- 拉取单只股票的实时行情、历史 K 线

数据来源：腾讯财经 (qt.gtimg.cn / web.ifzq.gtimg.cn)
数据范围：沪深主板 / 科创板 / 创业板，过滤 ST、退市、北交所。
"""

import requests
import time
import json
import re
from dotenv import load_dotenv

from logger import logger

load_dotenv()

# 腾讯财经实时行情 API（返回类似 v_sh600519="1~贵州茅台~..." 的文本）
QQ_QUOTE_URL = "https://qt.gtimg.cn/q="
# 腾讯财经历史 K 线 API（返回包含 JSON 的脚本片段）
QQ_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


# ============================================================
# 股票列表
# ============================================================

def generate_stock_codes():
    """从东方财富 API 实时获取沪深 A 股全部代码，替换原来的范围枚举法。"""
    codes = []
    page = 1
    page_size = 5000
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.eastmoney.com/",
    }
    base_url = "http://80.push2.eastmoney.com/api/qt/clist/get"

    try:
        while True:
            params = {
                "pn": page,
                "pz": page_size,
                "po": 1,
                "np": 1,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f12,f14",
            }
            r = requests.get(base_url, params=params, headers=headers, timeout=15)
            if r.status_code != 200:
                break

            data = r.json()
            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break

            for item in diff:
                code = str(item.get("f12", ""))
                name = item.get("f14", "")
                if not code or not name:
                    continue
                if 'ST' in name or '退' in name:
                    continue
                if code.startswith('8'):
                    continue
                market = 'sh' if code.startswith(('6', '9')) else 'sz'
                codes.append(market + code)

            total = data.get("data", {}).get("total", 0)
            if page * page_size >= total:
                break
            page += 1

        if codes:
            return codes
    except Exception as e:
        logger.warning(f"东方财富API获取股票列表失败: {e}")

    # 兜底：原有范围枚举
    logger.info("使用备用方法生成股票代码")
    for i in range(600000, 604000):
        codes.append('sh' + str(i))
    for i in range(688000, 690000):
        codes.append('sh' + str(i))
    for i in range(1, 3000):
        codes.append('sz' + str(i).zfill(6))
    for i in range(300000, 302000):
        codes.append('sz' + str(i))
    return codes


def validate_stocks_batch(codes_batch):
    """
    批量查询股票元信息，过滤无效条目（无名称 / ST / 退市 / 北交所）。

    返回 [{code, name, market, market_cap(亿)}, ...]
    """
    try:
        stock_str = ','.join(codes_batch)
        url = QQ_QUOTE_URL + stock_str
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []

        valid_stocks = []
        lines = r.text.strip().split(';')
        for line in lines:
            if not line.strip():
                continue
            parts = line.split('~')
            if len(parts) < 50:
                continue
            name = parts[1].strip()
            code = parts[2]
            if not name:
                continue
            if 'ST' in name or '退' in name:
                continue
            if code.startswith('8'):  # 北交所
                continue
            try:
                total_market_cap = float(parts[45]) if parts[45] else 0
            except (ValueError, IndexError):
                total_market_cap = 0
            market = 'sh' if line.startswith('v_sh') else 'sz'
            valid_stocks.append({
                'code': code,
                'name': name,
                'market': market,
                'market_cap': total_market_cap,
            })
        return valid_stocks
    except Exception as e:
        logger.error(f"批量验证股票失败: {e}")
        return []


# 全量股票列表内存缓存（进程级，1 小时 TTL）
_stock_list_cache = None
_stock_list_cache_time = 0
_CACHE_DURATION = 3600


def get_stock_list():
    """
    获取沪深 A 股全量股票列表，带 1 小时进程级缓存。

    首次调用会分批拉取约 5000 只股票，耗时数分钟；
    之后命中缓存直接返回。
    """
    global _stock_list_cache, _stock_list_cache_time

    current_time = time.time()
    if _stock_list_cache is not None and (current_time - _stock_list_cache_time) < _CACHE_DURATION:
        return _stock_list_cache

    all_codes = generate_stock_codes()
    all_stocks = []
    batch_size = 80
    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i + batch_size]
        valid = validate_stocks_batch(batch)
        all_stocks.extend(valid)
        time.sleep(0.1)

    _stock_list_cache = all_stocks
    _stock_list_cache_time = current_time
    logger.info(f"全量股票列表已刷新，共 {len(all_stocks)} 只")
    return all_stocks


# ============================================================
# K 线数据
# ============================================================

def get_kline_data(code, market, days=10):
    """
    获取股票最近 N 天日 K 线（前复权）。

    返回 [{day, open, close, high, low, volume}, ...]；失败返回 None。
    """
    try:
        symbol = f"{market}{code}"
        params = {
            '_var': 'kline_dayqfq',
            'param': f'{symbol},day,,,{days},qfq',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://web.ifzq.gtimg.cn/',
        }
        r = requests.get(QQ_KLINE_URL, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        print('K 线原始响应:', r.text)

        match = re.search(r'=(\{.*\})', r.text)
        if not match:
            return None

        data = json.loads(match.group(1))
        if data.get('code') != 0:
            return None

        klines = data.get('data', {}).get(symbol, {})
        # 优先前复权数据
        day_data = klines.get('qfqday') or klines.get('day')
        if not day_data:
            return None

        result = []
        for row in day_data:
            if len(row) >= 6:
                result.append({
                    'day': row[0],
                    'open': float(row[1]),
                    'close': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'volume': float(row[5]),
                })
        return result
    except Exception as e:
        logger.debug(f"K 线获取失败 {market}{code}: {e}")
        return None


# ============================================================
# 实时行情
# ============================================================

def get_realtime_quote(code, market):
    """
    获取股票实时行情。

    返回 {name, code, price, open, high, low, change_pct, volume, market_cap(亿)}；
    失败返回 None。

    字段位置（腾讯协议固定）：
        parts[1]  - 名称
        parts[2]  - 代码
        parts[3]  - 现价
        parts[5]  - 今开
        parts[33] - 最高
        parts[34] - 最低
        parts[32] - 涨跌幅 (%)
        parts[36] - 成交额 (万)
        parts[45] - 总市值 (亿)
    """
    try:
        symbol = f"{market}{code}"
        url = QQ_QUOTE_URL + symbol
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None

        raw = r.text.strip()
        eq_idx = raw.find('=')
        if eq_idx != -1:
            raw = raw[eq_idx + 1:]
            if raw.startswith('"') and raw.endswith('"'):
                raw = raw[1:-1]

        parts = raw.split('~')
        if len(parts) < 46:
            return None

        return {
            'name': parts[1] or '',
            'code': parts[2] or '',
            'price': float(parts[3]) if parts[3] else 0,
            'open': float(parts[5]) if parts[5] else 0,
            'high': float(parts[33]) if parts[33] else 0,
            'low': float(parts[34]) if parts[34] else 0,
            'change_pct': float(parts[32]) if parts[32] else 0,
            'volume': float(parts[36]) if parts[36] else 0,
            'market_cap': float(parts[45]) if parts[45] else 0,
        }
    except Exception as e:
        logger.debug(f"实时行情获取失败 {market}{code}: {e}")
        return None