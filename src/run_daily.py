"""一键运行完整流水线：

搜索 → 期刊盯梢 → 合并去重 → 过滤已推送 → 打分 → 生成日报 → 推送飞书 → 归档

用法（在项目根目录）：
    python src/run_daily.py
"""

import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import archive
import deliver
import digest
import rss_watch
import score
import search


def delivery_secret(env):
    """按 config.yaml 决定是否带签名。
    你的机器人用「自定义关键词」，use_signature=false，即使环境里有 FEISHU_SECRET 也忽略它。"""
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not config.get("delivery", {}).get("use_signature", False):
        return None
    return env.get("FEISHU_SECRET") or None


def merge_and_filter():
    """合并搜索候选 + 期刊盯梢结果，去重，并过滤掉已推送过的论文"""
    candidates = json.load(open(search.CANDIDATES_PATH, encoding="utf-8"))
    rss_papers = []
    if os.path.exists(rss_watch.OUTPUT_PATH):
        rss_papers = json.load(open(rss_watch.OUTPUT_PATH, encoding="utf-8"))

    merged = search.deduplicate(candidates + rss_papers)
    seen_path = os.path.join(ROOT, "data", "seen.json")
    seen = {}
    if os.path.exists(seen_path):
        seen = json.load(open(seen_path, encoding="utf-8"))
    fresh = [p for p in merged if search.paper_key(p) not in seen]

    with open(search.CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(fresh, f, ensure_ascii=False, indent=2)
    print(
        "合并后共 {} 篇，其中 {} 篇是新的（{} 篇已推送过，跳过）".format(
            len(merged), len(fresh), len(merged) - len(fresh)
        )
    )
    return fresh


def main():
    if "--send-test" in sys.argv:
        env = deliver.load_env()
        webhook = env.get("WEBHOOK_URL", "")
        if not webhook:
            print("ERROR: 没有配置 WEBHOOK_URL（检查 GitHub 密钥或本地 .env），无法发送测试消息。")
            sys.exit(1)
        result = deliver.send_message(
            "云端文献追踪测试消息：密钥配置成功，链路已打通！",
            webhook,
            delivery_secret(env),
        )
        print("飞书返回：", result)
        return

    print("========== 第 1 步：多源搜索 ==========")
    search.main()

    print()
    print("========== 第 2 步：期刊盯梢（RSS） ==========")
    rss_watch.main()

    print()
    print("========== 第 3 步：合并去重 + 过滤已推送 ==========")
    fresh = merge_and_filter()
    if not fresh:
        print("没有新的候选论文，本次到此结束（明天再来）。")
        return

    print()
    print("========== 第 4 步：六维打分 ==========")
    score.main()

    print()
    print("========== 第 5 步：生成日报 ==========")
    digest.main()

    print()
    print("========== 第 6 步：推送到飞书 ==========")
    env = deliver.load_env()
    webhook = env.get("WEBHOOK_URL", "")
    if not webhook:
        print("没有配置 WEBHOOK_URL（检查 GitHub 密钥或本地 .env），跳过推送。")
        print("日报已保存在 data/digest.md，可手动查看。")
    else:
        print("Webhook 已配置，正在发送……")
        with open(digest.DIGEST_PATH, encoding="utf-8") as f:
            text = f.read()
        result = deliver.send_message(
            text, webhook, delivery_secret(env)
        )
        print("飞书返回：", result)

    print()
    print("========== 第 7 步：归档 ==========")
    archive.main()

    print()
    print("全部完成！去飞书群看看今天的文献日报吧。")


if __name__ == "__main__":
    main()
