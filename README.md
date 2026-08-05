# 每日文献追踪查新

一个帮你每天自动盯住某个研究领域最新进展的「App」。它不需要手机界面——本质上是一条每天自动运行的流水线：

> 搜索 → 去重 → 打分筛选 → 精读摘要 → 推送给你 → 归档笔记

## 每天它为你做什么

1. **搜索**：从 arXiv、OpenAlex、Crossref 等学术数据库抓取最近几天的新论文（默认 30 篇候选）
2. **去重**：按 DOI / arXiv ID / 标题去掉重复
3. **打分筛选**：按 6 个维度打分，只留下最值得读的 5 篇
4. **精读摘要**：为每篇生成一句话结论、方法、关键结果、点评
5. **推送**：把摘要发到你的飞书 / Telegram / 本地文件
6. **归档**：把笔记存进 Obsidian 或本地文件夹，方便以后检索

## 目录结构

```
每日文献追踪查新/
├── README.md            # 本文件：项目说明和使用指南
├── config.yaml          # 配置文件（App 的"大脑"）：领域、关键词、权重、推送目标
├── src/                 # 程序代码，每个文件负责流水线的一个环节
│   ├── search.py        # 阶段 2：多源搜索
│   ├── score.py         # 阶段 3：打分筛选
│   ├── digest.py        # 阶段 4：摘要生成
│   ├── deliver.py       # 阶段 5：推送
│   └── archive.py       # 阶段 6：归档
├── data/
│   └── seen.json        # 去重索引（记录看过的论文，防止重复推送）
└── templates/
    └── digest.md        # 每日推送的格式模板
```

## 运行环境（已配置好，了解即可）

本项目统一使用 Codex 自带的 Python 3.12，已安装好唯一的第三方组件 PyYAML。
以后运行任何脚本都用这条命令（在项目根目录下）：

```bash
& "C:\Users\mamin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" src\search.py
```

（不用记——每次我带你运行时都会直接执行。）

## 飞书配置（5 分钟，一次性）

飞书推送用的是「群自定义机器人」的 Webhook 地址，不需要开发飞书应用，最简单。

1. 打开飞书，**新建一个专属群**（比如叫「文献日报」），或者进入你已有的群
2. 点群右上角 **⋯** → **设置** → **群机器人** → **添加机器人** → **自定义机器人**
3. 机器人名字随便起（比如「文献日报」），然后进入「安全设置」
4. **安全设置推荐选「加签」**：勾选后会出现一个 Secret 密钥，复制保存
   （如果你不想加签，也可以勾选「自定义关键词」——但那样每天的推送内容里必须包含那个关键词，比较麻烦，所以推荐加签）
5. 点「完成」，**复制 Webhook 地址**（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`）
6. 把项目里的 `.env.example` 复制一份改名为 `.env`，填入：

```bash
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/你复制的那串
FEISHU_SECRET=你复制的那串密钥（没选加签就留空）
```

7. 回来告诉我已经填好了，我们跑一条测试消息验证链路。

## 我们的路线图（一步一步来）

| 阶段 | 内容 | 状态 |
|:---:|------|:---:|
| 0 | 确定研究领域、关键词、推送方式 | ✅ 已完成 |
| 1 | 搭建项目骨架 | ✅ 已完成 |
| 2 | 实现搜索模块 + 期刊盯梢（RSS），跑通第一次抓取 | ✅ 已完成 |
| 3 | 实现打分筛选 + 日报生成 | ✅ 已完成 |
| 4 | 实现推送 + 归档 | ✅ 已完成 |
| 5 | 设置每日自动运行 | ⬜ 待设置 |
| 6 | 运行两周后调整关键词和评分权重 | ⬜ 待观察 |

每个阶段我都会先解释原理，再写代码，然后我们一起运行验证。你不用懂编程也能跟上——需要你做的只是告诉我你的领域，并检查每天推送的内容是否合口味。

## 一键运行

整条流水线（搜索 → 期刊盯梢 → 合并去重 → 打分 → 生成日报 → 推送飞书 → 归档）已经打通，
以后每天只要运行一条命令：

```bash
& "C:\Users\mamin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" src\run_daily.py
```

中间产物都在 `data/` 目录：`candidates.json`（候选）、`selected.json`（入选）、
`digest.md`（日报原文）、`archive/`（归档笔记）、`seen.json`（已推送索引，防止重复）。

## 网页版历史记录（GitHub Pages）

每天归档的论文会自动生成 `docs/index.json`，配合 `docs/index.html` 就是一个可搜索的网页版历史记录。
启用方法（一次性）：

1. 仓库 → **Settings → Pages**
2. **Source** 选 **Deploy from a branch** → 分支选 `main` → 目录选 `/docs` → **Save**
3. 等一两分钟，访问 `https://<你的用户名>.github.io/daily-literature/`

之后每天的归档都会自动同步到这个网页，手机浏览器也能看。

## 接入 Obsidian

归档笔记本身已经是带 YAML 头信息的 Markdown 文件，Obsidian 可以直接打开。
把 `config.yaml` 里的 `archive.root` 改成你 Obsidian 库里的一个专门文件夹
（例如 `D:\ObsidianVault\文献追踪`），本地运行 `src/run_daily.py` 时笔记就会直接写进 Obsidian。
云端运行仍写在仓库的 `data/archive/`（网页版数据来源），两边互不影响。
