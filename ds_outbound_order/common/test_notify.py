"""
Quick local test for MsTeamsHook.
Stubs BaseHook so no Airflow connection is needed.
Edit WEBHOOK_URL below, then press F5.
"""
from __future__ import annotations

import sys
import os
import types

# ── Stub airflow.hooks.base before importing MsTeamsHook ─────────────────────
_airflow       = types.ModuleType("airflow")
_hooks         = types.ModuleType("airflow.hooks")
_hooks_base    = types.ModuleType("airflow.hooks.base")

sys.modules["airflow"]            = _airflow
sys.modules["airflow.hooks"]      = _hooks
sys.modules["airflow.hooks.base"] = _hooks_base

# ── Paste your full Teams webhook URL here ────────────────────────────────────
WEBHOOK_URL = "https://outlook.office.com/webhookb2/xxxxx/IncomingWebhook/yyyyy/zzzzz"

class _FakeConn:
    host  = WEBHOOK_URL
    extra = None

class _MockBaseHook:
    @staticmethod
    def get_connection(conn_id):
        return _FakeConn()

_hooks_base.BaseHook = _MockBaseHook

# ── Import the real hook ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_notification_operator import MsTeamsHook

# ── Send test cards ───────────────────────────────────────────────────────────
hook = MsTeamsHook()

print("Sending failure card...")
hook.send_failure(
    dag_id='ds_inc_outbound_order',
    task_id='ds_inc_outbound_order_etl_data',
    error='AirflowTaskTimeout: task exceeded execution_timeout of 1h',
    facts={
        'Run ID': 'scheduled__2026-04-21T14:15:00+00:00',
        'Log':    'https://airflow.example.com/log/...',
    },
)

print("Done — check your Teams channel.")
