"""
bazi-analysis 表驱动测试

运行：python -m unittest discover -s tests -v

真值来源（不以本程序输出为准）：
- 节气时刻、日柱、起运：lunar_python 1.4.8 直接调用（库约定作为基准）
- 五鼠遁、五虎遁、天干五合与剋、地支六合六冲六害六破三合三会三刑：本文件手写的规则真值表
- 夏令时区间：Python zoneinfo（IANA Asia/Shanghai），不可用时跳过
测试通过只说明程序按声明的历法口径与规则表计算，不说明命理判断有效。
"""

import os
import subprocess
import sys
import unittest
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import bazi_core as core  # noqa: E402
import bazi_chart  # noqa: E402
from lunar_python import Solar  # noqa: E402

ZHI = '子丑寅卯辰巳午未申酉戌亥'
GAN = '甲乙丙丁戊己庚辛壬癸'


def lib_ec(dt):
    return Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second).getLunar().getEightChar()


def lib_jie(year, name):
    t = Solar.fromYmd(year, 6, 1).getLunar().getJieQiTable()[name]
    return datetime(t.getYear(), t.getMonth(), t.getDay(), t.getHour(), t.getMinute(), t.getSecond())


def fake_chart(year_gz, month_gz, day_gz, time_gz, gender='男'):
    return core.Chart(birth=None, gender=gender, year_gz=year_gz, month_gz=month_gz, day_gz=day_gz,
                      time_gz=time_gz, direction='顺行', yun_start=None, yun_offset=(0, 0, 0, 0), dayun=[])


# ---------------- 手写规则真值表 ----------------
TRUTH_WUSHUDUN = {'甲': '甲', '己': '甲', '乙': '丙', '庚': '丙', '丙': '戊', '辛': '戊', '丁': '庚', '壬': '庚',
                  '戊': '壬', '癸': '壬'}                      # 甲己还加甲，乙庚丙作初，丙辛从戊起，丁壬庚子居，戊癸何方发，壬子是真途
TRUTH_WUHUDUN = {'甲': '丙', '己': '丙', '乙': '戊', '庚': '戊', '丙': '庚', '辛': '庚', '丁': '壬', '壬': '壬',
                 '戊': '甲', '癸': '甲'}                      # 甲己之年丙作首……
TRUTH_GAN_KE = {'甲': '戊己', '乙': '戊己', '丙': '庚辛', '丁': '庚辛', '戊': '壬癸', '己': '壬癸',
                '庚': '甲乙', '辛': '甲乙', '壬': '丙丁', '癸': '丙丁'}
TRUTH_GAN_HE = ['甲己', '乙庚', '丙辛', '丁壬', '戊癸']
TRUTH_LIUHE = ['子丑', '寅亥', '卯戌', '辰酉', '巳申', '午未']
TRUTH_CHONG = ['子午', '丑未', '寅申', '卯酉', '辰戌', '巳亥']
TRUTH_HAI = ['子未', '丑午', '寅巳', '卯辰', '申亥', '酉戌']
TRUTH_PO = ['子酉', '午卯', '巳申', '寅亥', '辰丑', '戌未']
TRUTH_BANHE = ['申子', '子辰', '亥卯', '卯未', '寅午', '午戌', '巳酉', '酉丑']
TRUTH_GONG = ['申辰', '亥未', '寅戌', '巳丑']
TRUTH_ZIXING = '辰午酉亥'


def truth_zhi_types(a, b):
    if a == b:
        return {core.ZIXING if a in TRUTH_ZIXING else core.FUYIN}
    s = {a, b}
    out = set()
    for table, t in ((TRUTH_LIUHE, core.LIUHE), (TRUTH_CHONG, core.CHONG), (TRUTH_HAI, core.HAI),
                     (TRUTH_PO, core.PO), (TRUTH_BANHE, core.BANHE), (TRUTH_GONG, core.GONG)):
        if any(set(p) == s for p in table):
            out.add(t)
    if s == {'子', '卯'}:
        out.add(core.XING)
    return out


# ================= P0-1 时间基准 =================
class TestTimeBasis(unittest.TestCase):
    def test_p0_1_lichun_uses_standard_instant(self):
        birth = core.resolve_birth_time('2024-02-04 16:32', '北京')
        chart = core.build_chart(birth, '男')
        lichun = lib_jie(2024, '立春')
        self.assertLess(birth.true_solar, lichun, '本例的真太阳时钟面值应落在立春之前，才能覆盖原缺陷')
        self.assertGreater(birth.standard, lichun)
        self.assertEqual((chart.year_gz, chart.month_gz), ('甲辰', '丙寅'))
        ec = lib_ec(birth.standard)
        self.assertEqual((chart.year_gz, chart.month_gz), (ec.getYear(), ec.getMonth()))

    def test_jieqi_boundary_independent_of_longitude(self):
        cases = [(2024, '立春'), (2020, '小暑'), (2026, '大雪'), (2021, '小寒'), (1993, '大雪')]
        for year, name in cases:
            jt = lib_jie(year, name)
            for delta in (-2, 2):
                std = jt + timedelta(minutes=delta)
                ec = lib_ec(std)
                expect = (ec.getYear(), ec.getMonth())
                for lng in (None, 76.0, 120.0, 129.6):
                    with self.subTest(jie=name, year=year, delta=delta, lng=lng):
                        b = core.resolve_birth_time(std.strftime('%Y-%m-%d %H:%M'), longitude=lng)
                        # 输入精度到分钟：秒数截断后仍在节气同侧
                        c = core.build_chart(b, '女')
                        self.assertEqual((c.year_gz, c.month_gz), expect)
            before = lib_ec(jt - timedelta(minutes=2)).getMonth()
            after = lib_ec(jt + timedelta(minutes=2)).getMonth()
            self.assertNotEqual(before, after, f'{year}{name} 前后月柱应不同')

    def test_true_solar_cross_day_backward(self):
        b = core.resolve_birth_time('2000-01-01 01:00', '乌鲁木齐')
        self.assertEqual(b.true_solar.date(), date(1999, 12, 31))
        c = core.build_chart(b, '男')
        ec_std = lib_ec(datetime(2000, 1, 1, 1, 0))
        self.assertEqual((c.year_gz, c.month_gz), (ec_std.getYear(), ec_std.getMonth()))
        self.assertEqual(c.day_gz, lib_ec(datetime(1999, 12, 31, 12)).getDay())
        self.assertEqual(c.time_gz[1], '亥')

    def test_true_solar_cross_day_forward(self):
        b = core.resolve_birth_time('2000-01-01 23:40', '牡丹江')
        self.assertEqual(b.true_solar.date(), date(2000, 1, 2))
        c = core.build_chart(b, '男')
        self.assertEqual(c.day_gz, lib_ec(datetime(2000, 1, 2, 12)).getDay())
        self.assertEqual(c.time_gz, TRUTH_WUSHUDUN[c.day_gz[0]] + '子')
        ec_std = lib_ec(datetime(2000, 1, 1, 23, 40))
        self.assertEqual((c.year_gz, c.month_gz), (ec_std.getYear(), ec_std.getMonth()))

    def test_hour_branch_table(self):
        expect = {23: '子', 0: '子', 1: '丑', 2: '丑', 3: '寅', 4: '寅', 5: '卯', 6: '卯', 7: '辰', 8: '辰',
                  9: '巳', 10: '巳', 11: '午', 12: '午', 13: '未', 14: '未', 15: '申', 16: '申',
                  17: '酉', 18: '酉', 19: '戌', 20: '戌', 21: '亥', 22: '亥'}
        for h, z in expect.items():
            self.assertEqual(core.hour_branch(h), z, h)

    def test_wushudun_truth_table(self):
        for dg in GAN:
            start = GAN.index(TRUTH_WUSHUDUN[dg])
            for i, z in enumerate(ZHI):
                self.assertEqual(core.hour_pillar(dg, z), GAN[(start + i) % 10] + z, (dg, z))

    def test_hour_pillar_matches_library_except_late_zi(self):
        d = datetime(2023, 3, 1)
        for k in range(20):
            day = d + timedelta(days=37 * k)
            for h in range(0, 23):
                dt = day.replace(hour=h, minute=30)
                with self.subTest(dt=dt):
                    self.assertEqual(core.day_hour_pillars(dt), (lib_ec(dt).getDay(), lib_ec(dt).getTime()))

    def test_equation_of_time_range(self):
        for n in range(366):
            v = core.equation_of_time_minutes(date(2024, 1, 1) + timedelta(days=n))
            self.assertTrue(-15.5 <= v <= 17.0, v)


# ================= P0-2 晚子时 =================
class TestLateZi(unittest.TestCase):
    def test_p0_2_late_zi_keeps_real_instant(self):
        b = core.resolve_birth_time('2020-07-06 23:17')
        c = core.build_chart(b, '男')
        xiaoshu = lib_jie(2020, '小暑')
        self.assertTrue(datetime(2020, 7, 6, 22, 59) < xiaoshu < b.standard)
        self.assertEqual(c.pillars, ['庚子', '癸未', '庚戌', '丙子'])
        ec = lib_ec(b.standard)
        ec.setSect(2)  # 库：晚子时日柱算当天
        self.assertEqual((c.year_gz, c.month_gz, c.day_gz), (ec.getYear(), ec.getMonth(), ec.getDay()))
        self.assertEqual(c.time_gz, TRUTH_WUSHUDUN['庚'] + '子', '本 skill 约定：时柱按当天日干起子时')
        self.assertGreater(c.yun_start - b.standard, timedelta(days=365))
        yun = lib_ec(b.standard).getYun(1).getStartSolar()
        self.assertEqual(c.yun_start, datetime(yun.getYear(), yun.getMonth(), yun.getDay(), yun.getHour(), yun.getMinute(), yun.getSecond()))

    def test_late_zi_without_jieqi(self):
        c = core.build_chart(core.resolve_birth_time('2021-03-10 23:40'), '女')
        ec = lib_ec(datetime(2021, 3, 10, 23, 40))
        ec.setSect(2)
        self.assertEqual(c.pillars[:3], [ec.getYear(), ec.getMonth(), ec.getDay()])
        self.assertEqual(c.time_gz, TRUTH_WUSHUDUN[c.day_gz[0]] + '子')


# ================= P0-3 大运区间 =================
class TestDayun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chart = core.build_chart(core.resolve_birth_time('1990-03-15 14:30'), '男')

    def test_start_matches_library(self):
        s = lib_ec(datetime(1990, 3, 15, 14, 30)).getYun(1).getStartSolar()
        self.assertEqual(self.chart.yun_start, datetime(s.getYear(), s.getMonth(), s.getDay(), s.getHour(), s.getMinute()))
        self.assertEqual(self.chart.yun_start, datetime(1997, 2, 25, 14, 30))

    def test_left_closed_right_open(self):
        c = self.chart
        first, second = c.dayun[0], c.dayun[1]
        table = [
            (datetime(1997, 1, 1), None),
            (datetime(1997, 2, 25, 14, 29), None),
            (datetime(1997, 2, 25, 14, 30), first.gz),
            (datetime(2007, 2, 25, 14, 29), first.gz),
            (datetime(2007, 2, 25, 14, 30), second.gz),
        ]
        for when, gz in table:
            dy = c.dayun_at(when)
            self.assertEqual(dy.gz if dy else None, gz, when)
        for a, b in zip(c.dayun, c.dayun[1:]):
            self.assertEqual(a.end, b.start)
        self.assertEqual([d.gz for d in c.dayun[:3]], ['庚辰', '辛巳', '壬午'])

    def test_year_segments(self):
        c = self.chart
        segs = core.year_segments(c, 1997)
        self.assertEqual([s.dayun.gz if s.dayun else None for s in segs], [None, '庚辰'])
        self.assertEqual(segs[1].start, datetime(1997, 2, 25, 14, 30))
        self.assertEqual([s.dayun.gz for s in core.year_segments(c, 2007)], ['庚辰', '辛巳'])
        self.assertEqual(len(core.year_segments(c, 2008)), 1)

    def test_switch_year_signal_tagged(self):
        # 2027 丁未：丁壬合只在壬午段成立 → 标"交运前"
        row = core.build_year_row(self.chart, 2027)
        tags = {(tag, s.code) for tag, s in row.signals}
        self.assertIn(('交运前', 'HE_YUN_GAN'), tags)

    def test_age(self):
        b = datetime(1991, 11, 20, 6, 15)
        self.assertEqual(core.age_between(b, datetime(2026, 9, 16)), (34, 9))
        self.assertEqual(core.age_between(b, datetime(2026, 11, 20, 6, 14)), (34, 11))
        self.assertEqual(core.age_between(b, datetime(2026, 11, 20, 6, 15)), (35, 0))


# ================= P0-4 流年口径 =================
class TestLiunian(unittest.TestCase):
    def test_p0_4_as_of_before_lichun(self):
        self.assertEqual(core.year_ganzhi(core.liunian_year_of(datetime(2026, 1, 15))), '乙巳')
        self.assertEqual(core.year_ganzhi(core.liunian_year_of(datetime(2026, 2, 5))), '丙午')
        lc = lib_jie(2026, '立春')
        self.assertEqual(core.liunian_year_of(lc - timedelta(minutes=1)), 2025)
        self.assertEqual(core.liunian_year_of(lc), 2026)

    def test_lichun_in_february_of_same_year(self):
        for y in range(1900, 2101):
            lc = core.lichun(y)
            self.assertEqual((lc.year, lc.month), (y, 2), y)

    def test_year_ganzhi_matches_library(self):
        for y in range(1940, 2061):
            self.assertEqual(core.year_ganzhi(y), lib_ec(core.lichun(y) + timedelta(minutes=1)).getYear(), y)

    def test_as_of_parse(self):
        self.assertEqual(core.parse_as_of('2026-01-15'), datetime(2026, 1, 15))
        with self.assertRaises(core.InputError):
            core.parse_as_of('2026/01/15')


# ================= P1-13 节气月表 =================
class TestMonths(unittest.TestCase):
    def test_month_table_2026(self):
        chart = core.build_chart(core.resolve_birth_time('1991-10-05 08:20', longitude=113.3), '女')
        rows = core.build_month_table(chart, 2026)
        self.assertEqual([r.name for r in rows], [z + '月' for z in '寅卯辰巳午未申酉戌亥子丑'])
        first = GAN.index(TRUTH_WUHUDUN['丙'])
        expect = [GAN[(first + i) % 10] + '寅卯辰巳午未申酉戌亥子丑'[i] for i in range(12)]
        self.assertEqual([r.gz for r in rows], expect)
        self.assertEqual(rows[10].start, lib_jie(2026, '大雪'))
        self.assertEqual(rows[11].start.year, 2027)
        self.assertEqual(rows[11].end, core.lichun(2027))
        for prev, row in zip(rows, rows[1:]):
            self.assertEqual(prev.end, row.start)
            self.assertEqual(lib_ec(row.start - timedelta(minutes=1)).getMonth(), prev.gz)
            self.assertEqual(lib_ec(row.start + timedelta(minutes=1)).getMonth(), row.gz)

    def test_wuhudun_truth(self):
        for y in range(2000, 2012):
            yg = core.year_ganzhi(y)[0]
            rows_gz = lib_ec(core.lichun(y) + timedelta(minutes=5)).getMonth()
            self.assertEqual(rows_gz, TRUTH_WUHUDUN[yg] + '寅', y)


# ================= P0-5 / P1-6 / P1-7 关系 =================
class TestRelations(unittest.TestCase):
    def test_gan_ke_truth_table(self):
        for a in GAN:
            for b in GAN:
                self.assertEqual(b in core.GAN_KE_MAP[a], b in TRUTH_GAN_KE[a], (a, b))

    def test_gan_pair_relations(self):
        for a in GAN:
            for b in GAN:
                rels = core.gan_pair_relations(core.Member('流年', '干', a), core.Member('大运', '干', b))
                types = {r.type for r in rels}
                self.assertEqual(core.GAN_HE in types, any(set(p) == {a, b} for p in TRUTH_GAN_HE), (a, b))
                for r in rels:
                    if r.type == core.GAN_KE:
                        self.assertIn(r.members[1].char, TRUTH_GAN_KE[r.members[0].char], (a, b))

    def test_p0_5_ke_yun_gan_direction_all_pairs(self):
        chart = fake_chart('庚申', '戊子', '甲子', '庚午')
        for yt in GAN:
            for yun in GAN:
                sigs = core.detect_key_signals(chart, yt, '子', yun, '午')
                ke = [s for s in sigs if s.code == 'KE_YUN_GAN']
                if yun in TRUTH_GAN_KE[yt]:
                    self.assertEqual(len(ke), 1, (yt, yun))
                    self.assertEqual(ke[0].text, f'流年剋大运干({yt}剋{yun})')
                else:
                    self.assertEqual(ke, [], (yt, yun))

    def test_zhi_pair_truth_table(self):
        for a in ZHI:
            for b in ZHI:
                self.assertEqual(core.zhi_types(a, b), truth_zhi_types(a, b), (a, b))

    def test_p1_6_banhe_not_liuhe(self):
        self.assertEqual(core.zhi_types('寅', '午'), {core.BANHE})
        self.assertEqual(core.zhi_types('酉', '酉'), {core.ZIXING})
        total, details = core.score_events(['庚申', '戊子', '甲子', '庚午'], True, [(2022, 'children')])
        self.assertEqual(total, 1, details)

    def test_full_sanhe_new_trigger_with_positions(self):
        base = [core.Member('年柱', '支', '巳'), core.Member('日柱', '支', '酉'), core.Member('月柱', '支', '子')]
        rels = core.branch_structures(base + [core.Member('流年', '支', '丑')], {'流年'})
        sanhe = [r for r in rels if r.type == core.SANHE]
        self.assertEqual(len(sanhe), 1)
        self.assertEqual(sanhe[0].positions, {'年柱', '日柱', '流年'})
        self.assertEqual(sanhe[0].element, '金')
        self.assertIn('巳酉丑三合金局', core.relation_text(sanhe[0]))

    def test_existing_structure_not_retriggered(self):
        base = [core.Member('年柱', '支', '巳'), core.Member('月柱', '支', '酉'), core.Member('日柱', '支', '丑')]
        self.assertEqual(core.branch_structures(base + [core.Member('流年', '支', '巳')], {'流年'}), [])
        self.assertEqual(len(core.branch_structures(base)), 1)

    def test_sanhui_with_dayun(self):
        ms = [core.Member('时柱', '支', '寅'), core.Member('大运', '支', '卯'), core.Member('流年', '支', '辰')]
        rels = core.branch_structures(ms, {'流年'})
        self.assertEqual([(r.type, r.positions) for r in rels], [(core.SANHUI, {'时柱', '大运', '流年'})])

    def test_yuanju_sanxing_not_repeated_yearly(self):
        chart = fake_chart('己丑', '甲戌', '丁未', '庚子')
        for y in range(2000, 2012):
            gz = core.year_ganzhi(y)
            sigs = core.detect_key_signals(chart, gz[0], gz[1], '甲', '寅')
            self.assertNotIn('SANXING_DAY', {s.code for s in sigs}, y)
        chart2 = fake_chart('己丑', '甲子', '丁未', '庚子')
        sigs = core.detect_key_signals(chart2, '甲', '戌', '甲', '寅')
        self.assertIn('SANXING_DAY', {s.code for s in sigs})

    def test_suiyun_zhi_relation_and_duplicates(self):
        rels = core.external_relations(core.ext_members('流年', '甲子'), core.ext_members('大运', '庚午'))
        self.assertIn((core.CHONG, frozenset({'流年', '大运'})), {(r.type, frozenset(r.positions)) for r in rels})
        chart = fake_chart('甲子', '丙寅', '甲子', '丙寅')
        rels = core.external_relations(core.ext_members('流年', '庚子'), core.yuanju_members(chart))
        fuyin = sorted(next(m.pos for m in r.members if m.pos != '流年') for r in rels if r.type == core.FUYIN)
        self.assertEqual(fuyin, ['年柱', '日柱'])

    def test_he_text_does_not_claim_transformation(self):
        r = core.zhi_pair_relations(core.Member('流年', '支', '子'), core.Member('日柱', '支', '丑'))
        txt = core.relation_text(r[0], {'流年'})
        self.assertEqual(txt, '日柱支:子丑合(土)')
        self.assertNotIn('化', txt)

    def test_sp_summary_uses_level_not_emoji(self):
        fake = core.YearRow(year=2030, gz='庚戌', window=None, segments=[], interactions=[],
                            signals=[('', core.Signal('C', 'X', '🔥看起来像S级的文字'))])
        self.assertEqual(bazi_chart.level_rows([fake], 'S'), [])
        real = core.YearRow(year=2031, gz='辛亥', window=None, segments=[], interactions=[],
                            signals=[('交运后', core.Signal('S', 'Y', '文字'))])
        self.assertEqual([(r.year, part) for r, part in bazi_chart.level_rows([real], 'S')], [(2031, '交运后')])


# ================= P1-8 / P1-9 时辰反推 =================
class TestVerifyEvents(unittest.TestCase):
    def test_p1_8_event_subjects(self):
        table = [
            ('2020:孩子结婚', 'child', 'children'),
            ('2020:本人结婚', 'self', 'marriage'),
            ('2020:父亲住院', 'parent', 'family'),
            ('2020:本人住院', 'self', 'health'),
            ('2022:子女:结婚', 'child', 'children'),
            ('2003:学业', 'self', 'study'),
            ('2015:生孩子', 'child', 'children'),
            ('2012:升迁', 'self', 'career'),
            ('2009:老婆', 'spouse', 'marriage'),
        ]
        for text, subject, domain in table:
            ev = core.parse_event(text)
            self.assertEqual((ev.subject, ev.domain), (subject, domain), text)

    def test_p1_8_unsupported_and_ambiguous(self):
        for text in ('2030:晚年', '2030:事业归宿', '2020:结婚搬家', '2020:老公住院', '2020:随便', '2020', 'abc:婚恋',
                     '2020:孩子父亲住院'):
            with self.assertRaises(core.InputError, msg=text):
                core.parse_event(text)

    def test_hour_filter_validation(self):
        for bad in ('xyz', '寅,甲', '25:00-26:00', '寅卯'):
            with self.assertRaises(core.InputError, msg=bad):
                core.parse_hour_filter(bad)
        self.assertEqual(core.parse_hour_filter('寅, 卯时')[0], {'寅', '卯'})
        self.assertEqual(core.parse_hour_filter('03:00-07:00')[1], ((3, 0), (7, 0)))

    def _birth(self):
        return core.resolve_birth_time('1980-12-17 12:00')   # 庚申年 戊子月 甲子日

    def test_all_same_and_all_zero(self):
        birth = self._birth()
        # 家庭类只看年支、月支与流年干，不随时辰变化
        day = ['庚申', '戊子', '甲子', '甲子']
        zero_year = next(y for y in range(1990, 2025) if core.score_events(day, True, [(y, 'family')])[0] == 0)
        pos_year = next(y for y in range(1990, 2025) if core.score_events(day, True, [(y, 'family')])[0] > 0)
        asof = datetime(2026, 9, 16)
        self.assertEqual(core.verify_events(birth, '男', f'{zero_year}:家庭', asof).status, 'ALL_ZERO')
        r = core.verify_events(birth, '男', f'{pos_year}:家庭', asof)
        self.assertEqual(r.status, 'ALL_SAME')
        self.assertEqual(r.discriminating, [])

    def test_tie_and_leader(self):
        birth = self._birth()
        asof = datetime(2026, 9, 16)
        r = core.verify_events(birth, '男', '2022:子女:出生', asof)
        self.assertEqual(r.status, 'TIE')
        top = sorted(c.branch for c, t, _ in r.scores if t == r.scores[0][1])
        self.assertEqual(top, sorted('申亥巳寅'))
        r2 = core.verify_events(birth, '男', '2022:子女:出生,2016:子女:出生', asof)   # 2016 丙申：申伏吟、寅冲、巳合/刑?、亥害
        self.assertIn(r2.status, ('LEADER', 'TIE'))
        self.assertTrue(r2.discriminating)

    def test_duplicates_merged(self):
        r = core.verify_events(self._birth(), '男', '2022:子女,2022:子女:出生', datetime(2026, 9, 16))
        self.assertEqual(len(r.events), 1)
        self.assertTrue(any('重复' in n for n in r.notes))

    def test_event_year_bounds(self):
        with self.assertRaises(core.InputError):
            core.verify_events(self._birth(), '男', '1970:学业', datetime(2026, 9, 16))
        with self.assertRaises(core.InputError):
            core.verify_events(self._birth(), '男', '2030:学业', datetime(2026, 9, 16))

    def test_cross_day_candidates(self):
        cands = core.hour_candidates(self._birth(), '22:00-02:00')
        zi = [c for c in cands if c.branch == '子']
        self.assertEqual(len(zi), 2)
        self.assertEqual({c.pillars[2] for c in zi}, {'甲子', '乙丑'})
        self.assertEqual(len({c.label for c in cands}), len(cands))
        self.assertEqual([c.branch for c in cands], ['亥', '子', '子', '丑'])

    def test_jieqi_split_candidate(self):
        birth = core.resolve_birth_time('2020-07-06 12:00')      # 小暑 23:14:28
        cands = core.hour_candidates(birth)
        zi = [c for c in cands if c.branch == '子']
        self.assertEqual(sorted(c.pillars[1] for c in zi), ['壬午', '癸未'])
        early = next(c for c in zi if c.pillars[1] == '壬午')
        self.assertEqual(len(early.windows), 2)     # 早子 00–01 与晚子 23:00–23:14 四柱相同，合并
        self.assertEqual(len(cands), 13)

    def test_invalid_candidates_raise(self):
        with self.assertRaises(core.InputError):
            core.verify_events(self._birth(), '男', '2022:子女', datetime(2026, 9, 16), 'xyz')


# ================= P2-15 输入 =================
class TestInput(unittest.TestCase):
    def test_unknown_city_raises(self):
        with self.assertRaises(core.InputError):
            core.resolve_birth_time('1991-10-05 08:20', '不存在市')

    def test_longitude_validation(self):
        for bad in (float('nan'), float('inf'), 200.0, -181.0):
            with self.assertRaises(core.InputError):
                core.resolve_birth_time('1991-10-05 08:20', longitude=bad)
        b = core.resolve_birth_time('1991-10-05 08:20', longitude=10.0)
        self.assertTrue(any('超出中国范围' in w for w in b.warnings))

    def test_urumqi_longitude_minutes(self):
        b = core.resolve_birth_time('2000-06-01 12:00', '乌鲁木齐')
        self.assertAlmostEqual(b.longitude_minutes, -129.6, places=6)

    def test_no_location_means_no_correction(self):
        b = core.resolve_birth_time('2000-06-01 12:00')
        self.assertFalse(b.corrected)
        self.assertEqual(b.chart_time, b.standard)

    def test_dst_requires_declaration(self):
        with self.assertRaises(core.InputError):
            core.resolve_birth_time('1989-07-15 10:20', longitude=112.0)
        b = core.resolve_birth_time('1989-07-15 10:20', longitude=112.0, dst='clock')
        self.assertEqual(b.standard, datetime(1989, 7, 15, 9, 20))
        b2 = core.resolve_birth_time('1989-07-15 10:20', longitude=112.0, dst='standard')
        self.assertEqual(b2.standard, datetime(1989, 7, 15, 10, 20))
        with self.assertRaises(core.InputError):
            core.resolve_birth_time('1988-04-17 02:30', dst='clock')      # 钟面不存在
        with self.assertRaises(core.InputError):
            core.resolve_birth_time('1988-04-12 10:00')                    # 1988 开始日期有分歧
        b3 = core.resolve_birth_time('1993-07-01 10:00', dst='clock')
        self.assertEqual(b3.standard, datetime(1993, 7, 1, 10, 0))
        self.assertTrue(b3.warnings)

    def test_dst_periods_match_zoneinfo(self):
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo('Asia/Shanghai')
        except Exception:
            self.skipTest('zoneinfo / tzdata 不可用')
        d = datetime(1985, 1, 1, 12, 0)
        while d.year < 1993:
            with self.subTest(d=d):
                in_dst = d.replace(tzinfo=tz).utcoffset() == timedelta(hours=9)
                status = core.dst_status(d)
                if status != 'disputed':
                    self.assertEqual(status == 'in_dst', in_dst)
            d += timedelta(days=1)


# ================= 命令行冒烟 =================
class TestCli(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        return subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'bazi_chart.py'), *args],
                              capture_output=True, text=True, encoding='utf-8', env=env, timeout=180)

    def test_full_chart(self):
        p = self.run_cli('-d', '1991-10-05 08:20', '-g', '女', '--longitude', '113.3', '--as-of', '2026-09-16')
        self.assertEqual(p.returncode, 0, p.stderr)
        birth = core.resolve_birth_time('1991-10-05 08:20', longitude=113.3)
        chart = core.build_chart(birth, '女')
        cur = chart.dayun_at(datetime(2026, 9, 16))
        pillars = f'| 干支 | {chart.year_gz} | {chart.month_gz} | **{chart.day_gz}** | {chart.time_gz} |'
        for key in (pillars, f'当前大运：**{cur.gz}**', '当前流年：**丙午**', '节气月表', '流年作用关系完整表',
                    '交运)★', '🔥 S 级年份汇总', '✨ P 级年份汇总'):
            self.assertIn(key, p.stdout)

    def test_errors_exit_nonzero(self):
        for args in (('-d', '1991-10-05 08:20', '-g', '女', '-l', '不存在市'),
                     ('-d', '1989-07-15 10:20', '-g', '男'),
                     ('-d', '1980-12-17 12:00', '-g', '男', '--verify-events', '2022:子女', '--hour-candidates', 'xyz')):
            p = self.run_cli(*args)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertIn('错误', p.stderr)

    def test_verify_cli(self):
        p = self.run_cli('-d', '1980-12-17 12:00', '-g', '男', '--verify-events', '2022:子女:出生', '--as-of', '2026-09-16')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('不是时辰为真的概率', p.stdout)
        self.assertIn('最高分有并列', p.stdout)
        self.assertNotIn('最可能是真时辰', p.stdout)


if __name__ == '__main__':
    unittest.main()
