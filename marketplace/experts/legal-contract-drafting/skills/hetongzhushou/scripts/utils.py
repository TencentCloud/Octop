"""
合同智能助手工具函数
Contract Assistant Utilities

提供通用工具函数：文本处理、日期处理、格式化等
"""

import re
import json
import datetime
from typing import Dict, List, Optional, Any, Union
from pathlib import Path


# ==================== 文本处理工具 ====================

def normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    return re.sub(r'\s+', ' ', text).strip()


def normalize_quotes(text: str) -> str:
    """规范化引号"""
    replacements = {
        '"': '"', '"': '"',
        ''': "'", ''': "'",
        '«': '"', '»': '"',
        '‹': "'", '›': "'"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def normalize_dashes(text: str) -> str:
    """规范化破折号"""
    return text.replace('—', '-').replace('–', '-').replace('──', '-')


def clean_text(text: str) -> str:
    """清理文本"""
    text = normalize_whitespace(text)
    text = normalize_quotes(text)
    text = normalize_dashes(text)
    return text


def extract_numbers(text: str) -> List[Union[int, float]]:
    """提取文本中的数字"""
    # 提取整数
    integers = [int(m) for m in re.findall(r'\d+', text)]
    
    # 提取浮点数
    floats = []
    float_pattern = r'\d+\.\d+'
    for match in re.finditer(float_pattern, text):
        try:
            floats.append(float(match.group()))
        except ValueError:
            pass
    
    return integers + floats


def extract_amounts(text: str) -> List[Dict[str, Any]]:
    """提取金额信息"""
    amounts = []
    
    patterns = [
        # 纯数字+单位
        (r'([¥￥$])\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', 'currency'),
        (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:万|亿|元)', 'amount'),
        (r'(\d+(?:\.\d+)?)\s*%', 'percentage')
    ]
    
    for pattern, amount_type in patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            amounts.append({
                "type": amount_type,
                "value": match.group(0),
                "position": match.start()
            })
    
    return amounts


def extract_dates(text: str) -> List[Dict[str, Any]]:
    """提取日期信息"""
    dates = []
    
    patterns = [
        (r'\d{4}年\d{1,2}月\d{1,2}日', 'full_date'),
        (r'\d{4}-\d{1,2}-\d{1,2}', 'iso_date'),
        (r'\d{4}/\d{1,2}/\d{1,2}', 'slash_date'),
        (r'\d{4}年\d{1,2}月', 'year_month')
    ]
    
    for pattern, date_type in patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            dates.append({
                "type": date_type,
                "value": match.group(0),
                "position": match.start()
            })
    
    return dates


def extract_periods(text: str) -> List[Dict[str, Any]]:
    """提取期限信息"""
    periods = []
    
    # 提取时间长度
    period_pattern = r'(\d+)\s*(年|个月?|日|天)'
    matches = re.finditer(period_pattern, text)
    for match in matches:
        value = int(match.group(1))
        unit = match.group(2)
        periods.append({
            "value": value,
            "unit": unit,
            "text": match.group(0),
            "position": match.start()
        })
    
    return periods


def truncate_text(text: str, max_length: int = 200, 
                  suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def highlight_keywords(text: str, keywords: List[str],
                       prefix: str = "【", suffix: str = "】") -> str:
    """高亮关键词"""
    result = text
    for keyword in keywords:
        result = result.replace(keyword, f"{prefix}{keyword}{suffix}")
    return result


# ==================== 数字处理工具 ====================

def chinese_to_arabic(num_str: str) -> int:
    """将中文数字转换为阿拉伯数字"""
    mapping = {
        '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
        '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
        '十': 10, '百': 100, '千': 1000, '万': 10000
    }
    
    if num_str in mapping:
        return mapping[num_str]
    
    result = 0
    temp = 0
    
    for char in num_str:
        if char in mapping:
            value = mapping[char]
            if value >= 10:
                if temp == 0:
                    temp = 1
                result += temp * value
                temp = 0
            else:
                temp = value
    
    result += temp
    return result


def format_currency(amount: Union[int, float], 
                    currency: str = "CNY") -> str:
    """格式化货币"""
    if currency == "CNY":
        return f"¥{amount:,.2f}"
    elif currency == "USD":
        return f"${amount:,.2f}"
    elif currency == "EUR":
        return f"€{amount:,.2f}"
    else:
        return f"{amount:,.2f} {currency}"


def parse_percentage(text: str) -> Optional[float]:
    """解析百分比"""
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if match:
        return float(match.group(1))
    return None


# ==================== 日期处理工具 ====================

def parse_date(text: str) -> Optional[datetime.date]:
    """解析日期文本"""
    patterns = [
        (r'(\d{4})年(\d{1,2})月(\d{1,2})日', '%Y年%m月%d日'),
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),
        (r'(\d{4})/(\d{1,2})/(\d{1,2})', '%Y/%m/%d')
    ]
    
    for pattern, fmt in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.datetime.strptime(match.group(0), fmt).date()
            except ValueError:
                continue
    
    return None


def format_date(date: datetime.date, fmt: str = "%Y年%m月%d日") -> str:
    """格式化日期"""
    return date.strftime(fmt)


def calculate_period(start_date: datetime.date, 
                     end_date: datetime.date) -> Dict[str, int]:
    """计算日期间隔"""
    delta = end_date - start_date
    
    days = delta.days
    years = days // 365
    remaining_days = days % 365
    months = remaining_days // 30
    final_days = remaining_days % 30
    
    return {
        "days": days,
        "years": years,
        "months": months,
        "display_days": final_days
    }


# ==================== 文件处理工具 ====================

def read_file_safe(file_path: str, encoding: str = "utf-8") -> Optional[str]:
    """安全读取文件"""
    try:
        with open(file_path, "r", encoding=encoding) as f:
            return f.read()
    except FileNotFoundError:
        print(f"文件不存在: {file_path}")
        return None
    except UnicodeDecodeError:
        # 尝试其他编码
        for enc in ["gbk", "gb2312", "latin1"]:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except:
                continue
        print(f"文件编码错误: {file_path}")
        return None
    except Exception as e:
        print(f"读取文件失败: {e}")
        return None


def write_file_safe(content: str, file_path: str, 
                    encoding: str = "utf-8") -> bool:
    """安全写入文件"""
    try:
        # 确保目录存在
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"写入文件失败: {e}")
        return False


def get_file_extension(file_path: str) -> str:
    """获取文件扩展名"""
    return Path(file_path).suffix.lower()


def is_contract_file(file_path: str) -> bool:
    """判断是否为合同相关文件"""
    extensions = ['.txt', '.doc', '.docx', '.pdf', '.md']
    ext = get_file_extension(file_path)
    return ext in extensions


# ==================== JSON处理工具 ====================

def load_json_safe(file_path: str) -> Optional[Dict]:
    """安全加载JSON文件"""
    content = read_file_safe(file_path)
    if content:
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"JSON解析失败: {e}")
            return None
    return None


def save_json_safe(data: Any, file_path: str, 
                   indent: int = 2) -> bool:
    """安全保存JSON文件"""
    try:
        content = json.dumps(data, ensure_ascii=False, indent=indent)
        return write_file_safe(content, file_path)
    except Exception as e:
        print(f"JSON保存失败: {e}")
        return False


# ==================== 合同专用工具 ====================

def identify_clause_type(clause_text: str) -> str:
    """识别条款类型"""
    type_keywords = {
        "标的条款": ["标的", "标的物", "服务内容", "工作内容", "租赁物"],
        "价款条款": ["价款", "货款", "租金", "服务费", "报酬", "工资", "支付", "付款"],
        "期限条款": ["期限", "有效期", "起始", "终止", "届满", "续签", "到期"],
        "违约责任": ["违约", "违约金", "赔偿", "补偿"],
        "保密条款": ["保密", "机密", "商业秘密", "泄密"],
        "竞业限制": ["竞业限制", "竞业禁止", "竞争", "同行"],
        "争议解决": ["争议", "纠纷", "仲裁", "诉讼", "管辖", "法院"],
        "不可抗力": ["不可抗力", "自然灾害", "战争", "疫情"],
        "质量条款": ["质量", "标准", "规格", "验收", "检验"],
        "交付条款": ["交付", "交货", "发货", "运输", "送达"]
    }
    
    scores = {}
    for clause_type, keywords in type_keywords.items():
        score = sum(1 for kw in keywords if kw in clause_text)
        scores[clause_type] = score
    
    if scores:
        max_type = max(scores, key=scores.get)
        if scores[max_type] > 0:
            return max_type
    
    return "其他条款"


def calculate_risk_score(description: str, suggestion: str) -> float:
    """计算风险评分"""
    base_score = 5.0
    
    # 关键词权重
    negative_keywords = ["无", "任何", "所有", "无条件", "绝对", "必须", "强制"]
    positive_keywords = ["应当", "可以", "协商", "合理"]
    
    for kw in negative_keywords:
        if kw in description:
            base_score += 1.0
    
    for kw in positive_keywords:
        if kw in description:
            base_score -= 0.5
    
    # 建议的合理性
    if "建议" in suggestion and len(suggestion) > 20:
        base_score -= 0.5
    
    return max(0.0, min(10.0, base_score))


def format_contract_number(contract_type: str, 
                          date: Optional[datetime.date] = None) -> str:
    """生成合同编号"""
    if date is None:
        date = datetime.date.today()
    
    type_codes = {
        "劳动合同": "LD",
        "买卖合同": "MM",
        "租赁合同": "ZL",
        "服务合同": "FW",
        "借款合同": "JK",
        "技术合同": "JS"
    }
    
    code = type_codes.get(contract_type, "QT")
    date_str = date.strftime("%Y%m%d")
    
    return f"HT-{code}-{date_str}"


# ==================== 导出功能 ====================

def export_report(report: Dict, output_path: str, 
                format: str = "markdown") -> bool:
    """导出报告"""
    from scripts.report_generator import ReportGenerator
    
    generator = ReportGenerator()
    content = generator.generate(report, format=format)
    
    # 根据格式确定扩展名
    extensions = {
        "json": ".json",
        "markdown": ".md",
        "html": ".html",
        "text": ".txt"
    }
    
    extension = extensions.get(format, ".txt")
    if not output_path.endswith(extension):
        output_path = output_path + extension
    
    return write_file_safe(content, output_path)


# ==================== 主函数 ====================

if __name__ == "__main__":
    # 测试工具函数
    print("=== 文本处理测试 ===")
    text = "    这是一个   测试文本\t\n"
    print(f"清理后: [{clean_text(text)}]")
    
    print("\n=== 金额提取测试 ===")
    amounts = extract_amounts("合同总价为人民币500万元，预付款为合同总价的20%。")
    print(f"提取到的金额: {amounts}")
    
    print("\n=== 日期提取测试 ===")
    dates = extract_dates("合同期限自2024年1月1日起至2026年12月31日止。")
    print(f"提取到的日期: {dates}")
    
    print("\n=== 条款类型识别测试 ===")
    clause = "乙方离职后两年内不得在同类行业从事相关工作"
    print(f"条款类型: {identify_clause_type(clause)}")
