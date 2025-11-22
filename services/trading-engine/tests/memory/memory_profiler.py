#!/usr/bin/env python3
"""
Memory Leak Detection and Profiling
Purpose: Monitor memory usage and detect potential leaks in the Trading Engine

Usage:
  python memory_profiler.py          # Profile current session
  python memory_profiler.py --continuous  # Continuous monitoring
"""

import tracemalloc
import gc
import psutil
import time
import sys
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MemorySnapshot:
    """Memory usage snapshot"""
    timestamp: datetime
    rss_mb: float          # Resident Set Size
    vms_mb: float          # Virtual Memory Size
    percent: float         # Memory percent
    objects_count: int     # Number of Python objects
    top_allocations: List[tuple]


class MemoryProfiler:
    """Memory profiler and leak detector"""

    def __init__(self):
        self.snapshots: List[MemorySnapshot] = []
        self.process = psutil.Process()
        self.baseline_memory = None

    def start_tracking(self):
        """Start memory tracking"""
        tracemalloc.start(10)  # Track top 10 frames
        self.baseline_memory = self._get_memory_usage()
        print(f"✅ Memory tracking started")
        print(f"   Baseline: {self.baseline_memory:.2f} MB\n")

    def take_snapshot(self) -> MemorySnapshot:
        """Take a memory snapshot"""
        # Force garbage collection
        gc.collect()

        # Get process memory info
        mem_info = self.process.memory_info()
        mem_percent = self.process.memory_percent()

        # Get Python object counts
        objects_count = len(gc.get_objects())

        # Get top memory allocations
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')[:10]
        top_allocations = [
            (stat.filename, stat.lineno, stat.size / 1024 / 1024)  # Convert to MB
            for stat in top_stats
        ]

        snapshot_data = MemorySnapshot(
            timestamp=datetime.now(),
            rss_mb=mem_info.rss / 1024 / 1024,
            vms_mb=mem_info.vms / 1024 / 1024,
            percent=mem_percent,
            objects_count=objects_count,
            top_allocations=top_allocations
        )

        self.snapshots.append(snapshot_data)
        return snapshot_data

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        return self.process.memory_info().rss / 1024 / 1024

    def detect_leaks(self) -> Dict:
        """Detect potential memory leaks"""
        if len(self.snapshots) < 2:
            return {"leak_detected": False, "message": "Need at least 2 snapshots"}

        # Compare first and last snapshot
        first = self.snapshots[0]
        last = self.snapshots[-1]

        memory_increase = last.rss_mb - first.rss_mb
        object_increase = last.objects_count - first.objects_count
        percent_increase = (memory_increase / first.rss_mb) * 100

        # Check for sustained growth
        leak_detected = False
        if len(self.snapshots) >= 5:
            # Check if memory is consistently growing
            memory_trend = []
            for i in range(1, len(self.snapshots)):
                delta = self.snapshots[i].rss_mb - self.snapshots[i-1].rss_mb
                memory_trend.append(delta)

            # If more than 70% of snapshots show growth, potential leak
            growth_count = sum(1 for delta in memory_trend if delta > 1.0)  # 1MB threshold
            if growth_count > len(memory_trend) * 0.7:
                leak_detected = True

        return {
            "leak_detected": leak_detected,
            "memory_increase_mb": memory_increase,
            "memory_increase_percent": percent_increase,
            "object_increase": object_increase,
            "duration_seconds": (last.timestamp - first.timestamp).total_seconds(),
            "snapshots_analyzed": len(self.snapshots)
        }

    def print_snapshot(self, snapshot: MemorySnapshot):
        """Print snapshot details"""
        print(f"\n{'-'*60}")
        print(f"Memory Snapshot - {snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'-'*60}")
        print(f"  RSS (Resident Set Size): {snapshot.rss_mb:.2f} MB")
        print(f"  VMS (Virtual Memory):    {snapshot.vms_mb:.2f} MB")
        print(f"  Memory %:                {snapshot.percent:.1f}%")
        print(f"  Python Objects:          {snapshot.objects_count:,}")

        if self.baseline_memory:
            delta = snapshot.rss_mb - self.baseline_memory
            print(f"  Change from Baseline:    {delta:+.2f} MB ({delta/self.baseline_memory*100:+.1f}%)")

        print(f"\n  Top 5 Memory Allocations:")
        for i, (filename, lineno, size_mb) in enumerate(snapshot.top_allocations[:5], 1):
            # Truncate filename for readability
            short_filename = filename.split('/')[-1] if '/' in filename else filename
            print(f"    {i}. {short_filename}:{lineno} - {size_mb:.2f} MB")

    def print_leak_report(self, leak_info: Dict):
        """Print leak detection report"""
        print(f"\n{'='*60}")
        print("MEMORY LEAK DETECTION REPORT")
        print(f"{'='*60}\n")

        if leak_info["leak_detected"]:
            print("⚠️  POTENTIAL MEMORY LEAK DETECTED!")
        else:
            print("✅ No memory leak detected")

        print(f"\nAnalysis:")
        print(f"  Snapshots Analyzed:    {leak_info['snapshots_analyzed']}")
        print(f"  Duration:              {leak_info['duration_seconds']:.1f} seconds")
        print(f"  Memory Increase:       {leak_info['memory_increase_mb']:+.2f} MB")
        print(f"  Memory Growth:         {leak_info['memory_increase_percent']:+.1f}%")
        print(f"  Object Count Change:   {leak_info['object_increase']:+,}")

        if leak_info["leak_detected"]:
            print(f"\n⚠️  Recommendations:")
            print(f"  1. Review top memory allocations")
            print(f"  2. Check for unclosed resources (files, connections)")
            print(f"  3. Look for circular references")
            print(f"  4. Profile with memory_profiler for detailed analysis")

    def continuous_monitor(self, interval_seconds: int = 5, duration_minutes: int = 10):
        """Continuously monitor memory usage"""
        print(f"\n{'='*60}")
        print("CONTINUOUS MEMORY MONITORING")
        print(f"{'='*60}")
        print(f"Interval: {interval_seconds}s, Duration: {duration_minutes}min\n")

        self.start_tracking()

        iterations = (duration_minutes * 60) // interval_seconds
        for i in range(iterations):
            snapshot = self.take_snapshot()

            # Print every 10th snapshot to avoid spam
            if i % 10 == 0:
                self.print_snapshot(snapshot)

            time.sleep(interval_seconds)

        # Final analysis
        leak_info = self.detect_leaks()
        self.print_leak_report(leak_info)

    def profile_function(self, func, *args, **kwargs):
        """Profile a specific function's memory usage"""
        print(f"\n{'='*60}")
        print(f"PROFILING FUNCTION: {func.__name__}")
        print(f"{'='*60}\n")

        self.start_tracking()

        # Before snapshot
        snapshot_before = self.take_snapshot()
        print("Snapshot BEFORE function execution:")
        self.print_snapshot(snapshot_before)

        # Run function
        print(f"\nExecuting {func.__name__}...")
        start_time = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start_time

        # After snapshot
        snapshot_after = self.take_snapshot()
        print(f"\nSnapshot AFTER function execution ({duration:.2f}s):")
        self.print_snapshot(snapshot_after)

        # Analysis
        memory_delta = snapshot_after.rss_mb - snapshot_before.rss_mb
        objects_delta = snapshot_after.objects_count - snapshot_before.objects_count

        print(f"\n{'='*60}")
        print("FUNCTION PROFILE SUMMARY")
        print(f"{'='*60}")
        print(f"  Memory Change:    {memory_delta:+.2f} MB")
        print(f"  Objects Created:  {objects_delta:+,}")
        print(f"  Execution Time:   {duration:.2f}s")

        if abs(memory_delta) > 10:  # More than 10MB change
            print(f"\n⚠️  Warning: Significant memory change detected")

        return result


def example_usage():
    """Example usage of the memory profiler"""
    profiler = MemoryProfiler()

    # Example 1: Profile a function
    def test_function():
        """Test function that allocates memory"""
        data = []
        for i in range(1000000):
            data.append(i)
        return len(data)

    profiler.profile_function(test_function)

    # Example 2: Continuous monitoring (commented out for brevity)
    # profiler.continuous_monitor(interval_seconds=5, duration_minutes=2)


if __name__ == "__main__":
    if "--continuous" in sys.argv:
        profiler = MemoryProfiler()
        profiler.continuous_monitor(interval_seconds=10, duration_minutes=5)
    elif "--example" in sys.argv:
        example_usage()
    else:
        print(__doc__)
        print("\nOptions:")
        print("  --continuous  Run continuous monitoring")
        print("  --example     Run example usage")
        print("\nUse this module programmatically by importing MemoryProfiler")
