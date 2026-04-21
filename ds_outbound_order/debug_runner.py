"""
Debug runner for ds_outbound_order DAG.

Usage
-----
1. Set your DB credentials in the env block in .vscode/launch.json
   (or export them in your shell before running).
2. Press F5 in VS Code — or run:  python ds_outbound_order/debug_runner.py
3. Set breakpoints anywhere inside ds_outbound_order.py and step through normally.

How it works
------------
Airflow is NOT required to be installed.
This file stubs out every `airflow.*` import that ds_outbound_order.py needs,
then replaces MySqlHook with a real pymysql-backed implementation so the
ETL function talks to your actual database.
"""
from __future__ import annotations

import logging
import os
import sys
import types

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

# ── Stub Airflow modules before the DAG file is imported ─────────────────────
#    (the DAG-level code runs at import time, so stubs must come first)

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

for _name in [
    "airflow",
    "airflow.models",
    "airflow.models.dag",
    "airflow.operators",
    "airflow.operators.python",
    "airflow.operators.trigger_dagrun",
    "airflow.providers",
    "airflow.providers.mysql",
    "airflow.providers.mysql.hooks",
    "airflow.providers.mysql.hooks.mysql",
]:
    _stub(_name)


class _NoOp:
    """Absorbs DAG / Operator construction at module-import time."""
    def __init__(self, *a, **kw): pass
    def __enter__(self):           return self
    def __exit__(self, *a):        pass
    def __rshift__(self, other):   return other
    def __lshift__(self, other):   return self


sys.modules["airflow.models.dag"].DAG                               = _NoOp
sys.modules["airflow.operators.python"].PythonOperator              = _NoOp
sys.modules["airflow.operators.trigger_dagrun"].TriggerDagRunOperator = _NoOp


# ── Connection map ────────────────────────────────────────────────────────────
#    Add one entry per mysql_conn_id used by the DAG.
#    Keys must match the conn_id strings in ds_outbound_order.py exactly.
#
#    Each value is a dict accepted by pymysql.connect():
#      host, port, user, password, database
#
CONNECTIONS: dict[str, dict] = {
    "spc_mysql_ds": {
        "host":     os.getenv("SPC_DS_HOST",     "localhost"),
        "port":     int(os.getenv("SPC_DS_PORT", "3306")),
        "user":     os.getenv("SPC_DS_USER",     "root"),
        "password": os.getenv("SPC_DS_PASSWORD", ""),
        "database": os.getenv("SPC_DS_DB",       "spc_ds"),
    },
    # ── add more conn_ids here as needed ──────────────────────────────────────
    # "another_conn_id": {
    #     "host": "...", "port": 3306, "user": "...",
    #     "password": "...", "database": "...",
    # },
}


# ── Real MySqlHook backed by pymysql ─────────────────────────────────────────
import pandas as pd
import pymysql
from sqlalchemy import create_engine


class _RealMySqlHook:
    """Drop-in for airflow.providers.mysql.hooks.mysql.MySqlHook.

    Routes each mysql_conn_id to its own credentials via CONNECTIONS above.
    Raises KeyError with a clear message if a conn_id is not registered.
    """

    def __init__(self, mysql_conn_id: str | None = None):
        self.mysql_conn_id = mysql_conn_id
        if mysql_conn_id not in CONNECTIONS:
            raise KeyError(
                f"[debug_runner] Unknown conn_id '{mysql_conn_id}'. "
                f"Add it to CONNECTIONS in debug_runner.py. "
                f"Known IDs: {list(CONNECTIONS)}"
            )
        self._cfg = CONNECTIONS[mysql_conn_id]

    # ── internal ──────────────────────────────────────────────────────────────
    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(**self._cfg, charset="utf8mb4", autocommit=False)

    # ── public API (mirrors Airflow's MySqlHook) ──────────────────────────────
    def get_first(self, sql: str, parameters=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
                return cur.fetchone()

    def get_pandas_df(self, sql: str, parameters=None) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql(sql, conn, params=parameters)

    def run(self, sql: str, parameters=None) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
            conn.commit()

    def get_sqlalchemy_engine(self):
        c = self._cfg
        url = (
            f"mysql+pymysql://{c['user']}:{c['password']}"
            f"@{c['host']}:{c['port']}/{c['database']}?charset=utf8mb4"
        )
        # future=True enables SQLAlchemy 2.0-style Connection on 1.4.x,
        # giving conn.commit() / conn.rollback() without a version upgrade.
        return create_engine(url, future=True)


sys.modules["airflow.providers.mysql.hooks.mysql"].MySqlHook = _RealMySqlHook


# ── Stub TaskInstance (captures xcom_push output) ────────────────────────────
class _MockTaskInstance:
    def xcom_push(self, key: str, value) -> None:
        print(f"  [XCom]  {key!r:40s} = {value!r}")


# ── Import the actual DAG module ──────────────────────────────────────────────
#    All airflow stubs are in place, so this is safe.
sys.path.insert(0, os.path.dirname(__file__))
from ds_outbound_order import ds_inc_outbound_order_etl_data  # noqa: E402


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("─" * 60)
    for _cid, _cfg in CONNECTIONS.items():
        print(f"  [{_cid}]  {_cfg['user']}@{_cfg['host']}:{_cfg['port']}/{_cfg['database']}")
    print("─" * 60)

    ds_inc_outbound_order_etl_data(ti=_MockTaskInstance())

    print("─" * 60)
    print("  Done.")
    print("─" * 60)
