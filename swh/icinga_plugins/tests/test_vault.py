# Copyright (C) 2019-2021  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import time

from swh.icinga_plugins.tests.utils import invoke

from .web_scenario import WebScenario

DIR_ID = "ab" * 20

url_api = f"mock://swh-web.example.org/api/1/vault/directory/{DIR_ID}/"
url_fetch = f"mock://swh-web.example.org/api/1/vault/directory/{DIR_ID}/raw/"

response_pending = {
    "obj_id": DIR_ID,
    "obj_type": "directory",
    "progress_message": "foo",
    "status": "pending",
}

response_done = {
    "fetch_url": url_fetch,
    "id": 9,
    "obj_id": DIR_ID,
    "obj_type": "directory",
    "status": "done",
}

response_done_no_fetch = {
    "id": 9,
    "obj_id": DIR_ID,
    "obj_type": "directory",
    "status": "done",
}

response_failed = {
    "obj_id": DIR_ID,
    "obj_type": "directory",
    "progress_message": "foobar",
    "status": "failed",
}

response_unknown_status = {
    "obj_id": DIR_ID,
    "obj_type": "directory",
    "progress_message": "what",
    "status": "boo",
}


class FakeStorage:
    def __init__(self, foo, **kwargs):
        pass

    def directory_get_random(self):
        return bytes.fromhex(DIR_ID)


def test_vault_immediate_success(requests_mock, mocker, mocked_time):
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_done)
    scenario.add_step("get", url_fetch, "xx" * 40)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ]
    )

    assert result.output == (
        f"VAULT OK - cooking directory {DIR_ID} took "
        f"10.00s and succeeded.\n"
        f"| 'total_time' = 10.00s\n"
    )
    assert result.exit_code == 0, result.output


def test_vault_delayed_success(requests_mock, mocker, mocked_time):
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_pending)
    scenario.add_step("get", url_api, response_done)
    scenario.add_step("get", url_fetch, "xx" * 40)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ]
    )

    assert result.output == (
        f"VAULT OK - cooking directory {DIR_ID} took "
        f"20.00s and succeeded.\n"
        f"| 'total_time' = 20.00s\n"
    )
    assert result.exit_code == 0, result.output


def test_vault_failure(requests_mock, mocker, mocked_time):
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_failed)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        f"VAULT CRITICAL - cooking directory {DIR_ID} took "
        f"10.00s and failed with: foobar\n"
        f"| 'total_time' = 10.00s\n"
    )
    assert result.exit_code == 2, result.output


def test_vault_unknown_status(requests_mock, mocker, mocked_time):
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_unknown_status)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        f"VAULT CRITICAL - cooking directory {DIR_ID} took "
        f"10.00s and resulted in unknown status: boo\n"
        f"| 'total_time' = 10.00s\n"
    )
    assert result.exit_code == 2, result.output


def test_vault_timeout(requests_mock, mocker, mocked_time):
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_pending)
    scenario.add_step(
        "get", url_api, response_pending, callback=lambda: time.sleep(4000)
    )

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        f"VAULT CRITICAL - cooking directory {DIR_ID} took more than "
        f"4020.00s and has status: foo\n"
        f"| 'total_time' = 4020.00s\n"
    )
    assert result.exit_code == 2, result.output


def test_vault_cached_directory(requests_mock, mocker, mocked_time):
    """First serves a directory that's already in the cache, to
    test that vault_check requests another one."""
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=200)
    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_done)
    scenario.add_step("get", url_fetch, "xx" * 40)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ]
    )

    assert result.output == (
        f"VAULT OK - cooking directory {DIR_ID} took "
        f"10.00s and succeeded.\n"
        f"| 'total_time' = 10.00s\n"
    )
    assert result.exit_code == 0, result.output


def test_vault_no_directory(requests_mock, mocker, mocked_time):
    """Tests with an empty storage"""
    scenario = WebScenario()
    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage
    mocker.patch(f"{__name__}.FakeStorage.directory_get_random", return_value=None)

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ],
        catch_exceptions=True,
    )

    assert result.output == ("VAULT CRITICAL - No directory exists in the archive.\n")
    assert result.exit_code == 2, result.output


def test_vault_immediate_success_but_fetch_failed(requests_mock, mocker, mocked_time):
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_done)
    scenario.add_step("get", url_fetch, "", status_code=500)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        f"VAULT CRITICAL - cooking directory {DIR_ID} took "
        f"10.00s and succeeded, but fetch failed with status code 500.\n"
        f"| 'total_time' = 10.00s\n"
    )
    assert result.exit_code == 2, result.output


def test_vault_immediate_success_but_fetch_empty(requests_mock, mocker, mocked_time):
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_done)
    scenario.add_step("get", url_fetch, "")

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        f"VAULT CRITICAL - cooking directory {DIR_ID} took "
        f"10.00s and succeeded, but fetch was empty.\n"
        f"| 'total_time' = 10.00s\n"
    )
    assert result.exit_code == 2, result.output


def test_vault_immediate_success_but_no_fetch_url(requests_mock, mocker, mocked_time):
    scenario = WebScenario()

    scenario.add_step("get", url_api, {}, status_code=404)
    scenario.add_step("post", url_api, response_pending)
    scenario.add_step("get", url_api, response_done_no_fetch)

    scenario.install_mock(requests_mock)

    get_storage_mock = mocker.patch("swh.icinga_plugins.vault.get_storage")
    get_storage_mock.side_effect = FakeStorage

    result = invoke(
        [
            "check-vault",
            "--swh-web-url",
            "mock://swh-web.example.org",
            "--swh-storage-url",
            "foo://example.org",
            "directory",
        ],
        catch_exceptions=True,
    )

    assert result.output == (
        f"VAULT CRITICAL - cooking directory {DIR_ID} took 10.00s and succeeded, "
        f"but API response did not contain a fetch_url.\n"
        f"| 'total_time' = 10.00s\n"
    )
    assert result.exit_code == 2, result.output
