#!/usr/bin/env python3
"""
PubMed API Query Tool (with retry and better error handling)
Search for medical literature from NIH PubMed database.

Usage:
    python3 query_pubmed.py "keyword" [--limit N] [--year YYYY]

Examples:
    python3 query_pubmed.py "cough treatment"
    python3 query_pubmed.py "diabetes" --limit 5 --year 2024
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import sys
import time
from datetime import datetime

# PubMed API base URLs
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

def search_pubmed(query, limit=5, year=None, max_retries=3):
    """
    Search PubMed for medical literature with retry logic.
    Uses esummary to get article summaries directly.
    """
    if year is None:
        year = str(datetime.now().year - 1)
    
    # Build search query with date filter
    search_query = f'({query}) AND ({year}[Date - Publication] : 3000[Date - Publication])'
    
    for attempt in range(max_retries):
        try:
            # Step 1: Search for article IDs
            search_params = {
                'db': 'pmc',
                'term': search_query,
                'retmax': limit,
                'retmode': 'json',
                'sort': 'relevance'
            }
            
            search_url = f"{ESEARCH_URL}?{urllib.parse.urlencode(search_params)}"
            
            req = urllib.request.Request(
                search_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            )
            
            kwargs = {'timeout': 30}
            
            with urllib.request.urlopen(req, **kwargs) as response:
                search_data = json.loads(response.read().decode('utf-8'))
            
            # Extract IDs from search result
            if 'esearchresult' not in search_data or 'idlist' not in search_data['esearchresult']:
                return {'error': '未找到相关文献', 'note': '请尝试其他关键词'}
            
            id_list = search_data['esearchresult']['idlist'][:limit]
            
            if not id_list:
                return {'error': '未找到相关文献', 'note': '请尝试其他关键词'}
            
            # Step 2: Get summaries via esummary
            summary_params = {
                'db': 'pmc',
                'id': ','.join(id_list),
                'retmode': 'json'
            }
            
            summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urllib.parse.urlencode(summary_params)}"
            
            req2 = urllib.request.Request(
                summary_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            )
            
            with urllib.request.urlopen(req2, **kwargs) as response2:
                summary_data = json.loads(response2.read().decode('utf-8'))
            
            # Parse esummary results
            results = []
            if 'result' in summary_data:
                result_data = summary_data['result']
                # Get list of IDs
                uids_list = result_data.get('uids', [])
                
                for uid in uids_list:
                    # Get info for this UID
                    info = result_data.get(uid, {})
                    title = info.get('title', 'No title')
                    authors = info.get('authors', [])
                    authors_str = ', '.join([a.get('name', '') for a in authors[:5]])
                    if len(authors) > 5:
                        authors_str += ' et al.'
                    
                    journal = info.get('source', 'Unknown journal')
                    pubdate = info.get('pubdate', '')
                    abstract = info.get('abstract', '')
                    if abstract and len(abstract) > 300:
                        abstract = abstract[:300] + '...'
                    
                    result = {
                        'pmid': uid,
                        'title': title,
                        'authors': authors_str,
                        'journal': journal,
                        'pubdate': pubdate,
                        'abstract': abstract if abstract else 'No abstract available',
                        'link': f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
                    }
                    results.append(result)
            
            return results
            
        except urllib.error.URLError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                return {
                    'error': f'查询失败：{str(e)}',
                    'note': '网络问题，请检查连接或稍后重试'
                }
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Attempt {attempt + 1} failed: {e}, retrying...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                return {
                    'error': f'查询失败：{str(e)}',
                    'note': '网络问题，请检查连接或稍后重试'
                }
    
    return {'error': '未知错误'}

def format_output(results):
    """Format search results for display."""
    if isinstance(results, dict) and 'error' in results:
        return f"❌ {results['error']}\n{results.get('note', '')}"
    
    output = []
    output.append(f"\n📚 找到 {len(results)} 篇相关文献：\n")
    
    for i, result in enumerate(results, 1):
        output.append(f"[{i}] {result['title']}")
        output.append(f"    📖 {result['journal']} | {result['pubdate']}")
        output.append(f"    👤 {result['authors']}")
        if result.get('abstract') and result['abstract'] != 'No abstract available':
            abstract_preview = result['abstract'][:200] + '...' if len(result['abstract']) > 200 else result['abstract']
            output.append(f"    📝 {abstract_preview}")
        output.append(f"    🔗 {result['link']}")
        output.append("")
    
    return '\n'.join(output)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Search PubMed for medical literature')
    parser.add_argument('query', type=str, help='Search query (keywords)')
    parser.add_argument('--limit', type=int, default=5, help='Maximum results')
    parser.add_argument('--year', type=str, default=None, help='Publication year filter')
    
    args = parser.parse_args()
    
    results = search_pubmed(args.query, limit=args.limit, year=args.year)
    print(format_output(results))
