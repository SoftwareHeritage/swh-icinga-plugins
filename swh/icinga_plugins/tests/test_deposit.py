# Copyright (C) 2019-2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import datetime
import io
import os
import tarfile
import time
from typing import Optional

import pytest

from swh.icinga_plugins.tests.utils import invoke

from .web_scenario import WebScenario

POLL_INTERVAL = 10

BASE_URL = "http://swh-deposit.example.org/1"
BASE_WEB_URL = "http+mock://swh-web.example.org"
PROVIDER_URL = "http://icinga-checker.example.org"

COMMON_OPTIONS = [
    "--server",
    BASE_URL,
    "--username",
    "test",
    "--password",
    "test",
    "--collection",
    "testcol",
    "--swh-web-url",
    BASE_WEB_URL,
    "--provider-url",
    PROVIDER_URL,
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
       xmlns:swh="https://www.softwareheritage.org/schema/2018/deposit"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <swh:deposit_id>42</swh:deposit_id>
    <swh:deposit_date>2019-12-19 18:11:00</swh:deposit_date>
    <swh:deposit_archive>foo.tar.gz</swh:deposit_archive>
    <swh:deposit_status>{status}</swh:deposit_status>

    <sword:packaging>http://purl.org/net/sword/package/SimpleZip</sword:packaging>
</entry>
"""


STATUS_TEMPLATE = """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:swh="https://www.softwareheritage.org/schema/2018/deposit"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <swh:deposit_id>42</swh:deposit_id>
    <swh:deposit_status>{status}</swh:deposit_status>
    <swh:deposit_status_detail>{status_detail}</swh:deposit_status_detail>%s
</entry>
"""


def compute_origin():
    # This is the same origin the checker would compute, because we mock time.time
    # to be constant until time.sleep is called
    return (
        PROVIDER_URL
        + "/check-deposit-%s" % datetime.datetime.fromtimestamp(time.time()).isoformat()
    )


def status_template(
    status: str, status_detail: str = "", swhid: Optional[str] = None
) -> str:
    """Generate a proper status template out of status, status_detail and optional swhid"""
    if swhid is not None:
        template = (
            STATUS_TEMPLATE % f"\n    <swh:deposit_swh_id>{swhid}</swh:deposit_swh_id>"
        )
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
       xmlns:swh="https://www.softwareheritage.org/schema/2018/deposit"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <swh:deposit_id>42</swh:deposit_id>
    <swh:deposit_status>deposited</swh:deposit_status>
    <swh:deposit_status_detail></swh:deposit_status_detail>
</entry>
"""
    )

    actual_status = status_template(status="verified", status_detail="detail")
    assert (
        actual_status
        == """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:swh="https://www.softwareheritage.org/schema/2018/deposit"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <swh:deposit_id>42</swh:deposit_id>
    <swh:deposit_status>verified</swh:deposit_status>
    <swh:deposit_status_detail>detail</swh:deposit_status_detail>
</entry>
"""
    )

    actual_status = status_template(
        status="done", swhid="swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    )
    assert (
        actual_status
        == """
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:sword="http://purl.org/net/sword/"
       xmlns:swh="https://www.softwareheritage.org/schema/2018/deposit"
       xmlns:dcterms="http://purl.org/dc/terms/">
    <swh:deposit_id>42</swh:deposit_id>
    <swh:deposit_status>done</swh:deposit_status>
    <swh:deposit_status_detail></swh:deposit_status_detail>
    <swh:deposit_swh_id>swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74</swh:deposit_swh_id>
</entry>
"""
    )


@pytest.fixture(scope="session")
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp(__name__)


@pytest.fixture(scope="session")
def sample_metadata(tmp_path):
    """Returns a sample metadata file's path"""
    path = os.path.join(tmp_path, "metadata.xml")

    with open(path, "w") as fd:
        fd.write(SAMPLE_METADATA)

    return path


@pytest.fixture(scope="session")
def sample_archive(tmp_path):
    """Returns a sample archive's path"""
    path = os.path.join(tmp_path, "archive.tar.gz")

    with tarfile.open(path, "w:gz") as tf:
        tf.addfile(tarfile.TarInfo("hello.py"), io.BytesIO(b'print("Hello world")'))

    return path


def test_deposit_immediate_success(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    """Both deposit creation and deposit metadata update passed without delays"""
    origin = compute_origin()
    scenario = WebScenario()

    status_xml = status_template(
        status="done",
        status_detail="",
        swhid="swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74",
    )

    # Initial deposit
    scenario.add_step(
        "post",
        f"{BASE_URL}/testcol/",
        ENTRY_TEMPLATE.format(status="done"),
    )

    # Checker gets the SWHID
    swhid = "swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid=swhid,
    )
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", status_xml)

    # Then the checker checks the metadata appeared on the website
    scenario.add_step(
        "get",
        f"{BASE_WEB_URL}/api/1/raw-extrinsic-metadata/swhid/{swhid}/"
        f"?authority=deposit_client+http%3A%2F%2Ficinga-checker.example.org"
        f"&after=2022-03-04T17%3A02%3A39%2B00%3A00",
        [
            {
                "swhid": swhid,
                "origin": origin,
                "discovery_date": "2999-03-03T10:48:47+00:00",
                "metadata_url": f"{BASE_WEB_URL}/the-metadata-url",
            }
        ],
    )
    scenario.add_step("get", f"{BASE_WEB_URL}/the-metadata-url", SAMPLE_METADATA)

    # Then metadata update
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", status_xml)
    # internal deposit client does call status, then update metadata then status api
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_xml,
    )
    scenario.add_step(
        "put",
        f"{BASE_URL}/testcol/42/atom/",
        status_xml,
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_xml,
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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
    origin = compute_origin()

    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="loading"),
    )

    # Deposit done, checker gets the SWHID
    swhid = "swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid=swhid,
    )
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", status_xml)

    # Then the checker checks the metadata appeared on the website
    scenario.add_step(
        "get",
        f"{BASE_WEB_URL}/api/1/raw-extrinsic-metadata/swhid/{swhid}/"
        f"?authority=deposit_client+http%3A%2F%2Ficinga-checker.example.org"
        f"&after=2022-03-04T17%3A02%3A39%2B00%3A00",
        [
            {
                "swhid": swhid,
                "origin": origin,
                "discovery_date": "2999-03-03T10:48:47+00:00",
                "metadata_url": f"{BASE_WEB_URL}/the-metadata-url",
            }
        ],
    )
    scenario.add_step("get", f"{BASE_WEB_URL}/the-metadata-url", SAMPLE_METADATA)

    # Then metadata update
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", status_xml)
    # internal deposit client does call status, then update metadata then status api
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_xml,
    )
    scenario.add_step(
        "put",
        f"{BASE_URL}/testcol/42/atom/",
        status_xml,
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_xml,
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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
    """Deposit creation passed, deposit metadata update failed"""
    origin = compute_origin()
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="loading"),
    )

    # Deposit done, checker gets the SWHID
    swhid = "swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid=swhid,
    )
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", status_xml)

    # Then the checker checks the metadata appeared on the website
    scenario.add_step(
        "get",
        f"{BASE_WEB_URL}/api/1/raw-extrinsic-metadata/swhid/{swhid}/"
        f"?authority=deposit_client+http%3A%2F%2Ficinga-checker.example.org"
        f"&after=2022-03-04T17%3A02%3A39%2B00%3A00",
        [
            {
                "swhid": swhid,
                "origin": origin,
                "discovery_date": "2999-03-03T10:48:47+00:00",
                "metadata_url": f"{BASE_WEB_URL}/the-metadata-url",
            }
        ],
    )
    scenario.add_step("get", f"{BASE_WEB_URL}/the-metadata-url", SAMPLE_METADATA)

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
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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
    """Deposit creation exceeded delays, no deposit update occurred."""
    origin = compute_origin()
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )

    # Deposit done, checker gets the SWHID
    swhid = "swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid=swhid,
    )
    scenario.add_step("get", f"{BASE_URL}/testcol/42/status/", status_xml)

    # Then the checker checks the metadata appeared on the website
    scenario.add_step(
        "get",
        f"{BASE_WEB_URL}/api/1/raw-extrinsic-metadata/swhid/{swhid}/"
        f"?authority=deposit_client+http%3A%2F%2Ficinga-checker.example.org"
        f"&after=2022-03-04T17%3A02%3A39%2B00%3A00",
        [
            {
                "swhid": swhid,
                "origin": origin,
                "discovery_date": "2999-03-03T10:48:47+00:00",
                "metadata_url": f"{BASE_WEB_URL}/the-metadata-url",
            }
        ],
    )
    scenario.add_step("get", f"{BASE_WEB_URL}/the-metadata-url", SAMPLE_METADATA)

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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
    origin = compute_origin()
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )

    # Deposit done, checker gets the SWHID
    swhid = "swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid=swhid,
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_xml,
        callback=lambda: time.sleep(60),
    )

    # Then the checker checks the metadata appeared on the website
    scenario.add_step(
        "get",
        f"{BASE_WEB_URL}/api/1/raw-extrinsic-metadata/swhid/{swhid}/"
        f"?authority=deposit_client+http%3A%2F%2Ficinga-checker.example.org"
        f"&after=2022-03-04T17%3A02%3A39%2B00%3A00",
        [
            {
                "swhid": swhid,
                "origin": origin,
                "discovery_date": "2999-03-03T10:48:47+00:00",
                "metadata_url": f"{BASE_WEB_URL}/the-metadata-url",
            }
        ],
    )
    scenario.add_step("get", f"{BASE_WEB_URL}/the-metadata-url", SAMPLE_METADATA)

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "--critical",
            "50",
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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


def test_deposit_metadata_missing(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    origin = compute_origin()
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )

    # Deposit done, checker gets the SWHID
    swhid = "swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid=swhid,
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_xml,
    )

    # Then the checker checks the metadata appeared on the website
    metadata_list = [
        {
            # Filtered out, because wrong origin
            "swhid": swhid,
            "origin": "http://wrong-origin.example.org",
            "discovery_date": "2999-03-03T10:48:47+00:00",
            "metadata_url": f"{BASE_WEB_URL}/the-metadata-url",
        },
    ]
    scenario.add_step(
        "get",
        f"{BASE_WEB_URL}/api/1/raw-extrinsic-metadata/swhid/{swhid}/"
        f"?authority=deposit_client+http%3A%2F%2Ficinga-checker.example.org"
        f"&after=2022-03-04T17%3A02%3A39%2B00%3A00",
        metadata_list,
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
        f"DEPOSIT CRITICAL - No recent metadata on {swhid} with origin {origin} in: "
        f"{metadata_list!r}\n"
        "| 'load_time' = 10.00s\n"
        "| 'total_time' = 20.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_deposit_metadata_error(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )

    # Deposit done, checker gets the SWHID
    swhid = "swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid=swhid,
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_xml,
    )

    url_metadata = (
        f"{BASE_WEB_URL}/api/1/raw-extrinsic-metadata/swhid/{swhid}/"
        "?authority=deposit_client+http%3A%2F%2Ficinga-checker.example.org"
        "&after=2022-03-04T17%3A02%3A39%2B00%3A00"
    )
    # Then the checker checks the metadata appeared on the website, but the first time,
    # it's rate limited
    scenario.add_step(
        "get",
        url_metadata,
        # rate limited
        {},
        status_code=429,
    )
    # Then this fails to retrieve the response for some reason
    scenario.add_step(
        "get",
        url_metadata,
        "foo\nbar",
        status_code=400,
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
        "DEPOSIT CRITICAL - Getting the list of metadata returned code 400: "
        "b'foo\\nbar'\n"
        "| 'load_time' = 10.00s\n"
        "| 'total_time' = 20.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_deposit_metadata_corrupt(
    requests_mock, mocker, sample_archive, sample_metadata, mocked_time
):
    origin = compute_origin()
    scenario = WebScenario()

    scenario.add_step(
        "post", f"{BASE_URL}/testcol/", ENTRY_TEMPLATE.format(status="deposited")
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )

    # Deposit done, checker gets the SWHID
    swhid = "swh:1:dir:02ed6084fb0e8384ac58980e07548a547431cf74"
    status_xml = status_template(
        status="done",
        status_detail="",
        swhid=swhid,
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_xml,
    )

    # Then the checker checks the metadata appeared on the website
    metadata_list = [
        {
            "swhid": swhid,
            "origin": origin,
            "discovery_date": "2999-03-03T09:48:47+00:00",
            "metadata_url": f"{BASE_WEB_URL}/the-metadata-url",
        },
    ]
    scenario.add_step(
        "get",
        f"{BASE_WEB_URL}/api/1/raw-extrinsic-metadata/swhid/{swhid}/"
        f"?authority=deposit_client+http%3A%2F%2Ficinga-checker.example.org"
        f"&after=2022-03-04T17%3A02%3A39%2B00%3A00",
        metadata_list,
    )
    scenario.add_step(
        "get",
        f"{BASE_WEB_URL}/the-metadata-url",
        SAMPLE_METADATA[0:-1],  # corrupting the metadata by dropping the last byte
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
        f"DEPOSIT CRITICAL - Metadata on {swhid} with origin {origin} (at "
        f"{BASE_WEB_URL}/the-metadata-url) differs from uploaded Atom document (at "
        f"{sample_metadata})\n"
        "| 'load_time' = 10.00s\n"
        "| 'total_time' = 20.00s\n"
        "| 'upload_time' = 0.00s\n"
        "| 'validation_time' = 10.00s\n"
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
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="loading"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="failed", status_detail="booo"),
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="verified"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="loading"),
    )
    scenario.add_step(
        "get",
        f"{BASE_URL}/testcol/42/status/",
        status_template(status="what", status_detail="booo"),
    )

    scenario.install_mock(requests_mock)

    result = invoke(
        [
            "--prometheus-exporter",
            "--prometheus-exporter-directory",
            "/tmp",
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
