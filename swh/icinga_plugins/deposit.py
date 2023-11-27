# Copyright (C) 2019-2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import datetime
import logging
import sys
import time
from typing import Any, Dict, Optional

import requests
from tenacity.before_sleep import before_sleep_log

from swh.core.retry import http_retry
from swh.deposit.client import PublicApiDepositClient

from .base_check import BaseCheck

logger = logging.getLogger(__name__)


@http_retry(
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def requests_get(url: str, params: Dict = {}):
    """Get queries with retry on throttling exception.

    Remaining issues (< 429) are to be dealt with with the client call code.

    """
    response = requests.get(url, params=params)

    if 429 <= response.status_code:
        response.raise_for_status()

    return response


class DepositCheck(BaseCheck):
    TYPE = "DEPOSIT"
    DEFAULT_WARNING_THRESHOLD = 120
    DEFAULT_CRITICAL_THRESHOLD = 3600

    def __init__(self, obj):
        super().__init__(obj, application="deposit")
        self.api_url = obj["swh_web_url"].rstrip("/")
        self._poll_interval = obj["poll_interval"]
        self._archive_path = obj["archive"]
        self._metadata_path = obj["metadata"]
        self._collection = obj["collection"]
        self._slug: Optional[str] = None
        self._provider_url = obj["provider_url"]

        self._client = PublicApiDepositClient(
            {
                "url": obj["server"],
                "auth": {"username": obj["username"], "password": obj["password"]},
            }
        )

        self.register_prometheus_gauge("duration", "seconds", ["step", "status"])
        self.register_prometheus_gauge("status", "")

    def upload_deposit(self):
        slug = (
            "check-deposit-%s"
            % datetime.datetime.fromtimestamp(time.time()).isoformat()
        )
        result = self._client.deposit_create(
            archive=self._archive_path,
            metadata=self._metadata_path,
            collection=self._collection,
            in_progress=False,
            slug=slug,
        )
        self._slug = slug
        self._deposit_id = result["deposit_id"]
        return result

    def update_deposit_with_metadata(self) -> Dict[str, Any]:
        """Trigger a metadata update on the deposit once it's completed."""
        deposit = self.get_deposit_status()
        swhid = deposit["deposit_swh_id"]
        assert deposit["deposit_id"] == self._deposit_id

        # We can reuse the initial metadata file we already sent
        return self._client.deposit_update(
            self._collection,
            self._deposit_id,
            self._slug,
            metadata=self._metadata_path,
            swhid=swhid,
        )

    def get_deposit_status(self):
        return self._client.deposit_status(
            collection=self._collection, deposit_id=self._deposit_id
        )

    def wait_while_status(self, statuses, start_time, metrics, result):
        while result["deposit_status"] in statuses:
            metrics["total_time"] = time.time() - start_time
            if metrics["total_time"] > self.critical_threshold:
                self.print_result(
                    "CRITICAL",
                    f"Timed out while in status "
                    f'{result["deposit_status"]} '
                    f'({metrics["total_time"]}s seconds since deposit '
                    f"started)",
                    **metrics,
                )

                self.collect_prometheus_metric(
                    "duration",
                    metrics["total_time"],
                    [result["deposit_status"], "timeout"],
                )
                self.collect_prometheus_metric(
                    "duration", metrics["total_time"], ["", "timeout"]
                )
                self.collect_prometheus_metric("status", 2)

                sys.exit(2)

            time.sleep(self._poll_interval)

            result = self.get_deposit_status()

        return result

    def main(self):
        start_time = time.time()
        start_datetime = datetime.datetime.fromtimestamp(
            start_time, tz=datetime.timezone.utc
        )
        metrics = {}

        # Upload the archive and metadata
        result = self.upload_deposit()
        metrics["upload_time"] = time.time() - start_time

        # Wait for validation
        result = self.wait_while_status(["deposited"], start_time, metrics, result)
        metrics["total_time"] = time.time() - start_time
        metrics["validation_time"] = metrics["total_time"] - metrics["upload_time"]

        # Check validation succeeded
        if result["deposit_status"] == "rejected":
            self.print_result(
                "CRITICAL",
                f'Deposit was rejected: {result["deposit_status_detail"]}',
                **metrics,
            )
            self.collect_prometheus_metric(
                "duration", metrics["validation_time"], ["validation", "rejected"]
            )
            self.collect_prometheus_metric(
                "duration", metrics["total_time"], ["validation", "rejected"]
            )
            self.collect_prometheus_metric("status", 2)
            return 2
        self.collect_prometheus_metric(
            "duration", metrics["validation_time"], ["validation", "ok"]
        )

        # Wait for loading
        result = self.wait_while_status(
            ["verified", "loading"], start_time, metrics, result
        )
        metrics["total_time"] = time.time() - start_time
        metrics["load_time"] = (
            metrics["total_time"] - metrics["upload_time"] - metrics["validation_time"]
        )
        self.collect_prometheus_metric(
            "duration", metrics["load_time"], ["loading", result["deposit_status"]]
        )

        # Check loading succeeded
        if result["deposit_status"] == "failed":
            self.print_result(
                "CRITICAL",
                f'Deposit loading failed: {result["deposit_status_detail"]}',
                **metrics,
            )
            self.collect_prometheus_metric(
                "duration", metrics["total_time"], ["total", "failed"]
            )
            self.collect_prometheus_metric("status", 2)
            return 2

        # Check for unexpected status
        if result["deposit_status"] != "done":
            self.print_result(
                "CRITICAL",
                f'Deposit got unexpected status: {result["deposit_status"]} '
                f'({result["deposit_status_detail"]})',
                **metrics,
            )
            self.collect_prometheus_metric(
                "duration", metrics["total_time"], ["total", result["deposit_status"]]
            )
            self.collect_prometheus_metric("status", 2)
            return 2

        # Get the SWHID
        if "deposit_swh_id" not in result:
            # if the deposit succeeded immediately (which is rare), it does not
            # contain the SWHID, so we need to re-fetch its status.
            result = self.get_deposit_status()
        if result.get("deposit_swh_id") is None:
            self.print_result(
                "CRITICAL",
                f"'deposit_swh_id' missing from result: {result!r}",
                **metrics,
            )
            return 2

        swhid = result["deposit_swh_id"]

        # Check for unexpected status
        if result["deposit_status"] != "done":
            self.print_result(
                "CRITICAL",
                f'Deposit status went from "done" to: {result["deposit_status"]} '
                f'({result["deposit_status_detail"]})',
                **metrics,
            )
            return 2

        # Get metadata list from swh-web
        response = requests_get(
            f"{self.api_url}/api/1/raw-extrinsic-metadata/swhid/{swhid}/",
            params={
                "authority": f"deposit_client {self._provider_url}",
                "after": start_datetime.isoformat(),
            },
        )
        status_code = response.status_code
        if status_code != 200 and status_code != 429:
            self.print_result(
                "CRITICAL",
                f"Getting the list of metadata returned code {response.status_code}: "
                f"{response.content!r}",
                **metrics,
            )
            return 2

        metadata_objects = response.json()
        expected_origin = f"{self._provider_url}/{self._slug}"

        # Filter out objects that were clearly not created by this deposit
        relevant_metadata_objects = [
            d for d in metadata_objects if d.get("origin") == expected_origin
        ]
        if not relevant_metadata_objects:
            self.print_result(
                "CRITICAL",
                f"No recent metadata on {swhid} with origin {expected_origin} in: "
                f"{metadata_objects!r}",
                **metrics,
            )
            return 2

        # Check the metadata was loaded as-is
        metadata_url = relevant_metadata_objects[0]["metadata_url"]
        metadata_file = requests_get(metadata_url).content
        with open(self._metadata_path, "rb") as fd:
            expected_metadata_file = fd.read()
        if metadata_file != expected_metadata_file:
            self.print_result(
                "CRITICAL",
                f"Metadata on {swhid} with origin {expected_origin} "
                f"(at {metadata_url}) differs from uploaded Atom document "
                f"(at {self._metadata_path})",
                **metrics,
            )
            return 2

        # Everything went fine, check total time wasn't too large and
        # print result
        (status_code, status) = self.get_status(metrics["total_time"])
        self.print_result(
            status,
            f'Deposit took {metrics["total_time"]:.2f}s and succeeded.',
            **metrics,
        )

        if status_code != 0:  # Stop if any problem in the initial scenario
            self.collect_prometheus_metric("status", status_code)
            return status_code

        # Initial deposit is now completed, now we can update the deposit with metadata
        result = self.update_deposit_with_metadata()
        total_time = time.time() - start_time
        metrics_update = {
            "total_time": total_time,
            "update_time": (
                total_time
                - metrics["upload_time"]
                - metrics["validation_time"]
                - metrics["load_time"]
            ),
        }

        if "error" in result:
            self.print_result(
                "CRITICAL",
                f'Deposit Metadata update failed: {result["error"]} ',
                **metrics_update,
            )
            self.collect_prometheus_metric(
                "duration", metrics["total_time"], ["total", "metadata_error"]
            )
            self.collect_prometheus_metric("status", 2)
            return 2

        (status_code, status) = self.get_status(metrics_update["total_time"])
        self.print_result(
            status,
            f'Deposit Metadata update took {metrics_update["update_time"]:.2f}s '
            "and succeeded.",
            **metrics_update,
        )

        self.collect_prometheus_metric(
            "duration", metrics["total_time"], ["total", "done"]
        )
        self.collect_prometheus_metric("status", status_code)
        return status_code
