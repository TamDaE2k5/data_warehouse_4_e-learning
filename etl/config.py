"""Database connections and per-query resource limits."""

import os
import math

import clickhouse_connect
import psycopg2


def pg_connect():
    return psycopg2.connect(application_name="online_learning_dw", connect_timeout=15)


def staging_connect():
    return psycopg2.connect(
        dbname="dwh_staging",
        user="learning_stage",
        password=os.environ["PG_STAGE_PASSWORD"],
        application_name="online_learning_dw",
        connect_timeout=15,
    )


def source_connect():
    return psycopg2.connect(
        dbname="learning_oltp",
        user="learning_reader",
        password=os.environ["PG_READER_PASSWORD"],
        application_name="dw_readonly",
        connect_timeout=15,
    )


def query_threads():
    """Use whole query workers within the CPU quota, with one for fractional quotas."""
    try:
        cpu = float(os.getenv("DW_CPUS", "4"))
    except ValueError as error:
        raise ValueError("DW_CPUS must be finite and positive") from error
    if not math.isfinite(cpu) or cpu <= 0:
        raise ValueError("DW_CPUS must be finite and positive")
    return max(1, math.floor(cpu))


def ch_connect():
    return clickhouse_connect.get_client(
        host=os.getenv("CH_HOST", "localhost"),
        port=int(os.getenv("CH_PORT", "8123")),
        username=os.getenv("CH_USER", "learning"),
        password=os.environ["CH_PASSWORD"],
        connect_timeout=30,
        send_receive_timeout=600,
        settings={
            "max_threads": query_threads(),
            "max_memory_usage": 1800000000,
            "max_bytes_before_external_group_by": 500000000,
            "max_bytes_before_external_sort": 500000000,
        },
    )
