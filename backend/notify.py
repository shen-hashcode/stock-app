"""
管理员通知模块

通过微信订阅消息通知管理员：
1. 有新策略生成
2. 有用户购买订阅
"""

import os
import httpx
from datetime import datetime
from database import SessionLocal, User
from logger import logger
from dotenv import load_dotenv

load_dotenv()

WECHAT_APPID = os.getenv("WECHAT_APPID", "")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
# 订阅消息模板ID，需要在微信公众平台配置
TEMPLATE_ID = os.getenv("WX_NOTIFY_TEMPLATE_ID", "")

_access_token = None
_token_expire_time = 0


async def _get_access_token() -> str:
    """获取微信access_token（带缓存）"""
    global _access_token, _token_expire_time
    import time

    if _access_token and time.time() < _token_expire_time:
        return _access_token

    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={WECHAT_APPID}&secret={WECHAT_SECRET}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        data = resp.json()

    if "access_token" in data:
        _access_token = data["access_token"]
        _token_expire_time = time.time() + data.get("expires_in", 7200) - 300
        return _access_token
    else:
        logger.error(f"获取access_token失败: {data}")
        raise Exception(f"获取access_token失败: {data}")


async def notify_admins_new_strategy(user_id: int, strategy_id: int, strategy_name: str, user_nickname: str):
    """
    异步通知所有管理员有新策略生成

    通知内容包含：用户ID、策略ID、用户昵称、策略名称、创建时间
    """
    if not WECHAT_APPID or not WECHAT_SECRET or not TEMPLATE_ID:
        logger.warning("微信通知配置不完整，跳过管理员通知")
        return

    db = SessionLocal()
    try:
        admins = db.query(User).filter(User.is_admin == True).all()
        if not admins:
            logger.warning("没有管理员用户，跳过通知")
            return

        access_token = await _get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={access_token}"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for admin in admins:
            if not admin.openid or admin.openid.startswith("phone_"):
                continue

            payload = {
                "touser": admin.openid,
                "template_id": TEMPLATE_ID,
                "data": {
                    "thing1": {"value": f"用户{user_nickname}(ID:{user_id})生成了新策略"},
                    "thing2": {"value": f"策略:{strategy_name}(ID:{strategy_id})"},
                    "time3": {"value": now},
                }
            }

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=payload)
                    result = resp.json()
                    if result.get("errcode") == 0:
                        logger.info(f"管理员通知发送成功: admin={admin.id}")
                    else:
                        logger.warning(f"管理员通知发送失败: admin={admin.id}, error={result}")
            except Exception as e:
                logger.warning(f"管理员通知发送异常: admin={admin.id}, error={e}")
    except Exception as e:
        logger.error(f"管理员通知流程异常: {e}")
    finally:
        db.close()


async def notify_admins_new_subscription(user_id: int, user_nickname: str, package_name: str, amount_cents: int):
    """
    通知管理员有用户购买了订阅套餐

    管理员收到通知后知道需要为该用户准备策略脚本
    """
    if not WECHAT_APPID or not WECHAT_SECRET or not TEMPLATE_ID:
        logger.warning("微信通知配置不完整，跳过订阅通知")
        return

    db = SessionLocal()
    try:
        admins = db.query(User).filter(User.is_admin == True).all()
        if not admins:
            logger.warning("没有管理员用户，跳过通知")
            return

        access_token = await _get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={access_token}"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        amount_yuan = amount_cents / 100

        for admin in admins:
            if not admin.openid or admin.openid.startswith("phone_"):
                continue

            payload = {
                "touser": admin.openid,
                "template_id": TEMPLATE_ID,
                "data": {
                    "thing1": {"value": f"用户{user_nickname}(ID:{user_id})购买了订阅"},
                    "thing2": {"value": f"套餐:{package_name}，金额:{amount_yuan}元"},
                    "time3": {"value": now},
                }
            }

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=payload)
                    result = resp.json()
                    if result.get("errcode") == 0:
                        logger.info(f"订阅通知发送成功: admin={admin.id}")
                    else:
                        logger.warning(f"订阅通知发送失败: admin={admin.id}, error={result}")
            except Exception as e:
                logger.warning(f"订阅通知发送异常: admin={admin.id}, error={e}")
    except Exception as e:
        logger.error(f"订阅通知流程异常: {e}")
    finally:
        db.close()