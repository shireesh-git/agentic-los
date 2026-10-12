"""
Deterministic Benchmark Engine
Compares borrower metrics against sector peer cohorts.
Uses fixed peer data (versioned) — no randomness.
"""

from src.models.canonical_model import (
    BenchmarkResult, BenchmarkStatus, RiskSeverity, FinancialStatement, Sector,
)
from src.engines.ratio_engine import compute_all_ratios, RatioResult


# ═══════════════════════════════════════════════════════════════════════════════
# SECTOR PEER BENCHMARKS (versioned — benchmark_pack_v1)
# These would come from a database in production; fixed here for determinism.
# Format: {sector: {metric: (p25, median, p75)}}
# ═══════════════════════════════════════════════════════════════════════════════

SECTOR_BENCHMARKS = {
    "manufacturing": {
        "current_ratio":            (1.15, 1.35, 1.65),
        "debt_to_equity":           (0.60, 0.95, 1.40),
        "debt_to_ebitda":           (1.50, 2.20, 3.20),
        "interest_coverage_ratio":  (3.50, 5.00, 7.50),
        "net_profit_margin":        (0.04, 0.08, 0.12),
        "ebitda_margin":            (0.12, 0.18, 0.24),
        "return_on_equity":         (0.10, 0.16, 0.25),
        "return_on_assets":         (0.04, 0.07, 0.11),
        "asset_turnover":           (0.80, 1.05, 1.30),
        "debtor_days":              (45.0, 60.0, 80.0),
        "inventory_days":           (30.0, 45.0, 65.0),
        "payable_days":             (35.0, 50.0, 70.0),
        "working_capital_cycle":    (30.0, 55.0, 80.0),
        "dscr":                     (1.20, 1.50, 2.00),
        "tol_tnw":                  (1.00, 1.60, 2.50),
    },
    "infrastructure": {
        "current_ratio":            (0.95, 1.15, 1.40),
        "debt_to_equity":           (1.20, 1.80, 2.80),
        "debt_to_ebitda":           (2.50, 3.50, 5.00),
        "interest_coverage_ratio":  (1.80, 2.80, 4.00),
        "net_profit_margin":        (0.02, 0.06, 0.10),
        "ebitda_margin":            (0.10, 0.16, 0.22),
        "return_on_equity":         (0.06, 0.12, 0.18),
        "return_on_assets":         (0.02, 0.05, 0.08),
        "asset_turnover":           (0.50, 0.75, 1.00),
        "debtor_days":              (60.0, 90.0, 130.0),
        "inventory_days":           (15.0, 25.0, 40.0),
        "payable_days":             (50.0, 75.0, 100.0),
        "working_capital_cycle":    (20.0, 45.0, 80.0),
        "dscr":                     (1.00, 1.25, 1.60),
        "tol_tnw":                  (1.80, 2.80, 4.00),
    },
    "pharma": {
        "current_ratio":            (1.20, 1.50, 1.90),
        "debt_to_equity":           (0.40, 0.80, 1.30),
        "debt_to_ebitda":           (1.00, 1.80, 2.80),
        "interest_coverage_ratio":  (3.00, 5.50, 9.00),
        "net_profit_margin":        (0.06, 0.10, 0.16),
        "ebitda_margin":            (0.16, 0.22, 0.28),
        "return_on_equity":         (0.12, 0.18, 0.28),
        "return_on_assets":         (0.06, 0.10, 0.15),
        "asset_turnover":           (0.70, 0.90, 1.15),
        "debtor_days":              (50.0, 70.0, 95.0),
        "inventory_days":           (40.0, 55.0, 75.0),
        "payable_days":             (40.0, 55.0, 75.0),
        "working_capital_cycle":    (40.0, 65.0, 95.0),
        "dscr":                     (1.30, 1.70, 2.20),
        "tol_tnw":                  (0.80, 1.30, 2.00),
    },
    "logistics": {
        "current_ratio":            (1.00, 1.20, 1.45),
        "debt_to_equity":           (1.00, 1.60, 2.50),
        "debt_to_ebitda":           (2.00, 2.80, 4.00),
        "interest_coverage_ratio":  (2.00, 3.00, 4.50),
        "net_profit_margin":        (0.02, 0.04, 0.07),
        "ebitda_margin":            (0.10, 0.15, 0.20),
        "return_on_equity":         (0.08, 0.14, 0.22),
        "return_on_assets":         (0.03, 0.05, 0.08),
        "asset_turnover":           (0.90, 1.15, 1.45),
        "debtor_days":              (50.0, 70.0, 95.0),
        "inventory_days":           (5.0, 10.0, 20.0),
        "payable_days":             (40.0, 55.0, 75.0),
        "working_capital_cycle":    (10.0, 25.0, 45.0),
        "dscr":                     (1.10, 1.35, 1.70),
        "tol_tnw":                  (1.50, 2.50, 3.80),
    },
    "construction_epc": {
        "current_ratio":            (0.90, 1.10, 1.35),
        "debt_to_equity":           (1.30, 1.90, 3.00),
        "debt_to_ebitda":           (2.80, 3.80, 5.50),
        "interest_coverage_ratio":  (1.50, 2.50, 3.80),
        "net_profit_margin":        (0.04, 0.08, 0.12),
        "ebitda_margin":            (0.14, 0.20, 0.26),
        "return_on_equity":         (0.08, 0.14, 0.20),
        "return_on_assets":         (0.03, 0.06, 0.09),
        "asset_turnover":           (0.40, 0.60, 0.85),
        "debtor_days":              (55.0, 75.0, 110.0),
        "inventory_days":           (40.0, 65.0, 90.0),
        "payable_days":             (55.0, 80.0, 110.0),
        "working_capital_cycle":    (25.0, 55.0, 90.0),
        "dscr":                     (1.00, 1.20, 1.50),
        "tol_tnw":                  (2.00, 3.00, 4.50),
    },
}


# ─── Subsector Override Map ──────────────────────────────────────────────────
# When a subsector matches a key here, use the specialized benchmark set
# instead of the generic sector benchmarks.
SUBSECTOR_BENCHMARK_MAP = {
    "Road & Highway Construction — EPC": "construction_epc",
}


# ─── Benchmark Classification ────────────────────────────────────────────────

# Metrics where HIGHER is WORSE (e.g., debt ratios, days)
HIGHER_IS_WORSE = {
    "debt_to_equity", "debt_to_ebitda", "debtor_days", "inventory_days",
    "working_capital_cycle", "tol_tnw",
}

# Metrics where HIGHER is BETTER (e.g., coverage, margins)
HIGHER_IS_BETTER = {
    "current_ratio", "interest_coverage_ratio", "net_profit_margin",
    "ebitda_margin", "return_on_equity", "return_on_assets",
    "asset_turnover", "dscr", "payable_days",
}


def classify_benchmark(metric: str, value: float, p25: float, median: float, p75: float) -> tuple:
    """Deterministic benchmark classification."""
    if metric in HIGHER_IS_WORSE:
        if value > p75:
            return BenchmarkStatus.WORSE_THAN_PEER, RiskSeverity.HIGH
        elif value > median:
            return BenchmarkStatus.WORSE_THAN_PEER, RiskSeverity.MEDIUM
        elif value >= p25:
            return BenchmarkStatus.WITHIN_BAND, RiskSeverity.LOW
        else:
            return BenchmarkStatus.BETTER_THAN_PEER, RiskSeverity.LOW
    elif metric in HIGHER_IS_BETTER:
        if value < p25:
            return BenchmarkStatus.WORSE_THAN_PEER, RiskSeverity.HIGH
        elif value < median:
            return BenchmarkStatus.WORSE_THAN_PEER, RiskSeverity.MEDIUM
        elif value <= p75:
            return BenchmarkStatus.WITHIN_BAND, RiskSeverity.LOW
        else:
            return BenchmarkStatus.BETTER_THAN_PEER, RiskSeverity.LOW
    else:
        # Default: treat as informational
        return BenchmarkStatus.WITHIN_BAND, RiskSeverity.LOW


# ─── Benchmark Runner ────────────────────────────────────────────────────────

def benchmark_single_period(
    entity_id: str,
    sector: Sector,
    period: str,
    ratios: list[RatioResult],
    subsector: str = "",
) -> list[BenchmarkResult]:
    """Benchmark one period's ratios against sector peers."""
    sector_key = SUBSECTOR_BENCHMARK_MAP.get(subsector, sector.value)
    if sector_key not in SECTOR_BENCHMARKS:
        sector_key = sector.value
    if sector_key not in SECTOR_BENCHMARKS:
        return []

    peers = SECTOR_BENCHMARKS[sector_key]
    results = []

    for ratio in ratios:
        if ratio.value is None or ratio.ratio_name not in peers:
            continue

        p25, median, p75 = peers[ratio.ratio_name]
        status, severity = classify_benchmark(ratio.ratio_name, ratio.value, p25, median, p75)

        results.append(BenchmarkResult(
            entity_id=entity_id,
            metric=ratio.ratio_name,
            borrower_value=ratio.value,
            peer_median=median,
            peer_p25=p25,
            peer_p75=p75,
            status=status,
            severity=severity,
            sector=sector_key,
            period=period,
        ))

    return results


def benchmark_all_periods(
    entity_id: str,
    sector: Sector,
    financials: dict[str, FinancialStatement],
    subsector: str = "",
    ratios_by_period: dict[str, list[RatioResult]] | None = None,
) -> dict[str, list[BenchmarkResult]]:
    """Benchmark all periods. Returns {period: [BenchmarkResult]}.

    ``ratios_by_period``: the financial_analysis agent's ratios; computed here only when not given."""
    results = {}
    for period, fs in financials.items():
        ratios = (ratios_by_period or {}).get(period) or compute_all_ratios(fs)
        results[period] = benchmark_single_period(entity_id, sector, period, ratios, subsector=subsector)
    return results


def get_worst_benchmarks(benchmarks: dict[str, list[BenchmarkResult]], period: str = None) -> list[BenchmarkResult]:
    """Get the worst benchmark results (worse_than_peer with HIGH severity)."""
    if period:
        bm_list = benchmarks.get(period, [])
    else:
        bm_list = [bm for plist in benchmarks.values() for bm in plist]

    return [bm for bm in bm_list
            if bm.status == BenchmarkStatus.WORSE_THAN_PEER and bm.severity in (RiskSeverity.HIGH, RiskSeverity.MEDIUM)]


def benchmark_summary_table(benchmarks: list[BenchmarkResult]) -> list[dict]:
    """Produce a summary table suitable for CAM rendering."""
    return [
        {
            "metric": bm.metric,
            "borrower": bm.borrower_value,
            "peer_p25": bm.peer_p25,
            "peer_median": bm.peer_median,
            "peer_p75": bm.peer_p75,
            "status": bm.status.value,
            "severity": bm.severity.value,
        }
        for bm in benchmarks
    ]
