"""阶段 4：生成每日文献日报

把入选论文变成一份可以直接推送的日报：
每篇包含 一句话结论 / 方法 / 关键结果 / 点评。

用法：
    python src/digest.py

输入：data/selected.json（阶段 3 生成）
输出：data/digest.md（推送给你的内容）
"""

import datetime
import json
import os
import re

import yaml

from score import METHOD_WORDS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
SELECTED_PATH = os.path.join(ROOT, "data", "selected.json")
CANDIDATES_PATH = os.path.join(ROOT, "data", "candidates.json")
DIGEST_PATH = os.path.join(ROOT, "data", "digest.md")

SEPARATOR = "──────────────────────────"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def split_sentences(text):
    """把摘要拆成句子（按句号+空格/换行）"""
    return [s.strip() for s in re.split(r"(?<=\.)\s+|\n", text or "") if s.strip()]


def one_liner(paper):
    """一句话结论：取摘要第一句"""
    abstract = paper.get("abstract") or ""
    if not abstract:
        return "（暂无摘要，建议点开链接看原文）"
    first = split_sentences(abstract)[0]
    return first[:180]


def method_text(paper):
    """方法：挑出含方法学关键词的句子（最多 2 句）"""
    abstract = paper.get("abstract") or ""
    if not abstract:
        return "（无摘要，无法提取）"
    picked = [
        s for s in split_sentences(abstract)
        if any(w in s.lower() for w in METHOD_WORDS)
    ]
    return " ".join(picked[:2])[:300] or "（摘要中未明确描述方法，建议看原文）"


def result_text(paper):
    """关键结果：挑出含数字/单位的句子（最多 2 句）"""
    abstract = paper.get("abstract") or ""
    if not abstract:
        return "（无摘要，无法提取）"
    picked = [s for s in split_sentences(abstract) if re.search(r"\d", s)]
    return " ".join(picked[:2])[:300] or "（摘要中未见具体数据，建议查看全文）"


def commentary(paper):
    """点评：根据六维分数给出诚实的判断"""
    scores = paper.get("scores", {})
    parts = []
    if scores.get("journal", 0) >= 13:
        parts.append("期刊质量高")
    elif scores.get("journal", 0) >= 10:
        parts.append("期刊质量较好")
    else:
        parts.append("来自预印本/一般来源")
    if scores.get("topic", 0) >= 25:
        parts.append("与主线高度相关")
    elif scores.get("topic", 0) >= 15:
        parts.append("与主线相关")
    else:
        parts.append("相关性一般")
    if scores.get("applied", 0) >= 8:
        parts.append("应用价值突出")
    if scores.get("method", 0) >= 10:
        parts.append("方法描述详实")
    sentence = "；".join(parts) + "。"
    if scores.get("journal", 0) >= 12 and scores.get("method", 0) >= 10:
        sentence += "建议精读全文。"
    else:
        sentence += "可先读摘要，确有兴趣再看全文。"
    return sentence


def reading_depth(paper):
    """精读深度标签：有像样的摘要算「仅摘要」，否则「仅元数据」"""
    return "仅摘要" if len(paper.get("abstract") or "") >= 100 else "仅元数据"


def render_paper(index, paper):
    authors = paper.get("authors") or []
    author_str = ", ".join(authors[:2]) + (" et al." if len(authors) > 2 else "")
    lines = [
        SEPARATOR,
        "🏆 #{} | {}".format(index, paper["title"]),
        "{}, {} | {} | ⭐ {:.1f}/10 | 精读深度：{}".format(
            paper.get("journal", ""),
            paper.get("year", ""),
            author_str,
            paper.get("total", 0) / 10,
            reading_depth(paper),
        ),
    ]
    if paper.get("doi"):
        lines.append("DOI: {}".format(paper["doi"]))
    lines.append("🔗 {}".format(paper.get("url", "")))
    lines += [
        "",
        "💡 一句话：{}".format(one_liner(paper)),
        "",
        "🔬 方法：{}".format(method_text(paper)),
        "",
        "📊 关键结果：{}".format(result_text(paper)),
        "",
        "🗒 点评：{}".format(commentary(paper)),
        "",
    ]
    return "\n".join(lines)


def main():
    config = load_config()
    selected = json.load(open(SELECTED_PATH, encoding="utf-8"))
    try:
        candidate_count = len(json.load(open(CANDIDATES_PATH, encoding="utf-8")))
    except Exception:
        candidate_count = len(selected)

    lines = [
        "📚 {} 文献日报 | {}".format(
            datetime.date.today().isoformat(), config["research_profile"]["field"]
        ),
        "候选池：{} 篇 → 精选：{} 篇".format(candidate_count, len(selected)),
        "",
    ]
    for i, paper in enumerate(selected, 1):
        lines.append(render_paper(i, paper))

    text = "\n".join(lines).strip() + "\n"
    with open(DIGEST_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print("日报已生成：data/digest.md（{} 篇）".format(len(selected)))
    print()
    for i, paper in enumerate(selected, 1):
        print("  {}. {} [{:.1f}分]".format(i, paper["title"][:70], paper.get("total", 0)))


if __name__ == "__main__":
    main()
