# bazi-analysis

八字（四柱命理）分析 skill —— 为 Claude 设计的命理咨询后台引擎。

适合场景：给亲友看八字时把它当后台分析引擎，输入命主信息，输出结构化的八章分析报告。**输出对象是命理师本人**（不是命主），同时提供可直接发给命主的通俗表达。

## 特点

- **精确排盘**：Python 脚本计算四柱、大运、十神、藏干、起运。真太阳时校正含**经度时差 + 均时差**两层（约 80 个国内城市内置经度表）
- **三视角融合分析**：子平 / 盲派 / 现代心理学翻译
- **完整八章结构化报告**：
  1. 排盘信息
  2. 整体命局观察（格局/用神/人格画像）
  3. 生活面向分析（按年龄段展开）
  4. 当前大运分析
  5. 下一大运分析
  6. 整体画像与人生主线（散文，命主直接读）
  7. 重要年份与人生节点（窗口期式表达，非预言式）
  8. 今年的运势分析（含作用关系表 + 全年节奏建议）

## 设计原则

- **绝对不预言具体事件**（不说"X 岁会结婚""X 年会出车祸"等）
- **健康/重大风险用觉察式表达**，不直接预测疾病
- **女命分析无性别预设**（不用"克夫""旺夫"）
- **亲密关系问题不评判第三方**
- 命理黑话强制翻译为大白话（"显化""引动""应事"等禁用）
- 每个判断标注【稳】【分】【待】区分确定性

## 文件结构

```
bazi-analysis/
├── SKILL.md                       # 主入口
├── scripts/
│   └── bazi_chart.py              # 排盘脚本
└── references/
    ├── methodology.md             # 六步内部推理流程
    ├── output_structure.md        # 各章节详细格式
    └── style_guide.md             # 用词规范、禁用金句、特殊话题处理
```

## 使用方法

### 在 Claude Code / Claude.ai 中作为 skill

把整个仓库目录作为 skill 文件夹安装即可。

如需打包成 `.skill` 文件：

```bash
# 在仓库父目录下执行（假设仓库名是 bazi-analysis）
python -c "
import zipfile, pathlib
src = pathlib.Path('bazi-analysis')
with zipfile.ZipFile('bazi-analysis.skill', 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in src.rglob('*'):
        if f.is_file() and '.git' not in f.parts and '__pycache__' not in f.parts:
            zf.write(f, f.relative_to(src.parent))
"
```

### 直接运行排盘脚本（命令行传参，无需改代码）

```bash
pip install lunar_python

# 基本用法
python scripts/bazi_chart.py -d "1983-11-21 03:30" -g 男 -l 岳阳

# 直接指定经度（优先级高于 -l）
python scripts/bazi_chart.py -d "1990-03-15 14:30" -g 女 --longitude 121.5

# 不指定出生地 → 使用北京时间，不做校正
python scripts/bazi_chart.py -d "1990-03-15 14:30" -g 男

# 查看帮助
python scripts/bazi_chart.py --help
```

**参数：**

| 参数 | 必填 | 说明 |
|---|---|---|
| `-d / --datetime` | ✓ | 出生日期时间，格式 `"YYYY-MM-DD HH:MM"`（北京时间） |
| `-g / --gender` | ✓ | 性别，`男` 或 `女` |
| `-l / --location` |  | 出生城市（中文）。不在内置表中时仅应用均时差 |
| `--longitude` |  | 出生地经度（度），优先级高于 `--location` |

输出 markdown 格式的排盘结果（基本信息、四柱八字、五行分布、大运排布、当前位置）。

## 真太阳时算法说明

```
真太阳时 = 北京时间 − 经度时差 + 均时差
```

- **经度时差**：(120 − 出生地经度) × 4 分钟
- **均时差**（Equation of Time）：基于 Spencer 1971 简化公式，一年内在约 −14 ~ +16 分钟之间变化（11 月达到正向最大，2 月达到负向最大）

## 约定

- 晚子时（23:00-23:59）按方式 A 处理：日柱不换日，时柱按当天日干起子时
- 出生地不在经度表中时仅应用均时差
- 没有提供出生地时使用北京时间（不做任何校正）

## License

私人使用。
