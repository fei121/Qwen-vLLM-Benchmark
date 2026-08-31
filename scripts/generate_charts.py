#!/usr/bin/env python3
"""Generate publication-ready SVG charts from data/benchmark.csv.

No third-party Python dependencies are required. The output is deterministic,
keeps a pure-white canvas, and remains editable as SVG text.

Rows may describe different models and card counts (e.g. a 3B-active MoE model
on one/two GPUs vs a dense model on one GPU). Charts that reason about "more
cards" compare the same model across card counts; the model-selection chart
compares models on the same card count.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "benchmark.csv"
ASSETS = ROOT / "assets"

INK = "#0F172A"
MUTED = "#64748B"
GRID = "#E2E8F0"
BLUE = "#2563EB"
BLUE_LIGHT = "#DBEAFE"
ORANGE = "#F97316"
ORANGE_LIGHT = "#FFEDD5"
GREEN = "#059669"
GREEN_LIGHT = "#D1FAE5"
RED = "#DC2626"
TEAL = "#0D9488"
TEAL_LIGHT = "#CCFBF1"
WHITE = "#FFFFFF"
FONT = "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif"

# Short labels used across charts. "MoE" is inferred from the model id (A3B).
MODEL35 = "qwen3.6-35b-a3b-fp8"   # 35B total / 3B active (MoE)
MODEL27 = "qwen3.8-27b-fp8"       # dense 27B FP8
L35 = "35B-A3B"
L27 = "27B"


def load_rows() -> list[dict[str, str]]:
    with DATA.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise ValueError(f"expected at least 2 configurations, got {len(rows)}")
    return rows


def n(row: dict[str, str], key: str) -> float:
    return float(row[key])


def pct(old: float, new: float) -> float:
    return (new / old - 1.0) * 100.0


class SVG:
    def __init__(self, width: int, height: int, title: str, description: str):
        self.width = width
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f"<title id=\"title\">{escape(title)}</title>",
            f"<desc id=\"desc\">{escape(description)}</desc>",
            f'<rect width="{width}" height="{height}" fill="{WHITE}"/>',
        ]

    def rect(self, x, y, w, h, fill=WHITE, stroke="none", radius=0, stroke_width=1):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )

    def line(self, x1, y1, x2, y2, stroke=GRID, width=1, dash=None):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>'
        )

    def circle(self, cx, cy, r, fill, stroke=WHITE, stroke_width=3):
        self.parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )

    def text(self, x, y, value, size=16, fill=INK, weight=400, anchor="start", opacity=1.0):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" opacity="{opacity}">{escape(str(value))}</text>'
        )

    def finish(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([*self.parts, "</svg>", ""]), encoding="utf-8")


def title_block(svg: SVG, title: str, subtitle: str):
    svg.text(64, 62, title, size=30, weight=750)
    svg.text(64, 94, subtitle, size=15, fill=MUTED)
    svg.line(64, 116, svg.width - 64, 116, stroke=GRID)


def legend(svg: SVG, x: int, y: int, items: list[tuple[str, str]], gap: int = 150):
    cx = x
    for label, color in items:
        svg.circle(cx, y - 5, 6, color, stroke=color, stroke_width=0)
        svg.text(cx + 14, y, label, size=14, fill=MUTED)
        cx += gap


# --- single vs dual-card charts (same model: 35B-A3B) ----------------------
SINGLE_LABEL = f"{L35} ×1"
DUAL_LABEL = f"{L35} ×2"
SINGLE_BAR = f"{L35} 单卡"
DUAL_BAR = f"{L35} 双卡"


def mini_bar_panel(svg: SVG, x: int, y: int, w: int, h: int, label: str,
                   values: tuple[float, float], formatter, change_text: str,
                   higher_is_better: bool = True):
    svg.rect(x, y, w, h, fill=WHITE, stroke=GRID, radius=8)
    svg.text(x + 24, y + 38, label, size=17, weight=650)
    svg.text(x + w - 24, y + 38, change_text, size=15,
             fill=GREEN if higher_is_better else GREEN, weight=700, anchor="end")
    max_v = max(values) * 1.16
    baseline = y + h - 54
    chart_top = y + 78
    chart_h = baseline - chart_top
    for frac in (0, 0.5, 1):
        gy = baseline - chart_h * frac
        svg.line(x + 28, gy, x + w - 28, gy, stroke=GRID, dash="3 5" if frac else None)
    bar_w = 72
    centers = (x + w * 0.35, x + w * 0.69)
    for idx, (cx, value, color) in enumerate(zip(centers, values, (BLUE, ORANGE))):
        bh = chart_h * value / max_v
        svg.rect(cx - bar_w / 2, baseline - bh, bar_w, bh, fill=color, radius=4)
        svg.text(cx, baseline - bh - 13, formatter(value), size=17, weight=700, anchor="middle")
        svg.text(cx, baseline + 28, SINGLE_BAR if idx == 0 else DUAL_BAR, size=14, fill=MUTED, anchor="middle")


def grouped_latency_panel(svg: SVG, x: int, y: int, w: int, h: int, name: str,
                          keys: tuple[str, str, str], rows: tuple[dict, dict],
                          log_scale: bool = False):
    svg.rect(x, y, w, h, fill=WHITE, stroke=GRID, radius=8)
    svg.text(x + 22, y + 34, name, size=17, weight=650)
    a, b = rows
    values = [n(row, key) for key in keys for row in (a, b)]
    chart_left, chart_right = x + 58, x + w - 22
    chart_top, chart_bottom = y + 65, y + h - 50
    if log_scale:
        low = 100.0
        high = 10000.0
        ticks = [100, 1000, 10000]
        scale = lambda v: chart_bottom - (math.log10(v) - math.log10(low)) / (math.log10(high) - math.log10(low)) * (chart_bottom - chart_top)
    else:
        low = 0.0
        high = math.ceil(max(values) * 1.16 / 10) * 10
        ticks = [0, high / 2, high]
        scale = lambda v: chart_bottom - (v - low) / (high - low) * (chart_bottom - chart_top)
    for tick in ticks:
        ty = scale(tick)
        svg.line(chart_left, ty, chart_right, ty, stroke=GRID, dash="3 5")
        tick_text = f"{tick/1000:g}s" if log_scale and tick >= 1000 else f"{tick:g}"
        svg.text(chart_left - 9, ty + 4, tick_text, size=11, fill=MUTED, anchor="end")
    groups = ("均值", "中位数", "P99")
    group_w = (chart_right - chart_left) / 3
    bar_w = min(28, group_w * 0.22)
    for gi, (group, key) in enumerate(zip(groups, keys)):
        center = chart_left + group_w * (gi + 0.5)
        for ri, (row, color) in enumerate(zip((a, b), (BLUE, ORANGE))):
            value = n(row, key)
            bx = center + (-bar_w - 2 if ri == 0 else 2)
            by = scale(value)
            svg.rect(bx, by, bar_w, chart_bottom - by, fill=color, radius=3)
            label = f"{value/1000:.2f}s" if value >= 1000 else f"{value:.1f}"
            svg.text(bx + bar_w / 2, by - 8, label, size=11, weight=650, anchor="middle")
        svg.text(center, chart_bottom + 27, group, size=13, fill=MUTED, anchor="middle")
    unit = "ms · 对数轴" if log_scale else "ms"
    svg.text(x + w - 22, y + 34, unit, size=12, fill=MUTED, anchor="end")


def chart_throughput(a, b):
    svg = SVG(1200, 650, "吞吐与完成时间对比", "同为35B-A3B模型，双卡提升吞吐约38%，测试时长缩短约28%。")
    title_block(svg, "同一工作量下，双卡把服务能力提升约四成", "35B-A3B · 300 请求 · 并发 20 · 每请求 4,096 输入 + 1,024 输出 tokens")
    mini_bar_panel(
        svg, 64, 154, 338, 420, "输出吞吐 · tok/s",
        (n(a, "output_throughput_tps"), n(b, "output_throughput_tps")),
        lambda v: f"{v:,.0f}", f"+{pct(n(a, 'output_throughput_tps'), n(b, 'output_throughput_tps')):.1f}%"
    )
    mini_bar_panel(
        svg, 431, 154, 338, 420, "请求吞吐 · req/s",
        (n(a, "request_throughput_rps"), n(b, "request_throughput_rps")),
        lambda v: f"{v:.2f}", f"+{pct(n(a, 'request_throughput_rps'), n(b, 'request_throughput_rps')):.1f}%"
    )
    mini_bar_panel(
        svg, 798, 154, 338, 420, "完成时间 · 秒",
        (n(a, "duration_s"), n(b, "duration_s")),
        lambda v: f"{v:.1f}", f"{pct(n(a, 'duration_s'), n(b, 'duration_s')):.1f}%", higher_is_better=False
    )
    svg.text(64, 620, "值越高越好：吞吐   ·   值越低越好：完成时间", size=13, fill=MUTED)
    svg.finish(ASSETS / "throughput.svg")


def chart_latency(a, b):
    svg = SVG(1200, 760, "延迟分布对比", "双卡显著降低TTFT长尾，并稳定改善TPOT；ITL P99改善较小。")
    title_block(svg, "双卡显著收敛首 token 长尾", "35B-A3B 模型 · TTFT 使用对数轴；TPOT 与 ITL 使用线性轴。柱顶标注原始值")
    legend(svg, 850, 91, [(SINGLE_LABEL, BLUE), (DUAL_LABEL, ORANGE)])
    grouped_latency_panel(svg, 64, 154, 338, 520, "TTFT · 首 token 延迟", ("ttft_mean_ms", "ttft_median_ms", "ttft_p99_ms"), (a, b), True)
    grouped_latency_panel(svg, 431, 154, 338, 520, "TPOT · 每输出 token", ("tpot_mean_ms", "tpot_median_ms", "tpot_p99_ms"), (a, b), False)
    grouped_latency_panel(svg, 798, 154, 338, 520, "ITL · token 间隔", ("itl_mean_ms", "itl_median_ms", "itl_p99_ms"), (a, b), False)
    svg.text(64, 718, "P99 TTFT：6.28s → 1.85s（−70.6%）   ·   P99 ITL：123.88ms → 115.87ms（−6.5%）", size=14, fill=MUTED)
    svg.finish(ASSETS / "latency.svg")


def chart_efficiency(a, b):
    out_speedup = n(b, "output_throughput_tps") / n(a, "output_throughput_tps")
    efficiency = out_speedup / n(b, "gpu_count")
    gpu_s_single = n(a, "gpu_count") * n(a, "duration_s") / n(a, "total_generated_tokens") * 1_000_000
    gpu_s_dual = n(b, "gpu_count") * n(b, "duration_s") / n(b, "total_generated_tokens") * 1_000_000
    svg = SVG(1200, 650, "扩展效率与资源成本", "双卡加速1.384倍，并行效率69.2%，每百万输出token的GPU时间增加44.5%。")
    title_block(svg, "双卡买来容量与尾延迟，但不是线性扩展", "35B-A3B 模型 · 加速比衡量完成同一工作量的速度；GPU·秒是资源占用代理，不等同于电费")

    # Speedup scale
    svg.text(64, 167, "输出吞吐加速比", size=17, weight=650)
    sx0, sx1, sy = 64, 720, 235
    svg.line(sx0, sy, sx1, sy, stroke=GRID, width=8)
    for val in (0, 0.5, 1, 1.5, 2):
        px = sx0 + (sx1 - sx0) * val / 2
        svg.line(px, sy - 8, px, sy + 8, stroke=MUTED)
        svg.text(px, sy + 33, f"{val:g}×", size=12, fill=MUTED, anchor="middle")
    actual_x = sx0 + (sx1 - sx0) * out_speedup / 2
    svg.line(sx0, sy, actual_x, sy, stroke=ORANGE, width=8)
    svg.circle(actual_x, sy, 10, ORANGE)
    svg.text(actual_x, sy - 25, f"实测 {out_speedup:.3f}×", size=17, weight=750, anchor="middle")
    svg.text(sx1, sy - 25, "理想 2.000×", size=14, fill=MUTED, anchor="end")

    # Efficiency callout
    svg.rect(785, 154, 351, 142, fill=ORANGE_LIGHT, stroke="none", radius=8)
    svg.text(809, 188, "双卡并行效率", size=15, fill=MUTED, weight=600)
    svg.text(809, 247, f"{efficiency*100:.1f}%", size=48, fill=ORANGE, weight=800)
    svg.text(809, 275, "= 1.384× ÷ 2 GPUs", size=13, fill=MUTED)

    # GPU seconds bars
    svg.text(64, 360, "每 100 万输出 tokens 的 GPU 时间", size=17, weight=650)
    max_v = max(gpu_s_single, gpu_s_dual) * 1.12
    bar_x, bar_w = 250, 730
    for idx, (label, value, color) in enumerate((("单卡", gpu_s_single, BLUE), ("双卡", gpu_s_dual, ORANGE))):
        y = 407 + idx * 82
        svg.text(64, y + 23, label, size=15, fill=MUTED)
        svg.rect(bar_x, y, bar_w, 32, fill="#F1F5F9", radius=4)
        value_w = bar_w * value / max_v
        svg.rect(bar_x, y, value_w, 32, fill=color, radius=4)
        svg.text(bar_x + value_w - 12, y + 22, f"{value:.1f} GPU·s", size=14, fill=WHITE, weight=700, anchor="end")
    increase = pct(gpu_s_single, gpu_s_dual)
    svg.rect(1003, 406, 133, 115, fill=GREEN_LIGHT if increase < 0 else ORANGE_LIGHT, radius=8)
    svg.text(1069, 437, "资源占用", size=13, fill=MUTED, anchor="middle")
    svg.text(1069, 477, f"+{increase:.1f}%", size=25, fill=ORANGE, weight=800, anchor="middle")
    svg.text(1069, 502, "双卡 vs 单卡", size=12, fill=MUTED, anchor="middle")
    svg.text(64, 600, "决策含义：双卡适合追求更高容量与更低 P99；单卡的单位 GPU 产出更高。", size=15, fill=INK, weight=600)
    svg.finish(ASSETS / "efficiency.svg")


def chart_speculative(a, b):
    svg = SVG(1200, 620, "投机解码接受率对比", "双卡运行的总体、位置0和位置1接受率均略高。")
    title_block(svg, "双卡运行的投机接受率高 3.07 个百分点", "35B-A3B 模型 · 接受率变化可能受调度与请求序列影响；需要重复试验和关闭投机解码的消融对照")
    legend(svg, 850, 91, [(SINGLE_LABEL, BLUE), (DUAL_LABEL, ORANGE)])
    metrics = [
        ("总体接受率", "spec_acceptance_rate_pct"),
        ("Position 0", "spec_position_0_pct"),
        ("Position 1", "spec_position_1_pct"),
    ]
    chart_left, chart_right = 92, 930
    chart_top, chart_bottom = 170, 500
    low, high = 55, 85
    for tick in (55, 65, 75, 85):
        ty = chart_bottom - (tick - low) / (high - low) * (chart_bottom - chart_top)
        svg.line(chart_left, ty, chart_right, ty, stroke=GRID, dash="3 5")
        svg.text(chart_left - 12, ty + 4, f"{tick}%", size=12, fill=MUTED, anchor="end")
    group_w = (chart_right - chart_left) / 3
    for gi, (label, key) in enumerate(metrics):
        center = chart_left + group_w * (gi + 0.5)
        for ri, (row, color) in enumerate(((a, BLUE), (b, ORANGE))):
            value = n(row, key)
            bw = 62
            bx = center + (-bw - 5 if ri == 0 else 5)
            by = chart_bottom - (value - low) / (high - low) * (chart_bottom - chart_top)
            svg.rect(bx, by, bw, chart_bottom - by, fill=color, radius=4)
            svg.text(bx + bw / 2, by - 10, f"{value:.2f}%", size=13, weight=700, anchor="middle")
        svg.text(center, chart_bottom + 31, label, size=14, fill=MUTED, anchor="middle")
    svg.rect(972, 170, 164, 330, fill="#F8FAFC", stroke=GRID, radius=8)
    svg.text(992, 205, "接受长度", size=15, weight=650)
    svg.text(992, 255, f"{n(a, 'spec_acceptance_length'):.2f}", size=32, fill=BLUE, weight=800)
    svg.text(992, 279, "单卡", size=13, fill=MUTED)
    svg.text(992, 337, f"{n(b, 'spec_acceptance_length'):.2f}", size=32, fill=ORANGE, weight=800)
    svg.text(992, 361, "双卡", size=13, fill=MUTED)
    svg.line(992, 390, 1116, 390, stroke=GRID)
    svg.text(992, 426, "Draft 长度", size=13, fill=MUTED)
    svg.text(992, 458, "2.00 tokens", size=18, fill=INK, weight=700)
    svg.text(64, 578, "总体接受率：69.28% → 72.35%   ·   接受 tokens：178,421 → 181,636", size=14, fill=MUTED)
    svg.finish(ASSETS / "speculative.svg")


# --- model comparison chart (different models, same workload) -------------
def tri_bar_panel(svg: SVG, x: int, y: int, w: int, h: int, name: str, unit: str,
                  items: list[tuple[str, float, str]], formatter):
    svg.rect(x, y, w, h, fill=WHITE, stroke=GRID, radius=8)
    svg.text(x + 22, y + 34, name, size=16, weight=650)
    svg.text(x + w - 22, y + 34, unit, size=12, fill=MUTED, anchor="end")
    values = [v for _, v, _ in items]
    chart_left, chart_right = x + 46, x + w - 26
    chart_top, chart_bottom = y + 62, y + h - 46
    max_v = max(values) * 1.16
    for frac in (0, 0.5, 1):
        gy = chart_bottom - (chart_bottom - chart_top) * frac
        svg.line(chart_left, gy, chart_right, gy, stroke=GRID, dash="3 5" if frac else None)
    group_w = (chart_right - chart_left) / 3
    bar_w = min(72, group_w * 0.5)
    for gi, (label, value, color) in enumerate(items):
        center = chart_left + group_w * (gi + 0.5)
        bh = (chart_bottom - chart_top) * value / max_v
        svg.rect(center - bar_w / 2, chart_bottom - bh, bar_w, bh, fill=color, radius=4)
        svg.text(center, chart_bottom - bh - 12, formatter(value), size=15, weight=700, anchor="middle")
        svg.text(center, chart_bottom + 24, label, size=13, fill=MUTED, anchor="middle")


def chart_models(m27, m35_1x, m35_2x):
    gpu_s = lambda row: n(row, "gpu_count") * n(row, "duration_s") / n(row, "total_generated_tokens") * 1_000_000
    svg = SVG(1200, 800, "模型与卡数对比", "同为单卡时，3B激活的MoE 35B稠密27B；加第二张卡进一步缩短尾延迟。")
    title_block(svg, "选对模型，比加一张卡更有效", "300 请求 · 并发 20 · 每请求 4,096 输入 + 1,024 输出 tokens · 左→右：27B×1 · 35B-A3B×1 · 35B-A3B×2")
    legend(svg, 810, 91, [("27B ×1", TEAL), ("35B-A3B ×1", BLUE), ("35B-A3B ×2", ORANGE)], gap=122)

    tri_bar_panel(svg, 64, 154, 538, 258, "输出吞吐", "tok/s",
                  [(f"{L27} ×1", n(m27, "output_throughput_tps"), TEAL),
                   (f"{L35} ×1", n(m35_1x, "output_throughput_tps"), BLUE),
                   (f"{L35} ×2", n(m35_2x, "output_throughput_tps"), ORANGE)],
                  lambda v: f"{v:,.0f}")
    tri_bar_panel(svg, 628, 154, 508, 258, "平均 TTFT", "ms",
                  [(f"{L27} ×1", n(m27, "ttft_mean_ms"), TEAL),
                   (f"{L35} ×1", n(m35_1x, "ttft_mean_ms"), BLUE),
                   (f"{L35} ×2", n(m35_2x, "ttft_mean_ms"), ORANGE)],
                  lambda v: f"{v:,.0f}")
    tri_bar_panel(svg, 64, 438, 538, 258, "P99 TTFT", "ms",
                  [(f"{L27} ×1", n(m27, "ttft_p99_ms"), TEAL),
                   (f"{L35} ×1", n(m35_1x, "ttft_p99_ms"), BLUE),
                   (f"{L35} ×2", n(m35_2x, "ttft_p99_ms"), ORANGE)],
                  lambda v: f"{v:,.0f}")
    tri_bar_panel(svg, 628, 438, 508, 258, "GPU·秒 / 百万输出 tokens", "资源占用",
                  [(f"{L27} ×1", gpu_s(m27), TEAL),
                   (f"{L35} ×1", gpu_s(m35_1x), BLUE),
                   (f"{L35} ×2", gpu_s(m35_2x), ORANGE)],
                  lambda v: f"{v:,.0f}")
    ratio = n(m35_1x, "output_throughput_tps") / n(m27, "output_throughput_tps")
    svg.text(64, 734, f"单卡选型：35B-A3B 以约 3B 激活参数量，把 27B 稠密模型的输出吞吐提升约 {ratio:.2f}×，首 token 延迟拉低约 2–3 倍。", size=15, fill=INK, weight=600)
    svg.finish(ASSETS / "model-comparison.svg")


def row_for(model: str, gpu_count: int) -> dict[str, str]:
    for r in ROWS:
        if r["model"] == model and int(r["gpu_count"]) == gpu_count:
            return r
    raise ValueError(f"no row for model={model!r} gpu_count={gpu_count}")


def validate(rows: list[dict[str, str]]):
    for r in rows:
        assert int(n(r, "total_input_tokens") / n(r, "successful_requests")) == 4096
        assert int(n(r, "total_generated_tokens") / n(r, "successful_requests")) == 1024
        assert abs(n(r, "output_throughput_tps") - n(r, "total_generated_tokens") / n(r, "duration_s")) < 0.1
    single = row_for(MODEL35, 1)
    dual = row_for(MODEL35, 2)
    assert abs(pct(n(single, "duration_s"), n(dual, "duration_s")) - (-27.7582)) < 0.01
    assert abs(pct(n(single, "ttft_p99_ms"), n(dual, "ttft_p99_ms")) - (-70.5547)) < 0.01
    assert abs((n(dual, "output_throughput_tps") / n(single, "output_throughput_tps") / 2) - 0.6921) < 0.001
    m27 = row_for(MODEL27, 1)
    assert abs(n(single, "output_throughput_tps") / n(m27, "output_throughput_tps") - 2.1609) < 0.02


ROWS = load_rows()


def main():
    a = row_for(MODEL35, 1)   # 35B-A3B, single card
    b = row_for(MODEL35, 2)   # 35B-A3B, dual card
    m27 = row_for(MODEL27, 1)  # 27B dense, single card
    validate(ROWS)
    chart_throughput(a, b)
    chart_latency(a, b)
    chart_efficiency(a, b)
    chart_speculative(a, b)
    chart_models(m27, a, b)
    print("Generated 5 SVG charts in assets/; all numerical checks passed.")


if __name__ == "__main__":
    main()
