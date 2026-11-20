"""Candidate generation and measured layout selection."""

import json
import re
from collections import Counter
from copy import deepcopy
from datetime import date

import sqlglot
from sqlglot import exp


_INTEGER_TYPES = {"bigint", "integer", "int", "smallint", "tinyint"}
_LAYOUT_FIELDS = ("partitioning", "sorted_by", "file_mib", "row_group_mib", "shuffle")


def _is_encoded_date(value):
    if not isinstance(value, exp.Literal) or value.is_string:
        return False
    if not re.fullmatch(r"\d{8}", value.this):
        return False
    try:
        date(int(value.this[:4]), int(value.this[4:6]), int(value.this[6:]))
    except ValueError:
        return False
    return True


def _predicates(queries, types):
    frequency, encoded_dates = Counter(), Counter()
    template_columns = []
    for template in queries:
        where = sqlglot.parse_one(template["sql"], read="trino").args.get("where")
        columns = {node.name.lower() for node in where.find_all(exp.Column)} if where else set()
        if not columns <= types.keys():
            raise ValueError("Unknown predicate column")
        template_columns.append((str(template["template_id"]), columns))
        frequency.update(columns)
        if where is None:
            continue

        # Count valid numeric date boundaries once per template and column.
        encoded_columns = set()
        for node in where.walk():
            if not isinstance(node, (exp.Between, exp.GT, exp.GTE, exp.LT, exp.LTE)):
                continue
            column = node.this
            if not isinstance(column, exp.Column) or types[column.name.lower()].lower() not in _INTEGER_TYPES:
                continue
            if isinstance(node, exp.Between):
                boundaries = (node.args["low"], node.args["high"])
            else:
                boundaries = (node.expression,)
            if any(_is_encoded_date(value) for value in boundaries):
                encoded_columns.add(column.name.lower())
        encoded_dates.update(encoded_columns)
    return frequency, encoded_dates, template_columns


def _identity(layout):
    return json.dumps({key: layout[key] for key in _LAYOUT_FIELDS}, sort_keys=True)


def pools(queries, types, statistics, nominations, incumbent, composition_profile, incumbent_profile):
    """Return the three measured candidates for each of B3 and Beacon."""
    frequency, encoded_dates, template_columns = _predicates(queries, types)
    temporal = [
        column for column in frequency
        if types[column].lower() == "date" or types[column].lower().startswith("timestamp")
        or encoded_dates[column] >= 2
    ]
    if not temporal:
        raise ValueError("No supported temporal anchor")
    anchor_column = min(temporal, key=lambda column: (-frequency[column], column))
    if incumbent.get("bloom_columns"):
        raise ValueError("Unsupported Bloom-filter incumbent")
    current = {key: deepcopy(incumbent.get(key, [])) for key in ("partitioning", "sorted_by")}
    current.update(incumbent_profile)

    # Preserve compatible partitioning and non-temporal sort columns.
    anchor = next(
        (part for part in current["partitioning"]
         if re.fullmatch(r"(?:year|month|day)\(" + re.escape(anchor_column) + r"\)", part)),
        None,
    )
    if anchor is None:
        if encoded_dates[anchor_column] >= 2:
            anchor = f"truncate({anchor_column}, 100)"
        else:
            anchor = f"month({anchor_column})"
    partitions = list(dict.fromkeys([*current["partitioning"], anchor]))
    sorts = [column for column in current["sorted_by"] if column != anchor_column]
    used = {anchor_column, *sorts}
    for part in partitions:
        used.update(column for column in frequency if re.search(r"\b" + re.escape(column) + r"\b", part))
    eligible = [column for column in frequency if column not in used]
    if len(eligible) < 2:
        raise ValueError("Two additional candidate dimensions are required")

    selectivity = dict(statistics.get("column_selectivity", {}))
    if not selectivity:
        matches = statistics.get("matches", statistics.get("template_matches", {}))
        row_count = statistics["rows"]
        if row_count <= 0:
            raise ValueError("A positive table row count is required")
        for column in eligible:
            values = [matches[key] / row_count for key, columns in template_columns if column in columns]
            selectivity[column] = sum(values) / len(values)
    ranked = sorted(eligible, key=lambda column: (-frequency[column], selectivity[column], column))

    priorities = nominations.get("columns", nominations)
    if priorities.keys() - frequency.keys():
        raise ValueError("Nominations must be workload predicate columns")
    if any(not isinstance(weight, (int, float)) or not 0 <= weight <= 1 for weight in priorities.values()):
        raise ValueError("Invalid nomination weight")
    semantic = sorted(
        (column for column in eligible if column != ranked[0] and priorities.get(column, 0) >= 0.15),
        key=lambda column: (-priorities[column], -frequency[column], column),
    )
    branches = {"B3": ranked[:2], "Beacon": [ranked[0], semantic[0] if semantic else ranked[1]]}
    result = {}
    for method, columns in branches.items():
        candidates = [
            deepcopy(current),
            *(dict(partitioning=partitions[:], sorted_by=[*sorts, column], **composition_profile)
              for column in columns),
        ]
        if len({_identity(candidate) for candidate in candidates}) != 3:
            raise ValueError("Candidates must be physically distinct")
        result[method] = candidates
    return result


def select(units):
    """Select by workload CPU, elapsed time, logical input, then index."""
    if len(units) != 3 or {unit["candidate_index"] for unit in units} != {0, 1, 2}:
        raise ValueError("Three measured candidates are required")

    def cost(unit):
        totals = unit["totals"]["full"]
        return totals["cpu_s"], totals["wall_s"], totals["logical_bytes"], unit["candidate_index"]

    return min(units, key=cost)
