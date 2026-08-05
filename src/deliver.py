"""阶段 5：推送 —— 把每日摘要发到飞书群

飞书推送用的是「群自定义机器人」的 Webhook 地址：
你创建机器人后拿到一个链接，程序往这个链接发一条 HTTP 请求，
消息就会出现在群里。

用法（先在 .env 里填好 WEBHOOK_URL，可选 FEISHU_SECRET）：
    python src/deliver.py --test        发一条测试消息，验证链路是否打通

之后阶段 4 生成的摘要会调用 send_message() 真正推送。
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request


def load_env():
    """读取配置：优先取环境变量（云端定时任务用），其次读项目根目录 .env 文件"""
    env = {}
    for key in ("WEBHOOK_URL", "FEISHU_SECRET"):
        value = os.environ.get(key, "")
        if value:
            env[key] = value
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def make_sign(secret, timestamp):
    """飞书加签算法：对 timestamp+换行+secret 做 HMAC-SHA256，再 base64"""
    string_to_sign = "{}\n{}".format(timestamp, secret)
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_message(text, webhook_url, secret=None):
    """向飞书群发送一条文本消息，返回飞书服务器的响应"""
    payload = {"msg_type": "text", "content": {"text": text}}
    if secret:
        # 创建机器人时若勾选了"加签"，每条消息必须带上时间戳和签名
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = make_sign(secret, timestamp)

    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    env = load_env()
    webhook_url = env.get("WEBHOOK_URL", "")
    secret = env.get("FEISHU_SECRET", "")
    if not webhook_url:
        print("还没有配置 Webhook：请复制 .env.example 为 .env 并填写 WEBHOOK_URL")
        sys.exit(1)
    if "--test" in sys.argv:
        result = send_message(
            "✅ 文献追踪测试消息：推送链路已打通！", webhook_url, secret or None
        )
        print("飞书返回：", result)
