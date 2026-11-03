#!/home/linuxbrew/.linuxbrew/bin/python3.10
# -*- coding: utf-8 -*-
"""
股票仓位管理与风控专家 - 主计算脚本 (v1.0)
计算盈亏比例、仓位占比、生成操作建议
"""

import sys
import argparse
import time
from dataclasses import dataclass
from typing import List, Optional

# 尝试导入 AKShare
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    print("⚠️ AKShare 未安装，请运行：pip3 install akshare pandas -U")


@dataclass
class PositionInfo:
    """持仓信息"""
    stock_name: str
    stock_code: str
    cost_price: float
    current_price: float
    shares: int
    position_ratio: float  # 占总仓位比例 (%)
    total_assets: Optional[float] = None


@dataclass
class RiskAssessment:
    """风险评估结果"""
    profit_loss_ratio: float  # 盈亏比例 (%)
    profit_loss_amount: float  # 盈亏金额
    position_health: str  # 仓位健康度
    risk_level: str  # 风险等级
    status_category: str  # 状态分类（大幅浮盈/深度套牢等）


@dataclass
class ActionPlan:
    """操作计划"""
    model_name: str  # 推荐模型
    actions: List[dict]  # 具体操作列表
    trailing_stop_price: Optional[float]  # 移动止盈位
    target_price: Optional[float]  # 目标价
    psychology_tip: str  # 心理疏导


def calculate_profit_loss(cost: float, current: float) -> float:
    """计算盈亏比例"""
    if cost == 0:
        return 0.0
    return (current - cost) / cost * 100


def assess_risk(info: PositionInfo) -> RiskAssessment:
    """风险评估"""
    profit_loss_ratio = calculate_profit_loss(info.cost_price, info.current_price)
    profit_loss_amount = (info.current_price - info.cost_price) * info.shares
    
    # 仓位健康度评估
    if info.position_ratio > 60:
        position_health = "⚠️ 极度危险，需强制降仓"
        risk_level = "HIGH"
    elif info.position_ratio > 40:
        position_health = "⚠️ 偏重，建议再平衡"
        risk_level = "MEDIUM"
    elif info.position_ratio > 20:
        position_health = "✅ 健康"
        risk_level = "LOW"
    else:
        position_health = "✅ 轻仓，可适度加仓"
        risk_level = "LOW"
    
    # 状态分类
    if profit_loss_ratio > 30:
        status_category = "大幅浮盈 (>30%)"
    elif profit_loss_ratio > 20:
        status_category = "大幅浮盈 (>20%)"
    elif profit_loss_ratio > 10:
        status_category = "中等浮盈 (10-20%)"
    elif profit_loss_ratio > 0:
        status_category = "微利 (0-10%)"
    elif profit_loss_ratio > -5:
        status_category = "微亏 (-5%-0%)"
    elif profit_loss_ratio > -15:
        status_category = "中度套牢 (-15%~-5%)"
    else:
        status_category = "深度套牢 (<-15%)"
    
    return RiskAssessment(
        profit_loss_ratio=profit_loss_ratio,
        profit_loss_amount=profit_loss_amount,
        position_health=position_health,
        risk_level=risk_level,
        status_category=status_category
    )


def generate_action_plan(info: PositionInfo, assessment: RiskAssessment) -> ActionPlan:
    """生成操作计划"""
    actions = []
    model_name = ""
    trailing_stop_price = None
    target_price = None
    psychology_tip = ""
    
    current = info.current_price
    cost = info.cost_price
    ratio = assessment.profit_loss_ratio
    
    # 根据盈亏状态匹配策略
    if ratio > 30:
        # 大幅浮盈 >30%：倒金字塔止盈 + 移动跟踪
        model_name = "倒金字塔止盈 + 移动跟踪止盈"
        
        actions = [
            {
                "type": "TAKE_PROFIT",
                "emoji": "⚡",
                "title": "锁定利润",
                "description": f"建议在当前价位 ({current:.2f}元) 附近，卖出 30% 的持仓",
                "purpose": "落袋为安，收回大部分本金，释放资金流动性"
            },
            {
                "type": "TRAILING_STOP",
                "emoji": "🛡️",
                "title": "动态防守",
                "description": f"剩余 70% 底仓继续持有，将止盈位上移至 {current * 0.9:.2f}元（约 -10%）",
                "purpose": "让利润奔跑，但保护已有盈利"
            },
            {
                "type": "REBALANCE",
                "emoji": "🔄",
                "title": "极限目标/再平衡",
                "description": f"若继续冲至 {current * 1.2:.2f}元，再卖出 30%；抽出的资金可布局历史低位标的",
                "purpose": "避免过度集中，分散风险"
            }
        ]
        
        trailing_stop_price = current * 0.9
        target_price = current * 1.2
        psychology_tip = "卖飞是赚，套牢是亏。不要追求卖在最高点，把鱼尾留给别人。你已经赢了，现在要守住胜利果实。"
    
    elif ratio > 20:
        # 大幅浮盈 20-30%：移动跟踪止盈
        model_name = "移动跟踪止盈 (Trailing Stop)"
        
        # 计算防守位（20 日均线或阶段性低点）
        support_price = current * 0.92  # 简化计算，实际应基于均线
        
        actions = [
            {
                "type": "TRAILING_STOP",
                "emoji": "🛡️",
                "title": "动态防守",
                "description": f"继续持有，将止盈位设置在 {support_price:.2f}元（约 -8%）",
                "purpose": "让利润奔跑，跌破防守位立即止盈"
            },
            {
                "type": "PARTIAL_EXIT",
                "emoji": "⚡",
                "title": "部分止盈（可选）",
                "description": f"若想锁定利润，可卖出 20-30% 仓位",
                "purpose": "降低心理压力，保持良好心态"
            }
        ]
        
        trailing_stop_price = support_price
        psychology_tip = "趋势是你的朋友。只要不跌破防守位，就耐心持有。不要因为害怕回调而过早下车。"
    
    elif ratio > 10:
        # 中等浮盈 10-20%：设定止损，继续持有
        model_name = "持有 + 硬性止损"
        
        stop_loss = cost * 1.02  # 保本止损
        
        actions = [
            {
                "type": "HOLD",
                "emoji": "✋",
                "title": "继续持有",
                "description": "当前浮盈健康，建议继续持有",
                "purpose": "让利润继续奔跑"
            },
            {
                "type": "STOP_LOSS",
                "emoji": "🛑",
                "title": "设定止损",
                "description": f"将止损位设置在 {stop_loss:.2f}元（保本位）",
                "purpose": "确保这笔交易不亏损"
            }
        ]
        
        psychology_tip = "你已经在赚钱了，这是好事。保持耐心，让市场证明你的判断是对的。"
    
    elif ratio > 0:
        # 微利 0-10%：设定止损，观察
        model_name = "观察 + 硬性止损"
        
        stop_loss = cost * 0.97  # -3% 止损
        
        actions = [
            {
                "type": "HOLD",
                "emoji": "✋",
                "title": "继续持有/观察",
                "description": "微利状态，方向正确但盈利尚小",
                "purpose": "等待趋势确认"
            },
            {
                "type": "STOP_LOSS",
                "emoji": "🛑",
                "title": "设定止损",
                "description": f"将止损位设置在 {stop_loss:.2f}元（-3%）",
                "purpose": "控制亏损，保护本金"
            }
        ]
        
        psychology_tip = "交易是概率游戏。这笔交易目前正确，但要保持警惕，随时准备认错。"
    
    elif ratio > -5:
        # 微亏 -5%-0%：设定止损，考虑加仓或止损
        model_name = "止损/加仓二选一"
        
        stop_loss = cost * 0.95  # -5% 止损
        add_position = cost * 0.9  # -10% 加仓
        
        actions = [
            {
                "type": "DECISION",
                "emoji": "🤔",
                "title": "决策点",
                "description": "微亏状态，需要判断是否继续看好",
                "purpose": "明确交易逻辑"
            },
            {
                "type": "STOP_LOSS",
                "emoji": "🛑",
                "title": "止损方案",
                "description": f"若不看好，止损位在 {stop_loss:.2f}元（-5%）",
                "purpose": "控制亏损"
            },
            {
                "type": "ADD_POSITION",
                "emoji": "➕",
                "title": "加仓方案（可选）",
                "description": f"若仍看好，可在 {add_position:.2f}元（-10%）加仓摊薄成本",
                "purpose": "降低持仓成本"
            }
        ]
        
        psychology_tip = "承认错误是交易的一部分。如果逻辑变了，就止损；如果逻辑没变，就坚持。"
    
    elif ratio > -15:
        # 中度套牢 -15%~-5%：评估是否割肉或网格自救
        model_name = "网格自救 + 评估换股"
        
        grid_low = current * 0.9  # 网格下限
        grid_high = current * 1.1  # 网格上限
        
        actions = [
            {
                "type": "EVALUATE",
                "emoji": "🔍",
                "title": "评估基本面",
                "description": "判断公司基本面是否恶化，行业逻辑是否改变",
                "purpose": "决定是坚守还是换股"
            },
            {
                "type": "GRID_TRADING",
                "emoji": "🔄",
                "title": "网格做 T 自救",
                "description": f"在 {grid_low:.2f}-{grid_high:.2f}元区间做 T，降低成本",
                "purpose": "主动自救，而非被动等待"
            },
            {
                "type": "STOP_LOSS",
                "emoji": "🛑",
                "title": "止损底线",
                "description": f"若跌破 {current * 0.9:.2f}元，考虑割肉换股",
                "purpose": "避免深度套牢"
            }
        ]
        
        psychology_tip = "套牢不可怕，可怕的是被动等待。要么主动自救，要么果断换股，不要装死。"
    
    else:
        # 深度套牢 <-15%：割肉换股或长期抗战
        model_name = "割肉换股 vs 长期抗战"
        
        actions = [
            {
                "type": "EVALUATE",
                "emoji": "🔍",
                "title": "深度评估",
                "description": "审视买入逻辑是否完全错误，公司是否还有希望",
                "purpose": "决定去留"
            },
            {
                "type": "SWITCH",
                "emoji": "🔄",
                "title": "方案 A：割肉换股",
                "description": "换到处于低位的优质标的，用其他股票的盈利弥补亏损",
                "purpose": "主动出击，而非被动等待"
            },
            {
                "type": "HOLD_LONG",
                "emoji": "⏳",
                "title": "方案 B：长期抗战",
                "description": "若公司基本面没问题，只是行业周期低谷，可考虑长期持有等待周期反转",
                "purpose": "用时间换空间"
            }
        ]
        
        psychology_tip = "深度套牢是学费。关键是从中学到什么，而不是沉浸在痛苦中。换股不是认输，是战略转移。"
    
    return ActionPlan(
        model_name=model_name,
        actions=actions,
        trailing_stop_price=trailing_stop_price,
        target_price=target_price,
        psychology_tip=psychology_tip
    )


def format_output(info: PositionInfo, assessment: RiskAssessment, plan: ActionPlan) -> str:
    """格式化输出"""
    output = f"""
### 💼 持仓诊断报告：[{info.stock_name}]

**1. 盈亏与风险评估 (Risk Assessment)**
* **当前状态**：{assessment.status_category}
* **持仓成本**：{info.cost_price:.2f}元 | **当前现价**：{info.current_price:.2f}元
* **盈亏比例**：{assessment.profit_loss_ratio:+.1f}%
* **盈亏金额**：{assessment.profit_loss_amount:+.2f}元
* **仓位占比**：{info.position_ratio:.1f}%
* **仓位健康度**：{assessment.position_health}

**2. 当前盘面定性 (Market Context)**
* **风险等级**：{assessment.risk_level}
* **建议策略**：{plan.model_name}

**3. 下一步操作计划 (Actionable Plan)**

"""
    
    # 添加具体操作
    for action in plan.actions:
        output += f"* **{action['emoji']} {action['title']}**\n"
        output += f"  - {action['description']}\n"
        output += f"  - 目的：{action['purpose']}\n\n"
    
    if plan.trailing_stop_price:
        output += f"**防守位参考**：{plan.trailing_stop_price:.2f}元\n\n"
    
    if plan.target_price:
        output += f"**目标位参考**：{plan.target_price:.2f}元\n\n"
    
    output += f"""**4. 心理按摩 (Trading Psychology)**

> 💬 {plan.psychology_tip}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 风险提示：本建议仅供参考，不构成投资建议。股市有风险，操作需谨慎。
"""
    
    return output


def get_current_price_from_akshare(symbol: str, max_retries: int = 3) -> Optional[float]:
    """
    从 AKShare 获取股票当前价格
    
    ⚠️ 强制使用 AKShare，不 fallback
    """
    if not HAS_AKSHARE:
        print("❌ AKShare 未安装，无法获取股价")
        return None
    
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                wait_time = 2 ** (attempt - 1)
                print(f"⏳ 等待 {wait_time} 秒后重试 (第 {attempt}/{max_retries} 次)...")
                time.sleep(wait_time)
            else:
                print(f"[AKShare] 获取股价中... (第 {attempt}/{max_retries} 次尝试)")
            
            # 获取实时行情
            df = ak.stock_zh_a_spot_em()
            if df is not None and len(df) > 0:
                # 查找对应股票
                if symbol:
                    mask = df['代码'] == symbol
                    if mask.any():
                        row = df[mask].iloc[0]
                        price = row['最新价'] if '最新价' in row else row['收盘价']
                        print(f"✓ AKShare 成功获取 {symbol} 当前价格：{price:.2f}元")
                        return float(price)
            
            print(f"⚠️ 未找到股票 {symbol}")
            return None
            
        except Exception as e:
            print(f"⚠️ AKShare 尝试 {attempt}/{max_retries} 失败：{e}")
            if attempt == max_retries:
                print("❌ AKShare 所有重试均失败")
                return None
    
    return None


def main():
    parser = argparse.ArgumentParser(description='股票仓位管理与风控专家')
    parser.add_argument('--name', required=True, help='股票名称')
    parser.add_argument('--code', default='', help='股票代码')
    parser.add_argument('--cost', type=float, required=True, help='持仓成本价')
    parser.add_argument('--current', type=float, help='当前价格 (可选，不提供则从 AKShare 获取)')
    parser.add_argument('--shares', type=int, required=True, help='持仓股数')
    parser.add_argument('--ratio', type=float, required=True, help='仓位占比 (%)')
    parser.add_argument('--assets', type=float, help='总资产 (可选)')
    
    args = parser.parse_args()
    
    # 获取当前价格：优先使用 AKShare
    current_price = args.current
    if current_price is None and args.code:
        print(f"\n🔍 从 AKShare 获取 {args.code} 当前价格...")
        print("=" * 50)
        current_price = get_current_price_from_akshare(args.code, max_retries=3)
        
        if current_price is None:
            print("\n❌ 错误：无法获取当前价格")
            print("   请手动提供 --current 参数，或检查网络连接")
            sys.exit(1)
    elif current_price is None:
        print("\n❌ 错误：未提供股票代码，无法获取当前价格")
        print("   请使用 --code 指定股票代码，或手动提供 --current 参数")
        sys.exit(1)
    else:
        print(f"✅ 使用命令行提供的当前价格：{current_price:.2f}元")
    
    # 创建持仓信息
    info = PositionInfo(
        stock_name=args.name,
        stock_code=args.code,
        cost_price=args.cost,
        current_price=current_price,
        shares=args.shares,
        position_ratio=args.ratio,
        total_assets=args.assets
    )
    
    # 风险评估
    assessment = assess_risk(info)
    
    # 生成操作计划
    plan = generate_action_plan(info, assessment)
    
    # 输出结果
    print(format_output(info, assessment, plan))


if __name__ == '__main__':
    main()
