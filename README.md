# 酸性 CO₂ 电还原文献实时推送

这个项目每小时检索一次 OpenAlex，并将新出现的酸性 CO₂ 电还原相关论文推送到 Telegram。它不是只靠一个宽泛关键词：候选文献必须同时满足 **CO₂ + 电化学还原/电解 + 酸性或质子传导环境**，再用 DOI/OpenAlex ID 去重。

默认覆盖的表达包括：

- acidic media、acid electrolyte、low pH、hydronium、proton-rich
- proton exchange membrane、cation exchange membrane、solid polymer electrolyte、Nafion
- CO2RR、CO₂ electroreduction、CO₂ electrolysis

## 文件结构

```text
.
├── literature_bot.py
├── requirements.txt
├── state/seen.json
├── tests/test_literature_bot.py
├── AGENTS.md
├── CODEX_PROMPT.md
└── .github/workflows/literature-alert.yml
```

## 1. 创建 OpenAlex API key

在 OpenAlex 注册免费账户并复制 API key。免费 key 的每日额度足够本项目每小时运行。

## 2. 创建 Telegram Bot

1. 在 Telegram 搜索 `@BotFather`，执行 `/newbot`，获得 bot token。
2. 打开新 bot，给它发送 `/start`。
3. 在浏览器打开下面地址，把 `<TOKEN>` 换成 bot token：

```text
https://api.telegram.org/bot<TOKEN>/getUpdates
```

4. 在返回 JSON 中找到 `message.chat.id`，这就是 `TELEGRAM_CHAT_ID`。

## 3. 放到 GitHub

新建一个 GitHub repository，把本项目全部文件上传到默认分支。

进入：

```text
Repository → Settings → Secrets and variables → Actions → New repository secret
```

添加三个 secrets：

| Secret | 内容 |
|---|---|
| `OPENALEX_API_KEY` | OpenAlex API key |
| `TELEGRAM_BOT_TOKEN` | BotFather 给出的 token |
| `TELEGRAM_CHAT_ID` | `getUpdates` 返回的 chat id |

## 4. 首次测试

进入 GitHub 的 **Actions** 页面，选择 **Acidic CO2 literature alerts**，点击 **Run workflow**。

首次运行会：

- 检索最近 14 天；
- 最多推送最新 8 篇；
- 把当前已检索文献写入 `state/seen.json`；
- 此后只推送新文献。

工作流默认在每小时第 17 分钟运行。GitHub Actions 的定时任务不是硬实时，偶尔可能延迟几分钟。

## 5. 本地测试

```bash
python -m pip install -r requirements-dev.txt
export OPENALEX_API_KEY="你的 key"
python literature_bot.py --dry-run
python -m pytest -q
python -m ruff check .
```

Windows PowerShell：

```powershell
$env:OPENALEX_API_KEY="你的 key"
python literature_bot.py --dry-run
```

`--dry-run` 只打印结果，不发送 Telegram，也不更改去重状态。

## 调整推送范围

在 `literature_bot.py` 中修改：

- `SEARCH_QUERIES`：OpenAlex 初筛查询；
- `ACID_TERMS`：酸性相关表达；
- `ELECTROREDUCTION_TERMS`：CO₂RR 表达。

在 workflow 中可修改：

```yaml
LOOKBACK_DAYS: "14"
FIRST_RUN_SEND_LIMIT: "8"
MAX_ALERTS_PER_RUN: "20"
```

建议不要只添加 `MEA` 或 `zero-gap` 作为酸性判据，因为很多 AEM/碱性电解槽也使用这些结构。

## 交给 Codex

将 GitHub repository 连接到 Codex，然后把 `CODEX_PROMPT.md` 的内容粘贴给 Codex。`AGENTS.md` 已写明科学筛选边界、测试要求和安全规则。

## 常见问题

**没有任何推送**：先手动运行 workflow，查看 Actions 日志；确认 bot 已收到过你的 `/start`。

**推送太少**：扩展 `ACID_TERMS`，但仍需保留“CO₂ + 电还原 + 酸性环境”三项同时满足。

**推送太多无关论文**：不要直接删除本地 relevance filter；优先收紧 `ACID_TERMS` 或搜索式。

**state push 失败**：确认 workflow 的 `permissions: contents: write` 存在，并检查 repository 是否限制 GitHub Actions 写入。
