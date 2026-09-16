"""
八字排盘核心模块（纯计算，不打印）

bazi_chart.py 负责命令行与 markdown 输出；本模块负责全部计算，便于表驱动测试。

分层（输出里也按这个口径标注）：
- 历法计算：四柱、节气时刻、起运/交运时刻、流年/流月干支——由 lunar_python 与本模块的时间换算给出
- 关系查表：干支合冲刑害破、三合三会三刑——按下方显式规则表，不做合化成败判断
- 传统规则信号：S/P/A/B/C/D 等——作者编码的盲派启发式规则，阈值未经统计标定

时间口径（RULES_VERSION 生效期间固定）：
- 输入：公历、北京时间（UTC+8）。1986–1991 夏令时期间必须声明钟面是否为夏令时
- 年柱、月柱、起运：用北京标准时刻与 lunar_python 的节气时刻比较（两者同一基准）
- 日柱、时柱：用真太阳时（未提供出生地时用北京标准时间）
- 换日：00:00 换日；晚子时（23:00–23:59）日柱不换日，时柱按当天日干起子时（五鼠遁）
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from itertools import combinations

try:
    from lunar_python import Solar
except ImportError as exc:  # 不自动安装：依赖版本需锁定
    raise ImportError('缺少依赖 lunar_python（已验证版本 1.4.8）。请先运行：pip install -r requirements.txt') from exc

RULES_VERSION = '2026.09-r2'
VERIFIED_LUNAR_PYTHON = '1.4.8'
BEIJING_TZ = timezone(timedelta(hours=8))


class InputError(ValueError):
    """输入不合法，或需要用户补充信息才能继续（不做猜测）。"""


# ============ 基础表 ============
GAN10 = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
ZHI12 = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
JIAZI = [GAN10[i % 10] + ZHI12[i % 12] for i in range(60)]
YANG_GAN = {'甲', '丙', '戊', '庚', '壬'}
PILLAR_POS = ['年柱', '月柱', '日柱', '时柱']

# 五鼠遁：日干 → 子时天干
WUSHUDUN = {
    '甲': '甲', '己': '甲', '乙': '丙', '庚': '丙', '丙': '戊', '辛': '戊',
    '丁': '庚', '壬': '庚', '戊': '壬', '癸': '壬',
}

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

# ============ 城市经度表（地级市政府驻地近似值，°E）============
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
    # 2026-09 补充
    "梅州": 116.1, "潮州": 116.6, "揭阳": 116.4, "汕尾": 115.4,
    "惠州": 114.4, "河源": 114.7, "韶关": 113.6, "清远": 113.1,
    "肇庆": 112.5, "江门": 113.1, "阳江": 112.0, "茂名": 110.9,
    "云浮": 112.0, "榆林": 109.7, "延安": 109.5, "汉中": 107.0,
    "喀什": 76.0, "克拉玛依": 84.9, "伊宁": 81.3, "海拉尔": 119.8,
    "赤峰": 118.9, "鄂尔多斯": 109.8, "林芝": 94.4,
}
CHINA_LONGITUDE_RANGE = (73.0, 136.0)

# ============ 中国夏令时（1986–1991）============
# 来源：IANA tz 数据库 Asia/Shanghai（测试中与 zoneinfo 交叉核对）。
# 每段为北京标准时间区间 [开始, 结束)：开始日 02:00 标准时拨快到 03:00；结束日 02:00 夏令时（=01:00 标准时）拨回。
CN_DST_PERIODS = [
    (datetime(1986, 5, 4, 2), datetime(1986, 9, 14, 1)),
    (datetime(1987, 4, 12, 2), datetime(1987, 9, 13, 1)),
    (datetime(1988, 4, 17, 2), datetime(1988, 9, 11, 1)),
    (datetime(1989, 4, 16, 2), datetime(1989, 9, 17, 1)),
    (datetime(1990, 4, 15, 2), datetime(1990, 9, 16, 1)),
    (datetime(1991, 4, 14, 2), datetime(1991, 9, 15, 1)),
]
# 中文资料多记 1988 年 4 月 10 日开始，与 IANA 的 4 月 17 日不一致：这一段按"有分歧"处理
CN_DST_DISPUTED = [(datetime(1988, 4, 10, 2), datetime(1988, 4, 17, 2))]


# ============ 时间换算 ============
def equation_of_time_minutes(d: date) -> float:
    """均时差近似公式（Spencer 1971 简化版），一年内约 -14 ~ +16 分钟。"""
    n = (d - date(d.year, 1, 1)).days + 1
    b = math.radians(360.0 * (n - 81) / 365.0)
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def parse_clock(text: str) -> datetime:
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            pass
    raise InputError(f'出生时间格式不对，应为 "YYYY-MM-DD HH:MM"（公历、北京时间），收到 "{text}"')


def parse_as_of(text: str | None) -> datetime:
    if not text:
        return datetime.now(BEIJING_TZ).replace(tzinfo=None, microsecond=0)
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            pass
    raise InputError(f'--as-of 格式不对，应为 "YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM"（北京时间），收到 "{text}"')


def dst_status(clock: datetime) -> str:
    """判断北京钟面时间与夏令时的关系：none / in_dst / nonexistent / ambiguous / disputed。"""
    for start, end in CN_DST_PERIODS:
        # 钟面上：开始日 02:00–03:00 不存在；结束日 01:00–02:00 出现两次
        if start <= clock < start + timedelta(hours=1):
            return 'nonexistent'
        if end <= clock < end + timedelta(hours=1):
            return 'ambiguous'
        if start + timedelta(hours=1) <= clock < end:
            return 'in_dst'
    for start, end in CN_DST_DISPUTED:
        if start <= clock < end:
            return 'disputed'
    return 'none'


@dataclass
class BirthTime:
    clock: datetime                 # 用户输入的钟面时间
    standard: datetime              # 北京标准时间（UTC+8，已处理夏令时）
    dst_note: str                   # 夏令时处理说明
    longitude: float | None         # 用于校正的经度；None = 未校正
    location_label: str
    longitude_minutes: float        # 经度时差（地方平太阳时 − 北京标准时间）
    eot_minutes: float              # 均时差
    warnings: list = field(default_factory=list)

    @property
    def corrected(self) -> bool:
        return self.longitude is not None

    @property
    def total_minutes(self) -> float:
        return self.longitude_minutes + self.eot_minutes if self.corrected else 0.0

    @property
    def local_mean(self) -> datetime | None:
        return self.standard + timedelta(minutes=self.longitude_minutes) if self.corrected else None

    @property
    def true_solar(self) -> datetime | None:
        return self.standard + timedelta(minutes=self.total_minutes) if self.corrected else None

    @property
    def chart_time(self) -> datetime:
        """日柱、时柱所用的时间：真太阳时；未提供出生地时为北京标准时间。"""
        return self.true_solar if self.corrected else self.standard

    def to_chart(self, standard_dt: datetime) -> datetime:
        return standard_dt + timedelta(minutes=self.total_minutes)

    def to_standard(self, chart_dt: datetime) -> datetime:
        return chart_dt - timedelta(minutes=self.total_minutes)


def resolve_birth_time(clock_text: str, location: str | None = None, longitude: float | None = None,
                       dst: str | None = None) -> BirthTime:
    clock = parse_clock(clock_text)
    warnings = []

    status = dst_status(clock)
    if status == 'none':
        standard = clock
        dst_note = '不涉及夏令时'
        if dst:
            warnings.append(f'该时间不在 1986–1991 夏令时期间，--dst {dst} 已忽略')
    else:
        if dst not in ('clock', 'standard'):
            hint = {
                'in_dst': '落在中国夏令时期间（1986–1991）',
                'disputed': '落在 1988 年夏令时开始日期有分歧的一周内（中文资料 4 月 10 日 / IANA 4 月 17 日）',
                'ambiguous': '落在夏令时结束日重复出现的一小时内',
                'nonexistent': '落在夏令时开始日被跳过的一小时内（该钟面时间不存在）',
            }[status]
            raise InputError(
                f'出生时间 {clock:%Y-%m-%d %H:%M} {hint}，无法判断记录的是夏令时钟面还是标准时间。'
                '请确认后加参数：--dst clock（记录的是当时钟表时间，脚本会减 1 小时）'
                '或 --dst standard（记录的已经是标准北京时间）。')
        if status == 'nonexistent' and dst == 'clock':
            raise InputError(f'{clock:%Y-%m-%d %H:%M} 在夏令时开始日的钟面上不存在，请核对出生时间。')
        if dst == 'clock':
            standard = clock - timedelta(hours=1)
            dst_note = '按夏令时钟面处理，已减 1 小时换算为北京标准时间'
        else:
            standard = clock
            dst_note = '按用户声明：输入已是北京标准时间（未做夏令时换算）'

    if longitude is not None:
        if not isinstance(longitude, (int, float)) or not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise InputError(f'经度不合法：{longitude}（应为 -180 ~ 180 之间的有限数值，东经为正）')
        lng = float(longitude)
        label = f'{location}（经度 {lng}°E，手动指定）' if location else f'经度 {lng}°E'
    elif location:
        if location not in CITY_LONGITUDE:
            raise InputError(
                f'出生地「{location}」不在内置经度表中，不能静默跳过经度校正。'
                '请查询经度后用 --longitude 传入（县级可用所在地级市经度，误差通常 < 2 分钟）；'
                '若确实无法获得经度，去掉 -l，按北京标准时间排盘（不做真太阳时校正）。')
        lng = CITY_LONGITUDE[location]
        label = f'{location}（经度 {lng}°E，内置表）'
    else:
        lng = None
        label = '未提供（按北京标准时间排盘，不做真太阳时校正）'

    if lng is not None and not CHINA_LONGITUDE_RANGE[0] <= lng <= CHINA_LONGITUDE_RANGE[1]:
        warnings.append(f'经度 {lng}° 超出中国范围：输入时间必须已换算为北京时间（UTC+8），否则排盘无效')

    lng_min = (lng - 120.0) * 4 if lng is not None else 0.0
    eot = equation_of_time_minutes(standard.date()) if lng is not None else 0.0
    return BirthTime(clock=clock, standard=standard, dst_note=dst_note, longitude=lng,
                     location_label=label, longitude_minutes=lng_min, eot_minutes=eot, warnings=warnings)


# ============ lunar_python 封装 ============
def solar_of(dt: datetime):
    return Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def dt_of(solar) -> datetime:
    return datetime(solar.getYear(), solar.getMonth(), solar.getDay(),
                    solar.getHour(), solar.getMinute(), solar.getSecond())


def year_month_pillars(standard_dt: datetime) -> tuple[str, str]:
    """年柱、月柱：北京标准时刻与节气时刻比较（lunar_python 的节气时刻为北京时间）。"""
    ec = solar_of(standard_dt).getLunar().getEightChar()
    return ec.getYear(), ec.getMonth()


def day_pillar(d: date) -> str:
    """某公历日的日柱（取当日正午，避开晚子时流派设置）。"""
    return Solar.fromYmdHms(d.year, d.month, d.day, 12, 0, 0).getLunar().getEightChar().getDay()


def hour_branch(hour: int) -> str:
    return ZHI12[((hour + 1) // 2) % 12]


def hour_pillar(day_gan: str, branch: str) -> str:
    """五鼠遁起时干。晚子时按当天日干起子时（本 skill 约定）。"""
    zi = GAN10.index(WUSHUDUN[day_gan])
    return GAN10[(zi + ZHI12.index(branch)) % 10] + branch


def day_hour_pillars(chart_dt: datetime) -> tuple[str, str]:
    """日柱、时柱：00:00 换日；23:00–23:59 晚子时日柱不换日，时柱按当天日干起子时。"""
    dp = day_pillar(chart_dt.date())
    return dp, hour_pillar(dp[0], hour_branch(chart_dt.hour))


def lichun(year: int) -> datetime:
    return dt_of(Solar.fromYmd(year, 3, 1).getLunar().getJieQiTable()['立春'])


def liunian_year_of(dt: datetime) -> int:
    """流年年份口径：以立春精确时刻分界。"""
    return dt.year if dt >= lichun(dt.year) else dt.year - 1


def year_ganzhi(year: int) -> str:
    """流年年份 → 干支（公元 4 年为甲子；该年份指立春到次年立春）。"""
    return JIAZI[(year - 4) % 60]


def jie_of_liunian(year: int) -> list[tuple[str, datetime]]:
    """流年 year 的 12 个节（立春…小寒）加次年立春，共 13 项，均为北京时间精确时刻。"""
    cur = lichun(year)
    out = [('立春', cur)]
    for _ in range(12):
        nxt = solar_of(cur + timedelta(minutes=1)).getLunar().getNextJie()
        cur = dt_of(nxt.getSolar())
        out.append((nxt.getName(), cur))
    return out


def jie_between(start_std: datetime, end_std: datetime) -> list[tuple[str, datetime]]:
    out = []
    for y in range(liunian_year_of(start_std), liunian_year_of(end_std) + 1):
        for name, t in jie_of_liunian(y)[:12]:
            if start_std < t < end_std:
                out.append((name, t))
    return out


# ============ 起盘 ============
@dataclass
class DaYun:
    index: int                      # 1 起
    gz: str
    start: datetime                 # 北京标准时间，左闭
    end: datetime                   # 右开（下一步交运时刻）
    start_age: tuple                # (年, 月, 日) 交运时的实际年龄

    def contains(self, dt: datetime) -> bool:
        return self.start <= dt < self.end


@dataclass
class Chart:
    birth: BirthTime
    gender: str
    year_gz: str
    month_gz: str
    day_gz: str
    time_gz: str
    direction: str
    yun_start: datetime
    yun_offset: tuple               # (年, 月, 日, 时) lunar_python 起运差
    dayun: list

    @property
    def is_male(self) -> bool:
        return self.gender == '男'

    @property
    def pillars(self) -> list:
        return [self.year_gz, self.month_gz, self.day_gz, self.time_gz]

    @property
    def is_late_zi(self) -> bool:
        return self.birth.chart_time.hour == 23

    def ss(self, gan: str) -> str:
        return SST_TABLE[self.day_gz[0]].get(gan, '?')

    def dayun_at(self, dt: datetime):
        return next((d for d in self.dayun if d.contains(dt)), None)


def build_chart(birth: BirthTime, gender: str, n_dayun: int = 9) -> Chart:
    if gender not in ('男', '女'):
        raise InputError('性别只能是 男 或 女')
    year_gz, month_gz = year_month_pillars(birth.standard)
    day_gz, time_gz = day_hour_pillars(birth.chart_time)

    ec = solar_of(birth.standard).getLunar().getEightChar()
    is_male = gender == '男'
    yun = ec.getYun(1 if is_male else 0)
    start_solar = yun.getStartSolar()
    offset = (yun.getStartYear(), yun.getStartMonth(), yun.getStartDay(), yun.getStartHour())
    direction = '顺行' if yun.isForward() else '逆行'

    names = [d.getGanZhi() for d in yun.getDaYun(n_dayun + 1)[1:]]
    dayun = []
    for i, gz in enumerate(names):
        start = dt_of(start_solar.nextYear(10 * i))
        end = dt_of(start_solar.nextYear(10 * (i + 1)))
        dayun.append(DaYun(index=i + 1, gz=gz, start=start, end=end,
                           start_age=(offset[0] + 10 * i, offset[1], offset[2])))
    return Chart(birth=birth, gender=gender, year_gz=year_gz, month_gz=month_gz, day_gz=day_gz,
                 time_gz=time_gz, direction=direction, yun_start=dt_of(start_solar),
                 yun_offset=offset, dayun=dayun)


def age_between(birth: datetime, when: datetime) -> tuple[int, int]:
    """实际年龄（年, 月）。"""
    months = (when.year - birth.year) * 12 + (when.month - birth.month)
    if (when.day, when.hour, when.minute) < (birth.day, birth.hour, birth.minute):
        months -= 1
    return months // 12, months % 12


def span_years_months(a: datetime, b: datetime) -> tuple[int, int]:
    return age_between(a, b)


def nominal_age(birth_std: datetime, when: datetime) -> int:
    """虚岁：按农历年（春节）计。"""
    return solar_of(when).getLunar().getYear() - solar_of(birth_std).getLunar().getYear() + 1


# ============ 关系查表（结构化）============
# 类型常量——评分和信号只看类型，展示文字另行生成
GAN_HE, GAN_KE, GAN_FUYIN = 'GAN_HE', 'GAN_KE', 'GAN_FUYIN'
LIUHE, CHONG, HAI, PO, XING, ZIXING, FUYIN, BANHE, GONG = (
    'LIUHE', 'CHONG', 'HAI', 'PO', 'XING', 'ZIXING', 'FUYIN', 'BANHE', 'GONG')
SANHE, SANHUI, SANXING = 'SANHE', 'SANHUI', 'SANXING'

REL_LABEL = {
    GAN_HE: '合', GAN_KE: '剋', GAN_FUYIN: '伏吟',
    LIUHE: '合', CHONG: '冲', HAI: '害', PO: '破', XING: '刑', ZIXING: '自刑', FUYIN: '伏吟',
    BANHE: '半合', GONG: '拱', SANHE: '三合', SANHUI: '三会', SANXING: '三刑',
}

# 本版本支持的关系清单（其余如天干相冲、半刑、暗合不输出）
SUPPORTED_RELATIONS = ('天干：五合、剋（带方向）、伏吟；地支两两：六合、六冲、六害、六破、子卯刑、自刑（辰午酉亥）、'
                       '伏吟、半合（含中神）、拱（三合两端）；地支多支：三合局、三会方、三刑（寅巳申、丑戌未）')

_GAN_HE_TABLE = {frozenset('甲己'): '土', frozenset('乙庚'): '金', frozenset('丙辛'): '水',
                 frozenset('丁壬'): '木', frozenset('戊癸'): '火'}
_KE_WX = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}     # 我剋
SHENG_WX = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}   # 我生（日主 → 食伤五行）
GAN_KE_MAP = {g: {h for h in GAN10 if _KE_WX[WX_MAP[g]] == WX_MAP[h]} for g in GAN10}

_LIUHE_TABLE = {frozenset('子丑'): '土', frozenset('寅亥'): '木', frozenset('卯戌'): '火',
                frozenset('辰酉'): '金', frozenset('巳申'): '水', frozenset('午未'): None}  # 午未化土/化火有分歧
_CHONG_SET = {frozenset(p) for p in ('子午', '丑未', '寅申', '卯酉', '辰戌', '巳亥')}
_HAI_SET = {frozenset(p) for p in ('子未', '丑午', '寅巳', '卯辰', '申亥', '酉戌')}
_PO_SET = {frozenset(p) for p in ('子酉', '午卯', '巳申', '寅亥', '辰丑', '戌未')}
_XING_PAIR_SET = {frozenset('子卯')}
_ZIXING_SET = set('辰午酉亥')
SANHE_GROUPS = [('申子辰', '水', '子'), ('亥卯未', '木', '卯'), ('寅午戌', '火', '午'), ('巳酉丑', '金', '酉')]
SANHUI_GROUPS = [('寅卯辰', '木'), ('巳午未', '火'), ('申酉戌', '金'), ('亥子丑', '水')]
SANXING_GROUPS = ['寅巳申', '丑戌未']

# "动"类关系的显式归并规则（评分、信号用；破不计入，保持原规则口径）
MOVE_TYPES = {CHONG, LIUHE, XING, ZIXING, HAI, FUYIN}
TOUCH_TYPES = {LIUHE, CHONG, HAI, XING, ZIXING, FUYIN, BANHE, GONG}


@dataclass(frozen=True)
class Member:
    pos: str        # 年柱/月柱/日柱/时柱/大运/流年/流月
    kind: str       # 干 / 支
    char: str


@dataclass(frozen=True)
class Relation:
    type: str
    members: tuple      # GAN_KE：members[0] 剋 members[1]
    element: str | None = None

    @property
    def positions(self) -> set:
        return {m.pos for m in self.members}


def gan_pair_relations(a: Member, b: Member) -> list:
    out = []
    if a.char == b.char:
        return [Relation(GAN_FUYIN, (a, b))]
    pair = frozenset((a.char, b.char))
    if pair in _GAN_HE_TABLE:
        out.append(Relation(GAN_HE, (a, b), _GAN_HE_TABLE[pair]))
    if b.char in GAN_KE_MAP[a.char]:
        out.append(Relation(GAN_KE, (a, b)))
    if a.char in GAN_KE_MAP[b.char]:
        out.append(Relation(GAN_KE, (b, a)))
    return out


def zhi_pair_relations(a: Member, b: Member) -> list:
    if a.char == b.char:
        return [Relation(ZIXING if a.char in _ZIXING_SET else FUYIN, (a, b))]
    pair = frozenset((a.char, b.char))
    out = []
    if pair in _CHONG_SET:
        out.append(Relation(CHONG, (a, b)))
    if pair in _LIUHE_TABLE:
        out.append(Relation(LIUHE, (a, b), _LIUHE_TABLE[pair]))
    if pair in _HAI_SET:
        out.append(Relation(HAI, (a, b)))
    if pair in _PO_SET:
        out.append(Relation(PO, (a, b)))
    if pair in _XING_PAIR_SET:
        out.append(Relation(XING, (a, b)))
    for chars, wx, center in SANHE_GROUPS:
        if pair <= set(chars):
            out.append(Relation(BANHE if center in pair else GONG, (a, b), wx))
            break
    return out


def zhi_types(z1: str, z2: str) -> set:
    return {r.type for r in zhi_pair_relations(Member('', '支', z1), Member('', '支', z2))}


def branch_structures(members: list, required: set | None = None) -> list:
    """三合、三会、三刑。required 给定时只返回"必须有这些位置参与才成立"的结构（新触发），
    原局或既有背景已完整存在的结构不重复报告。"""
    groups = ([(SANHE, chars, wx) for chars, wx, _ in SANHE_GROUPS]
              + [(SANHUI, chars, wx) for chars, wx in SANHUI_GROUPS]
              + [(SANXING, chars, None) for chars in SANXING_GROUPS])
    out = []
    for rtype, chars, wx in groups:
        involved = tuple(m for m in members if m.kind == '支' and m.char in chars)
        if {m.char for m in involved} != set(chars):
            continue
        if required:
            base = {m.char for m in involved if m.pos not in required}
            if base == set(chars):
                continue
        out.append(Relation(rtype, involved, wx))
    return out


def relation_text(rel: Relation, anchor: set | None = None) -> str:
    """展示文字。anchor：外来位置（流年/大运/流月），两两关系以"原局位置+干/支:"作前缀。"""
    if rel.type in (SANHE, SANHUI, SANXING):
        present = {m.char for m in rel.members}
        chars = next(c for c in [g[0] for g in SANHE_GROUPS] + [g[0] for g in SANHUI_GROUPS] + SANXING_GROUPS
                     if set(c) == present)
        name = {SANHE: f'三合{rel.element}局', SANHUI: f'三会{rel.element}方', SANXING: '三刑'}[rel.type]
        parts = '+'.join(f'{m.pos}{m.char}' for m in rel.members)
        return f'{chars}{name}({parts})'
    a, b = rel.members
    if rel.type == GAN_KE:
        core = f'{a.char}剋{b.char}'
    else:
        core = f'{a.char}{b.char}{REL_LABEL[rel.type]}'
        if rel.element and rel.type in (GAN_HE, LIUHE, BANHE, GONG):
            core += f'({rel.element})'
    if anchor:
        others = [m for m in rel.members if m.pos not in anchor]
        if len(others) == 1:
            return f'{others[0].pos}{others[0].kind}:{core}'
    return f'{a.pos}{a.kind}-{b.pos}{b.kind}:{core}'


def yuanju_members(chart: Chart) -> list:
    out = []
    for pos, gz in zip(PILLAR_POS, chart.pillars):
        out += [Member(pos, '干', gz[0]), Member(pos, '支', gz[1])]
    return out


def ext_members(pos: str, gz: str) -> list:
    return [Member(pos, '干', gz[0]), Member(pos, '支', gz[1])]


def pair_relations(a: Member, b: Member) -> list:
    if a.kind != b.kind:
        return []
    return gan_pair_relations(a, b) if a.kind == '干' else zhi_pair_relations(a, b)


def internal_relations(chart: Chart) -> list:
    """原局内部：四柱两两（含不相邻）+ 原局已成的多支结构。"""
    ms = yuanju_members(chart)
    out = []
    for a, b in combinations(ms, 2):
        if a.pos != b.pos:
            out += pair_relations(a, b)
    return out + branch_structures(ms)


def external_relations(new: list, context: list) -> list:
    """新进来的干支（大运/流年/流月）与背景（原局及已在场的岁运）之间的两两关系，以及需要新干支参与才成立的多支结构。"""
    out = []
    for n in new:
        for c in context:
            out += pair_relations(n, c)
    required = {m.pos for m in new}
    return out + branch_structures(context + new, required)


# ============ 传统规则信号（结构化）============
@dataclass(frozen=True)
class Level:
    key: str
    emoji: str
    name: str
    legend: str


LEVELS = {
    'S': Level('S', '🔥', 'S级 外触型', '外部能量场对原局形成压力：男命比劫剋财+财弱+夫妻宫动；女命伤官见官或夫星被合走+夫妻宫被冲。主体感受是"事情找上门来"'),
    'P': Level('P', '✨', 'P级 内驱型', '非 S 级年份中，以下三条任两条成立（流年七杀叠大运七杀时排除）：①内部能量激活（原局多重伏吟/三现伏吟/自刑动）②食伤透干 ③食伤被六合或三合拱合引动。主体感受是"我想这么干"'),
    'S_REVIEW': Level('S_REVIEW', '⚠️', 'S复核', '官杀透干（七杀重/正官轻），附原局或大运有无食伤制、印化的粗判'),
    'SUIYUN': Level('SUIYUN', '⚡', '岁运并临', '流年干支=大运干支。B+ 单纯并临 / A 原局有同字 / A+ 整柱三叠（日柱三叠必须人工复核）'),
    'P_CAI': Level('P_CAI', '💰', 'P-财事', '财星透干独立标签（不进 P 级判定）'),
    'A': Level('A', '🔴', 'A级 单项强触动', '配偶星或夫妻宫被冲克，结构未完整闭环'),
    'B': Level('B', '🟠', 'B级 有动象', '动象存在，但未形成完整结构'),
    'C': Level('C', '🟡', 'C级 辅助', '可辅助解释，不单独定性'),
    'D': Level('D', '🔵', 'D级 背景', '只作参考'),
}
LEVEL_ORDER = ['S', 'P', 'S_REVIEW', 'SUIYUN', 'P_CAI', 'A', 'B', 'C', 'D']


@dataclass(frozen=True)
class Signal:
    level: str
    code: str
    text: str

    def display(self) -> str:
        return LEVELS[self.level].emoji + self.text


def detect_key_signals(chart: Chart, yt_gan: str, yt_zhi: str, yun_gan: str, yun_zhi: str) -> list:
    """流年关键信号（传统规则启发式，阈值未经统计标定）。"""
    ss = chart.ss
    is_male = chart.is_male
    signals = []
    add = lambda level, code, text: signals.append(Signal(level, code, text))
    yuan_ju = [(pos, gz[0], gz[1]) for pos, gz in zip(PILLAR_POS, chart.pillars)]
    day_zhi = chart.day_gz[1]
    yt_shishen = ss(yt_gan)
    bijie_set = ('比肩', '劫财')
    cai_set = ('正财', '偏财')
    guansha_set = ('正官', '七杀')
    shishang_set = ('伤官', '食神')
    yin_set = ('正印', '偏印')
    he = lambda g1, g2: frozenset((g1, g2)) in _GAN_HE_TABLE
    types = zhi_types

    # 原局比劫总权重（明字 1.0, 本气 0.75, 中气 0.4, 余气 0.15）
    bijie_score = sum(1.0 for g in (chart.year_gz[0], chart.month_gz[0], chart.time_gz[0]) if ss(g) in bijie_set)
    for _, _, zhi in yuan_ju:
        for i, cg in enumerate(ZHI_CANGGAN.get(zhi, [])):
            if ss(cg) in bijie_set:
                bijie_score += [0.75, 0.4, 0.15][i]

    cai_in_yuanju, guansha_in_yuanju = [], []
    for pos, gan, zhi in yuan_ju:
        if ss(gan) in cai_set:
            cai_in_yuanju.append((pos, gan, '透干'))
        if ss(gan) in guansha_set:
            guansha_in_yuanju.append((pos, gan, '透干'))
        for i, cg in enumerate(ZHI_CANGGAN.get(zhi, [])):
            qi = ['本气', '中气', '余气'][i]
            if ss(cg) in cai_set:
                cai_in_yuanju.append((pos, cg, f'{zhi}藏-{qi}'))
            if ss(cg) in guansha_set:
                guansha_in_yuanju.append((pos, cg, f'{zhi}藏-{qi}'))
    cai_strong = any(s == '透干' for *_, s in cai_in_yuanju) and any('本气' in s for *_, s in cai_in_yuanju)
    guansha_strong = (any(s == '透干' for *_, s in guansha_in_yuanju)
                      and any('本气' in s for *_, s in guansha_in_yuanju))

    if is_male:
        bijie_active, source = False, []
        if yt_shishen in bijie_set:
            bijie_active = True
            source.append(f'天干{yt_gan}透')
        cg = ZHI_CANGGAN.get(yt_zhi, [])
        if cg and ss(cg[0]) in bijie_set:
            bijie_active = True
            source.append(f'{yt_zhi}本气{cg[0]}')
        elif len(cg) >= 2 and ss(cg[1]) in bijie_set:
            touched = any(types(yt_zhi, z) & TOUCH_TYPES for *_, z in yuan_ju)
            if touched and bijie_score >= 2.5:
                bijie_active = True
                source.append(f'{yt_zhi}中气{cg[1]}(触发)')
        if bijie_active and cai_in_yuanju:
            day_touched = bool(types(yt_zhi, day_zhi) & {CHONG, HAI, FUYIN, ZIXING})
            if not cai_strong and day_touched:
                add('S', 'BIJIE_KE_CAI_S', f'比劫剋财+财弱+夫妻宫动({",".join(source)})')
            elif not cai_strong:
                add('A', 'BIJIE_KE_CAI', f'比劫剋财(财星弱,{",".join(source)})')
            else:
                add('B', 'BIJIE_ACTIVE', f'比劫透/动(财星有根可承受,{",".join(source)})')
        elif bijie_active:
            add('C', 'BIJIE_NO_CAI', '比劫动(原局无财星,主竞争耗财)')
        for pos, cai_gan, _ in cai_in_yuanju:
            if he(yt_gan, cai_gan):
                add('B', 'CAI_HE', f'财星{cai_gan}被流年合({pos})')
                break
        if yt_shishen in cai_set:
            add('C', 'CAI_TOU', '财星透干(妻星显)')
    else:
        if yt_shishen == '伤官':
            attacked = [(pos, gan) for pos, gan, _ in yuan_ju if ss(gan) == '正官' and gan in GAN_KE_MAP[yt_gan]]
            if ss(yun_gan) == '正官' and yun_gan in GAN_KE_MAP[yt_gan]:
                attacked.append(('大运', yun_gan))
            if attacked:
                targets = ','.join(f'{p}{g}' for p, g in attacked)
                if CHONG in types(yt_zhi, day_zhi):
                    add('S', 'SHANGGUAN_JIANGUAN_S', f'伤官见官+夫妻宫被冲({targets})')
                else:
                    add('A', 'SHANGGUAN_JIANGUAN', f'伤官见官({targets})')
        elif yt_shishen == '食神':
            if any(ss(g) == '七杀' for _, g, _ in yuan_ju) or ss(yun_gan) == '七杀':
                add('C', 'SHISHEN_ZHISHA', '食神制杀(需看七杀是用是忌)')
        for pos, gs_gan, source in guansha_in_yuanju:
            if source == '透干' and he(yt_gan, gs_gan):
                if CHONG in types(yt_zhi, day_zhi):
                    add('S', 'FUXING_HE_S', f'夫星{gs_gan}被合走+夫妻宫被冲({pos})')
                else:
                    add('A', 'FUXING_HE', f'夫星{gs_gan}被流年合走({pos})')
                break
        if yt_shishen in guansha_set:
            add('C', 'GUANSHA_TOU', '官杀透干(夫星显)')

    day_rel = types(yt_zhi, day_zhi)
    if CHONG in day_rel:
        if is_male and cai_in_yuanju and not cai_strong:
            add('A', 'CHONG_DAY_WEAK', f'流年冲日支+财星弱({yt_zhi}{day_zhi}冲)')
        elif not is_male and guansha_in_yuanju and not guansha_strong:
            add('A', 'CHONG_DAY_WEAK', f'流年冲日支+夫星弱({yt_zhi}{day_zhi}冲)')
        else:
            add('B', 'CHONG_DAY', f'流年冲日支({yt_zhi}{day_zhi}冲)')
    if yt_zhi == day_zhi:
        add('B', 'DAY_FUYIN', '日支伏吟(夫妻宫应期,吉凶看喜忌)')
    if LIUHE in day_rel:
        add('C', 'HE_DAY', f'合日支({yt_zhi}{day_zhi}合,关系活跃)')

    # 三刑动日支：只报告需要流年参与才成立的三刑（原局固有三刑不逐年重复）
    ms = [Member(pos, '支', zhi) for pos, _, zhi in yuan_ju] + [Member('流年', '支', yt_zhi)]
    for st in branch_structures(ms, {'流年'}):
        if st.type == SANXING and any(m.pos == '日柱' for m in st.members):
            add('B', 'SANXING_DAY', f'三刑动日支({relation_text(st)})')

    qisha = [(pos, gan) for pos, gan, _ in yuan_ju if ss(gan) == '七杀']
    if ss(yun_gan) == '七杀':
        qisha.append(('大运', yun_gan))
    for pos, qs_gan in qisha:
        if he(yt_gan, qs_gan):
            if is_male:
                add('C', 'QISHA_HE', f'七杀被合({pos}{qs_gan},约束力变化,需看用忌)')
            else:
                add('B', 'QISHA_HE', f'夫星七杀被合({pos}{qs_gan})')
            break

    if he(yt_gan, yun_gan):
        yun_ss = ss(yun_gan)
        if yun_ss in cai_set or yun_ss in guansha_set:
            add('B', 'HE_YUN_GAN', f'流年合大运{yun_gan}(大运为{yun_ss})')
        else:
            add('C', 'HE_YUN_GAN', f'流年合大运{yun_gan}')

    # 流年剋大运干：流年干剋大运干（方向：流年 → 大运）
    if yun_gan in GAN_KE_MAP[yt_gan]:
        add('D', 'KE_YUN_GAN', f'流年剋大运干({yt_gan}剋{yun_gan})')

    # P 级（非 S 级时判定）
    if not any(s.level == 'S' for s in signals):
        cond = []
        zhi_list = [z for *_, z in yuan_ju]
        gan_list = [g for _, g, _ in yuan_ju]
        same_zhi, same_gan = zhi_list.count(yt_zhi), gan_list.count(yt_gan)
        if same_zhi >= 2:
            cond.append(f'多重伏吟({yt_zhi}地支原局{same_zhi}现+流年={same_zhi + 1}现)')
        elif same_gan >= 2:
            cond.append(f'多重伏吟({yt_gan}天干原局{same_gan}现+流年={same_gan + 1}现)')
        elif yun_zhi == yt_zhi and same_zhi >= 1:
            cond.append(f'三现伏吟({yt_zhi}地支:原局+大运+流年)')
        elif yun_gan == yt_gan and same_gan >= 1:
            cond.append(f'三现伏吟({yt_gan}天干:原局+大运+流年)')
        elif yt_zhi in _ZIXING_SET and same_zhi >= 1:
            cond.append(f'自刑动({yt_zhi}{yt_zhi})')
        if yt_shishen in shishang_set:
            cond.append(f'食伤透干({yt_gan})')
        triggered = False
        for pos, gan, zhi in yuan_ju:
            has_ss = ss(gan) in shishang_set or (ZHI_CANGGAN.get(zhi) and ss(ZHI_CANGGAN[zhi][0]) in shishang_set)
            if has_ss and LIUHE in types(yt_zhi, zhi):
                cond.append(f'食伤被六合引动({pos}支{zhi}-{yt_zhi}合)')
                triggered = True
                break
        if not triggered:
            shang_wx = SHENG_WX[WX_MAP[chart.day_gz[0]]]
            for chars, wx, center in SANHE_GROUPS:
                if wx != shang_wx:
                    continue
                o1, o2 = [c for c in chars if c != center]
                other = o2 if yt_zhi == o1 else (o1 if yt_zhi == o2 else None)
                if other:
                    match = next(((pos, zhi) for pos, _, zhi in yuan_ju if zhi == other), None)
                    if match:
                        cond.append(f'食伤被拱合引动({match[0]}支{match[1]}-{yt_zhi}拱{wx})')
        excluded = yt_shishen == '七杀' and ss(yun_gan) == '七杀'
        if len(cond) >= 2 and not excluded:
            add('P', 'P_LEVEL', f'P级内驱型({"+".join(cond)})')

    if yt_shishen in cai_set:
        add('P_CAI', 'P_CAI', f'P-财事({yt_shishen}{yt_gan}透干,"用"显化)')

    if yt_shishen in guansha_set:
        gans = [g for _, g, _ in yuan_ju]
        zhis = [z for *_, z in yuan_ju]
        has_food = (any(ss(g) in shishang_set for g in gans) or ss(yun_gan) in shishang_set
                    or any(ss(ZHI_CANGGAN[z][0]) in shishang_set for z in zhis))
        has_yin = (any(ss(g) in yin_set for g in gans) or ss(yun_gan) in yin_set
                   or any(ss(ZHI_CANGGAN[z][0]) in yin_set for z in zhis))
        heaviness = '重' if yt_shishen == '七杀' else '轻'
        if has_food or has_yin:
            note = '/'.join(x for x, ok in (('食伤制', has_food), ('印化', has_yin)) if ok)
            add('S_REVIEW', 'S_REVIEW', f'S复核-{heaviness}({yt_shishen}{yt_gan}透+有{note},盲派粗判)')
        else:
            add('S_REVIEW', 'S_REVIEW', f'S复核-{heaviness}!!({yt_shishen}{yt_gan}透+无制无化,需人工身能任杀判定)')

    if yt_gan == yun_gan and yt_zhi == yun_zhi:
        gans = [g for _, g, _ in yuan_ju]
        zhis = [z for *_, z in yuan_ju]
        full = next((PILLAR_POS[i] for i in range(4) if gans[i] == yt_gan and zhis[i] == yt_zhi), None)
        if full == '日柱':
            add('SUIYUN', 'SUIYUN', f'岁运并临-A+({yt_gan}{yt_zhi}日柱三叠,自身/婚姻宫/身体应期,必须人工复核)')
        elif full:
            add('SUIYUN', 'SUIYUN', f'岁运并临-A+({yt_gan}{yt_zhi}整柱三叠于{full})')
        elif zhis.count(yt_zhi) or gans.count(yt_gan):
            parts = []
            if gans.count(yt_gan):
                parts.append(f'{yt_gan}天干{gans.count(yt_gan)}现')
            if zhis.count(yt_zhi):
                parts.append(f'{yt_zhi}地支{zhis.count(yt_zhi)}现')
            add('SUIYUN', 'SUIYUN', f'岁运并临-A({yt_gan}{yt_zhi}+原局[{",".join(parts)}])')
        else:
            add('SUIYUN', 'SUIYUN', f'岁运并临-B+({yt_gan}{yt_zhi}+原局无同字)')
    return signals


# ============ 流年表（按立春分界，交运年分段）============
@dataclass
class YearSegment:
    dayun: DaYun | None
    start: datetime
    end: datetime


@dataclass
class YearRow:
    year: int
    gz: str
    window: tuple
    segments: list
    interactions: list          # [(tag, Relation)]
    signals: list               # [(tag, Signal)]  tag: '' / '交运前' / '交运后'

    @property
    def switch(self) -> DaYun | None:
        starts = [s.dayun for s in self.segments[1:] if s.dayun]
        return starts[0] if starts else None

    def levels(self) -> set:
        return {s.level for _, s in self.signals}


def _struct_key(rel: Relation) -> tuple:
    return rel.type, frozenset(m.char for m in rel.members)


def year_segments(chart: Chart, year: int) -> list:
    start, end = lichun(year), lichun(year + 1)
    cuts = sorted({start, end} | {d.start for d in chart.dayun if start < d.start < end})
    return [YearSegment(chart.dayun_at(a), a, b) for a, b in zip(cuts, cuts[1:])]


def build_year_row(chart: Chart, year: int) -> YearRow:
    gz = year_ganzhi(year)
    segs = year_segments(chart, year)
    base = yuanju_members(chart)
    ln = ext_members('流年', gz)
    interactions = [('', r) for r in external_relations(ln, base)]
    yuanju_struct_keys = {_struct_key(r) for _, r in interactions if r.type in (SANHE, SANHUI, SANXING)}
    multi = len(segs) > 1
    sig_sets = []
    for seg in segs:
        if not seg.dayun:
            sig_sets.append(None)
            continue
        tag = seg.dayun.gz if multi else ''
        yun_ms = ext_members('大运', seg.dayun.gz)
        for n in ln:
            for c in yun_ms:
                for r in pair_relations(n, c):
                    interactions.append((tag, r))
        # 需要流年、且有大运参与才成立的多支结构（原局+流年已成立的不重复）
        for st in branch_structures(base + yun_ms + [ln[1]], {'流年'}):
            if any(m.pos == '大运' for m in st.members) and _struct_key(st) not in yuanju_struct_keys:
                interactions.append((tag, st))
        sig_sets.append(detect_key_signals(chart, gz[0], gz[1], seg.dayun.gz[0], seg.dayun.gz[1]))
    signals = []
    valid = [s for s in sig_sets if s is not None]
    if len(segs) == 1 or len(valid) <= 1:
        tag = '' if len(segs) == 1 or len(valid) == len(segs) else '起运后'
        for s in (valid[0] if valid else []):
            signals.append((tag, s))
    else:
        first, second = valid[0], valid[-1]
        for s in first:
            signals.append(('' if s in second else '交运前', s))
        for s in second:
            if s not in first:
                signals.append(('交运后', s))
    # 同一结构在两段都出现时去重
    seen, dedup = set(), []
    for tag, r in interactions:
        key = (tag, r)
        if key not in seen:
            seen.add(key)
            dedup.append((tag, r))
    return YearRow(year=year, gz=gz, window=(segs[0].start, segs[-1].end), segments=segs,
                   interactions=dedup, signals=signals)


def build_year_table(chart: Chart, until_age: int = 80) -> list:
    first = liunian_year_of(chart.yun_start)
    last = chart.birth.standard.year + until_age
    return [build_year_row(chart, y) for y in range(first, last + 1)]


# ============ 流月表（节气月）============
@dataclass
class MonthRow:
    name: str
    jie: str
    gz: str
    start: datetime
    end: datetime
    dayun: DaYun | None
    switch: DaYun | None
    interactions: list


def build_month_table(chart: Chart, year: int) -> list:
    jies = jie_of_liunian(year)
    ln = ext_members('流年', year_ganzhi(year))
    base = yuanju_members(chart)
    rows = []
    for (name, start), (_, end) in zip(jies[:12], jies[1:]):
        gz = year_month_pillars(start + timedelta(minutes=1))[1]
        dy = chart.dayun_at(start)
        switch = next((d for d in chart.dayun if start < d.start < end), None)
        context = base + ln + (ext_members('大运', dy.gz) if dy else [])
        rels = external_relations(ext_members('流月', gz), context)
        rows.append(MonthRow(name=f'{gz[1]}月', jie=name, gz=gz, start=start, end=end, dayun=dy,
                             switch=switch, interactions=rels))
    return rows


# ============ 时辰反推（--verify-events）============
SUBJECT_ALIASES = {
    'child': ['子女', '孩子', '儿子', '女儿', '小孩'],
    'parent': ['父母', '父亲', '母亲', '爸爸', '妈妈', '爸', '妈', '长辈', '爷爷', '奶奶', '外公', '外婆'],
    'spouse': ['配偶', '老公', '老婆', '丈夫', '妻子', '先生', '太太', '对象'],
    'self': ['本人', '自己', '命主', '我'],
}
SUBJECT_NAMES = {'self': '本人', 'child': '子女', 'parent': '父母/长辈', 'spouse': '配偶'}
CATEGORY_ALIASES = {
    'birth': ['生子', '生孩子', '生了', '怀孕', '生育', '产子', '添丁', '出生', '生娃'],
    'marriage': ['结婚', '离婚', '恋爱', '分手', '婚恋', '婚姻', '婚', '感情', '订婚'],
    'career': ['事业', '工作', '升职', '升迁', '跳槽', '换工作', '创业', '职', '失业'],
    'wealth': ['财', '钱', '破财', '进财', '投资', '收入', '生意', '亏'],
    'study': ['学业', '升学', '考试', '读书', '考证', '毕业', '学历', '上学', '高考', '中考'],
    'health': ['健康', '病', '手术', '住院', '身体', '受伤', '车祸', '意外'],
    'move': ['搬', '迁居', '搬迁', '移居', '换城市', '移民', '远行', '出国', '调动'],
    'family': ['家庭', '家里', '家变'],
}
CATEGORY_NAMES = {'birth': '生育', 'marriage': '婚恋', 'career': '事业', 'wealth': '财', 'study': '学业',
                  'health': '健康', 'move': '搬迁', 'family': '家庭'}
DOMAIN_NAMES = {'marriage': '婚恋', 'career': '事业', 'wealth': '财', 'study': '学业', 'health': '健康',
                'move': '搬迁', 'children': '子女', 'family': '家庭'}
UNSUPPORTED_EVENT_WORDS = ['晚年', '事业归宿', '退休', '归宿']
# 对定时辰有区分力的面向：只有依赖时支的子女类（时支随时辰变化）
TIME_SENSITIVE_DOMAINS = {'children'}


@dataclass(frozen=True)
class Event:
    year: int
    subject: str
    category: str | None
    domain: str
    raw: str


def _match_all(text: str, table: dict) -> list:
    return [k for k, words in table.items() if any(w in text for w in words)]


def parse_event(chunk: str) -> Event:
    chunk = chunk.strip()
    parts = [p.strip() for p in chunk.replace('：', ':').split(':')]
    if len(parts) not in (2, 3) or not all(parts):
        raise InputError(f'事件格式无法识别：「{chunk}」。用 "年:面向"（本人）或 "年:主体:类别"，如 "2022:子女:结婚"')
    try:
        year = int(parts[0])
    except ValueError:
        raise InputError(f'事件年份无法识别：「{parts[0]}」')
    label = ''.join(parts[1:])
    for w in UNSUPPORTED_EVENT_WORDS:
        if w in label:
            raise InputError(f'「{chunk}」：晚年/事业归宿类事件暂无经验证的评分规则，不能用于时辰反推。'
                             '目前能区分时辰的只有子女类事件（如 "2015:子女:出生"）。')
    if len(parts) == 3:
        subjects = _match_all(parts[1], SUBJECT_ALIASES)
        if len(subjects) != 1:
            raise InputError(f'「{chunk}」：主体「{parts[1]}」无法识别，支持 本人/子女/父母/配偶')
        subject = subjects[0]
        cats = _match_all(parts[2], CATEGORY_ALIASES)
    else:
        subjects = _match_all(label, SUBJECT_ALIASES)
        subjects = [s for s in subjects if s != 'self'] or (['self'] if subjects else [])
        if len(subjects) > 1:
            raise InputError(f'「{chunk}」同时出现多个主体（{"/".join(SUBJECT_NAMES[s] for s in subjects)}），'
                             '请改用 "年:主体:类别" 写清是谁的事')
        subject = subjects[0] if subjects else 'self'
        cats = _match_all(label, CATEGORY_ALIASES)
    if len(cats) > 1:
        # "婚恋" 类别词里含 "婚"，与"离婚/结婚"同类不算歧义
        raise InputError(f'「{chunk}」同时匹配多个类别（{"/".join(CATEGORY_NAMES[c] for c in cats)}），'
                         '请拆成多条事件，或用 "年:主体:类别" 只写一个类别')
    category = cats[0] if cats else None

    if subject == 'child':
        domain = 'children'
    elif subject == 'parent':
        if category == 'birth':
            raise InputError(f'「{chunk}」：父母类事件不支持"生育"类别')
        domain = 'family'
    elif subject == 'spouse':
        if category not in (None, 'marriage'):
            raise InputError(f'「{chunk}」：暂不支持以配偶为主体的{CATEGORY_NAMES[category]}事件（没有对应规则）。'
                             '如果是本人的婚恋事件，写 "年:婚恋"')
        domain = 'marriage'
    else:
        if category is None:
            raise InputError(f'「{chunk}」无法识别事件类别。支持：婚恋/事业/财/学业/健康/搬迁/生育(子女)/家庭；'
                             '别人的事请写主体，如 "2019:父亲:住院"')
        domain = 'children' if category == 'birth' else category
    return Event(year=year, subject=subject, category=category, domain=domain, raw=chunk)


def parse_events(raw: str, birth_year: int, as_of_year: int) -> tuple[list, list]:
    events, notes, seen = [], [], set()
    for chunk in raw.replace('，', ',').split(','):
        if not chunk.strip():
            continue
        ev = parse_event(chunk)
        if ev.year < birth_year:
            raise InputError(f'「{ev.raw}」：事件年份早于出生年')
        if ev.year > as_of_year:
            raise InputError(f'「{ev.raw}」：事件年份晚于查询日期，未来事件不能作为确认事件')
        key = (ev.year, ev.domain)
        if key in seen:
            notes.append(f'重复事件已合并（同年同面向只计一次）：{ev.raw}')
            continue
        seen.add(key)
        events.append(ev)
    if not events:
        raise InputError('没有可用的确认事件。格式示例：--verify-events "2003:学业,2015:子女:出生,2019:父亲:住院"')
    return events, notes


def score_events(pillars: list, is_male: bool, events: list) -> tuple[int, list]:
    """候选盘对确认事件的"应期对齐分"——只表示当前规则下的匹配程度，不是时辰概率。
    pillars: [年柱, 月柱, 日柱, 时柱]；events: [Event] 或 [(year, domain)]。"""
    year_gz, month_gz, day_gz, time_gz = pillars
    sst = SST_TABLE[day_gz[0]]
    ss = lambda g: sst.get(g, '?')
    year_zhi, month_zhi, day_zhi, time_zhi = year_gz[1], month_gz[1], day_gz[1], time_gz[1]
    gans = [year_gz[0], month_gz[0], day_gz[0], time_gz[0]]
    zhis_named = [('年支', year_zhi), ('月支', month_zhi), ('日支', day_zhi), ('时支', time_zhi)]
    cai, guansha, yin = ('正财', '偏财'), ('正官', '七杀'), ('正印', '偏印')
    bijie, shishang = ('比肩', '劫财'), ('食神', '伤官')
    has_cai = (any(ss(g) in cai for g in gans)
               or any(ss(cg) in cai for _, z in zhis_named for cg in ZHI_CANGGAN[z]))
    spouse = cai if is_male else guansha
    child = guansha if is_male else shishang
    ma = set('寅申巳亥')
    total, details = 0, []
    for ev in events:
        yr, dom = (ev.year, ev.domain) if isinstance(ev, Event) else ev
        gz = year_ganzhi(yr)
        lg, lz = gz
        sl = ss(lg)
        rel = lambda z: zhi_types(lz, z)
        best, note = 0, ''

        def lab(r):
            return '/'.join(REL_LABEL[t] for t in sorted(r))

        if dom == 'marriage':
            r = rel(day_zhi)
            if r & MOVE_TYPES:
                best, note = 3, f'流年{lz}动日支{day_zhi}({lab(r & MOVE_TYPES)})'
            for g in gans:
                if ss(g) in spouse and frozenset((lg, g)) in _GAN_HE_TABLE:
                    best = max(best, 2); note = note or f'配偶星{g}被流年{lg}合'
            if sl in spouse:
                best = max(best, 2); note = note or f'流年透配偶星{sl}'
            if BANHE in r:
                best = max(best, 1); note = note or f'流年{lz}与日支{day_zhi}半合'
        elif dom == 'career':
            if sl in guansha:
                best, note = 3, f'流年透{sl}'
            if rel(month_zhi) & {CHONG, LIUHE, XING, ZIXING}:
                best = max(best, 2); note = note or f'流年{lz}动月支{month_zhi}'
            if sl == '伤官':
                best = max(best, 2); note = note or '流年透伤官(事业动)'
            if sl in ('食神',) + cai:
                best = max(best, 1); note = note or f'流年透{sl}(弱)'
        elif dom == 'wealth':
            if sl in cai:
                best, note = 3, f'流年透财{sl}'
            if sl in bijie and has_cai:
                best = max(best, 3); note = note or '流年透比劫+原局有财(动财)'
            for nm, z in zhis_named:
                if ss(ZHI_CANGGAN[z][0]) in cai and rel(z) & {CHONG, LIUHE}:
                    best = max(best, 2); note = note or f'流年动{nm}财星'
        elif dom == 'study':
            if sl in yin:
                best, note = 3, f'流年透印{sl}'
            if rel(month_zhi) & {LIUHE, BANHE}:
                best = max(best, 2); note = note or '流年合月支'
            if sl in shishang:
                best = max(best, 1); note = note or f'流年透{sl}(弱)'
        elif dom == 'health':
            if CHONG in rel(day_zhi):
                best, note = 3, f'流年{lz}冲日支{day_zhi}'
            ms = [Member(nm, '支', z) for nm, z in zhis_named] + [Member('流年', '支', lz)]
            for st in branch_structures(ms, {'流年'}):
                if st.type == SANXING and st.positions & {'日支', '年支'}:
                    best = max(best, 2); note = note or '三刑动身宫'
            if day_gz[0] in GAN_KE_MAP[lg]:
                best = max(best, 2); note = note or f'流年{lg}剋日主'
            if CHONG in rel(year_zhi):
                best = max(best, 1); note = note or f'流年冲年支(弱)'
        elif dom == 'move':
            moved = False
            for nm, z in (('年支', year_zhi), ('月支', month_zhi), ('日支', day_zhi)):
                if CHONG in rel(z):
                    if lz in ma or z in ma:
                        best, note, moved = 3, f'驿马动:流年{lz}冲{nm}{z}', True
                    else:
                        best = max(best, 2); note = note or f'流年{lz}冲{nm}{z}'; moved = True
            if not moved and any(rel(z) & {CHONG, XING, ZIXING} for _, z in zhis_named):
                best = max(best, 1); note = note or '流年刑冲原局(弱)'
        elif dom == 'children':
            r = rel(time_zhi)
            if r & MOVE_TYPES:
                best, note = 3, f'流年{lz}动时支{time_zhi}({lab(r & MOVE_TYPES)})'
            if sl in child:
                best = max(best, 2); note = note or f'流年透子女星{sl}'
            if BANHE in r:
                best = max(best, 1); note = note or f'流年{lz}与时支{time_zhi}半合'
        elif dom == 'family':
            hit = False
            for nm, z in (('年支', year_zhi), ('月支', month_zhi)):
                if rel(z) & {CHONG, LIUHE, XING, ZIXING}:
                    best, note, hit = 3, f'流年{lz}动{nm}{z}', True
            if not hit and (sl in yin or sl == '偏财'):
                best = max(best, 2); note = note or f'流年透{sl}(父母星)'
        total += best
        details.append((yr, dom, gz, best, note))
    return total, details


@dataclass
class HourCandidate:
    label: str
    branch: str
    pillars: list
    windows: list           # [(chart_start, chart_end)]
    notes: list


def parse_hour_filter(text: str | None) -> tuple[set | None, tuple | None]:
    """--hour-candidates：地支列表（"寅,卯" / "寅时"）或北京时间范围（"03:00-07:00"）。无效输入报错。"""
    if not text or not text.strip():
        return None, None
    t = text.strip()
    m = re.fullmatch(r'(\d{1,2}):(\d{2})\s*[-~–—]\s*(\d{1,2}):(\d{2})', t)
    if m:
        h1, m1, h2, m2 = map(int, m.groups())
        if not (0 <= h1 <= 23 and 0 <= h2 <= 24 and 0 <= m1 < 60 and 0 <= m2 < 60):
            raise InputError(f'--hour-candidates 时间范围不合法：{t}')
        return None, ((h1, m1), (h2, m2))
    wanted = set()
    for item in re.split(r'[,，、\s]+', t):
        if not item:
            continue
        ch = item[:-1] if item.endswith('时') else item
        if len(ch) != 1 or ch not in ZHI12:
            raise InputError(f'--hour-candidates 含无效时辰「{item}」。应为地支（子丑寅…亥，可带"时"）或 "HH:MM-HH:MM"')
        wanted.add(ch)
    return wanted, None


def hour_candidates(birth: BirthTime, hour_filter: str | None = None) -> list:
    """按时辰、换日、节气切分候选段，逐段重算四柱（年月柱按北京标准时刻，日时柱按排盘时间），同四柱的段合并。"""
    branches, clock_range = parse_hour_filter(hour_filter)
    chart_day = birth.chart_time.date()
    if clock_range:
        (h1, m1), (h2, m2) = clock_range
        base = birth.standard.date()
        start_std = datetime(base.year, base.month, base.day) + timedelta(hours=h1, minutes=m1)
        end_std = datetime(base.year, base.month, base.day) + timedelta(hours=h2, minutes=m2)
        if birth.clock != birth.standard:  # 夏令时钟面范围同样减 1 小时
            start_std -= birth.clock - birth.standard
            end_std -= birth.clock - birth.standard
        if end_std <= start_std:
            end_std += timedelta(days=1)
        lo, hi = birth.to_chart(start_std), birth.to_chart(end_std)
    else:
        lo = datetime(chart_day.year, chart_day.month, chart_day.day)
        hi = lo + timedelta(days=1)

    cuts = {lo, hi}
    t = datetime(lo.year, lo.month, lo.day)
    while t <= hi:
        for h in range(0, 24):
            c = t + timedelta(hours=h)
            if (h % 2 == 1 or h == 0) and lo < c < hi:
                cuts.add(c)
        t += timedelta(days=1)
    for _, jt in jie_between(birth.to_standard(lo), birth.to_standard(hi)):
        cuts.add(birth.to_chart(jt))
    cuts = sorted(cuts)

    merged = {}
    for a, b in zip(cuts, cuts[1:]):
        mid = a + (b - a) / 2
        ym = year_month_pillars(birth.to_standard(mid))
        dh = day_hour_pillars(mid)
        key = (ym[0], ym[1], dh[0], dh[1])
        if branches and dh[1][1] not in branches:
            continue
        if key not in merged:
            merged[key] = HourCandidate(label='', branch=dh[1][1], pillars=list(key), windows=[], notes=[])
        merged[key].windows.append((a, b))
    cands = list(merged.values())
    if not cands:
        raise InputError('按 --hour-candidates 的限定没有得到任何候选时辰')
    by_branch = {}
    for c in cands:
        by_branch.setdefault(c.branch, []).append(c)
    for c in cands:
        label = f'{c.branch}时'
        peers = by_branch[c.branch]
        if len(peers) > 1:
            extra = []
            if len({p.pillars[2] for p in peers}) > 1:
                extra.append(f'{c.windows[0][0]:%m-%d}·{c.pillars[2]}日')
            if len({p.pillars[1] for p in peers}) > 1:
                extra.append(f'{c.pillars[1]}月')
            label += '（' + '·'.join(extra) + '）' if extra else ''
            c.notes.append('该时辰内跨换日或节气，已按段分开计算')
        c.label = label
    cands.sort(key=lambda c: c.windows[0][0])
    return cands


@dataclass
class VerifyResult:
    events: list
    candidates: list
    scores: list            # [(cand, total, details)] 按分数降序
    status: str             # ALL_ZERO / ALL_SAME / TIE / LEADER
    gap: int
    discriminating: list    # 分数在候选间有差异的事件
    notes: list


def verify_events(birth: BirthTime, gender: str, raw_events: str, as_of: datetime,
                  hour_filter: str | None = None) -> VerifyResult:
    events, notes = parse_events(raw_events, birth.standard.year, as_of.year)
    cands = hour_candidates(birth, hour_filter)
    is_male = gender == '男'
    scored = []
    for c in cands:
        total, details = score_events(c.pillars, is_male, events)
        scored.append((c, total, details))
    scored.sort(key=lambda x: -x[1])
    totals = [s[1] for s in scored]
    if max(totals) == 0:
        status, gap = 'ALL_ZERO', 0
    elif len(set(totals)) == 1:
        status, gap = 'ALL_SAME', 0
    elif len(totals) > 1 and totals[0] == totals[1]:
        status, gap = 'TIE', 0
    else:
        status, gap = 'LEADER', totals[0] - (totals[1] if len(totals) > 1 else 0)
    discriminating = []
    for i, ev in enumerate(events):
        if len({s[2][i][3] for s in scored}) > 1:
            discriminating.append(ev)
    return VerifyResult(events=events, candidates=cands, scores=scored, status=status, gap=gap,
                        discriminating=discriminating, notes=notes)
