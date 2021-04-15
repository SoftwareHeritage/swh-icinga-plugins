# Copyright (C) 2021  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import time
from typing import Dict, List

import requests

from .base_check import BaseCheck

REPORT_MSG = "Save code now request for origin"

WAITING_STATUSES = ("not yet scheduled", "running", "scheduled")


class SaveCodeNowCheck(BaseCheck):
    TYPE = "SAVECODENOW"
    DEFAULT_WARNING_THRESHOLD = 60
    DEFAULT_CRITICAL_THRESHOLD = 120

    def __init__(self, obj: Dict, origin: str, visit_type: str) -> None:
        super().__init__(obj)
        self.api_url = obj["swh_web_url"].rstrip("/")
        self.poll_interval = obj["poll_interval"]
        self.origin = origin
        self.visit_type = visit_type

    @staticmethod
    def api_url_scn(root_api_url: str, origin: str, visit_type: str) -> str:
        """Compute the save code now api url for a given origin"""
        return f"{root_api_url}/api/1/origin/save/{visit_type}/url/{origin}/"

    def main(self) -> int:
        """Scenario description:

        1. Requests a save code now request via the api for origin self.origin with type
        self.visit_type.

        2. Polling regularly at self.poll_interval seconds the completion status.

        3. When either succeeded, failed or threshold exceeded, report approximate time
        of completion. This will warn if thresholds are exceeded.

        """
        start_time: float = time.time()
        total_time: float = 0.0
        scn_url = self.api_url_scn(self.api_url, self.origin, self.visit_type)
        response = requests.post(scn_url)
        assert response.status_code == 200, (response, response.text)

        result: Dict = response.json()

        status_key = "save_task_status"
        request_date = result["save_request_date"]
        origin_info = (self.visit_type, self.origin)

        while result[status_key] in WAITING_STATUSES:
            time.sleep(self.poll_interval)
            response = requests.get(scn_url)
            assert (
                response.status_code == 200
            ), "Unexpected response: {response}, {response.text}"
            raw_result: List[Dict] = response.json()
            assert len(raw_result) > 0, f"Unexpected result: {raw_result}"

            if len(raw_result) > 1:
                # retrieve only the one status result we are interested in
                result = next(
                    filter(lambda r: r["save_request_date"] == request_date, raw_result)
                )
            else:
                result = raw_result[0]

            # this because the api can return multiple entries for the same origin
            assert result["save_request_date"] == request_date

            total_time = time.time() - start_time

            if total_time > self.critical_threshold:
                self.print_result(
                    "CRITICAL",
                    f"{REPORT_MSG} {origin_info} took more than {total_time:.2f}s "
                    f'and has status: {result["save_task_status"]}.',
                    total_time=total_time,
                )
                return 2

        if result[status_key] == "succeeded":
            (status_code, status) = self.get_status(total_time)
            self.print_result(
                status,
                f"{REPORT_MSG} {origin_info} took {total_time:.2f}s and succeeded.",
                total_time=total_time,
            )
            return status_code
        elif result[status_key] == "failed":
            self.print_result(
                "CRITICAL",
                f"{REPORT_MSG} {origin_info} took {total_time:.2f}s and failed.",
                total_time=total_time,
            )
            return 2
        else:
            self.print_result(
                "CRITICAL",
                f"{REPORT_MSG} {origin_info} took {total_time:.2f}s "
                "and resulted in unsupported status: "
                f"{result['save_request_status']} ; {result[status_key]}.",
                total_time=total_time,
            )
            return 2
