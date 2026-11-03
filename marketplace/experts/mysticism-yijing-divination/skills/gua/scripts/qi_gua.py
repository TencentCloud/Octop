import random
import hashlib
from datetime import datetime

BAGUA = {
    (1, 1, 1): "乾",
    (1, 1, 0): "兑",
    (1, 0, 1): "离",
    (1, 0, 0): "震",
    (0, 1, 1): "巽",
    (0, 1, 0): "坎",
    (0, 0, 1): "艮",
    (0, 0, 0): "坤",
}

BAGUA_NAMES = {
    "乾": "天",
    "兑": "泽",
    "离": "火",
    "震": "雷",
    "巽": "风",
    "坎": "水",
    "艮": "山",
    "坤": "地",
}

HEXAGRAM_DATA = [
    {"index": "01", "name": "乾", "full_name": "乾为天", "symbol": "䷀", "judgment": "元亨利贞", "upper_lower": "乾上乾下", "palace": "乾宫", "upper": "乾", "lower": "乾"},
    {"index": "02", "name": "坤", "full_name": "坤为地", "symbol": "䷁", "judgment": "元亨，利牝马之贞", "upper_lower": "坤上坤下", "palace": "坤宫", "upper": "坤", "lower": "坤"},
    {"index": "03", "name": "屯", "full_name": "水雷屯", "symbol": "䷂", "judgment": "元亨利贞，勿用有攸往", "upper_lower": "坎上震下", "palace": "坎宫", "upper": "坎", "lower": "震"},
    {"index": "04", "name": "蒙", "full_name": "山水蒙", "symbol": "䷃", "judgment": "亨。匪我求童蒙，童蒙求我", "upper_lower": "艮上坎下", "palace": "离宫", "upper": "艮", "lower": "坎"},
    {"index": "05", "name": "需", "full_name": "水天需", "symbol": "䷄", "judgment": "有孚，光亨，贞吉", "upper_lower": "坎上乾下", "palace": "坤宫", "upper": "坎", "lower": "乾"},
    {"index": "06", "name": "讼", "full_name": "天水讼", "symbol": "䷅", "judgment": "有孚窒惕，中吉，终凶", "upper_lower": "乾上坎下", "palace": "离宫", "upper": "乾", "lower": "坎"},
    {"index": "07", "name": "师", "full_name": "地水师", "symbol": "䷆", "judgment": "贞，丈人吉，无咎", "upper_lower": "坤上坎下", "palace": "坎宫", "upper": "坤", "lower": "坎"},
    {"index": "08", "name": "比", "full_name": "水地比", "symbol": "䷇", "judgment": "吉，原筮，元永贞，无咎", "upper_lower": "坎上坤下", "palace": "坤宫", "upper": "坎", "lower": "坤"},
    {"index": "09", "name": "小畜", "full_name": "风天小畜", "symbol": "䷈", "judgment": "亨。密云不雨，自我西郊", "upper_lower": "巽上乾下", "palace": "巽宫", "upper": "巽", "lower": "乾"},
    {"index": "10", "name": "履", "full_name": "天泽履", "symbol": "䷉", "judgment": "履虎尾，不咥人，亨", "upper_lower": "乾上兑下", "palace": "艮宫", "upper": "乾", "lower": "兑"},
    {"index": "11", "name": "泰", "full_name": "地天泰", "symbol": "䷊", "judgment": "小往大来，吉亨", "upper_lower": "坤上乾下", "palace": "坤宫", "upper": "坤", "lower": "乾"},
    {"index": "12", "name": "否", "full_name": "天地否", "symbol": "䷋", "judgment": "否之匪人，不利君子贞", "upper_lower": "乾上坤下", "palace": "乾宫", "upper": "乾", "lower": "坤"},
    {"index": "13", "name": "同人", "full_name": "天火同人", "symbol": "䷌", "judgment": "同人于野，亨", "upper_lower": "乾上离下", "palace": "离宫", "upper": "乾", "lower": "离"},
    {"index": "14", "name": "大有", "full_name": "火天大有", "symbol": "䷍", "judgment": "元亨", "upper_lower": "离上乾下", "palace": "乾宫", "upper": "离", "lower": "乾"},
    {"index": "15", "name": "谦", "full_name": "地山谦", "symbol": "䷎", "judgment": "亨，君子有终", "upper_lower": "坤上艮下", "palace": "兑宫", "upper": "坤", "lower": "艮"},
    {"index": "16", "name": "豫", "full_name": "雷地豫", "symbol": "䷏", "judgment": "利建侯行师", "upper_lower": "震上坤下", "palace": "震宫", "upper": "震", "lower": "坤"},
    {"index": "17", "name": "随", "full_name": "泽雷随", "symbol": "䷐", "judgment": "元亨利贞，无咎", "upper_lower": "兑上震下", "palace": "震宫", "upper": "兑", "lower": "震"},
    {"index": "18", "name": "蛊", "full_name": "山风蛊", "symbol": "䷑", "judgment": "元亨，利涉大川", "upper_lower": "艮上巽下", "palace": "巽宫", "upper": "艮", "lower": "巽"},
    {"index": "19", "name": "临", "full_name": "地泽临", "symbol": "䷒", "judgment": "元亨利贞，至于八月有凶", "upper_lower": "坤上兑下", "palace": "坤宫", "upper": "坤", "lower": "兑"},
    {"index": "20", "name": "观", "full_name": "风地观", "symbol": "䷓", "judgment": "盥而不荐，有孚颙若", "upper_lower": "巽上坤下", "palace": "乾宫", "upper": "巽", "lower": "坤"},
    {"index": "21", "name": "噬嗑", "full_name": "火雷噬嗑", "symbol": "䷔", "judgment": "亨，利用狱", "upper_lower": "离上震下", "palace": "巽宫", "upper": "离", "lower": "震"},
    {"index": "22", "name": "贲", "full_name": "山火贲", "symbol": "䷕", "judgment": "亨，小利有攸往", "upper_lower": "艮上离下", "palace": "艮宫", "upper": "艮", "lower": "离"},
    {"index": "23", "name": "剥", "full_name": "山地剥", "symbol": "䷖", "judgment": "不利有攸往", "upper_lower": "艮上坤下", "palace": "乾宫", "upper": "艮", "lower": "坤"},
    {"index": "24", "name": "复", "full_name": "地雷复", "symbol": "䷗", "judgment": "亨，出入无疾", "upper_lower": "坤上震下", "palace": "坤宫", "upper": "坤", "lower": "震"},
    {"index": "25", "name": "无妄", "full_name": "天雷无妄", "symbol": "䷘", "judgment": "元亨利贞，其匪正有眚", "upper_lower": "乾上震下", "palace": "巽宫", "upper": "乾", "lower": "震"},
    {"index": "26", "name": "大畜", "full_name": "山天大畜", "symbol": "䷙", "judgment": "利贞，不家食吉", "upper_lower": "艮上乾下", "palace": "艮宫", "upper": "艮", "lower": "乾"},
    {"index": "27", "name": "颐", "full_name": "山雷颐", "symbol": "䷚", "judgment": "贞吉，观颐，自求口实", "upper_lower": "艮上震下", "palace": "巽宫", "upper": "艮", "lower": "震"},
    {"index": "28", "name": "大过", "full_name": "泽风大过", "symbol": "䷛", "judgment": "栋桡，利有攸往，亨", "upper_lower": "兑上巽下", "palace": "震宫", "upper": "兑", "lower": "巽"},
    {"index": "29", "name": "坎", "full_name": "坎为水", "symbol": "䷜", "judgment": "习坎，有孚，维心亨", "upper_lower": "坎上坎下", "palace": "坎宫", "upper": "坎", "lower": "坎"},
    {"index": "30", "name": "离", "full_name": "离为火", "symbol": "䷝", "judgment": "利贞，亨，畜牝牛吉", "upper_lower": "离上离下", "palace": "离宫", "upper": "离", "lower": "离"},
    {"index": "31", "name": "咸", "full_name": "泽山咸", "symbol": "䷞", "judgment": "亨，利贞，取女吉", "upper_lower": "兑上艮下", "palace": "兑宫", "upper": "兑", "lower": "艮"},
    {"index": "32", "name": "恒", "full_name": "雷风恒", "symbol": "䷟", "judgment": "亨，无咎，利贞", "upper_lower": "震上巽下", "palace": "震宫", "upper": "震", "lower": "巽"},
    {"index": "33", "name": "遯", "full_name": "天山遯", "symbol": "䷠", "judgment": "亨，小利贞", "upper_lower": "乾上艮下", "palace": "乾宫", "upper": "乾", "lower": "艮"},
    {"index": "34", "name": "大壮", "full_name": "雷天大壮", "symbol": "䷡", "judgment": "利贞", "upper_lower": "震上乾下", "palace": "坤宫", "upper": "震", "lower": "乾"},
    {"index": "35", "name": "晋", "full_name": "火地晋", "symbol": "䷢", "judgment": "康侯用锡马蕃庶，昼日三接", "upper_lower": "离上坤下", "palace": "乾宫", "upper": "离", "lower": "坤"},
    {"index": "36", "name": "明夷", "full_name": "地火明夷", "symbol": "䷣", "judgment": "利艰贞", "upper_lower": "坤上离下", "palace": "坎宫", "upper": "坤", "lower": "离"},
    {"index": "37", "name": "家人", "full_name": "风火家人", "symbol": "䷤", "judgment": "利女贞", "upper_lower": "巽上离下", "palace": "巽宫", "upper": "巽", "lower": "离"},
    {"index": "38", "name": "睽", "full_name": "火泽睽", "symbol": "䷥", "judgment": "小事吉", "upper_lower": "离上兑下", "palace": "艮宫", "upper": "离", "lower": "兑"},
    {"index": "39", "name": "蹇", "full_name": "水山蹇", "symbol": "䷦", "judgment": "利西南，不利东北", "upper_lower": "坎上艮下", "palace": "兑宫", "upper": "坎", "lower": "艮"},
    {"index": "40", "name": "解", "full_name": "雷水解", "symbol": "䷧", "judgment": "利西南，无所往，其来复吉", "upper_lower": "震上坎下", "palace": "震宫", "upper": "震", "lower": "坎"},
    {"index": "41", "name": "损", "full_name": "山泽损", "symbol": "䷨", "judgment": "有孚，元吉，无咎", "upper_lower": "艮上兑下", "palace": "艮宫", "upper": "艮", "lower": "兑"},
    {"index": "42", "name": "益", "full_name": "风雷益", "symbol": "䷩", "judgment": "利有攸往，利涉大川", "upper_lower": "巽上震下", "palace": "巽宫", "upper": "巽", "lower": "震"},
    {"index": "43", "name": "夬", "full_name": "泽天夬", "symbol": "䷪", "judgment": "扬于王庭，孚号有厉", "upper_lower": "兑上乾下", "palace": "坤宫", "upper": "兑", "lower": "乾"},
    {"index": "44", "name": "姤", "full_name": "天风姤", "symbol": "䷫", "judgment": "女壮，勿用取女", "upper_lower": "乾上巽下", "palace": "乾宫", "upper": "乾", "lower": "巽"},
    {"index": "45", "name": "萃", "full_name": "泽地萃", "symbol": "䷬", "judgment": "亨，王假有庙", "upper_lower": "兑上坤下", "palace": "兑宫", "upper": "兑", "lower": "坤"},
    {"index": "46", "name": "升", "full_name": "地风升", "symbol": "䷭", "judgment": "元亨，用见大人", "upper_lower": "坤上巽下", "palace": "震宫", "upper": "坤", "lower": "巽"},
    {"index": "47", "name": "困", "full_name": "泽水困", "symbol": "䷮", "judgment": "亨，贞，大人吉", "upper_lower": "兑上坎下", "palace": "兑宫", "upper": "兑", "lower": "坎"},
    {"index": "48", "name": "井", "full_name": "水风井", "symbol": "䷯", "judgment": "改邑不改井，无丧无得", "upper_lower": "坎上巽下", "palace": "震宫", "upper": "坎", "lower": "巽"},
    {"index": "49", "name": "革", "full_name": "泽火革", "symbol": "䷰", "judgment": "己日乃孚，元亨利贞", "upper_lower": "兑上离下", "palace": "坎宫", "upper": "兑", "lower": "离"},
    {"index": "50", "name": "鼎", "full_name": "火风鼎", "symbol": "䷱", "judgment": "元吉，亨", "upper_lower": "离上巽下", "palace": "离宫", "upper": "离", "lower": "巽"},
    {"index": "51", "name": "震", "full_name": "震为雷", "symbol": "䷲", "judgment": "亨，震来虩虩，笑言哑哑", "upper_lower": "震上震下", "palace": "震宫", "upper": "震", "lower": "震"},
    {"index": "52", "name": "艮", "full_name": "艮为山", "symbol": "䷳", "judgment": "艮其背，不获其身", "upper_lower": "艮上艮下", "palace": "艮宫", "upper": "艮", "lower": "艮"},
    {"index": "53", "name": "渐", "full_name": "风山渐", "symbol": "䷴", "judgment": "女归吉，利贞", "upper_lower": "巽上艮下", "palace": "艮宫", "upper": "巽", "lower": "艮"},
    {"index": "54", "name": "归妹", "full_name": "雷泽归妹", "symbol": "䷵", "judgment": "征凶，无攸利", "upper_lower": "震上兑下", "palace": "兑宫", "upper": "震", "lower": "兑"},
    {"index": "55", "name": "丰", "full_name": "雷火丰", "symbol": "䷶", "judgment": "亨，王假之，勿忧", "upper_lower": "震上离下", "palace": "坎宫", "upper": "震", "lower": "离"},
    {"index": "56", "name": "旅", "full_name": "火山旅", "symbol": "䷷", "judgment": "小亨，旅贞吉", "upper_lower": "离上艮下", "palace": "离宫", "upper": "离", "lower": "艮"},
    {"index": "57", "name": "巽", "full_name": "巽为风", "symbol": "䷸", "judgment": "小亨，利有攸往，利见大人", "upper_lower": "巽上巽下", "palace": "巽宫", "upper": "巽", "lower": "巽"},
    {"index": "58", "name": "兑", "full_name": "兑为泽", "symbol": "䷹", "judgment": "亨，利贞", "upper_lower": "兑上兑下", "palace": "兑宫", "upper": "兑", "lower": "兑"},
    {"index": "59", "name": "涣", "full_name": "风水涣", "symbol": "䷺", "judgment": "亨，王假有庙，利涉大川", "upper_lower": "巽上坎下", "palace": "离宫", "upper": "巽", "lower": "坎"},
    {"index": "60", "name": "节", "full_name": "水泽节", "symbol": "䷻", "judgment": "亨，苦节不可贞", "upper_lower": "坎上兑下", "palace": "坎宫", "upper": "坎", "lower": "兑"},
    {"index": "61", "name": "中孚", "full_name": "风泽中孚", "symbol": "䷼", "judgment": "豚鱼吉，利涉大川", "upper_lower": "巽上兑下", "palace": "艮宫", "upper": "巽", "lower": "兑"},
    {"index": "62", "name": "小过", "full_name": "雷山小过", "symbol": "䷽", "judgment": "亨，利贞，可小事", "upper_lower": "震上艮下", "palace": "兑宫", "upper": "震", "lower": "艮"},
    {"index": "63", "name": "既济", "full_name": "水火既济", "symbol": "䷾", "judgment": "亨小，利贞，初吉终乱", "upper_lower": "坎上离下", "palace": "坎宫", "upper": "坎", "lower": "离"},
    {"index": "64", "name": "未济", "full_name": "火水未济", "symbol": "䷿", "judgment": "亨，小狐汔济，濡其尾", "upper_lower": "离上坎下", "palace": "离宫", "upper": "离", "lower": "坎"},
]

LIUSHISI_GUA = {(item["upper"], item["lower"]): item for item in HEXAGRAM_DATA}


def throw_three_coins(seed):
    random.seed(seed)
    results = []
    for i in range(3):
        coin = random.choice([2, 3])
        results.append(coin)
    return sum(results), results


def get_yao_type(sum_value):
    if sum_value == 6:
        return 0, "老阴(变爻)", True
    elif sum_value == 7:
        return 1, "少阳", False
    elif sum_value == 8:
        return 0, "少阴", False
    elif sum_value == 9:
        return 1, "老阳(变爻)", True
    else:
        return None, "未知", False


def get_gua_from_yao(yao_tuple):
    lower_gua = (yao_tuple[0], yao_tuple[1], yao_tuple[2])
    upper_gua = (yao_tuple[3], yao_tuple[4], yao_tuple[5])

    lower_name = BAGUA.get(lower_gua, "未知")
    upper_name = BAGUA.get(upper_gua, "未知")

    gua_key = (upper_name, lower_name)

    if gua_key in LIUSHISI_GUA:
        return LIUSHISI_GUA[gua_key]

    lower_element = BAGUA_NAMES.get(lower_name, "未知")
    upper_element = BAGUA_NAMES.get(upper_name, "未知")

    full_name = f"{upper_element}{lower_element}"
    return {
        "index": "00",
        "name": f"{upper_name}{lower_name}",
        "full_name": full_name,
        "symbol": "",
        "judgment": "",
        "upper_lower": f"{upper_name}上{lower_name}下",
        "palace": "",
        "upper": upper_name,
        "lower": lower_name,
    }


def qi_gua(question):
    from datetime import datetime
    current_time = datetime.now()
    time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

    combined = f"{question}|{time_str}"
    hash_obj = hashlib.md5(combined.encode('utf-8'))
    seed = int(hash_obj.hexdigest(), 16)

    gua_yao = []
    yao_details = []

    for i in range(6):
        current_seed = seed + i
        sum_value, coins = throw_three_coins(current_seed)
        yao_value, yao_name, is_changing = get_yao_type(sum_value)
        gua_yao.append(yao_value)
        yao_details.append({
            "position": i + 1,
            "coins_sum": sum_value,
            "coins": coins,
            "yao_type": yao_name,
            "yao_value": yao_value,
            "is_changing": is_changing
        })

    gua_tuple = tuple(gua_yao)
    gua_info = get_gua_from_yao(gua_tuple)

    bian_gua_yao = []
    for i, yao in enumerate(yao_details):
        if yao["is_changing"]:
            bian_gua_yao.append(1 if yao["yao_value"] == 0 else 0)
        else:
            bian_gua_yao.append(yao["yao_value"])

    bian_gua_tuple = tuple(bian_gua_yao)
    bian_gua_info = get_gua_from_yao(bian_gua_tuple)

    return {
        "question": question,
        "time": time_str,
        "gua_info": gua_info,
        "gua_name": gua_info["name"],
        "gua_full_name": gua_info["full_name"],
        "bian_gua_info": bian_gua_info,
        "bian_gua_name": bian_gua_info["name"],
        "bian_gua_full_name": bian_gua_info["full_name"],
        "yao_details": yao_details,
        "binary_sequence": gua_tuple,
        "bian_binary_sequence": bian_gua_tuple
    }


def print_gua_info(label, gua_info):
    print(f"【{label}】{gua_info['index']} {gua_info['name']} - {gua_info['full_name']} {gua_info['symbol']}")
    if gua_info["judgment"]:
        print(f"卦辞: {gua_info['judgment']}")
    print(f"上下卦: {gua_info['upper_lower']}")
    if gua_info["palace"]:
        print(f"所属宫: {gua_info['palace']}")


def format_trigram(bits):
    trigram = tuple(bits)
    trigram_name = BAGUA.get(trigram, "未知")
    return f"{trigram_name}({''.join(map(str, trigram))})"


def print_sequence_info(label, yao_tuple):
    lower_bits = yao_tuple[:3]
    upper_bits = yao_tuple[3:]
    six_bits = "".join(map(str, yao_tuple))
    print(f"{label}六爻: {six_bits} (自下而上)")
    print(f"{label}下卦: {format_trigram(lower_bits)}")
    print(f"{label}上卦: {format_trigram(upper_bits)}")


def draw_gua(yao_tuple, title="", yao_details=None):
    print(f"\n{title}")
    print("┌──────┐")
    # Data is stored from 1st yao to 6th yao; render from top (6th) to bottom (1st).
    for i in range(5, -1, -1):
        yao_value = yao_tuple[i]
        if yao_value == 1:
            yao_symbol = "▅▅▅▅▅"
        else:
            yao_symbol = "▅▅ ▅▅"

        change_mark = ""
        if yao_details and yao_details[i]['is_changing']:
            coins_sum = yao_details[i]['coins_sum']
            if coins_sum == 9:
                change_mark = " ○"
            elif coins_sum == 6:
                change_mark = " ×"

        print(f"│{yao_symbol}│{change_mark}")
    print("└──────┘")


def print_result(result):
    print(f"\n{'='*60}")
    print(f"问题: {result['question']}")
    print(f"起卦时间: {result['time']}")
    print(f"{'='*60}")

    print()
    print_gua_info("本卦", result["gua_info"])
    draw_gua(result['binary_sequence'], "本卦图形", result['yao_details'])

    print(f"\n本卦六爻详情 (从上到下显示):")
    print("-" * 60)
    for yao in reversed(result['yao_details']):
        yao_symbol = "▅▅▅▅▅" if yao['yao_value'] == 1 else "▅▅ ▅▅"
        change_mark = " ← 变" if yao['is_changing'] else ""
        coins_str = "+".join(map(str, yao['coins']))
        print(f"第{yao['position']}爻: {yao_symbol} ({yao['yao_type']}, {coins_str}={yao['coins_sum']}){change_mark}")

    print()
    print_sequence_info("本卦", result["binary_sequence"])

    if result['bian_gua_name'] != result['gua_name']:
        print(f"\n{'='*60}")
        print_gua_info("变卦", result["bian_gua_info"])
        draw_gua(result['bian_binary_sequence'], "变卦图形", result['yao_details'])

        print(f"\n变卦六爻详情 (从上到下显示):")
        print("-" * 60)
        for i in range(5, -1, -1):
            yao = result['yao_details'][i]
            bian_yao_value = result['bian_binary_sequence'][i]
            yao_symbol = "▅▅▅▅▅" if bian_yao_value == 1 else "▅▅ ▅▅"
            change_mark = " ← 变" if yao['is_changing'] else ""
            coins_str = "+".join(map(str, yao['coins']))
            yao_type = "老阳" if yao['coins_sum'] == 9 else ("老阴" if yao['coins_sum'] == 6 else ("少阳" if bian_yao_value == 1 else "少阴"))
            print(f"第{yao['position']}爻: {yao_symbol} ({yao_type}, {coins_str}={yao['coins_sum']}){change_mark}")

        print()
        print_sequence_info("变卦", result["bian_binary_sequence"])
    else:
        print(f"\n{'='*60}")
        print("【变卦】无变卦（无变爻）")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = input("请输入你的问题: ")

    result = qi_gua(question)
    print_result(result)
