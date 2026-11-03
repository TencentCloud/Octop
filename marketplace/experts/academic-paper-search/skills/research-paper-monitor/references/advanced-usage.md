# 高级用法示例

## 1. 定时任务设置

### 使用 OpenClaw HEARTBEAT

编辑 `HEARTBEAT.md` 文件：

```markdown
## 每日文献监测
- 时间: 每天 08:00
- 动作: 执行科研文献监测脚本
- 命令: python ~/.openclaw/workspace/skills/research-paper-monitor/scripts/monitor.py

## 每周文献综述
- 时间: 每周一 09:00
- 动作: 生成上周文献综述
- 命令: python ~/.openclaw/workspace/skills/research-paper-monitor/scripts/generate_digest.py --days 7 --output ~/.openclaw/research-monitor/weekly-digest.md
```

### 使用系统 Cron（Linux/Mac）

```bash
# 编辑 crontab
crontab -e

# 添加每日8点执行任务
0 8 * * * /usr/bin/python3 ~/.openclaw/workspace/skills/research-paper-monitor/scripts/monitor.py >> ~/.openclaw/research-monitor/cron.log 2>&1
```

---

## 2. 多研究领域配置

如果你有多个研究方向，可以创建多个配置文件：

```bash
# 主配置
~/.openclaw/research-monitor/config.json

# 副领域配置
~/.openclaw/research-monitor/config-bio.json
```

执行时指定配置：

```bash
# 修改 monitor.py 支持 --config 参数
python monitor.py --config ~/.openclaw/research-monitor/config-bio.json
```

---

## 3. 批量关键词管理

### 从文件导入关键词

创建 `keywords.txt`：
```
deep learning
neural network
computer vision
natural language processing
```

批量更新配置：

```python
import json

with open('keywords.txt') as f:
    keywords = [line.strip() for line in f if line.strip()]

with open('~/.openclaw/research-monitor/config.json') as f:
    config = json.load(f)

config['keywords'] = keywords

with open('~/.openclaw/research-monitor/config.json', 'w') as f:
    json.dump(config, f, indent=2)
```

---

## 4. 自定义推送方式

### 邮件推送

修改 `monitor.py` 中的 `send_feishu_notification` 函数，添加邮件支持：

```python
import smtplib
from email.mime.text import MIMEText

def send_email_notification(papers, email_config):
    msg = MIMEText(format_papers_for_email(papers))
    msg['Subject'] = f'文献监测日报 - {datetime.now().strftime("%Y-%m-%d")}'
    msg['From'] = email_config['from']
    msg['To'] = email_config['to']
    
    with smtplib.SMTP(email_config['smtp_server']) as server:
        server.login(email_config['username'], email_config['password'])
        server.send_message(msg)
```

### 微信推送（企业微信）

```python
import requests

def send_wecom_notification(papers, webhook_key):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    data = {
        "msgtype": "text",
        "text": {
            "content": format_papers_for_wechat(papers)
        }
    }
    requests.post(url, json=data)
```

---

## 5. 数据导出与备份

### 导出为 CSV

```python
import csv
import json

with open('~/.openclaw/research-monitor/literature-index.json') as f:
    index = json.load(f)

with open('papers.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['title', 'authors', 'source', 'url', 'published_date', 'score'])
    writer.writeheader()
    for paper in index['papers']:
        writer.writerow(paper)
```

### 备份到云存储

```bash
# 使用 rclone 备份到云端
rclone sync ~/.openclaw/research-papers/ remote:research-backup/
```

---

## 6. 与 Obsidian 集成

将文献库作为 Obsidian Vault：

```bash
# 创建软链接
ln -s ~/.openclaw/research-papers ~/Documents/ObsidianVault/文献库
```

或使用 Obsidian 的 Daily Notes 插件，将日报自动导入：

```python
# 在 monitor.py 中添加
obsidian_dir = "~/Documents/ObsidianVault/DailyNotes"
shutil.copy(daily_report, obsidian_dir)
```

---

## 7. 关键词效果分析

分析哪些关键词带来了更多相关论文：

```python
import json
from collections import Counter

with open('~/.openclaw/research-monitor/literature-index.json') as f:
    index = json.load(f)

keyword_hits = Counter()
for paper in index['papers']:
    for kw in paper.get('keywords_matched', []):
        keyword_hits[kw] += 1

print("关键词效果排名:")
for kw, count in keyword_hits.most_common():
    print(f"  {kw}: {count} 篇")
```

---

## 8. 论文去重优化

基于 DOI 的去重：

```python
def get_doi_from_url(url):
    """从各种URL格式提取DOI"""
    import re
    doi_pattern = r'10\.\d{4,}/[^\s]+'
    match = re.search(doi_pattern, url)
    return match.group(0) if match else None

def is_duplicate_advanced(paper, index):
    """增强版去重，支持DOI匹配"""
    paper_doi = paper.get('doi') or get_doi_from_url(paper.get('url', ''))
    paper_title = paper.get('title', '').lower().strip()
    
    for existing in index.get('papers', []):
        # DOI 匹配
        if paper_doi and existing.get('doi') == paper_doi:
            return True
        # 标题相似度匹配
        existing_title = existing.get('title', '').lower().strip()
        if similar(paper_title, existing_title) > 0.9:
            return True
    return False

from difflib import SequenceMatcher

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()
```

---

## 9. 与 Zotero 集成

将采集的论文自动导入 Zotero：

```python
import requests

def add_to_zotero(paper, zotero_api_key, user_id):
    """添加论文到 Zotero"""
    url = f"https://api.zotero.org/users/{user_id}/items"
    headers = {
        "Zotero-API-Key": zotero_api_key,
        "Content-Type": "application/json"
    }
    
    data = {
        "itemType": "journalArticle",
        "title": paper['title'],
        "url": paper['url'],
        "date": paper['published_date']
    }
    
    response = requests.post(url, headers=headers, json=data)
    return response.status_code == 200
```

---

## 10. 多用户配置

共享服务器上的多用户配置：

```
~/.openclaw/research-monitor/
├── users/
│   ├── user1/
│   │   ├── config.json
│   │   └── index.json
│   ├── user2/
│   │   ├── config.json
│   │   └── index.json
│   └── shared/
│       └── common-keywords.json
```

执行时指定用户：

```bash
python monitor.py --user user1
```
