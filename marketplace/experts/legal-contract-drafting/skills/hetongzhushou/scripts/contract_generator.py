"""
合同生成脚本
Contract Generator Script

功能：支持多种方式生成合同
1. 模板选择模式：从100+模板库选择
2. AI智能起草：根据需求描述自动生成
3. 对话引导填写：逐步引导用户输入合同信息
4. 条款建议：针对特定场景提供专业条款
"""

import json
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class ContractTemplate:
    """合同模板"""
    id: str
    name: str
    category: str
    applicable_scenarios: List[str]
    special_clauses: List[str]
    content: str
    required_fields: List[Dict]


@dataclass
class GeneratedContract:
    """生成的合同"""
    template_id: str
    contract_type: str
    sections: Dict[str, str]
    filled_fields: Dict[str, Any]
    raw_text: str
    warnings: List[str]


class ContractGenerator:
    """合同生成器"""
    
    def __init__(self):
        self.template_library = self._init_template_library()
    
    def generate_from_template(self, template_id: str, 
                               fields: Dict[str, Any]) -> GeneratedContract:
        """
        从模板生成合同
        
        Args:
            template_id: 模板ID
            fields: 填充字段
            
        Returns:
            生成的合同对象
        """
        template = self.template_library.get(template_id)
        if not template:
            raise ValueError(f"模板不存在: {template_id}")
        
        # 填充模板
        filled_text = template.content
        filled_fields = {}
        
        for field_name, field_value in fields.items():
            placeholder = f"{{{field_name}}}"
            filled_text = filled_text.replace(placeholder, str(field_value))
            filled_fields[field_name] = field_value
        
        # 生成合同编号
        import datetime
        contract_no = f"HT-{datetime.datetime.now().strftime('%Y%m%d')}-{template_id}"
        filled_text = filled_text.replace("{合同编号}", contract_no)
        
        # 提取章节
        sections = self._extract_sections(filled_text)
        
        # 检查警告
        warnings = self._check_warnings(filled_text, template)
        
        return GeneratedContract(
            template_id=template_id,
            contract_type=template.category,
            sections=sections,
            filled_fields=filled_fields,
            raw_text=filled_text,
            warnings=warnings
        )
    
    def suggest_clauses(self, scenario: str, clause_type: str) -> List[Dict]:
        """
        提供条款建议
        
        Args:
            scenario: 使用场景
            clause_type: 条款类型
            
        Returns:
            条款建议列表
        """
        suggestions = {
            "保密条款": {
                "推荐版本": {
                    "name": "平衡保护版本",
                    "content": """双方确认，乙方在任职期间接触的甲方商业秘密包括但不限于：
（一）客户名单、联系方式及需求信息；
（二）技术方案、软件源代码及算法；
（三）财务数据、经营策略及商业计划；
（四）其他经甲方标注为保密的信息。

保密期限：乙方离职后2年内仍需履行保密义务。
违约责任：乙方违反保密义务的，应向甲方支付违约金，金额为乙方离职前12个月平均工资的3倍。""",
                    "applicable": "适用于普通技术岗位"
                },
                "强保护版本": {
                    "name": "强保护版本",
                    "content": """双方确认，乙方在任职期间及离职后均需遵守保密义务。

保密范围包括但不限于：
（一）前款所列全部内容；
（二）经营策略、供应商信息、采购价格；
（三）员工薪酬体系、内部培训资料；
（四）甲方关联公司的商业信息。

保密期限：乙方离职后3年内。
违约金：乙方违反保密义务的，应支付不低于实际损失3倍的违约金。""",
                    "applicable": "适用于高级管理人员、核心技术人员"
                },
                "简化版本": {
                    "name": "简化版本",
                    "content": """乙方应当对在工作期间知悉的甲方商业秘密予以保密，不得向任何第三方披露或使用。

保密期限：劳动关系存续期间。
违约责任：乙方违反保密义务给甲方造成损失的，应当承担赔偿责任。""",
                    "applicable": "适用于普通行政岗位"
                }
            },
            "竞业限制条款": {
                "推荐版本": {
                    "name": "标准竞业限制版本",
                    "content": """乙方离职后，在竞业限制期限内不得从事与甲方有竞争关系的业务：

一、竞业限制范围
乙方竞业限制的范围为：与甲方生产或经营同类产品、从事同类业务的有竞争关系的其他用人单位。

二、竞业限制期限
竞业限制期限为：乙方离职后不超过2年。

三、经济补偿
甲方在竞业限制期内按月向乙方支付经济补偿，标准为乙方离职前12个月平均工资的30%。

四、违约责任
乙方违反竞业限制约定的，应当按照甲方已支付经济补偿总额的3倍向甲方支付违约金。""",
                    "applicable": "适用于大多数情形"
                }
            },
            "违约责任条款": {
                "标准版本": {
                    "name": "标准违约责任版本",
                    "content": """一、甲方违约责任
甲方未按约定支付价款的，每逾期一日，应按未付款项的0.05%向乙方支付违约金。

二、乙方违约责任
（一）逾期交货的，每逾期一日，按合同总价的0.05%向甲方支付违约金；
（二）货物不符合质量标准的，乙方应负责退换货，并赔偿甲方因此造成的损失。

三、违约金上限
双方确认，任何一方向对方支付的违约金总额不超过合同总价款的30%。""",
                    "applicable": "买卖/服务合同适用"
                }
            }
        }
        
        if clause_type in suggestions:
            return [asdict(v) for v in suggestions[clause_type].values()]
        return []
    
    def generate_with_ai(self, requirements: str, 
                         contract_type: str) -> Dict[str, Any]:
        """
        AI智能起草合同框架
        
        Args:
            requirements: 需求描述
            contract_type: 合同类型
            
        Returns:
            合同框架和建议
        """
        # 分析需求，提取关键信息
        key_info = self._extract_key_info(requirements)
        
        # 生成推荐结构
        structure = self._generate_structure(contract_type, key_info)
        
        # 生成关键条款建议
        key_clauses = self._generate_key_clauses(contract_type, key_info)
        
        return {
            "extracted_info": key_info,
            "recommended_structure": structure,
            "key_clauses": key_clauses,
            "customization_notes": self._generate_customization_notes(key_info)
        }
    
    def _init_template_library(self) -> Dict[str, ContractTemplate]:
        """初始化模板库"""
        templates = {}
        
        # 劳动合同模板
        templates["labor_standard"] = ContractTemplate(
            id="labor_standard",
            name="标准劳动合同",
            category="劳动人事类",
            applicable_scenarios=["普通员工入职", "新员工签订"],
            special_clauses=["基础条款完整"],
            content="""{合同编号}
劳动合同

甲方（用人单位）：{甲方名称}
统一社会信用代码：{甲方代码}
法定代表人：{甲方法人}
地址：{甲方地址}

乙方（劳动者）：{乙方姓名}
身份证号码：{乙方身份证}
联系电话：{乙方电话}
地址：{乙方地址}

根据《中华人民共和国劳动法》、《中华人民共和国劳动合同法》及相关法律法规的规定，甲乙双方经平等自愿、协商一致，订立本合同。

第一条 合同期限
一、本合同为有固定期限劳动合同。
二、合同期限为{合同期限}，自{开始日期}起至{结束日期}止。
三、试用期{试用期}，试用期包含在合同期内。

第二条 工作内容和工作地点
一、乙方同意在甲方{部门}部门从事{岗位}工作。
二、乙方的工作地点为{工作地点}。
三、乙方应按照甲方安排的工作内容和要求，完成工作任务。

第三条 工作时间和休息休假
一、甲方实行标准工时制，即每日工作{每日工时}小时，每周工作{每周工时}天。
二、甲方应保证乙方每周至少休息一日。
三、法定节假日按国家规定执行。

第四条 劳动报酬
一、乙方月工资为税前{月薪}元。
二、甲方于每月{发薪日}日前以{支付方式}支付乙方工资。
三、乙方加班应按照法律规定支付加班工资。

第五条 社会保险和福利待遇
一、甲乙双方应按国家和当地政府的规定参加社会保险。
二、乙方应缴纳的社会保险费由甲方代扣代缴。
三、甲方应根据企业经济效益情况，逐步提高乙方福利待遇。

第六条 劳动保护和职业培训
一、甲方应建立健全劳动安全卫生制度，对乙方进行劳动安全卫生教育。
二、甲方应为乙方提供符合国家规定的劳动安全卫生条件和必要的劳动保护用品。

第七条 规章制度和劳动纪律
一、乙方应遵守甲方依法制定的规章制度和劳动纪律。
二、甲方有权根据经营需要依法制定、修改规章制度。

第八条 合同的变更、解除和终止
一、经甲乙双方协商一致，可以变更本合同。
二、有下列情形之一的，甲方可以解除本合同：
   （一）...（详见劳动合同法）
三、有下列情形之一的，本合同终止：
   （一）...（详见劳动合同法）

第九条 违约责任
甲乙双方任何一方违反本合同约定的，应当依法承担相应的违约责任。

第十条 保密条款
{保密条款内容}

第十一条 竞业限制条款
{竞业限制条款内容}

第十二条 争议解决
因本合同引起的争议，双方应协商解决；协商不成的，可以向劳动争议仲裁委员会申请仲裁。

第十三条 其他约定
{其他约定}

甲方（盖章）：{甲方公章}
法定代表人（签字）：
日期：{签订日期}

乙方（签字）：{乙方签字}
日期：{签订日期}
""",
            required_fields=[
                {"name": "甲方名称", "type": "text", "required": True},
                {"name": "甲方代码", "type": "text", "required": True},
                {"name": "甲方法人", "type": "text", "required": True},
                {"name": "甲方地址", "type": "text", "required": True},
                {"name": "乙方姓名", "type": "text", "required": True},
                {"name": "乙方身份证", "type": "text", "required": True},
                {"name": "乙方电话", "type": "text", "required": True},
                {"name": "合同期限", "type": "text", "required": True},
                {"name": "试用期", "type": "text", "required": True},
                {"name": "月薪", "type": "number", "required": True}
            ]
        )
        
        # 买卖合同模板
        templates["sale_standard"] = ContractTemplate(
            id="sale_standard",
            name="标准商品买卖合同",
            category="买卖交易类",
            applicable_scenarios=["一般商品交易", "批发零售"],
            special_clauses=["质量标准", "验收条款", "违约责任"],
            content="""{合同编号}
商品买卖合同

买方（甲方）：{买方名称}
统一社会信用代码：{买方代码}
法定代表人：{买方法人}

卖方（乙方）：{卖方名称}
统一社会信用代码：{卖方代码}
法定代表人：{卖方法人}

根据《中华人民共和国民法典》及相关法律法规的规定，甲乙双方经友好协商，就甲方向乙方购买商品事宜，达成如下协议：

第一条 标的物
甲方向乙方购买以下商品：
{商品清单}

第二条 质量标准
一、商品质量应符合国家标准GB/T {质量标准号}。
二、商品应具有完整的功能和性能，符合产品说明书描述。
三、商品应配备必要的配件、说明书、保修卡。

第三条 价款及支付方式
一、合同总价为人民币（大写）{总价}元整（¥{总价数字}）。
二、付款方式：{付款方式}
三、付款期限：{付款期限}

第四条 交付时间、地点和方式
一、交货时间：{交货时间}
二、交货地点：{交货地点}
三、运输方式：{运输方式}
四、运费承担：{运费承担}

第五条 验收
一、甲方应在收到商品后{验收期限}日内进行验收。
二、验收标准：以本合同约定的质量标准为准。
三、验收方式：按国家标准和行业惯例进行。

第六条 违约责任
一、甲方逾期付款的，每逾期一日按未付款项的0.05%支付违约金。
二、乙方逾期交货的，每逾期一日按合同总价的0.05%支付违约金。
三、商品不符合质量标准的，乙方应负责退换货，并赔偿甲方因此造成的损失。

第七条 争议解决
因本合同引起的争议，双方应协商解决；协商不成的，提交{管辖机构}。

第八条 其他约定
{其他约定}

甲方（盖章）：{甲方公章}
日期：{签订日期}

乙方（盖章）：{乙方公章}
日期：{签订日期}
""",
            required_fields=[
                {"name": "买方名称", "type": "text", "required": True},
                {"name": "卖方名称", "type": "text", "required": True},
                {"name": "商品清单", "type": "textarea", "required": True},
                {"name": "总价", "type": "number", "required": True}
            ]
        )
        
        # 租赁合同模板
        templates["rental_standard"] = ContractTemplate(
            id="rental_standard",
            name="房屋租赁合同",
            category="租赁物业类",
            applicable_scenarios=["住宅租赁", "商铺租赁", "办公室租赁"],
            special_clauses=["租金支付", "押金条款", "维修责任", "提前解约"],
            content="""{合同编号}
房屋租赁合同

出租方（甲方）：{出租方名称}
身份证号码：{出租方证件号}
联系电话：{出租方电话}

承租方（乙方）：{承租方名称}
身份证号码：{承租方证件号}
联系电话：{承租方电话}

根据《中华人民共和国民法典》及相关法律法规的规定，甲乙双方经协商一致，就房屋租赁事宜，达成如下协议：

第一条 租赁物
甲方将位于{房屋地址}的房屋出租给乙方使用。
房屋基本情况：{房屋描述}
房屋用途：{使用用途}

第二条 租赁期限
一、租赁期限为{租赁期限}，自{开始日期}起至{结束日期}止。
二、租赁期满，甲方有权收回房屋，乙方应如期返还。

第三条 租金及支付方式
一、租金标准：月租金人民币{月租金}元整。
二、押金：乙方应向甲方支付押金人民币{押金}元。
三、支付方式：{支付方式}
四、支付时间：乙方应在每{付款周期}的{付款日}日前支付租金。

第四条 维修责任
一、甲方应保证出租房屋及附属设施符合正常使用状态。
二、小修由乙方负责，费用由乙方承担。
三、因甲方原因造成房屋损坏的，由甲方负责维修并承担费用。

第五条 提前解约
一、甲方提前收回房屋的，应提前{甲方提前通知天数}日通知乙方，并退还剩余租金和押金。
二、乙方提前退租的，应提前{乙方提前通知天数}日通知甲方，并支付{违约金}作为违约金。

第六条 争议解决
因本合同引起的争议，双方应协商解决；协商不成的，提交{管辖机构}。

甲方（签字）：{甲方签字}
日期：{签订日期}

乙方（签字）：{乙方签字}
日期：{签订日期}
""",
            required_fields=[
                {"name": "出租方名称", "type": "text", "required": True},
                {"name": "承租方名称", "type": "text", "required": True},
                {"name": "房屋地址", "type": "text", "required": True},
                {"name": "月租金", "type": "number", "required": True},
                {"name": "押金", "type": "number", "required": True}
            ]
        )
        
        return templates
    
    def _extract_sections(self, text: str) -> Dict[str, str]:
        """提取合同章节"""
        sections = {}
        
        # 按条款分割
        clause_pattern = r'第[零一二三四五六七八九十百\d]+条\s*[^\n]+'
        matches = list(re.finditer(clause_pattern, text))
        
        for i, match in enumerate(matches):
            clause_title = match.group(0)
            start = match.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(text)
            clause_content = text[start:min(end, start+500)].strip()
            
            sections[clause_title] = clause_content
        
        return sections
    
    def _check_warnings(self, text: str, template: ContractTemplate) -> List[str]:
        """检查警告信息"""
        warnings = []
        
        # 检查未填充的占位符
        unfilled = re.findall(r'\{[^}]+\}', text)
        if unfilled:
            warnings.append(f"存在未填充字段: {', '.join(unfilled)}")
        
        # 检查关键条款是否缺失
        key_clauses = ["违约责任", "争议解决", "保密"]
        for clause in key_clauses:
            if clause not in text:
                warnings.append(f"建议添加{clause}条款")
        
        return warnings
    
    def _extract_key_info(self, requirements: str) -> Dict[str, Any]:
        """从需求中提取关键信息"""
        info = {}
        
        # 提取金额
        amount_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:万|亿|元)', requirements)
        if amount_match:
            info["金额"] = amount_match.group(0)
        
        # 提取期限
        period_match = re.search(r'(\d+)\s*(?:年|个月?|日)', requirements)
        if period_match:
            info["期限"] = period_match.group(0)
        
        # 提取人员姓名
        name_match = re.search(r'(?:叫|姓|名为|姓名)[:：]?\s*([^\s，,。]+)', requirements)
        if name_match:
            info["姓名"] = name_match.group(1)
        
        # 提取公司名称
        company_match = re.search(r'([^\s公司企业厂社]+(?:公司|企业|厂|合作社))', requirements)
        if company_match:
            info["公司名称"] = company_match.group(1)
        
        return info
    
    def _generate_structure(self, contract_type: str, 
                            key_info: Dict) -> List[str]:
        """生成推荐合同结构"""
        structures = {
            "劳动合同": [
                "第一条 合同期限",
                "第二条 工作内容和工作地点",
                "第三条 工作时间和休息休假",
                "第四条 劳动报酬",
                "第五条 社会保险和福利待遇",
                "第六条 劳动保护和职业培训",
                "第七条 规章制度和劳动纪律",
                "第八条 合同的变更、解除和终止",
                "第九条 违约责任",
                "第十条 保密条款",
                "第十一条 竞业限制条款",
                "第十二条 争议解决",
                "第十三条 其他约定"
            ],
            "买卖合同": [
                "第一条 标的物",
                "第二条 质量标准",
                "第三条 价款及支付方式",
                "第四条 交付时间、地点和方式",
                "第五条 验收",
                "第六条 违约责任",
                "第七条 争议解决",
                "第八条 其他约定"
            ],
            "租赁合同": [
                "第一条 租赁物",
                "第二条 租赁期限",
                "第三条 租金及支付方式",
                "第四条 维修责任",
                "第五条 提前解约",
                "第六条 争议解决"
            ]
        }
        
        return structures.get(contract_type, [])
    
    def _generate_key_clauses(self, contract_type: str, 
                              key_info: Dict) -> List[Dict]:
        """生成关键条款建议"""
        suggestions = []
        
        if contract_type == "劳动合同":
            suggestions.append({
                "type": "保密条款",
                "suggestion": "建议根据岗位性质选择合适的保密条款版本",
                "options": ["标准版", "强化版", "简化版"]
            })
            suggestions.append({
                "type": "竞业限制条款",
                "suggestion": "如涉及核心技术人员，建议添加竞业限制条款",
                "options": ["标准竞业限制", "简化竞业限制", "不约定竞业限制"]
            })
        
        return suggestions
    
    def _generate_customization_notes(self, key_info: Dict) -> List[str]:
        """生成定制注意事项"""
        notes = []
        
        if "金额" in key_info:
            notes.append(f"涉及金额：{key_info['金额']}，建议明确约定支付方式和期限")
        
        if "期限" in key_info:
            notes.append(f"涉及期限：{key_info['期限']}，需明确起止日期")
        
        notes.append("请根据实际情况补充完整合同信息")
        
        return notes
    
    def list_templates(self, category: Optional[str] = None) -> List[Dict]:
        """列出模板库"""
        result = []
        
        for template_id, template in self.template_library.items():
            if category is None or template.category == category:
                result.append({
                    "id": template.id,
                    "name": template.name,
                    "category": template.category,
                    "applicable_scenarios": template.applicable_scenarios,
                    "special_clauses": template.special_clauses,
                    "field_count": len(template.required_fields)
                })
        
        return result


def main():
    """测试函数"""
    generator = ContractGenerator()
    
    # 列出模板
    print("=== 可用模板 ===")
    templates = generator.list_templates()
    for t in templates:
        print(f"- {t['name']} ({t['category']})")
    
    # 从模板生成
    print("\n=== 从模板生成合同 ===")
    fields = {
        "甲方名称": "深圳市XX科技有限公司",
        "甲方代码": "91440300XXXXXXXXX",
        "甲方法人": "李明",
        "甲方地址": "深圳市南山区科技园",
        "乙方姓名": "张三",
        "乙方身份证": "110101199001011234",
        "乙方电话": "13800138000",
        "乙方地址": "深圳市宝安区",
        "合同期限": "3年",
        "开始日期": "2024年1月1日",
        "结束日期": "2026年12月31日",
        "试用期": "6个月",
        "部门": "技术",
        "岗位": "高级工程师",
        "工作地点": "深圳市",
        "每日工时": "8",
        "每周工时": "40",
        "月薪": "28000",
        "发薪日": "15",
        "支付方式": "银行转账",
        "签订日期": "2023年12月15日",
        "甲方公章": "（公章）",
        "乙方签字": "（签字）",
        "保密条款内容": "（详见保密协议）",
        "竞业限制条款内容": "（详见竞业限制协议）",
        "其他约定": "（无）"
    }
    
    try:
        contract = generator.generate_from_template("labor_standard", fields)
        print(f"合同生成成功！")
        print(f"合同类型：{contract.contract_type}")
        print(f"包含章节数：{len(contract.sections)}")
        if contract.warnings:
            print(f"警告：{contract.warnings}")
    except Exception as e:
        print(f"生成失败：{e}")
    
    # 条款建议
    print("\n=== 保密条款建议 ===")
    suggestions = generator.suggest_clauses("技术岗位", "保密条款")
    for s in suggestions:
        print(f"【{s['name']}】- {s['applicable']}")
        print(s['content'][:200] + "...")
        print()


if __name__ == "__main__":
    main()
