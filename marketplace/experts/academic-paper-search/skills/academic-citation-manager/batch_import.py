#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量导入参考文献
支持从多种格式批量导入参考文献到学术引用管理器
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BibTeXParser:
    """BibTeX解析器"""
    
    def __init__(self):
        """初始化解析器"""
        self.entry_pattern = re.compile(r'@(\w+)\s*\{([^,]+),\s*(.*?)\n\s*\}', re.DOTALL)
        self.field_pattern = re.compile(r'(\w+)\s*=\s*\{(.*?)\}', re.DOTALL)
        self.type_mapping = {
            'article': 'journal_article',
            'book': 'book',
            'inproceedings': 'conference_paper',
            'phdthesis': 'thesis',
            'mastersthesis': 'thesis',
            'techreport': 'report',
            'misc': 'webpage'
        }
    
    def parse_file(self, file_path: str) -> List[Dict]:
        """解析BibTeX文件"""
        logger.info(f"解析BibTeX文件: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        entries = []
        for match in self.entry_pattern.finditer(content):
            entry_type = match.group(1)
            entry_key = match.group(2)
            entry_content = match.group(3)
            
            entry = {
                'id': entry_key,
                'type': self.type_mapping.get(entry_type, entry_type),
                'original_type': entry_type,
                'original_key': entry_key
            }
            
            # 解析字段
            for field_match in self.field_pattern.finditer(entry_content):
                field_name = field_match.group(1)
                field_value = field_match.group(2).strip('{}')
                
                # 处理特殊字段
                if field_name == 'author' or field_name == 'editor':
                    entry['authors'] = self._parse_authors(field_value)
                elif field_name == 'journal' or field_name == 'journaltitle':
                    entry['container_title'] = field_value
                elif field_name == 'year':
                    entry['year'] = int(field_value) if field_value.isdigit() else 2026
                else:
                    entry[field_name] = field_value
            
            entries.append(entry)
        
        logger.info(f"成功解析{len(entries)}条BibTeX条目")
        return entries
    
    def _parse_authors(self, author_string: str) -> List[Dict]:
        """解析作者字符串"""
        authors = []
        
        # 分割多个作者
        author_parts = re.split(r'\s+and\s+', author_string)
        
        for part in author_parts:
            part = part.strip()
            if not part:
                continue
            
            # 分析"姓, 名"格式
            name_parts = re.split(r',\s*', part)
            
            if len(name_parts) >= 2:
                family = name_parts[0].strip()
                given = name_parts[1].strip()
                authors.append({
                    'family': family,
                    'given': given,
                    'sequence': 'additional'
                })
            else:
                # 其他格式，尝试提取名字
                words = part.split()
                if len(words) >= 2:
                    authors.append({
                        'family': words[-1],
                        'given': ' '.join(words[:-1]),
                        'sequence': 'additional'
                    })
                elif words:
                    authors.append({
                        'family': words[0],
                        'given': '',
                        'sequence': 'additional'
                    })
        
        # 设置第一个作者为序列"first"
        if authors:
            authors[0]['sequence'] = 'first'
        
        return authors


class RISParser:
    """RIS格式解析器"""
    
    def __init__(self):
        """初始化解析器"""
        self.type_mapping = {
            'JOUR': 'journal_article',
            'BOOK': 'book',
            'CONF': 'conference_paper',
            'THES': 'thesis',
            'RPRT': 'report',
            'NEWS': 'newspaper_article'
        }
        self.field_mapping = {
            'TY': 'type',
            'AU': 'authors',
            'TI': 'title',
            'PY': 'year',
            'JO': 'container_title',
            'VL': 'volume',
            'IS': 'issue',
            'SP': 'page',
            'PB': 'publisher',
            'UR': 'url',
            'DO': 'doi',
            'SN': 'issn',
            'AB': 'abstract'
        }
    
    def parse_file(self, file_path: str) -> List[Dict]:
        """解析RIS文件"""
        logger.info(f"解析RIS文件: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 分割条目
        entries_text = re.split(r'\n\s*ER\s*\n', content)
        
        entries = []
        entry_id = 0
        
        for entry_text in entries_text:
            if not entry_text.strip():
                continue
            
            entry_id += 1
            entry = {'id': f'imported_ris_{entry_id:04d}'}
            
            # 解析字段
            lines = entry_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line or not '=' in line:
                    continue
                
                parts = line.split('=', 1)
                if len(parts) != 2:
                    continue
                
                field_code = parts[0].strip()
                field_value = parts[1].strip()
                
                # 映射字段名
                if field_code in self.field_mapping:
                    mapped_name = self.field_mapping[field_code]
                    
                    if field_code == 'AU':
                        entry['authors'] = self._parse_ris_authors(field_value)
                    elif field_code == 'TY' and field_value in self.type_mapping:
                        entry['type'] = self.type_mapping[field_value]
                    elif field_code == 'PY':
                        try:
                            entry['year'] = int(field_value[:4])
                        except ValueError:
                            entry['year'] = 2026
                    else:
                        entry[mapped_name] = field_value
            
            if 'type' not in entry:
                entry['type'] = 'webpage'
            
            entries.append(entry)
        
        logger.info(f"成功解析{len(entries)}条RIS条目")
        return entries
    
    def _parse_ris_authors(self, author_string: str) -> List[Dict]:
        """解析RIS作者字符串"""
        authors = []
        
        # RIS格式中，作者通常由AU字段提供，多个作者用换行分隔
        for author_line in author_string.split('\n'):
            author_line = author_line.strip()
            if not author_line:
                continue
            
            # 尝试"姓, 名"格式
            name_parts = re.split(r',\s*', author_line)
            
            if len(name_parts) >= 2:
                family = name_parts[0].strip()
                given = name_parts[1].strip()
                authors.append({
                    'family': family,
                    'given': given,
                    'sequence': 'additional'
                })
            elif name_parts and name_parts[0]:
                authors.append({
                    'family': name_parts[0],
                    'given': '',
                    'sequence': 'additional'
                })
        
        if authors:
            authors[0]['sequence'] = 'first'
        
        return authors


class BatchImporter:
    """批量导入器"""
    
    def __init__(self, manager):
        """初始化导入器"""
        self.manager = manager
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
    
    def import_from_bibtex(self, file_path: str, validate_doi: bool = True) -> Dict:
        """从BibTeX文件导入"""
        logger.info(f"开始从BibTeX导入: {file_path}")
        
        try:
            parser = BibTeXParser()
            entries = parser.parse_file(file_path)
            
            results = self._process_entries(entries, 'bibtex', validate_doi)
            
            logger.info(f"BibTeX导入完成: 成功{results['success']}, 失败{results['failed']}, 跳过{results['skipped']}")
            return results
            
        except Exception as e:
            error_msg = f"BibTeX导入失败: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            return {'total': 0, 'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}
    
    def import_from_ris(self, file_path: str, validate_doi: bool = True) -> Dict:
        """从RIS文件导入"""
        logger.info(f"开始从RIS导入: {file_path}")
        
        try:
            parser = RISParser()
            entries = parser.parse_file(file_path)
            
            results = self._process_entries(entries, 'ris', validate_doi)
            
            logger.info(f"RIS导入完成: 成功{results['success']}, 失败{results['failed']}, 跳过{results['skipped']}")
            return results
            
        except Exception as e:
            error_msg = f"RIS导入失败: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            return {'total': 0, 'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}
    
    def import_from_json(self, file_path: str, validate_doi: bool = True) -> Dict:
        """从JSON文件导入"""
        logger.info(f"开始从JSON导入: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            entries = data if isinstance(data, list) else data.get('references', [])
            
            if not isinstance(entries, list):
                error_msg = f"JSON格式错误: references应为列表"
                logger.error(error_msg)
                self.stats['errors'].append(error_msg)
                return {'total': 0, 'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}
            
            results = self._process_entries(entries, 'json', validate_doi)
            
            logger.info(f"JSON导入完成: 成功{results['success']}, 失败{results['failed']}, 跳过{results['skipped']}")
            return results
            
        except json.JSONDecodeError as e:
            error_msg = f"JSON解析失败: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            return {'total': 0, 'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}
        except Exception as e:
            error_msg = f"JSON导入失败: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            return {'total': 0, 'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}
    
    def import_from_csv(self, file_path: str, validate_doi: bool = True) -> Dict:
        """从CSV文件导入"""
        logger.info(f"开始从CSV导入: {file_path}")
        
        try:
            import csv
            entries = []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 映射CSV列名到内部字段名
                    entry = {
                        'id': row.get('id', ''),
                        'type': row.get('type', 'webpage'),
                        'title': row.get('title', ''),
                        'authors': self._parse_csv_authors(row.get('authors', '')),
                        'year': int(row.get('year', 2026)) if row.get('year', '').isdigit() else 2026,
                        'doi': row.get('doi', ''),
                        'container_title': row.get('journal', row.get('container_title', '')),
                        'volume': row.get('volume', ''),
                        'issue': row.get('issue', ''),
                        'page': row.get('page', ''),
                        'publisher': row.get('publisher', ''),
                        'url': row.get('url', ''),
                        'language': row.get('language', 'en')
                    }
                    entries.append(entry)
            
            results = self._process_entries(entries, 'csv', validate_doi)
            
            logger.info(f"CSV导入完成: 成功{results['success']}, 失败{results['failed']}, 跳过{results['skipped']}")
            return results
            
        except Exception as e:
            error_msg = f"CSV导入失败: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            return {'total': 0, 'success': 0, 'failed': 1, 'skipped': 0, 'errors': [error_msg]}
    
    def import_from_directory(self, directory: str, 
                          file_pattern: str = "*.{bib,ris,json,csv}",
                          validate_doi: bool = True) -> Dict:
        """从目录批量导入"""
        logger.info(f"开始从目录导入: {directory}")
        
        dir_path = Path(directory)
        if not dir_path.exists():
            error_msg = f"目录不存在: {directory}"
            logger.error(error_msg)
            return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0, 'errors': [error_msg]}
        
        # 查找所有匹配的文件
        files = list(dir_path.glob(file_pattern))
        logger.info(f"找到{len(files)}个文件")
        
        total_results = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
            'file_results': {}
        }
        
        for file_path in files:
            file_str = str(file_path)
            suffix = file_path.suffix.lower()
            
            try:
                if suffix == '.bib':
                    result = self.import_from_bibtex(file_str, validate_doi)
                elif suffix == '.ris':
                    result = self.import_from_ris(file_str, validate_doi)
                elif suffix == '.json':
                    result = self.import_from_json(file_str, validate_doi)
                elif suffix == '.csv':
                    result = self.import_from_csv(file_str, validate_doi)
                else:
                    logger.warning(f"跳过不支持的文件类型: {file_str}")
                    result = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 1, 'errors': []}
                
                total_results['total'] += result['total']
                total_results['success'] += result['success']
                total_results['failed'] += result['failed']
                total_results['skipped'] += result['skipped']
                total_results['errors'].extend(result['errors'])
                total_results['file_results'][file_path] = result
                
            except Exception as e:
                error_msg = f"导入文件{file_path}失败: {str(e)}"
                logger.error(error_msg)
                total_results['errors'].append(error_msg)
        
        logger.info(f"目录导入完成: 总计{total_results['total']}, 成功{total_results['success']}, 失败{total_results['failed']}, 跳过{total_results['skipped']}")
        return total_results
    
    def _process_entries(self, entries: List[Dict], 
                       source_type: str,
                       validate_doi: bool) -> Dict:
        """处理导入的条目"""
        results = {
            'total': len(entries),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
            'imported_ids': []
        }
        
        for entry in entries:
            try:
                # 验证必需字段
                if not entry.get('title'):
                    results['skipped'] += 1
                    results['errors'].append(f"跳过无标题条目: {entry.get('id', 'unknown')}")
                    continue
                
                # 生成ID
                if not entry.get('id'):
                    content = entry.get('title', '')
                    if entry.get('year'):
                        content += f"_{entry['year']}"
                    if entry.get('doi'):
                        content += f"_{entry['doi']}"
                    import hashlib
                    entry['id'] = f"import_{hashlib.md5(content.encode()).hexdigest()[:8]}"
                
                # 验证DOI
                if validate_doi and entry.get('doi'):
                    if not self._validate_doi(entry['doi']):
                        results['failed'] += 1
                        results['errors'].append(f"无效DOI: {entry['doi']} (ID: {entry['id']})")
                        continue
                
                # 添加到数据库
                ref_id = self.manager.database.add_reference(entry)
                results['success'] += 1
                results['imported_ids'].append(ref_id)
                
                logger.debug(f"成功导入: {entry['title']} (ID: {ref_id})")
                
            except Exception as e:
                error_msg = f"导入条目失败 (ID: {entry.get('id', 'unknown')}): {str(e)}"
                logger.error(error_msg)
                results['failed'] += 1
                results['errors'].append(error_msg)
        
        return results
    
    def _parse_csv_authors(self, author_string: str) -> List[Dict]:
        """解析CSV作者字符串"""
        authors = []
        
        if not author_string:
            return authors
        
        # CSV中作者可能用分号或and分隔
        parts = re.split(r'[;，]\s*and\s*', author_string)
        
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            
            # 尝试提取姓名
            words = part.split()
            if len(words) >= 2:
                family = words[-1]
                given = ' '.join(words[:-1])
            elif words:
                family = words[0]
                given = ' '.join(words[1:])
            else:
                continue
            
            authors.append({
                'family': family,
                'given': given,
                'sequence': 'first' if i == 0 else 'additional'
            })
        
        return authors
    
    def _validate_doi(self, doi: str) -> bool:
        """验证DOI格式"""
        if not doi:
            return True
        
        # 基本DOI格式验证
        doi_pattern = r'^10\.\d{4,}/.+'
        return bool(re.match(doi_pattern, doi))
    
    def generate_report(self) -> str:
        """生成导入报告"""
        report = []
        report.append("=" * 70)
        report.append("批量导入报告")
        report.append("=" * 70)
        report.append(f"\n总计: {self.stats['total']}")
        report.append(f"成功: {self.stats['success']}")
        report.append(f"失败: {self.stats['failed']}")
        report.append(f"跳过: {self.stats['skipped']}")
        
        if self.stats['errors']:
            report.append("\n错误:")
            for error in self.stats['errors'][:20]:  # 只显示前20个错误
                report.append(f"  - {error}")
            if len(self.stats['errors']) > 20:
                report.append(f"  ... 还有{len(self.stats['errors']) - 20}个错误未显示")
        
        report.append("\n" + "=" * 70)
        
        return '\n'.join(report)
    
    def export_report(self, output_file: str):
        """导出报告到文件"""
        report = self.generate_report()
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"报告已导出: {output_file}")
            return True
        except Exception as e:
            logger.error(f"导出报告失败: {str(e)}")
            return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='批量导入参考文献到学术引用管理器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  导入BibTeX文件:
    python batch_import.py --bibtex references.bib
  
  导入RIS文件:
    python batch_import.py --ris references.ris
  
  导入JSON文件:
    python batch_import.py --json references.json
  
  导入整个目录:
    python batch_import.py --directory ./references
  
  验证DOI并生成报告:
    python batch_import.py --bibtex references.bib --validate-doi --report import_report.txt

更多信息请访问: https://github.com/YouStudyeveryday/academic-citation-manager
        """
    )
    
    parser.add_argument('--bibtex', type=str, help='BibTeX文件路径')
    parser.add_argument('--ris', type=str, help='RIS文件路径')
    parser.add_argument('--json', type=str, help='JSON文件路径')
    parser.add_argument('--csv', type=str, help='CSV文件路径')
    parser.add_argument('--directory', type=str, help='导入目录路径')
    parser.add_argument('--pattern', type=str, default='*.{bib,ris,json,csv}',
                       help='目录中的文件模式（默认: *.{bib,ris,json,csv}）')
    parser.add_argument('--validate-doi', action='store_true',
                       help='验证DOI格式')
    parser.add_argument('--report', type=str,
                       help='导出导入报告到指定文件')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='显示详细输出')
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 导入管理器
    try:
        from academic_citation_skill import AcademicCitationManager
        manager = AcademicCitationManager()
        importer = BatchImporter(manager)
        
        # 执行导入
        if args.bibtex:
            results = importer.import_from_bibtex(args.bibtex, args.validate_doi)
            importer.stats.update(results)
        
        elif args.ris:
            results = importer.import_from_ris(args.ris, args.validate_doi)
            importer.stats.update(results)
        
        elif args.json:
            results = importer.import_from_json(args.json, args.validate_doi)
            importer.stats.update(results)
        
        elif args.csv:
            results = importer.import_from_csv(args.csv, args.validate_doi)
            importer.stats.update(results)
        
        elif args.directory:
            results = importer.import_from_directory(args.directory, args.pattern, args.validate_doi)
            importer.stats.update(results)
        
        else:
            print("错误: 必须指定输入文件或目录")
            print("使用 --help 查看帮助信息")
            return 1
        
        # 生成报告
        if args.report:
            success = importer.export_report(args.report)
            return 0 if success else 1
        else:
            print(importer.generate_report())
        
        return 0
        
    except ImportError as e:
        print(f"错误: 无法导入AcademicCitationManager: {str(e)}")
        print("请确保academic_citation_skill.py在同一目录下")
        return 1
    except Exception as e:
        logging.error(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())