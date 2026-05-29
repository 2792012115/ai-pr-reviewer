# 🤖 AI PR Review 助手

> **AI 驱动的 GitHub Pull Request 智能代码评审工具**
>
> 输入 GitHub PR 链接 → 自动获取代码变更 → AI 深度分析 → 生成专业评审报告

[![Python Tests](https://github.com/2792012115/ai-pr-reviewer/actions/workflows/test.yml/badge.svg)](https://github.com/2792012115/ai-pr-reviewer/actions/workflows/test.yml)

---

## 📋 项目简介

**AI PR Review 助手** 是一个基于大语言模型的代码评审工具，旨在帮助开发者提升 Pull Request 的 Review 效率与质量。

### 核心功能

| 功能 | 描述 |
|------|------|
| 🔍 **PR 变更总结** | 自动提取 PR 元信息，生成一句话摘要 + 详细变更分析 |
| ⚠️ **风险代码识别** | 识别安全漏洞、逻辑错误、性能问题，按严重程度分级 |
| 💡 **Review 建议生成** | 针对每个问题给出具体的修改建议和代码示例 |
| � **关注领域筛选** | 支持按安全/性能/逻辑/规范/可维护性聚焦评审 |
| 📤 **PR Comment 自动发布** | 评审完成一键发布到 GitHub PR 评论区 |
| 📊 **评审历史追踪** | 本地记录每次评审，支持趋势分析 |
| 🎯 **整体风险评估** | 0-10 分量化风险，可视化风险条展示 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (HTML/CSS/JS)               │
│                   用户输入 PR URL → 展示评审报告           │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP REST API
┌─────────────────────────▼───────────────────────────────┐
│                   FastAPI Backend (Python)               │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ GitHub Client │  │ AI Reviewer  │  │Report Generator│  │
│  │              │  │              │  │               │  │
│  │ · PR 数据获取 │  │ · 逐文件评审  │  │ · Markdown    │  │
│  │ · Diff 解析  │  │ · 聚合总结   │  │ · HTML 报告   │  │
│  │ · URL 解析   │  │ · 多模型支持  │  │ · JSON API    │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘  │
│         │                 │                              │
└─────────┼─────────────────┼──────────────────────────────┘
          │                 │
┌─────────▼─────┐  ┌────────▼──────────┐
│  GitHub API   │  │  OpenAI / LLM API │
│  (REST v3)    │  │  (GPT-4o 等)      │
└───────────────┘  └───────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- **Python** >= 3.11
- **GitHub Token**（[创建地址](https://github.com/settings/tokens)）
- **OpenAI API Key**（[获取地址](https://platform.openai.com/api-keys)）

### 安装与启动

```bash
# 1. 克隆仓库
git clone <your-repo-url>
cd ai-pr-reviewer

# 2. 创建虚拟环境
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. 安装依赖
pip install -r backend/requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 GITHUB_TOKEN 和 OPENAI_API_KEY

# 5. 启动服务
python run.py
```

打开浏览器访问 **http://localhost:8000**，输入 GitHub PR 链接即可开始评审。

---

## 📖 使用指南

### 1. 输入 PR 链接
在页面输入框中粘贴 GitHub PR URL，格式：
```
https://github.com/{owner}/{repo}/pull/{number}
```

### 2. 等待 AI 分析
系统会自动：
- 获取 PR 元信息和代码 diff
- 逐文件发送给 AI 模型分析
- 聚合生成整体评估报告

### 3. 查看评审报告
报告包含：
- **PR 摘要**：一句话总结 + 详细描述 + 关键变更
- **整体评估**：风险评分（0-10）+ 风险条 + 全局建议
- **文件详情**：每个文件的评审结果，问题按严重程度分级展示

### API 直接调用

```bash
curl -X POST http://localhost:8000/api/review \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

---

## 🧠 设计思路

### 模型选择

| 考量维度 | 选择 | 理由 |
|---------|------|------|
| **默认模型** | GPT-4o | 代码理解能力强、响应速度快、性价比高 |
| **备选方案** | Claude 3.5 Sonnet | 长上下文处理能力突出，适合大型 PR |
| **本地模型** | DeepSeek-Coder-V2 | 数据不出境，适合企业内部部署 |

通过 `OPENAI_MODEL` 和 `OPENAI_BASE_URL` 环境变量可灵活切换任何兼容 OpenAI API 的模型。

### 上下文获取方式

当前实现使用 **PR Diff（Unified Diff Patch）** 作为主要上下文：
- **优点**：数据量小、传输快、聚焦变更部分
- **局限**：缺少未修改代码的上下文

未来可通过 GitHub Contents API 获取完整文件内容作为补充上下文，提升分析准确度。

### 误报与漏报控制

- **低温度参数**（temperature=0.3）：确保评审结果稳定可复现
- **结构化输出**：通过 JSON Schema 约束 LLM 输出格式
- **风险分级**：critical/high/medium/low/info 五级，便于人工复核优先级
- **鼓励精确**：Prompt 中明确要求"只报告真实存在的问题"

---

## 🔮 未来扩展方向

- [ ] **Webhook 集成**：监听 GitHub PR 事件，自动触发评审
- [ ] **PR Comment 自动发布**：将评审结果作为 PR Comment 发布
- [ ] **自定义规则引擎**：支持团队编码规范（ESLint/PSR 等规则映射）
- [ ] **历史趋势分析**：追踪仓库代码质量变化趋势
- [ ] **多仓库支持**：GitLab / Gitee / Bitbucket 适配
- [ ] **增量评审**：仅分析 force-push 后的增量变更
- [ ] **评审记录存储**：持久化评审历史，支持对比和回溯
- [ ] **团队协作**：多人评审分配、评论讨论、问题跟踪

---

## 📁 项目结构

```
ai-pr-reviewer/
├── backend/
│   ├── main.py              # FastAPI 应用入口 + API 路由
│   ├── config.py            # 全局配置（环境变量）
│   ├── models.py            # 数据模型定义
│   ├── github_client.py     # GitHub REST API 客户端
│   ├── ai_reviewer.py       # AI 评审引擎（核心）
│   └── report_generator.py  # 报告生成器（Markdown/HTML）
├── frontend/
│   └── index.html           # Web 前端（单页应用）
├── tests/
│   └── test_all.py          # 单元测试 + 集成测试
├── run.py                   # 启动脚本
├── .env.example             # 环境变量模板
├── .gitignore
└── README.md
```

---

## 🧪 运行测试

```bash
cd ai-pr-reviewer
pytest tests/ -v
```

---

## 📄 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| Web 框架 | FastAPI | 0.115+ |
| 前端 | Vanilla HTML/CSS/JS | - |
| AI 引擎 | OpenAI Python SDK | 1.58+ |
| HTTP 客户端 | httpx | 0.28+ |
| 数据模型 | Pydantic | 2.10+ |
| 测试 | pytest | 8.3+ |

---

## 🎥 Demo 演示视频

👉 [B站观看完整演示](https://www.bilibili.com/video/BV1ADV86ZEnP/)

---

## ⚖️ 开源协议

MIT License

---

## 👥 贡献者

- 开发者：[Your Name]
- 项目来源：XEngineer 新工科计划 · 第二批议题 · 题目三

---

> Built with ❤️ for XEngineer 2026
