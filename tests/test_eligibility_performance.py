"""Performance benchmarks for eligibility classifier."""

import time
import tracemalloc
from decimal import Decimal
from pathlib import Path

from decision_service.engine.eligibility_classifier import EligibilityClassifier


def generate_test_items(count: int) -> list:
    """Generate test items for benchmarking."""
    descriptions = [
        "Professional carpet cleaning",
        "Normal wear and tear on walls",
        "Broken window pane replacement",
        "Unpaid rent - October 2024",
        "Repair holes in drywall",
        "Kitchen upgrade to granite counters",
        "Routine maintenance service",
        "Pre-existing damage repair",
        "Pet damage to carpet",
        "Smoking damage to walls",
        "Repaint due to damage",
        "Broken refrigerator repair",
        "Carpet damage repair",
        "Broken pipe repair",
        "Monthly electric bill",
        "Lawn maintenance",
        "Clean up water damage",
        "Mystery charge",
        "Unpaid electric bill",
        "Routine cleaning service",
    ]
    
    items = []
    for i in range(count):
        desc = descriptions[i % len(descriptions)]
        items.append({
            "description": desc,
            "amount": Decimal(f"{(i % 500) + 50}.00"),
            "line_number": i + 1
        })
    return items


def benchmark_classification_speed(classifier: EligibilityClassifier, item_count: int = 100):
    """Benchmark classification speed."""
    items = generate_test_items(item_count)
    
    start_time = time.perf_counter()
    results = classifier.classify_batch(items)
    end_time = time.perf_counter()
    
    total_time_ms = (end_time - start_time) * 1000
    avg_time_ms = total_time_ms / item_count
    
    print(f"\nClassification Speed Benchmark ({item_count} items):")
    print(f"  Total time: {total_time_ms:.2f} ms")
    print(f"  Average per item: {avg_time_ms:.3f} ms")
    print(f"  Items per second: {item_count / (total_time_ms / 1000):.0f}")
    
    assert total_time_ms < 200, f"Classification too slow: {total_time_ms:.2f}ms (target: <200ms for 100 items)"
    assert avg_time_ms < 2, f"Per-item classification too slow: {avg_time_ms:.3f}ms (target: <2ms per item)"
    
    return {
        "total_time_ms": total_time_ms,
        "avg_time_ms": avg_time_ms,
        "items_per_second": item_count / (total_time_ms / 1000)
    }


def benchmark_rules_reload(classifier: EligibilityClassifier):
    """Benchmark rules reload time."""
    rules_path = Path(__file__).parent.parent / "rules" / "rules_v1.0.yaml"
    
    start_time = time.perf_counter()
    classifier.reload_rules(str(rules_path))
    end_time = time.perf_counter()
    
    reload_time_ms = (end_time - start_time) * 1000
    
    print(f"\nRules Reload Benchmark:")
    print(f"  Reload time: {reload_time_ms:.2f} ms")
    
    assert reload_time_ms < 50, f"Rules reload too slow: {reload_time_ms:.2f}ms (target: <50ms)"
    
    return {"reload_time_ms": reload_time_ms}


def benchmark_memory_usage(classifier: EligibilityClassifier):
    """Benchmark memory usage."""
    tracemalloc.start()
    
    snapshot_before = tracemalloc.take_snapshot()
    
    items = generate_test_items(1000)
    results = classifier.classify_batch(items)
    
    snapshot_after = tracemalloc.take_snapshot()
    
    top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
    
    total_memory_mb = sum(stat.size_diff for stat in top_stats) / (1024 * 1024)
    
    print(f"\nMemory Usage Benchmark:")
    print(f"  Memory used: {total_memory_mb:.2f} MB")
    
    tracemalloc.stop()
    
    assert total_memory_mb < 50, f"Memory usage too high: {total_memory_mb:.2f}MB (target: <50MB)"
    
    return {"memory_mb": total_memory_mb}


def benchmark_single_item(classifier: EligibilityClassifier):
    """Benchmark single item classification."""
    item = {
        "description": "Professional carpet cleaning",
        "amount": Decimal("150.00"),
        "line_number": 1
    }
    
    times = []
    for _ in range(100):
        start = time.perf_counter()
        result = classifier.classify(item)
        end = time.perf_counter()
        times.append((end - start) * 1000)
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print(f"\nSingle Item Classification Benchmark (100 iterations):")
    print(f"  Average: {avg_time:.3f} ms")
    print(f"  Min: {min_time:.3f} ms")
    print(f"  Max: {max_time:.3f} ms")
    
    return {
        "avg_time_ms": avg_time,
        "min_time_ms": min_time,
        "max_time_ms": max_time
    }


def run_all_benchmarks():
    """Run all performance benchmarks."""
    print("=" * 80)
    print("ELIGIBILITY CLASSIFIER PERFORMANCE BENCHMARKS")
    print("=" * 80)
    
    rules_path = Path(__file__).parent.parent / "rules" / "rules_v1.0.yaml"
    classifier = EligibilityClassifier(str(rules_path))
    
    results = {}
    
    try:
        results['classification_speed'] = benchmark_classification_speed(classifier, 100)
        results['single_item'] = benchmark_single_item(classifier)
        results['rules_reload'] = benchmark_rules_reload(classifier)
        results['memory_usage'] = benchmark_memory_usage(classifier)
        
        print("\n" + "=" * 80)
        print("ALL BENCHMARKS PASSED")
        print("=" * 80)
        
        return results
    except AssertionError as e:
        print(f"\n❌ BENCHMARK FAILED: {e}")
        raise


if __name__ == "__main__":
    run_all_benchmarks()

