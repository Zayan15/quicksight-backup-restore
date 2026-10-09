"""AWS operation helpers, separated from the Streamlit interface for offline tests."""
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

FAILURES = {'FAILED', 'FAILED_ROLLBACK_COMPLETED', 'FAILED_ROLLBACK_ERROR'}
PENDING = {'QUEUED_FOR_IMMEDIATE_EXECUTION', 'IN_PROGRESS', 'FAILED_ROLLBACK_IN_PROGRESS'}


def wait_for_job(describe, *, timeout=600, interval=5, clock=time.monotonic,
                 sleep=time.sleep, notify=lambda status: None):
    """Bound local polling; timing out does not cancel the remote AWS job."""
    if timeout <= 0 or interval <= 0:
        raise ValueError('Timeout and interval must be positive.')
    deadline = clock() + timeout
    delay = interval
    while clock() < deadline:
        try:
            response = describe()
        except Exception as exc:
            code = getattr(exc, 'response', {}).get('Error', {}).get('Code')
            if code not in {'ThrottlingException', 'TooManyRequestsException'}:
                raise
            notify('Rate limited; retrying')
        else:
            status = response.get('JobStatus')
            if status == 'SUCCESSFUL':
                return response
            if status in FAILURES:
                raise RuntimeError(f'AWS job ended with {status}. Inspect the job in AWS for details.')
            if status not in PENDING:
                raise RuntimeError(f'Unexpected AWS job status: {status!r}')
            notify(status)
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(delay, remaining))
        delay = min(delay * 1.5, 30)
    raise TimeoutError('Stopped waiting after the polling deadline. The AWS job may still be running; check it before retrying.')


def validate_config(config):
    if not re.fullmatch(r'\d{12}', config.get('account_id', '')):
        raise ValueError('Enter a 12-digit AWS account ID.')
    if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d', config.get('region', '')):
        raise ValueError('Enter a valid AWS region name.')
    bucket = config.get('s3_bucket', '')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket) or '..' in bucket:
        raise ValueError('Enter a valid S3 bucket name, without s3://.')
    if not isinstance(config.get('s3_prefix', ''), str):
        raise ValueError('S3 prefix must be text.')


def validate_s3_uri(uri):
    parsed = urlparse(uri)
    if (parsed.scheme != 's3' or not parsed.netloc or not parsed.path.strip('/')
            or parsed.query or parsed.fragment or parsed.username or parsed.port):
        raise ValueError('Use an S3 URI with a bucket and object key, without query parameters.')
    return uri


def backup_key(prefix, name):
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', name).strip('._')[:100] or 'dashboard'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = prefix.rstrip('/') + '/' if prefix else ''
    return f'{folder}{safe}_{stamp}_{uuid.uuid4().hex[:8]}.qs'


def list_backups(s3, bucket, prefix):
    backups = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            if obj['Key'].endswith('.qs'):
                backups.append({'key': obj['Key'], 'name': obj['Key'][len(prefix):].removesuffix('.qs'),
                                'size': obj['Size'], 'modified': obj['LastModified']})
    return backups
