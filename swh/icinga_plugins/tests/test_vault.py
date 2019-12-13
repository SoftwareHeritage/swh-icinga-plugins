# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import enum
import json
import re

from click.testing import CliRunner

from swh.icinga_plugins.cli import cli


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

    class Step(enum.Enum):
        NOTHING_DONE = 0
        CHECKED_UNCOOKED = 1
        REQUESTED_COOKING = 2

    step = Step.NOTHING_DONE

    def post_callback(request, context):
        nonlocal step
        if step == Step.CHECKED_UNCOOKED:
            step = Step.REQUESTED_COOKING
            return json.dumps(response_pending)
        else:
            assert False, step

    def get_callback(request, context):
        context.json = True
        nonlocal step
        if step == Step.NOTHING_DONE:
            context.status_code = 404
            step = Step.CHECKED_UNCOOKED
        elif step == Step.CHECKED_UNCOOKED:
            assert False
        elif step == Step.REQUESTED_COOKING:
            return json.dumps(response_done)
        else:
            assert False, step

    requests_mock.get(
        f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/',
        text=get_callback)
    requests_mock.post(
        f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/',
        text=post_callback)

    get_storage_mock = mocker.patch('swh.icinga_plugins.vault.get_storage')
    get_storage_mock.side_effect = FakeStorage

    sleep_mock = mocker.patch('time.sleep')

    result = invoke([
        '--swh-web-url', 'mock://swh-web.example.org',
        '--swh-storage-url', 'foo://example.org',
        'check-vault', 'directory',
    ])

    assert re.match(
        rf'VAULT OK - cooking directory {dir_id} took '
        r'[0-9]\.[0-9]{2}s and succeeded.\n'
        r"| 'total time' = [0-9]\.[0-9]{2}s",
        result.output)

    sleep_mock.assert_called_once_with(10)


def test_vault_delayed_success(requests_mock, mocker):

    class Step(enum.Enum):
        NOTHING_DONE = 0
        CHECKED_UNCOOKED = 1
        REQUESTED_COOKING = 2
        PENDING = 3

    step = Step.NOTHING_DONE

    def post_callback(request, context):
        nonlocal step
        if step == Step.CHECKED_UNCOOKED:
            step = Step.REQUESTED_COOKING
            return json.dumps(response_pending)
        else:
            assert False, step

    def get_callback(request, context):
        context.json = True
        nonlocal step
        if step == Step.NOTHING_DONE:
            context.status_code = 404
            step = Step.CHECKED_UNCOOKED
        elif step == Step.CHECKED_UNCOOKED:
            assert False
        elif step == Step.REQUESTED_COOKING:
            step = Step.PENDING
            return json.dumps(response_pending)
        elif step == Step.PENDING:
            return json.dumps(response_done)
        else:
            assert False, step

    requests_mock.get(
        f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/',
        text=get_callback)
    requests_mock.post(
        f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/',
        text=post_callback)

    get_storage_mock = mocker.patch('swh.icinga_plugins.vault.get_storage')
    get_storage_mock.side_effect = FakeStorage

    sleep_mock = mocker.patch('time.sleep')

    result = invoke([
        '--swh-web-url', 'mock://swh-web.example.org',
        '--swh-storage-url', 'foo://example.org',
        'check-vault', 'directory',
    ])

    assert re.match(
        rf'VAULT OK - cooking directory {dir_id} took '
        r'[0-9]\.[0-9]{2}s and succeeded.\n'
        r"| 'total time' = [0-9]\.[0-9]{2}s",
        result.output)

    assert sleep_mock.call_count == 2


def test_vault_failure(requests_mock, mocker):

    class Step(enum.Enum):
        NOTHING_DONE = 0
        CHECKED_UNCOOKED = 1
        REQUESTED_COOKING = 2

    step = Step.NOTHING_DONE

    def post_callback(request, context):
        nonlocal step
        if step == Step.CHECKED_UNCOOKED:
            step = Step.REQUESTED_COOKING
            return json.dumps(response_pending)
        else:
            assert False, step

    def get_callback(request, context):
        context.json = True
        nonlocal step
        if step == Step.NOTHING_DONE:
            context.status_code = 404
            step = Step.CHECKED_UNCOOKED
        elif step == Step.CHECKED_UNCOOKED:
            assert False
        elif step == Step.REQUESTED_COOKING:
            return json.dumps(response_failed)
        else:
            assert False, step

    requests_mock.get(
        f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/',
        text=get_callback)
    requests_mock.post(
        f'mock://swh-web.example.org/api/1/vault/directory/{dir_id}/',
        text=post_callback)

    get_storage_mock = mocker.patch('swh.icinga_plugins.vault.get_storage')
    get_storage_mock.side_effect = FakeStorage

    sleep_mock = mocker.patch('time.sleep')

    result = invoke([
        '--swh-web-url', 'mock://swh-web.example.org',
        '--swh-storage-url', 'foo://example.org',
        'check-vault', 'directory',
    ], catch_exceptions=True)

    assert re.match(
        rf'VAULT CRITICAL - cooking directory {dir_id} took '
        r'[0-9]\.[0-9]{2}s and failed with: foobar\n'
        r"| 'total time' = [0-9]\.[0-9]{2}s",
        result.output)

    sleep_mock.assert_called_once_with(10)
