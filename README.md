# SemSkip

SemSkip pairs Beacon layout search with RangeWeaver incremental maintenance for Iceberg tables. Beacon adds validated workload-intent nominations to statistical layout candidates. RangeWeaver probes query input against a reference layout and chooses a maintenance action.

## Deploy

Use Docker Compose v2, Python 3.10 or later, Bash, and `curl`. On Windows, run the commands in WSL2 with Docker integration enabled.

```bash
bash scripts/up.sh
docker compose exec -T trino trino --execute 'SHOW CATALOGS'
bash scripts/spark.sh -e 'SHOW NAMESPACES IN semskip'
python3 -m pip install -e .
```

The first start creates local credentials, downloads the JDBC and Iceberg dependencies, and builds MinIO and its client from pinned upstream sources. Trino listens at `http://127.0.0.1:28080`.

`semskip.beacon` builds candidate pools from SQL templates, schema types, selectivity and validated column priorities. Its `select` function consumes measured candidate profiles. `semskip.rangeweaver` plans date ranges and accepts probe and rewrite callbacks. `semskip.spark` builds the Spark sort-rewrite statement.

## Get the datasets

| Dataset | Source |
| --- | --- |
| TPC-H | Trino generator, [`tpch.sf100.lineitem`](https://trino.io/docs/483/connector/tpch.html#tpc-h-schemas) |
| TPC-DS | Trino generator, [`tpcds.sf100.store_sales`](https://trino.io/docs/483/connector/tpcds.html#tpc-ds-schemas) |
| NYC | [TLC Yellow Taxi monthly Parquet](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) |
| BTS | [Reporting Carrier On-Time Performance](https://www.transtats.bts.gov/TableInfo.asp?gnoyr_VQ=FGJ) |
| GDELT | [GDELT 2.0 Event exports](https://gdeltproject.org/data.html) and [file index](https://data.gdeltproject.org/gdeltv2/masterfilelist.txt) |
