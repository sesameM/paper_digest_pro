# paper-distill-pro

**基于 MCP 协议的学术论文搜索、智能筛选与多平台推送服务器**

> 11 源并行检索 · PDF 全文解析 · Zotero / Mendeley / Notion 双向同步 · GitHub Actions 定时推送

---

## 目录

1. [项目概述](#1-项目概述)
2. [设计思路](#2-设计思路)
3. [系统架构](#3-系统架构)
4. [目录结构](#4-目录结构)
5. [核心模块详解](#5-核心模块详解)
6. [MCP Server 工具清单](#6-mcp-server-工具清单)
7. [GitHub Actions 工作流](#7-github-actions-工作流)
8. [安装与配置](#8-安装与配置)
9. [接入 AI 客户端](#9-接入-ai-客户端)
10. [典型使用场景](#10-典型使用场景)
11. [扩展开发指南](#11-扩展开发指南)
12. [测试](#12-测试)
13. [常见问题](#13-常见问题)
14. [技术选型](#14-技术选型)
15. [附录：快速参考](#15-附录快速参考)

---

## 1 项目概述

paper-distill-pro 是一个完整的学术论文自动化处理平台，通过 **MCP（Model Context Protocol）** 协议暴露给 Claude Desktop、Cursor、VS Code 等 AI 客户端使用。

### 支持的 11 个数据源

| 数据源 | 领域 | 是否需要 API Key |
|--------|------|-----------------|
| OpenAlex | 综合（250M+ 论文） | 否 |
| arXiv | CS / 物理 / 数学预印本 | 否 |
| Semantic Scholar | 综合 + 引用图谱 | 否（有 key 速率更高）|
| PubMed | 生物医学 | 否（有 key 速率更高）|
| CrossRef | DOI 元数据 | 否 |
| Europe PMC | 生命科学 | 否 |
| bioRxiv | 生物学预印本 | 否 |
| DBLP | 计算机科学 | 否 |
| Papers with Code | ML + 代码 | 否 |
| **IEEE Xplore** | 工程 / 电子 / CS | **是（免费申请）** |
| **ACM Digital Library** | 计算机科学 | 否（元数据免费）|
| **SSRN** | 社会科学 / 经济 / 法律 | 否（有 key 更完整）|

---

## 2 设计思路

### 2.1 服务器不内置 LLM

MCP 服务器只做**纯数据操作**：搜索、去重、解析、同步、推送。所有推理（总结、对比、提炼）交由 AI 客户端完成，不额外调用 LLM API。

### 2.2 OA-First 全文获取

```
paper.pdf_url（元数据中已知）
  → CORE API（2 亿+ OA 论文，需 CORE_API_KEY）
    → Unpaywall（法律合规，仅需邮箱）
      → arXiv 直链（对 CS/物理论文最有效）
        → None → 调用方降级到摘要
```

### 2.3 三级去重策略

```
优先级 1：DOI（规范化小写）
优先级 2：arXiv ID
优先级 3：标题前 50 字符 + 年份哈希

重复项的元数据会【合并】到主记录，不简单丢弃。
```

### 2.4 评分公式

```
score = 0.40 × relevance       # 查询词命中率（标题 + 摘要）
      + 0.35 × recency         # exp(-age/10)，10 年论文 ≈ 0.37
      + 0.25 × citation_norm   # log1p(n) / log1p(max)
```

三个权重在 `search/engine.py` 的 `_score()` 函数中直接修改。

### 2.5 双向同步设计

每个文献管理工具均实现了 `sync_to_*`（推送）和 `pull_from_*`（拉取）两个方向，支持工具间互相迁移数据。

---

## 3 系统架构

```
AI 客户端（Claude · Cursor · VS Code · Gemini CLI …）
        ↓  MCP（stdio 或 HTTP/SSE）
┌────────────────────────────────────────────────────────────┐
│                    paper-distill-pro                       │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  search/   11 源并发 → 去重合并 → 评分排序               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌─────────────────┐  ┌──────────────────────────────┐     │
│  │  fulltext/      │  │  sync/（双向）                │     │
│  │  OA 4 级降级     │  │  Zotero ↔ Web API v3         │     │
│  │  PyMuPDF 解析    │  │  Mendeley ↔ OAuth 2.0        │     │
│  │  章节结构提取     │  │  Notion ↔ Database API       │     │
│  └─────────────────┘  └──────────────────────────────┘     │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  push/  digest → dispatcher → Slack/TG/Email/WeCom   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
         ↓ HTTP / REST
11 个学术数据源
```

---

## 4 目录结构

```
paper-distill-pro/
├── pyproject.toml                        # 打包；2 个 CLI 入口
├── .env.example                          # 全部环境变量模板
├── .gitignore
│
├── .github/workflows/
│   ├── ci.yml                            # lint + test + build
│   ├── daily-digest.yml                  # 每日 08:00 UTC 定时推送
│   └── publish.yml                       # release tag → PyPI
│
└── src/paper_distill_pro/
    ├── server.py                         # MCP 入口，注册 17 个 Tool
    ├── models.py                         # 全局 Pydantic 数据模型
    ├── config.py                         # 环境变量管理
    │
    ├── search/
    │   ├── engine.py                     # 并发引擎 + 评分
    │   ├── dedup.py                      # 三级去重 + 元数据合并
    │   └── sources/
    │       ├── __init__.py               # ALL_CONNECTORS 注册表（12 个）
    │       ├── base.py                   # 抽象基类 + HTTP + 重试
    │       ├── openalex.py               # 倒排索引摘要重建
    │       ├── arxiv.py                  # Atom XML 解析
    │       ├── semantic_scholar.py       # 含引用图 API
    │       ├── pubmed.py                 # E-utilities 两阶段
    │       ├── crossref.py
    │       ├── other.py                  # EuropePMC/bioRxiv/DBLP/PwC
    │       └── premium.py                # IEEE / ACM / SSRN
    │
    ├── fulltext/
    │   ├── fetcher.py                    # OA 链路 4 级降级
    │   └── parser.py                     # PyMuPDF + 章节正则 + QA 组装
    │
    ├── sync/
    │   ├── zotero.py                     # Zotero Web API v3（双向）
    │   ├── mendeley.py                   # Mendeley OAuth 2.0（双向）
    │   └── notion.py                     # Notion API 2022-06-28（双向）
    │
    └── push/
        ├── digest.py                     # 并发搜索，组装 Digest
        ├── dispatcher.py                 # 扇出到多渠道
        ├── scheduler.py                  # paper-distill-push CLI
        └── channels/
            ├── slack.py                  # Block Kit JSON
            ├── telegram.py               # HTML，自动分段
            ├── email.py                  # HTML 模板，aiosmtplib
            └── wecom.py                  # 企业微信 Markdown
```

---

## 5 核心模块详解

### 5.1 数据模型 `models.py`

```python
class Paper(BaseModel):
    title: str
    authors: list[Author]       # Author(name, affiliation, orcid)
    year: Optional[int]
    doi: Optional[str]
    arxiv_id: Optional[str]
    abstract: Optional[str]
    citation_count: int = 0
    source: str                 # 来自哪个 connector
    oa_url: Optional[str]       # 开放获取 URL
    pdf_url: Optional[str]      # 直接 PDF 链接
    score: float = 0.0          # 评分后填入
    # 各数据源专属 ID
    pubmed_id / ieee_id / acm_id / ssrn_id / mendeley_id / zotero_key

    @property
    def dedup_key(self) -> str:   # DOI > arXiv > 标题哈希
```

### 5.2 `search/` — 11 源并行搜索

#### 并发核心

```python
raw = await asyncio.gather(*tasks, return_exceptions=True)
# return_exceptions=True：单源失败不影响其他源
all_papers = [p for result in raw if not isinstance(result, Exception) for p in result]
papers = deduplicate(all_papers)
```

#### 三个新数据源要点

**IEEE Xplore**
- `IEEE_API_KEY` 未设置时静默跳过，不报错
- 支持 `access_type == "OPEN_ACCESS"` 填充 `oa_url`
- 免费申请：[developer.ieee.org](https://developer.ieee.org)

**ACM Digital Library**
- 无需 API Key，优先尝试 JSON 接口，失败降级正则提取 HTML
- 全文仍需机构订阅，元数据（DOI、标题、年份）免费

**SSRN**
- 有 `SSRN_API_KEY` 时用官方 API，无 Key 时抓取公开搜索页
- 以下载量（downloads）作为引用量代理指标

### 5.3 `fulltext/` — PDF 全文解析

章节识别正则（行首锚定，避免正文误匹配）：

```python
_SECTION_PATTERNS = [
    ("abstract",     r"^[\s\d\.]*Abstract\s*$"),
    ("methods",      r"^[\s\d\.]*Methods?\s*$|^[\s\d\.]*Materials?\s+and\s+Methods?\s*$"),
    ("conclusion",   r"^[\s\d\.]*Conclusions?\s*$"),
    # ... 其他章节
]
# re.IGNORECASE | re.MULTILINE | re.DOTALL
```

降级：无法识别章节 → 启发式分割（首段 = abstract）。

截断：超出 `max_tokens × 4` 字节时，按优先级（abstract → methods → conclusion → ...）保留重要章节。

### 5.4 `sync/` — 双向文献同步

#### Zotero
- 推送前拉取已有 DOI 集合，自动跳过重复
- Collection 不存在时自动创建
- 每批最多 50 条（API 限制）

#### Mendeley
- 支持 `client_credentials` grant（CI 场景，无用户交互）
- 支持 `Authorization Code` grant（完整读写权限）
- Token 自动缓存，快过期时刷新

#### Notion
- 双向同步：`sync_to_notion` 推送 / `pull_from_notion` 拉取
- 数据库属性字段需提前手动创建（字段名区分大小写）
- 推送前检查标题重复，跳过已存在项

### 5.5 `push/` — 定时推送子系统

**架构**：`scheduler.py` → `digest.py` → `dispatcher.py` → `channels/`

**推送渠道**：

| 渠道 | 格式 | 限制 | 配置 |
|------|------|------|------|
| Slack | Block Kit JSON | 无实际限制 | `SLACK_WEBHOOK_URL` |
| Telegram | HTML + 链接 | 4096 字符/条，自动分段 | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` |
| Email | 完整 HTML | 无限制 | `SMTP_*` × 5 |
| WeCom | Markdown | 4096 字符 | `WECOM_WEBHOOK_URL` |

---

## 6 MCP Server 工具清单

| 分类 | Tool | 主要参数 |
|------|------|----------|
| 搜索 | `search_papers` | query, sources[], since_year, min_citations |
| 搜索 | `batch_search` | queries[], max_results_per_query |
| 全文 | `fetch_fulltext` | title, doi, arxiv_id, sections[], max_tokens |
| 全文 | `compare_papers` | papers[], aspect |
| 全文 | `extract_contributions` | title, doi, arxiv_id |
| 引用 | `get_citation_tree` | paper_id, depth, max_per_level |
| 引用 | `trace_lineage` | paper_id, generations |
| 趋势 | `analyze_trend` | keyword, years |
| 趋势 | `compare_trends` | keywords[], years |
| 同步 | `sync_to_zotero` | papers[], collection |
| 同步 | `pull_from_zotero` | collection, limit |
| 同步 | `sync_to_mendeley` | papers[], folder |
| 同步 | `pull_from_mendeley` | folder, limit |
| 同步 | `sync_to_notion` | papers[], database_id |
| 同步 | `pull_from_notion` | database_id, limit |
| 推送 | `send_digest` | keywords[], channels[], since_days, title |

`sources` 可选值：`openalex` · `arxiv` · `semantic_scholar` · `pubmed` · `crossref` · `europe_pmc` · `biorxiv` · `dblp` · `papers_with_code` · `ieee` · `acm` · `ssrn`

`aspect` 可选值：`methodology` · `results` · `contribution` · `full`

`paper_id` 格式：`ARXIV:1706.03762` · `DOI:10.xxx/xxx` · S2 内部 ID

---

## 7 GitHub Actions 工作流

### 文件概览

| 文件 | 触发 | 内容 |
|------|------|------|
| `ci.yml` | push/PR | ruff lint → format check → pytest（3.11+3.12）→ build |
| `daily-digest.yml` | 每日 08:00 UTC + 手动 | 安装 → 读 Secrets → paper-distill-push → 写 Summary |
| `publish.yml` | GitHub Release | uv build → PyPI OIDC Trusted Publishing |

### `daily-digest.yml` 手动参数

在 **Actions → Daily Scholar Digest → Run workflow** 可覆盖：

| 参数 | 说明 |
|------|------|
| `keywords` | 覆盖 `PUSH_KEYWORDS` Secret |
| `channels` | 覆盖 `PUSH_CHANNELS` |
| `since_days` | 搜索窗口天数 |
| `max_papers` | 每关键词最多几篇 |
| `dry_run` | `true` = 构建不推送（调试）|

### 所需 GitHub Secrets

| Secret | 是否必填 |
|--------|---------|
| `PUSH_KEYWORDS` | 必填 |
| `PUSH_CHANNELS` | 必填（`slack,telegram` 等）|
| `SLACK_WEBHOOK_URL` | Slack 必填 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram 必填 |
| `SMTP_USERNAME/PASSWORD/FROM/TO` | Email 必填 |
| `WECOM_WEBHOOK_URL` | WeCom 必填 |
| `SEMANTIC_SCHOLAR_API_KEY` | 推荐 |
| `CORE_API_KEY` | 推荐（提升全文命中）|
| `IEEE_API_KEY` | 启用 IEEE 必填 |
| `ZOTERO_API_KEY` / `ZOTERO_USER_ID` | Zotero 同步必填 |
| `MENDELEY_CLIENT_ID` / `MENDELEY_CLIENT_SECRET` | Mendeley 同步必填 |
| `NOTION_TOKEN` / `NOTION_DATABASE_ID` | Notion 同步必填 |

---

## 8 安装与配置

```bash
# 方式 1：uvx（推荐，无需安装）
uvx paper-distill-pro

# 方式 2：pip
pip install paper-distill-pro

# 方式 3：源码（开发者）
git clone https://github.com/you/paper-distill-pro.git
cd paper-distill-pro
cp .env.example .env     # 填写配置
pip install -e ".[dev]"
pytest tests/ -v         # 40 个测试应全绿
```

### 最简 `.env` 配置

```bash
# 基础：free 数据源 + Slack 推送
PUSH_KEYWORDS=large language models,RAG
PUSH_CHANNELS=slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
UNPAYWALL_EMAIL=you@example.com

# 启用 IEEE
IEEE_API_KEY=your_ieee_key

# 提升全文命中
CORE_API_KEY=your_core_key

# Zotero
ZOTERO_API_KEY=xxx
ZOTERO_USER_ID=12345678   # 数字 ID，非用户名

# Mendeley
MENDELEY_CLIENT_ID=xxx
MENDELEY_CLIENT_SECRET=xxx

# Notion
NOTION_TOKEN=secret_xxx
NOTION_DATABASE_ID=xxx
```

---

## 9 接入 AI 客户端

### Claude Desktop

```json
{
  "mcpServers": {
    "paper-distill": {
      "command": "uvx",
      "args": ["paper-distill-pro"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "your_key",
        "IEEE_API_KEY": "your_key",
        "CORE_API_KEY": "your_key",
        "UNPAYWALL_EMAIL": "you@example.com",
        "ZOTERO_API_KEY": "your_key",
        "ZOTERO_USER_ID": "12345678",
        "NOTION_TOKEN": "secret_xxx",
        "NOTION_DATABASE_ID": "xxx"
      }
    }
  }
}
```

配置文件路径：
- macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows：`%APPDATA%\Claude\claude_desktop_config.json`

### Cursor

```json
{
  "mcpServers": {
    "paper-distill": {
      "command": "uvx",
      "args": ["paper-distill-pro"]
    }
  }
}
```

### VS Code

`.vscode/mcp.json`:
```json
{
  "servers": {
    "paper-distill": {
      "type": "stdio",
      "command": "uvx",
      "args": ["paper-distill-pro"]
    }
  }
}
```

### HTTP 模式（团队共享）

```bash
# 服务端
paper-distill-pro --transport http --port 8765

# 客户端
{ "type": "http", "url": "http://your-server:8765/sse" }
```

---

## 10 典型使用场景

### 场景 A：11 源综合调研 + 三库同步

```
"搜索近 2 年 mixture of experts，优先 IEEE 和 arXiv，引用量 > 20"
→ search_papers(query="mixture of experts", since_year=2023,
               sources=["ieee","arxiv","semantic_scholar"], min_citations=20)

"把这些论文同步到 Zotero MoE 2025 + Mendeley Research + Notion"
→ sync_to_zotero(papers=[...], collection="MoE 2025")
→ sync_to_mendeley(papers=[...], folder="Research")
→ sync_to_notion(papers=[...])
```

### 场景 B：三库互迁

```
# Zotero → Notion
papers = await pull_from_zotero(collection="RAG 2025")
await sync_to_notion(papers=papers)

# Notion → Mendeley
papers = await pull_from_notion()
await sync_to_mendeley(papers=papers, folder="Imported")
```

### 场景 C：引用脉络分析

```
"Transformer 论文有哪些最重要的后续工作？"
→ get_citation_tree(paper_id="ARXIV:1706.03762", depth=1)

"帮我往前追溯 2 代参考文献"
→ trace_lineage(paper_id="ARXIV:1706.03762", generations=2)
```

### 场景 D：研究热点对比

```
"比较 chain-of-thought、RAG、MoE 近 5 年增速"
→ compare_trends(keywords=["chain-of-thought","RAG","MoE"], years=5)
```

---

## 11 扩展开发指南

### 添加新数据源（3 步）

```python
# Step 1: 新建 sources/scopus.py
class ScopusConnector(BaseConnector):
    name = "scopus"
    async def search(self, query, max_results=20) -> list[Paper]:
        resp = await self._get(BASE, params={"query": query}, headers={"X-ELS-APIKey": ...})
        return [Paper(title=e["dc:title"], doi=e.get("prism:doi"), source=self.name)
                for e in resp.json().get("search-results", {}).get("entry", [])]

# Step 2: 在 sources/__init__.py 注册
ALL_CONNECTORS["scopus"] = ScopusConnector

# Step 3: 在 config.py 添加 key（如需）
elsevier_api_key: Optional[str] = None
```

### 添加新推送渠道（3 步）

```python
# Step 1: 新建 push/channels/discord.py
async def send_discord(digest: Digest) -> bool:
    payload = {"embeds": [{"title": digest.title, "description": ...}]}
    async with httpx.AsyncClient() as c:
        resp = await c.post(settings.discord_webhook_url, json=payload)
        return resp.status_code == 204

# Step 2: 在 dispatcher.py 注册
_CHANNEL_MAP["discord"] = send_discord

# Step 3: 在 config.py 添加
discord_webhook_url: Optional[str] = None
```

### 调整评分权重

```python
# search/engine.py → _score()
score = 0.40 * relevance + 0.35 * recency + 0.25 * citation_norm  # 默认
score = 0.30 * relevance + 0.10 * recency + 0.60 * citation_norm  # 偏重经典
score = 0.25 * relevance + 0.65 * recency + 0.10 * citation_norm  # 偏重最新
```

---

## 12 测试

```bash
pytest tests/ -v                           # 40 个离线单元测试
pytest tests/ -v -k "TestDeduplication"   # 只运行去重测试
pytest tests/ -v -k "Connector"           # 只运行 connector 注册测试
```

| 测试类 | 数量 | 覆盖内容 |
|--------|------|----------|
| `TestPaperModel` | 10 | dedup_key、short_ref、序列化、source IDs |
| `TestDeduplication` | 9 | DOI/arXiv 去重、元数据合并、Jaccard |
| `TestFulltextParser` | 8 | 章节识别、截断、降级、PyMuPDF 缺失 |
| `TestDigestModel` | 3 | total_papers、DigestConfig、SyncResult |
| `TestConfig` | 4 | 字符串解析 |
| `TestScoring` | 2 | 分数范围、时效性 |
| `TestConnectorRegistry` | 4 | 12 个注册、subset、未知忽略 |

---

## 13 常见问题

**Q：IEEE 没有结果？**
未设置 `IEEE_API_KEY` 时静默跳过。免费申请：[developer.ieee.org](https://developer.ieee.org)

**Q：Mendeley 403 错误？**
需完成 OAuth 流程。CI 环境使用 `client_credentials` grant（设置 client_id + client_secret 即可，无需用户交互）。

**Q：Notion 同步失败？**
① 数据库字段名必须与代码中的键名完全匹配；② Integration 需要被分享到目标数据库（Notion 数据库 → ... → Connections → 添加你的 Integration）。

**Q：全文获取返回"无全文"？**
配置 `CORE_API_KEY`（免费）可显著提升命中率。订阅制论文无开放版本时自动降级到摘要，不报错。

**Q：GitHub Actions 定时停了？**
60 天无 commit 会暂停。在 Actions 页面手动触发一次即可恢复。

**Q：如何调试 Tool 调用？**
```bash
LOG_LEVEL=DEBUG paper-distill-pro
# 或使用 MCP Inspector：
npx @modelcontextprotocol/inspector uvx paper-distill-pro
```

---

## 14 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| MCP 框架 | `mcp` Python SDK | 官方，stdio/HTTP 均支持 |
| HTTP | `httpx` + asyncio | 原生 async，连接池 |
| 重试 | `tenacity` | 指数退避，条件灵活 |
| 数据模型 | `pydantic v2` | 自动 JSON Schema |
| 配置 | `pydantic-settings` | 类型安全环境变量 |
| PDF | `PyMuPDF (fitz)` | 比 pdfminer 快 5-10× |
| OAuth | `authlib` | Mendeley OAuth 2.0 |
| 邮件 | `aiosmtplib` | 原生 async SMTP |
| 日志 | `rich` | 彩色日志，traceback 清晰 |
| 打包 | `hatchling` + `uv` | `uvx` 一键运行 |
| 测试 | `pytest` + `pytest-asyncio` | asyncio_mode=auto |

---

## 15 附录：快速参考

```bash
# CLI
paper-distill-pro                               # stdio 模式
paper-distill-pro --transport http --port 8765  # HTTP 模式
paper-distill-push                              # 手动推送一次
pytest tests/ -v                                # 40 个测试
npx @modelcontextprotocol/inspector uvx paper-distill-pro  # 调试 UI
```

```
# 数据源（sources 参数）
free:    openalex arxiv semantic_scholar pubmed crossref europe_pmc biorxiv dblp papers_with_code acm ssrn
key:     ieee (IEEE_API_KEY)

# paper_id 格式（get_citation_tree / trace_lineage）
ARXIV:1706.03762    DOI:10.1145/xxx    <S2内部40位ID>

# aspect 参数（compare_papers）
methodology  results  contribution  full

# Notion 数据库必需字段
Title(title)  Year(number)  Citations(number)  Authors(rich_text)
Venue(rich_text)  DOI(rich_text)  arXiv(rich_text)  URL(url)
Fields(multi_select)  Source(select)
```

---

*版本 0.1.0 · MIT License · [GitHub Actions 定时推送已配置]*
