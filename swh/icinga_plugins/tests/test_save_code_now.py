# Copyright (C) 2021  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from datetime import datetime, timezone
import random
from typing import Dict, Optional, Tuple

import pytest

from swh.icinga_plugins.save_code_now import (
    REPORT_MSG,
    WAITING_STATUSES,
    SaveCodeNowCheck,
)

from .utils import invoke
from .web_scenario import WebScenario


def fake_response(
    origin: str,
    visit_type: str,
    sor_status: str = "pending",
    task_status: Optional[str] = None,
) -> Dict:
    """Fake a save code now request api response"""
    visit_date = None
    if task_status in ("failed", "succeeded"):
        visit_date = str(datetime.now(tz=timezone.utc))

    return {
        "visit_type": visit_type,
        "origin_url": origin,
        "save_request_date": "to-replace",
        "save_request_status": sor_status,
        "save_task_status": task_status,
        "visit_date": visit_date,
    }


@pytest.fixture
def origin_info() -> Tuple[str, str]:
    """Build an origin info to request save code now

    """
    origin_name = random.choice(range(10))
    return random.choice(["git", "svn", "hg"]), f"mock://fake-origin-url/{origin_name}"


def test_save_code_now_success(requests_mock, mocker, mocked_time, origin_info):
    """Successful ingestion scenario below threshold"""
    scenario = WebScenario()
    visit_type, origin = origin_info

    root_api_url = "mock://swh-web.example.org"
    api_url = SaveCodeNowCheck.api_url_scn(root_api_url, origin, visit_type)

    # creation request
    scenario.add_step(
        "post",
        api_url,
        fake_response(origin, visit_type, "accepted", "not yet scheduled"),
    )
    response_scheduled = fake_response(origin, visit_type, "accepted", "scheduled")
    # status polling requests
    scenario.add_step("get", api_url, [response_scheduled])
    # sometimes we can have multiple response so we fake that here
    scenario.add_step("get", api_url, [response_scheduled, response_scheduled])
    scenario.add_step(
        "get", api_url, [fake_response(origin, visit_type, "accepted", "succeeded")]
    )
    scenario.install_mock(requests_mock)

    # fmt: off
    result = invoke(
        [
            "check-savecodenow", "--swh-web-url", root_api_url,
            "origin", origin,
            "--visit-type", visit_type,
        ]
    )
    # fmt: on

    assert result.output == (
        f"{SaveCodeNowCheck.TYPE} OK - {REPORT_MSG} {origin_info} took "
        f"30.00s and succeeded.\n"
        f"| 'total_time' = 30.00s\n"
    )
    assert result.exit_code == 0, f"Unexpected result: {result.output}"


def test_save_code_now_failure(requests_mock, mocker, mocked_time, origin_info):
    """Failed ingestion scenario should be reported"""
    scenario = WebScenario()
    visit_type, origin = origin_info

    root_api_url = "mock://swh-web.example.org"
    api_url = SaveCodeNowCheck.api_url_scn(root_api_url, origin, visit_type)

    # creation request
    scenario.add_step(
        "post",
        api_url,
        fake_response(origin, visit_type, "accepted", "not yet scheduled"),
    )
    # status polling requests
    scenario.add_step(
        "get", api_url, [fake_response(origin, visit_type, "accepted", "scheduled")]
    )
    scenario.add_step(
        "get", api_url, [fake_response(origin, visit_type, "accepted", "failed")]
    )
    scenario.install_mock(requests_mock)

    # fmt: off
    result = invoke(
        [
            "check-savecodenow", "--swh-web-url", root_api_url,
            "origin", origin,
            "--visit-type", visit_type,
        ],
        catch_exceptions=True,
    )
    # fmt: on

    assert result.output == (
        f"{SaveCodeNowCheck.TYPE} CRITICAL - {REPORT_MSG} {origin_info} took "
        f"20.00s and failed.\n"
        f"| 'total_time' = 20.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected result: {result.output}"


def test_save_code_now_pending_state_unsupported(
    requests_mock, mocker, mocked_time, origin_info
):
    """Pending save requests are not supported in the test so they should fail early

    Pending requests are requests that need a moderator to accept the repository into
    the save code now flow.

    Do not actually use such origin to trigger the checks.

    """
    scenario = WebScenario()
    visit_type, origin = origin_info
    root_api_url = "mock://swh-web2.example.org"
    api_url = SaveCodeNowCheck.api_url_scn(root_api_url, origin, visit_type)

    # creation request
    scenario.add_step(
        "post", api_url, fake_response(origin, visit_type, "pending", "not created"),
    )
    scenario.install_mock(requests_mock)

    # fmt: off
    result = invoke(
        [
            "check-savecodenow", "--swh-web-url", root_api_url,
            "origin", origin,
            "--visit-type", visit_type,
        ],
        catch_exceptions=True,
    )
    # fmt: on

    assert result.output == (
        f"{SaveCodeNowCheck.TYPE} CRITICAL - {REPORT_MSG} {origin_info} took "
        f"0.00s and resulted in unsupported status: pending ; not created.\n"
        f"| 'total_time' = 0.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_save_code_now_threshold_exceeded(
    requests_mock, mocker, mocked_time, origin_info
):
    """Saving requests exceeding threshold should mention warning in output

    """
    scenario = WebScenario()
    visit_type, origin = origin_info

    root_api_url = "mock://swh-web2.example.org"
    api_url = SaveCodeNowCheck.api_url_scn(root_api_url, origin, visit_type)

    # creation request
    scenario.add_step(
        "post",
        api_url,
        fake_response(origin, visit_type, "accepted", "not yet scheduled"),
    )

    # we'll make the response being in the awaiting status
    # beyond 13, this will exceed the threshold
    for i in range(13):
        waiting_status = random.choice(WAITING_STATUSES)
        response_scheduled = fake_response(
            origin, visit_type, "accepted", waiting_status
        )
        scenario.add_step("get", api_url, [response_scheduled])
    scenario.install_mock(requests_mock)

    # fmt: off
    result = invoke(
        [
            "check-savecodenow", "--swh-web-url", root_api_url,
            "origin", origin,
            "--visit-type", visit_type,
        ],
        catch_exceptions=True,
    )
    # fmt: on

    assert result.output == (
        f"{SaveCodeNowCheck.TYPE} CRITICAL - {REPORT_MSG} {origin_info} took "
        f"more than 130.00s and has status: {waiting_status}.\n"
        f"| 'total_time' = 130.00s\n"
    )
    assert result.exit_code == 2, f"Unexpected output: {result.output}"


def test_save_code_now_unexpected_failure(
    requests_mock, mocker, mocked_time, origin_info
):
    """Unexpected failure if the webapi refuses to answer for example"""
    scenario = WebScenario()
    visit_type, origin = origin_info

    root_api_url = "mock://swh-web.example.org"
    api_url = SaveCodeNowCheck.api_url_scn(root_api_url, origin, visit_type)

    # creation request
    scenario.add_step(
        "post",
        api_url,
        fake_response(origin, visit_type, "accepted", "not yet scheduled"),
    )
    # status polling requests
    scenario.add_step(
        "get", api_url, [fake_response(origin, visit_type, "accepted", "scheduled")]
    )
    # unexpected issue when communicating with the api
    scenario.add_step("get", api_url, {}, status_code=500)
    scenario.install_mock(requests_mock)

    with pytest.raises(AssertionError):
        # fmt: off
        invoke(
            [
                "check-savecodenow", "--swh-web-url", root_api_url,
                "origin", origin,
                "--visit-type", visit_type,
            ],
        )
        # fmt: on
