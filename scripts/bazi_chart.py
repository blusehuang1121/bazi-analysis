"""
八字排盘脚本

用法（命令行传参，无需修改代码）：
    python bazi_chart.py -d "1983-11-21 03:30" -g 男 -l 岳阳
    python bazi_chart.py -d "1990-03-15 14:30" -g 女 --longitude 121.5
    python bazi_chart.py -d "1990-03-15 14:30" -g 男          # 不传出生地→使用北京时间

约定：
- 时间格式 "YYYY-MM-DD HH:MM"（北京时间）
- 真太阳时 = 北京时间 - 经度时差 + 均时差
- 晚子时（23:00-23:59）按方式 A：日柱不换日，时柱按当天日干起子时
- 出生地不在内置表中时仅应用均时差
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


def equation_of_time_minutes(year, month, day):
    """均时差近似公式（Spencer 1971 简化版）。一年内在约 -14 ~ +16 分钟之间。"""
    n = (date(year, month, day) - date(year, 1, 1)).days + 1
    B = math.radians(360.0 * (n - 81) / 365.0)
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


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
        location_used = f"{location}（不在内置表中，仅应用均时差）"
    else:
        # 没有任何位置信息时，连均时差都不应用
        eot_correction = 0.0

    correction = round(longitude_correction + eot_correction)

    original_dt = dt_input
    dt = original_dt + timedelta(minutes=correction)

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

    # ============ 输出 ============
    print("# 排盘结果\n")
    print("## 基本信息")
    print(f"- 输入时间：{original_dt.strftime('%Y-%m-%d %H:%M')}（北京时间）")
    print(f"- 出生地：{location_used}")
    print(f"- 经度时差：{round(longitude_correction):+d} 分钟")
    print(f"- 均时差：{round(eot_correction):+d} 分钟")
    print(f"- 真太阳时校正合计：{correction:+d} 分钟")
    print(f"- 校正后时间：{dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"- 性别：{gender}")
    print(f"- 当前年龄：实岁 {age_real}，虚岁 {age_xu}")
    if is_late_zi:
        print("- 时辰说明：晚子时（方式A：日柱不换日，时柱按当天日干起子时）")
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


if __name__ == '__main__':
    main()
