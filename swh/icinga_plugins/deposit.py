# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import datetime
import sys
import time

from .base_check import BaseCheck

from swh.deposit.client import PublicApiDepositClient


class DepositCheck(BaseCheck):
    TYPE = 'DEPOSIT'
    DEFAULT_WARNING_THRESHOLD = 120
    DEFAULT_CRITICAL_THRESHOLD = 3600

    def __init__(self, obj):
        super().__init__(obj)
        self._poll_interval = obj['poll_interval']
        self._archive_path = obj['archive']
        self._metadata_path = obj['metadata']
        self._collection = obj['collection']

        self._client = PublicApiDepositClient({
            'url': obj['server'],
            'auth': {
                'username': obj['username'],
                'password': obj['password'],
            },
        })

    def upload_deposit(self):
        result = self._client.deposit_create(
            archive=self._archive_path, metadata=self._metadata_path,
            collection=self._collection, in_progress=False,
            slug='check-deposit-%s' % datetime.datetime.now().isoformat())
        self._deposit_id = result['deposit_id']
        return result

    def get_deposit_status(self):
        return self._client.deposit_status(
            collection=self._collection,
            deposit_id=self._deposit_id)

    def wait_while_status(self, statuses, start_time, metrics, result):
        while result['deposit_status'] in statuses:
            metrics['total_time'] = time.time() - start_time
            if metrics['total_time'] > self.critical_threshold:
                self.print_result(
                    'CRITICAL',
                    f'Timed out while in status '
                    f'{result["deposit_status"]} '
                    f'({metrics["total_time"]}s seconds since deposit '
                    f'started)',
                    **metrics)
                sys.exit(2)

            time.sleep(self._poll_interval)

            result = self.get_deposit_status()

        return result

    def main(self):
        start_time = time.time()
        metrics = {}

        # Upload the archive and metadata
        result = self.upload_deposit()
        metrics['upload_time'] = time.time() - start_time

        # Wait for validation
        result = self.wait_while_status(
            ['deposited'], start_time, metrics, result)
        metrics['total_time'] = time.time() - start_time
        metrics['validation_time'] = \
            metrics['total_time'] - metrics['upload_time']

        # Check validation succeeded
        if result['deposit_status'] == 'rejected':
            self.print_result(
                'CRITICAL',
                f'Deposit was rejected: {result["deposit_status_detail"]}',
                **metrics)
            return 2

        # Wait for loading
        result = self.wait_while_status(
            ['verified', 'loading'], start_time, metrics, result)
        metrics['total_time'] = time.time() - start_time
        metrics['load_time'] = (
            metrics['total_time'] - metrics['upload_time']
            - metrics['validation_time'])

        # Check loading succeeded
        if result['deposit_status'] == 'failed':
            self.print_result(
                'CRITICAL',
                f'Deposit loading failed: {result["deposit_status_detail"]}',
                **metrics)
            return 2

        # Check for unexpected status
        if result['deposit_status'] != 'done':
            self.print_result(
                'CRITICAL',
                f'Deposit got unexpected status: {result["deposit_status"]} '
                f'({result["deposit_status_detail"]})',
                **metrics)
            return 2

        # Everything went fine, check total time wasn't too large and
        # print result
        (status_code, status) = self.get_status(metrics['total_time'])
        self.print_result(
            status,
            f'Deposit took {metrics["total_time"]:.2f}s and succeeded.',
            **metrics)
        return status_code
