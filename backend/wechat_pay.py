"""
微信支付模块

负责：
1. 生成预支付订单（JSAPI统一下单）
2. 生成前端支付参数（签名）
3. 验证支付回调签名
4. 解密回调通知数据
"""

import os
import time
import uuid
import json
import base64
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import requests

from logger import logger

# 微信支付配置
MCH_ID = os.getenv("WECHAT_MCH_ID", "")
API_KEY_V3 = os.getenv("WECHAT_API_KEY_V3", "")
MCH_SERIAL_NO = os.getenv("WECHAT_MCH_SERIAL_NO", "")
MCH_PRIVATE_KEY_PATH = os.getenv("WECHAT_MCH_PRIVATE_KEY_PATH", "")
PAY_NOTIFY_URL = os.getenv("WECHAT_PAY_NOTIFY_URL", "")
APPID = os.getenv("WECHAT_APPID", "")

# 微信支付API地址
JSAPI_ORDER_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"

# 缓存商户私钥
_private_key = None


def _load_private_key():
    """加载商户RSA私钥"""
    global _private_key
    if _private_key:
        return _private_key

    if not MCH_PRIVATE_KEY_PATH or not os.path.exists(MCH_PRIVATE_KEY_PATH):
        logger.error(f"商户私钥文件不存在: {MCH_PRIVATE_KEY_PATH}")
        return None

    with open(MCH_PRIVATE_KEY_PATH, "rb") as f:
        _private_key = load_pem_private_key(f.read(), password=None)
    return _private_key


def _sign(message: str) -> str:
    """使用商户私钥对消息进行RSA-SHA256签名"""
    key = _load_private_key()
    if not key:
        raise ValueError("无法加载商户私钥")

    signature = key.sign(
        message.encode("utf-8"),
        PKCS1v15(),
        SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")


def _build_auth_header(method: str, url_path: str, body: str = "") -> str:
    """构建微信支付API请求的Authorization头"""
    timestamp = str(int(time.time()))
    nonce_str = uuid.uuid4().hex
    sign_str = f"{method}\n{url_path}\n{timestamp}\n{nonce_str}\n{body}\n"
    signature = _sign(sign_str)

    return (
        f'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{MCH_ID}",'
        f'nonce_str="{nonce_str}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{MCH_SERIAL_NO}"'
    )


def generate_order_no() -> str:
    """生成唯一订单号：时间戳 + 随机串"""
    return datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:10].upper()


def create_prepay_order(order_no: str, amount_cents: int, description: str, openid: str) -> dict:
    """
    调用微信JSAPI统一下单接口

    返回: {"prepay_id": "..."} 或 {"error": "..."}
    """
    if not all([MCH_ID, API_KEY_V3, MCH_SERIAL_NO, APPID, PAY_NOTIFY_URL]):
        return {"error": "微信支付配置不完整，请检查环境变量"}

    body = {
        "appid": APPID,
        "mchid": MCH_ID,
        "description": description,
        "out_trade_no": order_no,
        "notify_url": PAY_NOTIFY_URL,
        "amount": {
            "total": amount_cents,
            "currency": "CNY"
        },
        "payer": {
            "openid": openid
        }
    }

    body_str = json.dumps(body, ensure_ascii=False)
    url_path = "/v3/pay/transactions/jsapi"
    auth_header = _build_auth_header("POST", url_path, body_str)

    try:
        resp = requests.post(
            JSAPI_ORDER_URL,
            data=body_str.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": auth_header,
            },
            timeout=10
        )

        if resp.status_code == 200:
            data = resp.json()
            return {"prepay_id": data.get("prepay_id")}
        else:
            logger.error(f"微信下单失败: {resp.status_code} {resp.text}")
            return {"error": f"微信下单失败: {resp.text}"}
    except Exception as e:
        logger.error(f"微信下单异常: {e}")
        return {"error": f"微信下单异常: {str(e)}"}


def build_payment_params(prepay_id: str) -> dict:
    """
    生成前端 wx.requestPayment 所需的参数（含签名）
    """
    timestamp = str(int(time.time()))
    nonce_str = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"

    sign_str = f"{APPID}\n{timestamp}\n{nonce_str}\n{package}\n"
    pay_sign = _sign(sign_str)

    return {
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign
    }


def verify_callback_signature(headers: dict, body: bytes) -> bool:
    """
    验证微信支付回调的签名

    注意：完整实现需要下载微信支付平台证书进行验证
    这里做基本的格式校验，生产环境应实现完整的证书验签
    """
    timestamp = headers.get("Wechatpay-Timestamp", "")
    nonce = headers.get("Wechatpay-Nonce", "")
    signature = headers.get("Wechatpay-Signature", "")
    serial = headers.get("Wechatpay-Serial", "")

    if not all([timestamp, nonce, signature, serial]):
        logger.warning("回调缺少签名头")
        return False

    # TODO: 生产环境需要用微信平台公钥验证签名
    # 此处先返回True，确保流程跑通后再补全验签逻辑
    return True


def decrypt_callback_data(resource: dict) -> dict:
    """
    AES-256-GCM解密回调通知数据

    参数:
        resource: 回调body中的resource字段，含 algorithm, ciphertext, nonce, associated_data
    返回:
        解密后的订单信息字典
    """
    try:
        ciphertext = base64.b64decode(resource["ciphertext"])
        nonce = resource["nonce"].encode("utf-8")
        associated_data = resource.get("associated_data", "").encode("utf-8")

        key = API_KEY_V3.encode("utf-8")
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)

        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        logger.error(f"解密回调数据失败: {e}")
        return {}
