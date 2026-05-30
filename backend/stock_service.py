import requests
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

QQ_QUOTE_URL = "https://qt.gtimg.cn/q="
QQ_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def generate_stock_codes():
    codes = []
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
            if not name or name == '':
                continue
            if 'ST' in name or '退' in name:
                continue
            if code.startswith('8'):
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
                'market_cap': total_market_cap
            })
        return valid_stocks
    except Exception as e:
        logger.error(f"批量验证股票失败: {e}")
        return []


def get_stock_list():
    all_codes = generate_stock_codes()
    all_stocks = []
    batch_size = 80

    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i+batch_size]
        valid = validate_stocks_batch(batch)
        all_stocks.extend(valid)
        time.sleep(0.1)

    return all_stocks


def get_kline_data(code, market, days=10):
    """返回K线数据列表, 每条记录是dict: day, open, close, high, low, volume"""
    try:
        symbol = f"{market}{code}"
        params = {
            '_var': 'kline_dayqfq',
            'param': f'{symbol},day,,,{days},qfq'
        }
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://web.ifzq.gtimg.cn/'
        }
        r = requests.get(QQ_KLINE_URL, params=params, headers=headers, timeout=10)

        if r.status_code != 200:
            return None

        match = re.search(r'=(\{.*\})', r.text)
        if not match:
            return None

        data = json.loads(match.group(1))
        if data.get('code') != 0:
            return None

        klines = data.get('data', {}).get(symbol, {})
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
                    'volume': float(row[5])
                })
        return result
    except Exception as e:
        return None


def get_realtime_quote(code, market):
    try:
        symbol = f"{market}{code}"
        url = QQ_QUOTE_URL + symbol
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None

        parts = r.text.split('~')
        if len(parts) < 40:
            return None

        return {
            'price': float(parts[3]) if parts[3] else 0,
            'change_pct': float(parts[32]) if parts[32] else 0,
            'volume': float(parts[36]) if parts[36] else 0,
            'market_cap': float(parts[45]) if parts[45] else 0
        }
    except:
        return None


def run_strategy(strategy_func, stock_list=None, max_workers=10):
    if stock_list is None:
        stock_list = get_stock_list()

    results = []

    def process_stock(stock):
        try:
            if strategy_func(stock):
                return stock
        except:
            pass
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_stock, s): s for s in stock_list}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results
