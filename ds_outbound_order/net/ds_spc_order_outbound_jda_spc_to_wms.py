from __future__ import annotations

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
import datetime
from datetime import timedelta
from airflow.hooks.base import BaseHook
from airflow.models import Variable
from airflow.providers.mysql.hooks.mysql import MySqlHook
import os,sys,subprocess,hashlib
import logging
import pendulum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.team_notification_operator import MsTeamsHook


job_id = "ds_spc_order_outbound_jda_spc_to_wms"
process_type = "SyncOrderOutboundSpcToWmsJda"
app_path = "/app/dotnet/program/etl_net_job"

TIMEOUT_DOTNET = timedelta(hours=2)

def run_dotnet_exe(**kwargs):
    conf = kwargs['dag_run'].conf
    parent_dag_id = conf.get('parent_dag_id')
    parent_run_id = conf.get('parent_run_id')
    dih_batch_id              = conf.get('dih_batch_id', '')
    total_outbound_order_success = conf.get('total_outbound_order_success', '0')
    owner_id                  = conf.get('owner_id', 'DS-DS')

    logging.info(f"Triggered by PARENT_DAG_ID: {parent_dag_id} PARENT_RUN_ID: {parent_run_id}")
    logging.info(f"dih_batch_id={dih_batch_id!r}  total={total_outbound_order_success!r}  owner_id={owner_id!r}")

    # Guard: nothing to process for this CO — skip dotnet and DB operations entirely.
    # This prevents spc_batch_id from being incremented unnecessarily.
    if not dih_batch_id:
        logging.info("dih_batch_id is empty — no pending batch for this CO, skipping.")
        return

    # Fetch connection
    db_order = BaseHook.get_connection('spc_order_mysql')
    db_staging = BaseHook.get_connection('sprint_wms_mysql')

    # Build env variables for your .NET app
    order_conn_string = (
        f"Server={db_order.host};Database={db_order.schema};user id={db_order.login};pwd={db_order.password};"
    )
    staging_conn_string = (
        f"Server={db_staging.host};Database={db_staging.schema};user id={db_staging.login};pwd={db_staging.password};"
    )

    spc_mysql_hook = MySqlHook(mysql_conn_id='spc_mysql_ds')
    sql_query_select_interface_info = f" SELECT spc_batch_id FROM spc_interface_info where interface_name = 'DS_INC_OUTBOUND_ORDER' limit 1 ;"
    interface_info = spc_mysql_hook.get_first(sql=sql_query_select_interface_info)
    logging.debug(interface_info)
    spc_outbound_batch_id = interface_info[0]
    new_spc_outbound_batch_id = spc_outbound_batch_id + 1
    logging.info(f"spc_outbound_batch_id = {spc_outbound_batch_id}, new_spc_outbound_batch_id = {new_spc_outbound_batch_id}")
    # increase spc_batch_id
    sql_query_update_interface_info = f" UPDATE spc_interface_info set spc_batch_id = {new_spc_outbound_batch_id} where interface_name = 'DS_INC_OUTBOUND_ORDER' ;"
    spc_mysql_hook.run(sql=sql_query_update_interface_info)
    str_spc_outbound_batch_id = str(spc_outbound_batch_id)

    env = {
        **os.environ,
        "ConnectionStrings__SPCMySqlOrderConnectionString": order_conn_string,
        "ConnectionStrings__WMSMySqlStagingConnectionString": staging_conn_string,
        "ETLNETJOB_SPC_BATCH_ID": str_spc_outbound_batch_id,
    }

    result = subprocess.Popen(
        ["dotnet", f"{app_path}/ETLCronjob.dll", "--process-type=" + process_type],
        cwd=app_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        print("=== .Net Logging Start ===")

        for line in result.stdout:
            print(line, end="")  # stream stdout live

        print("=== .Net Logging End ===")

        exit_code = result.wait()
        print("Exit code:", exit_code)

        if exit_code != 0:
            raise Exception(f".NET job failed with exit code {exit_code}")
    except Exception:
        # Catches AirflowTaskTimeout, KeyboardInterrupt, and job failures —
        # kill the subprocess so it does not keep running on the server.
        if result.poll() is None:
            result.kill()
            result.wait()
            logging.warning("Subprocess killed due to exception")
        raise
    finally:
        # Safety net: ensure the process is dead when this callable exits.
        if result.poll() is None:
            result.kill()
            result.wait()
            logging.warning("Subprocess killed in finally block")
    
    wms_mysql_hook = MySqlHook(mysql_conn_id='sprint_wms_mysql')

    # insert wms control table
    create_datetime_on_control_table = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    query_insert_wms_staging_control_table = (
        " INSERT INTO wms_staging.st_control_table"
        " (batch_number, interface_name, owner_id, tot_rec, tot_success, tot_fail,"
        "  control_table_status, create_by, create_date, update_by, update_date,"
        "  etl_batch_id, etl_system, source_batch_id, source_system)"
        " VALUES('{}', 'so', '{}', '{}', '{}', '{}', 'N', 'spc_etl', '{}', 'spc_etl', '{}', '{}', '{}', '{}', '{}');"
    ).format(
        str_spc_outbound_batch_id, owner_id,
        total_outbound_order_success, 0, 0,
        create_datetime_on_control_table, create_datetime_on_control_table,
        dih_batch_id, 'informatica', '', 'JDA',
    )
    logging.info(f"Inserting WMS control table row: batch={str_spc_outbound_batch_id}  owner={owner_id}  dih={dih_batch_id}")
    wms_mysql_hook.run(sql=query_insert_wms_staging_control_table)

    # update spc st_control_table status N→P→C
    sql_update_control_table = (
        f"UPDATE st_control_table"
        f" SET status = 'C', spc_batch_id = '{str_spc_outbound_batch_id}'"
        f" WHERE interface_name = 'DS_INC_OUTBOUND_ORDER'"
        f"   AND dih_batch_id = '{dih_batch_id}';"
    )
    logging.info(f"Updating SPC control table: dih_batch_id={dih_batch_id}  spc_batch_id={str_spc_outbound_batch_id}")
    spc_mysql_hook.run(sql=sql_update_control_table)

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


schedule = Variable.get(job_id + "_schedule", default_var="0 0 1 * *")

with DAG(
    dag_id=job_id,
    start_date=pendulum.datetime(2025, 10, 15),
    schedule=None,
    max_active_runs=1,
    catchup=False,
    tags=['ds', '.net','outbound_order'],
    render_template_as_native_obj=True,
    on_failure_callback=_on_failure,
    default_args={'on_failure_callback': _on_failure},
) as dag:

    run_job = PythonOperator(
        task_id='run_dotnet_job',
        python_callable=run_dotnet_exe,
        retries=0,
        retry_delay=0,
        do_xcom_push=True,
        execution_timeout=TIMEOUT_DOTNET,
    )

    # Define task dependencies
    run_job
