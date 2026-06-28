# CLAUDE.md — Paraguay Macro Research Briefing Tool

## 触发词

当用户说以下任意关键词时，立即执行下方的完整流程：
- "调研" / "开始调研" / "生成简报" / "更新简报"
- "巴拉圭调研" / "搜集巴拉圭资讯" / "生成巴拉圭报告"

---

## Step 0: 确认参数（逐一询问，不要跳过）

开始前必须分别询问用户：

**1. 时间跨度**（默认 `1w`）
> 请确认本次简报更新的时间范围：`1w` 最近一周 · `2w` 最近两周 · `1m` 最近1个月 · 或输入自定义起止日期如 `6月22日 — 6月28日`

**2. CPI 数据文件**
> 是否有最新的 CPI Excel 文件需要更新？如有请提供文件路径（如 `AE_IPC-26.6.xlsx`），无则回复"没有"。

**3. RIN 数据文件**
> 是否有最新的 RIN（外汇储备）Excel 文件需要更新？如有请提供文件路径，无则回复"没有"。

---

## Step 1: 读取模板并执行搜索

读取 `research_template.json` 获取六大方向的搜索查询，使用 **WebSearch 工具**（不是 DDG）搜索。每个 Section 的多个查询并行执行。

搜索时注意：
- 将查询中的月份年份替换为用户选择的实际时间范围
- 优先使用 `.gov.py` 和政府来源的 URL
- 结果严格限制在巴拉圭政府、权威媒体和国际权威来源内
- 排除 Wikipedia、Britannica、旅游指南等非新闻页面
- 24 个权威域名见 `config.py` 中的 `ALLOWED_NEWS_DOMAINS`

---

## Step 2: 编译英文简报

搜索结果整理为 `briefing_en.json`，结构遵循 `research_template.json`：

```json
{
  "topic": "Paraguay Briefing",
  "time_span": "June 22 – June 28, 2026",
  "sections": [
    {
      "title": "I. Macroeconomic Developments",
      "tier": 1,
      "events": [
        {
          "title": "事件标题（末尾标注日期 YYYY-MM-DD）",
          "date": "YYYY-MM-DD",
          "source_url": "https://...",
          "source_name": "来源名称",
          "summary": "50-200字英文摘要，包含关键数据和影响",
          "image_url": null,
          "is_gov_source": true/false,
          "is_authoritative": true/false
        }
      ]
    }
  ]
}
```

**内容要求**：
- 每个 Section 3-5 条事件，优先巴拉圭本地来源
- Section 5 和 6 每个事件必须包含 `client_tag` 字段
- Section 7 和 8 为 tier 2，无 events，仅有 `impact_analysis`
- Section 7/8 的分析必须引用前 6 章的具体事件和数据
- 使用 emoji 标记风险等级（🔴高 🟡中 🟢机会）

---

## Step 3: 翻译中文版

调用 Deepseek API（`web_app.py` 中的 `translate_briefing()`）将英文版翻译为中文，保存为 `briefing.json`。

API key: `sk-6b4cfee3b0e44befa030851e9e5173fb`

---

## Step 4: 获取文章图片

运行 `web_app.py` 中的 `fetch_og_image()` 为每个事件获取 OG 封面图，填充 `image_url` 字段。

---

## Step 5: 更新汇率

确保 `dashboard.html` 中 `MACRO_FX.monthly` 最后一个值和日期与 BCP 最新数据一致。BCP 来源：`https://www.bcp.gov.py/webapps/web/cotizacion/monedas`

---

## Step 6: 提交并展示

```bash
cd /Users/chenyuan/paraguay_research
git add index.html dashboard.html briefing.json briefing_en.json templates/
git commit -m "Update briefing to <time_span>"
git push origin main
```

向用户展示：
1. 各 Section 事件数统计
2. 时间跨度确认
3. 中英文版文件确认
4. GitHub Pages 链接：https://joanne-ya-chen.github.io/paraguay-research-dashboard/

---

## 展示方式

- **本地**：`python3 web_app.py --port 9000` → http://127.0.0.1:9000
- **分享**：https://joanne-ya-chen.github.io/paraguay-research-dashboard/

## 权威来源（24个）

政府：bcp.gov.py · hacienda.gov.py · mre.gov.py · mic.gov.py · presidencia.gov.py · senado.gov.py · diputados.gov.py · mtess.gov.py · mopc.gov.py · conatel.gov.py · ip.gov.py

媒体：abc.com.py · ultimahora.com · lanacion.com.py · 5dias.com.py · paraguay.com · elnacional.com.py · hoy.com.py · economia.com.py · diarioparaguayo.com · mobiletime.la · dplnews.com

国际：reuters.com · bloomberg.com · elpais.com · infobae.com · dialogochino.net · bbc.com
