"""
Latency profiling utilities.

Cung cấp ``LatencyTracker`` để đo thời gian từng chặng (stage) trong các
pipeline dài của hệ thống: tạo tenant, ingest document, và chat RAG.

Xem ``app/profiling/latency_tracker.py`` để biết cách dùng.
"""

from app.profiling.latency_tracker import LatencyTracker, StageTiming

__all__ = ["LatencyTracker", "StageTiming"]
