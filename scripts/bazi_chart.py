"""
八字排盘脚本

用法（命令行传参，无需修改代码）：
    python bazi_chart.py -d "1983-11-21 03:30" -g 男 -l 岳阳
    python bazi_chart.py -d "1990-03-15 14:30" -g 女 --longitude 121.5
    python bazi_chart.py -d "1990-03-15 14:30" -g 男          # 不传出生地 → 使用北京时间

约定：
- 时间格式 "YYYY-MM-DD HH:MM"（北京时间）
- 真太阳时 = 北京时间 - 经度时差 + 均时差
- 晚子时（23:00-23:59）按方式 A：日柱不换日，时柱按当天日干起子时
- 出生地不在内置表中时仅应用均时差

输出（markdown）包括：
- 基本信息（含真太阳时校正过程；时辰边界变化时输出警告）
- 四柱八字 + 藏干 + 十神
- 五行分布
- 大运排布
- 各大运 vs 原局的作用关系表
- 流年作用关系完整表（从起运到 80 岁），含关键信号识别（S/A/B/C/D 五档）
"""

import argparse
import math
import subprocess
import sys
from datetime import datetime, timedelta, date


def ensure_lunar_python():
    try:
        import lunar_python  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'lunar_python', '--quiet'], check=False)


# ============ 城市经度表 ============
CITY_LONGITUDE = {
    "北京": 116.4, "上海": 121.5, "天津": 117.2, "重庆": 106.5,
    "石家庄": 114.5, "太原": 112.5, "呼和浩特": 111.7, "沈阳": 123.4,
    "长春": 125.3, "哈尔滨": 126.6, "南京": 118.8, "杭州": 120.2,
    "合肥": 117.3, "福州": 119.3, "南昌": 115.9, "济南": 117.0,
    "郑州": 113.7, "武汉": 114.3, "长沙": 113.0, "广州": 113.3,
    "南宁": 108.4, "海口": 110.3, "成都": 104.1, "贵阳": 106.7,
    "昆明": 102.7, "拉萨": 91.1, "西安": 108.9, "兰州": 103.8,
    "西宁": 101.8, "银川": 106.3, "乌鲁木齐": 87.6, "台北": 121.5,
    "香港": 114.2, "澳门": 113.5, "深圳": 114.1, "苏州": 120.6,
    "无锡": 120.3, "宁波": 121.6, "温州": 120.7, "厦门": 118.1,
    "青岛": 120.4, "大连": 121.6, "唐山": 118.2, "保定": 115.5,
    "邯郸": 114.5, "包头": 110.0, "鞍山": 123.0, "丹东": 124.4,
    "齐齐哈尔": 123.9, "牡丹江": 129.6, "大庆": 125.0, "扬州": 119.4,
    "徐州": 117.2, "盐城": 120.1, "镇江": 119.4, "嘉兴": 120.8,
    "绍兴": 120.6, "金华": 119.6, "台州": 121.4, "芜湖": 118.4,
    "蚌埠": 117.4, "泉州": 118.6, "漳州": 117.6, "九江": 115.9,
    "赣州": 114.9, "潍坊": 119.1, "烟台": 121.4, "济宁": 116.6,
    "洛阳": 112.5, "开封": 114.3, "新乡": 113.9, "宜昌": 111.3,
    "襄阳": 112.1, "株洲": 113.1, "湘潭": 112.9, "衡阳": 112.6,
    "岳阳": 113.1, "常德": 111.7, "佛山": 113.1, "东莞": 113.7,
    "中山": 113.4, "珠海": 113.6, "汕头": 116.7, "湛江": 110.4,
    "桂林": 110.3, "柳州": 109.4, "三亚": 109.5, "绵阳": 104.7,
    "德阳": 104.4, "宜宾": 104.6, "遵义": 106.9, "丽江": 100.2,
    "大理": 100.2, "咸阳": 108.7, "宝鸡": 107.1, "天水": 105.7,
}

WUSHUDUN = {
    '甲': '甲', '己': '甲', '乙': '丙', '庚': '丙', '丙': '戊', '辛': '戊',
    '丁': '庚', '壬': '庚', '戊': '壬', '癸': '壬',
}
YANG_GAN = {'甲', '丙', '戊', '庚', '壬'}

WX_MAP = {
    '甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土', '己': '土',
    '庚': '金', '辛': '金', '壬': '水', '癸': '水',
    '寅': '木', '卯': '木', '巳': '火', '午': '火',
    '辰': '土', '戌': '土', '丑': '土', '未': '土',
    '申': '金', '酉': '金', '亥': '水', '子': '水',
}

ZHI_CANGGAN = {
    '子': ['癸'], '丑': ['己', '癸', '辛'], '寅': ['甲', '丙', '戊'], '卯': ['乙'],
    '辰': ['戊', '乙', '癸'], '巳': ['丙', '庚', '戊'], '午': ['丁', '己'],
    '未': ['己', '丁', '乙'], '申': ['庚', '壬', '戊'], '酉': ['辛'],
    '戌': ['戊', '辛', '丁'], '亥': ['壬', '甲'],
}

SST_TABLE = {
    '甲': {'甲': '比肩', '乙': '劫财', '丙': '食神', '丁': '伤官', '戊': '偏财', '己': '正财', '庚': '七杀', '辛': '正官', '壬': '偏印', '癸': '正印'},
    '乙': {'甲': '劫财', '乙': '比肩', '丙': '伤官', '丁': '食神', '戊': '正财', '己': '偏财', '庚': '正官', '辛': '七杀', '壬': '正印', '癸': '偏印'},
    '丙': {'甲': '偏印', '乙': '正印', '丙': '比肩', '丁': '劫财', '戊': '食神', '己': '伤官', '庚': '偏财', '辛': '正财', '壬': '七杀', '癸': '正官'},
    '丁': {'甲': '正印', '乙': '偏印', '丙': '劫财', '丁': '比肩', '戊': '伤官', '己': '食神', '庚': '正财', '辛': '偏财', '壬': '正官', '癸': '七杀'},
    '戊': {'甲': '七杀', '乙': '正官', '丙': '偏印', '丁': '正印', '戊': '比肩', '己': '劫财', '庚': '食神', '辛': '伤官', '壬': '偏财', '癸': '正财'},
    '己': {'甲': '正官', '乙': '七杀', '丙': '正印', '丁': '偏印', '戊': '劫财', '己': '比肩', '庚': '伤官', '辛': '食神', '壬': '正财', '癸': '偏财'},
    '庚': {'甲': '偏财', '乙': '正财', '丙': '七杀', '丁': '正官', '戊': '偏印', '己': '正印', '庚': '比肩', '辛': '劫财', '壬': '食神', '癸': '伤官'},
    '辛': {'甲': '正财', '乙': '偏财', '丙': '正官', '丁': '七杀', '戊': '正印', '己': '偏印', '庚': '劫财', '辛': '比肩', '壬': '伤官', '癸': '食神'},
    '壬': {'甲': '食神', '乙': '伤官', '丙': '偏财', '丁': '正财', '戊': '七杀', '己': '正官', '庚': '偏印', '辛': '正印', '壬': '比肩', '癸': '劫财'},
    '癸': {'甲': '伤官', '乙': '食神', '丙': '正财', '丁': '偏财', '戊': '正官', '己': '七杀', '庚': '正印', '辛': '偏印', '壬': '劫财', '癸': '比肩'},
}

# ============ 地支作用关系查表 ============
_LIUHE_PAIRS = {('子', '丑'), ('丑', '子'), ('寅', '亥'), ('亥', '寅'), ('卯', '戌'), ('戌', '卯'),
                ('辰', '酉'), ('酉', '辰'), ('巳', '申'), ('申', '巳'), ('午', '未'), ('未', '午')}
_LIUHE_HUA = {frozenset(['子', '丑']): '土', frozenset(['寅', '亥']): '木',
              frozenset(['卯', '戌']): '火', frozenset(['辰', '酉']): '金',
              frozenset(['巳', '申']): '水', frozenset(['午', '未']): '(无化气)'}

_LIUCHONG_PAIRS = {('子', '午'), ('午', '子'), ('丑', '未'), ('未', '丑'), ('寅', '申'), ('申', '寅'),
                   ('卯', '酉'), ('酉', '卯'), ('辰', '戌'), ('戌', '辰'), ('巳', '亥'), ('亥', '巳')}

_SANHE_SETS = {frozenset(['申', '子', '辰']): '水', frozenset(['亥', '卯', '未']): '木',
               frozenset(['寅', '午', '戌']): '火', frozenset(['巳', '酉', '丑']): '金'}
_SANHE_CENTER = {'水': '子', '木': '卯', '火': '午', '金': '酉'}

_SANHUI_SETS = {frozenset(['寅', '卯', '辰']): '木', frozenset(['巳', '午', '未']): '火',
                frozenset(['申', '酉', '戌']): '金', frozenset(['亥', '子', '丑']): '水'}

_XIANGHAI_PAIRS = {('子', '未'), ('未', '子'), ('丑', '午'), ('午', '丑'), ('寅', '巳'), ('巳', '寅'),
                   ('卯', '辰'), ('辰', '卯'), ('申', '亥'), ('亥', '申'), ('酉', '戌'), ('戌', '酉')}

_SANXING_GROUPS = [frozenset(['寅', '巳', '申']), frozenset(['丑', '戌', '未'])]
_ZIXING = {'辰', '午', '酉', '亥'}
_HUXING_PAIRS = {('子', '卯'), ('卯', '子')}

# ============ 天干作用关系查表 ============
_TIANGAN_HE = {('甲', '己'), ('己', '甲'), ('乙', '庚'), ('庚', '乙'), ('丙', '辛'), ('辛', '丙'),
               ('丁', '壬'), ('壬', '丁'), ('戊', '癸'), ('癸', '戊')}
_HE_HUA = {frozenset(['甲', '己']): '土', frozenset(['乙', '庚']): '金',
           frozenset(['丙', '辛']): '水', frozenset(['丁', '壬']): '木',
           frozenset(['戊', '癸']): '火'}
_GAN_KE = {'甲': {'戊', '己'}, '乙': {'戊', '己'}, '丙': {'庚', '辛'}, '丁': {'庚', '辛'},
           '戊': {'壬', '癸'}, '己': {'壬', '癸'}, '庚': {'甲', '乙'}, '辛': {'甲', '乙'},
           '壬': {'丙', '丁'}, '癸': {'丙', '丁'}}

# 60 甲子表
_GAN10 = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
_ZHI12 = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
_JIAZI = [_GAN10[i % 10] + _ZHI12[i % 12] for i in range(60)]


def equation_of_time_minutes(year, month, day):
    """均时差近似公式（Spencer 1971 简化版）。一年内 -14 ~ +16 分钟。"""
    n = (date(year, month, day) - date(year, 1, 1)).days + 1
    B = math.radians(360.0 * (n - 81) / 365.0)
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def hour_to_shichen(h):
    """24 小时转 12 时辰"""
    if h == 23 or h == 0:
        return "子"
    table = ['子', '丑', '丑', '寅', '寅', '卯', '卯', '辰', '辰', '巳', '巳',
             '午', '午', '未', '未', '申', '申', '酉', '酉', '戌', '戌', '亥', '亥']
    return table[h]


def year_to_ganzhi(year):
    """公历年 → 干支（公元 4 年为甲子）"""
    return _JIAZI[(year - 4) % 60]


def check_zhi_relation(z1, z2):
    """返回 (z1, z2) 之间的所有作用关系列表"""
    relations = []
    if z1 == z2:
        if z1 in _ZIXING:
            relations.append(f"{z1}{z2}自刑")
        else:
            relations.append(f"{z1}{z2}伏吟")
        return relations

    if (z1, z2) in _LIUCHONG_PAIRS:
        relations.append(f"{z1}{z2}冲")
    if (z1, z2) in _LIUHE_PAIRS:
        hua = _LIUHE_HUA.get(frozenset([z1, z2]), '')
        relations.append(f"{z1}{z2}合{hua}")
    if (z1, z2) in _XIANGHAI_PAIRS:
        relations.append(f"{z1}{z2}害")
    if (z1, z2) in _HUXING_PAIRS:
        relations.append(f"{z1}{z2}刑")
    # 半合判断
    for sanhe_set, qi in _SANHE_SETS.items():
        if frozenset([z1, z2]).issubset(sanhe_set):
            center = _SANHE_CENTER[qi]
            if center in [z1, z2]:
                relations.append(f"{z1}{z2}半合{qi}")
            else:
                relations.append(f"{z1}{z2}拱{qi}")
            break
    return relations


def check_gan_relation(g1, g2):
    """返回 (g1, g2) 之间的作用关系"""
    relations = []
    if g1 == g2:
        relations.append(f"{g1}{g2}伏吟")
        return relations
    if (g1, g2) in _TIANGAN_HE:
        hua = _HE_HUA[frozenset([g1, g2])]
        relations.append(f"{g1}{g2}合{hua}")
    if g2 in _GAN_KE.get(g1, set()):
        relations.append(f"{g1}剋{g2}")
    if g1 in _GAN_KE.get(g2, set()):
        relations.append(f"{g2}剋{g1}")
    return relations


def check_sanxing(zhi_list):
    """zhi_list 是支的列表，检查是否包含三刑组合"""
    zhi_set = set(zhi_list)
    sanxing_found = []
    for group in _SANXING_GROUPS:
        if group.issubset(zhi_set):
            sanxing_found.append('、'.join(group) + '三刑')
    return sanxing_found


def parse_args():
    parser = argparse.ArgumentParser(
        description='八字排盘 — 输入出生信息，输出 markdown 格式的排盘结果',
        epilog=(
            '示例:\n'
            '  python bazi_chart.py -d "1983-11-21 03:30" -g 男 -l 岳阳\n'
            '  python bazi_chart.py -d "1990-03-15 14:30" -g 女 --longitude 121.5\n'
            '  python bazi_chart.py -d "1990-03-15 14:30" -g 男           # 默认北京时间'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-d', '--datetime', required=True,
                        help='出生日期时间，格式 "YYYY-MM-DD HH:MM"（北京时间）')
    parser.add_argument('-g', '--gender', required=True, choices=['男', '女'],
                        help='性别')
    parser.add_argument('-l', '--location', default=None,
                        help='出生城市（中文），如"岳阳"。不在内置表中时仅应用均时差')
    parser.add_argument('--longitude', type=float, default=None,
                        help='出生地经度（度），优先级高于 --location')
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        dt_input = datetime.strptime(args.datetime, '%Y-%m-%d %H:%M')
    except ValueError:
        sys.exit(f'错误：--datetime 格式不对，应为 "YYYY-MM-DD HH:MM"，收到的是 "{args.datetime}"')

    year, month, day = dt_input.year, dt_input.month, dt_input.day
    hour, minute = dt_input.hour, dt_input.minute
    gender = args.gender
    location = args.location
    longitude = args.longitude

    # ============ 真太阳时校正 ============
    longitude_correction = 0.0
    eot_correction = equation_of_time_minutes(year, month, day)
    location_used = "未提供（使用北京时间，不做任何校正）"

    if longitude is not None:
        longitude_correction = (longitude - 120) * 4
        location_used = f"经度 {longitude}°E"
    elif location and location in CITY_LONGITUDE:
        lng = CITY_LONGITUDE[location]
        longitude_correction = (lng - 120) * 4
        location_used = f"{location}（经度 {lng}°E）"
    elif location:
        location_used = (
            f"{location}（⚠️ 不在内置表中，经度时差未校正，仅应用了均时差。"
            f"建议查询该地经度后用 --longitude 重跑）"
        )
    else:
        # 没有任何位置信息时，连均时差都不应用
        eot_correction = 0.0

    total_correction = longitude_correction + eot_correction

    original_dt = dt_input
    # 两种校正分别算（用于时辰边界检测）
    dt_lng_only = original_dt + timedelta(minutes=round(longitude_correction))
    dt_full = original_dt + timedelta(minutes=round(total_correction))

    shichen_lng = hour_to_shichen(dt_lng_only.hour)
    shichen_full = hour_to_shichen(dt_full.hour)
    shichen_changed = (shichen_lng != shichen_full)

    # 默认采用完整校正（最严谨的真太阳时）
    dt = dt_full

    # ============ 排盘 ============
    ensure_lunar_python()
    from lunar_python import Solar

    is_late_zi = (dt.hour == 23)
    if is_late_zi:
        probe = Solar.fromYmdHms(dt.year, dt.month, dt.day, 22, 59, 0)
    else:
        probe = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)

    lunar = probe.getLunar()
    ec = lunar.getEightChar()

    year_gz = ec.getYear()
    month_gz = ec.getMonth()
    day_gz = ec.getDay()
    if is_late_zi:
        day_gan = day_gz[0]
        time_gz = WUSHUDUN[day_gan] + '子'
    else:
        time_gz = ec.getTime()

    # ============ 大运顺逆 ============
    year_gan = year_gz[0]
    is_yang = year_gan in YANG_GAN
    is_male = gender == '男'
    direction = '顺行' if (is_yang and is_male) or (not is_yang and not is_male) else '逆行'

    # ============ 大运排布 ============
    # lunar_python 约定：getYun(1) 为男命，getYun(0) 为女命
    yun = ec.getYun(1 if is_male else 0)
    start_year_offset = yun.getStartYear()
    start_month = yun.getStartMonth()
    start_day = yun.getStartDay()
    start_solar = yun.getStartSolar()
    start_actual_year = start_solar.getYear()

    da_yun_list = yun.getDaYun()
    da_yun_data = []
    idx = 0
    for d in da_yun_list[:10]:
        if d.getGanZhi():
            age = start_year_offset + idx * 10
            yr = start_actual_year + idx * 10
            da_yun_data.append({'age': age, 'start': yr, 'end': yr + 9, 'gz': d.getGanZhi()})
            idx += 1
            if idx >= 9:
                break

    # ============ 当前年龄和大运 ============
    today = datetime.now()
    age_real = today.year - dt.year - (1 if (today.month, today.day) < (dt.month, dt.day) else 0)
    age_xu = today.year - dt.year + 1
    current_dy = next((d for d in da_yun_data if d['start'] <= today.year <= d['end']), None)

    liunian_solar = Solar.fromYmdHms(today.year, 6, 15, 12, 0, 0)
    liunian_gz = liunian_solar.getLunar().getYearInGanZhi()

    # ============ 五行 ============
    ming_count = {'木': 0, '火': 0, '土': 0, '金': 0, '水': 0}
    for c in year_gz + month_gz + day_gz + time_gz:
        ming_count[WX_MAP[c]] += 1

    # ============ 藏干 ============
    yh = ZHI_CANGGAN[year_gz[1]]
    mh = ZHI_CANGGAN[month_gz[1]]
    dh = ZHI_CANGGAN[day_gz[1]]
    th = ZHI_CANGGAN[time_gz[1]]

    # ============ 十神 ============
    sst = SST_TABLE[day_gz[0]]
    ss = lambda g: sst.get(g, '?')

    # ============ 流年作用关系计算模块 ============
    # 原局四柱
    yuan_ju = [
        ('年柱', year_gz[0], year_gz[1]),
        ('月柱', month_gz[0], month_gz[1]),
        ('日柱', day_gz[0], day_gz[1]),
        ('时柱', time_gz[0], time_gz[1]),
    ]
    day_zhi = day_gz[1]

    def analyze_year_vs_yuanju(yt_gan, yt_zhi):
        """流年 vs 原局四柱的作用关系"""
        interactions = []
        for pos, gan, zhi in yuan_ju:
            for rel in check_gan_relation(yt_gan, gan):
                interactions.append(f"{pos}干:{rel}")
            for rel in check_zhi_relation(yt_zhi, zhi):
                interactions.append(f"{pos}支:{rel}")
        for sx in check_sanxing([yt_zhi] + [z for _, _, z in yuan_ju]):
            interactions.append(f"三刑:{sx}")
        return interactions

    def analyze_yun_vs_yuanju(yun_gz):
        """大运 vs 原局四柱的作用关系"""
        yun_gan, yun_zhi = yun_gz[0], yun_gz[1]
        interactions = []
        for pos, gan, zhi in yuan_ju:
            for rel in check_gan_relation(yun_gan, gan):
                interactions.append(f"{pos}干:{rel}")
            for rel in check_zhi_relation(yun_zhi, zhi):
                interactions.append(f"{pos}支:{rel}")
        for sx in check_sanxing([yun_zhi] + [z for _, _, z in yuan_ju]):
            interactions.append(f"三刑:{sx}")
        return interactions

    # ============ 关键信号识别（星宫势动 + 五级权重）============
    #
    # 信号分级：S/A/B/C/D 五档，严格按"配偶星损 + 夫妻宫动 + 岁运触发"闭环判定
    # 男命核心：财星状态 + 夫妻宫 + 大运流年触发
    # 女命核心：夫星（官杀）状态 + 夫妻宫 + 食伤剋官闭环
    # 藏干分层：本气/中气/余气三档权重，非冲合触发时只算背景分
    # 七杀被合不一刀切，只在七杀为用神时算负面
    # 日支伏吟为应期，非凶兆，吉凶由喜忌决定
    def detect_key_signals(yt_gan, yt_zhi, yun_gan, yun_zhi, is_male):
        signals = []
        yt_shishen = ss(yt_gan)
        bijie_set = ('比肩', '劫财')
        cai_set = ('正财', '偏财')
        guansha_set = ('正官', '七杀')

        # ---- 原局比劫总权重（明字 1.0, 本气 0.75, 中气 0.4, 余气 0.15）----
        bijie_score = 0
        # 明字（年月时）
        for g in [year_gz[0], month_gz[0], time_gz[0]]:
            if ss(g) in bijie_set:
                bijie_score += 1.0
        # 地支藏（本气/中气/余气分权）
        for pos, gan, zhi in yuan_ju:
            for idx_cg, cg in enumerate(ZHI_CANGGAN.get(zhi, [])):
                if ss(cg) in bijie_set:
                    weights = [0.75, 0.4, 0.15]
                    bijie_score += weights[idx_cg]

        # ---- 原局财星 / 官杀状态 ----
        cai_in_yuanju = []
        guansha_in_yuanju = []
        for pos, gan, zhi in yuan_ju:
            if ss(gan) in cai_set:
                cai_in_yuanju.append((pos, gan, '透干'))
            if ss(gan) in guansha_set:
                guansha_in_yuanju.append((pos, gan, '透干'))
            for idx_cg, cg in enumerate(ZHI_CANGGAN.get(zhi, [])):
                qi = ['本气', '中气', '余气'][idx_cg]
                if ss(cg) in cai_set:
                    cai_in_yuanju.append((pos, cg, f'{zhi}藏-{qi}'))
                if ss(cg) in guansha_set:
                    guansha_in_yuanju.append((pos, cg, f'{zhi}藏-{qi}'))

        cai_strong = (any(s == '透干' for _, _, s in cai_in_yuanju)
                      and any('本气' in s for _, _, s in cai_in_yuanju))
        guansha_strong = (any(s == '透干' for _, _, s in guansha_in_yuanju)
                          and any('本气' in s for _, _, s in guansha_in_yuanju))

        # ===== 男命核心信号 =====
        if is_male:
            # 信号 1：比劫剋财
            bijie_year_active = False
            bijie_source = []
            if yt_shishen in bijie_set:
                bijie_year_active = True
                bijie_source.append(f'天干{yt_gan}透')
            yt_zhi_canggan = ZHI_CANGGAN.get(yt_zhi, [])
            if yt_zhi_canggan and ss(yt_zhi_canggan[0]) in bijie_set:
                bijie_year_active = True
                bijie_source.append(f'{yt_zhi}本气{yt_zhi_canggan[0]}')
            elif len(yt_zhi_canggan) >= 2 and ss(yt_zhi_canggan[1]) in bijie_set:
                zhi_touched = any(check_zhi_relation(yt_zhi, z) for _, _, z in yuan_ju)
                if zhi_touched and bijie_score >= 2.5:
                    bijie_year_active = True
                    bijie_source.append(f'{yt_zhi}中气{yt_zhi_canggan[1]}(触发)')

            if bijie_year_active and cai_in_yuanju:
                day_zhi_touched = ((yt_zhi, day_zhi) in _LIUCHONG_PAIRS
                                   or (yt_zhi, day_zhi) in _XIANGHAI_PAIRS
                                   or yt_zhi == day_zhi)
                if not cai_strong and day_zhi_touched:
                    signals.append(f'🔥比劫剋财+财弱+夫妻宫动({",".join(bijie_source)})')
                elif not cai_strong:
                    signals.append(f'🔴比劫剋财(财星弱,{",".join(bijie_source)})')
                else:
                    signals.append(f'🟠比劫透/动(财星有根可承受,{",".join(bijie_source)})')
            elif bijie_year_active and not cai_in_yuanju:
                signals.append('🟡比劫动(原局无财星,主竞争耗财)')

            # 信号 2：财星受冲合
            for pos, cai_gan, source in cai_in_yuanju:
                if (yt_gan, cai_gan) in _TIANGAN_HE:
                    signals.append(f'🟠财星{cai_gan}被流年合({pos})')
                    break

            # 信号 3：财星透干（中性）
            if yt_shishen in cai_set:
                signals.append('🟡财星透干(妻星显)')

        # ===== 女命核心信号 =====
        if not is_male:
            # 信号 1：伤官见官
            if yt_shishen == '伤官':
                zhengguan_attacked = []
                for pos, gan, zhi in yuan_ju:
                    if ss(gan) == '正官' and gan in _GAN_KE.get(yt_gan, set()):
                        zhengguan_attacked.append((pos, gan))
                if ss(yun_gan) == '正官' and yun_gan in _GAN_KE.get(yt_gan, set()):
                    zhengguan_attacked.append(('大运', yun_gan))

                if zhengguan_attacked:
                    day_zhi_chong = (yt_zhi, day_zhi) in _LIUCHONG_PAIRS
                    targets = ",".join(f"{p}{g}" for p, g in zhengguan_attacked)
                    if day_zhi_chong:
                        signals.append(f'🔥伤官见官+夫妻宫被冲({targets})')
                    else:
                        signals.append(f'🔴伤官见官({targets})')
            elif yt_shishen == '食神':
                qisha_exists = any(ss(g) == '七杀' for _, g, _ in yuan_ju) or ss(yun_gan) == '七杀'
                if qisha_exists:
                    signals.append('🟡食神制杀(需看七杀是用是忌)')

            # 信号 2：夫星被合走
            for pos, gs_gan, source in guansha_in_yuanju:
                if source == '透干' and (yt_gan, gs_gan) in _TIANGAN_HE:
                    day_zhi_chong = (yt_zhi, day_zhi) in _LIUCHONG_PAIRS
                    if day_zhi_chong:
                        signals.append(f'🔥夫星{gs_gan}被合走+夫妻宫被冲({pos})')
                    else:
                        signals.append(f'🔴夫星{gs_gan}被流年合走({pos})')
                    break

            # 信号 3：官杀透干
            if yt_shishen in guansha_set:
                signals.append('🟡官杀透干(夫星显)')

        # ===== 共通信号 =====
        # 夫妻宫被冲
        if (yt_zhi, day_zhi) in _LIUCHONG_PAIRS:
            if is_male and cai_in_yuanju and not cai_strong:
                signals.append(f'🔴流年冲日支+财星弱({yt_zhi}{day_zhi}冲)')
            elif not is_male and guansha_in_yuanju and not guansha_strong:
                signals.append(f'🔴流年冲日支+夫星弱({yt_zhi}{day_zhi}冲)')
            else:
                signals.append(f'🟠流年冲日支({yt_zhi}{day_zhi}冲)')

        # 日支伏吟（应期）
        if yt_zhi == day_zhi:
            signals.append('🟠日支伏吟(夫妻宫应期,吉凶看喜忌)')

        # 流年合日支
        if (yt_zhi, day_zhi) in _LIUHE_PAIRS:
            signals.append(f'🟡合日支({yt_zhi}{day_zhi}合,关系活跃)')

        # 三刑动日支
        for sx in check_sanxing([yt_zhi] + [z for _, _, z in yuan_ju]):
            if day_zhi in sx:
                signals.append(f'🟠三刑动日支({sx})')

        # 七杀被合（辅助信号）
        qisha_positions = [(pos, gan) for pos, gan, _ in yuan_ju if ss(gan) == '七杀']
        if ss(yun_gan) == '七杀':
            qisha_positions.append(('大运', yun_gan))
        for pos, qs_gan in qisha_positions:
            if (yt_gan, qs_gan) in _TIANGAN_HE:
                if is_male:
                    signals.append(f'🟡七杀被合({pos}{qs_gan},约束力变化,需看用忌)')
                else:
                    signals.append(f'🟠夫星七杀被合({pos}{qs_gan})')
                break

        # 流年合大运干
        if (yt_gan, yun_gan) in _TIANGAN_HE:
            yun_shishen = ss(yun_gan)
            if yun_shishen in cai_set or yun_shishen in guansha_set:
                signals.append(f'🟠流年合大运{yun_gan}(大运为{yun_shishen})')
            else:
                signals.append(f'🟡流年合大运{yun_gan}')

        # 流年剋大运干（背景）
        if yt_gan in _GAN_KE.get(yun_gan, set()):
            signals.append(f'🔵流年剋大运干({yt_gan}剋{yun_gan})')

        return signals

    # ============ 生成完整流年表 ============
    def get_yun_for_year(y):
        for d in da_yun_data:
            if d['start'] <= y <= d['end']:
                return d['gz']
        return None

    def get_yun_start_year(yun_gz):
        for d in da_yun_data:
            if d['gz'] == yun_gz:
                return d['start']
        return None

    start_y = start_actual_year
    end_y = dt.year + 80
    liunian_table = []
    for y in range(start_y, end_y + 1):
        gz = year_to_ganzhi(y)
        age = y - dt.year
        yun_gz_y = get_yun_for_year(y)
        if not yun_gz_y:
            continue
        liunian_table.append({
            'year': y, 'age': age, 'gz': gz, 'yun': yun_gz_y,
            'interactions': analyze_year_vs_yuanju(gz[0], gz[1]),
            'signals': detect_key_signals(gz[0], gz[1], yun_gz_y[0], yun_gz_y[1], is_male),
            'is_new_yun': (y == get_yun_start_year(yun_gz_y)),
        })

    # ============ 输出 ============
    print("# 排盘结果\n")
    print("## 基本信息")
    print(f"- 输入时间：{original_dt.strftime('%Y-%m-%d %H:%M')}（北京时间）")
    print(f"- 出生地：{location_used}")
    print(f"- 经度时差：{longitude_correction:+.1f} 分钟")
    print(f"- 均时差：{eot_correction:+.2f} 分钟（{original_dt.date()}）")
    print(f"- 真太阳时合计校正：{total_correction:+.1f} 分钟")
    print(f"- 真太阳时：{dt_full.strftime('%Y-%m-%d %H:%M')}")
    print(f"- 性别：{gender}")
    print(f"- 当前年龄：实岁 {age_real}，虚岁 {age_xu}")

    # 时辰边界警告
    if shichen_changed:
        print()
        print("⚠️ **重要警告：均时差导致时辰发生变化**")
        print(f"  - 只校正经度的话：{dt_lng_only.strftime('%H:%M')} → **{shichen_lng}时**")
        print(f"  - 加上均时差后：{dt_full.strftime('%H:%M')} → **{shichen_full}时**")
        print(f"  - 当前脚本采用完整真太阳时校正（{shichen_full}时）排盘")
        print(f"  - 如果命主已习惯按 {shichen_lng}时 排的盘，需要核对——确认哪个时辰是命主习惯的版本后可重新排")

    if is_late_zi:
        print("- 时辰说明：晚子时（方式 A：日柱不换日，时柱按当天日干起子时）")
    print()

    print("## 大运顺逆判断")
    print(f"- 命主为 **{gender}**，年柱 **{year_gz}**，年干 **{year_gan}** 为 **{'阳' if is_yang else '阴'}** 干")
    print(f"- 所以是 **{'阳' if is_yang else '阴'}{gender}**，大运 **{direction}**\n")

    print("## 四柱八字\n")
    print("| | 年柱 | 月柱 | 日柱 | 时柱 |")
    print("|---|---|---|---|---|")
    print(f"| 干支 | {year_gz} | {month_gz} | **{day_gz}** | {time_gz} |")
    print(f"| 天干十神 | {ss(year_gz[0])} | {ss(month_gz[0])} | 日主 | {ss(time_gz[0])} |")
    print(f"| 藏干 | {'、'.join(yh)} | {'、'.join(mh)} | {'、'.join(dh)} | {'、'.join(th)} |")
    print(f"| 藏干十神 | {'/'.join(ss(g) for g in yh)} | {'/'.join(ss(g) for g in mh)} | {'/'.join(ss(g) for g in dh)} | {'/'.join(ss(g) for g in th)} |\n")

    print("## 五行分布（明字统计）")
    for wx, c in ming_count.items():
        print(f"- {wx}：{c} {'●' * c if c else '○'}")
    print()

    print(f"## 大运排布（{direction}）")
    print(f"- 起运：出生后 **{start_year_offset} 年 {start_month} 个月 {start_day} 天**"
          f"（公历 {start_solar.getYear()}-{start_solar.getMonth():02d}-{start_solar.getDay():02d} 开始）\n")
    print("| 起始岁数 | 起止年份 | 干支 | 天干十神 |")
    print("|---|---|---|---|")
    for d in da_yun_data:
        cur = " ← **当前**" if current_dy and d['start'] == current_dy['start'] else ""
        print(f"| {d['age']} 岁 | {d['start']}-{d['end']} | {d['gz']} | {ss(d['gz'][0])}{cur} |")
    print()

    if current_dy:
        walked = today.year - current_dy['start']
        remaining = current_dy['end'] - today.year
        print("## 当前位置")
        print(f"- 当前大运：**{current_dy['gz']}**（{current_dy['start']}-{current_dy['end']}），"
              f"已走 {walked} 年，剩余 {remaining} 年")
        print(f"- 当前流年：**{liunian_gz}**（{today.year}年）")
        print()

    # ---- 大运 vs 原局作用表 ----
    print("## 各大运与原局的作用关系")
    print()
    print("| 大运 | 起止 | 大运 vs 原局作用 |")
    print("|---|---|---|")
    for d in da_yun_data:
        yun_interactions = analyze_yun_vs_yuanju(d['gz'])
        interactions_str = '; '.join(yun_interactions) if yun_interactions else '(无明显作用)'
        cur_mark = " ←当前" if current_dy and d['start'] == current_dy['start'] else ""
        print(f"| **{d['gz']}**{cur_mark} | {d['start']}-{d['end']} | {interactions_str} |")
    print()

    # ---- 流年作用关系完整表 ----
    print("## 流年作用关系完整表（从起运到 80 岁）")
    print()
    print("说明（信号分五档，按强度从高到低）：")
    print("- 🔥 S级 极高危/强应期：配偶星损 + 夫妻宫动 + 岁运同时触发")
    print("- 🔴 A级 高危：配偶星或夫妻宫被严重冲克（闭环未完整）")
    print("- 🟠 B级 警示：有动象，但未形成完整风险闭环")
    print("- 🟡 C级 辅助：可辅助解释，不单独定吉凶（七杀被合、流年合大运干等多在此档）")
    print("- 🔵 D级 背景：只作参考，不作判断依据")
    print("- 关键信号是基于'星宫势动'框架和五行作用自动识别，仅作初判")
    print("- 大运 vs 原局的作用在每个大运首年标注（其他年份相同）")
    print()
    print("| 年份 | 岁 | 流年 | 所在大运 | 流年 vs 原局作用 | 关键信号 |")
    print("|---|---|---|---|---|---|")

    current_year_num = today.year
    for row in liunian_table:
        y = row['year']
        interactions_str = '; '.join(row['interactions']) if row['interactions'] else '—'
        signals_str = ' '.join(row['signals']) if row['signals'] else ''
        year_mark = ' **(今年)**' if y == current_year_num else ''
        yun_mark = '★' if row['is_new_yun'] else ''
        time_mark = '✓' if y < current_year_num else ('●' if y == current_year_num else '○')
        print(f"| {time_mark}{y}{year_mark} | {row['age']} | {row['gz']} | {row['yun']}{yun_mark} | {interactions_str} | {signals_str} |")

    print()
    print("**符号说明**：✓ 已过年份  ● 当年  ○ 未来年份  ★ 大运起始年")


if __name__ == '__main__':
    main()
