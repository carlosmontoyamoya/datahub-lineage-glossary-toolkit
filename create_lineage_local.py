from datetime import datetime, timezone
import openlineage.client.facet as ol_facet
import openlineage.client.run as ol_run
import openlineage.client as ol_cl
import pandas as pd
import traceback
import logging
import uuid
import json
import os

# Logging setup
logger = logging.getLogger(name='Local Lineage Creator')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def load_validate_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine='python')

    if not len(df):
        raise Exception('DataFrame is Empty')
    if df.isna().any().any():
        raise Exception('Dataframe must not contain empty values')

    required_columns = {
        'job_name': 'object',
        'id': 'int64',
        'input_table_source': 'object',
        'input_table': 'object',
        'input_column': 'object',
        'input_column_data_type': 'object',
        'input_add_schema': 'bool',
        'output_table_destination': 'object',
        'output_table': 'object',
        'output_column': 'object',
        'output_column_data_type': 'object',
        'output_add_schema': 'bool',
        'transformation': 'bool'
    }

    if set(df.columns) != set(required_columns):
        raise Exception(f'DataFrame must contain exactly these columns: {list(required_columns.keys())}')

    for column, dtype in required_columns.items():
        if str(df[column].dtype) != dtype:
            raise Exception(f"Column {column} must be of type {dtype}, but got {df[column].dtype}")
    
    return df

def generate_input_dataset(df: pd.DataFrame):
    inputs = []
    for table_data, columns in df.groupby(['input_table_source', 'input_table']):
        namespace = table_data[0]
        table = table_data[1]
        column_group = columns.groupby('input_column')[['input_column_data_type', 'input_add_schema']].apply(lambda x: x.iloc[0]).reset_index()
        input = ol_run.Dataset(namespace=namespace, name=table)
        if column_group['input_add_schema'].any():
            input.facets['schema'] = ol_facet.SchemaDatasetFacet(fields=[
                ol_facet.SchemaField(name=row.input_column, type=row.input_column_data_type)
                for row in column_group.itertuples()
            ])
        inputs.append(input)
    return inputs

def generate_output_dataset(df: pd.DataFrame):
    outputs = []
    for table_data, transformations in df.groupby(['output_table_destination', 'output_table']):
        namespace = table_data[0]
        table = table_data[1]
        column_group = transformations.groupby('output_column')
        column_data = column_group[['output_column_data_type', 'output_add_schema']].apply(lambda x: x.iloc[0]).reset_index()
        output = ol_run.Dataset(
            namespace=namespace,
            name=table,
            facets={
                "columnLineage": ol_facet.ColumnLineageDatasetFacet(
                    fields={
                        output_column: ol_facet.ColumnLineageDatasetFacetFieldsAdditional(
                            inputFields=[
                                ol_facet.ColumnLineageDatasetFacetFieldsAdditionalInputFields(
                                    namespace=row.input_table_source,
                                    name=row.input_table,
                                    field=row.input_column
                                )
                                for row in group_data.itertuples()
                            ],
                            transformationType='AGGREGATION' if len(group_data) > 1 else 'TRANSFORMATION' if group_data['transformation'].any() else 'IDENTITY',
                            transformationDescription=None
                        )
                        for output_column, group_data in column_group
                    }
                )
            }
        )
        if column_data['output_add_schema'].any():
            output.facets['schema'] = ol_facet.SchemaDatasetFacet(fields=[
                ol_facet.SchemaField(name=row.output_column, type=row.output_column_data_type)
                for row in column_data.itertuples()
            ])
        outputs.append(output)
    return outputs

def generate_run_event(run, job, event_type, inputs=None, outputs=None):
    return ol_run.RunEvent(
        eventType=event_type,
        eventTime=datetime.now(timezone.utc).isoformat(),
        run=run,
        job=job,
        inputs=inputs,
        outputs=outputs,
        producer=ol_facet.PRODUCER
    )

if __name__ == "__main__":
    try:
        with open("config.json", "r") as f:
            config = json.load(f)

        access_token = config["access_token"]
        os.environ["OPENLINEAGE_URL"] = f'{config["api_url"]}/{config["api_endpoint"]}'
        os.environ["OPENLINEAGE_API_KEY"] = access_token
        client = ol_cl.OpenLineageClient()

        for metadata in config["linage_csv_s3_paths"]:
            job_name = metadata["name"]
            data_path = metadata["path"]

            logger.info(f"Processing lineage for {job_name} from file {data_path}")
            df = load_validate_df(data_path)

            for job_name_group, group_df in df.groupby("job_name"):
                run_id = str(uuid.uuid4())
                run = ol_run.Run(run_id)
                job = ol_run.Job(namespace="local-test", name=job_name_group)

                inputs = generate_input_dataset(group_df)
                outputs = generate_output_dataset(group_df)

                event = generate_run_event(run, job, ol_run.RunState.COMPLETE, inputs=inputs, outputs=outputs)
                client.emit(event)

                logger.info(f"✅ Lineage emitted for job {job_name_group}")



    except Exception:
        traceback.print_exc()
