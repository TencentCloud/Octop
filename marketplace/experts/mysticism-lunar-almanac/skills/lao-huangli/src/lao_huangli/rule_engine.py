from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

from .calendar_core import DIZHI


ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / "rules"


def load_ruleset_items(profile_id: str, filename: str) -> List[Dict[str, object]]:
    path = RULES_DIR / profile_id / f"{filename}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def get_ruleset_source_metadata(ruleset_id: Optional[str]) -> Dict[str, object]:
    if not ruleset_id:
        return {"ruleSourceLevel": "none", "sourceRefs": []}

    ruleset_dir = RULES_DIR / ruleset_id
    if not ruleset_dir.exists():
        return {"ruleSourceLevel": "none", "sourceRefs": []}

    source_levels = OrderedDict()
    source_refs = OrderedDict()
    for path in sorted(ruleset_dir.glob("*.json")):
        if path.name == "placeholder.json":
            continue
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            continue
        for item in data:
            level = item.get("sourceLevel")
            if level:
                source_levels[level] = True
            for ref in item.get("sourceRef", []):
                key = (ref.get("work"), ref.get("location"), ref.get("url"))
                if key not in source_refs:
                    source_refs[key] = ref

    level_text = ",".join(source_levels.keys()) if source_levels else "none"
    return {"ruleSourceLevel": level_text, "sourceRefs": list(source_refs.values())}


def get_rule_file_source_metadata(ruleset_id: Optional[str], filename: str) -> Dict[str, object]:
    if not ruleset_id:
        return {"ruleSourceLevel": "none", "sourceRefs": []}

    items = load_ruleset_items(ruleset_id, filename)
    source_levels = OrderedDict()
    source_refs = OrderedDict()
    for item in items:
        level = item.get("sourceLevel")
        if level:
            source_levels[level] = True
        for ref in item.get("sourceRef", []):
            key = (ref.get("work"), ref.get("location"), ref.get("url"))
            if key not in source_refs:
                source_refs[key] = ref

    level_text = ",".join(source_levels.keys()) if source_levels else "none"
    return {"ruleSourceLevel": level_text, "sourceRefs": list(source_refs.values())}


def compute_jianchu(profile_id: str, month_branch: str, day_branch: str) -> str:
    rules = load_ruleset_items(profile_id, "jianchu")
    if not rules:
        return "待规则库补齐"

    cycle = rules[0]["cycle"]
    month_index = DIZHI.index(month_branch)
    day_index = DIZHI.index(day_branch)
    return cycle[(day_index - month_index) % 12]


def compute_yellow_black_dao(profile_id: str, month_branch: str, day_branch: str) -> str:
    rules = load_ruleset_items(profile_id, "yellow-black-dao")
    if not rules:
        return "待规则库补齐"

    rule = rules[0]
    start_branch = rule["monthStarts"][month_branch]
    start_index = DIZHI.index(start_branch)
    day_index = DIZHI.index(day_branch)
    return rule["order"][(day_index - start_index) % 12]


def compute_duty_god(profile_id: str, month_branch: str, day_branch: str) -> str:
    rules = load_ruleset_items(profile_id, "duty-gods")
    if rules:
        rule = rules[0]
        order = rule["order"]
        starts = load_ruleset_items(profile_id, "yellow-black-dao")
        if starts:
            start_branch = starts[0]["monthStarts"][month_branch]
            start_index = DIZHI.index(start_branch)
            day_index = DIZHI.index(day_branch)
            return order[(day_index - start_index) % 12]
    return compute_yellow_black_dao(profile_id, month_branch, day_branch)


def compute_star_lists(profile_id: str, duty_god: str) -> Dict[str, List[str]]:
    good_rules = load_ruleset_items(profile_id, "good-stars")
    bad_rules = load_ruleset_items(profile_id, "bad-stars")
    good_stars = good_rules[0].get("starsByDutyGod", {}).get(duty_god, []) if good_rules else []
    bad_stars = bad_rules[0].get("starsByDutyGod", {}).get(duty_god, []) if bad_rules else []

    if not good_rules or not bad_rules:
        yb_rules = load_ruleset_items(profile_id, "yellow-black-dao")
        if yb_rules:
            good_gods = set(yb_rules[0].get("goodGods", []))
            if duty_god in good_gods and not good_stars:
                good_stars = [duty_god]
            if duty_god not in good_gods and not bad_stars:
                bad_stars = [duty_god]

    return {"goodStars": good_stars, "badStars": bad_stars}


def compute_chongsha(profile_id: str, day_branch: str) -> str:
    rules = load_ruleset_items(profile_id, "chongsha")
    if not rules:
        return "待规则库补齐"

    rule = rules[0]
    opposite_branch = rule["oppositeBranches"].get(day_branch)
    if not opposite_branch:
        return "待规则库补齐"

    direction = None
    for trine, value in rule["shaDirectionsByTrine"].items():
        if day_branch in trine:
            direction = value
            break

    animal = rule["branchToAnimal"].get(opposite_branch)
    if not direction or not animal:
        return "待规则库补齐"

    return f"冲{animal}煞{direction}"


def compute_pengzu(profile_id: str, day_ganzhi: str) -> str:
    rules = load_ruleset_items(profile_id, "pengzu")
    if not rules:
        return "待规则库补齐"

    rule = rules[0]
    day_gan = day_ganzhi[0]
    day_branch = day_ganzhi[1]
    gan_text = rule["ganRules"].get(day_gan)
    zhi_text = rule["zhiRules"].get(day_branch)
    if not gan_text or not zhi_text:
        return "待规则库补齐"

    return f"{gan_text}；{zhi_text}"


def compute_taishen(profile_id: str, day_ganzhi: str) -> str:
    rules = load_ruleset_items(profile_id, "taishen")
    if not rules:
        return "待规则库补齐"

    rule = rules[0]
    return rule["dayGanzhiToPosition"].get(day_ganzhi, "待规则库补齐")


def compute_directions(profile_id: str, day_gan: str) -> Dict[str, str]:
    rules = load_ruleset_items(profile_id, "directions")
    if not rules:
        return {
            "caiShen": "待规则库补齐",
            "xiShen": "待规则库补齐",
            "fuShen": "待规则库补齐",
        }

    rule = rules[0]
    values = rule.get("byDayGan", {}).get(day_gan)
    if not values:
        return {
            "caiShen": "待规则库补齐",
            "xiShen": "待规则库补齐",
            "fuShen": "待规则库补齐",
        }
    return {
        "caiShen": values.get("caiShen", "待规则库补齐"),
        "xiShen": values.get("xiShen", "待规则库补齐"),
        "fuShen": values.get("fuShen", "待规则库补齐"),
    }


def compute_time_gods(
    profile_id: str, day_branch: str, hour_slots: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    rules = load_ruleset_items(profile_id, "time-gods")
    if not rules:
        return hour_slots

    rule = rules[0]
    offset = rule.get("offsetsByDayBranch", {}).get(day_branch)
    if offset is None:
        return hour_slots

    order = rule.get("order", [])
    god_types = rule.get("godTypes", {})
    luck_by_type = rule.get("luckByGodType", {})
    if not order:
        return hour_slots

    enriched: List[Dict[str, str]] = []
    for idx, item in enumerate(hour_slots):
        tian_shen = order[(idx + offset) % len(order)]
        god_type = god_types.get(tian_shen, "")
        enriched.append(
            {
                **item,
                "tianShen": tian_shen,
                "luck": luck_by_type.get(god_type, ""),
            }
        )
    return enriched


def evaluate_rules(profile_id: str, rule_context: Dict[str, str]) -> Dict[str, List[str]]:
    decision = {"yi": [], "ji": [], "warnings": [], "explanations": []}
    for rule in load_ruleset_items(profile_id, "yi-ji-rules"):
        field_value = rule_context.get(rule["field"])
        match_mode = rule.get("match", "equals")
        if match_mode == "containsAny":
            values = field_value if isinstance(field_value, list) else []
            if not any(value in values for value in rule["values"]):
                continue
        elif field_value not in rule["values"]:
            continue

        effect = rule["effect"]
        decision[effect].extend(rule["items"])
        decision["explanations"].append(rule["reason"])

    for key in ("yi", "ji", "warnings", "explanations"):
        decision[key] = list(OrderedDict.fromkeys(decision[key]))
    return decision


def get_active_ruleset(profile_id: str, overlay_ruleset: Optional[str]) -> Optional[str]:
    if profile_id == "bazi-v1":
        return overlay_ruleset
    return profile_id


def get_capabilities(profile_id: str, ruleset_id: Optional[str], is_hybrid: bool) -> Dict[str, bool]:
    has_rule_layer = ruleset_id is not None
    return {
        "calendarCore": True,
        "ganzhi": True,
        "solarTerms": True,
        "jianchu": has_rule_layer,
        "yellowBlackDao": has_rule_layer,
        "dutyGod": has_rule_layer,
        "yiJi": has_rule_layer,
        "sourceTrace": has_rule_layer,
        "isHybrid": is_hybrid,
    }

def build_field_sources(ruleset_id: Optional[str], daily: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    field_to_rule_file = {
        "jianchu": "jianchu",
        "yellowBlackDao": "yellow-black-dao",
        "dutyGod": "duty-gods",
        "goodStars": "good-stars",
        "badStars": "bad-stars",
        "chongsha": "chongsha",
        "taishen": "taishen",
        "pengzu": "pengzu",
        "caiShen": "directions",
        "xiShen": "directions",
        "fuShen": "directions",
    }
    field_sources: Dict[str, Dict[str, object]] = {}
    for field, rule_file in field_to_rule_file.items():
        metadata = get_rule_file_source_metadata(ruleset_id, rule_file)
        if not ruleset_id:
            field_sources[field] = {
                "ruleFile": rule_file,
                "status": "pending",
                "sourceLevel": metadata["ruleSourceLevel"],
                "sourceRefs": metadata["sourceRefs"],
            }
            continue
        value = daily.get(field, "")
        if metadata["ruleSourceLevel"] == "none":
            status = "pending"
        elif isinstance(value, list):
            status = "implemented"
        else:
            status = "pending" if value == "待规则库补齐" else "implemented"
        field_sources[field] = {
            "ruleFile": rule_file,
            "status": status,
            "sourceLevel": metadata["ruleSourceLevel"],
            "sourceRefs": metadata["sourceRefs"],
        }
    return field_sources


def evaluate_rule_layer(
    profile_id: str,
    overlay_ruleset: Optional[str],
    calendar_context: Dict[str, object],
) -> Dict[str, object]:
    ganzhi = calendar_context["ganzhi"]
    month_branch = ganzhi["month"][1]
    day_branch = ganzhi["day"][1]
    day_ganzhi = ganzhi["day"]
    day_gan = day_ganzhi[0]
    is_hybrid = profile_id == "bazi-v1" and overlay_ruleset is not None
    ruleset_id = get_active_ruleset(profile_id, overlay_ruleset)

    if ruleset_id:
        duty_god = compute_duty_god(ruleset_id, month_branch, day_branch)
        star_lists = compute_star_lists(ruleset_id, duty_god)
        directions = compute_directions(ruleset_id, day_gan)
        daily = {
            "jianchu": compute_jianchu(ruleset_id, month_branch, day_branch),
            "yellowBlackDao": compute_yellow_black_dao(ruleset_id, month_branch, day_branch),
            "dutyGod": duty_god,
            "goodStars": star_lists["goodStars"],
            "badStars": star_lists["badStars"],
            "chongsha": compute_chongsha(ruleset_id, day_branch),
            "taishen": compute_taishen(ruleset_id, day_ganzhi),
            "pengzu": compute_pengzu(ruleset_id, day_ganzhi),
            "caiShen": directions["caiShen"],
            "xiShen": directions["xiShen"],
            "fuShen": directions["fuShen"],
        }
        decision = evaluate_rules(ruleset_id, daily)
    else:
        daily = {
            "jianchu": "未启用",
            "yellowBlackDao": "未启用",
            "dutyGod": "未启用",
            "goodStars": [],
            "badStars": [],
            "chongsha": "未启用",
            "taishen": "未启用",
            "pengzu": "未启用",
            "caiShen": "未启用",
            "xiShen": "未启用",
            "fuShen": "未启用",
        }
        decision = {"yi": [], "ji": [], "warnings": [], "explanations": []}

    source_metadata = get_ruleset_source_metadata(ruleset_id)
    provenance = {
        "calendarCore": "algorithmic",
        "ruleLayer": ruleset_id,
        "ruleSourceLevel": source_metadata["ruleSourceLevel"],
        "sourceRefs": source_metadata["sourceRefs"],
        "fieldSources": build_field_sources(ruleset_id, daily),
        "hourSlotSource": get_rule_file_source_metadata(ruleset_id, "time-gods"),
        "isHybrid": is_hybrid,
        "overlayRuleset": overlay_ruleset,
    }
    return {
        "daily": daily,
        "decision": decision,
        "capabilities": get_capabilities(profile_id, ruleset_id, is_hybrid),
        "provenance": provenance,
        "ruleLayer": ruleset_id,
        "isHybrid": is_hybrid,
    }
