"""
八字排盘脚本（命令行 + markdown 输出；计算见 bazi_core.py）

用法：
    python bazi_chart.py -d "1983-11-21 03:30" -g 男 -l 岳阳
    python bazi_chart.py -d "1990-03-15 14:30" -g 女 --longitude 121.5 --as-of 2026-01-15
    python bazi_chart.py -d "1989-07-15 10:20" -g 男 --longitude 112.0 --dst clock
    python bazi_chart.py -d "1990-03-15 12:00" -g 男 --verify-events "2003:学业,2015:子女:出生" --hour-candidates "午,未"

输入约定：
- 时间为公历、北京时间（UTC+8）。境外出生先换算成北京时间
- 1986–1991 夏令时期间必须用 --dst 声明钟面口径
- 出生地不在内置表时必须给 --longitude；不给出生地 = 按北京标准时间排盘、不做真太阳时校正

输出（markdown）：基本信息与时间口径、四柱藏干十神、五行、原局内部作用、大运（精确交运时刻）、
当前位置（按 --as-of）、大运 vs 原局、当前流年节气月表、流年作用关系完整表、S/P 年份汇总；
或 --verify-events 的时辰反推结果。
"""

import argparse
import sys

# Windows 终端默认 GBK/cp936，输出 emoji 与部分汉字会崩；强制 UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

try:
    import bazi_core as core
except ImportError as exc:
    sys.exit(f'错误：{exc}')

from datetime import timedelta


def fmt_dt(dt, seconds=False):
    return dt.strftime('%Y-%m-%d %H:%M:%S' if seconds else '%Y-%m-%d %H:%M')


def lunar_python_version():
    try:
        import importlib.metadata as md
        return md.version('lunar_python')
    except Exception:
        return '未知'


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='八字排盘 — 输入出生信息，输出 markdown 格式的排盘结果',
        epilog=(
            '示例:\n'
            '  python bazi_chart.py -d "1983-11-21 03:30" -g 男 -l 岳阳\n'
            '  python bazi_chart.py -d "1990-03-15 14:30" -g 女 --longitude 121.5 --as-of 2026-01-15\n'
            '  python bazi_chart.py -d "1990-03-15 14:30" -g 男            # 不给出生地：北京标准时间，不校正'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-d', '--datetime', required=True, help='出生时间 "YYYY-MM-DD HH:MM"（公历、北京时间 UTC+8）')
    parser.add_argument('-g', '--gender', required=True, choices=['男', '女'], help='性别')
    parser.add_argument('-l', '--location', default=None,
                        help='出生城市（中文，内置表）。不在表中会报错，需改用 --longitude')
    parser.add_argument('--longitude', type=float, default=None, help='出生地经度（东经为正），优先于 --location')
    parser.add_argument('--dst', choices=['clock', 'standard'], default=None,
                        help='1986–1991 夏令时期间必填：clock=记录的是当时钟表时间（减 1 小时）；standard=已是标准北京时间')
    parser.add_argument('--as-of', default=None,
                        help='查询时刻 "YYYY-MM-DD[ HH:MM]"（北京时间），决定当前大运/流年；默认现在')
    parser.add_argument('--month-year', type=int, default=None,
                        help='节气月表所属的流年年份（立春起算），默认为查询时刻所在流年')
    parser.add_argument('--verify-events', default=None,
                        help='时辰反推：确认事件，"年:面向" 或 "年:主体:类别"，如 "2003:学业,2015:子女:出生,2019:父亲:住院"')
    parser.add_argument('--hour-candidates', default=None,
                        help='配合 --verify-events：限定候选，地支 "寅,卯" 或北京时间范围 "03:00-07:00"；无效输入会报错')
    return parser.parse_args(argv)


# ============ 输出：常规排盘 ============
def print_basic(chart, as_of):
    b = chart.birth
    ver = lunar_python_version()
    print('# 排盘结果\n')
    print('## 基本信息')
    ver_note = '' if ver == core.VERIFIED_LUNAR_PYTHON else f'（⚠️ 已验证版本为 {core.VERIFIED_LUNAR_PYTHON}，当前版本结果未经测试）'
    print(f'- 规则版本：{core.RULES_VERSION}；lunar_python {ver}{ver_note}')
    print(f'- 查询时刻（as-of）：{fmt_dt(as_of)}（北京时间）')
    print(f'- 输入时间：{fmt_dt(b.clock)}（公历钟面）')
    print(f'- 夏令时：{b.dst_note}')
    print(f'- 北京标准时间：{fmt_dt(b.standard)}')
    print(f'- 出生地：{b.location_label}')
    if b.corrected:
        print(f'- 经度时差：{b.longitude_minutes:+.1f} 分钟 → 地方平太阳时 {fmt_dt(b.local_mean)}')
        print(f'- 均时差：{b.eot_minutes:+.2f} 分钟 → 真太阳时 {fmt_dt(b.true_solar)}（合计 {b.total_minutes:+.1f} 分钟）')
    basis = '真太阳时' if b.corrected else '北京标准时间（未校正）'
    print(f'- 时间口径：年柱、月柱、起运按**北京标准时刻**与节气比较；日柱、时柱按**{basis}**；'
          '00:00 换日，晚子时日柱不换日、时柱按当天日干起子时')
    print(f'- 性别：{chart.gender}')
    y, m = core.age_between(b.standard, as_of)
    print(f'- 查询时年龄：周岁 {y} 岁 {m} 个月；虚岁 {core.nominal_age(b.standard, as_of)}（按农历年）')
    for w in b.warnings:
        print(f'- ⚠️ {w}')

    # 节气临界提示
    near = core.jie_between(b.standard - timedelta(hours=3), b.standard + timedelta(hours=3))
    for name, t in near:
        diff = (b.standard - t).total_seconds() / 60
        side = '后' if diff >= 0 else '前'
        print(f'- ⚠️ 出生时刻在{name}（{fmt_dt(t, True)}）{side} {abs(diff):.0f} 分钟：年柱/月柱对出生时间精度敏感，请核对出生记录')

    # 时辰边界：只校正经度 vs 加均时差
    if b.corrected:
        lng_only = b.standard + timedelta(minutes=b.longitude_minutes)
        if core.hour_branch(lng_only.hour) != core.hour_branch(b.true_solar.hour) or lng_only.date() != b.true_solar.date():
            print()
            print('⚠️ **重要警告：均时差改变了时辰或日期**')
            print(f'  - 只校正经度：{fmt_dt(lng_only)} → **{core.hour_branch(lng_only.hour)}时**')
            print(f'  - 加上均时差：{fmt_dt(b.true_solar)} → **{core.hour_branch(b.true_solar.hour)}时**（本脚本采用）')
            print('  - 若命主习惯的是另一版本，需核对后决定')
    if chart.is_late_zi:
        print('- 时辰说明：晚子时（日柱不换日，时柱按当天日干起子时）')
    print()

    print('## 大运顺逆判断')
    yg = chart.year_gz[0]
    yin_yang = '阳' if yg in core.YANG_GAN else '阴'
    print(f'- 命主为 **{chart.gender}**，年柱 **{chart.year_gz}**，年干 **{yg}** 为 **{yin_yang}** 干')
    print(f'- 所以是 **{yin_yang}{chart.gender}**，大运 **{chart.direction}**\n')


def print_pillars(chart):
    ss = chart.ss
    hidden = [core.ZHI_CANGGAN[gz[1]] for gz in chart.pillars]
    print('## 四柱八字\n')
    print('| | 年柱 | 月柱 | 日柱 | 时柱 |')
    print('|---|---|---|---|---|')
    print(f'| 干支 | {chart.year_gz} | {chart.month_gz} | **{chart.day_gz}** | {chart.time_gz} |')
    print(f'| 天干十神 | {ss(chart.year_gz[0])} | {ss(chart.month_gz[0])} | 日主 | {ss(chart.time_gz[0])} |')
    print('| 藏干 | ' + ' | '.join('、'.join(h) for h in hidden) + ' |')
    print('| 藏干十神 | ' + ' | '.join('/'.join(ss(g) for g in h) for h in hidden) + ' |\n')

    count = {wx: 0 for wx in '木火土金水'}
    for c in ''.join(chart.pillars):
        count[core.WX_MAP[c]] += 1
    print('## 五行分布（明字统计）')
    for wx, c in count.items():
        print(f"- {wx}：{c} {'●' * c if c else '○'}")
    print()

    rels = core.internal_relations(chart)
    print('## 原局内部作用关系（查表，四柱两两含不相邻）')
    print()
    print('> 合(X) 只标该合的化神五行，**不代表已合化**；合化成败需另按月令、力量、有无破合判断。')
    print(f'> 支持的关系：{core.SUPPORTED_RELATIONS}')
    print()
    gan = [core.relation_text(r) for r in rels if r.members[0].kind == '干']
    zhi = [core.relation_text(r) for r in rels if r.members[0].kind == '支' and len(r.members) == 2]
    multi = [core.relation_text(r) for r in rels if len(r.members) > 2]
    print(f"- 天干：{'；'.join(gan) if gan else '（无）'}")
    print(f"- 地支：{'；'.join(zhi) if zhi else '（无）'}")
    print(f"- 多支结构（原局固有，流年/大运表中不再逐年重复）：{'；'.join(multi) if multi else '（无）'}")
    print()


def fmt_age(t):
    y, m, d = t
    return f'{y} 岁 {m} 个月' + (f' {d} 天' if d else '')


def print_dayun(chart, as_of):
    ss = chart.ss
    cur = chart.dayun_at(as_of)
    y, m, d, h = chart.yun_offset
    print(f'## 大运排布（{chart.direction}）')
    print(f'- 起运：出生后 **{y} 年 {m} 个月 {d} 天**'
          f'（lunar_python 默认算法：出生到{"下一个" if chart.direction == "顺行" else "上一个"}节的天数与时辰差折算，3 天折 1 年）')
    print(f'- 起运时刻：**{fmt_dt(chart.yun_start)}**（北京时间）；每步大运区间为 [交运时刻, 下步交运时刻)\n')
    print('| 步 | 大运 | 交运时刻 | 下步交运 | 交运时年龄 | 天干十神 |')
    print('|---|---|---|---|---|---|')
    for dy in chart.dayun:
        mark = ' ← **当前**' if cur is dy else ''
        print(f'| {dy.index} | {dy.gz} | {fmt_dt(dy.start)} | {fmt_dt(dy.end)} | {fmt_age(dy.start_age)} | {ss(dy.gz[0])}{mark} |')
    print()

    ln_year = core.liunian_year_of(as_of)
    ln_gz = core.year_ganzhi(ln_year)
    print(f'## 当前位置（查询时刻 {fmt_dt(as_of)}）')
    if cur:
        wy, wm = core.span_years_months(cur.start, as_of)
        ry, rm = core.span_years_months(as_of, cur.end)
        print(f'- 当前大运：**{cur.gz}**（{fmt_dt(cur.start)} → {fmt_dt(cur.end)}），已走 {wy} 年 {wm} 个月，剩余约 {ry} 年 {rm} 个月')
    elif as_of < chart.yun_start:
        print(f'- 当前大运：**尚未起运**（起运时刻 {fmt_dt(chart.yun_start)}）')
    else:
        print('- 当前大运：超出已排大运范围')
    print(f'- 当前流年：**{ln_gz}**（流年 {ln_year}：{fmt_dt(core.lichun(ln_year))} 立春 → {fmt_dt(core.lichun(ln_year + 1))} 立春）')
    seg_switch = [s for s in core.year_segments(chart, ln_year)[1:] if s.dayun]
    for s in seg_switch:
        print(f'- 本流年内交运：{fmt_dt(s.start)} 起进入 **{s.dayun.gz}**，此前一段仍属上一步大运')
    nxt = next((dy for dy in chart.dayun if dy.start > as_of), None)
    if nxt:
        print(f'- 下一次交运：{fmt_dt(nxt.start)} → {nxt.gz}')
    print()

    print('## 各大运与原局的作用关系（查表）')
    print()
    print('| 大运 | 区间 | 大运 vs 原局作用 |')
    print('|---|---|---|')
    base = core.yuanju_members(chart)
    for dy in chart.dayun:
        rels = core.external_relations(core.ext_members('大运', dy.gz), base)
        text = '; '.join(core.relation_text(r, {'大运'}) for r in rels) or '(无明显作用)'
        mark = ' ←当前' if cur is dy else ''
        print(f'| **{dy.gz}**{mark} | {dy.start:%Y-%m-%d} → {dy.end:%Y-%m-%d} | {text} |')
    print()


def print_months(chart, year):
    rows = core.build_month_table(chart, year)
    print(f'## 流年 {year}（{core.year_ganzhi(year)}）节气月表')
    print()
    print('> 月以"节"为界（不是农历月、不是公历月），时刻为北京时间；子月、丑月跨公历年。'
          '作用关系为查表结果（流月与原局、流年、当时大运），不含吉凶判断。')
    print()
    print('| 节气月 | 起（节 · 北京时间） | 止 | 月柱 | 当时大运 | 流月作用 |')
    print('|---|---|---|---|---|---|')
    for i, r in enumerate(rows):
        end_name = rows[i + 1].jie if i + 1 < len(rows) else '立春'
        dy = r.dayun.gz if r.dayun else '起运前'
        if r.switch:
            dy += f'→{r.switch.gz}({r.switch.start:%m-%d %H:%M}交运)'
        text = '; '.join(core.relation_text(x, {'流月'}) for x in r.interactions) or '—'
        print(f'| {r.name} | {r.jie} {fmt_dt(r.start)} | {end_name} {fmt_dt(r.end)} | {r.gz} | {dy} | {text} |')
    print()


def print_years(chart, as_of):
    rows = core.build_year_table(chart)
    cur_year = core.liunian_year_of(as_of)
    birth_year = chart.birth.standard.year
    print('## 流年作用关系完整表（起运所在流年 → 80 岁）')
    print()
    print('**口径**：年份指流年（立春精确时刻起算，到次年立春止），不是公历年；"岁" = 流年年份 − 出生年（年份差，非周岁）。'
          '交运发生在某流年内时，大运列写"前→后(交运日)"，信号分段计算并标〔交运前〕〔交运后〕。')
    print()
    print('信号分级（传统规则启发式，按强度从高到低）：')
    for key in core.LEVEL_ORDER:
        lv = core.LEVELS[key]
        print(f'- {lv.emoji} {lv.name}：{lv.legend}')
    print('- ⚠️ 档位是规则触发强度提示，不是吉凶定性、不是危机预警；阈值为作者编码的启发式规则，未经统计标定')
    print('- 大运 vs 原局的作用见上表（每步大运固定），本表只列流年带来的作用')
    print()
    print('| 流年 | 岁 | 干支 | 所在大运 | 流年作用（原局；大运） | 关键信号 |')
    print('|---|---|---|---|---|---|')
    for row in rows:
        y = row.year
        mark = '✓' if y < cur_year else ('●' if y == cur_year else '○')
        this_year = ' **(当前流年)**' if y == cur_year else ''
        segs = row.segments
        if len(segs) == 1:
            yun = segs[0].dayun.gz if segs[0].dayun else '起运前'
        else:
            names = [s.dayun.gz if s.dayun else '起运前' for s in segs]
            verb = '起运' if segs[0].dayun is None else '交运'
            yun = f'{names[0]}→{names[-1]}({segs[-1].start:%m-%d}{verb})★'
        inter = []
        for tag, r in row.interactions:
            txt = core.relation_text(r, {'流年'})
            inter.append(f'〔{tag}〕{txt}' if tag else txt)
        sigs = [f'{s.display()}〔{tag}〕' if tag else s.display() for tag, s in row.signals]
        print(f"| {mark}{y}{this_year} | {y - birth_year} | {row.gz} | {yun} | {'; '.join(inter) or '—'} | {' '.join(sigs)} |")
    print()
    print('**符号说明**：✓ 已过流年  ● 当前流年  ○ 未来流年  ★ 该流年内起运/交运')
    print()
    return rows, cur_year


def life_stage_facets(age_n):
    """按年龄段列出待命主验证的候选面向（不是预测）。"""
    if age_n <= 13:
        return '家庭变动 / 父母关系 / 健康事件 / 学业转折 / 搬家转学'
    if age_n <= 17:
        return '学业重大节点 / 家庭关系 / 心理认知变化 / 健康 / 早期情感'
    if age_n <= 25:
        return '升学/就业转折 / 感情初体验 / 家庭经济 / 自我定位 / 重要离开或加入'
    if age_n <= 35:
        return '婚恋重大决定 / 工作变动 / 合伙创业 / 买房搬家 / 父母关系调整 / 子女节点'
    if age_n <= 50:
        return '事业重大节点 / 合伙股权调整 / 客户/资源结构变动 / 健康节点 / 家庭关系 / 子女'
    if age_n <= 65:
        return '事业转型 / 子女重大事件 / 父母健康 / 健康/根基调整 / 自我定位重整'
    return '健康节点 / 子女家庭 / 财产安排 / 生活方式重大调整 / 自我接纳'


def level_rows(rows, level):
    out = []
    for r in rows:
        tags = {tag for tag, s in r.signals if s.level == level}
        if tags:
            out.append((r, '' if '' in tags else '、'.join(sorted(tags))))
    return out


def print_sp(chart, rows, cur_year):
    birth_year = chart.birth.standard.year
    s_rows, p_rows = level_rows(rows, 'S'), level_rows(rows, 'P')
    print('## 🔥 S 级年份汇总（外触型 · 规则触发年份）')
    print()
    print('**关键说明（请如实理解，勿夸大）：**')
    print()
    print(f"- **判定条件**：{core.LEVELS['S'].legend}。")
    print('- **S 级 ≠ 危机预警**。信号可正可负，取决于命主当时所在大运和经营状态。')
    print('- 检测器本质识别的是"**财/配偶星与夫妻宫的双重触动**"这一种结构，**不是多面向探测器**。')
    print('- **具体应在哪个面向脚本无法判定**；面向需由命主反馈确定，不能由脚本或年龄段臆测。')
    print('- 下表「候选面向」按年龄段列出**待验证的可能方向**；阈值未经统计标定，属传统规则推断，不是验证过的预测。')
    print()
    if not s_rows:
        print('（本盘从起运到 80 岁无 S 级年份）')
    else:
        print('| 流年 | 岁 | 候选面向（待命主反馈，非预测） | 干支 | 大运 |')
        print('|---|---|---|---|---|')
        for r, part in s_rows:
            yun = '/'.join(dict.fromkeys(s.dayun.gz for s in r.segments if s.dayun))
            note = f'（仅{part}）' if part else ''
            print(f'| {r.year}{note} | {r.year - birth_year} | {life_stage_facets(r.year - birth_year)} | {r.gz} | {yun} |')
        print()
        past = sum(1 for r, _ in s_rows if r.year < cur_year)
        future = sum(1 for r, _ in s_rows if r.year > cur_year)
        print(f'**统计**：过往 S 级流年 {past} 个 / 未来 S 级流年 {future} 个')
        print()
        print('**用法**：拿过往 S 级流年与命主真实经历对照，记录实际应在的面向（及平淡、无感的年份），写入命主档案。'
              '命中率低 → 先核对出生时间记录，再考虑此盘规则不适用；不要为了对上而换解释。')

    print()
    print('## ✨ P 级年份汇总（内驱型 · 规则触发年份）')
    print()
    print('**关键说明**：')
    print()
    print(f"- **判定条件**：{core.LEVELS['P'].legend}。")
    print('- 财星透干单独标 💰P-财事，官杀透干单独标 ⚠️S复核，岁运并临单独标 ⚡，均不进 P 级判定。')
    print('- 应事倾向主动型：主动争取机会、开启新阶段、做关键决定；具体面向同样待命主反馈确定。')
    print()
    if not p_rows:
        print('（本盘从起运到 80 岁无 P 级年份）')
    else:
        print('| 流年 | 岁 | 候选面向（待命主反馈，非预测） | 干支 | 大运 |')
        print('|---|---|---|---|---|')
        for r, part in p_rows:
            yun = '/'.join(dict.fromkeys(s.dayun.gz for s in r.segments if s.dayun))
            note = f'（仅{part}）' if part else ''
            print(f'| {r.year}{note} | {r.year - birth_year} | {life_stage_facets(r.year - birth_year)} | {r.gz} | {yun} |')
        print()
        past = sum(1 for r, _ in p_rows if r.year < cur_year)
        future = sum(1 for r, _ in p_rows if r.year > cur_year)
        print(f'**统计**：过往 P 级流年 {past} 个 / 未来 P 级流年 {future} 个')


# ============ 输出：时辰反推 ============
STATUS_TEXT = {
    'ALL_ZERO': '所有候选在当前规则下均为 0 分：这批事件与任何候选都没有规则匹配，**不能据此判断时辰**。',
    'ALL_SAME': '所有候选同分：这批事件对时辰没有区分力，**不能据此判断时辰**。',
    'TIE': '最高分有并列：证据不足以在并列候选之间区分，**保留为不确定**。',
    'LEADER': '有唯一最高分候选。',
}


def print_verify(birth, gender, result, hour_filter, as_of):
    print('# 时辰反推结果\n')
    print(f'- 规则版本：{core.RULES_VERSION}；查询时刻 {fmt_dt(as_of)}')
    print('- **对齐分的含义**：候选盘在确认事件年是否出现对应面向的规则信号。权重是作者设定的传统规则，'
          '未经统计验证——它只表示"当前规则下的匹配程度"，**不是时辰为真的概率**。')
    print('- **假设**：出生日期可靠；年柱/月柱按北京标准时刻比较节气（候选段内跨节气会拆开）；'
          f"日柱/时柱按{'真太阳时' if birth.corrected else '北京标准时间'}，00:00 换日，晚子时日柱不换日；"
          f"候选范围：{hour_filter or '出生当日全部十二时辰'}")
    print('- 确认事件：' + '，'.join(
        f'{ev.year} {core.SUBJECT_NAMES[ev.subject]}·{core.DOMAIN_NAMES[ev.domain]}（{ev.raw}）'
        for ev in result.events))
    for n in result.notes:
        print(f'- ⚠️ {n}')
    print()
    print('| 排名 | 候选 | 排盘时间段 | 四柱 | 对齐分 |')
    print('|---|---|---|---|---|')
    rank, prev = 0, None
    for i, (c, total, _) in enumerate(result.scores, 1):
        if total != prev:
            rank, prev = i, total
        windows = '、'.join(f'{a:%m-%d %H:%M}–{b:%H:%M}' for a, b in c.windows)
        print(f"| {rank} | **{c.label}** | {windows} | {' '.join(c.pillars)} | {total} |")
    print()

    print('## 结论\n')
    print(STATUS_TEXT[result.status])
    if result.status == 'LEADER':
        top = result.scores[0]
        print(f'\n- 当前规则下匹配度最高：**{top[0].label}**，领先第二名 {result.gap} 分。'
              + ('分差只有 1，区分很弱。' if result.gap == 1 else '')
              + '请结合命主体感、可靠的出生记录再定，不要单凭分数确定时辰。')
    elif result.status == 'TIE':
        top_score = result.scores[0][1]
        tied = [c.label for c, t, _ in result.scores if t == top_score]
        print(f'\n- 并列最高（{top_score} 分）：{"、".join(tied)}')
    print()

    show = result.scores[:1] if result.status == 'LEADER' else [s for s in result.scores if s[1] == result.scores[0][1]][:3]
    if result.status not in ('ALL_ZERO', 'ALL_SAME'):
        print('## 逐事件明细\n')
        for c, total, details in show:
            print(f'**{c.label}**（{total} 分）\n')
            print('| 事件年 | 面向 | 流年 | 得分 | 命中规则 |')
            print('|---|---|---|---|---|')
            for yr, dom, gz, best, note in details:
                print(f"| {yr} | {core.DOMAIN_NAMES[dom]} | {gz} | {best} | {note or '（未对上）'} |")
            print()

    print('## 事件区分力\n')
    events = result.events
    if result.discriminating:
        print('- 在候选之间分数有差异的事件：' + '，'.join(f'{e.year}{core.DOMAIN_NAMES[e.domain]}' for e in result.discriminating))
    else:
        print('- 没有任何事件在候选之间产生分差。')
    if not any(e.domain in core.TIME_SENSITIVE_DOMAINS for e in events):
        print('- 本批事件没有子女类事件。婚恋、健康主要看日支，事业、家庭、搬迁主要看年月支，基本不随时辰改变'
              '（婚恋里"时干配偶星被合"一项例外），通常无法区分相邻时辰。建议补充子女出生等子女类事件（如 "2015:子女:出生"）。')
    print('- 时辰定下后写入命主档案；出生时间有可靠记录（出生证明等）时，以记录为准，不因事件对不上而改时辰。')


# ============ 主流程 ============
def main(argv=None):
    args = parse_args(argv)
    try:
        as_of = core.parse_as_of(args.as_of)
        birth = core.resolve_birth_time(args.datetime, args.location, args.longitude, args.dst)
        if args.verify_events:
            result = core.verify_events(birth, args.gender, args.verify_events, as_of, args.hour_candidates)
            print_verify(birth, args.gender, result, args.hour_candidates, as_of)
            return
        if args.hour_candidates:
            raise core.InputError('--hour-candidates 只能配合 --verify-events 使用')
        chart = core.build_chart(birth, args.gender)
    except core.InputError as exc:
        sys.exit(f'错误：{exc}')

    print_basic(chart, as_of)
    print_pillars(chart)
    print_dayun(chart, as_of)
    print_months(chart, args.month_year or core.liunian_year_of(as_of))
    rows, cur_year = print_years(chart, as_of)
    print_sp(chart, rows, cur_year)


if __name__ == '__main__':
    main()
