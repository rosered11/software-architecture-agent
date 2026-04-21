"""
team_notification_operator.py
────────────────────────────────────────────────────────────────────────────────
Microsoft Teams Notification Library for Apache Airflow
SPC SCM Data Pipeline — Shared Utilities

SETUP (Airflow UI → Admin → Connections):
  Conn ID  : teams_webhook_conn   (or any name you prefer)
  Conn Type: HTTP
  Host     : https://outlook.office.com   (or https://<tenant>.webhook.office.com)
  Schema   : https
  Extra    : {"webhook_path": "/webhookb2/xxxxx/IncomingWebhook/yyyyy/zzzzz"}

  ─── OR ───  store the full URL in Host directly:
  Host     : https://outlook.office.com/webhookb2/xxxxx/IncomingWebhook/yyyyy/zzzzz

USAGE:
    from ms_teams_hook import MsTeamsHook, notify_success, notify_failure

    # Simple helpers
    notify_success(dag_id='my_dag', task_id='load_data', message='10,000 rows loaded')
    notify_failure(dag_id='my_dag', task_id='load_data', error='Connection timeout')

    # Full control
    hook = MsTeamsHook(teams_conn_id='teams_webhook_conn')
    hook.send_card(
        title='📦 Stock Reconcile Done',
        message='Variance report attached.',
        color=MsTeamsHook.COLOR_SUCCESS,
        facts={'Rows': 5_000, 'Variances': 12},
        buttons=[{'name': 'Open Dashboard', 'url': 'https://dashboard.example.com'}],
    )
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

# stdlib
import json
import logging
import datetime
from typing import Any

# third-party
import requests
import pytz

# airflow
from airflow.hooks.base import BaseHook

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
BKK_TZ = pytz.timezone('Asia/Bangkok')

DEFAULT_CONN_ID = 'teams_webhook_conn'

# Accent colors (hex without #) for card headers
COLOR_SUCCESS = '2DC72D'   # green
COLOR_FAILURE = 'FF0000'   # red
COLOR_WARNING = 'FFA500'   # orange
COLOR_INFO    = '0078D7'   # Microsoft blue


# ── Internal Helpers ───────────────────────────────────────────────────────────

def _now_bkk() -> str:
    """Return current Bangkok time as a human-readable string."""
    return datetime.datetime.now(BKK_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')


def _resolve_webhook_url(conn_id: str) -> str:
    """
    Resolve the full Teams webhook URL from an Airflow HTTP connection.

    Supports two layouts:
      (a) Full URL stored in `host`  →  used as-is.
      (b) Base URL in `host` + path in `extra.webhook_path`  →  concatenated.

    Raises
    ------
    ValueError
        If the resolved URL does not start with 'https://'.
    """
    conn = BaseHook.get_connection(conn_id)
    host = (conn.host or '').rstrip('/')

    extra: dict[str, Any] = {}
    if conn.extra:
        try:
            extra = json.loads(conn.extra)
        except json.JSONDecodeError:
            log.warning(f"[MsTeamsHook] Could not parse 'extra' JSON for conn '{conn_id}'")

    webhook_path = extra.get('webhook_path', '').strip('/')

    if webhook_path:
        url = f"{host}/{webhook_path}"
    else:
        # Assume host already contains the full webhook URL
        url = host

    if not url.startswith('https://'):
        raise ValueError(
            f"[MsTeamsHook] Webhook URL must start with 'https://'. "
            f"Got: '{url}' from conn_id='{conn_id}'. "
            "Check Airflow Connection → Host / Extra → webhook_path."
        )

    return url


def _build_message_card(
    title: str,
    message: str,
    color: str = COLOR_INFO,
    facts: dict[str, Any] | None = None,
    buttons: list[dict[str, str]] | None = None,
) -> dict:
    """
    Build a legacy Office 365 MessageCard payload.

    Compatible with all Teams tenants without requiring Power Automate.

    Parameters
    ----------
    title   : Card title shown in bold at the top.
    message : Body text (supports basic Markdown in Teams).
    color   : Hex color string (without '#') for the card's left border.
    facts   : Optional key-value pairs rendered as a fact table.
    buttons : Optional list of {'name': str, 'url': str} dicts for action buttons.
    """
    sections: list[dict] = []

    # ── Fact section ──────────────────────────────────────────────────────────
    fact_list = [{'name': 'Time (BKK)', 'value': _now_bkk()}]
    if facts:
        fact_list += [
            {'name': str(k), 'value': str(v)}
            for k, v in facts.items()
        ]
    sections.append({'facts': fact_list, 'markdown': True})

    # ── Potential actions (buttons) ───────────────────────────────────────────
    potential_actions: list[dict] = []
    if buttons:
        for btn in buttons:
            potential_actions.append({
                '@type'  : 'OpenUri',
                'name'   : btn.get('name', 'Open'),
                'targets': [{'os': 'default', 'uri': btn['url']}],
            })

    payload: dict = {
        '@type'            : 'MessageCard',
        '@context'         : 'http://schema.org/extensions',
        'themeColor'       : color,
        'summary'          : title,
        'title'            : title,
        'text'             : message,
        'sections'         : sections,
    }

    if potential_actions:
        payload['potentialAction'] = potential_actions

    return payload


# ── Main Hook ─────────────────────────────────────────────────────────────────

class MsTeamsHook:
    """
    Airflow hook for sending notifications to Microsoft Teams via Incoming Webhook.

    Parameters
    ----------
    teams_conn_id : Airflow Connection ID (HTTP type).
    timeout       : HTTP request timeout in seconds.

    Class Attributes (color constants)
    ------------------------------------
    COLOR_SUCCESS, COLOR_FAILURE, COLOR_WARNING, COLOR_INFO
    """

    COLOR_SUCCESS = COLOR_SUCCESS
    COLOR_FAILURE = COLOR_FAILURE
    COLOR_WARNING = COLOR_WARNING
    COLOR_INFO    = COLOR_INFO

    def __init__(
        self,
        teams_conn_id: str = DEFAULT_CONN_ID,
        timeout: int = 30,
    ) -> None:
        self.teams_conn_id = teams_conn_id
        self.timeout       = timeout
        self._webhook_url  = _resolve_webhook_url(teams_conn_id)

    # ── Core send ─────────────────────────────────────────────────────────────

    def send_card(
        self,
        title  : str,
        message: str,
        color  : str = COLOR_INFO,
        facts  : dict[str, Any] | None = None,
        buttons: list[dict[str, str]] | None = None,
    ) -> None:
        """
        Send a MessageCard to Teams.

        Parameters
        ----------
        title   : Card title.
        message : Body text.
        color   : Hex accent color — use MsTeamsHook.COLOR_* constants.
        facts   : Optional {'Key': 'Value', ...} shown as a fact table.
        buttons : Optional [{'name': 'Label', 'url': 'https://...'}, ...].

        Raises
        ------
        requests.HTTPError
            If the Teams endpoint returns a non-2xx status.
        """
        payload = _build_message_card(
            title=title,
            message=message,
            color=color,
            facts=facts,
            buttons=buttons,
        )

        log.info(f"[MsTeamsHook] Sending card '{title}' to Teams (conn={self.teams_conn_id})")

        try:
            response = requests.post(
                self._webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'},
            )
            response.raise_for_status()
            log.info(
                f"[MsTeamsHook] Notification sent successfully "
                f"(status={response.status_code}, title='{title}')"
            )
        except requests.HTTPError as e:
            log.error(
                f"[MsTeamsHook] HTTP error sending to Teams: {e} "
                f"(response body: {e.response.text[:500] if e.response else 'N/A'})"
            )
            raise
        except requests.RequestException as e:
            log.error(f"[MsTeamsHook] Request failed sending to Teams: {e}")
            raise

    # ── Convenience methods ───────────────────────────────────────────────────

    def send_success(
        self,
        dag_id : str,
        task_id: str,
        message: str = 'Task completed successfully.',
        facts  : dict[str, Any] | None = None,
        buttons: list[dict[str, str]] | None = None,
    ) -> None:
        """Send a green success card."""
        self.send_card(
            title  = f'✅ SUCCESS — {dag_id} / {task_id}',
            message= message,
            color  = self.COLOR_SUCCESS,
            facts  = facts,
            buttons= buttons,
        )

    def send_failure(
        self,
        dag_id : str,
        task_id: str,
        error  : str | Exception,
        facts  : dict[str, Any] | None = None,
        buttons: list[dict[str, str]] | None = None,
    ) -> None:
        """Send a red failure card. Pass the caught exception as `error`."""
        self.send_card(
            title  = f'❌ FAILURE — {dag_id} / {task_id}',
            message= f'**Error:** {error}',
            color  = self.COLOR_FAILURE,
            facts  = facts,
            buttons= buttons,
        )

    def send_warning(
        self,
        dag_id : str,
        task_id: str,
        message: str,
        facts  : dict[str, Any] | None = None,
        buttons: list[dict[str, str]] | None = None,
    ) -> None:
        """Send an orange warning card."""
        self.send_card(
            title  = f'⚠️ WARNING — {dag_id} / {task_id}',
            message= message,
            color  = self.COLOR_WARNING,
            facts  = facts,
            buttons= buttons,
        )

    def send_info(
        self,
        dag_id : str,
        task_id: str,
        message: str,
        facts  : dict[str, Any] | None = None,
        buttons: list[dict[str, str]] | None = None,
    ) -> None:
        """Send a blue informational card."""
        self.send_card(
            title  = f'ℹ️ INFO — {dag_id} / {task_id}',
            message= message,
            color  = self.COLOR_INFO,
            facts  = facts,
            buttons= buttons,
        )


# ── Module-Level Shortcuts ────────────────────────────────────────────────────
# Use these for one-liners inside PythonOperator callables.

def notify_success(
    dag_id       : str,
    task_id      : str,
    message      : str = 'Task completed successfully.',
    facts        : dict[str, Any] | None = None,
    buttons      : list[dict[str, str]] | None = None,
    teams_conn_id: str = DEFAULT_CONN_ID,
) -> None:
    """One-liner: send a success notification to Teams."""
    MsTeamsHook(teams_conn_id).send_success(
        dag_id=dag_id, task_id=task_id,
        message=message, facts=facts, buttons=buttons,
    )


def notify_failure(
    dag_id       : str,
    task_id      : str,
    error        : str | Exception,
    facts        : dict[str, Any] | None = None,
    buttons      : list[dict[str, str]] | None = None,
    teams_conn_id: str = DEFAULT_CONN_ID,
) -> None:
    """One-liner: send a failure notification to Teams."""
    MsTeamsHook(teams_conn_id).send_failure(
        dag_id=dag_id, task_id=task_id,
        error=error, facts=facts, buttons=buttons,
    )


def notify_warning(
    dag_id       : str,
    task_id      : str,
    message      : str,
    facts        : dict[str, Any] | None = None,
    buttons      : list[dict[str, str]] | None = None,
    teams_conn_id: str = DEFAULT_CONN_ID,
) -> None:
    """One-liner: send a warning notification to Teams."""
    MsTeamsHook(teams_conn_id).send_warning(
        dag_id=dag_id, task_id=task_id,
        message=message, facts=facts, buttons=buttons,
    )


def notify_info(
    dag_id       : str,
    task_id      : str,
    message      : str,
    facts        : dict[str, Any] | None = None,
    buttons      : list[dict[str, str]] | None = None,
    teams_conn_id: str = DEFAULT_CONN_ID,
) -> None:
    """One-liner: send an info notification to Teams."""
    MsTeamsHook(teams_conn_id).send_info(
        dag_id=dag_id, task_id=task_id,
        message=message, facts=facts, buttons=buttons,
    )