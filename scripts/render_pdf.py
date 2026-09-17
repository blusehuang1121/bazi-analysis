"""
命主版 PDF 渲染脚本（HTML → PDF）

用法：
    python render_pdf.py 命主档案/{标识}_命盘分析_命主版.html
    python render_pdf.py report.html -o out.pdf --preview 预览目录

流程：
1. 检查 HTML 里是否还有没替换的模板占位符 {{...}}（有则中止）
2. 调用本机 Edge / Chrome 无头打印成 PDF（A4，页边距由模板里的 @page 决定，不带页眉页脚）
3. 分页检查：列出每页首行，标出"溢出尾页"（除封面外正文过短的页，通常是上一章多出来的几行或一张被挤下来的表）
4. 可选 --preview：把每页渲染成 PNG，并拼 3 张缩略总览图，方便肉眼检查

依赖：Edge 或 Chrome（必需）；pypdfium2 + Pillow（分页检查与预览，缺失时跳过）
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Windows 终端默认 GBK，强制 UTF-8 输出（同 bazi_chart.py）；sys.exit 的报错走 stderr，也要一起改
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

# 正文字数低于此值的非封面页，视为溢出尾页
SHORT_PAGE_CHARS = 300

BROWSER_CANDIDATES = [
    # Windows
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
    # macOS
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
]
BROWSER_NAMES = ['msedge', 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge']


def find_browser(explicit=None):
    if explicit:
        return explicit if Path(explicit).exists() else None
    for p in BROWSER_CANDIDATES:
        if p and Path(p).exists():
            return p
    for name in BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def check_placeholders(html_path):
    text = Path(html_path).read_text(encoding='utf-8')
    return sorted(set(re.findall(r'\{\{[^{}]{0,40}\}\}', text)))


def _pdf_signature(pdf_path):
    p = Path(pdf_path)
    if not p.exists():
        return None
    st = p.stat()
    return (st.st_mtime_ns, st.st_size)


def print_to_pdf(browser, html_path, pdf_path, wait_seconds=90):
    # Edge 的启动器可能在 PDF 真正写完之前就退出：必须等到"比打印前新、且大小稳定"的文件，
    # 否则会读到上一次的旧 PDF（分页检查和预览全是旧内容）或误报没生成
    before = _pdf_signature(pdf_path)
    user_data = tempfile.mkdtemp(prefix='bazi_pdf_')
    try:
        cmd = [
            browser, '--headless=new', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', f'--user-data-dir={user_data}',
            '--no-pdf-header-footer', f'--print-to-pdf={pdf_path}',
            Path(html_path).resolve().as_uri(),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=180)
        deadline = time.monotonic() + wait_seconds
        last = None
        while time.monotonic() < deadline:
            sig = _pdf_signature(pdf_path)
            if sig and sig != before and sig[1] > 0:
                if sig == last:
                    return
                last = sig
            time.sleep(1)
    finally:
        shutil.rmtree(user_data, ignore_errors=True)
    sys.exit(f'错误：浏览器没有生成新的 PDF（等待 {wait_seconds} 秒）。\n{result.stderr[-1500:]}')


def page_texts(pdf_path):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    pdf = pdfium.PdfDocument(pdf_path)
    texts = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
    pdf.close()
    return texts


def layout_report(pdf_path):
    texts = page_texts(pdf_path)
    if texts is None:
        print('- 未安装 pypdfium2，跳过分页检查（pip install pypdfium2）')
        return
    print(f'- 共 {len(texts)} 页')
    print()
    print('| 页 | 字数 | 首行 | 末行 | 检查 |')
    print('|---|---|---|---|---|')
    short = []
    for i, t in enumerate(texts, 1):
        lines = [ln.strip() for ln in t.replace('\r', '').split('\n') if ln.strip()]
        n = len(re.sub(r'\s', '', t))
        first = lines[0][:24] if lines else ''
        last = lines[-1][-24:] if lines else ''
        flag = ''
        if i > 1 and n < SHORT_PAGE_CHARS:
            flag = '⚠️ 溢出尾页'
            short.append(i)
        print(f'| {i} | {n} | {first} | {last} | {flag} |')
    print()
    if short:
        print(f'⚠️ 第 {"、".join(map(str, short))} 页正文过短，多半是上一页溢出。修法见 references/client_pdf.md「分页修正」。')
    else:
        print('✓ 无溢出尾页')


def render_previews(pdf_path, out_dir):
    try:
        import pypdfium2 as pdfium
        from PIL import Image
    except ImportError:
        print('- 未安装 pypdfium2 / Pillow，跳过预览图')
        return
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(pdf_path)
    images = []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=1.1).to_pil()
        img.save(out / f'p{i + 1:02d}.png')
        images.append(img)
    pdf.close()
    # 缩略总览：每张 5 页
    w, h = images[0].size
    tw, th = int(w * 0.42), int(h * 0.42)
    sheets = []
    for k in range(0, len(images), 5):
        group = images[k:k + 5]
        sheet = Image.new('RGB', (tw * len(group) + 10 * (len(group) - 1), th), 'white')
        for j, im in enumerate(group):
            sheet.paste(im.resize((tw, th)), (j * (tw + 10), 0))
        name = out / f'sheet{k // 5 + 1}.png'
        sheet.save(name)
        sheets.append(name.name)
    print(f'- 预览图：{out}（逐页 p01.png…，总览 {"、".join(sheets)}）')


def parse_args():
    parser = argparse.ArgumentParser(
        description='命主版 PDF 渲染 — 把按 templates/client_report.html 填好的 HTML 打印成 A4 PDF',
        epilog=(
            '示例:\n'
            '  python render_pdf.py 命主档案/{标识}_命盘分析_命主版.html\n'
            '  python render_pdf.py report.html -o out.pdf --preview preview/'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('html', help='填好内容的命主版 HTML')
    parser.add_argument('-o', '--output', default=None, help='输出 PDF 路径，默认与 HTML 同名同目录')
    parser.add_argument('--preview', default=None, help='把每页渲染成 PNG 存到此目录（含缩略总览图）')
    parser.add_argument('--browser', default=None, help='手动指定 Edge/Chrome 可执行文件路径')
    parser.add_argument('--allow-placeholders', action='store_true',
                        help='允许残留 {{占位符}}（仅用于预览模板本身）')
    return parser.parse_args()


def main():
    args = parse_args()
    html_path = Path(args.html)
    if not html_path.exists():
        sys.exit(f'错误：找不到 HTML 文件 {html_path}')
    pdf_path = Path(args.output) if args.output else html_path.with_suffix('.pdf')
    pdf_path = pdf_path.resolve()

    leftovers = check_placeholders(html_path)
    if leftovers and not args.allow_placeholders:
        sys.exit('错误：HTML 里还有没替换的模板占位符：\n  ' + '\n  '.join(leftovers[:20]))

    browser = find_browser(args.browser)
    if not browser:
        sys.exit('错误：找不到 Edge 或 Chrome。用 --browser 指定浏览器可执行文件路径。')

    print('# 命主版 PDF 渲染')
    print()
    print(f'- 浏览器：{browser}')
    print_to_pdf(browser, html_path, str(pdf_path))
    print(f'- 输出：{pdf_path}（{pdf_path.stat().st_size // 1024} KB）')
    layout_report(str(pdf_path))
    if args.preview:
        render_previews(str(pdf_path), args.preview)


if __name__ == '__main__':
    main()
