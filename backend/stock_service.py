"""
智能选股助手 - 股票数据服务模块

本模块负责：
1. 获取沪深A股股票列表
2. 获取单只股票的实时行情数据
3. 获取单只股票的历史K线数据
4. 并发执行策略筛选

数据来源：腾讯财经API（qt.gtimg.cn）
数据范围：沪深两市全部A股（不含北交所、ST股、退市股）

主要函数：
- get_stock_list(): 获取全量股票列表
- get_kline_data(): 获取历史K线数据
- get_realtime_quote(): 获取实时行情
- run_strategy(): 多线程并发执行策略
"""

# ============================================================
# 第一部分：导入依赖
# ============================================================

import requests  # HTTP请求库
import time  # 时间控制（请求间隔）
import json  # JSON解析
import re  # 正则表达式
import os  # 环境变量
from concurrent.futures import ThreadPoolExecutor, as_completed  # 多线程并发
from typing import List, Dict, Optional  # 类型注解
import logging  # 日志记录
from dotenv import load_dotenv

load_dotenv()

# 创建日志记录器
logger = logging.getLogger(__name__)


# ============================================================
# 第二部分：API地址配置
# ============================================================

# 腾讯财经实时行情API
# 返回格式: v_sh600519="1~贵州茅台~600519~1680.00~..."
QQ_QUOTE_URL = "https://qt.gtimg.cn/q="

# 腾讯财经K线数据API
# 返回JSON格式的日K线数据
QQ_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


# ============================================================
# 第三部分：股票列表获取
# ============================================================

def generate_stock_codes():
    """
    生成沪深A股的股票代码列表
    
    按照股票代码规则生成所有可能的代码：
    - 上海主板: 600000-603999
    - 上海科创板: 688000-689999
    - 深圳主板: 000001-002999
    - 深圳创业板: 300000-301999
    
    返回:
        list: 股票代码列表，格式如 ['sh600000', 'sz000001', ...]
    
    注意:
        生成的代码不一定都有效，需要通过validate_stocks_batch验证
    """
    codes = []
    
    # 上海主板股票 (600000-603999)
    for i in range(600000, 604000):
        codes.append('sh' + str(i))
    
    # 上海科创板股票 (688000-689999)
    for i in range(688000, 690000):
        codes.append('sh' + str(i))
    
    # 深圳主板股票 (000001-002999)
    for i in range(1, 3000):
        codes.append('sz' + str(i).zfill(6))  # zfill(6)补零到6位
    
    # 深圳创业板股票 (300000-301999)
    for i in range(300000, 302000):
        codes.append('sz' + str(i))
    
    return codes


def validate_stocks_batch(codes_batch):
    """
    批量验证股票代码是否有效
    
    通过腾讯行情API批量查询股票信息，过滤无效股票
    
    过滤规则：
    1. 股票名称为空的跳过
    2. ST股、退市股跳过
    3. 北交所股票（8开头）跳过
    
    参数:
        codes_batch: 股票代码批次列表，如 ['sh600000', 'sh600001', ...]
    
    返回:
        list: 有效股票列表，每个元素是dict:
            {
                'code': '600519',      # 股票代码
                'name': '贵州茅台',    # 股票名称
                'market': 'sh',        # 市场
                'market_cap': 21000.5  # 总市值(亿)
            }
    
    调用链:
        get_stock_list() -> validate_stocks_batch() -> 腾讯API
    """
    try:
        # 拼接股票代码，用逗号分隔
        stock_str = ','.join(codes_batch)
        url = QQ_QUOTE_URL + stock_str
        
        # 发送HTTP请求
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []

        valid_stocks = []
        # 解析返回数据，每只股票用分号分隔
        lines = r.text.strip().split(';')
        
        for line in lines:
            if not line.strip():
                continue
            
            # 用波浪号分割字段
            parts = line.split('~')
            if len(parts) < 50:
                continue  # 字段数量不足，跳过
            
            # 提取基本信息
            name = parts[1].strip()  # 股票名称
            code = parts[2]  # 股票代码
            
            # 过滤无效股票
            if not name or name == '':
                continue  # 名称为空
            if 'ST' in name or '退' in name:
                continue  # ST股或退市股
            if code.startswith('8'):
                continue  # 北交所股票
            
            # 提取总市值（亿元）
            try:
                total_market_cap = float(parts[45]) if parts[45] else 0
            except (ValueError, IndexError):
                total_market_cap = 0
            
            # 判断市场（上海或深圳）
            market = 'sh' if line.startswith('v_sh') else 'sz'
            
            # 添加到有效股票列表
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


# 股票列表缓存
_stock_list_cache = None
_stock_list_cache_time = 0
_CACHE_DURATION = 3600  # 缓存1小时（秒）

def get_stock_list():
    """
    获取沪深A股全量股票列表（带缓存）
    
    工作流程：
    1. 检查缓存是否有效
    2. 缓存有效则直接返回
    3. 缓存无效则重新获取
    
    返回:
        list: 有效股票列表，约5000只股票
    """
    global _stock_list_cache, _stock_list_cache_time
    
    # 检查缓存是否有效
    current_time = time.time()
    if _stock_list_cache is not None and (current_time - _stock_list_cache_time) < _CACHE_DURATION:
        return _stock_list_cache
    
    # 缓存无效，重新获取
    all_codes = generate_stock_codes()
    all_stocks = []
    batch_size = 80
    
    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i+batch_size]
        valid = validate_stocks_batch(batch)
        all_stocks.extend(valid)
        time.sleep(0.1)
    
    # 更新缓存
    _stock_list_cache = all_stocks
    _stock_list_cache_time = current_time
    
    return all_stocks


def get_stock_list_quick(limit=200):
    """
    快速获取股票列表（热门股票，无需网络请求）
    
    返回A股热门股票列表，用于快速测试
    
    参数:
        limit: 返回股票数量限制，默认200
    
    返回:
        list: 热门股票列表
    """
    hot_stocks = [
        {'code': '600519', 'name': '贵州茅台', 'market': 'sh', 'market_cap': 21000},
        {'code': '000858', 'name': '五粮液', 'market': 'sz', 'market_cap': 6800},
        {'code': '601318', 'name': '中国平安', 'market': 'sh', 'market_cap': 8500},
        {'code': '600036', 'name': '招商银行', 'market': 'sh', 'market_cap': 11000},
        {'code': '000333', 'name': '美的集团', 'market': 'sz', 'market_cap': 5200},
        {'code': '600900', 'name': '长江电力', 'market': 'sh', 'market_cap': 6500},
        {'code': '601012', 'name': '隆基绿能', 'market': 'sh', 'market_cap': 2800},
        {'code': '300750', 'name': '宁德时代', 'market': 'sz', 'market_cap': 9500},
        {'code': '000001', 'name': '平安银行', 'market': 'sz', 'market_cap': 2100},
        {'code': '600276', 'name': '恒瑞医药', 'market': 'sh', 'market_cap': 3200},
        {'code': '000568', 'name': '泸州老窖', 'market': 'sz', 'market_cap': 2800},
        {'code': '002714', 'name': '牧原股份', 'market': 'sz', 'market_cap': 2500},
        {'code': '600887', 'name': '伊利股份', 'market': 'sh', 'market_cap': 2000},
        {'code': '000651', 'name': '格力电器', 'market': 'sz', 'market_cap': 2200},
        {'code': '601888', 'name': '中国中免', 'market': 'sh', 'market_cap': 3500},
        {'code': '600809', 'name': '山西汾酒', 'market': 'sh', 'market_cap': 2800},
        {'code': '002352', 'name': '顺丰控股', 'market': 'sz', 'market_cap': 2200},
        {'code': '600309', 'name': '万华化学', 'market': 'sh', 'market_cap': 2600},
        {'code': '002475', 'name': '立讯精密', 'market': 'sz', 'market_cap': 2400},
        {'code': '601166', 'name': '兴业银行', 'market': 'sh', 'market_cap': 4200},
        {'code': '000725', 'name': '京东方A', 'market': 'sz', 'market_cap': 1800},
        {'code': '600585', 'name': '海螺水泥', 'market': 'sh', 'market_cap': 1500},
        {'code': '002594', 'name': '比亚迪', 'market': 'sz', 'market_cap': 7000},
        {'code': '600030', 'name': '中信证券', 'market': 'sh', 'market_cap': 3200},
        {'code': '000002', 'name': '万科A', 'market': 'sz', 'market_cap': 1200},
        {'code': '601398', 'name': '工商银行', 'market': 'sh', 'market_cap': 18000},
        {'code': '600000', 'name': '浦发银行', 'market': 'sh', 'market_cap': 2800},
        {'code': '002415', 'name': '海康威视', 'market': 'sz', 'market_cap': 3500},
        {'code': '600050', 'name': '中国联通', 'market': 'sh', 'market_cap': 1500},
        {'code': '601857', 'name': '中国石油', 'market': 'sh', 'market_cap': 12000},
        {'code': '600028', 'name': '中国石化', 'market': 'sh', 'market_cap': 6500},
        {'code': '000538', 'name': '云南白药', 'market': 'sz', 'market_cap': 1200},
        {'code': '002304', 'name': '洋河股份', 'market': 'sz', 'market_cap': 2200},
        {'code': '600690', 'name': '海尔智家', 'market': 'sh', 'market_cap': 2400},
        {'code': '000063', 'name': '中兴通讯', 'market': 'sz', 'market_cap': 1800},
        {'code': '601688', 'name': '华泰证券', 'market': 'sh', 'market_cap': 1800},
        {'code': '600009', 'name': '上海机场', 'market': 'sh', 'market_cap': 1100},
        {'code': '002142', 'name': '宁波银行', 'market': 'sz', 'market_cap': 2000},
        {'code': '600570', 'name': '恒生电子', 'market': 'sh', 'market_cap': 800},
        {'code': '300059', 'name': '东方财富', 'market': 'sz', 'market_cap': 2500},
        {'code': '002230', 'name': '科大讯飞', 'market': 'sz', 'market_cap': 1200},
        {'code': '600886', 'name': '国投电力', 'market': 'sh', 'market_cap': 1000},
        {'code': '000661', 'name': '长春高新', 'market': 'sz', 'market_cap': 800},
        {'code': '300124', 'name': '汇川技术', 'market': 'sz', 'market_cap': 1800},
        {'code': '601138', 'name': '工业富联', 'market': 'sh', 'market_cap': 3000},
        {'code': '002049', 'name': '紫光国微', 'market': 'sz', 'market_cap': 1000},
        {'code': '600763', 'name': '通策医疗', 'market': 'sh', 'market_cap': 400},
        {'code': '300015', 'name': '爱尔眼科', 'market': 'sz', 'market_cap': 1800},
        {'code': '601225', 'name': '陕西煤业', 'market': 'sh', 'market_cap': 2000},
        {'code': '002460', 'name': '赣锋锂业', 'market': 'sz', 'market_cap': 1200},
    ]
    return hot_stocks[:limit]


# ============================================================
# 第四部分：K线数据获取
# ============================================================

def get_kline_data(code, market, days=10):
    """
    获取股票的历史K线数据
    
    从腾讯财经API获取日K线数据（前复权）
    
    参数:
        code: 股票代码，如 "600519"
        market: 市场，"sh" 或 "sz"
        days: 获取天数，默认10天
    
    返回:
        list: K线数据列表，每个元素是dict:
            {
                'day': '2024-01-15',  # 日期
                'open': 1680.00,      # 开盘价
                'close': 1695.50,     # 收盘价
                'high': 1700.00,      # 最高价
                'low': 1675.00,       # 最低价
                'volume': 12500000    # 成交量
            }
        None: 获取失败时返回
    
    调用链:
        策略函数 -> get_kline_data() -> 腾讯K线API
    
    示例:
        klines = get_kline_data("600519", "sh", days=20)
        for k in klines:
            print(f"{k['day']}: 收盘价 {k['close']}")
    """
    try:
        # 构建请求参数
        symbol = f"{market}{code}"
        params = {
            '_var': 'kline_dayqfq',  # 变量名
            'param': f'{symbol},day,,,{days},qfq'  # 参数: 股票代码,周期,开始日期,结束日期,天数,复权方式
        }
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://web.ifzq.gtimg.cn/'
        }
        
        # 发送请求
        r = requests.get(QQ_KLINE_URL, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            return None

        # 解析JSON响应
        # 响应格式: kline_dayqfq={...}
        match = re.search(r'=(\{.*\})', r.text)
        if not match:
            return None

        data = json.loads(match.group(1))
        if data.get('code') != 0:
            return None

        # 提取K线数据
        klines = data.get('data', {}).get(symbol, {})
        # 优先使用前复权数据，如果没有则使用普通数据
        day_data = klines.get('qfqday') or klines.get('day')

        if not day_data:
            return None

        # 转换为标准格式
        result = []
        for row in day_data:
            if len(row) >= 6:
                result.append({
                    'day': row[0],           # 日期
                    'open': float(row[1]),   # 开盘价
                    'close': float(row[2]),  # 收盘价
                    'high': float(row[3]),   # 最高价
                    'low': float(row[4]),    # 最低价
                    'volume': float(row[5])  # 成交量
                })
        return result
    except Exception as e:
        return None


# ============================================================
# 第五部分：实时行情获取
# ============================================================

def get_realtime_quote(code, market):
    """
    获取股票的实时行情数据
    
    从腾讯财经API获取股票的最新价格、涨跌幅等信息
    
    参数:
        code: 股票代码，如 "600519"
        market: 市场，"sh" 或 "sz"
    
    返回:
        dict: 实时行情数据
            {
                'price': 1680.00,        # 现价
                'change_pct': 1.25,      # 涨跌幅(%)
                'volume': 12500000,      # 成交量
                'market_cap': 21000.5    # 总市值(亿)
            }
        None: 获取失败时返回
    
    调用链:
        策略执行 -> 获取实时行情 -> get_realtime_quote() -> 腾讯API
    
    数据字段说明:
        parts[3]: 现价
        parts[32]: 涨跌幅(%)
        parts[36]: 成交量
        parts[45]: 总市值(亿)
    """
    try:
        symbol = f"{market}{code}"
        url = QQ_QUOTE_URL + symbol
        
        # 发送请求
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None

        # 解析返回数据
        parts = r.text.split('~')
        if len(parts) < 40:
            return None

        # 提取行情数据
        return {
            'price': float(parts[3]) if parts[3] else 0,        # 现价
            'change_pct': float(parts[32]) if parts[32] else 0,  # 涨跌幅(%)
            'volume': float(parts[36]) if parts[36] else 0,      # 成交量
            'market_cap': float(parts[45]) if parts[45] else 0   # 总市值(亿)
        }
    except:
        return None


# ============================================================
# 第六部分：策略并发执行
# ============================================================

def run_strategy(strategy_func, stock_list=None, max_workers=10):
    """
    并发执行策略筛选
    
    使用线程池并发执行策略函数，提高筛选效率
    
    参数:
        strategy_func: 策略函数，接收stock_info字典，返回True/False
        stock_list: 股票列表（可选，默认获取全量）
        max_workers: 最大线程数，默认10
    
    返回:
        list: 符合条件的股票列表
    
    性能:
        - 10线程并发，比单线程快约10倍
        - 全量筛选约需5-15分钟
    
    调用链:
        run_steady_rise.py -> run_strategy() -> strategy_func(stock)
                                                -> 多线程并发执行
    
    示例:
        from strategies.steady_rise import strategy_steady_rise
        results = run_strategy(
            lambda stock: strategy_steady_rise(stock, days=5),
            stock_list=stock_list,
            max_workers=10
        )
    """
    # 如果没有提供股票列表，则获取全量
    if stock_list is None:
        stock_list = get_stock_list()

    results = []

    def process_stock(stock):
        """
        处理单只股票
        
        对单只股票执行策略函数，如果符合条件则返回股票信息
        异常时返回None，不影响其他股票的处理
        """
        try:
            if strategy_func(stock):
                return stock
        except:
            pass
        return None

    # 使用线程池并发执行
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        futures = {executor.submit(process_stock, s): s for s in stock_list}

        # 等待所有任务完成，收集结果
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results


# ============================================================
# 第七部分：AI策略生成
# ============================================================

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

STRATEGY_PROMPT = """你是一个Python量化选股脚本生成器。用户会描述选股条件，你需要生成一个Python函数。

要求：
1. 函数名必须为 check_stock(stock_info)
2. stock_info 是一个字典，包含: code(股票代码), name(名称), market(市场sh/sz), market_cap(市值,亿)
3. 可以调用以下已导入的函数:
   - get_kline_data(code, market, days=10): 返回K线列表，每项为dict含 day,open,close,high,low,volume
   - get_realtime_quote(code, market): 返回dict含 price,change_pct,volume,open,high,low,market_cap
4. 函数返回 True 表示符合条件，False 表示不符合
5. 只输出纯Python代码，不要markdown标记，不要解释

用户条件：{description}
"""


async def generate_strategy_script(description: str) -> str:
    """调用LLM生成策略脚本"""
    if not LLM_API_KEY:
        raise ValueError("未配置LLM_API_KEY环境变量，无法生成AI策略")

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业的Python量化选股脚本生成器，只输出代码。"},
            {"role": "user", "content": STRATEGY_PROMPT.format(description=description)}
        ],
        "temperature": 0.3,
        "max_tokens": 2000
    }

    resp = requests.post(LLM_API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    # 去除可能的markdown代码块标记
    content = re.sub(r'^```python\s*\n?', '', content.strip())
    content = re.sub(r'\n?```\s*$', '', content.strip())
    return content


def extract_strategy_name(name: str) -> str:
    """提取/清理策略名称"""
    if not name or not name.strip():
        return "自定义策略"
    return name.strip()[:50]
