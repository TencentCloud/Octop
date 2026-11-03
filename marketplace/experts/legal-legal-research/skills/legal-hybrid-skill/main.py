# -*- coding: utf-8 -*-
import json
import requests

class Skill:
    def __init__(self):
        self.name = "智能法律助手(官方API+本地兜底)"
        self.desc = "优先国家法律法规数据库API查询，失败自动切换本地库"
        self.version = "2.1"
        self.author = "doubao"
        self.timeout = 8

        # 本地兜底库
        self.law_db = self._load_json("law_db.json")
        self.case_db = self._load_json("case_db.json")

        # 你指定的 官方可用API（无密钥）
        self.api_url = "https://flk.npc.gov.cn/api/"

    def _load_json(self, fn):
        try:
            with open(fn, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def _api_search(self, query):
        """调用官方法律API"""
        params = {
            "type": "flfg",
            "searchType": "title;vague",
            "keyword": query,
            "page": "1",
            "size": "5"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            r = requests.get(self.api_url, params=params, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except:
            return None

    def _search_local_laws(self, query):
        """本地法条兜底搜索"""
        matches = []
        for name, content in self.law_db.items():
            if query in name or query in content:
                matches.append({"name": name, "content": content})
        return matches

    def _search_local_cases(self, query):
        """本地案例兜底搜索（完美适配你的case_db.json）"""
        matches = []
        for case in self.case_db:
            keywords = " ".join(case.get("keywords", []))
            text = " ".join([
                case.get("title", ""),
                keywords,
                case.get("fact", ""),
                case.get("judgement", "")
            ])
            if query in text:
                matches.append(case)
        return matches

    def run(self, query):
        query = query.strip()
        if not query:
            return "请输入法律问题关键词，例如：试用期辞退、借钱不还、工伤、租房押金"

        # ===================== 1. 优先走官方API =====================
        law_list = []
        api_data = self._api_search(query)

        if api_data and api_data.get("code") == 200 and api_data.get("data"):
            for item in api_data["data"].get("list", []):
                title = item.get("title", "未命名")
                content = item.get("content", "").replace("<br>", "\n").strip()
                law_list.append({"name": title, "content": content})

        # ===================== 2. API无结果 → 本地法条兜底 =====================
        if not law_list:
            law_list = self._search_local_laws(query)

        # ===================== 3. 本地案例兜底（ always 可用） =====================
        case_list = self._search_local_cases(query)

        # ===================== 4. 输出格式化结果 =====================
        output = []

        if law_list:
            output.append("📜 法律条文：")
            for law in law_list:
                output.append(f"【{law['name']}】")
                output.append(law["content"])
                output.append("")

        if case_list:
            output.append("⚖️ 参考案例：")
            for idx, case in enumerate(case_list, 1):
                output.append(f"【案例{idx}】{case['title']}")
                output.append(f"案情：{case['fact']}")
                output.append(f"判决：{case['judgement']}")
                output.append(f"依据法条：{', '.join(case['laws'])}")
                output.append("")

        if not output:
            return "未找到相关内容，请换个关键词试试。"

        return "\n".join(output)