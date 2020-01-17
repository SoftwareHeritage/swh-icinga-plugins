# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import io
import os
import tarfile
import time

from click.testing import CliRunner
import pytest

from swh.icinga_plugins.cli import cli
from .web_scenario import WebScenario


BASE_URL = 'http://swh-deposit.example.org/1'

COMMON_OPTIONS = [
    '--server', BASE_URL,
    '--username', 'test',
    '--password', 'test',
    '--collection', 'testcol',
]


SAMPLE_METADATA = '''
<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
xmlns:codemeta="https://doi.org/10.5063/SCHEMA/CODEMETA-2.0">
  <title>Test Software</title>
  <client>swh</client>
  <external_identifier>test-software</external_identifier>
  <codemeta:author>
    <codemeta:name>No One</codemeta:name>
  </codemeta:author>
</entry>
'''


ENTRY_TEMPLATE = '''
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <deposit_id>42</deposit_id>
    <deposit_date>2019-12-19 18:11:00</deposit_date>
    <deposit_archive>foo.tar.gz</deposit_archive>
    <deposit_status>{status}</deposit_status>

    <sword:packaging>http://purl.org/net/sword/package/SimpleZip</sword:packaging>
</entry>
'''


STATUS_TEMPLATE = '''
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <deposit_id>42</deposit_id>
    <deposit_status>{status}</deposit_status>
    <deposit_status_detail>{status_detail}</deposit_status_detail>
</entry>
'''


@pytest.fixture(scope='session')
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp(__name__)


@pytest.fixture(scope='session')
def sample_metadata(tmp_path):
    """Returns a sample metadata file's path

    """
    path = os.path.join(tmp_path, 'metadata.xml')

    with open(path, 'w') as fd:
        fd.write(SAMPLE_METADATA)

    return path


@pytest.fixture(scope='session')
def sample_archive(tmp_path):
    """Returns a sample archive's path

    """
    path = os.path.join(tmp_path, 'archive.tar.gz')

    with tarfile.open(path, 'w:gz') as tf:
        tf.addfile(
            tarfile.TarInfo('hello.py'),
            io.BytesIO(b'print("Hello world")'))

    return path


def invoke(args, catch_exceptions=False):
    runner = CliRunner()
    result = runner.invoke(cli, args)
    if not catch_exceptions and result.exception:
        print(result.output)
        raise result.exception
    return result


def test_deposit_immediate_success(
        requests_mock, mocker, sample_archive, sample_metadata, mocked_time):
    scenario = WebScenario()

    scenario.add_step(
        'post', BASE_URL + '/testcol/',
        ENTRY_TEMPLATE.format(status='done'))

    scenario.install_mock(requests_mock)

    result = invoke([
        'check-deposit',
        *COMMON_OPTIONS,
        'single',
        '--archive', sample_archive,
        '--metadata', sample_metadata,
    ])

    assert result.output == (
        "DEPOSIT OK - Deposit took 0.00s and succeeded.\n"
        "| 'load_time' = 0.00s\n"
        "| 'total_time' = 0.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 0.00s\n")
    assert result.exit_code == 0, result.output


def test_deposit_delays(
        requests_mock, mocker, sample_archive, sample_metadata, mocked_time):
    scenario = WebScenario()

    scenario.add_step(
        'post', BASE_URL + '/testcol/',
        ENTRY_TEMPLATE.format(status='deposited'))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='verified', status_detail=''))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='loading', status_detail=''))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='done', status_detail=''))

    scenario.install_mock(requests_mock)

    result = invoke([
        'check-deposit',
        *COMMON_OPTIONS,
        'single',
        '--archive', sample_archive,
        '--metadata', sample_metadata,
    ])

    assert result.output == (
        "DEPOSIT OK - Deposit took 30.00s and succeeded.\n"
        "| 'load_time' = 20.00s\n"
        "| 'total_time' = 30.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n")
    assert result.exit_code == 0, result.output


def test_deposit_delay_warning(
        requests_mock, mocker, sample_archive, sample_metadata, mocked_time):
    scenario = WebScenario()

    scenario.add_step(
        'post', BASE_URL + '/testcol/',
        ENTRY_TEMPLATE.format(status='deposited'))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='verified', status_detail=''))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='done', status_detail=''))

    scenario.install_mock(requests_mock)

    result = invoke([
        '--warning', '15',
        'check-deposit',
        *COMMON_OPTIONS,
        'single',
        '--archive', sample_archive,
        '--metadata', sample_metadata,
    ], catch_exceptions=True)

    assert result.output == (
        "DEPOSIT WARNING - Deposit took 20.00s and succeeded.\n"
        "| 'load_time' = 10.00s\n"
        "| 'total_time' = 20.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n")
    assert result.exit_code == 1, result.output


def test_deposit_delay_critical(
        requests_mock, mocker, sample_archive, sample_metadata, mocked_time):
    scenario = WebScenario()

    scenario.add_step(
        'post', BASE_URL + '/testcol/',
        ENTRY_TEMPLATE.format(status='deposited'))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='verified', status_detail=''))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='done', status_detail=''),
        callback=lambda: time.sleep(60))

    scenario.install_mock(requests_mock)

    result = invoke([
        '--critical', '50',
        'check-deposit',
        *COMMON_OPTIONS,
        'single',
        '--archive', sample_archive,
        '--metadata', sample_metadata,
    ], catch_exceptions=True)

    assert result.output == (
        "DEPOSIT CRITICAL - Deposit took 80.00s and succeeded.\n"
        "| 'load_time' = 70.00s\n"
        "| 'total_time' = 80.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n")
    assert result.exit_code == 2, result.output


def test_deposit_timeout(
        requests_mock, mocker, sample_archive, sample_metadata, mocked_time):
    scenario = WebScenario()

    scenario.add_step(
        'post', BASE_URL + '/testcol/',
        ENTRY_TEMPLATE.format(status='deposited'),
        callback=lambda: time.sleep(1500))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='verified', status_detail=''),
        callback=lambda: time.sleep(1500))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='loading', status_detail=''),
        callback=lambda: time.sleep(1500))

    scenario.install_mock(requests_mock)

    result = invoke([
        'check-deposit',
        *COMMON_OPTIONS,
        'single',
        '--archive', sample_archive,
        '--metadata', sample_metadata,
    ], catch_exceptions=True)

    assert result.output == (
        "DEPOSIT CRITICAL - Timed out while in status loading "
        "(4520.0s seconds since deposit started)\n"
        "| 'total_time' = 4520.00s\n"
        "| 'upload_time' = 1500.00s\n"
        "| 'validation_time' = 1510.00s\n")
    assert result.exit_code == 2, result.output


def test_deposit_rejected(
        requests_mock, mocker, sample_archive, sample_metadata, mocked_time):
    scenario = WebScenario()

    scenario.add_step(
        'post', BASE_URL + '/testcol/',
        ENTRY_TEMPLATE.format(status='deposited'))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='rejected', status_detail='booo'))

    scenario.install_mock(requests_mock)

    result = invoke([
        'check-deposit',
        *COMMON_OPTIONS,
        'single',
        '--archive', sample_archive,
        '--metadata', sample_metadata,
    ], catch_exceptions=True)

    assert result.output == (
        "DEPOSIT CRITICAL - Deposit was rejected: booo\n"
        "| 'total_time' = 10.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n")
    assert result.exit_code == 2, result.output


def test_deposit_failed(
        requests_mock, mocker, sample_archive, sample_metadata, mocked_time):
    scenario = WebScenario()

    scenario.add_step(
        'post', BASE_URL + '/testcol/',
        ENTRY_TEMPLATE.format(status='deposited'))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='verified', status_detail=''))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='loading', status_detail=''))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='failed', status_detail='booo'))

    scenario.install_mock(requests_mock)

    result = invoke([
        'check-deposit',
        *COMMON_OPTIONS,
        'single',
        '--archive', sample_archive,
        '--metadata', sample_metadata,
    ], catch_exceptions=True)

    assert result.output == (
        "DEPOSIT CRITICAL - Deposit loading failed: booo\n"
        "| 'load_time' = 20.00s\n"
        "| 'total_time' = 30.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n")
    assert result.exit_code == 2, result.output


def test_deposit_unexpected_status(
        requests_mock, mocker, sample_archive, sample_metadata, mocked_time):
    scenario = WebScenario()

    scenario.add_step(
        'post', BASE_URL + '/testcol/',
        ENTRY_TEMPLATE.format(status='deposited'))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='verified', status_detail=''))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='loading', status_detail=''))
    scenario.add_step(
        'get', BASE_URL + '/testcol/42/status/',
        STATUS_TEMPLATE.format(status='what', status_detail='booo'))

    scenario.install_mock(requests_mock)

    result = invoke([
        'check-deposit',
        *COMMON_OPTIONS,
        'single',
        '--archive', sample_archive,
        '--metadata', sample_metadata,
    ], catch_exceptions=True)

    assert result.output == (
        "DEPOSIT CRITICAL - Deposit got unexpected status: what (booo)\n"
        "| 'load_time' = 20.00s\n"
        "| 'total_time' = 30.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n")
    assert result.exit_code == 2, result.output
