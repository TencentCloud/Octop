"""
CBT心理治疗师 - 记忆增强模块

功能：
1. 持久化存储所有对话历史
2. 自动提取关键标签（认知扭曲类型、核心议题）
3. 提供上下文检索，支持跨会话连续性
4. 生成记忆增强的回应提示

使用方法：
    from cbt_memory import CBTMemoryManager
    
    memory = CBTMemoryManager(user_id="user_001")
    memory.save_turn(user_input, therapist_response, tags=["焦虑", "工作压力"])
    context = memory.get_context_for_session()
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import re


class CBTMemoryManager:
    """CBT记忆管理器 - 长期记忆与上下文检索"""
    
    # CBT核心关键词库
    COGNITIVE_DISTORTIONS = {
        "全或无思维": ["全或无", "非黑即白", "要么全部要么没有", "完美主义", "不允许犯错"],
        "灾难化": ["灾难", "完蛋", "肯定完", "一定会失败", "最坏的结果", "万一"],
        "读心术": ["他们肯定觉得", "他知道我在想", "别人一定认为", "他们都看不起我"],
        "贴标签": ["我是个失败者", "我很蠢", "我一无是处", "我是个loser"],
        "选择性注意": ["只记得", "只看到", "从来没有人", "总是", "每次都"],
        "情绪推理": ["我感觉所以我就是", "我觉得不对劲所以肯定有问题"],
        "应该陈述": ["应该", "必须", "一定", "不得不", "理应"],
        "过度概括": ["所有", "每个人", "没有人", "从来不", "总是"],
        "贬低积极": ["那不算什么", "只是运气好", "这没什么", "谁都能做到"],
        "个人化": ["都是我的错", "怪我", "因为我"],
    }
    
    EMOTION_KEYWORDS = [
        "焦虑", "抑郁", "愤怒", "恐惧", "悲伤", "孤独", "羞耻", "内疚",
        "无力", "绝望", "紧张", "担忧", "烦躁", "沮丧", "失落", "空虚"
    ]
    
    TOPIC_KEYWORDS = {
        "工作": ["工作", "领导", "同事", "项目", "deadline", "加班", "裁员", "升职"],
        "关系": ["伴侣", "男朋友", "女朋友", "老公", "老婆", "父母", "朋友", "家人"],
        "健康": ["生病", "身体", "睡眠", "失眠", "焦虑症", "抑郁症", "吃药"],
        "自我": ["自尊", "自信", "自我价值", "人生意义", "我不知道我是谁"],
        "学业": ["考试", "学习", "成绩", "毕业", "论文", "导师"],
    }
    
    def __init__(self, user_id: str, storage_dir: str = None):
        """
        初始化记忆管理器
        
        Args:
            user_id: 用户唯一标识
            storage_dir: 存储目录，默认为 workspace/cbt-sessions/
        """
        self.user_id = user_id
        self.storage_dir = storage_dir or os.path.join(
            os.path.expanduser("~"), ".qclaw", "workspace", "cbt-sessions"
        )
        os.makedirs(self.storage_dir, exist_ok=True)
        
        self.history_file = os.path.join(self.storage_dir, f"history_{user_id}.json")
        self.summary_file = os.path.join(self.storage_dir, f"summary_{user_id}.json")
        
        self.conversation_history: List[Dict] = self._load_history()
        self.session_summary: Dict = self._load_summary()
    
    def _load_history(self) -> List[Dict]:
        """加载完整对话历史"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []
    
    def _load_summary(self) -> Dict:
        """加载用户档案摘要"""
        if os.path.exists(self.summary_file):
            try:
                with open(self.summary_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return self._default_summary()
        return self._default_summary()
    
    def _default_summary(self) -> Dict:
        """创建默认摘要结构"""
        return {
            "user_id": self.user_id,
            "first_session": None,
            "total_sessions": 0,
            "total_turns": 0,
            "core_beliefs": [],  # 核心信念列表
            "cognitive_patterns": {},  # 认知扭曲频率统计
            "main_topics": {},  # 主要议题统计
            "emotion_trends": [],  # 情绪趋势 [(date, score)]
            "milestones": [],  # 治疗里程碑
            "last_session_date": None,
            "treatment_goals": [],  # 治疗目标
        }
    
    def save_turn(self, user_input: str, therapist_response: str, 
                  emotion_score: Optional[int] = None,
                  session_number: Optional[int] = None):
        """
        保存单轮对话记录
        
        Args:
            user_input: 用户输入
            therapist_response: 治疗师回应
            emotion_score: 情绪评分 (1-10)
            session_number: 会话编号
        """
        # 提取关键信息
        tags = self._extract_tags(user_input)
        cognitive_distortions = self._detect_cognitive_distortions(user_input)
        topics = self._detect_topics(user_input)
        emotions = self._detect_emotions(user_input)
        
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_number": session_number,
            "user": user_input,
            "therapist": therapist_response,
            "emotion_score": emotion_score,
            "tags": tags,
            "cognitive_distortions": cognitive_distortions,
            "topics": topics,
            "emotions": emotions,
        }
        
        self.conversation_history.append(record)
        self._update_summary(record)
        self._persist()
    
    def _extract_tags(self, text: str) -> List[str]:
        """提取关键词标签"""
        tags = []
        
        # 检测认知扭曲
        for distortion, keywords in self.COGNITIVE_DISTORTIONS.items():
            for kw in keywords:
                if kw in text:
                    tags.append(f"认知扭曲:{distortion}")
                    break
        
        # 检测情绪
        for emotion in self.EMOTION_KEYWORDS:
            if emotion in text:
                tags.append(f"情绪:{emotion}")
        
        # 检测议题
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    tags.append(f"议题:{topic}")
                    break
        
        return list(set(tags))
    
    def _detect_cognitive_distortions(self, text: str) -> List[str]:
        """检测认知扭曲类型"""
        detected = []
        for distortion, keywords in self.COGNITIVE_DISTORTIONS.items():
            for kw in keywords:
                if kw in text:
                    detected.append(distortion)
                    break
        return detected
    
    def _detect_topics(self, text: str) -> List[str]:
        """检测主要议题"""
        detected = []
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    detected.append(topic)
                    break
        return detected
    
    def _detect_emotions(self, text: str) -> List[str]:
        """检测情绪词"""
        return [e for e in self.EMOTION_KEYWORDS if e in text]
    
    def _update_summary(self, record: Dict):
        """更新用户档案摘要"""
        now = datetime.now()
        
        if self.session_summary["first_session"] is None:
            self.session_summary["first_session"] = now.isoformat()
        
        self.session_summary["total_turns"] += 1
        self.session_summary["last_session_date"] = now.isoformat()
        
        # 更新认知模式统计
        for cd in record.get("cognitive_distortions", []):
            self.session_summary["cognitive_patterns"][cd] = \
                self.session_summary["cognitive_patterns"].get(cd, 0) + 1
        
        # 更新议题统计
        for topic in record.get("topics", []):
            self.session_summary["main_topics"][topic] = \
                self.session_summary["main_topics"].get(topic, 0) + 1
        
        # 更新情绪趋势
        if record.get("emotion_score"):
            self.session_summary["emotion_trends"].append({
                "date": now.strftime("%Y-%m-%d"),
                "score": record["emotion_score"]
            })
    
    def _persist(self):
        """持久化存储"""
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
        
        with open(self.summary_file, 'w', encoding='utf-8') as f:
            json.dump(self.session_summary, f, ensure_ascii=False, indent=2)
    
    def get_recent_context(self, turn_count: int = 5) -> List[Dict]:
        """获取最近N轮对话"""
        return self.conversation_history[-turn_count:] if self.conversation_history else []
    
    def get_context_by_topic(self, topic: str, limit: int = 10) -> List[Dict]:
        """按议题检索历史对话"""
        results = []
        for record in reversed(self.conversation_history):
            if topic in record.get("topics", []):
                results.append(record)
                if len(results) >= limit:
                    break
        return results
    
    def get_context_by_distortion(self, distortion: str, limit: int = 10) -> List[Dict]:
        """按认知扭曲类型检索历史对话"""
        results = []
        for record in reversed(self.conversation_history):
            if distortion in record.get("cognitive_distortions", []):
                results.append(record)
                if len(results) >= limit:
                    break
        return results
    
    def get_context_for_session(self) -> str:
        """
        生成会话开始时的上下文摘要
        用于在每次会话开始时快速回顾重要信息
        """
        if not self.conversation_history:
            return "【首次会话】这是来访者的首次咨询，尚无历史记录。"
        
        summary_parts = []
        
        # 基本信息
        total_sessions = self.session_summary.get("total_sessions", 0)
        total_turns = self.session_summary.get("total_turns", 0)
        summary_parts.append(f"【来访档案】共 {total_turns} 轮对话")
        
        # 高频认知模式
        patterns = self.session_summary.get("cognitive_patterns", {})
        if patterns:
            top_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:3]
            summary_parts.append(f"【常见认知模式】{', '.join([p[0] for p in top_patterns])}")
        
        # 主要议题
        topics = self.session_summary.get("main_topics", {})
        if topics:
            top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:3]
            summary_parts.append(f"【主要议题】{', '.join([t[0] for t in top_topics])}")
        
        # 最近对话摘要
        recent = self.get_recent_context(3)
        if recent:
            summary_parts.append("【最近对话】")
            for r in recent[-3:]:
                summary_parts.append(f"  - 用户: {r['user'][:50]}...")
        
        # 核心信念（如果有记录）
        core_beliefs = self.session_summary.get("core_beliefs", [])
        if core_beliefs:
            summary_parts.append(f"【已识别的核心信念】{'; '.join(core_beliefs[:3])}")
        
        return "\n".join(summary_parts)
    
    def add_core_belief(self, belief: str):
        """添加识别到的核心信念"""
        if belief not in self.session_summary["core_beliefs"]:
            self.session_summary["core_beliefs"].append(belief)
            self._persist()
    
    def add_milestone(self, milestone: str):
        """添加治疗里程碑"""
        self.session_summary["milestones"].append({
            "date": datetime.now().isoformat(),
            "description": milestone
        })
        self._persist()
    
    def set_treatment_goals(self, goals: List[str]):
        """设置/更新治疗目标"""
        self.session_summary["treatment_goals"] = goals
        self._persist()
    
    def increment_session_count(self):
        """增加会话计数"""
        self.session_summary["total_sessions"] += 1
        self._persist()
    
    def search_history(self, query: str, limit: int = 10) -> List[Dict]:
        """
        搜索历史对话
        
        Args:
            query: 搜索关键词
            limit: 返回结果数量限制
        
        Returns:
            匹配的对话记录列表
        """
        results = []
        query_lower = query.lower()
        
        for record in reversed(self.conversation_history):
            if (query_lower in record.get("user", "").lower() or
                query_lower in record.get("therapist", "").lower() or
                any(query_lower in tag.lower() for tag in record.get("tags", []))):
                results.append(record)
                if len(results) >= limit:
                    break
        
        return results


# 便捷函数
def create_memory_manager(user_id: str = "default") -> CBTMemoryManager:
    """创建记忆管理器实例"""
    return CBTMemoryManager(user_id)


if __name__ == "__main__":
    # 测试代码
    mm = CBTMemoryManager("test_user")
    
    # 模拟保存几轮对话
    mm.save_turn(
        "我最近工作压力很大，总是担心会犯错被领导批评",
        "我理解这种压力。能具体说说你最担心的是什么吗？",
        emotion_score=6,
        session_number=1
    )
    
    mm.save_turn(
        "我担心一旦犯错就会被裁员，那样我就完蛋了",
        "这是灾难化的思维。我们来检验一下，过去你犯过错误吗？结果如何？",
        emotion_score=7,
        session_number=1
    )
    
    # 打印上下文
    print(mm.get_context_for_session())
    
    # 添加核心信念
    mm.add_core_belief("犯错=灾难/被抛弃")
    
    # 搜索历史
    results = mm.search_history("犯错")
    print(f"找到 {len(results)} 条相关记录")
