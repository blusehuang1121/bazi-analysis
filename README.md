# bazi-analysis

八字（四柱命理）分析 skill —— 给 Claude 做命理咨询的后台引擎。

输出对象是命理师本人（不是命主），同时提供可直接发给命主的通俗表达。

## 安装

### Claude Code

直接告诉 Claude Code：

```
请帮我安装 github.com/blusehuang1121/bazi-analysis 中的 Skills
```

### 命令行运行排盘脚本

```bash
pip install lunar_python
python scripts/bazi_chart.py -d "1983-11-21 03:30" -g 男 -l 岳阳
python scripts/bazi_chart.py --help    # 查看完整参数
```

## 文件结构

```
├── SKILL.md                       # 主入口
├── scripts/bazi_chart.py          # 排盘脚本（含经度时差 + 均时差校正）
└── references/
    ├── methodology.md             # 六步内部推理流程
    ├── output_structure.md        # 各章节详细格式
    └── style_guide.md             # 用词规范、禁用金句、特殊话题处理
```

## License

私人使用。
