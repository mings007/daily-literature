"""阶段 6：归档 —— 把入选论文存进本地文献库 + 更新"已推送"索引

用法：
    python src/archive.py

输入：data/selected.json（阶段 3 生成）
输出：
  - 笔记：data/archive/YYYY-MM-DD/*.md（config 配了 Obsidian 路径则写到那里）
  - 索引：data/seen.json（记录已推送论文，避免明天重复推送）
"""

import datetime
import json
import os

import yaml

from search import paper_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
SELECTED_PATH = os.path.join(ROOT, "data", "selected.json")
SEEN_PATH = os.path.join(ROOT, "data", "seen.json")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_note(paper):
    scores = paper.get("scores", {})
    title = paper.get("title", "").replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        "---",
        'title: "{}"'.format(title),
        'journal: "{}"'.format(paper.get("journal", "")),
        "date: {}".format(paper.get("publication_date", "")),
        'doi: "{}"'.format(paper.get("doi", "")),
        "score: {:.1f}/100".format(paper.get("total", 0)),
        "---",
        "",
        "## 链接",
        paper.get("url", ""),
        "",
        "## 摘要",
        paper.get("abstract", "") or "（无摘要）",
        "",
        "## 六维评分",
        "主题 {:.1f} / 方法 {:.1f} / 期刊 {:.1f} / 关联 {:.1f} / 应用 {:.1f} / 归档 {:.1f}".format(
            scores.get("topic", 0), scores.get("method", 0), scores.get("journal", 0),
            scores.get("network", 0), scores.get("applied", 0), scores.get("archival", 0),
        ),
    ]
    return "\n".join(lines)


def section_text(body, heading):
    """提取笔记正文中某个二级标题下的内容（到下一个二级标题为止）"""
    marker = "## " + heading + "\n"
    if marker not in body:
        return ""
    rest = body.split(marker, 1)[1]
    next_heading = rest.find("\n## ")
    if next_heading != -1:
        rest = rest[:next_heading]
    return " ".join(rest.split())


def parse_note(text):
    """把一篇归档笔记解析成网页索引条目；不是本系统格式的文件返回 None"""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except Exception:
        return None
    if not meta.get("title") or not meta.get("doi"):
        return None
    body = parts[2]
    score_text = str(meta.get("score", "")).split("/")[0]
    try:
        score = float(score_text)
    except ValueError:
        score = 0
    return {
        "title": meta.get("title", ""),
        "journal": meta.get("journal", ""),
        "date": str(meta.get("date", "")),
        "doi": meta.get("doi", ""),
        "score": score,
        "url": section_text(body, "链接"),
        "abstract": section_text(body, "摘要")[:400],
    }


def build_index(archive_root):
    """扫描归档目录，生成网页版历史记录的数据（按日期倒序）"""
    entries = []
    for dirpath, _, filenames in os.walk(archive_root):
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            path = os.path.join(dirpath, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    entry = parse_note(f.read())
            except Exception:
                entry = None
            if entry:
                entries.append(entry)
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries


def main():
    config = load_config()
    selected = json.load(open(SELECTED_PATH, encoding="utf-8"))

    archive_root = config.get("archive", {}).get("root")
    if not archive_root or archive_root == "CHANGE_ME":
        archive_root = os.path.join(ROOT, "data", "archive")
        print("提示：config.yaml 的 archive.root 还是 CHANGE_ME，先归档到本地 data/archive/")

    today = datetime.date.today().isoformat()
    day_dir = os.path.join(archive_root, today)
    os.makedirs(day_dir, exist_ok=True)

    seen = {}
    if os.path.exists(SEEN_PATH):
        seen = json.load(open(SEEN_PATH, encoding="utf-8"))

    for paper in selected:
        key = paper_key(paper)
        if not key:
            continue
        filename = key.replace(":", "_").replace("/", "_") + ".md"
        with open(os.path.join(day_dir, filename), "w", encoding="utf-8") as f:
            f.write(render_note(paper))
        seen[key] = today

    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)
    print("归档 {} 篇到 {}，并更新 data/seen.json".format(len(selected), day_dir))

    # 同步更新网页版历史记录的数据文件
    index_path = os.path.join(ROOT, "docs", "index.json")
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    entries = build_index(archive_root)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print("网页版历史已更新：docs/index.json（共 {} 条）".format(len(entries)))


if __name__ == "__main__":
    main()
