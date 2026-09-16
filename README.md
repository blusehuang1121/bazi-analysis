# bazi-analysis

八字（四柱命理）分析 skill —— 给 Claude 做命理咨询的后台引擎。

输出对象是命理师本人（不是命主），同时提供可直接发给命主的通俗表达。

## 安装

直接告诉 Claude Code：

```
请帮我安装 github.com/blusehuang1121/bazi-analysis 中的 Skills
```

安装依赖（脚本不会自动安装）：

```
pip install -r requirements.txt
```

改动脚本后跑测试：

```
python -m unittest discover -s tests
```

测试只验证历法口径、关系查表和评分规则按声明实现，不说明命理判断有效。

## 使用

安装好之后，把命主信息直接发给 Claude，会自动触发八章分析。

**方式一：完整出生信息**

```
1990年3月15日 14:30，北京，男
```

```
帮我看个八字：1983年11月21日 03:30 岳阳 男
```

**方式二：直接给排好的八字**

```
乾造：庚午、戊寅、丙子、辛卯，35岁，男
```

**方式三：贴一张八字截图**

直接把图片发过去即可。

**补充信息（可选）**

发命主信息时可以一起说当前关注的面向，分析会据此调整侧重：

```
1985年7月25日 23:30 长沙 女，最近想看下今年的运势和事业
```

## 文件结构

```
├── SKILL.md                       # 主入口
├── requirements.txt               # 依赖（lunar_python 锁定 1.4.8）
├── scripts/
│   ├── bazi_chart.py              # 排盘命令行 + markdown 输出
│   ├── bazi_core.py               # 历法、关系查表、信号、流年/流月、时辰反推（纯计算）
│   └── render_pdf.py              # 命主版 PDF 渲染（HTML → A4 PDF + 分页检查）
├── tests/
│   └── test_bazi.py               # 表驱动测试（节气/晚子时/交运/流年/关系/反推/输入）
├── templates/
│   └── client_report.html         # 命主版 PDF 模板（样式 + 章节骨架）
└── references/
    ├── methodology.md             # 内部推理流程
    ├── output_structure.md        # 各章节详细格式
    ├── style_guide.md             # 用词规范、禁用金句、特殊话题处理
    ├── blind_imagery.md           # 盲派象意参考表
    └── client_pdf.md              # 命主版 PDF 的章节映射、删改规则、分页修正
```

## License

[MIT](LICENSE)
