"""Spark SQL for sort rewrites."""

import re


def rewrite_sql(schema, table, sort_column="sqldate", where=None):
    for name in (schema, table, sort_column):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name):
            raise ValueError("Invalid identifier")

    # Spark procedure strings use backslash escaping.
    where_arg = ""
    if where:
        condition = where.replace("\\", "\\\\").replace("'", "\\'")
        where_arg = f", where => '{condition}'"
    table_name = f"{schema}.{table}"
    return (
        f"ALTER TABLE semskip.{table_name} "
        "SET TBLPROPERTIES ('read.parquet.vectorization.enabled'='false');\n"
        "CALL semskip.system.rewrite_data_files("
        f"table => '{table_name}', strategy => 'sort', sort_order => '{sort_column} ASC NULLS LAST', "
        "options => map('rewrite-all', 'true', "
        "'target-file-size-bytes', '67108864', "
        "'max-file-group-size-bytes', '1073741824', "
        "'max-concurrent-file-group-rewrites', '1')"
        f"{where_arg});"
    )
