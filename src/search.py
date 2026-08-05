"""阶段 2：多源搜索 —— 每天为你抓取最近几天的新论文

从 arXiv / OpenAlex / Crossref 三个免费数据库抓取候选论文，
每个关键词单独搜索，再用标题/摘要做相关性过滤，
最后去掉重复并保存到 data/candidates.json，供下一步打分筛选。

用法（在项目根目录）：
    python src/search.py

抓取数量、关键词、回看天数都在 config.yaml 里配置。
某个数据库临时挂了也没关系——代码会自动跳过它，用剩下的数据库继续。
"""

import datetime
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import yaml

# 项目根目录（本文件在 src/ 下，所以往上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
CANDIDATES_PATH = os.path.join(ROOT, "data", "candidates.json")

# arXiv 返回的是 XML，需要这些命名空间才能读到里面的字段
ARXIV_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# 各种"看起来像连字符"的字符（Unicode 里的 ‐ – — 等），统一当成普通连字符处理
HYPHEN_CHARS = "\u2010\u2011\u2012\u2013\u2014\u2015"


def norm(text):
    """小写 + 连字符归一化，避免 NIR‐II 和 NIR-II 匹配不上"""
    return "".join("-" if ch in HYPHEN_CHARS else ch for ch in (text or "")).lower()


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def http_get_json(url, timeout=20):
    """请求一个返回 JSON 的接口；网络抖动时自动重试 2 次"""
    return _request_with_retry(url, timeout, as_json=True)


def http_get_text(url, timeout=20):
    """请求一个返回文本的接口（arXiv 返回 XML 文本）；网络抖动时自动重试"""
    return _request_with_retry(url, timeout, as_json=False)


def _request_with_retry(url, timeout, as_json):
    last_error = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "daily-literature-tracker/0.1"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            return json.loads(body) if as_json else body
        except Exception as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 * (attempt + 1))  # 等 2 秒、4 秒后重试
    raise last_error


def search_arxiv(keyword, exclude, from_date, to_date, max_results):
    """arXiv：预印本库，物理/计算机/数学等领域更新最快"""
    query = 'all:"{}"'.format(keyword)
    for word in exclude:
        query += ' ANDNOT all:"{}"'.format(word)
    query += " AND submittedDate:[{}0000 TO {}2359]".format(
        from_date.strftime("%Y%m%d"), to_date.strftime("%Y%m%d")
    )
    url = (
        "http://export.arxiv.org/api/query?search_query={}"
        "&max_results={}&sortBy=submittedDate&sortOrder=descending"
    ).format(urllib.parse.quote(query), max_results)

    root = ET.fromstring(http_get_text(url))
    papers = []
    for entry in root.findall("a:entry", ARXIV_NS):
        title = " ".join(
            (entry.findtext("a:title", default="", namespaces=ARXIV_NS) or "").split()
        )
        summary = " ".join(
            (entry.findtext("a:summary", default="", namespaces=ARXIV_NS) or "").split()
        )
        published = entry.findtext("a:published", default="", namespaces=ARXIV_NS)
        authors = [
            a.findtext("a:name", default="", namespaces=ARXIV_NS)
            for a in entry.findall("a:author", ARXIV_NS)
        ]
        link = entry.findtext("a:id", default="", namespaces=ARXIV_NS)
        arxiv_id = link.rsplit("/", 1)[-1] if link else ""
        papers.append(
            {
                "title": title,
                "authors": authors,
                "year": published[:4],
                "source": "arxiv",
                "journal": "arXiv preprint",
                "doi": "",
                "arxiv_id": arxiv_id,
                "url": link,
                "abstract": summary,
                "publication_date": published[:10],
            }
        )
    return papers


def reconstruct_abstract(inverted_index):
    """OpenAlex 把摘要打散成"单词 -> 位置"的字典，这里把它还原成句子"""
    if not inverted_index:
        return ""
    words = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))


def search_openalex(keyword, exclude, from_date, to_date, max_results):
    """OpenAlex：覆盖全球学术文献的开放数据库，期刊论文为主"""
    # 不加引号：要求标题/摘要里同时出现关键词的几个词（如 NIR-II 和 imaging），
    # 比完整短语匹配召回更多，比模糊搜索噪音更少
    url = (
        "https://api.openalex.org/works?"
        "filter=title_and_abstract.search:{},from_publication_date:{},"
        "to_publication_date:{}&sort=publication_date:desc&per-page={}"
        "&mailto=tracker@example.com"
    ).format(
        urllib.parse.quote(keyword),
        from_date.isoformat(),
        to_date.isoformat(),
        max_results,
    )

    data = http_get_json(url)
    papers = []
    for work in data.get("results", []):
        title = (work.get("title") or "").strip()
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        source = (work.get("primary_location") or {}).get("source") or {}
        journal = source.get("display_name") or ""
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in work.get("authorships", [])
        ]
        papers.append(
            {
                "title": title,
                "authors": authors,
                "year": (work.get("publication_date") or "")[:4],
                "source": "openalex",
                "journal": journal,
                "doi": doi,
                "arxiv_id": "",
                "url": work.get("doi") or work.get("id", ""),
                "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
                "publication_date": work.get("publication_date") or "",
            }
        )
    return papers


def search_crossref(keyword, exclude, from_date, to_date, max_results):
    """Crossref：期刊论文的 DOI 注册中心，覆盖最广"""
    url = (
        "https://api.crossref.org/works?query.title={}"
        "&filter=from-pub-date:{},until-pub-date:{},type:journal-article"
        "&rows=50&sort=published&order=desc"
    ).format(
        urllib.parse.quote(keyword),
        from_date.isoformat(),
        to_date.isoformat(),
    )

    data = http_get_json(url)
    papers = []
    for item in data.get("message", {}).get("items", []):
        title = (item.get("title") or [""])[0]
        authors = [
            "{} {}".format(a.get("given", ""), a.get("family", "")).strip()
            for a in item.get("author", [])
        ]
        published = item.get("published", {}).get("date-parts", [[None]])[0]
        papers.append(
            {
                "title": title,
                "authors": authors,
                "year": published[0],
                "source": "crossref",
                "journal": (item.get("container-title") or [""])[0],
                "doi": item.get("DOI", ""),
                "arxiv_id": "",
                "url": "https://doi.org/{}".format(item.get("DOI", "")),
                "abstract": item.get("abstract", "") or "",
                "publication_date": "-".join(str(x) for x in published),
            }
        )
    return papers


def matches_keywords(paper, keywords, exclude=()):
    """相关性过滤：标题/摘要里出现任一关键词就算相关；
    关键词里有连字符词（如 NIR-II）时，标题出现该词也算相关。
    标题里出现排除词的论文直接淘汰。"""
    title = norm(paper.get("title"))
    text = norm((paper.get("title") or "") + " " + (paper.get("abstract") or ""))
    for word in exclude:
        if norm(word) in title:
            return False
    for kw in keywords:
        kw_lower = norm(kw)
        if kw_lower in text:
            return True
        for token in kw_lower.split():
            if "-" in token and token in title:
                return True
    return False


def paper_key(paper):
    """生成论文的去重/查重键：DOI -> arXiv 编号 -> 规范化标题"""
    if paper.get("doi"):
        return "doi:" + paper["doi"].lower()
    if paper.get("arxiv_id"):
        return "arxiv:" + paper["arxiv_id"].lower()
    if paper.get("title"):
        return "title:" + " ".join(norm(paper["title"]).split())
    return None


def deduplicate(papers):
    """按 DOI -> arXiv 编号 -> 规范化标题 的顺序去重"""
    seen = set()
    unique = []
    for paper in papers:
        key = paper_key(paper)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(paper)
    return unique


def main():
    config = load_config()
    research = config["research_profile"]
    keywords = research["keywords"]["include"]
    exclude = research["keywords"].get("exclude", [])
    search_cfg = config["search"]
    candidate_pool = search_cfg["candidate_pool_size"]
    lookback = search_cfg["lookback_days"]

    if not keywords or any(kw == "CHANGE_ME" for kw in keywords):
        print("先在 config.yaml 里填写研究领域和关键词（把 CHANGE_ME 替换掉），再运行本程序。")
        return

    # 每个关键词在每个数据库各抓多少篇；总数大致落在候选池规模附近
    per_keyword = max(5, candidate_pool // len(keywords) + 2)

    to_date = datetime.date.today()
    from_date = to_date - datetime.timedelta(days=lookback)
    print("领域：", research["field"])
    print("关键词：", keywords)
    print("回看范围：", from_date, "→", to_date)
    print()

    sources = [
        ("arXiv", search_arxiv, 3),  # arXiv 要求请求间隔 >=3 秒，必须礼貌等待
        ("OpenAlex", search_openalex, 0),
        ("Crossref", search_crossref, 0),
    ]
    all_papers = []
    for name, func, pause in sources:
        for kw in keywords:
            try:
                raw = func(kw, exclude, from_date, to_date, per_keyword)
                relevant = [p for p in raw if matches_keywords(p, keywords, exclude)]
                all_papers.extend(relevant)
                print(
                    "{}「{}」：原始 {} 篇 → 相关 {} 篇".format(
                        name, kw, len(raw), len(relevant)
                    )
                )
            except Exception as error:
                print("{}「{}」：暂时失败（{}），已自动跳过".format(name, kw, error))
            finally:
                if pause:
                    time.sleep(pause)

    unique = deduplicate(all_papers)
    os.makedirs(os.path.dirname(CANDIDATES_PATH), exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print()
    print("去重后共 {} 篇候选，已保存到 data/candidates.json".format(len(unique)))
    print("前 10 篇标题：")
    for i, paper in enumerate(unique[:10], 1):
        print("  {}. {}".format(i, paper["title"][:90]))


if __name__ == "__main__":
    main()
