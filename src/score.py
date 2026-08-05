"""阶段 3：打分筛选 —— 按六个维度给候选论文打分，只保留最值得读的几篇

六个维度（满分 100，各维度有上限，总分 = 六项之和）：
1. 主题相关 (35)：标题/摘要与关键词的吻合程度；低于 10 分直接淘汰
2. 方法学价值 (20)：摘要里出现的方法类关键词越多，价值越高
3. 期刊质量 (15)：期刊知名度（Nature 系、顶级化学材料期刊高，预印本低）
4. 关联度 (10)：与 config 里配置的关注作者/机构的关联
5. 应用价值 (10)：成像、治疗、诊断等应用类词汇
6. 归档价值 (10)：摘要完整度等长期参考价值

用法：
    python src/score.py

输入：data/candidates.json（阶段 2 生成）
输出：data/selected.json（最终入选的论文）+ 终端打分表
"""

import json
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
CANDIDATES_PATH = os.path.join(ROOT, "data", "candidates.json")
SELECTED_PATH = os.path.join(ROOT, "data", "selected.json")

# 六维权重（与 config.yaml 里的 scoring 一致）
WEIGHTS = {"topic": 35, "method": 20, "journal": 15, "network": 10, "applied": 10, "archival": 10}

# 各种"看起来像连字符"的字符（Unicode 里的 ‐ – — 等），统一当成普通连字符处理
HYPHEN_CHARS = "\u2010\u2011\u2012\u2013\u2014\u2015"


def norm(text):
    """小写 + 连字符归一化，避免 NIR‐II 和 NIR-II 匹配不上"""
    return "".join("-" if ch in HYPHEN_CHARS else ch for ch in (text or "")).lower()

# 期刊质量分级：按片段匹配，越靠前的越先匹配（长名字放前面，避免"Nature Communications"被"Nature"抢先）
JOURNAL_TIERS = [
    ("Nature Communications", 14),
    ("Nature", 15),
    ("Science", 15),
    ("Cell", 15),
    ("Journal of the American Chemical Society", 14),
    ("JACS", 14),
    ("Angewandte", 14),
    ("Advanced Materials", 14),
    ("Advanced Science", 14),
    ("ACS Nano", 14),
    ("Nano Letters", 13),
    ("PNAS", 13),
    ("Advanced Functional Materials", 13),
    ("Journal of Nanobiotechnology", 12),
    ("ACS Applied", 12),
    ("Biomaterials", 12),
    ("Chemical Engineering Journal", 12),
    ("Analytical Chemistry", 12),
    ("ChemRxiv", 5),
    ("arXiv", 5),
    ("bioRxiv", 5),
    ("SSRN", 5),
]

# 方法学信号词：出现越多，说明论文的方法描述越具体
METHOD_WORDS = [
    "synthesis", "synthesized", "characterization", "in vivo", "in vitro",
    "experiment", "density functional", "molecular dynamics", "quantum yield",
    "photothermal", "photodynamic", "nanoparticle", "conjugated", "doping",
    "stability", "fluorescence lifetime", "quantum dot", "hydrogel", "coating",
    "self-assembly", "rationetric", "turn-on", "turn-off",
]

# 应用价值信号词
APPLIED_WORDS = [
    "imaging", "theranostic", "therapy", "photothermal", "photodynamic",
    "diagnosis", "biosensor", "cancer", "tumor", "in vivo", "clinical",
    "surgery", "drug", "nanomedicine", "immunotherapy", "guided",
]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_candidates():
    with open(CANDIDATES_PATH, encoding="utf-8") as f:
        return json.load(f)


def signature_tokens(keywords):
    """从关键词里提炼"标志性词"，如 NIR-II 里的 nir-ii（带连字符的独特词）"""
    tokens = set()
    for kw in keywords:
        for token in norm(kw).split():
            if "-" in token:
                tokens.add(token)
    return tokens


def score_topic(paper, keywords):
    """主题相关（上限 35）：标题出现标志性词 +12；关键词短语出现在标题 +8、摘要 +4"""
    title = norm(paper.get("title"))
    abstract = norm(paper.get("abstract"))
    score = 0.0
    for token in signature_tokens(keywords):
        if token in title:
            score += 12
            break
    for kw in keywords:
        kw_lower = norm(kw)
        if kw_lower in title:
            score += 8
        elif kw_lower in abstract:
            score += 4
    return min(WEIGHTS["topic"], score)


def score_method(paper):
    """方法学价值（上限 20）：摘要里每出现一个方法学信号词 +2.5"""
    abstract = norm(paper.get("abstract"))
    hits = sum(1 for word in METHOD_WORDS if word in abstract)
    return min(WEIGHTS["method"], hits * 2.5)


def score_journal(paper):
    """期刊质量（上限 15）：匹配分级表里"最长的命中期刊名"，避免 Advanced Science 被 Science 抢走"""
    journal = norm(paper.get("journal"))
    best_value = 8.0
    best_length = 0
    for name, value in JOURNAL_TIERS:
        tier_name = norm(name)
        if tier_name in journal and len(tier_name) > best_length:
            best_value = value
            best_length = len(tier_name)
    return float(best_value)


def score_network(paper, important):
    """关联度（上限 10）：config 里配置的关注作者/机构，命中一个 +5"""
    if not important:
        return 0.0
    text = norm(
        " ".join(paper.get("authors") or [])
        + " "
        + (paper.get("journal") or "")
    )
    hits = sum(1 for name in important if norm(name) in text)
    return min(WEIGHTS["network"], hits * 5.0)


def score_applied(paper):
    """应用价值（上限 10）：标题/摘要里每出现一个应用信号词 +2"""
    text = norm((paper.get("title") or "") + " " + (paper.get("abstract") or ""))
    hits = sum(1 for word in APPLIED_WORDS if word in text)
    return min(WEIGHTS["applied"], hits * 2.0)


def score_archival(paper):
    """归档价值（上限 10）：摘要越完整，长期参考价值越高"""
    length = len(paper.get("abstract") or "")
    if length >= 1200:
        return 10.0
    if length >= 800:
        return 8.0
    if length >= 400:
        return 6.0
    if length >= 150:
        return 4.0
    return 2.0


def score_paper(paper, config):
    """给一篇论文打六维分，返回（分数字典, 各项是否合规）"""
    research = config["research_profile"]
    keywords = research["keywords"]["include"]
    important = research.get("important_authors_or_orgs", [])
    scores = {
        "topic": score_topic(paper, keywords),
        "method": score_method(paper),
        "journal": score_journal(paper),
        "network": score_network(paper, important),
        "applied": score_applied(paper),
        "archival": score_archival(paper),
    }
    # 安全校验：任何维度不能超过权重上限，总分必须等于六项之和
    ok = all(scores[k] <= WEIGHTS[k] for k in WEIGHTS)
    total = sum(scores.values())
    return scores, total, ok


def main():
    config = load_config()
    candidates = load_candidates()
    top_n = config["search"]["final_selection_count"]

    print("候选论文 {} 篇，开始六维打分……".format(len(candidates)))
    print()

    ranked = []
    for paper in candidates:
        scores, total, ok = score_paper(paper, config)
        if not ok:
            print("⚠️ 发现不合规的分数，请检查评分逻辑：", paper["title"][:50])
        if scores["topic"] < 10:
            print("主题相关低于 10 分，淘汰：", paper["title"][:60])
            continue
        ranked.append((total, scores, paper))

    ranked.sort(key=lambda x: x[0], reverse=True)
    selected = [
        {**paper, "scores": scores, "total": total} for total, scores, paper in ranked
    ]
    selected = selected[:top_n]

    with open(SELECTED_PATH, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)

    print("最终入选 {} 篇，已保存到 data/selected.json".format(len(selected)))
    print()
    for i, (total, scores, paper) in enumerate(ranked, 1):
        mark = ">>> 入选" if i <= top_n else "   未入"
        print("{} #{} [{:>4.1f}分] {}".format(mark, i, total, paper["title"][:60]))
        print(
            "        主题{:.1f} 方法{:.1f} 期刊{:.1f} 关联{:.1f} 应用{:.1f} 归档{:.1f}".format(
                scores["topic"], scores["method"], scores["journal"],
                scores["network"], scores["applied"], scores["archival"],
            )
        )


if __name__ == "__main__":
    main()
