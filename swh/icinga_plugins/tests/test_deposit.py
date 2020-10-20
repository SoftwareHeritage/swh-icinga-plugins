# Copyright (C) 2019-2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import io
import os
import tarfile
import time
from typing import Optional

from click.testing import CliRunner
import pytest

from swh.icinga_plugins.cli import icinga_cli_group

from .web_scenario import WebScenario

BASE_URL = "http://swh-deposit.example.org/1"

COMMON_OPTIONS = [
    "--server",
    BASE_URL,
    "--username",
    "test",
    "--password",
    "test",
    "--collection",
    "testcol",
]


SAMPLE_METADATA = """
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
"""


ENTRY_TEMPLATE = """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <deposit_id>42</deposit_id>
    <deposit_date>2019-12-19 18:11:00</deposit_date>
    <deposit_archive>foo.tar.gz</deposit_archive>
    <deposit_status>{status}</deposit_status>

    <sword:packaging>http://purl.org/net/sword/package/SimpleZip</sword:packaging>
</entry>
"""


STATUS_TEMPLATE = """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <deposit_id>42</deposit_id>
    <deposit_status>{status}</deposit_status>
    <deposit_status_detail>{status_detail}</deposit_status_detail>%s
</entry>
"""


def status_template(
    status: str, status_detail: str = "", swhid: Optional[str] = None
) -> str:
    """Generate a proper status template out of status, status_detail and optional swhid

    """
    if swhid is not None:
        template = STATUS_TEMPLATE % f"\n    <deposit_swh_id>{swhid}</deposit_swh_id>"
        return template.format(status=status, status_detail=status_detail, swhid=swhid)
    template = STATUS_TEMPLATE % ""
    return template.format(status=status, status_detail=status_detail)


def test_status_template():
    actual_status = status_template(status="deposited")
    assert (
        actual_status
        == """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <deposit_id>42</deposit_id>
    <deposit_status>deposited</deposit_status>
    <deposit_status_detail></deposit_status_detail>
</entry>
"""
    )

    actual_status = status_template(status="verified", status_detail="detail")
    assert (
        actual_status
        == """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <deposit_id>42</deposit_id>
    <deposit_status>verified</deposit_status>
    <deposit_status_detail>detail</deposit_status_detail>
</entry>
"""
    )

    actual_status = status_template(status="done", swhid="10")
    assert (
        actual_status
        == """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <deposit_id>42</deposit_id>
    <deposit_status>done</deposit_status>
    <deposit_status_detail></deposit_status_detail>
    <deposit_swh_id>10</deposit_swh_id>
</entry>
"""
    )


@pytest.fixture(scope="session")
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp(__name__)


@pytest.fixture(scope="session")
def sample_metadata(tmp_path):
    """Returns a sample metadata file's path

    """
    path = os.path.join(tmp_path, "metadata.xml")

    with open(path, "w") as fd:
        fd.write(SAMPLE_METADATA)

    return path


@pytest.fixture(scope="session")
def sample_archive(tmp_path):
    """Returns a sample archive's path

    """
    path = os.path.join(tmp_path, "archive.tar.gz")

    with tarfile.open(path, "w:gz") as tf:
        tf.addfile(tarfile.TarInfo("hello.py"), io.BytesIO(b'print("Hello world")'))

    return path


def invoke(args, catch_exceptions=False):
    runner = CliRunner()
    result = runner.invoke(icinga_cli_group, args)
    if not catch_exceptions and result.exception:
        print(result.output)
        raise result.exception
    return result


def test_deposit_immediate_success(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    """Both deposit creation and deposit metadata update passed without delays

    """
    scenario = WebScenario()

    status_xml = status_template(
        status="done",
        status_detail="",
        swhid="swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74",
    )

    # Initial deposit
    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="done")
    )
    # Then metadata update
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid="swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74",
    )
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", status_xml)
    # internal deposit client does call status, then update metadata then status api
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_xml,
    )
    scenario.add_step(
        "put", f"{BASE_URL}/testcol/42/metadata/", status_xml,
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_xml,
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ]
    )

    assert result.output == (
        "DEPOSIT OK - Deposit took 0.00s and succeeded.\n"
        "| 'load_time' = 0.00s\n"
        "| 'total_time' = 0.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 0.00s\n"
        "DEPOSIT OK - Deposit Metadata update took 0.00s and succeeded.\n"
        "| 'total_time' = 0.00s\n"
        "| 'update_time' = 0.00s\n"
    )
    assert result.exit_code == 0, f"Unexpected output: {result.output}"


def test_deposit_delays(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    """Deposit creation passed with some delays, deposit metadata update passed without
    delay

    """
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="verified"),
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="loading"),
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="done"),
    )
    # Then metadata update
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid="swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74",
    )
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", status_xml)
    # internal deposit client does call status, then update metadata then status api
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_xml,
    )
    scenario.add_step(
        "put", f"{BASE_URL}/testcol/42/metadata/", status_xml,
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_xml,
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ]
    )

    assert result.output == (
        "DEPOSIT OK - Deposit took 30.00s and succeeded.\n"
        "| 'load_time' = 20.00s\n"
        "| 'total_time' = 30.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
        "DEPOSIT OK - Deposit Metadata update took 0.00s and succeeded.\n"
        "| 'total_time' = 30.00s\n"
        "| 'update_time' = 0.00s\n"
    )
    assert result.exit_code == 0, f"Unexpected output: {result.output}"


def test_deposit_then_metadata_update_failed(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    """Deposit creation passed, deposit metadata update failed

    """
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="verified"),
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="loading"),
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="done"),
    )
    # Then metadata update calls
    failed_status_xml = status_template(
        status="failed",  # lying here
        status_detail="Failure to ingest",
        swhid="swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74",
    )
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", failed_status_xml)
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", failed_status_xml)

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        "DEPOSIT OK - Deposit took 30.00s and succeeded.\n"
        "| 'load_time' = 20.00s\n"
        "| 'total_time' = 30.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
        "DEPOSIT CRITICAL - Deposit Metadata update failed: You can only update "
        "metadata on deposit with status 'done' \n"
        "| 'total_time' = 30.00s\n"
        "| 'update_time' = 0.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_deposit_delay_warning(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    """Deposit creation exceeded delays, no deposit update occurred.

    """
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="verified"),
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="done"),
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "--warning",
            "15",
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        "DEPOSIT WARNING - Deposit took 20.00s and succeeded.\n"
        "| 'load_time' = 10.00s\n"
        "| 'total_time' = 20.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
    )
    assert result.exit_code == 1, f"Unexpected output: {result.output}"


def test_deposit_delay_critical(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="verified"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="done"),
        callback=lambda: time.sleep(60),
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "--critical",
            "50",
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        "DEPOSIT CRITICAL - Deposit took 80.00s and succeeded.\n"
        "| 'load_time' = 70.00s\n"
        "| 'total_time' = 80.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_deposit_timeout(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    scenario = WebScenario()

    scenario.add_step(
        "post",
        f"{BASE_URL}/testcol/",
        ENTRY_TEMPLATE.format(status="deposited"),
        callback=lambda: time.sleep(1500),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
        callback=lambda: time.sleep(1500),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="loading"),
        callback=lambda: time.sleep(1500),
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        "DEPOSIT CRITICAL - Timed out while in status loading "
        "(4520.0s seconds since deposit started)\n"
        "| 'total_time' = 4520.00s\n"
        "| 'upload_time' = 1500.00s\n"
        "| 'validation_time' = 1510.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_deposit_rejected(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="rejected", status_detail="booo"),
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        "DEPOSIT CRITICAL - Deposit was rejected: booo\n"
        "| 'total_time' = 10.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_deposit_failed(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="verified"),
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="loading"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="failed", status_detail="booo"),
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        "DEPOSIT CRITICAL - Deposit loading failed: booo\n"
        "| 'load_time' = 20.00s\n"
        "| 'total_time' = 30.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_deposit_unexpected_status(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="verified"),
    )
    scenario.add_step(
        "get", f"{BASE_URL}/testcol/42/status/", status_template(status="loading"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="what", status_detail="booo"),
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "check-deposit",
            *COMMON_OPTIONS,
            "single",
            "--archive",
            sample_archive,
            "--metadata",
            sample_metadata,
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        "DEPOSIT CRITICAL - Deposit got unexpected status: what (booo)\n"
        "| 'load_time' = 20.00s\n"
        "| 'total_time' = 30.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"
