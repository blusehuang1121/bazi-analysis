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

# Windows 终端默认 GBK/cp936，输出 emoji 与部分汉字会崩（UnicodeEncodeError）。
# 强制 stdout 用 UTF-8，保证脚本在任何 codepage 下都能正常输出 markdown。
try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass


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


# ============ 时辰反推（--verify-events）支持函数 ============
# 命主反馈过往确认事件 → 反查每个候选时柱在那些年是否产生了对应面向的应期信号
# → 应期对得最齐的时柱最可能是真时辰。打分逻辑对应 references/blind_imagery.md 的"信号↔面向反查表"。
# 只用模块级原语，独立于 main() 里的 detect_key_signals，零侵入。

_DOMAIN_ALIASES = {
    'marriage': ['婚', '感情', '恋', '配偶', '老婆', '老公', '对象', '结婚', '离婚', '分手'],
    'career':   ['事业', '工作', '升职', '升迁', '跳槽', '换工作', '创业', '职', '事业变动', '失业'],
    'wealth':   ['财', '钱', '破财', '进财', '投资', '收入', '生意', '亏'],
    'study':    ['学业', '升学', '考试', '读书', '考证', '毕业', '学历', '上学'],
    'health':   ['健康', '病', '手术', '住院', '身体', '伤', '车祸', '意外'],
    'move':     ['搬', '迁', '换城市', '移民', '远行', '出国', '调动'],
    'children': ['子女', '生子', '孩子', '怀孕', '生育', '产子', '添丁', '生孩'],
    'family':   ['家庭', '父母', '父亲', '母亲', '长辈', '家里', '爸', '妈'],
}
_DOMAIN_NAMES = {
    'marriage': '婚恋', 'career': '事业', 'wealth': '财', 'study': '学业',
    'health': '健康', 'move': '搬迁', 'children': '子女', 'family': '家庭',
}
# 对定时辰有区分力的面向（依赖时支，时支随时辰变）
_TIME_SENSITIVE_DOMAINS = {'children'}


def normalize_domain(label):
    """把命主反馈的自由文本面向标签归一到内部 domain key。"""
    for key, aliases in _DOMAIN_ALIASES.items():
        for a in aliases:
            if a in label:
                return key
    return None


def hour_pillar_candidates(day_gan):
    """根据日干用五鼠遁推出 12 个候选时柱（子时起，依次子丑寅…亥）。"""
    zi_gan = WUSHUDUN[day_gan]
    zi_idx = _GAN10.index(zi_gan)
    return [_GAN10[(zi_idx + i) % 10] + zhi for i, zhi in enumerate(_ZHI12)]


def _zhi_rel_types(a, b):
    """返回 a、b 两支之间的关系类型集合：冲/合/半合/拱/害/刑/自刑/伏吟。"""
    types = set()
    for r in check_zhi_relation(a, b):
        for t in ('冲', '半合', '拱', '自刑', '伏吟', '合', '害', '刑'):
            if t in r:
                types.add(t)
    return types


def score_events(day_gz, year_gz, month_gz, time_gz, is_male, events):
    """对一个候选盘给确认事件打"应期对齐分"。
    events: [(year:int, domain_key:str)]
    返回 (total, details, time_contributed)。
    time_contributed: 时支是否在某事件里实际贡献了得分（衡量该批证据对定时辰是否有区分力）。"""
    sst = SST_TABLE[day_gz[0]]
    ss = lambda g: sst.get(g, '?')
    year_zhi, month_zhi, day_zhi, time_zhi = year_gz[1], month_gz[1], day_gz[1], time_gz[1]
    gans = [year_gz[0], month_gz[0], day_gz[0], time_gz[0]]
    zhis_named = [('年支', year_zhi), ('月支', month_zhi), ('日支', day_zhi), ('时支', time_zhi)]

    cai = ('正财', '偏财'); guansha = ('正官', '七杀'); yin = ('正印', '偏印')
    bijie = ('比肩', '劫财'); shishang = ('食神', '伤官')
    has_cai = (any(ss(g) in cai for g in gans)
               or any(any(ss(cg) in cai for cg in ZHI_CANGGAN.get(z, [])) for _, z in zhis_named))
    spouse = cai if is_male else guansha
    child = guansha if is_male else shishang
    ma = ('寅', '申', '巳', '亥')

    total = 0
    details = []
    time_contributed = False
    for (yr, dom) in events:
        gz = year_to_ganzhi(yr)
        lg, lz = gz[0], gz[1]
        sl = ss(lg)
        best = 0
        note = ''
        used_time = False
        rel = lambda z: _zhi_rel_types(lz, z)

        if dom == 'marriage':
            r = rel(day_zhi)
            if r & {'冲', '合', '刑', '害', '伏吟'}:
                best, note = 3, f'流年{lz}动日支{day_zhi}({"/".join(r)})'
            for g in gans:
                if ss(g) in spouse and (lg, g) in _TIANGAN_HE:
                    best = max(best, 2); note = note or f'配偶星{g}被流年{lg}合'
            if sl in spouse:
                best = max(best, 2); note = note or f'流年透配偶星{sl}'
            if '半合' in r:
                best = max(best, 1)
        elif dom == 'career':
            if sl in guansha:
                best, note = 3, f'流年透{sl}'
            if rel(month_zhi) & {'冲', '合', '刑'}:
                best = max(best, 2); note = note or f'流年{lz}动月支{month_zhi}'
            if sl == '伤官':
                best = max(best, 2); note = note or '流年透伤官(事业动)'
            if sl in ('食神',) + cai:
                best = max(best, 1)
        elif dom == 'wealth':
            if sl in cai:
                best, note = 3, f'流年透财{sl}'
            if sl in bijie and has_cai:
                best = max(best, 3); note = note or '流年透比劫+原局有财(动财)'
            for nm, z in zhis_named:
                zc = ZHI_CANGGAN.get(z, [])
                if zc and ss(zc[0]) in cai and (rel(z) & {'冲', '合'}):
                    best = max(best, 2); note = note or f'流年动{nm}财星'
        elif dom == 'study':
            if sl in yin:
                best, note = 3, f'流年透印{sl}'
            if rel(month_zhi) & {'合', '半合'}:
                best = max(best, 2); note = note or '流年合月支'
            if sl in shishang:
                best = max(best, 1)
        elif dom == 'health':
            if '冲' in rel(day_zhi):
                best, note = 3, f'流年{lz}冲日支{day_zhi}'
            sx = check_sanxing([lz, year_zhi, month_zhi, day_zhi, time_zhi])
            joined = ''.join(sx)
            if sx and (day_zhi in joined or year_zhi in joined):
                best = max(best, 2); note = note or '三刑动身宫'
            if day_gz[0] in _GAN_KE.get(lg, set()):
                best = max(best, 2); note = note or f'流年{lg}剋日主'
            if '冲' in rel(year_zhi):
                best = max(best, 1)
        elif dom == 'move':
            moved = False
            for nm, z in (('年支', year_zhi), ('月支', month_zhi), ('日支', day_zhi)):
                if '冲' in rel(z):
                    if lz in ma or z in ma:
                        best, note, moved = 3, f'驿马动:流年{lz}冲{nm}{z}', True
                    else:
                        best = max(best, 2); note = note or f'流年{lz}冲{nm}{z}'; moved = True
            if not moved and any(rel(z) & {'冲', '刑'} for _, z in zhis_named):
                best = max(best, 1)
        elif dom == 'children':
            r = rel(time_zhi)
            if r & {'冲', '合', '刑', '害', '伏吟'}:
                best, note, used_time = 3, f'流年{lz}动时支{time_zhi}({"/".join(r)})', True
            if sl in child:
                best = max(best, 2); note = note or f'流年透子女星{sl}'
            if '半合' in r:
                best = max(best, 1); used_time = True
        elif dom == 'family':
            hit = False
            for nm, z in (('年支', year_zhi), ('月支', month_zhi)):
                if rel(z) & {'冲', '合', '刑'}:
                    best, note, hit = 3, f'流年{lz}动{nm}{z}', True
            if not hit and (sl in yin or sl == '偏财'):
                best = max(best, 2); note = note or f'流年透{sl}(父母星)'

        total += best
        if used_time:
            time_contributed = True
        details.append((yr, dom, gz, best, note))
    return total, details, time_contributed


def run_verify_events(day_gz, year_gz, month_gz, is_male, raw_events, hour_filter):
    """时辰反推主流程：枚举候选时柱，按确认事件应期对齐分排名，打印结果。"""
    # 解析事件
    events = []
    for chunk in raw_events.replace('，', ',').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        sep = '：' if '：' in chunk else (':' if ':' in chunk else None)
        if sep is None:
            print(f"⚠️ 格式无法识别（缺冒号）：{chunk}（已跳过）")
            continue
        yr_s, dom_s = chunk.split(sep, 1)
        try:
            yr = int(yr_s.strip())
        except ValueError:
            print(f"⚠️ 年份无法识别：{yr_s.strip()}（已跳过）")
            continue
        dom = normalize_domain(dom_s.strip())
        if dom is None:
            print(f"⚠️ 面向无法识别：{dom_s.strip()}（已跳过）。支持：婚姻/事业/财/学业/健康/搬迁/子女/家庭")
            continue
        events.append((yr, dom, dom_s.strip()))

    if not events:
        print("错误：没有可用的确认事件。格式示例：--verify-events \"2003:学业,2009:婚恋,2015:子女\"")
        return

    events_for_score = [(yr, dom) for yr, dom, _ in events]
    day_gan = day_gz[0]
    all_cands = hour_pillar_candidates(day_gan)
    if hour_filter:
        wanted = set(c.strip() for c in hour_filter.replace('，', ',').split(','))
        cands = [c for c in all_cands if c[1] in wanted] or all_cands
    else:
        cands = all_cands

    scored = []
    for cand in cands:
        total, details, time_used = score_events(day_gz, year_gz, month_gz, cand, is_male, events_for_score)
        scored.append({'gz': cand, 'total': total, 'details': details, 'time_used': time_used})
    scored.sort(key=lambda x: x['total'], reverse=True)

    # 是否有任何候选靠时支区分（即证据里有子女/晚年类、且确实命中时支）
    any_time_discriminate = any(s['time_used'] for s in scored)
    time_sensitive_events = [e for e in events if e[1] in _TIME_SENSITIVE_DOMAINS]

    print("# 时辰反推结果\n")
    print("**原理**：每个候选时柱在命主确认的事件年是否产生对应面向的应期信号，对得越齐越可能是真时辰。")
    print("打分对应 `references/blind_imagery.md` 的信号↔面向反查表。\n")
    print(f"- 固定日柱：**{day_gz}**（假设出生日期可靠，仅时辰待定）")
    print(f"- 年/月柱：{year_gz} / {month_gz}　性别：{'男' if is_male else '女'}")
    print("- 确认事件：" + "，".join(f"{yr}{_DOMAIN_NAMES[dom]}({raw})" for yr, dom, raw in events))
    print()

    print("| 排名 | 候选时柱 | 时支 | 对齐分 | 时支是否参与定时 |")
    print("|---|---|---|---|---|")
    for i, s in enumerate(scored, 1):
        mark = '✓' if s['time_used'] else '—'
        print(f"| {i} | **{s['gz']}** | {s['gz'][1]} | {s['total']} | {mark} |")
    print()

    top = scored[0]
    tie = [s for s in scored if s['total'] == top['total']]
    print("## 最佳候选明细\n")
    if len(tie) > 1:
        print(f"⚠️ **{len(tie)} 个候选并列最高分（{top['total']}）**：{'、'.join(s['gz'] for s in tie)}——这批证据无法唯一确定时辰，需补充更多事件。\n")
    print(f"**{top['gz']}** 的逐事件命中：\n")
    print("| 事件年 | 面向 | 流年 | 得分 | 命中信号 |")
    print("|---|---|---|---|---|")
    for yr, dom, gz, best, note in top['details']:
        note_disp = note if note else ('弱信号（仅十神倾向）' if best > 0 else '（未对上）')
        print(f"| {yr} | {_DOMAIN_NAMES[dom]} | {gz} | {best} | {note_disp} |")
    print()

    # 区分力提示
    print("## ⚠️ 区分力提示\n")
    if not time_sensitive_events:
        print("- **本批证据对定时辰的区分力弱**：所列事件多落在日支（婚姻/健康）或年月支（事业/家庭），"
              "而日支、年月支**不随时辰改变**——它们能验证整盘大方向，但无法单独定时辰。")
        print("- **强烈建议补充子女类、晚年/事业归宿类事件**（如子女出生年份）：时支随时辰变化，"
              "这类事件才能真正区分相邻时辰。重跑：`--verify-events \"...,YYYY:子女\"`")
    elif not any_time_discriminate:
        print("- 提供了子女/晚年类事件，但在所有候选时柱下都未命中时支应期——可能事件年记忆有偏差，或日柱/年月柱本身需要复核。")
    else:
        print("- 本批证据包含时支敏感事件且有候选靠时支命中，定时辰区分力较好。")
    print("- 分数接近的候选都应保留为候选时柱，结合命主对盘的体感（性格、长相、六亲）综合判断，不要只看分数。")
    print("- 时辰定下后，把结论写入命主档案（见 output_structure.md「命主档案」节），后续分析按此时辰展开。")


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
    parser.add_argument('--verify-events', default=None,
                        help='时辰反推模式：传入命主确认的过往事件，格式 "年:面向,年:面向"，'
                             '如 "2003:学业,2009:婚恋,2015:子女"。'
                             '面向支持 婚姻/事业/财/学业/健康/搬迁/子女/家庭。'
                             '脚本会枚举候选时柱，按应期对齐分排名。')
    parser.add_argument('--hour-candidates', default=None,
                        help='配合 --verify-events：限定候选时支范围，如 "寅,卯"。不传则评估全部 12 时辰。')
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

    # ============ 时辰反推模式（早退出，不走常规排盘输出）============
    if args.verify_events:
        run_verify_events(day_gz, year_gz, month_gz, is_male, args.verify_events, args.hour_candidates)
        return

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

        # ===== P 级 内驱型（仅在非 S 级时触发） =====
        # 命理逻辑：内部能量过度堆积/激活 → 主动外溢突破
        # 三条触发条件，任意 2 条同时成立 → P 级
        is_s_level = any('🔥' in s for s in signals)
        if not is_s_level:
            p_conditions = []

            # 条件 1：内部能量激活（A 档：3 现及以上）
            # A 档判定（任一成立即触发）：
            #   1. 原局多重伏吟：流年天干/地支在原局已现 ≥ 2 次（原局双现+流年=3现及以上）
            #   2. 三现伏吟：流年天干/地支 = 大运同位字 + 原局已现 ≥ 1 次（原局+大运+流年=3现）
            #   3. 自刑动：流年地支为自刑字 + 原局有同字
            # B/C 档（岁运并临、单干/单支同字）—— 暂不进 P 级触发，作独立信号或不输出
            yuanju_zhi_list = [z for _, _, z in yuan_ju]
            yuanju_gan_list = [year_gz[0], month_gz[0], day_gz[0], time_gz[0]]
            same_zhi_in_yuanju = yuanju_zhi_list.count(yt_zhi)
            same_gan_in_yuanju = yuanju_gan_list.count(yt_gan)
            self_punish_zhi = ('亥', '辰', '午', '酉')

            if same_zhi_in_yuanju >= 2:
                # 原局多重伏吟（地支）
                p_conditions.append(f'多重伏吟({yt_zhi}地支原局{same_zhi_in_yuanju}现+流年={same_zhi_in_yuanju + 1}现)')
            elif same_gan_in_yuanju >= 2:
                # 原局多重伏吟（天干）
                p_conditions.append(f'多重伏吟({yt_gan}天干原局{same_gan_in_yuanju}现+流年={same_gan_in_yuanju + 1}现)')
            elif yun_zhi == yt_zhi and same_zhi_in_yuanju >= 1:
                # 三现伏吟（原局+大运+流年地支同字）
                p_conditions.append(f'三现伏吟({yt_zhi}地支:原局+大运+流年)')
            elif yun_gan == yt_gan and same_gan_in_yuanju >= 1:
                # 三现伏吟（原局+大运+流年天干同字）
                p_conditions.append(f'三现伏吟({yt_gan}天干:原局+大运+流年)')
            elif yt_zhi in self_punish_zhi and same_zhi_in_yuanju >= 1:
                p_conditions.append(f'自刑动({yt_zhi}{yt_zhi})')

            # 条件 2：食伤透干（"体"的外溢——自我能量主动外显）
            # 盲派"体用"重构：只有食伤、印、比劫属"体"，财、官、杀属"用"
            # 食伤透干 = 体（自我创造力/表达力）主动外溢 → P 级
            # 财星透干 → 单独标"P-财事"，不进 P 触发（"用"进来）
            # 官杀透干 → S 复核路径（外部压力）
            shang_shi_for_cond2 = ('伤官', '食神')
            if yt_shishen in shang_shi_for_cond2:
                p_conditions.append(f'食伤透干({yt_gan})')

            # 条件 3：食伤被合引动（自我表达/创造力被点燃）
            # - 子条件 3A：流年地支与原局食伤位形成六合
            # - 子条件 3B：流年地支与原局某地支形成三合拱合，且拱出的中心字属食伤五行
            shang_shi_set = ('伤官', '食神')
            shang_shi_triggered = False

            # 3A：六合引动食伤位
            for pos, gan, zhi in yuan_ju:
                has_shang_shi = (ss(gan) in shang_shi_set)
                if not has_shang_shi:
                    cg_list = ZHI_CANGGAN.get(zhi, [])
                    if cg_list and ss(cg_list[0]) in shang_shi_set:
                        has_shang_shi = True
                if has_shang_shi and (yt_zhi, zhi) in _LIUHE_PAIRS:
                    p_conditions.append(f'食伤被六合引动({pos}支{zhi}-{yt_zhi}合)')
                    shang_shi_triggered = True
                    break

            # 3B：三合局拱合 — 拱出食伤五行
            if not shang_shi_triggered:
                # 日主 → 食伤五行
                day_to_shang_wuxing = {
                    '甲': '火', '乙': '火',
                    '丙': '土', '丁': '土',
                    '戊': '金', '己': '金',
                    '庚': '水', '辛': '水',
                    '壬': '木', '癸': '木',
                }
                # 三合局：每个五行对应（两个非中心字 + 中心字）
                sanhe_groups = {
                    '水': ('申', '辰', '子'),
                    '火': ('寅', '戌', '午'),
                    '木': ('亥', '未', '卯'),
                    '金': ('巳', '丑', '酉'),
                }
                ss_wx = day_to_shang_wuxing.get(day_gz[0])
                if ss_wx and ss_wx in sanhe_groups:
                    o1, o2, _ = sanhe_groups[ss_wx]
                    pair_match = None
                    if yt_zhi == o1:
                        for pos, _, zhi in yuan_ju:
                            if zhi == o2:
                                pair_match = (pos, zhi)
                                break
                    elif yt_zhi == o2:
                        for pos, _, zhi in yuan_ju:
                            if zhi == o1:
                                pair_match = (pos, zhi)
                                break
                    if pair_match:
                        p_conditions.append(
                            f'食伤被拱合引动({pair_match[0]}支{pair_match[1]}-{yt_zhi}拱{ss_wx})'
                        )

            # P 级判定 — 排除"双重七杀压制"情形（流年七杀+大运七杀=压制型，内驱难显化）
            p_excluded = (yt_shishen == '七杀' and ss(yun_gan) == '七杀')
            if len(p_conditions) >= 2 and not p_excluded:
                signals.append(f'✨P级内驱型({"+".join(p_conditions)})')

        # ===== 盲派"用进来"信号（独立于 P/S 主判定）=====
        # 财星 / 官杀透干属于"用"（外部能量进来），按盲派应分别处理：
        # 财星透干 → P-财事独立标签（不进 P 触发，但标识财事年）
        # 官杀透干 → S 复核（七杀重，正官轻），看制化结构
        guansha_set_check = ('正官', '七杀')
        cai_set_check = ('正财', '偏财')

        if yt_shishen in cai_set_check:
            # 财星透干 = "用"进来 — 默认 P-财事，特殊情况转 S 复核（暂未实现）
            signals.append(f'💰P-财事({yt_shishen}{yt_gan}透干,"用"显化)')

        if yt_shishen in guansha_set_check:
            # 官杀透干 = 外部压力进来，进 S 复核路径
            # 复核：原局或大运是否有食伤制 / 印化（盲派粗判）
            yuanju_gan = [year_gz[0], month_gz[0], day_gz[0], time_gz[0]]
            yuanju_zhi_for_check = [z for _, _, z in yuan_ju]
            shang_shi_check = ('伤官', '食神')
            yin_set = ('正印', '偏印')

            # 食伤是否存在（原局明字 / 大运透 / 食伤本气藏支）
            has_food_god = (
                any(ss(g) in shang_shi_check for g in yuanju_gan)
                or ss(yun_gan) in shang_shi_check
                or any(ZHI_CANGGAN.get(z, ['', ''])[0] and ss(ZHI_CANGGAN[z][0]) in shang_shi_check
                       for z in yuanju_zhi_for_check)
            )
            # 印星是否存在
            has_yin = (
                any(ss(g) in yin_set for g in yuanju_gan)
                or ss(yun_gan) in yin_set
                or any(ZHI_CANGGAN.get(z, ['', ''])[0] and ss(ZHI_CANGGAN[z][0]) in yin_set
                       for z in yuanju_zhi_for_check)
            )

            heaviness = '重' if yt_shishen == '七杀' else '轻'
            if has_food_god or has_yin:
                control_note = []
                if has_food_god:
                    control_note.append('食伤制')
                if has_yin:
                    control_note.append('印化')
                signals.append(
                    f'⚠️S复核-{heaviness}({yt_shishen}{yt_gan}透+有{"/".join(control_note)},盲派粗判)'
                )
            else:
                signals.append(
                    f'⚠️S复核-{heaviness}!!({yt_shishen}{yt_gan}透+无制无化,需人工身能任杀判定)'
                )

        # ===== 岁运并临独立标识 =====
        # 流年干支完全等于大运干支 → 强应期，按原局共字情况分档
        if yt_gan == yun_gan and yt_zhi == yun_zhi:
            yuanju_zhi_yj = [z for _, _, z in yuan_ju]
            yuanju_gan_yj = [year_gz[0], month_gz[0], day_gz[0], time_gz[0]]
            same_zhi_in_yj = yuanju_zhi_yj.count(yt_zhi)
            same_gan_in_yj = yuanju_gan_yj.count(yt_gan)

            # 整柱三叠：原局有同柱（同干同支）
            full_pillar_match = None
            pillar_names = ['年柱', '月柱', '日柱', '时柱']
            for i, (g, z) in enumerate(zip(yuanju_gan_yj, yuanju_zhi_yj)):
                if g == yt_gan and z == yt_zhi:
                    full_pillar_match = pillar_names[i]
                    break

            if full_pillar_match:
                if full_pillar_match == '日柱':
                    signals.append(f'⚡岁运并临-A+({yt_gan}{yt_zhi}日柱三叠,自身/婚姻宫/身体应期,必须人工复核)')
                else:
                    signals.append(f'⚡岁运并临-A+({yt_gan}{yt_zhi}整柱三叠于{full_pillar_match})')
            elif same_zhi_in_yj >= 1 or same_gan_in_yj >= 1:
                same_parts = []
                if same_gan_in_yj >= 1:
                    same_parts.append(f'{yt_gan}天干{same_gan_in_yj}现')
                if same_zhi_in_yj >= 1:
                    same_parts.append(f'{yt_zhi}地支{same_zhi_in_yj}现')
                signals.append(f'⚡岁运并临-A({yt_gan}{yt_zhi}+原局[{",".join(same_parts)}])')
            else:
                signals.append(f'⚡岁运并临-B+({yt_gan}{yt_zhi}+原局无同字)')

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
    print("说明（信号分级，按强度从高到低）：")
    print("- 🔥 S级 外触型强应期：外部能量场对原局形成压力（比劫剋财 + 配偶星损 + 夫妻宫动）。主体感受是\"事情找上门来\"。")
    print("- ✨ P级 内驱型强应期：盲派\"体\"（食伤/比劫/印）的主动外溢（多重伏吟/三现 + 食伤透干 + 食伤被合 三选二）。主体感受是\"我想这么干\"。")
    print("- ⚠️ S复核 官杀透干：盲派\"用\"进来——七杀重 / 正官轻；附带制化判定（有食伤制 or 印化 = 降档）")
    print("- ⚡ 岁运并临：流年干支=大运干支。B+ 单纯并临 / A 原局有同字 / A+ 整柱三叠（日柱三叠必须人工复核）")
    print("- 💰 P-财事：财星透干独立标签（盲派属\"用\"但应在财务/资源/男命妻星）")
    print("- 🔴 A级 单项强触动：配偶星或夫妻宫被冲克（结构未完整闭环）")
    print("- 🟠 B级 有动象：动象存在，但未形成完整结构")
    print("- 🟡 C级 辅助：可辅助解释，不单独定性（七杀被合、流年合大运干等多在此档）")
    print("- 🔵 D级 背景：只作参考")
    print("- ⚠️ 档位是强度提示（值得优先看），不是吉凶定性、更不是危机预警；性质正负由所在大运和经营决定")
    print("- 档位为未标定的启发式阈值，靠命主反馈校准（见 methodology 元规则三）；关键信号仅作初判")
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
    print()

    # ---- S 级 / P 级年份单独汇总表 ----
    s_rows = [r for r in liunian_table if any('🔥' in s for s in r['signals'])]
    p_rows = [r for r in liunian_table if any('✨' in s for s in r['signals'])]

    print("## 🔥 S 级年份汇总（外触型 · 强能量节点）")
    print()
    print("**关键说明（请如实理解，勿夸大）：**")
    print()
    print("- **S 级 = 外触型**。能量来源在原局之外——流年/大运的字对原局形成剋、冲、合。主体感受是\"**事情找上门来，我得应对**\"。")
    print("- **S 级 ≠ 危机预警**。信号可正可负，取决于命主当时所在大运的能量场和经营状态。")
    print("- **底层判定结构是单一的：比劫剋财 + 财弱 + 夫妻宫动**（女命为伤官见官/夫星被合 + 夫妻宫动）。")
    print("  即检测器本质识别的是\"**财与亲密关系的双重触动**\"这一种结构，**不是一个多面向探测器**。")
    print("- **具体应在哪个面向（婚恋/合伙/客户/朋友财务/健康/搬迁/家庭…）脚本无法判定**——")
    print("  同一个结构在不同人、不同大运上会落在不同面向。**面向必须由命主反馈收敛确定，不能由脚本或年龄段臆测。**")
    print("- 下表「候选应事面向」仅按年龄段列出**待命主验证的可能方向**，是反馈收敛的起点，不是预测结论。")
    print()
    def life_stage_facets(age_n):
        """根据年龄段返回该 S 级年份最有可能的多面向应事提示。"""
        if age_n <= 13:
            return "家庭变动 / 父母关系 / 健康事件 / 学业转折 / 搬家转学"
        elif age_n <= 17:
            return "学业重大节点 / 家庭关系 / 心理认知变化 / 健康 / 早期情感"
        elif age_n <= 25:
            return "升学/就业转折 / 感情初体验 / 家庭经济 / 自我定位 / 重要离开或加入"
        elif age_n <= 35:
            return "婚恋重大决定 / 工作变动 / 合伙创业 / 买房搬家 / 父母关系调整 / 子女节点"
        elif age_n <= 50:
            return "事业重大节点 / 合伙股权调整 / 客户/资源结构变动 / 健康节点 / 家庭关系 / 子女"
        elif age_n <= 65:
            return "事业转型 / 子女重大事件 / 父母健康 / 健康/根基调整 / 自我定位重整"
        else:
            return "健康节点 / 子女家庭 / 财产安排 / 生活方式重大调整 / 自我接纳"

    current_year_num = today.year
    if not s_rows:
        print("（本盘从起运到 80 岁无 S 级年份）")
    else:
        print("| 年份 | 岁 | 候选应事面向（待命主反馈收敛，非预测） | 流年 | 大运 |")
        print("|---|---|---|---|---|")
        for row in s_rows:
            y = row['year']
            facets = life_stage_facets(row['age'])
            print(f"| {y} | {row['age']} | {facets} | {row['gz']} | {row['yun']} |")
        print()
        past_s = [r for r in s_rows if r['year'] < current_year_num]
        future_s = [r for r in s_rows if r['year'] > current_year_num]
        print(f"**统计**：过往 S 级年份 {len(past_s)} 个 / 未来 S 级年份 {len(future_s)} 个")
        print()
        print("**说明**：")
        print("- 「候选应事面向」是按年龄段列出的**典型方向候选**，不是预测——所有 S 级触发结构相同"
              "（比劫剋财 + 财弱 + 夫妻宫动），脚本无法判定具体落在哪个面向。")
        print("- **正确用法**：拿过往 S 级年份与命主真实经历逐个对照，确认每年实际应在了哪个面向，"
              "写入命主档案的「信号→面向图谱」。这就是反馈收敛——收敛后才知道这个人的 S 级倾向应在何处。")
        print()
        print("**校准与定时辰**：过往 S 级命中率高 → 算法对此盘适用度高；命中率低 → 优先怀疑时辰，"
              "用 `--verify-events` 反推（注意：婚姻类事件对定时辰无区分力，需配合子女/晚年类事件）。")

    # ---- P 级年份汇总表 ----
    print()
    print("## ✨ P 级年份汇总（内驱型 · 主动突破节点 · 自我能量外溢）")
    print()
    print("**关键说明**：")
    print()
    print("- **P 级 = 内驱型**。能量来源在原局自身——多重伏吟/自刑（内部能量堆积）+ 财官透干（外显机会）+ 食伤被合引动（自我能力被点燃）。主体感受是\"**我想这么干，我感觉到自己的力量**\"。")
    print("- **P 级倾向于主动突破型应事**：主动争取机会、主动开启新阶段、主动做出关键决定。与 S 级的\"被推动响应\"互补。")
    print("- **应事典型形态**：主动争取/拿下机会、技能跃迁、专业突破、创业启动、主动转换跑道、个人作品/创作产出、自我认知重整。")
    print("- **底层判定结构（盲派\"体用\"重构后）**：以下三条任意 2 条同时成立 + 非 S 级 + 不满足排除条件")
    print("  1. **内部能量激活（A 档）**：以下任一成立 →")
    print("     a. 原局多重伏吟（流年天干/地支在原局已 ≥2 现）→ 总计 ≥3 现")
    print("     b. 三现伏吟（流年 = 大运同位字 + 原局已 ≥1 现）→ 原局+大运+流年三现")
    print("     c. 自刑动（流年地支为自刑字 + 原局有同字）")
    print("  2. **食伤透干**（盲派\"体\"的外溢——自我表达/创造力主动激活）")
    print("     注：财星透干 → 已剥离为 💰P-财事 独立标识（\"用\"进来）")
    print("     注：官杀透干 → 已剥离为 ⚠️S复核 独立信号（外部压力）")
    print("  3. **食伤被合引动**：流年与原局食伤位六合 OR 三合局拱出食伤五行（拱合也算引动）")
    print("- **排除条件**：流年七杀 + 大运七杀 → 双重压制（已由 ⚠️S复核 系统处理）")
    print("- **岁运并临**作为独立强节点（⚡ 标识），不进 P 级判定")
    print()
    if not p_rows:
        print("（本盘从起运到 80 岁无 P 级年份）")
    else:
        print("| 年份 | 岁 | 候选应事面向（待命主反馈收敛，非预测） | 流年 | 大运 |")
        print("|---|---|---|---|---|")
        for row in p_rows:
            facets = life_stage_facets(row['age'])
            print(f"| {row['year']} | {row['age']} | {facets} | {row['gz']} | {row['yun']} |")
        print()
        past_p = [r for r in p_rows if r['year'] < current_year_num]
        future_p = [r for r in p_rows if r['year'] > current_year_num]
        print(f"**统计**：过往 P 级年份 {len(past_p)} 个 / 未来 P 级年份 {len(future_p)} 个")
        print()
        print("**S/P 综合校准建议**：")
        print("- 同时拿过往 S 级和 P 级与命主对照——")
        print("- S 级（外触）对应\"事情找上门\"的强应期；P 级（内驱）对应\"自己主动出击\"的突破年")
        print("- 两者性质互补，共同构成命局的\"强能量年份地图\"")


if __name__ == '__main__':
    main()
