import unittest
from unittest.mock import Mock
from operations import wait_for_job, validate_config, validate_s3_uri, backup_key, list_backups

class FakeClock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds

class OperationsTests(unittest.TestCase):
    def poll(self, responses, **kwargs):
        clock = FakeClock()
        describe = Mock(side_effect=responses)
        return wait_for_job(describe, clock=clock, sleep=clock.sleep, **kwargs)

    def test_queued_and_rollback_progress_are_polled(self):
        result = self.poll([{'JobStatus': s} for s in ['QUEUED_FOR_IMMEDIATE_EXECUTION', 'IN_PROGRESS', 'SUCCESSFUL']])
        self.assertEqual(result['JobStatus'], 'SUCCESSFUL')
        with self.assertRaisesRegex(RuntimeError, 'FAILED_ROLLBACK_COMPLETED'):
            self.poll([{'JobStatus': 'FAILED_ROLLBACK_IN_PROGRESS'}, {'JobStatus': 'FAILED_ROLLBACK_COMPLETED'}])

    def test_all_failure_states_stop(self):
        for state in ['FAILED', 'FAILED_ROLLBACK_COMPLETED', 'FAILED_ROLLBACK_ERROR']:
            with self.subTest(state=state), self.assertRaises(RuntimeError):
                self.poll([{'JobStatus': state}])

    def test_unknown_status_stops_instead_of_busy_loop(self):
        with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
            self.poll([{'JobStatus': 'UNKNOWN'}])

    def test_deadline_bounds_wait(self):
        clock = FakeClock()
        describe = Mock(return_value={'JobStatus': 'IN_PROGRESS'})
        with self.assertRaises(TimeoutError):
            wait_for_job(describe, timeout=12, clock=clock, sleep=clock.sleep)
        self.assertEqual(clock.now, 12)
        self.assertEqual(describe.call_count, 2)

    def test_throttling_is_retried_but_access_denied_is_not(self):
        throttled = Exception('throttled')
        throttled.response = {'Error': {'Code': 'ThrottlingException'}}
        self.assertEqual(self.poll([throttled, {'JobStatus': 'SUCCESSFUL'}])['JobStatus'], 'SUCCESSFUL')
        with self.assertRaisesRegex(PermissionError, 'denied'):
            self.poll([PermissionError('denied')])

    def test_throttling_obeys_deadline(self):
        exc = Exception('throttle')
        exc.response = {'Error': {'Code': 'ThrottlingException'}}
        with self.assertRaises(TimeoutError):
            self.poll([exc]*5, timeout=10)

    def test_s3_listing_reads_all_pages_and_filters_bundles(self):
        s3 = Mock()
        item = lambda key: {'Key': key, 'Size': 10, 'LastModified': 'demo'}
        s3.get_paginator.return_value.paginate.return_value = [
            {'Contents': [item('backups/one.qs'), item('backups/note.txt')]},
            {}, {'Contents': [item('backups/two.qs')]}]
        self.assertEqual([x['name'] for x in list_backups(s3, 'example-bucket', 'backups/')], ['one', 'two'])

    def test_invalid_config_rejected(self):
        good = {'account_id': '000000000000', 'region': 'us-west-2', 's3_bucket': 'example-bucket', 's3_prefix': ''}
        validate_config(good)
        for key, value in [('account_id', ''), ('region', ''), ('s3_bucket', 's3://wrong'), ('s3_prefix', None)]:
            with self.subTest(key=key), self.assertRaises(ValueError): validate_config({**good, key:value})

    def test_uri_requires_bucket_and_key(self):
        self.assertEqual(validate_s3_uri('s3://example-bucket/backups/demo.qs'), 's3://example-bucket/backups/demo.qs')
        for uri in ['https://example.com/a.qs', 's3:///a.qs', 's3://bucket', 's3://bucket/a?x=y']:
            with self.subTest(uri=uri), self.assertRaises(ValueError): validate_s3_uri(uri)

    def test_backup_names_do_not_overwrite_or_create_subfolders(self):
        first = backup_key('backups/', '../../A / report')
        second = backup_key('backups/', '../../A / report')
        self.assertNotEqual(first, second)
        self.assertEqual(first.count('/'), 1)
        self.assertTrue(first.endswith('.qs'))

if __name__ == '__main__': unittest.main()
