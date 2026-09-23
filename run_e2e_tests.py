#!/usr/bin/env python3
"""FB Auto Post — Production E2E Test Suite Runner.

Executes 4 tiers of opaque-box E2E tests:
- Tier 1: Feature Coverage in Isolation (>= 75 tests)
- Tier 2: Boundary & Corner Cases (25 tests)
- Tier 3: Cross-Feature Combinations (15 tests)
- Tier 4: Real-World Farm Scenarios (5 tests)

Usage:
    python run_e2e_tests.py [--tier {1,2,3,4,all}] [-v] [--tb {auto,short,line,no}]
"""

import sys
import os
import time
import argparse
from pathlib import Path

# Configure UTF-8 on Windows stdout if supported
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
os.environ["TESTING"] = "true"
PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Safe ANSI formatting
GREEN = "\033[92m" if os.environ.get("NO_COLOR") is None else ""
RED = "\033[91m" if os.environ.get("NO_COLOR") is None else ""
YELLOW = "\033[93m" if os.environ.get("NO_COLOR") is None else ""
CYAN = "\033[96m" if os.environ.get("NO_COLOR") is None else ""
BOLD = "\033[1m" if os.environ.get("NO_COLOR") is None else ""
RESET = "\033[0m" if os.environ.get("NO_COLOR") is None else ""


TIER_CONFIG = {
    "1": {
        "name": "Tier 1: Feature Coverage in Isolation",
        "file": "tests/e2e/test_tier1_features.py",
        "target_count": 75,
        "description": "5+ isolated tests for each of the 15 features in PROJECT.md"
    },
    "2": {
        "name": "Tier 2: Boundary & Corner Cases",
        "file": "tests/e2e/test_tier2_boundaries.py",
        "target_count": 25,
        "description": "Empty inputs, 60s lease expirations, rate limits, large payloads"
    },
    "3": {
        "name": "Tier 3: Cross-Feature Pairwise Combinations",
        "file": "tests/e2e/test_tier3_combinations.py",
        "target_count": 15,
        "description": "Multi-worker claiming, post with media+spintax, checkpoint aborts"
    },
    "4": {
        "name": "Tier 4: Real-World Farm Scenarios",
        "file": "tests/e2e/test_tier4_scenarios.py",
        "target_count": 5,
        "description": "10-node farm, batch dispatch, crash failover, 24h lifecycle"
    }
}


def print_banner():
    print(f"{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}[*] FB AUTO POST -- PRODUCTION E2E TEST SUITE RUNNER{RESET}")
    print(f"{CYAN}    Production-Grade Facebook Account Farm & Distributed Automation{RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}")
    print(f"Working Directory: {PROJECT_ROOT}")
    print(f"Python Executable: {sys.executable}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")


class TestResultCollector:
    """Pytest plugin to collect detailed execution statistics."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.errors = 0
        self.total = 0
        self.failures = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.total += 1
            if report.passed:
                self.passed += 1
            elif report.failed:
                self.failed += 1
                self.failures.append((report.nodeid, report.longreprtext))
            elif report.skipped:
                self.skipped += 1
        elif report.when == "setup" and report.failed:
            self.errors += 1
            self.failures.append((report.nodeid, report.longreprtext))


def run_tier(tier_key: str, verbose: bool = False, tb: str = "short") -> tuple[int, TestResultCollector, float]:
    tier_info = TIER_CONFIG[tier_key]
    test_path = PROJECT_ROOT / tier_info["file"]
    
    print(f"{BOLD}[>] Running {tier_info['name']}{RESET}")
    print(f"    File: {tier_info['file']} (Target: >={tier_info['target_count']} tests)")
    print(f"    Scope: {tier_info['description']}")
    
    import pytest
    collector = TestResultCollector()
    
    pytest_args = [
        str(test_path),
        "-q" if not verbose else "-v",
        f"--tb={tb}",
        "--disable-warnings"
    ]

    start_time = time.time()
    exit_code = pytest.main(pytest_args, plugins=[collector])
    elapsed = time.time() - start_time
    
    status_color = GREEN if exit_code == 0 else RED
    status_label = "PASSED" if exit_code == 0 else "FAILED"
    print(f"    Result: {status_color}{BOLD}{status_label}{RESET} in {elapsed:.2f}s "
          f"({collector.passed} passed, {collector.failed} failed, {collector.skipped} skipped, total: {collector.total})\n")

    return exit_code, collector, elapsed


def main():
    parser = argparse.ArgumentParser(description="FB Auto Post E2E Test Runner")
    parser.add_argument("--tier", choices=["1", "2", "3", "4", "all"], default="all",
                        help="Specify tier to execute (default: all)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test execution")
    parser.add_argument("--tb", choices=["auto", "short", "line", "no"], default="short",
                        help="Traceback formatting")
    args = parser.parse_args()

    print_banner()

    tiers_to_run = ["1", "2", "3", "4"] if args.tier == "all" else [args.tier]
    
    results = {}
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_count = 0
    total_time = 0.0
    overall_exit_code = 0

    for t in tiers_to_run:
        exit_code, collector, elapsed = run_tier(t, verbose=args.verbose, tb=args.tb)
        results[t] = {
            "exit_code": exit_code,
            "collector": collector,
            "elapsed": elapsed
        }
        total_passed += collector.passed
        total_failed += collector.failed
        total_errors += collector.errors
        total_count += collector.total
        total_time += elapsed
        if exit_code != 0:
            overall_exit_code = 1

    # Print Summary Table
    print(f"{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}[*] E2E TEST EXECUTION SUMMARY REPORT{RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{'Tier':<10} | {'Target':<7} | {'Total':<6} | {'Passed':<7} | {'Failed':<7} | {'Time (s)':<9} | {'Status':<8}")
    print("-" * 70)

    for t in tiers_to_run:
        info = TIER_CONFIG[t]
        c = results[t]["collector"]
        el = results[t]["elapsed"]
        st = f"{GREEN}PASS{RESET}" if results[t]["exit_code"] == 0 else f"{RED}FAIL{RESET}"
        print(f"Tier {t:<5} | {info['target_count']:<7} | {c.total:<6} | {c.passed:<7} | {c.failed:<7} | {el:<9.2f} | {st}")

    print("-" * 70)
    overall_status = f"{GREEN}{BOLD}ALL TIERS PASSED{RESET}" if overall_exit_code == 0 else f"{RED}{BOLD}FAILURES DETECTED{RESET}"
    print(f"{'TOTAL':<10} | {120 if args.tier == 'all' else '-':<7} | {total_count:<6} | {total_passed:<7} | {total_failed:<7} | {total_time:<9.2f} | {overall_status}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}\n")

    return overall_exit_code


if __name__ == "__main__":
    sys.exit(main())
