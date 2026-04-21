from __future__ import annotations

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from airflow.hooks.base import BaseHook
from airflow.models import Variable
import os,sys,subprocess,hashlib
import logging
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.team_notification_operator import MsTeamsHook


job_id = "ds_spc_order_outbound_jda_staging_to_spc"
process_type = "SyncOrderOutboundStagingToSpcJda"
app_path = "/app/dotnet/program/etl_net_job"

TIMEOUT_DOTNET = timedelta(hours=2)

def run_dotnet_exe(**kwargs):
    conf = kwargs['dag_run'].conf
    parent_dag_id = conf.get('parent_dag_id')
    parent_run_id = conf.get('parent_run_id')
    dih_batch_id = conf.get('dih_batch_id')
    if not dih_batch_id:
        dih_batch_id = ''
    logging.info(f"Triggered by PARENT_DAG_ID: {parent_dag_id} PARENT_RUN_ID: {parent_run_id}")
    logging.info(f"Process DIH Batch Id: {dih_batch_id}")

    # Fetch connection
    db_order = BaseHook.get_connection('spc_order_mysql')
    db_staging = BaseHook.get_connection('spc_mysql_ds')

    # Build env variables for your .NET app
    order_conn_string = (
        f"Server={db_order.host};Database={db_order.schema};user id={db_order.login};pwd={db_order.password};"
    )
    staging_conn_string = (
        f"Server={db_staging.host};Database={db_staging.schema};user id={db_staging.login};pwd={db_staging.password};"
    )
    env = {
        **os.environ,
        "ConnectionStrings__SPCMySqlOrderConnectionString": order_conn_string,
        "ConnectionStrings__SPCMySqlStagingConnectionString": staging_conn_string,
        "ETLNETJOB_DIH_BATCH_ID": str(dih_batch_id),
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
    start_date=datetime(2025, 10, 15),
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

    run_job
