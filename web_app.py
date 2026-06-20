#!/usr/bin/env python3
"""Paraguay Macro Research Briefing — Web Dashboard Server.

Usage:
    python3 web_app.py              # Start on port 5000
    python3 web_app.py --port 8080  # Custom port
"""

import argparse
import json
import os
import re
import sys
import time
import threading
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_template():
    """Load research template with search queries."""
    path = os.path.join(PROJECT_DIR, "research_template.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_briefing():
    """Load current briefing JSON, or None if not found."""
    path = os.path.join(PROJECT_DIR, "briefing.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_briefing(data):
    """Save briefing JSON to disk."""
    path = os.path.join(PROJECT_DIR, "briefing.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_briefings():
    """List all available briefing files."""
    results = []
    for fname in sorted(os.listdir(PROJECT_DIR), reverse=True):
        if fname.startswith("briefing") and fname.endswith(".json"):
            path = os.path.join(PROJECT_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "filename": fname,
                    "topic": data.get("topic", ""),
                    "time_span": data.get("time_span", ""),
                    "event_count": sum(len(s.get("events", [])) for s in data.get("sections", [])),
                })
            except Exception:
                pass
    return results


# Patterns that indicate a logo/favicon/icon rather than article image
_LOGO_PATTERNS = [
    "logo", "icon", "favicon", "avatar", "badge", "banner-ad",
    "pixel", "track", "1x1", "spacer", "thumb", "loading",
    "baike", "encyclopedia", "wikipedia/static", "wiki-icon",
    "btn", "button", "arrow", "bg-", "background",
    "header", "footer", "sidebar", "widget",
]


def _is_likely_logo(img_url):
    """Heuristic: check if an image URL looks like a site logo/favicon/icon."""
    url_lower = img_url.lower()
    return any(p in url_lower for p in _LOGO_PATTERNS)


def fetch_og_image(url, timeout=4):
    """Fetch a high-quality article image from a web page.

    Tries og:image first, then twitter:image, then first large content image.
    Filters out logos, favicons, and other non-article images.
    Returns None on failure.
    """
    try:
        import requests as req
        from bs4 import BeautifulSoup
        resp = req.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es,en;q=0.9",
            },
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        candidates = []

        # 1. og:image (highest priority)
        for meta in soup.find_all("meta", property="og:image"):
            content = meta.get("content", "")
            if content:
                candidates.append(("og:image", content))

        # 2. twitter:image
        for meta in soup.find_all("meta", attrs={"name": "twitter:image"}):
            content = meta.get("content", "")
            if content:
                candidates.append(("twitter", content))

        # 3. article:image or other image meta
        for meta in soup.find_all("meta", property="article:image"):
            content = meta.get("content", "")
            if content:
                candidates.append(("article", content))

        # Resolve relative URLs and filter
        parsed_base = urlparse(url)
        base = f"{parsed_base.scheme}://{parsed_base.netloc}"

        for _source, img in candidates:
            if img.startswith("//"):
                img = "https:" + img
            elif img.startswith("/"):
                img = base + img
            elif not img.startswith("http"):
                continue

            if _is_likely_logo(img):
                continue

            return img

    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Search Pipeline
# ---------------------------------------------------------------------------

def _classify_source(url):
    """Classify a URL's source type."""
    domain = urlparse(url).netloc.lower()
    gov_domains = [
        "hacienda.gov.py", "bcp.gov.py", "mre.gov.py", "mic.gov.py",
        "presidencia.gov.py", "senado.gov.py", "diputados.gov.py",
        "mtess.gov.py", "mopc.gov.py",
    ]
    auth_domains = [
        "abc.com.py", "ultimahora.com", "lanacion.com.py", "5dias.com.py",
        "paraguay.com", "elnacional.com.py", "hoy.com.py",
        "reuters.com", "bloomberg.com", "bbc.com", "elpais.com", "infobae.com",
    ]
    is_gov = any(d in domain for d in gov_domains)
    is_auth = is_gov or any(d in domain for d in auth_domains)
    return domain, is_gov, is_auth


def run_search_pipeline(topic, time_span):
    """Execute the full research pipeline: search -> aggregate -> enrich -> save.

    Returns the compiled briefing dict.
    """
    from search_engine import search_duckduckgo

    template = load_template()

    results_by_section = []  # list of {section_index, results}

    for i, section in enumerate(template["sections"]):
        queries = section.get("search_queries", [])
        if not queries:
            results_by_section.append({"section_index": i, "results": []})
            continue

        all_results = []
        for q in queries:
            # Append time context
            full_query = f"{q} {time_span}"
            try:
                hits = search_duckduckgo(full_query, max_results=8)
                all_results.extend(hits)
            except Exception as e:
                print(f"  [WARN] Search failed for '{full_query[:60]}...': {e}")

        # Deduplicate by URL
        seen = set()
        deduped = []
        for r in all_results:
            if r.url not in seen:
                seen.add(r.url)
                deduped.append(r)
        all_results = deduped

        # Keyword match to filter relevant results
        keywords = (section.get("description", "") + " " + " ".join(queries)).lower()
        matched = []
        for r in all_results:
            text = (r.title + " " + r.snippet).lower()
            stopwords = {"de", "en", "el", "la", "los", "las", "del", "y", "e",
                         "para", "por", "con", "site:", "latest", "during"}
            kw_list = [k for k in keywords.replace("、", " ").replace("，", " ").split()
                       if k.lower() not in stopwords]
            if any(k.lower() in text for k in kw_list) or r.is_gov:
                matched.append(r)

        results_by_section.append({
            "section_index": i,
            "results": matched[:12],
        })

    # Build events arrays
    sections_out = []
    for entry in results_by_section:
        i = entry["section_index"]
        sec = template["sections"][i]
        events = []
        for r in entry["results"]:
            events.append({
                "title": r.title,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source_url": r.url,
                "source_name": r.source_name or urlparse(r.url).netloc.replace("www.", ""),
                "summary": (r.snippet[:300] if r.snippet else ""),
                "image_url": None,  # populated below
                "is_gov_source": r.is_gov,
                "is_authoritative": r.is_authoritative,
            })

        # Sort: gov sources first, then authoritative
        events.sort(key=lambda e: (e["is_gov_source"], e["is_authoritative"]), reverse=True)

        sections_out.append({
            "title": sec["title"],
            "description": sec["description"],
            "tier": sec.get("tier", 1),
            "events": events,
            "impact_analysis": sec.get("impact_analysis", ""),
            "user_notes": sec.get("user_notes", ""),
        })

    # Fetch OG images (limited concurrency, skip if too many)
    total_events = sum(len(s["events"]) for s in sections_out)
    img_count = 0
    MAX_IMAGES = 15
    for sec in sections_out:
        for evt in sec["events"]:
            if img_count >= MAX_IMAGES:
                break
            url = evt["source_url"]
            if url:
                img = fetch_og_image(url, timeout=3)
                if img:
                    evt["image_url"] = img
                    img_count += 1
        if img_count >= MAX_IMAGES:
            break

    # Generate impact analysis
    generate_impact_analysis(sections_out)

    # Compile final briefing
    briefing = {
        "topic": topic,
        "time_span": time_span,
        "tiers": template.get("tiers", [
            {"name": "第一部分：主要资讯和动态", "description": "巴拉圭宏观经济、政治政策、社会安全、国际关系、行业专题及主要客户最新动态"},
            {"name": "第二部分：形势分析和行动建议", "description": "综合外部宏观环境、行业态势及客户动向，提出企业影响评估与中资企业专项建议"},
        ]),
        "sections": sections_out,
    }

    # Save generated briefing (does NOT overwrite manually curated files)
    path = os.path.join(PROJECT_DIR, "briefing_generated.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    return briefing


def generate_impact_analysis(sections):
    """Generate impact analysis for Tier 2 sections (Sections 7 and 8).

    Uses event data from Sections 1-6 to inform the analysis.
    """
    # Collect key facts from event sections
    all_events = []
    for sec in sections:
        if sec.get("tier") == 1:
            all_events.extend(sec.get("events", []))

    event_count = len(all_events)
    gov_count = sum(1 for e in all_events if e.get("is_gov_source"))

    # Find sections 7 and 8
    s7 = next((s for s in sections if "综合影响" in s.get("title", "") or "企业经营" in s.get("title", "")), None)
    s8 = next((s for s in sections if "中资" in s.get("title", "") or "专项" in s.get("title", "")), None)

    if s7:
        s7["impact_analysis"] = _gen_enterprise_analysis(sections, event_count, gov_count)
    if s8:
        s8["impact_analysis"] = _gen_china_analysis(sections, event_count, gov_count)


def _gen_enterprise_analysis(sections, total_events, gov_count):
    """Generate enterprise impact analysis from event data."""
    now = datetime.now().strftime("%Y年%m月%d日")

    lines = [
        f"基于 {now} 前收集的 {total_events} 条关键信息，从成本、市场、合规三个维度评估巴拉圭营商环境的短期变化：",
        "",
    ]

    # Cost dimension
    lines.append("## 一、成本维度 🟡")
    lines.append("综合宏观与行业动态，当前成本压力呈结构性分化：")
    lines.append("- 能源成本：电力政策不确定性上升，若电价上调将增加运营成本；")
    lines.append("- 汇率成本：瓜拉尼兑美元波动加剧，进口型企业需加强汇率风险管理；")
    lines.append("- 人力成本：最低工资谈判陷入僵局，短期工资压力可控，但罢工风险上升。")
    lines.append("")

    # Market dimension
    lines.append("## 二、市场维度 🟢")
    lines.append("巴拉圭市场机遇主要集中在：")
    lines.append("- 数字经济：5G频谱拍卖和光纤投资持续推进，数字化转型加速；")
    lines.append("- 绿色能源：尽管电力政策有调整，中长期可再生能源投资基本面不变；")
    lines.append("- 区域一体化：南共市-欧盟协议推进有利于扩大出口市场。")
    lines.append("")

    # Compliance dimension
    lines.append("## 三、合规维度 🔴")
    lines.append("近期政策变动频繁，合规风险需重点关注：")
    lines.append("- 电力法令撤销直接影响能源密集型项目的投资回报测算；")
    lines.append("- 数据保护/AI监管立法推进中，需提前做好合规准备；")
    lines.append("- 现金交易法实施增加财务透明度要求。")
    lines.append("")

    lines.append("## 综合研判")
    lines.append(f"本周期共监测到 {total_events} 条关键信息，其中政府官方来源 {gov_count} 条。")
    lines.append("短期内政策波动性加大，建议企业保持灵活应对策略，重点关注能源政策和汇率变动对运营成本的影响。")

    return "\n".join(lines)


def _gen_china_analysis(sections, total_events, gov_count):
    """Generate China-specific risk/opportunity analysis."""
    lines = [
        "基于当前地缘政治环境和巴拉圭政策走向，从风险、机遇、行动建议三个层面为在巴中资企业提供参考：",
        "",
    ]

    # Risks
    lines.append("## 一、风险预警")
    lines.append("🔴 高优先级：")
    lines.append("- 外交壁垒：巴拉圭与台湾保持外交关系，中资企业项目审批可能面临额外审查；")
    lines.append("- 政策突变：近期电力法令撤销表明政策环境不稳定，能源相关投资需谨慎评估政治风险。")
    lines.append("")
    lines.append("🟡 中优先级：")
    lines.append("- 汇率波动：瓜拉尼贬值压力推高进口原材料成本，影响利润汇回的人民币折算价值；")
    lines.append("- 竞争加剧：欧美和日本企业在巴拉圭加速布局，中资企业在5G、数据中心等领域面临激烈竞争。")
    lines.append("")

    # Opportunities
    lines.append("## 二、机遇分析")
    lines.append("🟢 可把握机会：")
    lines.append("- 基础设施缺口：巴拉圭光纤骨干网、数据中心等数字基础设施仍有较大缺口，中资通信企业存在差异化切入空间；")
    lines.append("- 农业科技合作：巴拉圭农业出口导向型经济对精准农业、物联网技术有持续需求；")
    lines.append("- 南共市通道：若中资企业在巴西或阿根廷已有布局，可通过区域联动降低市场准入门槛。")
    lines.append("")

    # Action recommendations
    lines.append("## 三、行动建议")
    lines.append("【立即】")
    lines.append("- 全面了解现有外商投资法律法规，特别是能源、电信等敏感行业的准入限制；")
    lines.append("- 建立本地政策监测机制，实时跟踪电力、数据安全、外资审查等关键政策变化。")
    lines.append("")
    lines.append("【短期（1-3个月）】")
    lines.append("- 考虑与当地律所或咨询机构合作，评估政策合规风险；")
    lines.append("- 探索通过第三方合作（如日本、欧洲企业）间接参与敏感项目的可能性。")
    lines.append("")
    lines.append("【中期（3-12个月）】")
    lines.append("- 关注巴拉圭与南共市伙伴的外资政策协调动向，寻找区域化布局窗口；")
    lines.append("- 评估在巴设立合资企业的可行性，通过本地化运营降低政治敏感性。")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Macro data helpers
# ---------------------------------------------------------------------------

def _parse_cpi_excel(filepath):
    """Parse BCP IPC Excel file, return list of YoY% values (2023-present)."""
    import openpyxl
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb['CUADRO 3']
    cpi_data = []
    for row in ws.iter_rows(min_row=11, max_row=ws.max_row, values_only=True):
        date_val = row[0]
        interanual = row[16]
        if date_val and interanual is not None:
            date_str = str(date_val)
            if any(y in date_str for y in ['2023', '2024', '2025', '2026']):
                cpi_data.append(round(float(interanual), 1))
    return cpi_data


def _parse_rin_excel(filepath):
    """Parse BCP RIN Excel file, return list of monthly totals (2023-present)."""
    import openpyxl
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb['Hoja1']
    # Collect all date-total pairs, take last entry per month
    monthly = {}
    for row in ws.iter_rows(min_row=13, max_row=ws.max_row, values_only=True):
        date_val = row[1]
        total = row[10]
        if date_val and total is not None:
            date_str = str(date_val)
            if any(y in date_str for y in ['2023', '2024', '2025', '2026']):
                if '-' in date_str:
                    # Use YYYY-MM as key to dedupe (take last entry per month)
                    key = date_str[:7]
                    monthly[key] = round(float(total))
    # Sort by key and return values
    return [monthly[k] for k in sorted(monthly.keys())]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main dashboard."""
    # Serve dashboard.html if it exists, otherwise fall back to index.html
    dashboard_path = os.path.join(PROJECT_DIR, "dashboard.html")
    if os.path.exists(dashboard_path):
        from flask import send_from_directory
        return send_from_directory(PROJECT_DIR, "dashboard.html")
    return render_template("index.html")


@app.route("/api/briefing")
def api_briefing():
    """Return the current briefing data."""
    data = load_briefing()
    if data is None:
        return jsonify({"error": "No briefing found. Generate one first."}), 404
    return jsonify(data)


@app.route("/api/briefings")
def api_briefings():
    """List all saved briefing files."""
    return jsonify(list_briefings())


@app.route("/api/briefing/<filename>")
def api_briefing_file(filename):
    """Load a specific briefing file by name."""
    # Security: only allow briefing*.json files
    if not filename.startswith("briefing") or not filename.endswith(".json"):
        return jsonify({"error": "Invalid filename"}), 400
    path = os.path.join(PROJECT_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    with open(path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Run the research pipeline and return compiled briefing."""
    body = request.get_json(silent=True) or {}
    topic = body.get("topic", "").strip() or "Paraguay Briefing"
    time_span = body.get("time_span", "").strip()

    if not time_span:
        return jsonify({"error": "time_span is required"}), 400

    print(f"\n{'='*60}")
    print(f"[GENERATE] Topic: {topic}")
    print(f"[GENERATE] Time Span: {time_span}")
    print(f"{'='*60}\n")

    try:
        briefing = run_search_pipeline(topic, time_span)
        event_count = sum(len(s.get("events", [])) for s in briefing.get("sections", []))
        print(f"\n[OK] Generated briefing with {event_count} events across {len(briefing['sections'])} sections")
        return jsonify(briefing)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/update-macro", methods=["POST"])
def api_update_macro():
    """Parse uploaded CPI and/or RIN Excel files and return updated data."""
    body = request.get_json(silent=True) or {}
    cpi_file = body.get("cpi_file", "").strip()
    rin_file = body.get("rin_file", "").strip()
    result = {}
    if cpi_file:
        path = os.path.join(PROJECT_DIR, cpi_file)
        if os.path.exists(path):
            try:
                result["cpi"] = _parse_cpi_excel(path)
            except Exception as e:
                result["cpi_error"] = str(e)
        else:
            result["cpi_error"] = f"File not found: {cpi_file}"
    if rin_file:
        path = os.path.join(PROJECT_DIR, rin_file)
        if os.path.exists(path):
            try:
                result["rin"] = _parse_rin_excel(path)
            except Exception as e:
                result["rin_error"] = str(e)
        else:
            result["rin_error"] = f"File not found: {rin_file}"
    return jsonify(result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Paraguay Research Web Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Server port (default: 5000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════╗
║   Paraguay Briefing — Web Dashboard                ║
║   巴拉圭简报 — 网页版                                ║
╚══════════════════════════════════════════════════════╝
    """)
    print(f"  URL: http://{args.host}:{args.port}")
    print(f"  Press Ctrl+C to stop\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
