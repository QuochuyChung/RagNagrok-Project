"""
Phân tích file JSONL do LatencyTracker sinh ra.

Đọc các file trong ``profiling_results/`` rồi in bảng thống kê p50/p95/max
theo từng stage, giúp xác định chặng nào đang là bottleneck thật.

Cách dùng:
    python scripts/analyze_latency.py                    # tất cả các flow
    python scripts/analyze_latency.py --flow chat        # lọc 1 flow
    python scripts/analyze_latency.py --date 20260806    # lọc theo ngày
    python scripts/analyze_latency.py --top 5            # chỉ 5 stage chậm nhất
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Console Windows mặc định là cp1252 -> in tiếng Việt sẽ ném UnicodeEncodeError.
# Ép stdout sang UTF-8 để script chạy được ở cả PowerShell lẫn terminal Linux.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def percentile(values: list[float], pct: float) -> float:
    """Percentile theo kiểu nearest-rank — không nội suy, đủ dùng để so sánh."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(round(pct / 100 * len(ordered) + 0.5)) - 1, len(ordered) - 1)
    return ordered[max(idx, 0)]


def load_rows(directory: Path, flow: str | None, date: str | None) -> list[dict]:
    pattern = f"latency_{flow or '*'}_{date or '*'}.jsonl"
    rows: list[dict] = []
    for path in sorted(directory.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"  [bỏ qua] {path.name}:{line_no} không phải JSON hợp lệ")
    return rows


def report(rows: list[dict], top: int | None) -> None:
    by_flow: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_flow[row.get("flow", "unknown")].append(row)

    for flow, flow_rows in sorted(by_flow.items()):
        totals = [r["total_ms"] for r in flow_rows if "total_ms" in r]
        unattributed = [r.get("unattributed_ms", 0.0) for r in flow_rows]

        print()
        print("=" * 88)
        print(f"FLOW: {flow}   ({len(flow_rows)} lượt chạy)")
        print("=" * 88)
        if totals:
            print(
                f"  Tổng thời gian:  p50={statistics.median(totals):9.1f}ms  "
                f"p95={percentile(totals, 95):9.1f}ms  max={max(totals):9.1f}ms"
            )
        if unattributed:
            share = (statistics.median(unattributed) / statistics.median(totals) * 100) if totals and statistics.median(totals) else 0
            print(
                f"  Chưa được đo:    p50={statistics.median(unattributed):9.1f}ms "
                f"({share:.1f}% tổng thời gian)"
            )
            if share > 20:
                print("    ^ Trên 20% thời gian chưa nằm trong stage nào — còn điểm mù cần gắn đo thêm.")

        # Gom theo stage
        agg: dict[str, list[float]] = defaultdict(list)
        failures: dict[str, int] = defaultdict(int)
        for row in flow_rows:
            for stage in row.get("stages", []):
                agg[stage["stage"]].append(stage["duration_ms"])
                if stage.get("failed"):
                    failures[stage["stage"]] += 1

        if not agg:
            print("  (chưa có stage nào được ghi nhận)")
            continue

        ranked = sorted(agg.items(), key=lambda kv: statistics.median(kv[1]), reverse=True)
        if top:
            ranked = ranked[:top]

        print()
        print(f"  {'STAGE':<45} {'N':>5} {'p50':>10} {'p95':>10} {'max':>10}")
        print(f"  {'-' * 45} {'-' * 5} {'-' * 10} {'-' * 10} {'-' * 10}")
        for name, values in ranked:
            flag = f"  ⚠ {failures[name]} lỗi" if failures[name] else ""
            # Stage lồng nhau (có dấu chấm) thụt vào cho dễ đọc cây
            depth = name.count(".")
            label = ("  " * depth) + name.split(".")[-1] if depth else name
            print(
                f"  {label:<45} {len(values):>5} "
                f"{statistics.median(values):>9.1f}ms {percentile(values, 95):>9.1f}ms {max(values):>9.1f}ms{flag}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phân tích latency JSONL của LatencyTracker")
    parser.add_argument("--dir", default="profiling_results", help="Thư mục chứa file JSONL")
    parser.add_argument("--flow", help="Lọc theo flow: chat | document_ingest | document_process | tenant_provisioning | email_invitation")
    parser.add_argument("--date", help="Lọc theo ngày, định dạng YYYYMMDD")
    parser.add_argument("--top", type=int, help="Chỉ hiện N stage chậm nhất")
    args = parser.parse_args()

    directory = Path(args.dir)
    if not directory.exists():
        print(f"Không tìm thấy thư mục '{directory}'. Chạy hệ thống với ENABLE_LATENCY_PROFILING=true trước đã.")
        return

    rows = load_rows(directory, args.flow, args.date)
    if not rows:
        print(f"Không có dữ liệu trong '{directory}' khớp bộ lọc (flow={args.flow}, date={args.date}).")
        return

    report(rows, args.top)
    print()


if __name__ == "__main__":
    main()
