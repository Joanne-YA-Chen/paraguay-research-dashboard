"""Configuration for Paraguay Research Briefing Tool."""

import os
from dataclasses import dataclass, field


@dataclass
class SearchConfig:
    backend: str = "duckduckgo"  # duckduckgo | brave | serpapi | newsapi | manual
    brave_api_key: str = ""
    serpapi_key: str = ""
    newsapi_key: str = ""
    max_results_per_query: int = 10
    region: str = "py"  # Paraguay-focused


@dataclass
class PPTConfig:
    title_font_size: int = 32
    heading_font_size: int = 22
    body_font_size: int = 14
    source_font_size: int = 10
    title_font: str = "SimHei"
    body_font: str = "Microsoft YaHei"
    primary_color: str = "1B3A5C"  # Dark blue
    accent_color: str = "C41230"    # Red accent
    output_dir: str = "sample_output"


@dataclass
class Config:
    search: SearchConfig = field(default_factory=SearchConfig)
    ppt: PPTConfig = field(default_factory=PPTConfig)

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls()
        cfg.search.brave_api_key = os.environ.get("BRAVE_API_KEY", "")
        cfg.search.serpapi_key = os.environ.get("SERPAPI_KEY", "")
        cfg.search.newsapi_key = os.environ.get("NEWSAPI_KEY", "")
        cfg.deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        return cfg

    deepseek_api_key: str = ""


# Authoritative Paraguayan sources for source filtering and prioritization
PARAGUAY_GOV_DOMAINS = [
    "hacienda.gov.py",       # Ministry of Finance
    "bcp.gov.py",            # Central Bank of Paraguay
    "mre.gov.py",            # Ministry of Foreign Affairs
    "mic.gov.py",            # Ministry of Industry and Commerce
    "presidencia.gov.py",    # Presidency
    "senado.gov.py",         # Senate
    "diputados.gov.py",      # Chamber of Deputies
    "mtess.gov.py",          # Ministry of Labor
    "mopc.gov.py",           # Ministry of Public Works
    "conatel.gov.py",        # Telecom regulator
    "ip.gov.py",             # Paraguay state news agency
]

PARAGUAY_AUTHORITATIVE_MEDIA = [
    "abc.com.py",            # ABC Color
    "ultimahora.com",        # Última Hora
    "lanacion.com.py",       # La Nación
    "5dias.com.py",          # 5 Días (business)
    "paraguay.com",          # Paraguay.com
    "elnacional.com.py",     # El Nacional
    "hoy.com.py",            # Hoy
]

INTERNATIONAL_SOURCES = [
    "reuters.com",
    "bloomberg.com",
    "bbc.com",
    "elpais.com",
    "infobae.com",
    "dialogochino.net",      # China-Latin America relations
]

TRUSTED_SOURCES = PARAGUAY_GOV_DOMAINS + PARAGUAY_AUTHORITATIVE_MEDIA + INTERNATIONAL_SOURCES

# Strict whitelist for news filtering — only results from these domains are kept
ALLOWED_NEWS_DOMAINS = TRUSTED_SOURCES
