"""Query-range planning and reference-assisted maintenance."""

import calendar
import re
from dataclasses import dataclass
from statistics import median


def layout_from_training(queries, first_year=2020, last_year=2025):
    """Return calendar buckets and a Spark filter for hot quarters."""
    if not 1 <= first_year <= last_year <= 9999:
        raise ValueError("Invalid year range")
    ranges = []
    for query in queries:
        matches = re.findall(r"\bsqldate\s+BETWEEN\s+(\d{8})\s+AND\s+(\d{8})",
                             query["sql"], flags=re.I)
        if len(matches) != int(query["group"] == "general"):
            raise ValueError("Unexpected number of workload date predicates")
        ranges.extend((int(lo), int(hi)) for lo, hi in matches)

    quarters = []
    for year in range(first_year, last_year + 1):
        for month in (1, 4, 7, 10):
            lo = year * 10000 + month * 100 + 1
            end_month = month + 2
            hi = year * 10000 + end_month * 100 + calendar.monthrange(year, end_month)[1]
            quarters.append((lo, hi, sum(a <= lo and b >= hi for a, b in ranges)))
    threshold = median(coverage for _, _, coverage in quarters)
    hot = [(lo, hi) for lo, hi, coverage in quarters if coverage > threshold]
    if not hot:
        raise ValueError("The workload has no above-median date coverage")

    # Use disjoint monthly and quarterly bucket keys.
    predicate = "(" + " OR ".join(f"sqldate BETWEEN {lo} AND {hi}" for lo, hi in hot) + ")"
    month = "CAST(floor(sqldate/100) AS BIGINT)"
    quarter = (
        "CAST(floor(sqldate/10000) AS BIGINT)*4"
        f" + CAST(floor((pmod({month},100)-1)/3) AS BIGINT)"
    )
    bucket = f"CAST(CASE WHEN {predicate} THEN 10000000 + {month} ELSE {quarter} END AS BIGINT)"
    return {"hot_ranges": hot, "hot_predicate": predicate, "bucket_sql": bucket}


def select_files(files, hot_ranges):
    """Return complete files overlapping a hot range or having unknown bounds."""
    return [
        file for file in files
        if file.get("lower") is None or file.get("upper") is None
        or any(file["lower"] <= hi and file["upper"] >= lo for lo, hi in hot_ranges)
    ]


@dataclass(frozen=True)
class Probe:
    physical_bytes: int
    elapsed_s: float


def scan_pass(current, reference, tolerance=1.05):
    if reference.physical_bytes == 0:
        return current.physical_bytes == 0
    return current.physical_bytes / reference.physical_bytes <= tolerance


def maintain(probe, rewrite, reference, reference_build_s, tolerance=1.05):
    """Probe the current snapshot and rewrite locally or fully when needed."""
    work = {"reference_s": reference_build_s + reference.elapsed_s}
    current = probe()
    work["probe_before_s"] = current.elapsed_s
    if scan_pass(current, reference, tolerance):
        return "retain", work

    # Each rewrite callback commits and verifies one snapshot.
    work["rewrite_local_s"] = rewrite("local")
    current = probe()
    work["probe_after_local_s"] = current.elapsed_s
    if scan_pass(current, reference, tolerance):
        return "local", work

    work["rewrite_full_s"] = rewrite("full")
    work["probe_after_full_s"] = probe().elapsed_s
    return "full", work
