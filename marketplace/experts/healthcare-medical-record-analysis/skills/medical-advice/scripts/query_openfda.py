#!/usr/bin/env python3
"""
OpenFDA Drug API Query Tool (with retry and better error handling)
Search for drug information from FDA's open database.

Usage:
    python3 query_openfda.py "drug_name" [--type label|events]

Examples:
    python3 query_openfda.py "ibuprofen"
    python3 query_openfda.py "acetaminophen" --type events
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import sys
import time

# OpenFDA API base URL
BASE_URL = "https://api.fda.gov"

def query_drug_label(drug_name, limit=5, max_retries=3):
    """
    Query drug label information with retry logic.
    """
    params = {
        'search': f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}"',
        'limit': limit,
        'skip': 0
    }
    
    url = f"{BASE_URL}/drug/label.json?{urllib.parse.urlencode(params)}"
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json'
                }
            )
            
            kwargs = {'timeout': 30}
            
            with urllib.request.urlopen(req, **kwargs) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                results = []
                if 'results' in data:
                    for item in data['results'][:limit]:
                        result = {
                            'brand_name': item.get('openfda', {}).get('brand_name', ['Unknown'])[0],
                            'generic_name': item.get('openfda', {}).get('generic_name', ['Unknown'])[0],
                            'manufacturer': item.get('manufacturer_name', ['Unknown'])[0],
                            'purpose': item.get('purpose', ['N/A'])[0],
                            'indication': extract_text_from_fda_format(item.get('indications_and_usage', [])),
                            'warning': extract_text_from_fda_format(item.get('warnings', []))[:300] + '...' if item.get('warnings') else 'No warnings listed',
                            'dosage': extract_text_from_fda_format(item.get('dosage_and_administration', []))[:300] + '...' if item.get('dosage_and_administration') else 'No dosage info',
                            'active_ingredient': item.get('active_ingredient', []),
                            'route': item.get('route', ['Unknown'])[0],
                            'source_url': item.get('source_url', '')
                        }
                        results.append(result)
                
                return results
                
        except urllib.error.URLError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                return {'error': f'查询失败：{str(e)}', 'note': '网络问题，请检查连接'}
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Attempt {attempt + 1} failed: {e}, retrying...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                return {'error': f'查询失败：{str(e)}', 'note': '网络问题，请检查连接'}
    
    return {'error': '未知错误'}

def query_drug_events(drug_name, limit=10, max_retries=3):
    """
    Query adverse event reports for a drug with retry logic.
    """
    params = {
        'search': f'patientdrug.drugname:"{drug_name}"',
        'limit': limit,
        'skip': 0
    }
    
    url = f"{BASE_URL}/drug/event.json?{urllib.parse.urlencode(params)}"
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json'
                }
            )
            
            kwargs = {'timeout': 30}
            
            with urllib.request.urlopen(req, **kwargs) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                total = data.get('meta', {}).get('results', {}).get('total', 0)
                
                return {
                    'drug_name': drug_name,
                    'total_reports': total,
                    'note': '不良事件报告总数（仅供参考，不代表因果关系）',
                    'sample_events': data.get('results', [])[:3]
                }
                
        except urllib.error.URLError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Attempt {attempt + 1} failed, retrying...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                return {'error': f'查询失败：{str(e)}'}
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Attempt {attempt + 1} failed: {e}, retrying...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                return {'error': f'查询失败：{str(e)}'}
    
    return {'error': '未知错误'}

def extract_text_from_fda_format(data):
    """
    Extract readable text from FDA's nested format
    """
    if not data:
        return ''
    
    if isinstance(data, str):
        return data.strip()
    
    if isinstance(data, list):
        texts = []
        for item in data:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    texts.append(text)
            elif isinstance(item, dict):
                for key, value in item.items():
                    extracted = extract_text_from_fda_format(value)
                    if extracted:
                        texts.append(extracted)
        return ' '.join(texts[:500])
    
    return str(data)[:500]

def format_drug_output(results):
    """Format drug results for display."""
    if isinstance(results, dict) and 'error' in results:
        return f"❌ {results['error']}\n{results.get('note', '')}"
    
    output = []
    output.append(f"\n💊 找到 {len(results)} 个相关药品信息：\n")
    
    for i, result in enumerate(results, 1):
        output.append(f"[{i}] {result['brand_name']} ({result['generic_name']})")
        output.append(f"    🏭 生产商：{result['manufacturer']}")
        output.append(f"    💉 给药途径：{result['route']}")
        output.append(f"    📋 用途：{result['purpose']}")
        
        if result['active_ingredient']:
            ingredients = result['active_ingredient']
            if isinstance(ingredients, list):
                ingredients = ingredients[0] if len(ingredients) == 1 else str(ingredients)
            output.append(f"    🧪 有效成分：{ingredients}")
        
        if result['indication']:
            output.append(f"    ✅ 适应症：{result['indication'][:200]}...")
        
        if result['warning'] and result['warning'] != 'No warnings listed':
            output.append(f"    ⚠️  警告：{result['warning']}")
        
        if result['source_url']:
            output.append(f"    🔗 {result['source_url']}")
        
        output.append("")
    
    return '\n'.join(output)

def format_events_output(result):
    """Format adverse events summary."""
    if isinstance(result, dict) and 'error' in result:
        return result['error']
    
    output = []
    output.append(f"\n📊 不良事件报告统计：\n")
    output.append(f"药品：{result['drug_name']}")
    output.append(f"报告总数：{result['total_reports']:,}")
    output.append(f"\n⚠️  注意：这只是报告数量，不代表因果关系。")
    output.append(f"许多报告是预期内的副作用或与其他因素相关。\n")
    
    return '\n'.join(output)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Query OpenFDA drug database')
    parser.add_argument('drug_name', type=str, help='Drug name to search')
    parser.add_argument('--type', type=str, choices=['label', 'events'], default='label',
                       help='Query type: label (drug info) or events (adverse events)')
    parser.add_argument('--limit', type=int, default=5, help='Maximum results')
    
    args = parser.parse_args()
    
    if args.type == 'label':
        results = query_drug_label(args.drug_name, limit=args.limit)
        print(format_drug_output(results))
    else:
        results = query_drug_events(args.drug_name, limit=args.limit)
        print(format_events_output(results))
