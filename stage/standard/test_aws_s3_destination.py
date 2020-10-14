# Copyright 2020 StreamSets Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import logging
import string

import pytest
from streamsets.testframework.markers import aws
from streamsets.testframework.utils import get_random_string

logger = logging.getLogger(__name__)

# Sandbox prefix for S3 bucket
S3_SANDBOX_PREFIX = 'sandbox'

# Reference https://docs.aws.amazon.com/AmazonS3/latest/dev/BucketRestrictions.html
S3_BUCKET_NAMES = [
    # For 3 characters we use 2 letters + 1 digit to avoid colliding with system buckets
    ('minsize', get_random_string(string.digits, 2) + get_random_string(string.ascii_lowercase, 1)),
    ('maxsize', get_random_string(string.ascii_lowercase, 63)),
    ('lowercase', get_random_string(string.ascii_lowercase)),
    ('hypen', get_random_string(string.ascii_lowercase) + '-' + get_random_string(string.ascii_lowercase)),
    ('period', get_random_string(string.ascii_lowercase) + '.' + get_random_string(string.ascii_lowercase)),
    ('digits', get_random_string(string.digits)),
    ('hexadecimal', get_random_string(string.hexdigits).lower())
]

# Reference https://docs.aws.amazon.com/AmazonS3/latest/dev/UsingMetadata.html
S3_PATHS = [
    ('lowercase', get_random_string(string.ascii_lowercase)),
    ('uppercase', get_random_string(string.ascii_uppercase)),
    ('letters', get_random_string(string.ascii_letters)),
    ('digits', get_random_string(string.digits)),
    ('hexadecimal', get_random_string(string.hexdigits).lower()),
    ('forward_slash', get_random_string() + '/' + get_random_string()),
    ('start_forward_slash', '/' + get_random_string()),
    ('end_forward_slash', get_random_string() + '/'),
    ('exclamation_point', get_random_string() + '!' + get_random_string()),
    ('start_exclamation_point', '!' + get_random_string()),
    ('end_exclamation_point', get_random_string() + '!'),
    ('hypen', get_random_string() + '-' + get_random_string()),
    ('start_hypen', '-' + get_random_string()),
    ('end_hypen', get_random_string() + '-'),
    ('underscore', get_random_string() + '_' + get_random_string()),
    ('start_underscore', get_random_string() + '_'),
    ('end_underscore', '_' + get_random_string()),
    ('period', get_random_string() + '.' + get_random_string()),
    ('start_period', '.' + get_random_string()),
    ('end_period', get_random_string() + '.'),
    ('asterisk', get_random_string() + '*' + get_random_string()),
    ('start_asterisk', '*' + get_random_string()),
    ('end_asterisk', get_random_string() + '*'),
    ('dot', get_random_string() + '.' + get_random_string()),
    ('start_dot', '.' + get_random_string()),
    ('end_dot', get_random_string() + '.'),
    ('single_quote', get_random_string() + '\'' + get_random_string()),
    ('start_single_quote', '\'' + get_random_string()),
    ('end_single_quote', get_random_string() + '\''),
    ('open_parenthesis', get_random_string() + '(' + get_random_string()),
    ('start_open_parenthesis', '(' + get_random_string()),
    ('end_open_parenthesis', get_random_string() + '('),
    ('close_parenthesis', get_random_string() + ')' + get_random_string()),
    ('start_close_parenthesis', ')' + get_random_string()),
    ('end_close_parenthesis', get_random_string() + ')'),
]


@aws('s3')
@pytest.mark.parametrize('test_name, s3_bucket_name', S3_BUCKET_NAMES, ids=[i[0] for i in S3_BUCKET_NAMES])
def test_object_names_bucket(sdc_builder, sdc_executor, aws, test_name, s3_bucket_name):
    """Test for S3 target stage. We do so by running a dev raw data source generator to S3 destination
    sandbox bucket and then reading S3 bucket using STF client to assert data between the client to what has
    been ingested by the pipeline.
    """

    s3_bucket = s3_bucket_name
    s3_key = f'{S3_SANDBOX_PREFIX}/{get_random_string(string.ascii_letters, 10)}'

    # Bucket name is inside the record itself
    raw_str = f'{{ "bucket" : "{s3_bucket}", "company" : "StreamSets Inc."}}'

    # Build the pipeline
    builder = sdc_builder.get_pipeline_builder()

    dev_raw_data_source = builder.add_stage('Dev Raw Data Source').set_attributes(data_format='JSON',
                                                                                  raw_data=raw_str,
                                                                                  stop_after_first_batch=True)

    s3_destination = builder.add_stage('Amazon S3', type='destination')
    s3_destination.set_attributes(bucket=s3_bucket, data_format='JSON', partition_prefix=s3_key)

    dev_raw_data_source >> s3_destination

    s3_dest_pipeline = builder.build().configure_for_environment(aws)
    sdc_executor.add_pipeline(s3_dest_pipeline)

    client = aws.s3
    try:
        client.create_bucket(Bucket=s3_bucket, CreateBucketConfiguration={'LocationConstraint': aws.region})
        sdc_executor.start_pipeline(s3_dest_pipeline).wait_for_finished()

        # assert record count to S3 the size of the objects put
        list_s3_objs = client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)
        assert len(list_s3_objs['Contents']) == 1

        # read data from S3 to assert it is what got ingested into the pipeline
        s3_obj_key = client.get_object(Bucket=s3_bucket, Key=list_s3_objs['Contents'][0]['Key'])

        # We're comparing the logic structure (JSON) rather than byte-to-byte to allow for different ordering, ...
        s3_contents = s3_obj_key['Body'].read().decode().strip()
        assert json.loads(s3_contents) == json.loads(raw_str)

    finally:
        try:
            delete_keys = {'Objects': [{'Key': k['Key']}
                                       for k in client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)['Contents']]}
            client.delete_objects(Bucket=s3_bucket, Delete=delete_keys)
        finally:
            client.delete_bucket(Bucket=s3_bucket)


@aws('s3')
@pytest.mark.parametrize('test_name, path_name', S3_PATHS, ids=[i[0] for i in S3_PATHS])
def test_object_names_path(sdc_builder, sdc_executor, aws, test_name, path_name):
    """Test for S3 target stage. We do so by running a dev raw data source generator to S3 destination
    sandbox bucket and then reading S3 bucket using STF client to assert data between the client to what has
    been ingested by the pipeline.
    """

    s3_bucket = aws.s3_bucket_name
    s3_key = path_name

    # Bucket name is inside the record itself
    raw_str = f'{{ "bucket" : "{s3_bucket}", "company" : "StreamSets Inc."}}'

    # Build the pipeline
    builder = sdc_builder.get_pipeline_builder()

    dev_raw_data_source = builder.add_stage('Dev Raw Data Source').set_attributes(data_format='JSON',
                                                                                  raw_data=raw_str,
                                                                                  stop_after_first_batch=True)

    s3_destination = builder.add_stage('Amazon S3', type='destination')
    s3_destination.set_attributes(bucket=s3_bucket, data_format='JSON', partition_prefix=s3_key)

    dev_raw_data_source >> s3_destination

    s3_dest_pipeline = builder.build().configure_for_environment(aws)
    sdc_executor.add_pipeline(s3_dest_pipeline)

    client = aws.s3
    try:
        sdc_executor.start_pipeline(s3_dest_pipeline).wait_for_finished()

        # assert record count to S3 the size of the objects put
        list_s3_objs = client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)
        assert len(list_s3_objs['Contents']) == 1

        # read data from S3 to assert it is what got ingested into the pipeline
        s3_obj_key = client.get_object(Bucket=s3_bucket, Key=list_s3_objs['Contents'][0]['Key'])

        # We're comparing the logic structure (JSON) rather than byte-to-byte to allow for different ordering, ...
        s3_contents = s3_obj_key['Body'].read().decode().strip()
        assert json.loads(s3_contents) == json.loads(raw_str)

    finally:
        delete_keys = {'Objects': [{'Key': k['Key']}
                                   for k in client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)['Contents']]}
        client.delete_objects(Bucket=s3_bucket, Delete=delete_keys)


@aws('s3')
def test_dataflow_events(sdc_builder, sdc_executor, aws):
    """
    We write from Dev to S3 using wiretap to capture events and verifying their content
    """

    s3_bucket = aws.s3_bucket_name
    s3_key = f'{S3_SANDBOX_PREFIX}/{get_random_string(string.ascii_letters, 10)}'

    # Bucket name is inside the record itself
    raw_str = f'{{ "bucket" : "{s3_bucket}", "company" : "StreamSets Inc."}}'

    # Build the pipeline
    builder = sdc_builder.get_pipeline_builder()

    dev_raw_data_source = builder.add_stage('Dev Raw Data Source').set_attributes(data_format='JSON',
                                                                                  raw_data=raw_str,
                                                                                  stop_after_first_batch=True)

    s3_destination = builder.add_stage('Amazon S3', type='destination')
    s3_destination.set_attributes(bucket=s3_bucket, data_format='JSON', partition_prefix=s3_key)

    wiretap = builder.add_wiretap()

    dev_raw_data_source >> s3_destination >= wiretap.destination

    s3_dest_pipeline = builder.build().configure_for_environment(aws)
    sdc_executor.add_pipeline(s3_dest_pipeline)

    client = aws.s3
    try:
        sdc_executor.start_pipeline(s3_dest_pipeline).wait_for_finished()

        # Validate event generation
        assert wiretap.output_records[0].get_field_data('/bucket') == aws.s3_bucket_name
        assert wiretap.output_records[0].get_field_data('/recordCount') == 1

        # assert record count to S3 the size of the objects put
        list_s3_objs = client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)
        assert len(list_s3_objs['Contents']) == 1

        # read data from S3 to assert it is what got ingested into the pipeline
        s3_obj_key = client.get_object(Bucket=s3_bucket, Key=list_s3_objs['Contents'][0]['Key'])

        # We're comparing the logic structure (JSON) rather than byte-to-byte to allow for different ordering, ...
        s3_contents = s3_obj_key['Body'].read().decode().strip()
        assert json.loads(s3_contents) == json.loads(raw_str)

    finally:
        delete_keys = {'Objects': [{'Key': k['Key']}
                                   for k in client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)['Contents']]}
        client.delete_objects(Bucket=s3_bucket, Delete=delete_keys)


@aws('s3')
def test_multiple_batches(sdc_builder, sdc_executor, aws):
    """
    Test for S3 target stage. We verify that the destination work fine with more than one batch.
    """

    s3_bucket = aws.s3_bucket_name
    s3_key = f'{S3_SANDBOX_PREFIX}/{get_random_string(string.ascii_letters, 10)}'

    # Bucket name is inside the record itself
    raw_str = f'{{ "bucket" : "{s3_bucket}", "company" : "StreamSets Inc."}}'

    # Build the pipeline
    builder = sdc_builder.get_pipeline_builder()

    dev_raw_data_source = builder.add_stage('Dev Raw Data Source').set_attributes(data_format='JSON',
                                                                                  raw_data=raw_str,
                                                                                  stop_after_first_batch=False)

    s3_destination = builder.add_stage('Amazon S3', type='destination')
    s3_destination.set_attributes(bucket=s3_bucket, data_format='JSON', partition_prefix=s3_key)

    dev_raw_data_source >> s3_destination

    s3_dest_pipeline = builder.build().configure_for_environment(aws)
    sdc_executor.add_pipeline(s3_dest_pipeline)

    client = aws.s3
    try:
        sdc_executor.start_pipeline(s3_dest_pipeline).wait_for_pipeline_output_records_count(20)
        sdc_executor.stop_pipeline(s3_dest_pipeline)

        # assert record count to S3 the size of the objects put
        list_s3_objs = client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)

        history = sdc_executor.get_pipeline_history(s3_dest_pipeline)
        history_records = history.latest.metrics.counter('stage.AmazonS3_01.outputRecords.counter').count
        assert len(list_s3_objs['Contents']) == history_records

        # read data from S3 to assert it is what got ingested into the pipeline
        s3_obj_key = client.get_object(Bucket=s3_bucket, Key=list_s3_objs['Contents'][0]['Key'])

        # We're comparing the logic structure (JSON) rather than byte-to-byte to allow for different ordering, ...
        s3_contents = s3_obj_key['Body'].read().decode().strip()
        assert json.loads(s3_contents) == json.loads(raw_str)

    finally:
        delete_keys = {'Objects': [{'Key': k['Key']}
                                   for k in client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)['Contents']]}
        client.delete_objects(Bucket=s3_bucket, Delete=delete_keys)


@aws('s3')
def test_push_pull(sdc_builder, sdc_executor, aws):
    """
    We plan to verify that the connector works fine with Dev Raw Data Source and Dev Data Generator, an example of pull
    and push strategies, so as we already verified Dev Raw Data Source, we will use Dev Data Generator here to complete
    the coverage.
    """

    s3_bucket = aws.s3_bucket_name
    s3_key = f'{S3_SANDBOX_PREFIX}/{get_random_string(string.ascii_letters, 10)}'

    # Build the pipeline
    builder = sdc_builder.get_pipeline_builder()

    dev_data_generator = builder.add_stage('Dev Data Generator')

    dev_data_generator.set_attributes(batch_size=1,
                                      fields_to_generate=[
                                          {'field': 'stringField', 'type': 'STRING', 'precision': 10, 'scale': 2}])

    s3_destination = builder.add_stage('Amazon S3', type='destination')
    s3_destination.set_attributes(bucket=s3_bucket, data_format='JSON', partition_prefix=s3_key)

    dev_data_generator >> s3_destination

    s3_dest_pipeline = builder.build().configure_for_environment(aws)
    sdc_executor.add_pipeline(s3_dest_pipeline)

    client = aws.s3
    try:
        sdc_executor.start_pipeline(s3_dest_pipeline).wait_for_pipeline_output_records_count(25)
        sdc_executor.stop_pipeline(s3_dest_pipeline)

        history = sdc_executor.get_pipeline_history(s3_dest_pipeline)
        history_records = history.latest.metrics.counter('stage.AmazonS3_01.outputRecords.counter').count

        # assert record count to S3 the size of the objects put
        list_s3_objs = client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)
        assert len(list_s3_objs['Contents']) == history_records

    finally:
        delete_keys = {'Objects': [{'Key': k['Key']}
                                   for k in client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_key)['Contents']]}
        client.delete_objects(Bucket=s3_bucket, Delete=delete_keys)
