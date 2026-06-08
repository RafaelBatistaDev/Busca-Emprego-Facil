#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi>=0.110.0",
#     "uvicorn[standard]>=0.23.0",
#     "python-multipart>=0.0.6",
#     "requests>=2.31.0",
#     "beautifulsoup4>=4.12.0",
#     "lxml>=4.9.0",
#     "pywebview>=5.0",
#     "PyQt6>=6.0.0",
#     "PyQt6-WebEngine>=6.0.0",
#     "qtpy>=2.4.0",
# ]
# ///
"""
Busca Emprego Fácil — Aplicativo e Scraper em Arquivo Único
Consolida:
  1. Servidor Backend FastAPI e Rotas de API
  2. Interface de Usuário Frontend (HTML/CSS/JS)
  3. Lógica de Busca e Todos os Scrapers (Nacionais e Regionais de Pernambuco)
  4. Modo de Execução CLI e Agendamento
"""

import os
import re
import sys
import json
import time
import uvicorn
import hashlib
import logging
import argparse
import threading
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse

app = FastAPI(title="Busca Emprego Fácil")

# --- CONFIGURAÇÃO DE DIRETÓRIOS E CONSTANTES ---
USER_HOME   = Path.home()
BASE_DIR    = Path(__file__).resolve().parent
DATA_DIR    = Path("/tmp")
LOG_DIR     = USER_HOME / ".local" / "log"
CONFIG_FILE = BASE_DIR / "config_vagas.json"

# Logging setup
TIMESTAMP_INIT = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"job_hunter_{TIMESTAMP_INIT}.log"

HEADERS_HTTP = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 15
PLATAFORMAS_SEM_FILTRO_GEO: set[str] = {"Gupy"}

# Configuração Padrão
CONFIG_PADRAO = {
  "keywords": [
    "Porteiro",
    "Vigia",
    "Auxiliar de Linha de Produção",
    "Fiscal de Loja",
    "Prevenção de Perdas"
  ],
  "localizacao": "Recife, PE",
  "max_vagas_por_plataforma": 10,
  "delay_entre_requisicoes": 2.5,
  "plataformas": [
    "gupy",
    "linkedin",
    "indeed",
    "infojobs",
    "infojobs_geo",
    "empregope",
    "comunidadeempregope",
    "blogspot_pe",
    "google_news",
    "jobrapido"
  ]
}

# --- CORES E LOGGING ---
class Color:
    G = "\033[1;32m"; B = "\033[1;34m"; Y = "\033[1;33m"
    R = "\033[1;31m"; C = "\033[1;36m"; M = "\033[1;35m"; N = "\033[0m"

def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger_obj = logging.getLogger("job_hunter")
    logger_obj.setLevel(logging.INFO)
    if not logger_obj.handlers:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s — %(message)s"))
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger_obj.addHandler(fh)
        logger_obj.addHandler(ch)
    return logger_obj

logger = _setup_logging()

def section(titulo: str) -> None:
    borda = "═" * 55
    logger.info(f"\n{Color.M}{borda}\n  {titulo}\n{borda}{Color.N}")

def log(msg: str)     -> None: logger.info(f"{Color.B}[INFO]{Color.N}    {msg}")
def success(msg: str) -> None: logger.info(f"{Color.G}[OK]{Color.N}      {msg}")
def warn(msg: str)    -> None: logger.warning(f"{Color.Y}[AVISO]{Color.N}  {msg}")
def error(msg: str)   -> None: logger.error(f"{Color.R}[ERRO]{Color.N}   {msg}")
def debug(msg: str)   -> None: logger.debug(f"{Color.C}[DEBUG]{Color.N}  {msg}")

def bootstrap() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).lower()

def get_json_out() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DATA_DIR / f"vagas_{timestamp}.json"

# --- CACHE EM MEMÓRIA ---
CONFIG_MEM = CONFIG_PADRAO.copy()
VAGAS_CACHE = []

# --- CONFIGURAÇÃO (CARREGAR / SALVAR EM MEMÓRIA) ---
def carregar_config() -> dict:
    """Carrega as configurações a partir da memória."""
    global CONFIG_MEM
    return CONFIG_MEM

def salvar_config(config_data: dict) -> None:
    """Salva as configurações na memória."""
    global CONFIG_MEM
    CONFIG_MEM = config_data


# --- MODELOS ---
@dataclass
class Vaga:
    titulo:        str
    empresa:       str
    localizacao:   str
    url:           str
    plataforma:    str
    descricao:     str = ""
    salario:       str = ""
    data_postagem: str = ""
    data_busca:    str = field(
        default_factory=lambda: datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    )
    data_coleta:   str = field(
        default_factory=lambda: datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    )
    id_unico:  str = field(default="", init=False)
    categoria: str = field(default="", init=False)

    def __post_init__(self) -> None:
        raw = f"{self.titulo.lower()}{self.empresa.lower()}{self.plataforma}"
        self.id_unico = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict:
        return asdict(self)


# --- CLASSES BASE DE SCRAPING ---
class BaseScraper(ABC):
    nome: str = "Base"

    def __init__(
        self,
        keywords:    list[str],
        localizacao: str,
        max_vagas:   int   = 20,
        delay:       float = 2.0,
    ) -> None:
        self.keywords    = keywords
        self.localizacao = localizacao
        self.max_vagas   = max_vagas
        self.delay       = delay
        self.session     = requests.Session()
        self.session.headers.update(HEADERS_HTTP)

    def _get(
        self,
        url:    str,
        params: dict | None = None,
    ) -> requests.Response | None:
        time.sleep(self.delay)
        try:
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            warn(f"[{self.nome}] HTTP {e.response.status_code}: {url}")
        except requests.exceptions.ConnectionError:
            warn(f"[{self.nome}] Sem conexão: {url}")
        except requests.exceptions.Timeout:
            warn(f"[{self.nome}] Timeout ({REQUEST_TIMEOUT}s): {url}")
        except requests.exceptions.RequestException as e:
            warn(f"[{self.nome}] Request error: {e}")
        return None

    @abstractmethod
    def buscar(self) -> list[Vaga]: ...


class StaticUrlScraper(BaseScraper):
    nome: str       = "StaticUrl"
    URLS: list[str] = []

    @abstractmethod
    def _extrair(self, soup: BeautifulSoup, url: str) -> list[Vaga]: ...

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        for url in self.URLS:
            resp = self._get(url)
            if not resp:
                continue
            soup        = BeautifulSoup(resp.text, "html.parser")
            encontradas = self._extrair(soup, url)[: self.max_vagas]
            if encontradas:
                success(f"[{self.nome}] {len(encontradas)} vagas → {url}")
            else:
                warn(f"[{self.nome}] Sem vagas (seletor pode ter mudado) → {url}")
            vagas.extend(encontradas)
        return vagas


# --- IMPLEMENTAÇÕES DOS SCRAPERS ---

class GupyScraper(BaseScraper):
    nome     = "Gupy"
    BASE_URL = "https://portal.api.gupy.io/api/job"

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        for kw in self.keywords:
            resp = self._get(self.BASE_URL, params={
                "name":   kw,
                "limit":  self.max_vagas,
                "offset": 0,
            })
            if not resp:
                continue
            for job in resp.json().get("data", []):
                city  = job.get("city",  "") or ""
                state = job.get("state", "") or ""
                vagas.append(Vaga(
                    titulo      = job.get("name", ""),
                    empresa     = job.get("careerPageName", "N/D"),
                    localizacao = f"{city} - {state}",
                    url         = job.get("jobUrl", ""),
                    plataforma  = "Gupy",
                ))
        return vagas


class IndeedScraper(BaseScraper):
    nome     = "Indeed"
    BASE_URL = "https://br.indeed.com/empregos"

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        for kw in self.keywords:
            resp = self._get(self.BASE_URL, params={"q": kw, "l": self.localizacao})
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select(".job_seen_beacon")[: self.max_vagas]:
                titulo_el  = card.select_one("h2.jobTitle")
                empresa_el = card.select_one("[data-testid='company-name'], .companyName")
                local_el   = card.select_one("[data-testid='text-location'], .companyLocation")
                link_el    = card.select_one("h2.jobTitle a")
                if not titulo_el:
                    continue
                href = link_el.get("href", "") if link_el else ""
                url  = href if href.startswith("http") else f"https://br.indeed.com{href}"
                vagas.append(Vaga(
                    titulo      = titulo_el.get_text(strip=True),
                    empresa     = empresa_el.get_text(strip=True) if empresa_el else "N/D",
                    localizacao = local_el.get_text(strip=True) if local_el else self.localizacao,
                    url         = url,
                    plataforma  = "Indeed",
                ))
        return vagas


class InfoJobsScraper(BaseScraper):
    nome     = "InfoJobs"
    BASE_URL = "https://www.infojobs.com.br"

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        for kw in self.keywords:
            kw_f  = kw.lower().replace(" ", "-")
            loc_f = self.localizacao.lower().replace(",", "").replace(" ", "-")
            resp  = self._get(f"{self.BASE_URL}/vagas-de-emprego-{kw_f}-em-{loc_f}.aspx")
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("div.js_rowCard")[: self.max_vagas]:
                titulo_el = card.select_one("h2")
                if not titulo_el:
                    continue
                empresa = "N/D"
                empresa_link = card.select_one("a.text-body.text-decoration-none")
                if empresa_link:
                    span = empresa_link.select_one("span.text-nowrap")
                    if span:
                        empresa = span.find(string=True, recursive=False)
                        empresa = empresa.strip() if empresa else span.get_text(strip=True)
                localizacao = self.localizacao
                local_el = card.select_one("div.mb-8")
                if local_el:
                    for spam in local_el.select("span.js_divUserVagaDistance"):
                        spam.decompose()
                    localizacao = local_el.get_text(strip=True)
                salario = ""
                money_icon = card.select_one("svg.icon-money")
                if money_icon:
                    salario = money_icon.find_parent().get_text(strip=True)
                link_el = card.select_one("[data-href]")
                href = link_el.get("data-href", "") if link_el else ""
                url  = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                vagas.append(Vaga(
                    titulo      = titulo_el.get_text(strip=True),
                    empresa     = empresa,
                    localizacao = localizacao,
                    url         = url,
                    plataforma  = "InfoJobs",
                    salario     = salario,
                ))
        return vagas


class LinkedInScraper(BaseScraper):
    nome     = "LinkedIn"
    BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        for kw in self.keywords:
            resp = self._get(self.BASE_URL, params={
                "keywords": kw,
                "location": self.localizacao,
            })
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select(".base-card")[: self.max_vagas]:
                titulo_el  = card.select_one(".base-search-card__title")
                empresa_el = card.select_one(".base-search-card__subtitle")
                local_el   = card.select_one(".job-search-card__location")
                link_el    = card.select_one("a.base-card__full-link")
                if not titulo_el:
                    continue
                vagas.append(Vaga(
                    titulo      = titulo_el.get_text(strip=True),
                    empresa     = empresa_el.get_text(strip=True) if empresa_el else "N/D",
                    localizacao = local_el.get_text(strip=True) if local_el else self.localizacao,
                    url         = link_el.get("href", "") if link_el else "",
                    plataforma  = "LinkedIn",
                ))
        return vagas


class EmpregoPEScraper(BaseScraper):
    nome     = "EmpregoPE"
    BASE_URL = "https://empregospernambuco.com.br/jobs"
    _SELETORES_CARD = ["li.job", "li.job-alt"]
    _PARAMS_BUSCA = ("search_keywords", "q")

    def _detectar_cards(self, soup: BeautifulSoup) -> list:
        for seletor in self._SELETORES_CARD:
            cards = soup.select(seletor)
            if cards:
                return cards
        return []

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        for keyword in self.keywords:
            cards = []
            for param_key in self._PARAMS_BUSCA:
                resp = self._get(self.BASE_URL, params={param_key: keyword})
                if not resp:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = self._detectar_cards(soup)
                if cards:
                    break
            if not cards:
                continue
            for card in cards[: self.max_vagas]:
                try:
                    titulo_el = card.select_one("div.job-title a") or card.select_one("h1 a, h2 a, h3 a") or card.select_one("a")
                    if not titulo_el:
                        continue
                    meta_el = card.select_one("div.job-meta")
                    empresa_el = meta_el.select_one("[class*='company'], strong, span") if meta_el else None
                    local_el = card.select_one("[class*='location'], [class*='local'], div.job-meta [class*='loc']")
                    data_el = card.select_one("div.job-date, time[datetime]")
                    data_post = data_el.get("datetime") or data_el.get_text(strip=True) if data_el else ""
                    href = titulo_el.get("href", "")
                    link = href if href.startswith("http") else f"https://empregospernambuco.com.br{href}"
                    vagas.append(Vaga(
                        titulo=titulo_el.get_text(strip=True),
                        empresa=empresa_el.get_text(strip=True) if empresa_el else "N/D",
                        localizacao=local_el.get_text(strip=True) if local_el else "Pernambuco",
                        url=link,
                        plataforma="EmpregoPE",
                        data_postagem=data_post,
                    ))
                except Exception:
                    pass
        return vagas


class ComunidadeEmpregoPEScraper(BaseScraper):
    nome     = "ComunidadeEmpregoPE"
    BASE_URL = "https://comunidadeempregope.com.br"

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        endpoints = ["/", "/vagas", "/empregos", "/oportunidades", "/jobs"]
        soup_principal = None
        for endpoint in endpoints:
            resp = self._get(f"{self.BASE_URL}{endpoint}")
            if resp:
                soup_principal = BeautifulSoup(resp.text, "html.parser")
                if soup_principal.select("[class*='job'], [class*='vaga'], article"):
                    break
        if not soup_principal:
            return []
        cards = soup_principal.select("article, .post, [class*='vaga'], [class*='job']") or soup_principal.select("div.entry, div.card")
        keywords_lower = [k.lower() for k in self.keywords]
        for card in cards[: self.max_vagas * 3]:
            try:
                titulo_el = card.select_one("h1 a, h2 a, h3 a, .entry-title a")
                empresa_el = card.select_one("[class*='company'], [class*='empresa'], .author")
                local_el = card.select_one("[class*='location'], [class*='local'], [class*='city']")
                desc_el = card.select_one("p, .excerpt, .summary, [class*='desc']")
                data_el = card.select_one("time[datetime], .entry-date, [class*='date'], [class*='data']")
                if not titulo_el:
                    continue
                titulo = titulo_el.get_text(strip=True)
                desc = desc_el.get_text(strip=True) if desc_el else ""
                texto = (titulo + " " + desc).lower()
                if not any(kw in texto for kw in keywords_lower):
                    continue
                href = titulo_el.get("href", "")
                link = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                data_post = data_el.get("datetime") or data_el.get_text(strip=True) if data_el else ""
                vagas.append(Vaga(
                    titulo=titulo,
                    empresa=empresa_el.get_text(strip=True) if empresa_el else "N/D",
                    localizacao=local_el.get_text(strip=True) if local_el else "Pernambuco",
                    url=link,
                    plataforma="ComunidadeEmpregoPE",
                    descricao=desc[:300],
                    data_postagem=data_post,
                ))
                if len(vagas) >= self.max_vagas:
                    break
            except Exception:
                pass
        return vagas


class BlogspotRSSScraper(BaseScraper):
    nome    = "BlogspotPE"
    RSS_URL = "https://informevagaspe.blogspot.com/feeds/posts/default?alt=rss&max-results=50"

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        resp = self._get(self.RSS_URL)
        if not resp:
            return []
        try:
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
        except Exception:
            return []
        keywords_lower = [k.lower() for k in self.keywords]
        for item in items[: self.max_vagas * 3]:
            try:
                titulo   = item.findtext("title", "").strip()
                link     = item.findtext("link", "").strip()
                desc_raw = item.findtext("description", "").strip()
                pubdate  = item.findtext("pubDate", "").strip()
                desc_soup = BeautifulSoup(desc_raw, "html.parser")
                desc      = desc_soup.get_text(separator=" ", strip=True)[:500]
                texto = (titulo + " " + desc).lower()
                if not any(kw in texto for kw in keywords_lower):
                    continue
                empresa = self._extrair_empresa(desc)
                local   = self._extrair_local(desc) or "Pernambuco"
                vagas.append(Vaga(
                    titulo=titulo or "Vaga no InformeVagasPE",
                    empresa=empresa,
                    localizacao=local,
                    url=link,
                    plataforma="BlogspotPE",
                    descricao=desc[:300],
                    data_postagem=pubdate,
                ))
                if len(vagas) >= self.max_vagas:
                    break
            except Exception:
                pass
        return vagas

    def _extrair_empresa(self, texto: str) -> str:
        padroes = [
            r"empresa[:\s]+([A-Z][^\n,\.]{2,40})",
            r"contratante[:\s]+([A-Z][^\n,\.]{2,40})",
            r"(?:vaga|oportunidade)\s+(?:na|no|em)\s+([A-Z][^\n,\.]{2,40})",
        ]
        for padrao in padroes:
            match = re.search(padrao, texto, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "N/D"

    def _extrair_local(self, texto: str) -> str:
        cidades_pe = ["Recife", "Jaboatão", "Caruaru", "Olinda", "Paulista", "Cabo de Santo Agostinho", "Camaragibe", "Garanhuns", "Petrolina", "Vitória de Santo Antão"]
        for cidade in cidades_pe:
            if cidade.lower() in texto.lower():
                return f"{cidade} - PE"
        return ""


class GoogleNewsScraper(BaseScraper):
    nome     = "GoogleNews"
    RSS_BASE = "https://news.google.com/rss/search"
    QUERIES_PE = [
        "concursos pernambuco abertos",
        "seleção simplificada pernambuco",
        "processo seletivo recife PE",
        "edital concurso público pernambuco",
    ]

    def _parse_data_rss(self, data_str: str) -> datetime | None:
        if not data_str:
            return None
        try:
            return datetime.strptime(data_str.strip(), "%a, %d %b %Y %H:%M:%S %Z")
        except ValueError:
            return None

    def _é_dentro_do_ultimo_mes(self, pubdate_str: str) -> bool:
        data = self._parse_data_rss(pubdate_str)
        if not data:
            return True
        hoje = datetime.now()
        dias_diff = (hoje - data).days
        return 0 <= dias_diff <= 30

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        urls_vistos = set()
        for query in self.QUERIES_PE:
            params = {"q": query, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
            resp = self._get(self.RSS_BASE, params=params)
            if not resp:
                continue
            try:
                root = ET.fromstring(resp.content)
                items = root.findall(".//item")
            except Exception:
                continue
            for item in items[: self.max_vagas * 2]:
                try:
                    titulo   = item.findtext("title", "").strip()
                    link     = item.findtext("link", "").strip()
                    fonte    = item.findtext("source", "").strip()
                    pubdate  = item.findtext("pubDate", "").strip()
                    desc_raw = item.findtext("description", "").strip()
                    if not titulo or not link:
                        continue
                    if link in urls_vistos:
                        continue
                    urls_vistos.add(link)
                    if not self._é_dentro_do_ultimo_mes(pubdate):
                        continue
                    desc_soup = BeautifulSoup(desc_raw, "html.parser")
                    desc      = desc_soup.get_text(strip=True)[:300]
                    vagas.append(Vaga(
                        titulo=titulo,
                        empresa=fonte or "Google News",
                        localizacao="Pernambuco",
                        url=link,
                        plataforma="GoogleNews",
                        descricao=desc,
                        data_postagem=pubdate,
                    ))
                    if len(vagas) >= self.max_vagas:
                        break
                except Exception:
                    pass
        return vagas


class InfoJobsGeoScraper(StaticUrlScraper):
    nome     = "InfoJobsGeo"
    BASE_URL = "https://www.infojobs.com.br"
    URLS = [
        "https://www.infojobs.com.br/vagas-de-emprego-fiscal+de+preven%c3%a7%c3%a3o+de+perdas-em-recife,-pe.aspx?Antiguedad=3&sprd=25&splat=-8.037708&splng=-34.9540847",
        "https://www.infojobs.com.br/empregos.aspx?splng=-34.9540847&palabra=Porteiro&splat=-8.037708&sprd=25&poblacion=5207362",
        "https://www.infojobs.com.br/empregos.aspx?palabra=Porteiro&sprd=25&splng=-34.9540847&splat=-8.037708&poblacion=5207273",
    ]

    def _extrair(self, soup: BeautifulSoup, url: str) -> list[Vaga]:
        vagas: list[Vaga] = []
        cards = soup.select("div.js_rowCard")
        for card in cards:
            try:
                titulo_el  = card.select_one("h2")
                link_div   = card.select_one("div.js_cardLink[data-href]")
                empresa_el = card.select_one("a[href*='/empresa-']")
                salario_el = card.select_one("[class*='salary'], [class*='salario']")
                data_el    = card.select_one("div.js_date[data-value]")
                data_texto = card.select_one("div.text-medium.small.text-nowrap")
                if not titulo_el or not link_div:
                    continue
                if data_el and data_el.get("data-value"):
                    data_post = data_el["data-value"][:10]
                elif data_texto:
                    data_post = data_texto.get_text(strip=True)
                else:
                    data_post = ""
                vagas.append(Vaga(
                    titulo=titulo_el.get_text(strip=True),
                    empresa=empresa_el.get_text(strip=True) if empresa_el else "N/D",
                    localizacao="Recife - PE",
                    url=self.BASE_URL + link_div["data-href"],
                    plataforma="InfoJobsGeo",
                    salario=salario_el.get_text(strip=True) if salario_el else "A combinar",
                    data_postagem=data_post,
                ))
            except Exception:
                pass
        return vagas


class JobrapidoScraper(BaseScraper):
    nome     = "Jobrapido"
    BASE_URL = "https://br.jobrapido.com"
    HOST     = "https://br.jobrapido.com"

    def buscar(self) -> list[Vaga]:
        vagas: list[Vaga] = []
        for kw in self.keywords:
            resp = self._get(self.BASE_URL, params={"w": kw, "l": "Recife", "r": "25"})
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("article.js_result, .result, li.result") or soup.select("[class*='job-card'], [class*='jobCard']") or soup.select("div[data-job-id], li[data-id]")
            if not cards:
                continue
            for card in cards[: self.max_vagas]:
                try:
                    titulo_el  = card.select_one("h2 a, h3 a, .title a, [class*='title'] a, [itemprop='title']")
                    empresa_el = card.select_one("[itemprop='hiringOrganization'], .company, [class*='company']")
                    local_el   = card.select_one("[itemprop='addressLocality'], .location, [class*='location']")
                    salario_el = card.select_one("[itemprop='baseSalary'], .salary, [class*='salary']")
                    data_el    = card.select_one("time[datetime], [class*='date'], [class*='data']")
                    if not titulo_el:
                        continue
                    href = titulo_el.get("href", "")
                    url = href if href.startswith("http") else f"{self.HOST}{href}"
                    data_post = data_el.get("datetime") or data_el.get_text(strip=True) if data_el else ""
                    vagas.append(Vaga(
                        titulo        = titulo_el.get_text(strip=True),
                        empresa       = empresa_el.get_text(strip=True) if empresa_el else "N/D",
                        localizacao   = local_el.get_text(strip=True) if local_el else "Recife - PE",
                        url           = url,
                        plataforma    = "Jobrapido",
                        salario       = salario_el.get_text(strip=True) if salario_el else "",
                        data_postagem = data_post,
                    ))
                except Exception:
                    pass
        return vagas


# --- REGISTRO DE MOTOR DE BUSCA ---
SCRAPERS_MAP: dict[str, type[BaseScraper]] = {
    "gupy":                 GupyScraper,
    "indeed":               IndeedScraper,
    "infojobs":             InfoJobsScraper,
    "linkedin":             LinkedInScraper,
    "empregope":            EmpregoPEScraper,
    "comunidadeempregope":  ComunidadeEmpregoPEScraper,
    "blogspot_pe":          BlogspotRSSScraper,
    "google_news":          GoogleNewsScraper,
    "infojobs_geo":         InfoJobsGeoScraper,
    "jobrapido":            JobrapidoScraper,
}

# --- PROCESSAMENTO E BUSCA ---
def filtrar_por_localizacao(vagas: list[Vaga], localizacao: str) -> list[Vaga]:
    termos = [normalizar_texto(t) for t in localizacao.replace(",", " ").split() if len(t) > 1]
    def é_local(v: Vaga) -> bool:
        if v.plataforma in PLATAFORMAS_SEM_FILTRO_GEO:
            return True
        loc = normalizar_texto(v.localizacao)
        return any(t in loc for t in termos)
    antes = len(vagas)
    vagas = [v for v in vagas if é_local(v)]
    removidas = antes - len(vagas)
    if removidas:
        warn(f"{removidas} vagas fora de '{localizacao}' removidas pelo filtro geográfico.")
    return vagas

def categorize_vagas(vagas: list[Vaga], keywords: list[str]) -> list[Vaga]:
    kw_n = [normalizar_texto(k) for k in keywords]
    for v in vagas:
        v.categoria = "Outros"
        texto = normalizar_texto(v.titulo + v.descricao)
        for i, kn in enumerate(kw_n):
            if kn in texto:
                v.categoria = keywords[i].capitalize()
                break
    return vagas

def salvar_json_hunter(vagas: list[Vaga], caminho: Path) -> None:
    try:
        payload = {
            "meta": {
                "total":     len(vagas),
                "gerado_em": datetime.now().isoformat(),
            },
            "vagas": [v.to_dict() for v in vagas],
        }
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        warn(f"Não foi possível salvar o arquivo JSON localmente: {e}")

def executar_busca(config: dict) -> list[Vaga]:
    todas: list[Vaga] = []
    for nome in config.get("plataformas", []):
        cls = SCRAPERS_MAP.get(nome.lower())
        if not cls:
            warn(f"Plataforma desconhecida ignorada: '{nome}'")
            continue
        section(f"🔍 {nome.upper()}")
        try:
            resultado = cls(
                config["keywords"],
                config["localizacao"],
                config["max_vagas_por_plataforma"],
                config["delay_entre_requisicoes"],
            ).buscar()
            if resultado:
                isento = cls.nome in PLATAFORMAS_SEM_FILTRO_GEO
                sufixo = " (nacional — filtro no JS)" if isento else ""
                success(f"{len(resultado)} vagas coletadas em {nome}{sufixo}")
                for v in resultado[:3]:
                    log(f"   → {v.titulo} | {v.empresa} | {v.localizacao}")
                if len(resultado) > 3:
                    log(f"   ... e mais {len(resultado) - 3} vagas.")
            else:
                warn(f"Nenhuma vaga retornada por {nome}.")
            todas.extend(resultado)
        except Exception as e:
            error(f"{nome}: {e}")

    vistos = set()
    urls_vistos = set()
    unicas = []
    for v in todas:
        if v.id_unico not in vistos and v.url not in urls_vistos:
            vistos.add(v.id_unico)
            urls_vistos.add(v.url)
            unicas.append(v)
    duplicadas = len(todas) - len(unicas)
    if duplicadas:
        log(f"{duplicadas} duplicatas removidas (por título/empresa/URL).")
    unicas = filtrar_por_localizacao(unicas, config["localizacao"])
    return unicas


# --- TEMPLATE FRONTEND ---
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Busca Emprego Fácil</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" sizes="96x96" href="/buscaempregofacil.png">
    
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
    
    <style>
        :root {
            --bg: #0b0d14;
            --bg2: #111420;
            --bg-glass: rgba(17, 20, 32, 0.85);
            --surface: #1e2235;
            --surface-hover: #2a2f4a;
            --border: #2a2f4a;
            --border-hover: rgba(79, 255, 176, 0.35);
            --accent: #4fffb0;
            --accent-glow: rgba(79, 255, 176, 0.15);
            --accent2: #3de8ff;
            --accent2-glow: rgba(61, 232, 255, 0.15);
            --danger: #ff4e6a;
            --danger-glow: rgba(255, 78, 106, 0.15);
            --text-primary: #e8eaf4;
            --text-secondary: #7b82a6;
            --text-muted: #64748b;
            --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            --font-main: 'DM Sans', sans-serif;
            --font-title: 'Syne', sans-serif;
        }
        
        *, *::before, *::after {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: var(--font-main);
            background: var(--bg);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
            background-image: radial-gradient(circle at 10% 20%, rgba(16, 185, 129, 0.03) 0%, transparent 40%),
                              radial-gradient(circle at 90% 80%, rgba(79, 70, 229, 0.03) 0%, transparent 40%);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 30px 20px;
        }
        
        /* Glassmorphism Header */
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 24px;
            background: var(--bg-glass);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            padding: 18px 24px;
            border-radius: 20px;
            border: 1px solid var(--border);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
            flex-wrap: wrap;
            gap: 16px;
        }
        
        .logo-container {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .logo-img {
            width: 38px;
            height: 38px;
            object-fit: contain;
        }
        
        h1 {
            font-family: var(--font-title);
            font-size: 22px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #ffffff 30%, var(--text-secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        nav {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        
        .nav-btn {
            padding: 9px 16px;
            border-radius: 12px;
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-secondary);
            font-family: var(--font-title);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .nav-btn:hover {
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.03);
        }
        
        .nav-btn.active {
            background: var(--surface);
            border-color: var(--border);
            color: var(--accent);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        
        .nav-btn-action {
            background: var(--accent-glow);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: var(--accent);
        }
        .nav-btn-action:hover {
            background: rgba(16, 185, 129, 0.25);
            border-color: var(--accent);
        }
        
        .nav-btn.btn-clear {
            background: var(--danger-glow);
            border-color: rgba(244, 63, 94, 0.3);
            color: var(--danger);
        }
        .nav-btn.btn-clear:hover {
            background: rgba(244, 63, 94, 0.25);
            border-color: var(--danger);
        }
        
        /* Stats Dashboard Panel */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        
        .stat-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            gap: 16px;
            transition: var(--transition);
        }
        
        .stat-card:hover {
            border-color: var(--border-hover);
            transform: translateY(-2px);
        }
        
        .stat-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            flex-shrink: 0;
            box-shadow: 0 0 8px currentColor;
        }
        .stat-indicator-vagas { color: var(--accent); background-color: var(--accent); }
        .stat-indicator-categorias { color: var(--accent2); background-color: var(--accent2); }
        .stat-indicator-fontes { color: var(--text-secondary); background-color: var(--text-secondary); }
        
        .stat-info {
            display: flex;
            flex-direction: column;
        }
        
        .stat-label {
            color: var(--text-muted);
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .stat-value {
            font-family: var(--font-title);
            font-size: 20px;
            font-weight: 700;
            color: var(--text-primary);
            margin-top: 2px;
        }
        
        /* Views layout */
        .view {
            display: none;
            animation: fadeIn 0.3s ease-out forwards;
        }
        .view.active {
            display: block;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* Filter Container */
        .filters-container {
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            align-items: center;
            background: var(--bg-glass);
            padding: 14px 20px;
            border-radius: 16px;
            border: 1px solid var(--border);
        }
        
        .filter-group {
            display: flex;
            align-items: center;
            gap: 8px;
            flex: 1;
            min-width: 180px;
        }
        
        .filter-input {
            width: 100%;
            padding: 10px 14px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            color: var(--text-primary);
            border-radius: 10px;
            font-family: var(--font-main);
            font-size: 13px;
            outline: none;
            transition: var(--transition);
        }
        
        .filter-input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }
        
        .filter-label {
            color: var(--text-secondary);
            font-size: 12px;
            white-space: nowrap;
        }
        
        .btn-reset-filter {
            padding: 10px 18px;
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            border-radius: 10px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            transition: var(--transition);
            width: auto;
        }
        
        .btn-reset-filter:hover {
            border-color: var(--text-secondary);
            color: var(--text-primary);
        }
        
        /* Categorias e Vagas cards list */
        .categoria-section {
            background: var(--bg-glass);
            border: 1px solid var(--border);
            border-radius: 16px;
            margin-bottom: 20px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        }
        
        .categoria-title {
            font-family: var(--font-title);
            font-size: 14px;
            font-weight: 700;
            padding: 14px 20px;
            border-bottom: 1px solid var(--border);
            color: var(--accent);
            background: rgba(255, 255, 255, 0.01);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .categoria-badge {
            background: var(--accent-glow);
            color: var(--accent);
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
        }
        
        .vagas-list {
            padding: 16px;
            display: grid;
            grid-template-columns: 1fr;
            gap: 12px;
        }
        
        .vaga-card {
            padding: 16px 20px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            transition: var(--transition);
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .vaga-card:hover {
            border-color: var(--border-hover);
            background: var(--surface-hover);
            transform: translateX(4px);
        }
        
        .vaga-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
            flex-wrap: wrap;
        }
        
        .vaga-titulo {
            font-family: var(--font-title);
            font-size: 15px;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1.4;
            flex: 1;
            min-width: 200px;
        }
        
        .vaga-platform-badge {
            font-size: 10px;
            padding: 3px 8px;
            border-radius: 6px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }
        
        .badge-gupy { background: rgba(0, 102, 255, 0.12); color: #3de8ff; border: 1px solid rgba(0, 102, 255, 0.2); }
        .badge-linkedin { background: rgba(10, 102, 194, 0.12); color: #00a0dc; border: 1px solid rgba(10, 102, 194, 0.2); }
        .badge-indeed { background: rgba(33, 100, 245, 0.12); color: #4b89ff; border: 1px solid rgba(33, 100, 245, 0.2); }
        .badge-infojobs { background: rgba(255, 102, 0, 0.12); color: #ff8533; border: 1px solid rgba(255, 102, 0, 0.2); }
        .badge-infojobs_geo { background: rgba(255, 153, 0, 0.12); color: #ffa933; border: 1px solid rgba(255, 153, 0, 0.2); }
        .badge-empregope { background: rgba(16, 185, 129, 0.12); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2); }
        .badge-comunidadeempregope { background: rgba(139, 92, 246, 0.12); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.2); }
        .badge-blogspot_pe { background: rgba(249, 115, 22, 0.12); color: #fb923c; border: 1px solid rgba(249, 115, 22, 0.2); }
        .badge-google_news { background: rgba(59, 130, 246, 0.12); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.2); }
        .badge-jobrapido { background: rgba(20, 184, 166, 0.12); color: #2dd4bf; border: 1px solid rgba(20, 184, 166, 0.2); }
        .badge-other { background: rgba(100, 116, 139, 0.12); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.2); }
        
        .vaga-body {
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
        }
        
        .vaga-detalhe {
            font-size: 13px;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .vaga-detalhe strong {
            color: var(--text-primary);
            font-weight: 500;
        }
        
        .vaga-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-top: 1px solid rgba(255, 255, 255, 0.03);
            padding-top: 12px;
            margin-top: 4px;
            flex-wrap: wrap;
            gap: 10px;
        }
        
        .vaga-link {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border);
            color: var(--text-primary);
            text-decoration: none;
            font-size: 12px;
            font-weight: 600;
            border-radius: 8px;
            transition: var(--transition);
        }
        
        .vaga-link:hover {
            background: var(--accent);
            color: var(--bg);
            border-color: var(--accent);
            box-shadow: 0 4px 12px var(--accent-glow);
        }
        
        .vaga-data-badge {
            font-size: 11px;
            color: var(--text-muted);
        }
        
        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 60px 40px;
            background: var(--bg-glass);
            border: 1px dashed var(--border);
            border-radius: 16px;
            color: var(--text-secondary);
        }
        
        .empty-title {
            font-family: var(--font-title);
            font-size: 16px;
            color: var(--text-primary);
            margin-bottom: 6px;
        }
        
        /* Configuration Form Layout */
        form {
            background: var(--bg-glass);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 24px 30px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.15);
        }
        
        .form-section-title {
            font-family: var(--font-title);
            font-size: 16px;
            font-weight: 700;
            color: var(--accent2);
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border);
        }
        
        .form-group {
            margin-bottom: 16px;
        }
        
        form label {
            display: block;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 6px;
        }
        
        form textarea,
        form input[type="text"],
        form input[type="number"] {
            width: 100%;
            padding: 10px 14px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text-primary);
            font-family: var(--font-main);
            font-size: 13px;
            outline: none;
            resize: vertical;
            transition: var(--transition);
        }
        
        form textarea:focus,
        form input:focus {
            border-color: var(--accent2);
            box-shadow: 0 0 0 3px var(--accent2-glow);
        }
        
        .form-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }
        
        .platforms-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 10px;
            margin-top: 8px;
        }
        
        .platform-card {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 10px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            color: var(--text-secondary);
            transition: var(--transition);
            user-select: none;
        }
        
        .platform-card:hover {
            border-color: var(--border-hover);
            color: var(--text-primary);
        }
        
        .platform-card input[type="checkbox"] {
            appearance: none;
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 5px;
            position: relative;
            cursor: pointer;
            transition: var(--transition);
        }
        
        .platform-card input[type="checkbox"]:checked {
            background: var(--accent2);
            border-color: var(--accent2);
        }
        
        .platform-card input[type="checkbox"]:checked::after {
            content: "✓";
            position: absolute;
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
        }
        
        .platform-card span {
            flex-grow: 1;
        }
        
        .btn-submit {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, var(--accent2) 0%, #312e81 100%);
            color: #ffffff;
            font-family: var(--font-title);
            font-size: 14px;
            font-weight: 700;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            transition: var(--transition);
            margin-top: 16px;
            box-shadow: 0 4px 15px rgba(79, 70, 229, 0.2);
        }
        
        .btn-submit:hover {
            opacity: 0.95;
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(79, 70, 229, 0.35);
        }
        
        /* Spinner Glass Overlay */
        .loader-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(5, 6, 12, 0.8);
            backdrop-filter: blur(12px);
            z-index: 1000;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
        }
        
        .loader-overlay.active {
            opacity: 1;
            pointer-events: auto;
        }
        
        .spinner {
            width: 50px;
            height: 50px;
            border: 3px solid rgba(255, 255, 255, 0.05);
            border-top-color: var(--accent);
            border-right-color: var(--accent2);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }
        
        .loader-text {
            font-family: var(--font-title);
            font-size: 16px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 6px;
            text-align: center;
        }
        
        .loader-sub {
            font-size: 13px;
            color: var(--text-secondary);
            text-align: center;
            padding: 0 20px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Toast Notification System */
        .toast-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 1001;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: 360px;
            width: calc(100% - 40px);
        }
        
        .toast {
            padding: 12px 18px;
            border-radius: 12px;
            background: rgba(13, 17, 34, 0.9);
            border: 1px solid var(--border);
            color: var(--text-primary);
            font-size: 13px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            gap: 10px;
            transform: translateX(120%);
            transition: transform 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55), opacity 0.3s;
            opacity: 0;
        }
        
        .toast.show {
            transform: translateX(0);
            opacity: 1;
        }
        
        .toast-success { border-left: 3px solid var(--accent); }
        .toast-error { border-left: 3px solid var(--danger); }
        
        @media (max-width: 768px) {
            .container {
                padding: 16px 12px;
            }
            header {
                flex-direction: column;
                gap: 14px;
                align-items: stretch;
                text-align: center;
                padding: 16px;
            }
            .logo-container {
                justify-content: center;
            }
            h1 {
                font-size: 20px;
            }
            nav {
                justify-content: center;
                gap: 6px;
            }
            .nav-btn {
                padding: 8px 12px;
                font-size: 12px;
                flex: 1;
                min-width: 120px;
                justify-content: center;
            }
            .stats-grid {
                grid-template-columns: 1fr;
                gap: 10px;
            }
            .stat-card {
                padding: 12px 16px;
            }
            .filters-container {
                padding: 12px;
                flex-direction: column;
                align-items: stretch;
            }
            .filter-group {
                min-width: 100%;
            }
            .btn-reset-filter {
                width: 100%;
                text-align: center;
            }
            .form-grid {
                grid-template-columns: 1fr;
                gap: 12px;
            }
            form {
                padding: 16px 20px;
            }
            .vaga-card {
                padding: 14px 16px;
            }
            .vaga-titulo {
                font-size: 14px;
            }
            .vaga-body {
                flex-direction: column;
                gap: 8px;
            }
            .vaga-footer {
                flex-direction: column;
                align-items: stretch;
                gap: 12px;
            }
            .vaga-link {
                justify-content: center;
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="logo-container">
                <img class="logo-img" src="/buscaempregofacil.png" alt="Logo" onerror="this.style.display='none'">
                <h1>Busca Emprego Fácil</h1>
            </div>
            <nav>
                <button class="nav-btn active" id="btn-tab-vagas">Vagas</button>
                <button class="nav-btn" id="btn-tab-config">Configuração</button>
                <button class="nav-btn nav-btn-action" id="btn-executar-coleta">Executar Coleta</button>
                <button class="nav-btn btn-clear" id="btn-limpar-vagas">Limpar Vagas</button>
            </nav>
        </header>

        <!-- Stats Bar -->
        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-indicator stat-indicator-vagas"></span>
                <div class="stat-info">
                    <span class="stat-label">Vagas Encontradas</span>
                    <span class="stat-value" id="stat-total">0</span>
                </div>
            </div>
            <div class="stat-card">
                <span class="stat-indicator stat-indicator-categorias"></span>
                <div class="stat-info">
                    <span class="stat-label">Categorias Ativas</span>
                    <span class="stat-value" id="stat-categories">0</span>
                </div>
            </div>
            <div class="stat-card">
                <span class="stat-indicator stat-indicator-fontes"></span>
                <div class="stat-info">
                    <span class="stat-label">Fontes Carregadas</span>
                    <span class="stat-value" id="stat-platforms">0</span>
                </div>
            </div>
        </div>

        <!-- View Vagas -->
        <div class="view active" id="view-vagas">
            <div class="filters-container">
                <div class="filter-group">
                    <input type="text" id="filtro-cidade" placeholder="Cidade ou Localização..." class="filter-input">
                </div>
                <div class="filter-group">
                    <span class="filter-label">De:</span>
                    <input type="date" id="data-inicio" class="filter-input">
                </div>
                <div class="filter-group">
                    <span class="filter-label">Até:</span>
                    <input type="date" id="data-fim" class="filter-input">
                </div>
                <button class="btn-reset-filter" id="btn-resetar-filtros">Limpar Filtros</button>
            </div>

            <!-- Vagas container -->
            <div id="vagas-container">
                <div class="empty-state">
                    <h3 class="empty-title">Sem vagas no cache</h3>
                    <p>Clique em "Executar Coleta" no menu superior para iniciar a busca.</p>
                </div>
            </div>
        </div>

        <!-- View Configurações -->
        <div class="view" id="view-config">
            <form id="config-form">
                <div class="form-section-title">Critérios de Busca</div>
                
                <div class="form-group">
                    <label for="keywords">Palavras-chave (uma por linha):</label>
                    <textarea id="keywords" rows="4" placeholder="Porteiro&#10;Vigia&#10;Fiscal de Loja"></textarea>
                </div>

                <div class="form-group">
                    <label for="localizacao">Cidade/Estado padrão:</label>
                    <input type="text" id="localizacao" placeholder="Recife, PE">
                </div>

                <div class="form-grid">
                    <div class="form-group">
                        <label for="max_vagas">Máx. Vagas por Plataforma:</label>
                        <input type="number" id="max_vagas" value="10" min="1">
                    </div>
                    <div class="form-group">
                        <label for="delay">Intervalo entre requisições (segundos):</label>
                        <input type="number" id="delay" value="2.5" step="0.1" min="0">
                    </div>
                </div>

                <div class="form-section-title" style="margin-top: 24px;">Fontes de Pesquisa</div>
                <label>Plataformas ativas:</label>
                <div class="platforms-grid" id="platforms-container">
                </div>

                <button type="submit" class="btn-submit">Salvar Configurações</button>
            </form>
        </div>
    </div>

    <!-- Spinner Loader -->
    <div class="loader-overlay" id="loader">
        <div class="spinner"></div>
        <div class="loader-text" id="loader-title">Coletando vagas...</div>
        <div class="loader-sub">Isso pode levar alguns minutos dependendo do volume de plataformas configuradas.</div>
    </div>

    <!-- Container Toast -->
    <div class="toast-container" id="toast-container"></div>

    <script>
        const PLATAFORMAS_DISPONIVEIS = [
            { id: 'gupy', label: 'Gupy' },
            { id: 'linkedin', label: 'LinkedIn' },
            { id: 'indeed', label: 'Indeed' },
            { id: 'infojobs', label: 'InfoJobs' },
            { id: 'infojobs_geo', label: 'InfoJobs (Geo)' },
            { id: 'empregope', label: 'Emprego PE' },
            { id: 'comunidadeempregope', label: 'Comunidade PE' },
            { id: 'blogspot_pe', label: 'Blogspot PE' },
            { id: 'google_news', label: 'Google News' },
            { id: 'jobrapido', label: 'Jobrapido' }
        ];

        let vagasAtuais = [];

        document.addEventListener('DOMContentLoaded', () => {
            inicializarPlataformasForm();
            carregarConfiguracoes();
            carregarVagasDoCache();
            
            // Vincular abas do menu superior
            const btnVagas = document.getElementById('btn-tab-vagas');
            const btnConfig = document.getElementById('btn-tab-config');
            if (btnVagas) btnVagas.addEventListener('click', () => switchTab('vagas'));
            if (btnConfig) btnConfig.addEventListener('click', () => switchTab('config'));
            
            // Vincular botões de ação do cabeçalho
            const btnColeta = document.getElementById('btn-executar-coleta');
            const btnLimpar = document.getElementById('btn-limpar-vagas');
            if (btnColeta) btnColeta.addEventListener('click', executarColeta);
            if (btnLimpar) btnLimpar.addEventListener('click', confirmarLimparVagas);
            
            // Vincular campos de filtro
            const filtroCidade = document.getElementById('filtro-cidade');
            const filtroDataInicio = document.getElementById('data-inicio');
            const filtroDataFim = document.getElementById('data-fim');
            const btnResetar = document.getElementById('btn-resetar-filtros');
            
            if (filtroCidade) filtroCidade.addEventListener('input', filtrarVagas);
            if (filtroDataInicio) filtroDataInicio.addEventListener('change', filtrarVagas);
            if (filtroDataFim) filtroDataFim.addEventListener('change', filtrarVagas);
            if (btnResetar) btnResetar.addEventListener('click', limparFiltro);
            
            // Vincular formulário de configuração
            const formConfig = document.getElementById('config-form');
            if (formConfig) formConfig.addEventListener('submit', salvarConfig);
            
            const params = new URLSearchParams(window.location.search);
            if (params.get('tab') === 'config' || window.location.hash === '#config') {
                switchTab('config');
            }
        });

        function switchTab(tabId) {
            document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            
            if (tabId === 'vagas') {
                const viewVagas = document.getElementById('view-vagas');
                const btnVagas = document.getElementById('btn-tab-vagas');
                if (viewVagas) viewVagas.classList.add('active');
                if (btnVagas) btnVagas.classList.add('active');
            } else if (tabId === 'config') {
                const viewConfig = document.getElementById('view-config');
                const btnConfig = document.getElementById('btn-tab-config');
                if (viewConfig) viewConfig.classList.add('active');
                if (btnConfig) btnConfig.classList.add('active');
            }
        }

        function inicializarPlataformasForm() {
            const container = document.getElementById('platforms-container');
            if (!container) return;
            container.innerHTML = '';
            
            PLATAFORMAS_DISPONIVEIS.forEach(p => {
                const label = document.createElement('label');
                label.className = 'platform-card';
                label.innerHTML = `
                    <input type="checkbox" name="plataformas" value="${p.id}">
                    <span>${p.label}</span>
                `;
                container.appendChild(label);
            });
        }

        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            if (!container) return;
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            
            toast.innerHTML = `<span class="toast-text">${message}</span>`;
            
            container.appendChild(toast);
            toast.offsetHeight;
            toast.classList.add('show');
            
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }, 4000);
        }

        async function carregarConfiguracoes() {
            try {
                const res = await fetch('/api/config');
                if (!res.ok) throw new Error('Não foi possível carregar as configurações do servidor.');
                
                const data = await res.json();
                
                if (data) {
                    const elKeywords = document.getElementById('keywords');
                    const elLocalizacao = document.getElementById('localizacao');
                    const elMaxVagas = document.getElementById('max_vagas');
                    const elDelay = document.getElementById('delay');
                    
                    if (elKeywords) elKeywords.value = (data.keywords || []).join(String.fromCharCode(10));
                    if (elLocalizacao) elLocalizacao.value = data.localizacao || 'Recife, PE';
                    if (elMaxVagas) elMaxVagas.value = data.max_vagas_por_plataforma || 20;
                    if (elDelay) elDelay.value = data.delay_entre_requisicoes || 2.5;
                    
                    const checks = document.querySelectorAll('input[name="plataformas"]');
                    const ativas = data.plataformas || [];
                    checks.forEach(chk => {
                        chk.checked = ativas.includes(chk.value);
                    });
                }
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function salvarConfig(event) {
            if (event) event.preventDefault();
            
            const elKeywords = document.getElementById('keywords');
            const elLocalizacao = document.getElementById('localizacao');
            const elMaxVagas = document.getElementById('max_vagas');
            const elDelay = document.getElementById('delay');
            
            const keywordsText = elKeywords ? elKeywords.value : '';
            const keywords = keywordsText.split(String.fromCharCode(10)).map(k => k.replace(String.fromCharCode(13), '').trim()).filter(k => k);
            const localizacao = elLocalizacao ? elLocalizacao.value : '';
            const max_vagas = elMaxVagas ? (parseInt(elMaxVagas.value, 10) || 20) : 20;
            const delay = elDelay ? (parseFloat(elDelay.value) || 2.5) : 2.5;
            
            const plataformas = [];
            document.querySelectorAll('input[name="plataformas"]:checked').forEach(chk => {
                plataformas.push(chk.value);
            });
            
            const payload = {
                keywords,
                localizacao,
                max_vagas,
                delay,
                plataformas
            };
            
            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const data = await res.json();
                if (data.status === 'success') {
                    showToast(data.message || 'Configurações salvas!');
                } else {
                    throw new Error(data.message || 'Erro desconhecido ao salvar.');
                }
            } catch (err) {
                showToast(err.message, 'error');
            }
        }

        async function carregarVagasDoCache() {
            try {
                const res = await fetch('/api/vagas');
                if (res.ok) {
                    const data = await res.json();
                    vagasAtuais = data.vagas || [];
                    renderizarVagas(vagasAtuais);
                }
            } catch (e) {
                console.error('Erro ao ler vagas do cache do servidor:', e);
            }
        }

        function renderizarVagas(vagas) {
            const container = document.getElementById('vagas-container');
            if (!container) return;
            container.innerHTML = '';
            
            // Atualiza estatísticas
            const elStatTotal = document.getElementById('stat-total');
            const elStatCategories = document.getElementById('stat-categories');
            const elStatPlatforms = document.getElementById('stat-platforms');
            
            if (elStatTotal) elStatTotal.innerText = vagas ? vagas.length : 0;
            
            if (!vagas || vagas.length === 0) {
                if (elStatCategories) elStatCategories.innerText = 0;
                if (elStatPlatforms) elStatPlatforms.innerText = 0;
                container.innerHTML = `
                    <div class="empty-state">
                        <h3 class="empty-title">Sem vagas no cache</h3>
                        <p>Configure seus critérios e clique em "Executar Coleta" para buscar vagas.</p>
                    </div>
                `;
                return;
            }
            
            const categorias = {};
            const plataformas = new Set();
            vagas.forEach(v => {
                const cat = v.categoria || 'Outros';
                if (!categorias[cat]) categorias[cat] = [];
                categorias[cat].push(v);
                if (v.plataforma) plataformas.add(v.plataforma);
            });
            
            if (elStatCategories) elStatCategories.innerText = Object.keys(categorias).length;
            if (elStatPlatforms) elStatPlatforms.innerText = plataformas.size;
            
            Object.keys(categorias).sort().forEach(cat => {
                const vagasGrupo = categorias[cat];
                
                const section = document.createElement('div');
                section.className = 'categoria-section';
                section.id = `cat-${cat.toLowerCase().replace(/[^a-z0-9]/g, '-')}`;
                
                section.innerHTML = `
                    <div class="categoria-title">
                        <span>${cat}</span>
                        <span class="categoria-badge">${vagasGrupo.length}</span>
                    </div>
                    <div class="vagas-list"></div>
                `;
                
                const list = section.querySelector('.vagas-list');
                if (!list) return;
                
                vagasGrupo.forEach(v => {
                    const card = document.createElement('div');
                    card.className = 'vaga-card';
                    
                    let dataText = '';
                    if (v.data_coleta) {
                        dataText = `Coleta: ${v.data_coleta}`;
                    } else if (v.data_busca) {
                        dataText = `Busca: ${v.data_busca}`;
                    } else if (v.data_postagem) {
                        dataText = `Postada: ${v.data_postagem.substring(0, 10)}`;
                    }
                    
                    const dataAttr = v.data_coleta ? v.data_coleta.substring(0, 10) : (v.data_postagem ? v.data_postagem.substring(0, 10) : '9999-12-31');
                    card.dataset.data = dataAttr;
                    card.dataset.cidade = (v.localizacao || '').toLowerCase();
                    
                    const platformLower = (v.plataforma || 'other').toLowerCase();
                    let badgeClass = `badge-${platformLower}`;
                    if (!['gupy', 'linkedin', 'indeed', 'infojobs', 'infojobs_geo', 'empregope', 'comunidadeempregope', 'blogspot_pe', 'google_news', 'jobrapido'].includes(platformLower)) {
                        badgeClass = 'badge-other';
                    }
                    
                    card.innerHTML = `
                        <div class="vaga-header">
                            <h4 class="vaga-titulo">${v.titulo}</h4>
                            <span class="vaga-platform-badge ${badgeClass}">${v.plataforma}</span>
                        </div>
                        <div class="vaga-body">
                            <div class="vaga-detalhe">Empresa: <strong>${v.empresa || 'Não informada'}</strong></div>
                            <div class="vaga-detalhe">Localização: <strong>${v.localizacao || 'Não informada'}</strong></div>
                            ${v.salario ? `<div class="vaga-detalhe">Salário: <strong>${v.salario}</strong></div>` : ''}
                        </div>
                        <div class="vaga-footer">
                            <span class="vaga-data-badge">${dataText}</span>
                            <a href="${v.url}" target="_blank" class="vaga-link">Acessar Vaga</a>
                        </div>
                    `;
                    
                    list.appendChild(card);
                });
                
                container.appendChild(section);
            });
        }

        function filtrarVagas() {
            const elFiltroCidade = document.getElementById('filtro-cidade');
            const elDataInicio = document.getElementById('data-inicio');
            const elDataFim = document.getElementById('data-fim');
            
            const cidadeTermo = elFiltroCidade ? elFiltroCidade.value.toLowerCase().trim() : '';
            const dataInicio = elDataInicio ? elDataInicio.value : '';
            const dataFim = elDataFim ? elDataFim.value : '';
            
            document.querySelectorAll('.vaga-card').forEach(card => {
                const cidadeVaga = (card.dataset.cidade || '').toLowerCase();
                const dataVaga = card.dataset.data || '';
                
                let matchesCidade = !cidadeTermo || cidadeVaga.includes(cidadeTermo);
                
                let matchesData = true;
                if (dataInicio || dataFim) {
                    if (dataInicio && dataVaga < dataInicio) matchesData = false;
                    if (dataFim && dataVaga > dataFim) matchesData = false;
                }
                
                card.style.display = (matchesCidade && matchesData) ? '' : 'none';
            });
            
            document.querySelectorAll('.categoria-section').forEach(section => {
                const visiveis = [...section.querySelectorAll('.vaga-card')].some(c => c.style.display !== 'none');
                section.style.display = visiveis ? '' : 'none';
            });
        }

        function limparFiltro() {
            const elFiltroCidade = document.getElementById('filtro-cidade');
            const elDataInicio = document.getElementById('data-inicio');
            const elDataFim = document.getElementById('data-fim');
            
            if (elFiltroCidade) elFiltroCidade.value = '';
            if (elDataInicio) elDataInicio.value = '';
            if (elDataFim) elDataFim.value = '';
            
            document.querySelectorAll('.vaga-card').forEach(card => card.style.display = '');
            document.querySelectorAll('.categoria-section').forEach(section => section.style.display = '');
        }

        async function executarColeta() {
            const loader = document.getElementById('loader');
            if (loader) loader.classList.add('active');
            
            try {
                const res = await fetch('/api/run');
                if (!res.ok) throw new Error('Falha no processo de coleta do servidor.');
                
                const data = await res.json();
                
                if (data.status === 'success') {
                    vagasAtuais = data.vagas || [];
                    renderizarVagas(vagasAtuais);
                    switchTab('vagas');
                    showToast(`Busca concluída! ${vagasAtuais.length} vaga(s) salvas no cache.`);
                } else {
                    throw new Error(data.message || 'Erro desconhecido na coleta.');
                }
            } catch (err) {
                showToast(err.message, 'error');
            } finally {
                if (loader) loader.classList.remove('active');
            }
        }

        function confirmarLimparVagas() {
            if (confirm('Tem certeza de que deseja limpar o histórico de vagas do cache?')) {
                limparVagasBackend();
            }
        }

        async function limparVagasBackend() {
            vagasAtuais = [];
            renderizarVagas([]);
            limparFiltro();
            
            try {
                const res = await fetch('/api/clear');
                if (!res.ok) throw new Error('Não foi possível limpar o histórico de vagas no servidor.');
                
                const data = await res.json();
                if (data.status === 'success') {
                    showToast(data.message || 'Busca excluída do cache com sucesso!');
                } else {
                    throw new Error(data.message || 'Erro ao limpar no servidor.');
                }
            } catch (err) {
                showToast(err.message, 'error');
            }
        }
    </script>
</body>
</html>"""


# --- ROTAS E API ---

@app.get('/favicon.ico')
def favicon() -> Response:
    return Response(status_code=204)

@app.get('/buscaempregofacil.png')
def get_logo():
    """Serve a logo buscaempregofacil.png se existir localmente."""
    logo_path = BASE_DIR / "config" / "buscaempregofacil.png"
    if logo_path.exists():
        return FileResponse(logo_path)
    user_icon = Path.home() / ".local" / "share" / "icons" / "buscaempregofacil.png"
    if user_icon.exists():
        return FileResponse(user_icon)
    return Response(status_code=404)

@app.get('/', response_class=HTMLResponse)
def index():
    """Retorna a interface do frontend unificada (HTML)."""
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return HTMLResponse(content=INDEX_HTML, headers=headers)

@app.get('/config')
def config_redirect():
    """Redireciona para a aba de configurações no frontend."""
    return RedirectResponse("/?tab=config", status_code=303)

@app.get('/api/config')
def get_config_api():
    """Retorna as configurações atuais em formato JSON."""
    return carregar_config()

@app.post('/api/config')
async def save_config_api(request: Request):
    """Salva novas configurações enviadas pelo frontend."""
    try:
        config_data = await request.json()
        keywords_raw = config_data.get('keywords', '')
        
        if isinstance(keywords_raw, str):
            keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]
        else:
            keywords = [k.strip() for k in keywords_raw if k.strip()]
            
        new_config = {
            'keywords': keywords,
            'localizacao': config_data.get('localizacao', ''),
            'max_vagas_por_plataforma': int(config_data.get('max_vagas', 20)),
            'delay_entre_requisicoes': float(config_data.get('delay', 2.5)),
            'plataformas': config_data.get('plataformas', []),
        }
        salvar_config(new_config)
        return {"status": "success", "message": "Configuração salva com sucesso!"}
    except Exception as exc:
        return {"status": "error", "message": f"Erro ao salvar configuração: {exc}"}

@app.get('/api/run')
def run_api():
    """Executa a busca de vagas e salva no cache em memória."""
    try:
        cfg = carregar_config()
        vagas_objs = executar_busca(cfg)
        vagas_objs = categorize_vagas(vagas_objs, cfg.get('keywords', []))
        
        global VAGAS_CACHE
        VAGAS_CACHE = [v.to_dict() for v in vagas_objs]
        
        return {"status": "success", "vagas": VAGAS_CACHE}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.get('/api/vagas')
def get_vagas_api():
    """Retorna a lista de vagas armazenada no cache em memória."""
    global VAGAS_CACHE
    return {"status": "success", "vagas": VAGAS_CACHE}

@app.get('/api/clear')
def clear_api():
    """Limpa o cache de vagas em memória."""
    try:
        global VAGAS_CACHE
        VAGAS_CACHE = []
        return {"status": "success", "message": "Cache de vagas em memória limpo com sucesso!"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# --- UNIFIED ENTRYPOINT (CLI & WEB SERVER) ---

def configurar_desktop() -> None:
    """Configura o ícone e o arquivo desktop do usuário no sistema."""
    import shutil
    try:
        user_home = Path.home()
        apps_dir = user_home / ".local" / "share" / "applications"
        icons_dir = user_home / ".local" / "share" / "icons"
        
        apps_dir.mkdir(parents=True, exist_ok=True)
        icons_dir.mkdir(parents=True, exist_ok=True)
        
        src_icon = BASE_DIR / "config" / "buscaempregofacil.png"
        dst_icon = icons_dir / "buscaempregofacil.png"
        
        if src_icon.exists():
            shutil.copy2(src_icon, dst_icon)
        
        src_desktop = BASE_DIR / "config" / "buscaempregofacil.desktop"
        dst_desktop = apps_dir / "buscaempregofacil.desktop"
        
        if src_desktop.exists():
            uv_path = shutil.which("uv")
            if not uv_path:
                local_uv = user_home / ".local" / "bin" / "uv"
                if local_uv.exists():
                    uv_path = str(local_uv)
                else:
                    uv_path = "uv"
            
            main_py_path = BASE_DIR / "main.py"
            desktop_content = src_desktop.read_text(encoding="utf-8")
            
            novas_linhas = []
            for line in desktop_content.splitlines():
                if line.startswith("Exec="):
                    novas_linhas.append(f"Exec={uv_path} run \"{main_py_path}\"")
                elif line.startswith("Icon="):
                    novas_linhas.append(f"Icon={dst_icon}")
                elif line.startswith("Name="):
                    novas_linhas.append("Name=Busca Emprego Fácil")
                elif line.startswith("StartupWMClass="):
                    novas_linhas.append("StartupWMClass=buscaempregofacil")
                else:
                    novas_linhas.append(line)
            
            dst_desktop.write_text("\n".join(novas_linhas), encoding="utf-8")
            dst_desktop.chmod(0o755)
            
    except Exception as exc:
        sys.stderr.write(f"Aviso: Erro ao configurar desktop/ícone: {exc}\n")

def main() -> None:
    """Entrypoint unificado: executa em modo CLI ou Web Server."""
    configurar_desktop()
    parser = argparse.ArgumentParser(description="Busca Emprego Fácil — Painel e Scraper Unificados")
    parser.add_argument("--cli", action="store_true", help="Executar coleta via linha de comando")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE, help="Caminho para config JSON")
    parser.add_argument("--host", type=str, default=os.getenv("HOST", "127.0.0.1"), help="Host do servidor")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", 8000)), help="Porta do servidor")
    args = parser.parse_args()

    if args.cli:
        # Modo CLI
        bootstrap()
        cfg = carregar_config()
        
        section("CONFIGURAÇÃO CLI")
        log(f"Keywords   : {cfg['keywords']}")
        log(f"Localização: {cfg['localizacao']}")
        log(f"Plataformas: {cfg.get('plataformas', [])}")
        log(f"Max/plat.  : {cfg['max_vagas_por_plataforma']}")
        log(f"Sem filtro : {sorted(PLATAFORMAS_SEM_FILTRO_GEO)} (nacional — filtro no JS)")
        log(f"Log        : {LOG_FILE}")

        vagas = executar_busca(cfg)
        vagas = categorize_vagas(vagas, cfg["keywords"])

        section("RESULTADO FINAL CLI")
        if vagas:
            success(f"Total de vagas únicas: {len(vagas)}")
            por_plat = {}
            for v in vagas:
                por_plat[v.plataforma] = por_plat.get(v.plataforma, 0) + 1
            for plat, qtd in sorted(por_plat.items(), key=lambda x: -x[1]):
                tipo = "[Nacional]" if plat in PLATAFORMAS_SEM_FILTRO_GEO else "[Local]"
                log(f"   {tipo} {plat:<12}: {qtd} vagas")

            json_out = get_json_out()
            salvar_json_hunter(vagas, json_out)
            success(f"JSON salvo em: {json_out}")
        else:
            warn("Nenhuma vaga coletada. Verifique config_vagas.json e o log.")
    else:
        # Modo Servidor Web (Janela Nativa Webview com fallback para Navegador)
        def rodar_fastapi():
            uvicorn.run(app, host=args.host, port=args.port, log_level='info')

        try:
            import webview
            print(f"\nIniciando interface nativa do Busca Emprego Fácil (janela local)...")
            
            # Thread para rodar o FastAPI em background
            t_api = threading.Thread(target=rodar_fastapi, daemon=True)
            t_api.start()
            
            # Aguarda o servidor subir
            time.sleep(0.5)
            
            # Configuração de Ícone e Desktop no Qt6 para que o ícone apareça no dock do sistema
            try:
                from PyQt6.QtCore import Qt, QCoreApplication
                # Define compartilhamento de contexto OpenGL antes de instanciar a aplicação
                QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
                # Nome do app correspondendo ao StartupWMClass do atalho desktop
                QCoreApplication.setApplicationName("buscaempregofacil")
                
                # Importação preventiva exigida pelo QtWebEngine
                import PyQt6.QtWebEngineWidgets
                
                from PyQt6.QtGui import QGuiApplication, QIcon
                from PyQt6.QtWidgets import QApplication
                
                app_qt = QApplication.instance()
                if not app_qt:
                    app_qt = QApplication(sys.argv)
                
                user_home = Path.home()
                dst_icon = user_home / ".local" / "share" / "icons" / "buscaempregofacil.png"
                if dst_icon.exists():
                    app_qt.setWindowIcon(QIcon(str(dst_icon)))
                
                # Nome do arquivo desktop sem o sufixo .desktop para evitar warnings
                QGuiApplication.setDesktopFileName("buscaempregofacil")
                QGuiApplication.setApplicationDisplayName("Busca Emprego Fácil")
            except Exception as eqt:
                sys.stderr.write(f"Aviso ao configurar Qt6 Window Icon: {eqt}\n")
            
            # Cria a janela e inicia o loop GUI
            webview.create_window("Busca Emprego Fácil", f"http://{args.host}:{args.port}", width=1000, height=700)
            webview.start()
        except Exception as e:
            print(f"\nNão foi possível abrir a janela nativa ({e}).")
            print(f"Fazendo fallback: abrindo no navegador padrão do sistema...")
            
            import webbrowser
            def abrir_navegador():
                time.sleep(0.5)
                webbrowser.open(f"http://{args.host}:{args.port}")
                
            t_nav = threading.Thread(target=abrir_navegador, daemon=True)
            t_nav.start()
            
            # Aguarda a thread do uvicorn (que já foi iniciada em t_api.start()) terminar
            t_api.join()

if __name__ == '__main__':
    main()
