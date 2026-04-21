from __future__ import annotations

import logging
import os
import sys
from datetime import timedelta

import pendulum
import pytz
import pandas as pd

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.mysql.hooks.mysql import MySqlHook

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common.team_notification_operator import MsTeamsHook

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
SPC_CONN_ID    = 'spc_mysql_ds'
INTERFACE_NAME = 'DS_INC_OUTBOUND_ORDER'
CHUNKSIZE      = 10_000
BKK_TZ         = pytz.timezone('Asia/Bangkok')
CO_LIST       = ['CDS', 'RBS']
CO_OWNER_MAP  = {'CDS': 'CDS-CDS', 'RBS': 'RBS-RBS'}
# transaction_type → order_no prefix
PREFIX_MAP = {'TO': 'MT', 'RV': 'MV', 'IU': 'MI'}

# ── Execution timeouts ─────────────────────────────────────────────────────────
TIMEOUT_EXTRACT      = timedelta(hours=1)    # ETL fetch + insert
TIMEOUT_STAGING_SPC  = timedelta(hours=2)    # .NET staging → SPC
TIMEOUT_SPC_WMS      = timedelta(hours=2)    # .NET SPC → WMS

# Columns selected from st_outbound_order (no SELECT *)
ORDER_SOURCE_COLUMNS = [
    'jda_batch_id', 'dih_batch_id', 'event_status', 'order_no', 'order_date',
    'company', 'order_from', 'order_type', 'ship_to', 'ship_to_addr1',
    'ship_to_addr2', 'ship_to_addr3', 'city', 'province', 'country', 'postcode',
    'ship_to_name', 'bill_to_name', 'bill_to_addr1', 'bill_to_addr2',
    'bill_to_addr3', 'bill_to_company_name', 'order_remark', 'priority_code',
    'order_priority_code', 'transaction_type', 'reference_no', 'lable_type',
    'order_due_date', 'order_type_name',
]

# Columns selected from st_outbound_order_detail (no SELECT *)
# jda_batch_id / dih_batch_id / company come from the header via merge
DETAIL_SOURCE_COLUMNS = [
    'order_no', 'ibc', 'order_qty', 'qty', 'total_qty',
    'unit_price', 'product_type', 'product_sub_type', 'sku', 'cost', 'brand_id',
]

# Final column order for spc_jda_outbound_header_staging
HEADER_STG_COLUMNS = [
    'jda_batch_id', 'dih_batch_id', 'event_status', 'order_no', 'order_date',
    'company', 'order_from', 'order_type', 'ship_to', 'ship_to_addr1',
    'ship_to_addr2', 'ship_to_addr3', 'city', 'province', 'country', 'postcode',
    'ship_to_name', 'bill_to_name', 'bill_to_addr1', 'bill_to_addr2',
    'bill_to_addr3', 'bill_to_company_name', 'order_remark', 'priority_code',
    'order_priority_code', 'transaction_type', 'reference_no', 'label_type',
    'create_by', 'order_due_date', 'spc_interface_name', 'wms_interface_name',
    'order_type_name',
]

# Final column order for spc_jda_outbound_detail_staging
DETAIL_STG_COLUMNS = [
    'jda_batch_id', 'dih_batch_id', 'company', 'order_no', 'linenum', 'ibc',
    'order_qty', 'qty', 'total_qty', 'unit_price', 'product_type',
    'product_sub_type', 'sku', 'cost', 'create_by', 'brand_id',
]

_ORDER_COLS_SQL  = ', '.join(ORDER_SOURCE_COLUMNS)
_DETAIL_COLS_SQL = ', '.join(DETAIL_SOURCE_COLUMNS)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _insert_chunks(df: pd.DataFrame, engine, table: str, chunksize: int = CHUNKSIZE) -> None:
    """Insert DataFrame into MySQL table in chunks using a single connection."""
    with engine.connect() as conn:
        for i in range(0, len(df), chunksize):
            chunk = df.iloc[i:i + chunksize]
            chunk.to_sql(table, conn, if_exists='append', index=False)
            log.info("Inserted chunk %d: rows %d–%d into '%s'",
                     i // chunksize + 1, i, i + len(chunk), table)
        conn.commit()


def _build_header_df(df_order: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw st_outbound_order rows into spc_jda_outbound_header_staging shape.
    - Applies transaction_type → prefix mapping to order_no
    - Renames lable_type (source typo) → label_type
    - Adds computed columns: create_by, spc_interface_name, wms_interface_name
    """
    df = df_order[ORDER_SOURCE_COLUMNS].copy()

    # Apply prefix: new order_no = prefix + original order_no
    df['order_no'] = df['transaction_type'].map(PREFIX_MAP).fillna('') + df['order_no']

    # Fix source typo in column name
    df = df.rename(columns={'lable_type': 'label_type'})

    # Set-by-code columns
    df['create_by']          = 'spc-etl'
    df['spc_interface_name'] = INTERFACE_NAME
    df['wms_interface_name'] = 'so'

    return df[HEADER_STG_COLUMNS]


def _build_detail_df(df_order: pd.DataFrame, df_detail: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw st_outbound_order_detail rows into spc_jda_outbound_detail_staging shape.
    - Merges header columns (jda_batch_id, dih_batch_id, company, prefixed order_no)
      from df_order so that each detail row carries the correct new order_no
    - Sets linenum = ibc (per original spec)
    - Adds create_by
    """
    # Build a slim order key table with the prefixed order_no
    order_keys = df_order[['order_no', 'jda_batch_id', 'dih_batch_id', 'company',
                            'transaction_type']].copy()
    order_keys['new_order_no'] = (
        order_keys['transaction_type'].map(PREFIX_MAP).fillna('')
        + order_keys['order_no']
    )
    order_keys = order_keys.drop(columns=['transaction_type'])

    df = df_detail[DETAIL_SOURCE_COLUMNS].copy()
    df = df.merge(order_keys, on='order_no', how='inner')

    # Replace original order_no with prefixed version
    df['order_no'] = df['new_order_no']
    df = df.drop(columns=['new_order_no'])

    # Set-by-code columns
    df['linenum']   = df['ibc']
    df['create_by'] = 'spc-etl'

    return df[DETAIL_STG_COLUMNS]


# ── Main Task ──────────────────────────────────────────────────────────────────
def ds_inc_outbound_order_etl_data(**kwargs) -> None:
    """
    1. Check control table for a pending DS_INC_OUTBOUND_ORDER batch (CDS or RBS).
    2. Pull outbound order header + detail from SPC MySQL.
    3. Transform into staging shape (prefix order_no, rename columns, add computed cols).
    4. Insert into spc_jda_outbound_header_staging + spc_jda_outbound_detail_staging.
    5. Update control table status N → P.
    6. Push dih_batch_id, total_outbound_order_success, app_name to XCom.
    """
    ti       = kwargs['ti']
    spc_hook = MySqlHook(mysql_conn_id=SPC_CONN_ID)

    for co in CO_LIST:
        # ── 1. Control table ───────────────────────────────────────────────────────
        log.info("[%s] Querying control table for interface '%s'", co, INTERFACE_NAME)
        record = spc_hook.get_first(
            "SELECT dih_batch_id, tot_rec "
            "FROM st_control_table "
            "WHERE interface_name = %s AND status = 'N' AND co = %s "
            "ORDER BY dih_batch_id DESC "
            "LIMIT 1",
            parameters=(INTERFACE_NAME, co),
        )
        if record is None:
            log.info("[%s] No pending control table record found — skipping", co)
            # Push empty values so downstream tasks receive a defined XCom key
            ti.xcom_push(key=f'dih_batch_id_{co}',   value='')
            ti.xcom_push(key=f'total_success_{co}',   value='0')
            continue

        dih_batch_id = record[0]
        tot_rec      = record[1]
        log.info("[%s] Found batch: dih_batch_id=%s  tot_rec=%s", co, dih_batch_id, tot_rec)

        # ── 2. Fetch source data ───────────────────────────────────────────────────
        df_order = spc_hook.get_pandas_df(
            f"SELECT {_ORDER_COLS_SQL} FROM st_outbound_order WHERE dih_batch_id = %s",
            parameters=(dih_batch_id,),
        )
        log.info("[%s] Fetched %d outbound order header rows", co, len(df_order))

        df_detail = spc_hook.get_pandas_df(
            f"SELECT {_DETAIL_COLS_SQL} FROM st_outbound_order_detail WHERE dih_batch_id = %s",
            parameters=(dih_batch_id,),
        )
        log.info("[%s] Fetched %d outbound order detail rows", co, len(df_detail))

        # ── 3. Transform ───────────────────────────────────────────────────────────
        df_header_stg = _build_header_df(df_order)
        df_detail_stg = _build_detail_df(df_order, df_detail)
        total_success = len(df_header_stg)
        log.info("[%s] Transformed %d header rows and %d detail rows", co, total_success, len(df_detail_stg))

        # ── 4. Insert ──────────────────────────────────────────────────────────────
        engine = spc_hook.get_sqlalchemy_engine()
        try:
            _insert_chunks(df_detail_stg, engine, 'spc_jda_outbound_detail_staging')
            _insert_chunks(df_header_stg, engine, 'spc_jda_outbound_header_staging')
            log.info("[%s] Insert complete: %d header, %d detail", co, total_success, len(df_detail_stg))
        finally:
            engine.dispose()
            log.info("[%s] Engine disposed", co)

        # ── 5. Update control table ────────────────────────────────────────────────
        spc_hook.run(
            "UPDATE st_control_table SET status = 'P' "
            "WHERE interface_name = %s AND dih_batch_id = %s AND status = 'N'",
            parameters=(INTERFACE_NAME, dih_batch_id),
        )
        log.info("[%s] Control table status → 'P' for dih_batch_id=%s", co, dih_batch_id)

        # ── 6. XCom — push per CO so each child DAG chain gets its own values ──────
        ti.xcom_push(key=f'dih_batch_id_{co}', value=str(dih_batch_id))
        ti.xcom_push(key=f'total_success_{co}', value=str(total_success))

    ti.xcom_push(key='app_name', value='sync_order_outbound')


# ── Failure callback ───────────────────────────────────────────────────────────
def _on_failure(context: dict) -> None:
    ti = context['task_instance']
    MsTeamsHook().send_failure(
        dag_id=ti.dag_id,
        task_id=ti.task_id,
        error=context.get('exception', 'Task failed'),
        facts={
            'Run ID': ti.run_id,
            'Log':    ti.log_url,
        },
    )


# ── DAG ────────────────────────────────────────────────────────────────────────
_EXTRACT_TASK_ID = 'ds_inc_outbound_order_etl_data'

with DAG(
    dag_id='ds_inc_outbound_order',
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    schedule='15,45 * * * *',
    catchup=False,
    render_template_as_native_obj=True,
    tags=['ds', 'inc', 'outbound_order'],
    max_active_runs=1,
    on_failure_callback=_on_failure,
    default_args={'on_failure_callback': _on_failure},
) as dag:

    extract_task = PythonOperator(
        task_id=_EXTRACT_TASK_ID,
        python_callable=ds_inc_outbound_order_etl_data,
        do_xcom_push=False,  # function uses ti.xcom_push() explicitly
        execution_timeout=TIMEOUT_EXTRACT,
    )

    # ── Generate one staging→wms chain per CO, run sequentially ──────────────
    # Result for CO_LIST = ['CDS', 'RBS']:
    #   extract_task
    #     >> staging_to_spc_cds >> spc_to_wms_cds
    #     >> staging_to_spc_rbs >> spc_to_wms_rbs
    prev_task = extract_task
    for co in CO_LIST:
        co_lower = co.lower()

        staging_to_spc = TriggerDagRunOperator(
            task_id=f'spc_order_outbound_jda_staging_to_spc_{co_lower}',
            trigger_dag_id='spc_order_outbound_jda_staging_to_spc',
            poke_interval=5,
            reset_dag_run=False,
            wait_for_completion=True,
            allowed_states=['success'],
            failed_states=['failed'],
            execution_timeout=TIMEOUT_STAGING_SPC,
            conf={
                'parent_dag_id':                '{{ dag_run.dag_id }}',
                'parent_run_id':                '{{ dag_run.run_id }}',
                'trigger_time':                 '{{ ts }}',
                'app_name':                     f"{{{{ ti.xcom_pull(task_ids='{_EXTRACT_TASK_ID}', key='app_name') }}}}",
                'dih_batch_id':                 f"{{{{ ti.xcom_pull(task_ids='{_EXTRACT_TASK_ID}', key='dih_batch_id_{co}') }}}}",
                'total_outbound_order_success': f"{{{{ ti.xcom_pull(task_ids='{_EXTRACT_TASK_ID}', key='total_success_{co}') }}}}",
                'owner_id':                     CO_OWNER_MAP[co],
            },
        )

        spc_to_wms = TriggerDagRunOperator(
            task_id=f'spc_order_outbound_jda_spc_to_wms_{co_lower}',
            trigger_dag_id='spc_order_outbound_jda_spc_to_wms',
            poke_interval=5,
            reset_dag_run=False,
            wait_for_completion=True,
            allowed_states=['success'],
            failed_states=['failed'],
            execution_timeout=TIMEOUT_SPC_WMS,
            conf={
                'parent_dag_id':                '{{ dag_run.dag_id }}',
                'parent_run_id':                '{{ dag_run.run_id }}',
                'trigger_time':                 '{{ ts }}',
                'app_name':                     f"{{{{ ti.xcom_pull(task_ids='{_EXTRACT_TASK_ID}', key='app_name') }}}}",
                'dih_batch_id':                 f"{{{{ ti.xcom_pull(task_ids='{_EXTRACT_TASK_ID}', key='dih_batch_id_{co}') }}}}",
                'total_outbound_order_success': f"{{{{ ti.xcom_pull(task_ids='{_EXTRACT_TASK_ID}', key='total_success_{co}') }}}}",
                'owner_id':                     CO_OWNER_MAP[co],
            },
        )

        prev_task >> staging_to_spc >> spc_to_wms
        prev_task = spc_to_wms