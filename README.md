# paper-distill-pro

**基于 MCP 协议的学术论文智能检索与分析平台**

> **12 个学术数据库并行检索** · **PDF 全文解析与 LLM 增强** · **双向文献管理同步** · **多平台自动推送**

---

## 目录

1. [项目概述](#项目概述)
2. [核心功能](#核心功能)
3. [支持的数据源](#支持的数据源)
4. [系统架构](#系统架构)
5. [安装指南](#安装指南)
6. [配置说明](#配置说明)
7. [MCP 工具参考](#mcp-工具参考)
8. [使用示例](#使用示例)
9. [AI 客户端集成](#ai-客户端集成)
10. [GitHub Actions 自动化](#github-actions-自动化)
11. [开发指南](#开发指南)
12. [测试](#测试)
13. [常见问题](#常见问题)

---

## 项目概述

**paper-distill-pro** 是一个基于模型上下文协议（MCP）的学术论文处理服务器，为研究人员提供统一的文献检索、分析和管理接口。通过 Claude、Cursor、VS Code 等 AI 助手，您可以：

- 一键检索 12 个权威学术数据库
- 智能去重与相关性排序
- PDF 全文解析与深度分析
- 与主流文献管理工具双向同步
- 自动化研究摘要推送

### 核心特性

| 特性 | 说明 |
|------|------|
| **极速并行** | 同时查询 12 个数据库，几秒内获得全面结果 |
| **精准去重** | 三级去重策略，避免重复文献 |
| **智能排序** | 综合相关性、时效性和引用量的评分算法 |
| **双向同步** | 支持 Zotero、Mendeley、Notion、Obsidian 互操作 |
| **多端推送** | 自动摘要推送到 Slack、Telegram、邮箱等平台 |

---

## 核心功能

### 1. 多源学术检索

并行查询 **12 个权威学术数据库**：

| 数据库 | 领域覆盖 | 需要 API 密钥 |
|--------|----------|---------------|
| **OpenAlex** | 综合性（2.5 亿+ 论文） | 否 |
| **arXiv** | 计算机/物理/数学预印本 | 否 |
| **Semantic Scholar** | 综合性 + 引用图谱 | 否（有密钥速率更高） |
| **PubMed** | 生物医学 | 否（有密钥速率更高） |
| **CrossRef** | DOI 元数据 | 否 |
| **Europe PMC** | 生命科学 | 否 |
| **bioRxiv** | 生物学预印本 | 否 |
| **DBLP** | 计算机科学 | 否 |
| **Papers with Code** | 机器学习 + 代码实现 | 否 |
| **IEEE Xplore** | 工程/电子/计算机 | 是（免费申请） |
| **ACM Digital Library** | 计算机科学 | 否 |
| **SSRN** | 社会科学/经济/法律 | 否（有密钥更完整） |

### 2. 智能论文排序

采用加权评分算法：

```python
score = 0.40 × relevance       # 查询词匹配度（标题 + 摘要）
      + 0.35 × recency         # 时间衰减：exp(-age/10)
      + 0.25 × citation_norm   # 归一化引用量
```

**可定制权重**：在 `search/engine.py` 中调整权重系数。

### 3. 三级去重策略

```
优先级 1: DOI（规范化小写）
优先级 2: arXiv ID
优先级 3: 标题哈希（前 50 字符 + 年份）
```

**智能合并**：重复论文的元数据会合并到主记录，保留最完整的信息。

### 4. 全文处理能力

- **四级开放获取链**：元数据 → CORE API → Unpaywall → arXiv 直链
- **PDF 智能解析**：基于 PyMuPDF 的章节识别与提取
- **LLM 增强分析**：可选的子代理深度分析功能
- **章节感知提取**：自动识别摘要、引言、方法、结果、结论、参考文献

### 5. 文献管理集成

**双向同步**支持主流工具：

- **Zotero**：Web API v3，支持集合管理
- **Mendeley**：OAuth 2.0 认证，支持文件夹操作
- **Notion**：数据库 API，自定义字段映射
- **Obsidian**：本地库，Markdown 格式化

### 6. 自动化研究摘要

定时推送研究摘要：

- 多关键词监控
- 可配置时间窗口
- 自动排序过滤
- 多渠道分发（Slack、Telegram、邮件、飞书、企业微信）

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                  AI 客户端（Claude/Cursor/VSCode）              │
└─────────────────────────────┬───────────────────────────────────┘
                              │ MCP 协议（stdio/HTTP）
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   paper-distill-pro MCP 服务器                  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  搜索引擎（12 个数据源）                                    │ │
│  │  · 并发查询        · 智能去重                               │ │
│  │  · 相关性评分      · 引用排序                               │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────┐  ┌────────────────────────────────────┐ │
│  │  全文处理模块    │  │  同步模块                           │ │
│  │  · OA 链接获取   │  │  Zotero ↔ Mendeley ↔ Notion ↔      │ │
│  │  · PDF 解析      │  │  Obsidian（双向同步）               │ │
│  │  · LLM 子代理    │  │                                      │ │
│  └──────────────────┘  └────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  推送/摘要调度器                                           │ │
│  │  · 关键词监控      · 多渠道分发                            │ │
│  │  · GitHub Actions 集成                                    │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP/REST
                              ↓
                    ┌─────────────────────┐
                    │  学术 API 接口       │
                    │  （12 个数据源）     │
                    └─────────────────────┘
```

---

## 安装指南

### 快速安装（推荐）

```bash
# 使用 uvx（无需安装，直接运行）
uvx paper-distill-pro
```

### 标准安装

```bash
# 使用 pip
pip install paper-distill-pro

# 使用 uv（更快）
uv pip install --system paper-distill-pro
```

### 开发者安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/paper-distill-pro.git
cd paper-distill-pro

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件填写您的配置

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v
```

### 系统要求

- Python 3.11 或更高版本
- API 密钥为可选项（基础功能无需密钥）

---

## 配置说明

从提供的模板创建配置文件：

```bash
cp .env.example .env
```

### 最小化配置（仅使用免费数据源）

```bash
# 基础配置 + Slack 通知
PUSH_KEYWORDS=大语言模型,检索增强生成
PUSH_CHANNELS=slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
UNPAYWALL_EMAIL=your@email.com
```

### 完整配置示例

```bash
# ── 学术 API 密钥（可选但推荐）──
SEMANTIC_SCHOLAR_API_KEY=your_key_here
CORE_API_KEY=your_core_key          # 提升全文获取成功率
IEEE_API_KEY=your_ieee_key          # 从 developer.ieee.org 免费获取

# ── 文献管理工具 ──
# Zotero
ZOTERO_API_KEY=your_zotero_key
ZOTERO_USER_ID=12345678

# Mendeley
MENDELEY_CLIENT_ID=your_client_id
MENDELEY_CLIENT_SECRET=your_client_secret

# Notion
NOTION_TOKEN=secret_your_notion_token
NOTION_DATABASE_ID=your_database_id

# Obsidian（本地）
OBSIDIAN_VAULT_PATH=~/Documents/ObsidianVault

# ── 推送渠道 ──
PUSH_CHANNELS=slack,telegram,email
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com
SMTP_TO=recipient@email.com

# ── LLM 增强功能（可选）──
SUB_AGENT_API_KEY=your_anthropic_key
SUB_AGENT_MODEL=claude-3-5-sonnet-20241022

# ── 摘要设置 ──
PUSH_KEYWORDS=机器学习,深度学习,自然语言处理
PUSH_SINCE_DAYS=7
PUSH_MAX_PAPERS_PER_KEYWORD=5
PUSH_DIGEST_TITLE=每日研究摘要
```

---

## MCP 工具参考

### 搜索工具

#### `search_papers`

跨多个学术数据库搜索，支持高级过滤。

**参数**：

- `query`（字符串）：搜索查询
- `sources`（列表，可选）：指定搜索的数据库
- `since_year`（整数，可选）：筛选发表年份
- `min_citations`（整数，可选）：最小引用次数
- `max_results`（整数，可选）：最大结果数（默认 20）

**可用数据源**：`openalex`、`arxiv`、`semantic_scholar`、`pubmed`、`crossref`、`europe_pmc`、`biorxiv`、`dblp`、`papers_with_code`、`ieee`、`acm`、`ssrn`

#### `batch_search`

并行执行多个搜索查询。

**参数**：

- `queries`（字符串列表）：搜索查询列表
- `max_results_per_query`（整数，可选）：每个查询的结果数（默认 20）

### 全文工具

#### `fetch_fulltext`

检索和解析 PDF 全文，支持章节提取。

**参数**：

- `title`（字符串）：论文标题（用于识别）
- `doi`（字符串，可选）：DOI 标识符
- `arxiv_id`（字符串，可选）：arXiv ID
- `sections`（列表，可选）：要提取的章节
- `max_tokens`（整数，可选）：提取的 token 限制
- `use_llm`（布尔值，可选）：启用 LLM 增强

#### `compare_papers`

在特定方面比较多篇论文。

**参数**：

- `papers`（字典列表）：要比较的论文
- `aspect`（字符串）：比较重点（`methodology`、`results`、`contribution`、`full`）
- `use_llm`（布尔值，可选）：启用 LLM 分析

#### `extract_contributions`

提取论文的主要贡献。

**参数**：

- `title`（字符串）：论文标题
- `doi`（字符串，可选）：DOI
- `arxiv_id`（字符串，可选）：arXiv ID
- `use_llm`（布尔值，可选）：启用 LLM 分析

### 引用分析工具

#### `get_citation_tree`

构建展示关系的引用树。

**参数**：

- `paper_id`（字符串）：论文标识符（`ARXIV:id`、`DOI:doi` 或 S2 ID）
- `depth`（整数，可选）：树深度（默认 1）
- `max_per_level`（整数，可选）：每层最大论文数（默认 20）

#### `trace_lineage`

向前追溯研究谱系。

**参数**：

- `paper_id`（字符串）：论文标识符
- `generations`（整数，可选）：向前追溯的代数（默认 2）

### 趋势分析工具

#### `analyze_trend`

分析关键词的发表趋势。

**参数**：

- `keyword`（字符串）：搜索关键词
- `years`（整数，可选）：年数（默认 5）

#### `compare_trends`

比较多关键词的趋势。

**参数**：

- `keywords`（字符串列表）：要比较的关键词
- `years`（整数，可选）：分析时间跨度（默认 5）

### 同步工具

#### Zotero 同步

- `sync_to_zotero`：将论文推送到 Zotero 集合
- `pull_from_zotero`：从 Zotero 集合拉取论文

#### Mendeley 同步

- `sync_to_mendeley`：将论文推送到 Mendeley 文件夹
- `pull_from_mendeley`：从 Mendeley 文件夹拉取论文

#### Notion 同步

- `sync_to_notion`：将论文推送到 Notion 数据库
- `pull_from_notion`：从 Notion 数据库拉取论文

#### Obsidian 同步

- `sync_to_obsidian`：将论文推送到 Obsidian 库
- `pull_from_obsidian`：从 Obsidian 库拉取论文

### 推送工具

#### `send_digest`

生成并发送研究摘要到多个渠道。

**参数**：

- `keywords`（字符串列表）：搜索关键词
- `channels`（字符串列表）：目标渠道
- `since_days`（整数，可选）：回溯天数（默认 7）
- `title`（字符串，可选）：摘要标题

**可用渠道**：`slack`、`telegram`、`email`、`wecom`、`feishu`

---

## 使用示例

### 示例 1：多源文献综述

```python
# 跨 IEEE、arXiv 和 Semantic Scholar 搜索
papers = await search_papers(
    query="transformer architecture",
    sources=["ieee", "arxiv", "semantic_scholar"],
    since_year=2020,
    min_citations=50,
    max_results=30
)

# 同步到多个平台
await sync_to_zotero(papers, collection="Transformer 综述")
await sync_to_mendeley(papers, folder="ML 研究")
await sync_to_notion(papers)
```

### 示例 2：引用分析

```python
# 分析 "Attention Is All You Need" 的影响力
tree = await get_citation_tree(
    paper_id="ARXIV:1706.03762",
    depth=2,
    max_per_level=50
)

# 追溯研究谱系
lineage = await trace_lineage(
    paper_id="ARXIV:1706.03762",
    generations=3
)
```

### 示例 3：跨平台文献管理迁移

```python
# 从 Zotero 迁移到 Notion
zotero_papers = await pull_from_zotero(
    collection="深度学习",
    limit=100
)
await sync_to_notion(zotero_papers)

# 从 Mendeley 迁移到 Obsidian
mendeley_papers = await pull_from_mendeley(
    folder="研究",
    limit=200
)
await sync_to_obsidian(
    mendeley_papers,
    folder="文献综述",
    include_abstract=True
)
```

### 示例 4：研究趋势分析

```python
# 比较 AI 研究趋势
trends = await compare_trends(
    keywords=[
        "reinforcement learning",
        "transformers",
        "diffusion models"
    ],
    years=5
)

# 分析特定领域
report = await analyze_trend(
    keyword="graph neural networks",
    years=3
)
```

---

## AI 客户端集成

### Claude Desktop

添加到 `claude_desktop_config.json`：

**macOS**：`~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**：`%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "paper-distill": {
      "command": "uvx",
      "args": ["paper-distill-pro"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "your_key",
        "IEEE_API_KEY": "your_ieee_key",
        "CORE_API_KEY": "your_core_key",
        "UNPAYWALL_EMAIL": "your@email.com",
        "ZOTERO_API_KEY": "your_zotero_key",
        "ZOTERO_USER_ID": "12345678",
        "NOTION_TOKEN": "secret_your_token",
        "NOTION_DATABASE_ID": "your_database_id"
      }
    }
  }
}
```

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

创建 `.vscode/mcp.json`：

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

**服务器端**：

```bash
paper-distill-pro --transport http --port 8765
```

**客户端**：

```json
{
  "type": "http",
  "url": "http://your-server:8765/sse"
}
```

---

## GitHub Actions 自动化

### 自动化每日摘要

项目包含用于自动化研究摘要的 GitHub Actions 工作流：

**功能特点**：

- 定时运行（UTC 时间每天 08:00）
- 手动触发并支持参数覆盖
- 多渠道推送支持
- 试运行模式用于测试
- 自动故障日志记录

**必需的 GitHub Secrets**：

| Secret | 用途 |
|--------|------|
| `PUSH_KEYWORDS` | 摘要关键词 |
| `PUSH_CHANNELS` | 目标平台 |
| `SLACK_WEBHOOK_URL` | Slack 通知 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram 通知 |
| `SMTP_*` | 邮件通知 |
| `FEISHU_WEBHOOK_URL` | 飞书通知 |
| `WECOM_WEBHOOK_URL` | 企业微信通知 |
| `SEMANTIC_SCHOLAR_API_KEY` | 增强搜索 |
| `CORE_API_KEY` | 全文获取 |
| `IEEE_API_KEY` | IEEE 数据库 |

**手动触发参数**：

- `keywords`：覆盖默认关键词
- `channels`：覆盖目标渠道
- `since_days`：自定义时间窗口
- `max_papers`：每个关键词的结果数
- `dry_run`：测试模式（仅构建不发送）

---

## 开发指南

### 项目结构

```
paper-distill-pro/
├── src/paper_distill_pro/
│   ├── server.py              # MCP 服务器（17 个工具）
│   ├── models.py              # Pydantic 数据模型
│   ├── config.py              # 配置管理
│   ├── search/                # 多源搜索引擎
│   │   ├── engine.py          # 并发搜索与评分
│   │   ├── dedup.py           # 去重逻辑
│   │   └── sources/           # 12 个数据库连接器
│   ├── fulltext/              # PDF 处理
│   │   ├── fetcher.py         # OA 链接解析
│   │   ├── parser.py          # PDF 解析与提取
│   │   └── sub_agent.py       # LLM 增强
│   ├── sync/                  # 文献管理
│   │   ├── zotero.py          # Zotero Web API v3
│   │   ├── mendeley.py        # Mendeley OAuth 2.0
│   │   ├── notion.py          # Notion 数据库 API
│   │   └── obsidian.py        # 本地库同步
│   └── push/                  # 摘要自动化
│       ├── digest.py          # 摘要组装
│       ├── dispatcher.py       # 多渠道推送
│       ├── scheduler.py       # CLI 入口
│       └── channels/          # 推送渠道实现
├── tests/                     # 测试套件
├── .github/workflows/         # CI/CD 与自动化
├── pyproject.toml             # 包配置
└── .env.example               # 配置模板
```

### 添加新数据源

1. 在 `search/sources/` 中创建连接器：

```python
class YourConnector(BaseConnector):
    name = "your_source"

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        # 实现代码
        pass
```

2. 在 `search/sources/__init__.py` 中注册：

```python
ALL_CONNECTORS["your_source"] = YourConnector
```

3. 如需要，在 `config.py` 中添加配置

### 添加推送渠道

1. 在 `push/channels/` 中创建渠道：

```python
async def send_your_channel(digest: Digest) -> bool:
    # 实现代码
    pass
```

2. 在 `push/dispatcher.py` 中注册：

```python
_CHANNEL_MAP["your_channel"] = send_your_channel
```

3. 在 `config.py` 中添加配置

### 调整评分算法

在 `search/engine.py` 中修改权重：

```python
# 默认权重
score = 0.40 * relevance + 0.35 * recency + 0.25 * citation_norm

# 偏重经典文献
score = 0.30 * relevance + 0.10 * recency + 0.60 * citation_norm

# 偏重最新文献
score = 0.25 * relevance + 0.65 * recency + 0.10 * citation_norm
```

---

## 测试

### 运行测试

```bash
# 所有测试
pytest tests/ -v

# 特定测试类别
pytest tests/ -v -k "TestPaperModel"
pytest tests/ -v -k "TestDeduplication"
pytest tests/ -v -k "Connector"
```

### 测试覆盖

- **40+ 单元测试**覆盖核心功能
- **离线测试**（无需 API 调用）
- **测试类别**：
  - 论文模型验证
  - 去重逻辑
  - 全文解析
  - 连接器注册
  - 配置解析
  - 评分算法

---

## 常见问题

### Q：为什么没有 IEEE 的结果？

**A**：IEEE 需要 API 密钥。没有设置 `IEEE_API_KEY` 时，该数据源会被跳过。可从 [developer.ieee.org](https://developer.ieee.org) 免费申请密钥。

### Q：如何提高全文获取成功率？

**A**：配置 `CORE_API_KEY`（从 [core.ac.uk](https://core.ac.uk/services/api) 免费获取），这能显著提升开放获取 PDF 的发现率。

### Q：可以在没有任何 API 密钥的情况下使用吗？

**A**：可以！12 个数据源中有 9 个无需密钥即可使用：OpenAlex、arXiv、Semantic Scholar、PubMed、CrossRef、Europe PMC、bioRxiv、DBLP 和 Papers with Code。

### Q：如何调试 MCP 工具调用？

**A**：启用调试日志：

```bash
LOG_LEVEL=DEBUG paper-distill-pro
```

或使用 MCP Inspector 进行交互式调试：

```bash
npx @modelcontextprotocol/inspector uvx paper-distill-pro
```

### Q：我的 GitHub Actions 工作流为什么停止了？

**A**：GitHub 在 60 天不活动后会禁用定时工作流。从 Actions → Daily Scholar Digest → Run workflow 手动触发一次即可恢复。

### Q：如何在不同文献管理工具之间迁移？

**A**：使用双向同步工具：

```python
# Zotero → Notion
papers = await pull_from_zotero("我的集合")
await sync_to_notion(papers)

# Mendeley → Obsidian
papers = await pull_from_mendeley("研究")
await sync_to_obsidian(papers, folder="文献")
```

### Q：Mendeley 同步出现 403 错误？

**A**：需要完成 OAuth 流程。CI 环境使用 `client_credentials` 授权（设置 client_id + client_secret 即可，无需用户交互）。

### Q：Notion 同步失败？

**A**：
1. 数据库字段名必须与代码中的键名完全匹配
2. Integration 需要被分享到目标数据库（Notion 数据库 → ... → Connections → 添加你的 Integration）

### Q：全文获取返回"无全文"？

**A**：配置 `CORE_API_KEY`（免费）可显著提升命中率。订阅制论文无开放版本时会自动降级到摘要，不会报错。

---

## 技术栈

| 组件 | 技术选择 | 用途 |
|------|----------|------|
| MCP 框架 | `mcp` Python SDK | 模型上下文协议实现 |
| HTTP 客户端 | `httpx` + asyncio | 异步 HTTP 与连接池 |
| 数据模型 | `pydantic v2` | 类型安全数据验证 |
| 配置管理 | `pydantic-settings` | 环境变量管理 |
| PDF 处理 | `PyMuPDF (fitz)` | 快速 PDF 文本提取 |
| OAuth | `authlib` | Mendeley OAuth 2.0 流程 |
| 邮件 | `aiosmtplib` | 异步 SMTP 客户端 |
| 日志 | `rich` | 格式化控制台输出 |
| 打包 | `hatchling` + `uv` | 现代 Python 打包 |
| 测试 | `pytest` + `pytest-asyncio` | 异步测试支持 |

---

## 许可证

MIT License - 详见 LICENSE 文件。

---

## 版本

**当前版本**：1.0.0

**更新日志**：

- 初始发布，支持 12 个学术数据源
- 完整的 MCP 服务器实现，包含 17 个工具
- 4 个文献管理平台的双向同步
- 多渠道摘要自动化
- GitHub Actions 工作流集成

---

## 贡献

欢迎贡献！请随时提交 issue 或拉取请求。

**贡献领域**：

- 新增学术数据源
- 新的推送渠道集成
- 增强 PDF 解析算法
- 改进评分策略
- 文档改进

---

## 支持

如有问题、疑问或建议：

- 在 GitHub 上提交 issue
- 查看现有文档
- 使用调试日志查看 MCP 工具输出

---

