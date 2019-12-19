# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import re
import time

from click.testing import CliRunner

from swh.icinga_plugins.cli import cli
from .web_scenario import WebScenario


dir_id = 'ab'*20

response_pending = {
    "obj_id": dir_id,
    "obj_type": "directory",
    "progress_message": "foo",
    "status": "pending"
}

response_done = {
    "fetch_url": f"/api/1/vault/directory/{dir_id}/raw/",
    "id": 9,
    "obj_id": dir_id,
    "obj_type": "directory",
    "status": "done"
}

response_failed = {
    "obj_id": dir_id,
    "obj_type": "directory",
    "progress_message": "foobar",
    "status": "failed"
}


class FakeStorage:
    def __init__(self, foo, **kwargs):
        pass

    def directory_get_random(self):
        return bytes.fromhex(dir_id)


def invoke(args, catch_exceptions=False):
    runner = CliRunner()
    result = runner.invoke(cli, args)
    if not catch_exceptions and result.exception:
        print(result.output)
        raise result.exception
    return result


def test_vault_immediate_success(requests_mock, mocker):
    scenario = WebScenario()

    url = f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/'

    scenario.add_step('get', url, {}, status_code=404)
    scenario.add_step('post', url, response_pending)
    scenario.add_step('get', url, response_done)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch('swh.icinga_plugins.vault.get_storage')
    get_storage_mock.side_effect = FakeStorage

    sleep_mock = mocker.patch('time.sleep')

    result = invoke([
        '--swh-web-url', 'mock://swh-web.example.org',
        '--swh-storage-url', 'foo://example.org',
        'check-vault', 'directory',
    ])

    assert re.match(
        rf'^VAULT OK - cooking directory {dir_id} took '
        r'[0-9]\.[0-9]{2}s and succeeded.\n'
        r"\| 'total_time' = [0-9]\.[0-9]{2}s$",
        result.output)
    assert result.exit_code == 0, result.output

    sleep_mock.assert_called_once_with(10)


def test_vault_delayed_success(requests_mock, mocker):
    scenario = WebScenario()

    url = f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/'

    scenario.add_step('get', url, {}, status_code=404)
    scenario.add_step('post', url, response_pending)
    scenario.add_step('get', url, response_pending)
    scenario.add_step('get', url, response_done)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch('swh.icinga_plugins.vault.get_storage')
    get_storage_mock.side_effect = FakeStorage

    sleep_mock = mocker.patch('time.sleep')

    result = invoke([
        '--swh-web-url', 'mock://swh-web.example.org',
        '--swh-storage-url', 'foo://example.org',
        'check-vault', 'directory',
    ])

    assert re.match(
        rf'^VAULT OK - cooking directory {dir_id} took '
        r'[0-9]\.[0-9]{2}s and succeeded.\n'
        r"\| 'total_time' = [0-9]\.[0-9]{2}s$",
        result.output)
    assert result.exit_code == 0, result.output

    assert sleep_mock.call_count == 2


def test_vault_failure(requests_mock, mocker):
    scenario = WebScenario()

    url = f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/'

    scenario.add_step('get', url, {}, status_code=404)
    scenario.add_step('post', url, response_pending)
    scenario.add_step('get', url, response_failed)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch('swh.icinga_plugins.vault.get_storage')
    get_storage_mock.side_effect = FakeStorage

    sleep_mock = mocker.patch('time.sleep')

    result = invoke([
        '--swh-web-url', 'mock://swh-web.example.org',
        '--swh-storage-url', 'foo://example.org',
        'check-vault', 'directory',
    ], catch_exceptions=True)

    assert re.match(
        rf'^VAULT CRITICAL - cooking directory {dir_id} took '
        r'[0-9]\.[0-9]{2}s and failed with: foobar\n'
        r"\| 'total_time' = [0-9]\.[0-9]{2}s\n$",
        result.output)
    assert result.exit_code == 2, result.output

    sleep_mock.assert_called_once_with(10)


def test_vault_timeout(requests_mock, mocker):
    time_offset = 0

    def increment_time():
        nonlocal time_offset
        time_offset += 4000

    scenario = WebScenario()

    url = f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/'

    scenario.add_step('get', url, {}, status_code=404)
    scenario.add_step('post', url, response_pending)
    scenario.add_step('get', url, response_pending)
    scenario.add_step('get', url, response_pending,
                      callback=increment_time)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch('swh.icinga_plugins.vault.get_storage')
    get_storage_mock.side_effect = FakeStorage

    sleep_mock = mocker.patch('time.sleep')

    real_time = time.time
    mocker.patch(
        'time.time', side_effect=lambda: real_time() + time_offset)

    result = invoke([
        '--swh-web-url', 'mock://swh-web.example.org',
        '--swh-storage-url', 'foo://example.org',
        'check-vault', 'directory',
    ], catch_exceptions=True)

    assert re.match(
        rf'^VAULT CRITICAL - cooking directory {dir_id} took more than '
        r'[0-9]+\.[0-9]{2}s and has status: foo\n'
        r"\| 'total_time' = [0-9]{4}\.[0-9]{2}s\n$",
        result.output)
    assert result.exit_code == 2, result.output

    assert sleep_mock.call_count == 2
