#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Academic Citation Manager - 学术引用管理器
专业的科研论文引用管理工具，支持多种引用格式和Crossref API集成
"""

import re
import json
import requests
import hashlib
import time
import argparse
from typing import Dict, List, Optional, Union, Any, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CitationStyle(Enum):
    """引用格式枚举"""
    APA = "apa"
    MLA = "mla"
    CHICAGO = "chicago"
    CHICAGO_AUTHOR_DATE = "chicago-author-date"
    GBT7714 = "gbt7714"
    IEEE = "ieee"
    HARVARD = "harvard"
    BIBTEX = "bibtex"


class DocumentType(Enum):
    """文献类型枚举"""
    JOURNAL = "journal_article"
    BOOK = "book"
    CONFERENCE = "conference_paper"
    THESIS = "thesis"
    REPORT = "report"
    NEWSPAPER = "newspaper_article"
    WEBPAGE = "webpage"


class ChineseDocumentType(Enum):
    """中文文献类型枚举（GB/T 7714）"""
    MONOGRAPH = "[M]"
    JOURNAL_ARTICLE = "[J]"
    CONFERENCE_PAPER = "[C]"
    DISSERTATION = "[D]"
    REPORT = "[R]"
    NEWSPAPER = "[N]"
    STANDARD = "[S]"
    PATENT = "[P]"
    DATABASE = "[DB]"
    COMPILER = "[CP]"


@dataclass
class Author:
    """作者信息"""
    given: str
    family: str
    sequence: str = "additional"
    orcid: Optional[str] = None
    affiliation: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.family} {self.given}"

    def format_name(self, style: CitationStyle = CitationStyle.APA) -> str:
        """格式化作者姓名"""
        if style == CitationStyle.GBT7714:
            return f"{self.family}{self.given}"
        elif style in [CitationStyle.IEEE, CitationStyle.CHICAGO]:
            return f"{self.family}, {self.given[0]}"
        elif style == CitationStyle.MLA:
            return f"{self.family}, {self.given}"
        else:
            return f"{self.family}, {self.given[0]}."


@dataclass
class Reference:
    """参考文献信息"""
    id: str
    type: str
    title: str
    authors: List[Author]
    year: int
    doi: Optional[str] = None
    isbn: Optional[str] = None
    container_title: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    page: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None
    published_date: Optional[str] = None
    language: str = "en"
    tags: List[str] = field(default_factory=list)
    abstract: Optional[str] = None
    issn: Optional[List[str]] = None

    def __post_init__(self):
        """初始化后处理"""
        if not self.id:
            self.id = self._generate_id()

    def _generate_id(self) -> str:
        """生成唯一ID"""
        content = f"{self.title}_{self.year}"
        if self.doi:
            content += f"_{self.doi}"
        elif self.isbn:
            content += f"_{self.isbn}"
        return f"ref_{hashlib.md5(content.encode()).hexdigest()[:8]}"

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'authors': [
                {'given': a.given, 'family': a.family, 'sequence': a.sequence}
                for a in self.authors
            ],
            'year': self.year,
            'doi': self.doi,
            'isbn': self.isbn,
            'container_title': self.container_title,
            'volume': self.volume,
            'issue': self.issue,
            'page': self.page,
            'publisher': self.publisher,
            'url': self.url,
            'published_date': self.published_date,
            'language': self.language,
            'tags': self.tags,
            'abstract': self.abstract,
            'issn': self.issn
        }


class BaseCitationFormatter(ABC):
    """引用格式化器基类"""

    @abstractmethod
    def format_in_text_citation(self, reference: Reference,
                                citation_type: str = "parenthetical",
                                page: Optional[str] = None) -> str:
        """格式化文中引用"""
        pass

    @abstractmethod
    def format_bibliography_entry(self, reference: Reference) -> str:
        """格式化参考文献条目"""
        pass


class APAFormatter(BaseCitationFormatter):
    """APA 7th Edition格式化器"""

    def format_in_text_citation(self, reference: Reference,
                                citation_type: str = "parenthetical",
                                page: Optional[str] = None) -> str:
        if not reference.authors:
            return "Unknown"

        first_author = reference.authors[0]
        authors_count = len(reference.authors)

        if citation_type == "parenthetical":
            if authors_count == 1:
                citation = f"({first_author.family}, {reference.year})"
            elif authors_count == 2:
                second_author = reference.authors[1]
                citation = f"({first_author.family} & {second_author.family}, {reference.year})"
            else:
                citation = f"({first_author.family} et al., {reference.year})"
        else:
            citation = f"{first_author.family} ({reference.year})"

        if page:
            citation = f"{citation[:-1]}, p. {page})"
        
        return citation

    def format_bibliography_entry(self, reference: Reference) -> str:
        authors_text = self._format_authors(reference.authors)
        year = reference.year
        title = reference.title

        if reference.type == "journal_article":
            entry = f"{authors_text} ({year}). {title}. {reference.container_title}, {reference.volume}({reference.issue}), {reference.page}."
            if reference.doi:
                entry += f" https://doi.org/{reference.doi}"
        elif reference.type == "book":
            entry = f"{authors_text} ({year}). {title}. {reference.publisher}."
        elif reference.type == "conference_paper":
            entry = f"{authors_text} ({year}). {title}. In {reference.container_title} (pp. {reference.page}). {reference.publisher}."
        else:
            entry = f"{authors_text} ({year}). {title}. {reference.container_title}."

        return entry

    def _format_authors(self, authors: List[Author]) -> str:
        if not authors:
            return "Unknown"
        
        if len(authors) == 1:
            return f"{authors[0].family}, {authors[0].given[0]}."
        elif len(authors) == 2:
            return f"{authors[0].family}, {authors[0].given[0]}., & {authors[1].family}, {authors[1].given[0]}."
        elif len(authors) <= 7:
            formatted = ", ".join([f"{a.family}, {a.given[0]}." for a in authors[:-1]])
            formatted += f", & {authors[-1].family}, {authors[-1].given[0]}."
            return formatted
        else:
            return f"{authors[0].family}, {authors[0].given[0]}., et al."


class MLAFormatter(BaseCitationFormatter):
    """MLA 9th Edition格式化器"""

    def format_in_text_citation(self, reference: Reference,
                                citation_type: str = "parenthetical",
                                page: Optional[str] = None) -> str:
        if not reference.authors:
            return "Unknown"

        first_author = reference.authors[0]
        authors_count = len(reference.authors)
        year_short = str(reference.year)[-2:]

        if authors_count == 1:
            citation = f"({first_author.family} {year_short})"
        elif authors_count <= 3:
            authors_text = "-".join([f"{a.family}" for a in reference.authors])
            citation = f"({authors_text} {year_short})"
        else:
            citation = f"({first_author.family} et al. {year_short})"

        if page:
            citation = f"{citation[:-1]}, {page})"

        return citation

    def format_bibliography_entry(self, reference: Reference) -> str:
        authors_text = self._format_authors(reference.authors)
        title = f'"{reference.title}"'
        year = reference.year

        if reference.type == "journal_article":
            entry = f"{authors_text}. {title}. {reference.container_title}, vol. {reference.volume}, no. {reference.issue}, {year}, pp. {reference.page}."
        elif reference.type == "book":
            entry = f"{authors_text}. {title}. {reference.publisher}, {year}."
        else:
            entry = f"{authors_text}. {title}. {reference.container_title}, {year}."

        return entry

    def _format_authors(self, authors: List[Author]) -> str:
        if not authors:
            return "Unknown"
        
        if len(authors) <= 3:
            return ", ".join([f"{a.family}, {a.given}" for a in authors])
        else:
            return f"{authors[0].family}, {authors[0].given}, et al."


class ChicagoFormatter(BaseCitationFormatter):
    """Chicago 17th Edition格式化器"""

    def format_in_text_citation(self, reference: Reference,
                                citation_type: str = "parenthetical",
                                page: Optional[str] = None) -> str:
        if not reference.authors:
            return "Unknown"

        first_author = reference.authors[0]
        authors_count = len(reference.authors)

        if citation_type == "notes":
            citation = f"{first_author.family}, {reference.title}"
            if page:
                citation += f", {page}"
            citation += "."
        else:
            if authors_count == 1:
                citation = f"({first_author.family} {reference.year})"
                if page:
                    citation = f"{citation[:-1]}, {page})"
            else:
                citation = f"({first_author.family} et al. {reference.year})"
                if page:
                    citation = f"{citation[:-1]}, {page})"

        return citation

    def format_bibliography_entry(self, reference: Reference) -> str:
        authors_text = self._format_authors(reference.authors)
        year = reference.year
        title = f'"{reference.title}"'

        if reference.type == "journal_article":
            entry = f"{authors_text}. {year}. {title}. {reference.container_title} {reference.volume}, no. {reference.issue} (p. {reference.page})."
        elif reference.type == "book":
            entry = f"{authors_text}. {year}. {title}. {reference.publisher}: {reference.page}."
        else:
            entry = f"{authors_text}. {year}. {title}. {reference.container_title}."

        return entry

    def _format_authors(self, authors: List[Author]) -> str:
        if not authors:
            return "Unknown"
        
        if len(authors) == 1:
            return f"{authors[0].family}, {authors[0].given}"
        elif len(authors) <= 3:
            return ", ".join([f"{a.family}, {a.given}" for a in authors])
        else:
            return f"{authors[0].family}, {authors[0].given}, et al."


class IEEEFormatter(BaseCitationFormatter):
    """IEEE格式化器"""

    def format_in_text_citation(self, reference: Reference,
                                citation_type: str = "parenthetical",
                                page: Optional[str] = None) -> str:
        return f"[{reference.id}]"

    def format_bibliography_entry(self, reference: Reference) -> str:
        authors_text = self._format_authors(reference.authors)
        year = reference.year
        title = f'"{reference.title}"'

        if reference.type == "journal_article":
            entry = f"[{reference.id}] {authors_text}, {title}, {reference.container_title}, vol. {reference.volume}, no. {reference.issue}, pp. {reference.page}, {year}."
        elif reference.type == "book":
            entry = f"[{reference.id}] {authors_text}, {title}. {reference.publisher}, {year}."
        elif reference.type == "conference_paper":
            entry = f"[{reference.id}] {authors_text}, {title}, in {reference.container_title}, {year}, pp. {reference.page}."
        else:
            entry = f"[{reference.id}] {authors_text}, {title}. {reference.container_title}, {year}."

        return entry

    def _format_authors(self, authors: List[Author]) -> str:
        if not authors:
            return "Unknown"
        
        author_list = ", ".join([f"{a.family} {a.given[0]}." for a in authors[:3]])
        if len(authors) > 3:
            author_list += ", et al."
        return author_list


class GBT7714Formatter(BaseCitationFormatter):
    """GB/T 7714-2015格式化器（中文文献）"""

    def __init__(self):
        """初始化格式化器"""
        self.type_codes = {
            "book": ChineseDocumentType.MONOGRAPH.value,
            "journal_article": ChineseDocumentType.JOURNAL_ARTICLE.value,
            "conference_paper": ChineseDocumentType.CONFERENCE_PAPER.value,
            "thesis": ChineseDocumentType.DISSERTATION.value,
            "report": ChineseDocumentType.REPORT.value,
            "newspaper_article": ChineseDocumentType.NEWSPAPER.value,
            "standard": ChineseDocumentType.STANDARD.value,
            "patent": ChineseDocumentType.PATENT.value,
            "database": ChineseDocumentType.DATABASE.value,
            "compiler": ChineseDocumentType.COMPILER.value
        }

    def format_in_text_citation(self, reference: Reference,
                                citation_type: str = "parenthetical",
                                page: Optional[str] = None) -> str:
        if not reference.authors:
            return "Unknown"

        first_author = reference.authors[0]
        authors_count = len(reference.authors)

        if citation_type == "numeric":
            return f"[{reference.id}]"
        else:
            if authors_count == 1:
                citation = f"({first_author.family}, {reference.year})"
            elif authors_count <= 3:
                authors_text = ",".join([f"{a.family}" for a in reference.authors])
                citation = f"({authors_text}, {reference.year})"
            else:
                citation = f"({first_author.family} et al., {reference.year})"
            
            if page:
                citation = f"{citation[:-1]}, {page})"
            
            return citation

    def format_bibliography_entry(self, reference: Reference) -> str:
        authors_text = self._format_chinese_authors(reference.authors)
        year = reference.year
        title = reference.title
        type_code = self.type_codes.get(reference.type, "")

        if reference.type == "journal_article":
            entry = f"{authors_text}. {title}{type_code}. {reference.container_title}, {year}, {reference.volume}({reference.issue}): {reference.page}."
        elif reference.type == "book":
            entry = f"{authors_text}. {title}{type_code}. {reference.publisher}, {year}: {reference.page}."
        elif reference.type == "conference_paper":
            entry = f"{authors_text}. {title}{type_code}. // {reference.container_title}, {year}, {reference.page}."
        elif reference.type == "thesis":
            entry = f"{authors_text}. {title}{type_code}. {reference.container_title}, {year}."
        elif reference.type == "report":
            entry = f"{authors_text}. {title}{type_code}. {reference.container_title}, {year}."
        elif reference.type == "standard":
            entry = f"{title}{type_code}. {reference.container_title}, {year}."
        elif reference.type == "patent":
            entry = f"{title}{type_code}. {reference.container_title}, {year}."
        else:
            entry = f"{authors_text}. {title}{type_code}. {reference.container_title}, {year}."

        if reference.doi:
            entry += f" doi: {reference.doi}."
        if reference.url:
            entry += f" {reference.url}."

        return entry

    def _format_chinese_authors(self, authors: List[Author]) -> str:
        if not authors:
            return "Unknown"
        
        formatted = ",".join([f"{a.family}{a.given}" for a in authors])
        return formatted


class HarvardFormatter(BaseCitationFormatter):
    """Harvard格式化器"""

    def format_in_text_citation(self, reference: Reference,
                                citation_type: str = "parenthetical",
                                page: Optional[str] = None) -> str:
        if not reference.authors:
            return "Unknown"

        first_author = reference.authors[0]

        citation = f"({first_author.family}, {reference.year}"
        if page:
            citation = f"{citation}, p. {page})"

        return citation

    def format_bibliography_entry(self, reference: Reference) -> str:
        authors_text = self._format_authors(reference.authors)
        year = reference.year
        title = reference.title

        if reference.type == "journal_article":
            entry = f"{authors_text} ({year}) '{reference.title}', {reference.container_title}, {reference.volume}({reference.issue}), p. {reference.page}."
        elif reference.type == "book":
            entry = f"{authors_text} ({year}) {title}. {reference.publisher}."
        else:
            entry = f"{authors_text} ({year}) '{title}', {reference.container_title}."

        return entry

    def _format_authors(self, authors: List[Author]) -> str:
        if not authors:
            return "Unknown"
        
        if len(authors) == 1:
            return f"{authors[0].family}, {authors[0].given}"
        elif len(authors) == 2:
            return f"{authors[0].family}, {authors[0].given} and {authors[1].family}, {authors[1].given}"
        elif len(authors) <= 3:
            return ", ".join([f"{a.family}, {a.given}" for a in authors])
        else:
            return f"{authors[0].family}, {authors[0].given}, et al."


class CrossrefClient:
    """Crossref API客户端"""

    def __init__(self, config_file: str = "crossref_config.json"):
        """初始化Crossref客户端"""
        self.config = self._load_config(config_file)
        self.cache = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AcademicCitationManager/1.0.0 (mailto:youstudyeveryday@example.com)'
        })
        self.last_request_time = 0
        self.min_request_interval = 0.1

    def _load_config(self, config_file: str) -> Dict:
        """加载配置文件"""
        config_path = Path(__file__).parent / config_file
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "api_base": "https://api.crossref.org",
                "rate_limit": 10,
                "cache_ttl": 86400
            }

    def _rate_limit_wait(self):
        """遵守速率限制"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()

    def fetch_by_doi(self, doi: str) -> Optional[Dict]:
        """通过DOI获取文献信息"""
        cache_key = f"doi_{doi}"
        if cache_key in self.cache:
            logger.info(f"Using cached result for DOI: {doi}")
            return self.cache[cache_key]

        self._rate_limit_wait()

        try:
            url = f"{self.config['api_base']}/works/{doi}"
            logger.info(f"Fetching DOI from: {url}")
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                result = self._parse_crossref_response(data)
                self.cache[cache_key] = result
                logger.info(f"Successfully fetched reference: {result.get('title', 'Unknown')}")
                return result
            elif response.status_code == 404:
                logger.warning(f"DOI not found: {doi}")
            else:
                logger.error(f"Failed to fetch DOI {doi}: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching DOI: {doi}")
        except Exception as e:
            logger.error(f"Error fetching DOI {doi}: {str(e)}")
        
        return None

    def search_by_title_author(self, title: str, author: str = None,
                            year: int = None, max_results: int = 10) -> List[Dict]:
        """通过标题和作者搜索文献"""
        self._rate_limit_wait()

        try:
            params = {
                'query.title': title,
                'rows': max_results,
                'select': 'doi,title,author,type,published-print,container-title,volume,issue,page,publisher,ISSN'
            }
            
            if author:
                params['query.author'] = author
            if year:
                params['filter'] = f'from-pub-date:{year},until-pub-date:{year}'

            url = f"{self.config['api_base']}/works"
            logger.info(f"Searching with params: {params}")
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('message', {}).get('items', [])
                logger.info(f"Found {len(items)} references")
                return [self._parse_crossref_response(item) for item in items[:max_results]]
            else:
                logger.error(f"Search failed: HTTP {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error searching: {str(e)}")
        
        return []

    def _parse_crossref_response(self, data: Dict) -> Dict:
        """解析Crossref API响应"""
        message = data.get('message', {})
        
        try:
            authors = []
            for item in message.get('author', []):
                author = Author(
                    given=item.get('given', ''),
                    family=item.get('family', ''),
                    sequence=item.get('sequence', 'additional')
                )
                authors.append(author)

            title = ''
            if 'title' in message and message['title']:
                title = message['title'][0]
            elif 'short-container-title' in message and message['short-container-title']:
                title = message['short-container-title'][0]

            year = datetime.now().year
            published = message.get('published-print', {})
            if 'date-parts' in published and published['date-parts']:
                year = published['date-parts'][0][0]

            return {
                'type': message.get('type', 'journal-article'),
                'title': title,
                'authors': authors,
                'year': year,
                'doi': message.get('DOI'),
                'container_title': message.get('container-title', [''])[0] if message.get('container-title') else None,
                'volume': message.get('volume'),
                'issue': message.get('issue'),
                'page': message.get('page'),
                'publisher': message.get('publisher'),
                'published_date': str(published.get('date', '')),
                'issn': message.get('ISSN'),
                'language': 'en'
            }
        except Exception as e:
            logger.error(f"Error parsing Crossref response: {str(e)}")
            return {}


class ReferenceDatabase:
    """本地文献数据库"""

    def __init__(self, db_file: str = "reference_database.json"):
        """初始化数据库"""
        self.db_file = Path(__file__).parent / db_file
        self.data = self._load_database()
        self._ensure_db_structure()

    def _ensure_db_structure(self):
        """确保数据库结构完整"""
        if 'metadata' not in self.data:
            self.data['metadata'] = {
                'version': '1.0.0',
                'created_date': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat()
            }
        if 'references' not in self.data:
            self.data['references'] = {}
        if 'citation_mappings' not in self.data:
            self.data['citation_mappings'] = {}

    def _load_database(self) -> Dict:
        """加载数据库"""
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading database: {str(e)}")
        
        return {}

    def save_database(self):
        """保存数据库"""
        self.data["metadata"]["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            logger.info(f"Database saved: {self.db_file}")
        except Exception as e:
            logger.error(f"Error saving database: {str(e)}")

    def add_reference(self, reference: Union[Reference, Dict]) -> str:
        """添加参考文献"""
        if isinstance(reference, Reference):
            ref_data = reference.to_dict()
        else:
            ref_data = reference
            
        ref_id = ref_data.get('id', '')
        if not ref_id:
            ref = Reference(**ref_data)
            ref_id = ref.id
            ref_data['id'] = ref_id
        
        self.data["references"][ref_id] = ref_data
        self.save_database()
        logger.info(f"Reference added: {ref_id}")
        return ref_id

    def get_reference(self, ref_id: str) -> Optional[Dict]:
        """获取参考文献"""
        return self.data["references"].get(ref_id)

    def get_all_references(self) -> List[Dict]:
        """获取所有参考文献"""
        return list(self.data["references"].values())

    def update_reference(self, ref_id: str, reference: Union[Reference, Dict]):
        """更新参考文献"""
        if ref_id in self.data["references"]:
            if isinstance(reference, Reference):
                ref_data = reference.to_dict()
            else:
                ref_data = reference
            self.data["references"][ref_id] = ref_data
            self.save_database()
            logger.info(f"Reference updated: {ref_id}")

    def delete_reference(self, ref_id: str):
        """删除参考文献"""
        if ref_id in self.data["references"]:
            del self.data["references"][ref_id]
            if ref_id in self.data["citation_mappings"]:
                del self.data["citation_mappings"][ref_id]
            self.save_database()
            logger.info(f"Reference deleted: {ref_id}")

    def search_references(self, query: str, field: str = "title") -> List[Dict]:
        """搜索参考文献"""
        results = []
        query_lower = query.lower()
        
        for ref in self.data["references"].values():
            if field in ref and query_lower in str(ref[field]).lower():
                results.append(ref)
                
        logger.info(f"Found {len(results)} references matching: {query}")
        return results

    def add_citation_mapping(self, ref_id: str, document_id: str, position: int):
        """添加引用映射"""
        if ref_id not in self.data["citation_mappings"]:
            self.data["citation_mappings"][ref_id] = []
        
        mapping = next((m for m in self.data["citation_mappings"][ref_id]
                      if m["document_id"] == document_id), None)
        
        if mapping:
            if position not in mapping["positions"]:
                mapping["positions"].append(position)
        else:
            self.data["citation_mappings"][ref_id].append({
                "document_id": document_id,
                "positions": [position]
            })
        
        self.save_database()

    def get_citation_count(self, ref_id: str) -> int:
        """获取引用次数"""
        mappings = self.data["citation_mappings"].get(ref_id, [])
        return sum(len(m.get("positions", [])) for m in mappings)

    def export_to_json(self, output_file: str):
        """导出为JSON格式"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        logger.info(f"Exported to JSON: {output_file}")

    def import_from_json(self, input_file: str):
        """从JSON格式导入"""
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for ref_id, ref_data in data.get('references', {}).items():
            self.data["references"][ref_id] = ref_data
        
        self.data["citation_mappings"] = data.get("citation_mappings", {})
        self.save_database()
        logger.info(f"Imported from JSON: {input_file}")


class CitationIntegrityChecker:
    """引用完整性检查器"""

    def __init__(self):
        """初始化检查器"""
        self.citation_patterns = {
            'numeric_bracket': re.compile(r'\[(\w+)\]'),
            'at_sign': re.compile(r'@(\w+)'),
            'parenthetical': re.compile(r'\(([A-Z][a-z]+,\s*\d{4})')
        }
        self.ref_pattern = re.compile(r'^\d+\.|\[\d+\]')

    def check_document(self, document_text: str,
                    bibliography: List[Dict]) -> Dict:
        """检查文档引用完整性"""
        in_text_citations = self._extract_citations(document_text)
        bib_ids = {ref['id'] for ref in bibliography}
        
        missing_in_bib = [c for c in in_text_citations if c not in bib_ids]
        unused_refs = [ref_id for ref_id in bib_ids if ref_id not in in_text_citations]
        
        report = {
            'total_citations': len(in_text_citations),
            'total_references': len(bib_ids),
            'missing_in_bibliography': missing_in_bib,
            'unused_references': unused_refs,
            'inconsistencies': len(missing_in_bib) + len(unused_refs),
            'issues': []
        }
        
        if missing_in_bib:
            report['issues'].append({
                'type': 'missing_in_bibliography',
                'count': len(missing_in_bib),
                'items': missing_in_bib
            })
        
        if unused_refs:
            report['issues'].append({
                'type': 'unused_references',
                'count': len(unused_refs),
                'items': unused_refs
            })
        
        logger.info(f"Integrity check: {report['total_citations']} citations, {report['total_references']} references")
        return report

    def _extract_citations(self, text: str) -> List[str]:
        """提取文中引用"""
        citations = []
        
        for pattern_name, pattern in self.citation_patterns.items():
            matches = pattern.findall(text)
            citations.extend(matches)
        
        return list(set(citations))


class FormatConverter:
    """格式转换器"""

    def __init__(self):
        """初始化转换器"""
        self.formatters = {
            CitationStyle.APA: APAFormatter(),
            CitationStyle.MLA: MLAFormatter(),
            CitationStyle.CHICAGO: ChicagoFormatter(),
            CitationStyle.IEEE: IEEEFormatter(),
            CitationStyle.GBT7714: GBT7714Formatter(),
            CitationStyle.HARVARD: HarvardFormatter()
        }

    def convert_reference(self, reference: Dict,
                        from_style: CitationStyle,
                        to_style: CitationStyle) -> Dict:
        """转换单个引用格式"""
        ref_obj = self._dict_to_reference(reference)
        
        from_formatter = self.formatters.get(from_style)
        to_formatter = self.formatters.get(to_style)
        
        if not to_formatter:
            raise ValueError(f"Unsupported citation style: {to_style}")
        
        original_entry = from_formatter.format_bibliography_entry(ref_obj) if from_formatter else str(reference)
        converted_entry = to_formatter.format_bibliography_entry(ref_obj)
        
        return {
            'id': reference.get('id', ''),
            'original': original_entry,
            'converted': converted_entry,
            'from_style': from_style.value,
            'to_style': to_style.value
        }

    def convert_batch(self, references: List[Dict],
                     from_style: CitationStyle,
                     to_style: CitationStyle) -> List[Dict]:
        """批量转换引用格式"""
        results = []
        for ref in references:
            try:
                result = self.convert_reference(ref, from_style, to_style)
                results.append(result)
            except Exception as e:
                logger.error(f"Error converting reference: {str(e)}")
        return results

    def _dict_to_reference(self, ref_dict: Dict) -> Reference:
        """将字典转换为Reference对象"""
        authors = []
        for author_data in ref_dict.get('authors', []):
            author = Author(
                given=author_data.get('given', ''),
                family=author_data.get('family', ''),
                sequence=author_data.get('sequence', 'additional')
            )
            authors.append(author)

        return Reference(
            id=ref_dict.get('id', ''),
            type=ref_dict.get('type', 'journal_article'),
            title=ref_dict.get('title', ''),
            authors=authors,
            year=ref_dict.get('year', datetime.now().year),
            doi=ref_dict.get('doi'),
            isbn=ref_dict.get('isbn'),
            container_title=ref_dict.get('container_title'),
            volume=ref_dict.get('volume'),
            issue=ref_dict.get('issue'),
            page=ref_dict.get('page'),
            publisher=ref_dict.get('publisher'),
            url=ref_dict.get('url'),
            published_date=ref_dict.get('published_date'),
            language=ref_dict.get('language', 'en'),
            tags=ref_dict.get('tags', []),
            abstract=ref_dict.get('abstract'),
            issn=ref_dict.get('issn')
        )

    def export_bibtex(self, references: List[Dict]) -> str:
        """导出为BibTeX格式"""
        bibtex_lines = []
        
        for ref in references:
            key = ref.get('id', 'unknown')
            entry_type = self._get_bibtex_type(ref.get('type', 'misc'))
            
            bibtex = f"@{entry_type}{{{key},\n"
            
            fields = []
            for k, v in ref.items():
                if k not in ['id', 'type']:
                    if v:
                        if k == 'authors':
                            authors = ", and ".join([f"{a.get('family', '')}, {a.get('given', '')}" 
                                                       for a in v])
                            fields.append(f"author = {{{authors}}}")
                        elif k == 'container_title':
                            fields.append(f"journal = {{{v}}}")
                        elif k == 'year':
                            fields.append(f"year = {{{v}}}")
                        else:
                            fields.append(f"{k} = {{{v}}}")
            
            bibtex += ",\n".join(fields)
            bibtex += "\n}\n\n"
            bibtex_lines.append(bibtex)
        
        return ''.join(bibtex_lines)

    def _get_bibtex_type(self, doc_type: str) -> str:
        """获取BibTeX条目类型"""
        type_mapping = {
            'journal_article': 'article',
            'book': 'book',
            'conference_paper': 'inproceedings',
            'thesis': 'phdthesis',
            'report': 'techreport',
            'newspaper_article': 'article'
        }
        return type_mapping.get(doc_type, 'misc')


class AcademicCitationManager:
    """学术引用管理器 - 主类"""

    def __init__(self, config_dir: Optional[str] = None):
        """初始化管理器"""
        if config_dir:
            config_path = Path(config_dir)
        else:
            config_path = Path(__file__).parent

        self.crossref_client = CrossrefClient(str(config_path / "crossref_config.json"))
        self.database = ReferenceDatabase(str(config_path / "reference_database.json"))
        self.checker = CitationIntegrityChecker()
        self.converter = FormatConverter()
        logger.info("AcademicCitationManager initialized")

    def fetch_reference_by_doi(self, doi: str) -> Optional[Dict]:
        """通过DOI获取文献信息"""
        logger.info(f"Fetching reference by DOI: {doi}")
        data = self.crossref_client.fetch_by_doi(doi)
        if data:
            ref_id = self.database.add_reference(data)
            data['id'] = ref_id
            return data
        return None

    def fetch_reference_by_isbn(self, isbn: str) -> Optional[Dict]:
        """通过ISBN获取图书信息"""
        logger.info(f"Fetching reference by ISBN: {isbn}")
        try:
            url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data:
                    book_data = list(data.values())[0] if data else {}
                    ref_data = self._parse_openlibrary_data(book_data)
                    ref_id = self.database.add_reference(ref_data)
                    ref_data['id'] = ref_id
                    return ref_data
        except Exception as e:
            logger.error(f"Error fetching ISBN {isbn}: {str(e)}")
        return None

    def _parse_openlibrary_data(self, data: Dict) -> Dict:
        """解析OpenLibrary数据"""
        try:
            authors = []
            for author_data in data.get('authors', []):
                author = Author(
                    given=author_data.get('name', '').split(' ')[-1],
                    family=author_data.get('name', '').split(' ')[0]
                )
                authors.append(author)

            return {
                'type': 'book',
                'title': data.get('title', ''),
                'authors': authors,
                'year': int(data.get('publish_date', '2026')[:4]) if data.get('publish_date') else 2026,
                'isbn': data.get('isbn_13', [None])[0] or data.get('isbn_10', [None])[0],
                'publisher': data.get('publishers', [''])[0] if data.get('publishers') else None,
                'page': data.get('number_of_pages'),
                'language': 'en'
            }
        except Exception as e:
            logger.error(f"Error parsing OpenLibrary data: {str(e)}")
            return {}

    def search_references(self, title: str, author: Optional[str] = None,
                        year: Optional[int] = None, max_results: int = 10) -> List[Dict]:
        """搜索参考文献"""
        logger.info(f"Searching references: {title}")
        results = self.crossref_client.search_by_title_author(title, author, year, max_results)
        
        for result in results:
            ref_id = self.database.add_reference(result)
            result['id'] = ref_id
        
        return results

    def add_to_library(self, reference: Union[Reference, Dict]) -> str:
        """添加文献到本地库"""
        if isinstance(reference, Reference):
            ref_data = reference.to_dict()
        else:
            ref_data = reference
        
        ref_id = self.database.add_reference(ref_data)
        logger.info(f"Reference added to library: {ref_id}")
        return ref_id

    def generate_citation(self, reference_id: str,
                         style: str = "apa",
                         citation_type: str = "parenthetical",
                         page: Optional[str] = None) -> str:
        """生成文中引用"""
        try:
            style_enum = CitationStyle(style)
        except ValueError:
            logger.error(f"Unsupported citation style: {style}")
            return f"[{reference_id}]"
        
        ref_data = self.database.get_reference(reference_id)
        
        if not ref_data:
            logger.warning(f"Reference not found: {reference_id}")
            return f"[{reference_id}]"
        
        reference = self.converter._dict_to_reference(ref_data)
        formatter = self.converter.formatters.get(style_enum, self.converter.formatters[CitationStyle.APA])
        
        citation = formatter.format_in_text_citation(reference, citation_type, page)
        return citation

    def generate_bibliography(self, style: str = "apa",
                           sort_by: str = "alphabetical") -> List[str]:
        """生成参考文献列表"""
        try:
            style_enum = CitationStyle(style)
        except ValueError:
            logger.error(f"Unsupported citation style: {style}")
            style_enum = CitationStyle.APA

        references = self.database.get_all_references()
        
        if sort_by == "alphabetical":
            references.sort(key=lambda x: (x.get('title', ''), x.get('year', 0)))
        elif sort_by == "citation_order":
            references.sort(key=lambda x: x.get('id', ''))
        elif sort_by == "year":
            references.sort(key=lambda x: x.get('year', 0), reverse=True)
        
        formatter = self.converter.formatters.get(style_enum, self.converter.formatters[CitationStyle.APA])
        bibliography = []
        
        for ref_dict in references:
            try:
                reference = self.converter._dict_to_reference(ref_dict)
                entry = formatter.format_bibliography_entry(reference)
                bibliography.append(entry)
            except Exception as e:
                logger.error(f"Error formatting reference: {str(e)}")
        
        logger.info(f"Generated bibliography: {len(bibliography)} entries")
        return bibliography

    def check_citation_integrity(self, document_text: str) -> Dict:
        """检查引用完整性"""
        references = self.database.get_all_references()
        return self.checker.check_document(document_text, references)

    def convert_citation_style(self, references: List[Dict],
                             from_style: str, to_style: str) -> List[Dict]:
        """转换引用格式"""
        try:
            from_style_enum = CitationStyle(from_style)
            to_style_enum = CitationStyle(to_style)
        except ValueError as e:
            logger.error(f"Unsupported citation style: {str(e)}")
            return []
        
        return self.converter.convert_batch(references, from_style_enum, to_style_enum)

    def export_bibtex(self, output_file: str) -> bool:
        """导出为BibTeX格式"""
        references = self.database.get_all_references()
        bibtex_content = self.converter.export_bibtex(references)
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(bibtex_content)
            logger.info(f"Exported BibTeX: {output_file}")
            return True
        except Exception as e:
            logger.error(f"Error exporting BibTeX: {str(e)}")
            return False

    def import_from_bibtex(self, input_file: str) -> int:
        """从BibTeX格式导入"""
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                bibtex_content = f.read()
            
            imported_count = 0
            entries = self._parse_bibtex(bibtex_content)
            
            for entry in entries:
                ref_id = self.database.add_reference(entry)
                imported_count += 1
            
            logger.info(f"Imported {imported_count} references from BibTeX")
            return imported_count
        except Exception as e:
            logger.error(f"Error importing BibTeX: {str(e)}")
            return 0

    def _parse_bibtex(self, bibtex_content: str) -> List[Dict]:
        """解析BibTeX内容"""
        entries = []
        entry_pattern = re.compile(r'@(\w+)\s*\{([^,]+),\s*(.*?)\n\s*\}', re.DOTALL)
        
        for match in entry_pattern.finditer(bibtex_content):
            entry_type = match.group(1)
            entry_key = match.group(2)
            entry_content = match.group(3)
            
            fields = {}
            field_pattern = re.compile(r'(\w+)\s*=\s*\{(.*?)\}')
            
            for field_match in field_pattern.finditer(entry_content):
                field_name = field_match.group(1)
                field_value = field_match.group(2).strip()
                fields[field_name] = field_value
            
            entry = {
                'id': entry_key,
                'type': self._map_bibtex_type(entry_type),
                'title': fields.get('title', ''),
                'authors': self._parse_bibtex_authors(fields.get('author', '')),
                'year': int(fields.get('year', datetime.now().year)),
                'journal': fields.get('journal') or fields.get('journaltitle'),
                'volume': fields.get('volume'),
                'number': fields.get('number'),
                'pages': fields.get('pages'),
                'publisher': fields.get('publisher'),
                'doi': fields.get('doi'),
                'isbn': fields.get('isbn') or fields.get('isbn13'),
                'language': fields.get('language', 'en')
            }
            
            entries.append(entry)
        
        return entries

    def _map_bibtex_type(self, bibtex_type: str) -> str:
        """映射BibTeX类型到内部类型"""
        type_mapping = {
            'article': 'journal_article',
            'book': 'book',
            'inproceedings': 'conference_paper',
            'phdthesis': 'thesis',
            'mastersthesis': 'thesis',
            'techreport': 'report',
            'misc': 'webpage'
        }
        return type_mapping.get(bibtex_type.lower(), 'webpage')

    def _parse_bibtex_authors(self, author_string: str) -> List[Dict]:
        """解析BibTeX作者字符串"""
        authors = []
        if not author_string:
            return authors
        
        author_parts = re.split(r'\s+and\s+', author_string)
        
        for part in author_parts:
            name_parts = re.split(r',\s*', part.strip())
            if len(name_parts) >= 2:
                family = name_parts[0].strip()
                given = name_parts[1].strip()
                authors.append({
                    'family': family,
                    'given': given,
                    'sequence': 'additional'
                })
        
        return authors

    def get_library_stats(self) -> Dict:
        """获取文献库统计信息"""
        references = self.database.get_all_references()
        
        type_counts = {}
        year_counts = {}
        language_counts = {}
        
        for ref in references:
            ref_type = ref.get('type', 'unknown')
            type_counts[ref_type] = type_counts.get(ref_type, 0) + 1
            
            year = ref.get('year', 0)
            year_counts[year] = year_counts.get(year, 0) + 1
            
            language = ref.get('language', 'en')
            language_counts[language] = language_counts.get(language, 0) + 1
        
        return {
            'total_references': len(references),
            'type_distribution': type_counts,
            'year_distribution': year_counts,
            'language_distribution': language_counts
        }

    def export_to_json(self, output_file: str) -> bool:
        """导出为JSON格式"""
        try:
            self.database.export_to_json(output_file)
            return True
        except Exception as e:
            logger.error(f"Error exporting to JSON: {str(e)}")
            return False

    def import_from_json(self, input_file: str) -> int:
        """从JSON格式导入"""
        try:
            self.database.import_from_json(input_file)
            references = self.database.get_all_references()
            return len(references)
        except Exception as e:
            logger.error(f"Error importing from JSON: {str(e)}")
            return 0


def main():
    """主函数 - 命令行接口"""
    parser = argparse.ArgumentParser(
        description='Academic Citation Manager - 为科研论文和毕业论文添加真实参考文献并规范引用标注',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  通过DOI获取文献信息:
    python academic_citation_skill.py --fetch-doi 10.1038/nature14539
  
  搜索文献:
    python academic_citation_skill.py --search "Deep Learning" --author "LeCun"
  
  生成参考文献列表:
    python academic_citation_skill.py --generate-bib --style apa --sort alphabetical
  
  检查引用完整性:
    python academic_citation_skill.py --check document.txt
  
  格式转换:
    python academic_citation_skill.py --convert --from-style apa --to-style ieee --input refs.txt

更多信息请访问: https://github.com/YouStudyeveryday/academic-citation-manager
        """
    )
    
    parser.add_argument('--fetch-doi', type=str, help='通过DOI获取文献信息')
    parser.add_argument('--fetch-isbn', type=str, help='通过ISBN获取图书信息')
    parser.add_argument('--search', type=str, help='搜索文献（标题）')
    parser.add_argument('--author', type=str, help='作者名称（用于搜索）')
    parser.add_argument('--year', type=int, help='出版年份（用于搜索）')
    parser.add_argument('--max-results', type=int, default=10, help='最大结果数（默认10）')
    
    parser.add_argument('--style', type=str, default='apa',
                       help='引用格式 (apa, mla, chicago, ieee, gbt7714, harvard)')
    parser.add_argument('--sort', type=str, default='alphabetical',
                       help='排序方式 (alphabetical, citation_order, year)')
    
    parser.add_argument('--generate-bib', action='store_true', help='从文献库生成参考文献列表')
    parser.add_argument('--output', type=str, help='输出文件路径')
    
    parser.add_argument('--convert', action='store_true', help='转换引用格式')
    parser.add_argument('--from-style', type=str, help='源格式（用于转换）')
    parser.add_argument('--to-style', type=str, help='目标格式（用于转换）')
    parser.add_argument('--input', type=str, help='输入文件路径')
    
    parser.add_argument('--check', type=str, help='检查文档引用完整性')
    
    parser.add_argument('--import-bibtex', type=str, help='从BibTeX文件导入')
    parser.add_argument('--export-bibtex', type=str, help='导出为BibTeX文件')
    
    parser.add_argument('--import-json', type=str, help='从JSON文件导入')
    parser.add_argument('--export-json', type=str, help='导出为JSON文件')
    
    parser.add_argument('--stats', action='store_true', help='显示文献库统计信息')
    
    args = parser.parse_args()
    manager = AcademicCitationManager()

    try:
        if args.fetch_doi:
            print(f"正在获取DOI文献信息: {args.fetch_doi}")
            ref = manager.fetch_reference_by_doi(args.fetch_doi)
            if ref:
                print(f"\n文献信息:")
                print(f"  标题: {ref.get('title', 'Unknown')}")
                print(f"  作者: {', '.join([f\"{a.get('family', '')} {a.get('given', '')}\" for a in ref.get('authors', [])])}")
                print(f"  年份: {ref.get('year', 'Unknown')}")
                print(f"  类型: {ref.get('type', 'Unknown')}")
                print(f"  DOI: {ref.get('doi', 'Unknown')}")
                print(f"  容器: {ref.get('container_title', 'N/A')}")
                print(f"  卷期: {ref.get('volume', 'N/A')}({ref.get('issue', 'N/A')})")
                print(f"  页码: {ref.get('page', 'N/A')}")
            else:
                print("未找到文献信息")

        elif args.fetch_isbn:
            print(f"正在获取ISBN图书信息: {args.fetch_isbn}")
            ref = manager.fetch_reference_by_isbn(args.fetch_isbn)
            if ref:
                print(f"\n图书信息:")
                print(f"  标题: {ref.get('title', 'Unknown')}")
                print(f"  作者: {', '.join([f\"{a.get('family', '')} {a.get('given', '')}\" for a in ref.get('authors', [])])}")
                print(f"  年份: {ref.get('year', 'Unknown')}")
                print(f"  ISBN: {ref.get('isbn', 'Unknown')}")
                print(f"  出版社: {ref.get('publisher', 'N/A')}")
                print(f"  页数: {ref.get('page', 'N/A')}")
            else:
                print("未找到图书信息")

        elif args.search:
            print(f"正在搜索文献: {args.search}")
            if args.author:
                print(f"  作者: {args.author}")
            if args.year:
                print(f"  年份: {args.year}")
            
            results = manager.search_references(
                args.search, args.author, args.year, args.max_results
            )
            
            print(f"\n找到 {len(results)} 篇文献:\n")
            for i, ref in enumerate(results, 1):
                print(f"{i}. {ref.get('title', 'Unknown')} ({ref.get('year', 'Unknown')})")
                print(f"   作者: {', '.join([f\"{a.get('family', '')} {a.get('given', '')}\" for a in ref.get('authors', [])[:3]])}")
                if len(ref.get('authors', [])) > 3:
                    print("   等")
                print(f"   DOI: {ref.get('doi', 'N/A')}")
                print()

        elif args.generate_bib:
            print(f"正在生成参考文献列表 ({args.style}格式, {args.sort}排序):")
            bibliography = manager.generate_bibliography(args.style, args.sort)
            
            output_text = "\n".join([f"{i}. {entry}" for i, entry in enumerate(bibliography, 1)])
            
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(output_text)
                print(f"\n参考文献列表已保存到: {args.output}")
            else:
                print(f"\n{output_text}")

        elif args.check:
            print(f"正在检查文档引用完整性: {args.check}")
            with open(args.check, 'r', encoding='utf-8') as f:
                document_text = f.read()
            
            report = manager.check_citation_integrity(document_text)
            
            print(f"\n引用完整性报告:")
            print(f"  文中引用总数: {report['total_citations']}")
            print(f"  参考文献总数: {report['total_references']}")
            print(f"  不一致项数量: {report['inconsistencies']}")
            
            if report['missing_in_bibliography']:
                print(f"\n  文中引用但参考文献列表缺失 ({len(report['missing_in_bibliography'])} 项):")
                for item in report['missing_in_bibliography']:
                    print(f"    - {item}")
            
            if report['unused_references']:
                print(f"\n  参考文献列表中未使用 ({len(report['unused_references'])} 项):")
                for item in report['unused_references']:
                    print(f"    - {item}")
            
            if report['inconsistencies'] == 0:
                print("\n  引用完整性检查通过！")

        elif args.convert and args.input:
            print(f"正在转换引用格式: {args.from_style} -> {args.to_style}")
            
            with open(args.input, 'r', encoding='utf-8') as f:
                data = json.load(f)
                references = data if isinstance(data, list) else data.get('references', [])
            
            converted = manager.convert_citation_style(references, args.from_style, args.to_style)
            
            print(f"\n转换结果 ({len(converted)} 项):\n")
            for item in converted:
                print(f"ID: {item.get('id', 'unknown')}")
                print(f"  原始: {item.get('original', '')[:100]}...")
                print(f"  转换后: {item.get('converted', '')[:100]}...")
                print()

        elif args.import_bibtex:
            print(f"正在从BibTeX导入: {args.import_bibtex}")
            count = manager.import_from_bibtex(args.import_bibtex)
            print(f"\n成功导入 {count} 篇文献")

        elif args.export_bibtex:
            print(f"正在导出为BibTeX: {args.export_bibtex}")
            success = manager.export_bibtex(args.export_bibtex)
            if success:
                print(f"\n成功导出到: {args.export_bibtex}")

        elif args.import_json:
            print(f"正在从JSON导入: {args.import_json}")
            count = manager.import_from_json(args.import_json)
            print(f"\n成功导入 {count} 篇文献")

        elif args.export_json:
            print(f"正在导出为JSON: {args.export_json}")
            success = manager.export_to_json(args.export_json)
            if success:
                print(f"\n成功导出到: {args.export_json}")

        elif args.stats:
            print("文献库统计信息:")
            stats = manager.get_library_stats()
            print(f"\n  总文献数: {stats['total_references']}")
            print(f"\n  文献类型分布:")
            for type_name, count in stats['type_distribution'].items():
                print(f"    {type_name}: {count}")
            print(f"\n  年份分布:")
            for year, count in sorted(stats['year_distribution'].items(), reverse=True)[:10]:
                print(f"    {year}: {count}")
            print(f"\n  语言分布:")
            for lang, count in stats['language_distribution'].items():
                print(f"    {lang}: {count}")

        else:
            print("未指定操作。使用 --help 查看帮助信息。")

    except KeyboardInterrupt:
        print("\n操作已取消")
    except Exception as e:
        logger.error(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()