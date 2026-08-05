"""期刊盯梢 —— 抓取重点期刊的最新目录（RSS），只留下与研究领域相关的论文

这些 RSS 源来自出版社官网，公开免费，不需要登录，也不违反使用协议。
相比 OpenAlex，期刊目录更新更快（论文上线当天就能抓到）。

用法：
    python src/rss_watch.py

要盯的期刊在 config.yaml 的 journal_watch 里配置。
输出：data/rss_results.json（相关论文，稍后与搜索候选合并去重）
"""

import datetime
import email.utils
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

import yaml

from search import matches_keywords, norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
OUTPUT_PATH = os.path.join(ROOT, "data", "rss_results.json")

# 非研究类内容的标题特征（勘误、社论、新闻等，跳过）
SKIP_TITLE_HINTS = ("correction", "erratum", "editorial", "retraction", "news",
                    "comment", "erratum:", "addendum")

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s<>\"]+")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_rss(url, timeout=20):
    """抓取 RSS 文本，失败时抛异常由调用方跳过"""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "daily-literature-tracker/0.1",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def local_name(tag):
    """去掉 XML 命名空间前缀，取标签名"""
    return tag.rsplit("}", 1)[-1]


def child_text(element, name):
    """取子元素文本（兼容带命名空间的 XML）"""
    for child in element:
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def parse_feed(text):
    """解析 RSS 2.0 或 Atom 源，统一返回 [{title, link, description, pub_date}]"""
    root = ET.fromstring(text)
    kind = local_name(root.tag)
    items = []
    if kind == "feed":  # Atom
        for entry in root.iter():
            if local_name(entry.tag) != "entry":
                continue
            link = ""
            for child in entry:
                if local_name(child.tag) == "link":
                    link = child.get("href") or child.text or ""
            items.append(
                {
                    "title": child_text(entry, "title"),
                    "link": link,
                    "description": child_text(entry, "summary"),
                    "pub_date": child_text(entry, "updated"),
                }
            )
    else:  # RSS 2.0
        for item in root.iter():
            if local_name(item.tag) != "item":
                continue
            items.append(
                {
                    "title": child_text(item, "title"),
                    "link": child_text(item, "link"),
                    "description": child_text(item, "description"),
                    "pub_date": child_text(item, "pubDate"),
                }
            )
    return items


def strip_html(text):
    """去掉 HTML 标签，压缩空白，方便做关键词匹配"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(text.split())


def parse_date(text):
    """把 RSS 里的日期解析成 YYYY-MM-DD；解析不了返回空串"""
    if not text:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(text)
        return dt.date().isoformat()
    except Exception:
        return (text or "")[:10]


def rss_item_to_paper(item, journal_name):
    """把一条 RSS 记录转成统一的论文格式"""
    description = strip_html(item.get("description"))
    title = " ".join((item.get("title") or "").split())
    link = item.get("link") or ""
    doi_match = DOI_PATTERN.search(link + " " + description)
    doi = doi_match.group(0).rstrip(".,;").split("?")[0] if doi_match else ""
    return {
        "title": title,
        "authors": [],
        "year": (item.get("pub_date") or "")[:4],
        "source": "rss:" + journal_name,
        "journal": journal_name,
        "doi": doi,
        "arxiv_id": "",
        "url": link,
        "abstract": description,
        "publication_date": parse_date(item.get("pub_date")),
    }


def main():
    config = load_config()
    keywords = config["research_profile"]["keywords"]["include"]
    exclude = config["research_profile"]["keywords"].get("exclude", [])
    journals = config.get("journal_watch", [])
    lookback = config["search"]["lookback_days"]
    from_date = datetime.date.today() - datetime.timedelta(days=lookback)

    if not journals:
        print("config.yaml 里还没有配置 journal_watch，先添加想盯的期刊。")
        return

    print("回看范围：", from_date, "→", datetime.date.today())
    print()
    relevant_all = []
    for journal in journals:
        name = journal["name"]
        url = journal["rss"]
        try:
            items = parse_feed(fetch_rss(url))
            kept = []
            for item in items:
                title = (item.get("title") or "").lower()
                if any(title.startswith(h) for h in SKIP_TITLE_HINTS):
                    continue
                paper = rss_item_to_paper(item, name)
                if paper.get("publication_date") and paper["publication_date"] < from_date.isoformat():
                    continue
                if matches_keywords(paper, keywords, exclude):
                    kept.append(paper)
            relevant_all.extend(kept)
            print(
                "{}：目录 {} 条 → 相关 {} 条".format(name, len(items), len(kept))
            )
        except Exception as error:
            print("{}：抓取失败（{}），已跳过".format(name, error))

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(relevant_all, f, ensure_ascii=False, indent=2)

    print()
    print("期刊盯梢共发现 {} 篇相关论文，已保存到 data/rss_results.json".format(len(relevant_all)))
    for i, paper in enumerate(relevant_all[:10], 1):
        print("  {}. [{}] {}".format(i, paper["journal"], paper["title"][:70]))


if __name__ == "__main__":
    main()
