# -*- coding: utf-8 -*-
"""
跨境电商商品文案智能生成器（升级版）
Skill标识：cross_border_copywriter_v2
功能：支持多平台、多语种、A/B测试多版本、合规检查、字符长度自动适配的商品文案生成
适用平台：Amazon、SHEIN、Temu、Shopee、TikTok Shop等
支持语言：zh（中文）、en（英文）、es（西班牙语）、fr（法语）、de（德语）、ja（日语）、ar（阿拉伯语）、bilingual（双语）
"""

import json
import re

class CrossBorderCopywriter:
    def __init__(self):
        # 初始化核心配置
        self.platform_char_limit = {
            "Amazon": {"title": 200, "short_description": 150, "long_description": 500, "bullet_point": 100},
            "Temu": {"title": 80, "short_description": 100, "long_description": 300, "bullet_point": 80},
            "SHEIN": {"title": 80, "short_description": 100, "long_description": 300, "bullet_point": 80},
            "TikTok Shop": {"title": 60, "short_description": 80, "long_description": 200, "bullet_point": 70},
            "Shopee": {"title": 120, "short_description": 120, "long_description": 400, "bullet_point": 90}
        }
        
        # 合规词库（侵权词、违禁词，多语种）
        self.compliance_words = {
            "infringement": ["Nike", "Apple", "Adidas", "Gucci", "LV", "Chanel", "Samsung", "Huawei"],
            "prohibited": {
                "common": ["绝对", "最", "第一", "唯一", "根治", "特效", "防爆", "无毒"],
                "es": ["absoluto", "mejor", "primero", "único", "curar", "efecto especial"],
                "fr": ["absolu", "meilleur", "premier", "unique", "guérir", "effet spécial"],
                "de": ["absolut", "bester", "erster", "einzigartig", "heilen", "spezieller Effekt"],
                "ja": ["絶対", "最高", "最初", "唯一", "治す", "特別効果"],
                "ar": ["مطلق", "الأفضل", "الأول", "فريد", "يعالج", "تأثير خاص"]
            }
        }
        
        # 小语种营销话术库
        self.small_language_slogans = {
            "es": {
                "marketing": "¡Oferta Exclusiva! Solo por hoy, descuento del 30% + envío gratuito a todo el país. No te lo pierdas!",
                "professional": "Hecho con materiales de alta calidad, duraderos y seguros, adaptados a tus necesidades diarias.",
                "luxury": "Diseño elegante y exclusivo, eleva tu estilo de vida con detalles exquisitos.",
                "casual": "Producto práctico y económico, ideal para toda la familia, fácil de usar y mantener."
            },
            "fr": {
                "marketing": "Promotion Limitée ! Réduction de 25% + livraison gratuite pour les commandes aujourd’hui.",
                "professional": "Fabriqué avec des matériaux premium, fiable et performant, répondant aux normes européennes.",
                "luxury": "Design chic et sophistiqué, alliant élégance et praticité pour un style unique.",
                "casual": "Produit accessible et polyvalent, parfait pour le quotidien, pour toute la famille."
            },
            "de": {
                "marketing": "Sonderangebot! Nur heute 20% Rabatt + kostenloser Versand in ganz Deutschland. Schnell bestellen!",
                "professional": "Hergestellt aus hochwertigen Materialien, langlebig und sicher, entspricht den höchsten Qualitätsstandards.",
                "luxury": "Elegantes und exklusives Design, kombiniert Luxus und Funktion für einen premium Lebensstil.",
                "casual": "Praktisches und kostengünstiges Produkt, einfach zu bedienen, ideal für den Alltag."
            },
            "ja": {
                "marketing": "限定セール！本日のみ30%オフ＋全国送料無料です、お早めにお申し込みください。",
                "professional": "高品質素材を使用し、耐久性と安全性に優れ、日常のニーズに応えます。",
                "luxury": "エレガントで独特なデザイン、繊細なディテールであなたのライフスタイルを引き上げます。",
                "casual": "実用的で経済的な商品、家族全員に適し、使いやすくメンテナンスも簡単です。"
            },
            "ar": {
                "marketing": "عرض خاص! خصم 25% فقط اليوم + توصيل مجاني إلى جميع أنحاء البلاد، لا تفوّت هذا الفرصة!",
                "professional": "صنوع من المواد عالية الجودة، متينة وآمنة، تُلبي احتياجاتك اليومية.",
                "luxury": "تصميم أنيق وفريد، يرفع مستوى نمط حياتك بالتفاصيل الدقيقة.",
                "casual": "منتج عملي ومريح للسعر، مثالي للعائلة بأكملها، سهل الاستخدام والصيانة."
            }
        }

    def check_compliance(self, content, language="en", category=None):
        """合规检查：检测侵权词、违禁词，返回检查结果及修改建议"""
        compliance_result = {"status": "通过", "suggestion": ""}
        # 检测侵权词
        infringement_words = [word for word in self.compliance_words["infringement"] if word.lower() in content.lower()]
        if infringement_words:
            compliance_result["status"] = "未通过"
            compliance_result["suggestion"] += f"检测到侵权词：{','.join(infringement_words)}，建议替换为同义通用词汇；"
        
        # 检测违禁词
        prohibited_words = self.compliance_words["prohibited"]["common"]
        if language in self.compliance_words["prohibited"]:
            prohibited_words.extend(self.compliance_words["prohibited"][language])
        found_prohibited = [word for word in prohibited_words if word in content]
        if found_prohibited:
            compliance_result["status"] = "未通过"
            compliance_result["suggestion"] += f"检测到违禁词：{','.join(found_prohibited)}，建议替换为合规表达；"
        
        return compliance_result

    def adapt_character_length(self, content, module, platform="Amazon"):
        """字符长度自动适配：根据平台和模块限制，压缩/扩充内容"""
        if platform not in self.platform_char_limit:
            platform = "Amazon"  # 默认适配Amazon
        limit = self.platform_char_limit[platform][module]
        content_length = len(content)
        
        if content_length <= limit:
            # 字符不足，补充核心话术（不堆砌）
            supplement = ""
            if module == "title":
                supplement = " - 品质保障" if len(content) + 10 <= limit else ""
            elif module == "short_description":
                supplement = " 性价比之选" if len(content) + 8 <= limit else ""
            content += supplement
            return content, f"{len(content)}字符（≤{limit}字符，符合{platform}要求）"
        else:
            # 字符超出，压缩冗余词汇，保留核心信息
            content = re.sub(r"\s+", " ", content).strip()
            if len(content) > limit:
                content = content[:limit-3] + "..."
            return content, f"{len(content)}字符（≤{limit}字符，符合{platform}要求）"

    def generate_ab_versions(self, params, version_count=2, diff_type="keyword"):
        """生成A/B测试多版本文案"""
        versions = []
        base_copy = self.generate_single_copy(params)
        
        for i in range(version_count):
            version = chr(65 + i)  # A、B、C、D、E
            copy_data = base_copy.copy()
            copy_data["version"] = version
            
            # 根据差异类型调整文案
            if diff_type == "keyword":
                # 关键词顺序差异
                keywords = params.get("keywords", [])
                if keywords:
                    if i % 2 == 0:
                        copy_data["title"] = f"{keywords[0]} {copy_data['title'].replace(keywords[0], '', 1).strip()}"
                    else:
                        copy_data["title"] = f"{copy_data['title'].replace(keywords[-1], '', 1).strip()} {keywords[-1]}"
            elif diff_type == "tone":
                # 风格差异
                tones = ["professional", "marketing"]
                copy_data["tone"] = tones[i % 2]
                copy_data["short_description"] = self.small_language_slogans.get(params.get("language", "en"), {}).get(tones[i % 2], copy_data["short_description"])
            elif diff_type == "structure":
                # 结构差异
                copy_data["bullet_points"].reverse()
            elif diff_type == "content":
                # 内容侧重点差异
                features = params.get("features", [])
                if features:
                    focus = features[i % len(features)]
                    copy_data["long_description"] = f"{focus}：{copy_data['long_description']}"
            
            # 重新检查合规和字符长度
            copy_data["compliance_check"] = self.check_compliance(copy_data["title"] + copy_data["long_description"], params.get("language", "en"), params.get("category"))
            copy_data["character_adaptation"]["title"] = self.adapt_character_length(copy_data["title"], "title", params.get("platform", "Amazon"))[1]
            copy_data["character_adaptation"]["short_description"] = self.adapt_character_length(copy_data["short_description"], "short_description", params.get("platform", "Amazon"))[1]
            copy_data["character_adaptation"]["long_description"] = self.adapt_character_length(copy_data["long_description"], "long_description", params.get("platform", "Amazon"))[1]
            
            versions.append(copy_data)
        
        return versions

    def generate_single_copy(self, params):
        """生成单版本文案"""
        # 提取输入参数
        product_name = params.get("product_name", "")
        category = params.get("category", "")
        platform = params.get("platform", "Amazon")
        language = params.get("language", "en")
        keywords = params.get("keywords", [])
        features = params.get("features", [])
        tone = params.get("tone", "professional")
        length = params.get("length", "long")
        
        # 生成标题（融入关键词）
        title = f"{product_name} {' '.join(keywords)}" if keywords else product_name
        title, title_char_info = self.adapt_character_length(title, "title", platform)
        
        # 生成短描述
        short_desc = f"{product_name}，{'、'.join(features)}，适合日常使用。" if features else f"{product_name}，品质可靠，性价比高。"
        if language in self.small_language_slogans:
            short_desc = self.small_language_slogans[language].get(tone, short_desc)
        short_desc, short_char_info = self.adapt_character_length(short_desc, "short_description", platform)
        
        # 生成详细描述
        long_desc = f"这款{product_name}属于{category}品类，拥有{'、'.join(features)}等优势，采用高品质材质，适配{platform}平台，满足您的日常需求。"
        long_desc, long_char_info = self.adapt_character_length(long_desc, "long_description", platform)
        
        # 生成卖点列表
        bullet_points = features if features else [f"高品质{product_name}", "适配多场景使用", "合规保障", "平台优化"]
        
        # 生成标签
        tags = keywords + [category, product_name] if keywords and category else [product_name]
        tags = list(set(tags))[:4]  # 去重，保留前4个
        
        # 合规检查
        compliance_check = self.check_compliance(title + short_desc + long_desc, language, category)
        
        return {
            "title": title,
            "short_description": short_desc,
            "long_description": long_desc,
            "bullet_points": bullet_points,
            "tags": tags,
            "language": language,
            "platform_fit": platform,
            "compliance_check": compliance_check,
            "character_adaptation": {
                "title": title_char_info,
                "short_description": short_char_info,
                "long_description": long_char_info
            }
        }

    def generate_copy(self, params):
        """主生成函数：根据参数生成单版本/多版本文案"""
        ab_version = params.get("ab_version", 1)
        ab_diff_type = params.get("ab_diff_type", "keyword")
        
        if ab_version >= 2:
            return {
                "ab_version_count": ab_version,
                "ab_diff_type": ab_diff_type,
                "versions": self.generate_ab_versions(params, ab_version, ab_diff_type)
            }
        else:
            return {
                "ab_version_count": 1,
                "ab_diff_type": ab_diff_type,
                "versions": [self.generate_single_copy(params)]
            }

# 测试代码
if __name__ == "__main__":
    test_params = {
        "product_name": "便携式无线蓝牙耳机",
        "category": "3C数码",
        "platform": "Amazon",
        "language": "de",
        "keywords": ["drahtlose Ohrhörer", "Bluetooth 5.3", "Rauschunterdrückung", "24h Spielzeit"],
        "features": ["降噪", "长续航", "轻便", "防水", "触控"],
        "tone": "professional",
        "length": "long",
        "ab_version": 2,
        "ab_diff_type": "keyword"
    }
    writer = CrossBorderCopywriter()
    result = writer.generate_copy(test_params)
    print(json.dumps(result, ensure_ascii=False, indent=2))
