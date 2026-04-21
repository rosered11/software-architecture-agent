"""
Debug runner for spc_order_outbound_jda_staging_to_spc DAG.

This DAG does NOT use XCom directly — it reads kwargs['dag_run'].conf,
which is populated by TriggerDagRunOperator in the parent DAG using XCom values.

To simulate a real run, edit MOCK_CONF below with the values you want to test.
These are the same fields that the parent DAG resolves from XCom and passes in.

Press F5 in VS Code to run.
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

# ── Mock conf — simulates what TriggerDagRunOperator injects from XCom ────────
#    These values come from ds_inc_outbound_order_etl_data() xcom_push calls.
#    Edit these to match the batch you want to debug.
MOCK_CONF = {
    "parent_dag_id":                "ds_inc_outbound_order",
    "parent_run_id":                "manual__2026-04-20T00:00:00+00:00",
    "trigger_time":                 "2026-04-20T00:00:00+00:00",
    "app_name":                     "sync_order_outbound",
    "dih_batch_id":                 "spcmock26042001,spcmock26042002",   # ← from xcom key='dih_batch_id'
    "total_outbound_order_success": "10,5",                              # ← from xcom key='total_outbound_order_success'
}

# ── Skip the actual dotnet subprocess? ────────────────────────────────────────
#    Set True to stub out the dotnet call and only debug the Python logic.
#    Set False to actually run the .NET job (requires dotnet + correct app_path).
SKIP_DOTNET = True


# ── Stub Airflow modules ──────────────────────────────────────────────────────
def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

for _name in [
    "airflow",
    "airflow.models",
    "airflow.models.dag",
    "airflow.models",
    "airflow.hooks",
    "airflow.hooks.base",
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
    def __init__(self, *a, **kw): pass
    def __enter__(self):          return self
    def __exit__(self, *a):       pass
    def __rshift__(self, other):  return other
    def __lshift__(self, other):  return self


sys.modules["airflow.models.dag"].DAG                                 = _NoOp
sys.modules["airflow.operators.python"].PythonOperator                = _NoOp
sys.modules["airflow.operators.trigger_dagrun"].TriggerDagRunOperator = _NoOp


# ── Mock Variable.get ─────────────────────────────────────────────────────────
#    Called at module level: Variable.get(job_id + "_schedule", default_var=...)
_airflow_models = sys.modules["airflow.models"]

class _MockVariable:
    @staticmethod
    def get(key, default_var=None):
        return default_var

_airflow_models.Variable = _MockVariable


# ── Mock BaseHook.get_connection ──────────────────────────────────────────────
#    Returns a fake connection object whose attributes build valid conn strings.
#    Add / edit entries to match the conn_ids used in the DAG.

DB_CONNECTIONS = {
    "spc_order_mysql": {
        "host":     os.getenv("SPC_ORDER_HOST",     "localhost"),
        "schema":   os.getenv("SPC_ORDER_DB",       "spc_order"),
        "login":    os.getenv("SPC_ORDER_USER",     "root"),
        "password": os.getenv("SPC_ORDER_PASSWORD", ""),
    },
    "spc_mysql_ds": {
        "host":     os.getenv("SPC_DS_HOST",        "localhost"),
        "schema":   os.getenv("SPC_DS_DB",          "spc_ds"),
        "login":    os.getenv("SPC_DS_USER",        "root"),
        "password": os.getenv("SPC_DS_PASSWORD",    ""),
    },
    # add more conn_ids here if needed
}


class _FakeConnection:
    def __init__(self, cfg: dict):
        self.host     = cfg["host"]
        self.schema   = cfg["schema"]
        self.login    = cfg["login"]
        self.password = cfg["password"]


class _MockBaseHook:
    @staticmethod
    def get_connection(conn_id: str) -> _FakeConnection:
        if conn_id not in DB_CONNECTIONS:
            raise KeyError(
                f"[debug_runner] Unknown conn_id '{conn_id}'. "
                f"Add it to DB_CONNECTIONS in debug_runner.py. "
                f"Known IDs: {list(DB_CONNECTIONS)}"
            )
        return _FakeConnection(DB_CONNECTIONS[conn_id])


sys.modules["airflow.hooks.base"].BaseHook = _MockBaseHook


# ── Mock MySqlHook (used by spc_to_wms only, but stub here for safety) ────────
import pymysql
import pandas as pd
from sqlalchemy import create_engine

MYSQL_CONNECTIONS = {
    "spc_mysql_ds": {
        "host":     os.getenv("SPC_DS_HOST",        "localhost"),
        "port":     int(os.getenv("SPC_DS_PORT",    "3306")),
        "user":     os.getenv("SPC_DS_USER",        "root"),
        "password": os.getenv("SPC_DS_PASSWORD",    ""),
        "database": os.getenv("SPC_DS_DB",          "spc_ds"),
    },
}


class _RealMySqlHook:
    def __init__(self, mysql_conn_id: str | None = None):
        self.mysql_conn_id = mysql_conn_id
        if mysql_conn_id not in MYSQL_CONNECTIONS:
            raise KeyError(
                f"[debug_runner] Unknown mysql conn_id '{mysql_conn_id}'. "
                f"Add it to MYSQL_CONNECTIONS. Known: {list(MYSQL_CONNECTIONS)}"
            )
        self._cfg = MYSQL_CONNECTIONS[mysql_conn_id]

    def _connect(self):
        return pymysql.connect(**self._cfg, charset="utf8mb4", autocommit=False)

    def get_first(self, sql, parameters=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
                return cur.fetchone()

    def get_pandas_df(self, sql, parameters=None) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql(sql, conn, params=parameters)

    def run(self, sql, parameters=None) -> None:
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
        return create_engine(url)


sys.modules["airflow.providers.mysql.hooks.mysql"].MySqlHook = _RealMySqlHook


# ── Patch subprocess.Popen to skip dotnet if SKIP_DOTNET=True ────────────────
if SKIP_DOTNET:
    import subprocess
    import io

    _real_popen = subprocess.Popen

    class _MockPopen:
        def __init__(self, cmd, *a, **kw):
            print(f"  [DOTNET SKIPPED]  would run: {cmd}")
            self.stdout     = io.StringIO("")
            self.returncode = 0

        def wait(self):
            return 0

        def poll(self):
            return 0

    subprocess.Popen = _MockPopen


# ── Mock dag_run object ───────────────────────────────────────────────────────
class _MockDagRun:
    def __init__(self, conf: dict):
        self.conf      = conf
        self.dag_id    = conf.get("parent_dag_id", "debug_dag")
        self.run_id    = conf.get("parent_run_id", "debug_run")


# ── Import and run the target function ───────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from spc_order_outbound_jda_staging_to_spc import run_dotnet_exe  # noqa: E402


if __name__ == "__main__":
    print("─" * 60)
    print("  DAG    spc_order_outbound_jda_staging_to_spc")
    print("  conf:")
    for k, v in MOCK_CONF.items():
        print(f"    {k:<38} = {v!r}")
    print(f"  SKIP_DOTNET = {SKIP_DOTNET}")
    print("─" * 60)

    run_dotnet_exe(dag_run=_MockDagRun(MOCK_CONF))

    print("─" * 60)
    print("  Done.")
    print("─" * 60)
