# Copyright (C) 2019-2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import sys
import tarfile
import time
from typing import List

import requests

from swh.storage import get_storage

from .base_check import BaseCheck


class NoDirectory(Exception):
    pass


class VaultCheck(BaseCheck):
    TYPE = "VAULT"
    DEFAULT_WARNING_THRESHOLD = 0
    DEFAULT_CRITICAL_THRESHOLD = 3600

    def __init__(self, obj):
        super().__init__(obj, application="vault")
        self._swh_storage = get_storage("remote", url=obj["swh_storage_url"])
        self._swh_web_url = obj["swh_web_url"]
        self._poll_interval = obj["poll_interval"]

        self.register_prometheus_gauge("status", "")
        self.register_prometheus_gauge("duration", "seconds", ["step", "status"])

    def _url_for_dir(self, dir_id):
        return self._swh_web_url + f"/api/1/vault/directory/{dir_id.hex()}/"

    def _pick_directory(self):
        dir_ = self._swh_storage.directory_get_random()
        if dir_ is None:
            raise NoDirectory()
        return dir_

    def _pick_uncached_directory(self):
        while True:
            dir_id = self._pick_directory()
            response = requests.get(self._url_for_dir(dir_id))
            if response.status_code == 404:
                return dir_id

    def _collect_prometheus_metrics(
        self, status: int, duration: float, labels: List[str]
    ) -> None:
        self.collect_prometheus_metric("status", status)
        self.collect_prometheus_metric(
            "duration",
            duration,
            labels,
        )

    def main(self):
        try:
            dir_id = self._pick_uncached_directory()
        except NoDirectory:
            self.print_result("CRITICAL", "No directory exists in the archive.")
            return 2

        start_time = time.time()
        total_time = 0
        response = requests.post(self._url_for_dir(dir_id))
        assert response.status_code == 200, (response, response.text)
        result = response.json()
        while result["status"] in ("new", "pending"):
            time.sleep(self._poll_interval)
            response = requests.get(self._url_for_dir(dir_id))
            assert response.status_code == 200, (response, response.text)
            result = response.json()

            total_time = time.time() - start_time

            if total_time > self.critical_threshold:
                self.print_result(
                    "CRITICAL",
                    f"cooking directory {dir_id.hex()} took more than "
                    f"{total_time:.2f}s and has status: "
                    f'{result["progress_message"]}',
                    total_time=total_time,
                )

                self._collect_prometheus_metrics(2, total_time, ["cooking", "timeout"])

                return 2

        if result["status"] == "failed":
            self.print_result(
                "CRITICAL",
                f"cooking directory {dir_id.hex()} took {total_time:.2f}s "
                f'and failed with: {result["progress_message"]}',
                total_time=total_time,
            )

            self._collect_prometheus_metrics(2, total_time, ["cooking", "failed"])

            return 2
        elif result["status"] != "done":
            self.print_result(
                "CRITICAL",
                f"cooking directory {dir_id.hex()} took {total_time:.2f}s "
                f'and resulted in unknown status: {result["status"]}',
                total_time=total_time,
            )

            self._collect_prometheus_metrics(2, total_time, ["cooking", "unknown"])
            return 2

        (status_code, status) = self.get_status(total_time)

        if "fetch_url" not in result:
            self.print_result(
                "CRITICAL",
                f"cooking directory {dir_id.hex()} took {total_time:.2f}s "
                f"and succeeded, but API response did not contain a fetch_url.",
                total_time=total_time,
            )
            self._collect_prometheus_metrics(2, total_time, ["fetch", "no_url"])
            return 2

        with requests.get(result["fetch_url"], stream=True) as fetch_response:
            try:
                fetch_response.raise_for_status()
            except requests.HTTPError:
                self.print_result(
                    "CRITICAL",
                    f"cooking directory {dir_id.hex()} took {total_time:.2f}s "
                    f"and succeeded, but fetch failed with status code "
                    f"{fetch_response.status_code}.",
                    total_time=total_time,
                )
                self._collect_prometheus_metrics(2, total_time, ["fetch", "error"])
                return 2

            content_type = fetch_response.headers.get("Content-Type")
            if content_type not in ("application/gzip", "application/octet-stream"):
                self.print_result(
                    "CRITICAL",
                    f"Unexpected Content-Type when downloading bundle: {content_type}",
                    total_time=total_time,
                )
                self._collect_prometheus_metrics(
                    2, total_time, ["download", "unexpected_content_type"]
                )
                return 2

            try:
                with tarfile.open(fileobj=fetch_response.raw, mode="r|gz") as tf:
                    # Note that we are streaming the tarfile from the network,
                    # so we are allowed at most one pass on the tf object;
                    # and the sooner we close it the better.
                    # Fortunately, checking only the first member is good enough:
                    tarinfo = tf.next()
                    swhid = f"swh:1:dir:{dir_id.hex()}"
                    if not tarinfo or (
                        tarinfo.name != swhid
                        and not tarinfo.name.startswith(f"{swhid}/")
                    ):
                        self.print_result(
                            "CRITICAL",
                            f"Unexpected member in tarball: {tarinfo.name}"
                            if tarinfo
                            else "Fetched tarball is empty",
                            total_time=total_time,
                        )
                        self._collect_prometheus_metrics(
                            2, total_time, ["check", "archive_content"]
                        )
                        return 2
            except tarfile.ReadError as e:
                self.print_result(
                    "CRITICAL",
                    f"ReadError while reading tarball: {e}",
                    total_time=total_time,
                )
                self._collect_prometheus_metrics(
                    2, total_time, ["check", "archive_content"]
                )
                return 2
            except tarfile.StreamError as e:
                if (
                    sys.version_info < (3, 11)
                    and e.args[0] == "seeking backwards is not allowed"
                ):
                    # Probably https://github.com/python/cpython/issues/91078
                    self.print_result(
                        "CRITICAL",
                        f"StreamError while reading tarball (empty file?): {e}",
                        total_time=total_time,
                    )
                    self._collect_prometheus_metrics(
                        2, total_time, ["check", "archive_content"]
                    )
                    return 2

                self.print_result(
                    "CRITICAL",
                    f"StreamError while reading tarball: {e}",
                    total_time=total_time,
                )
                self._collect_prometheus_metrics(
                    2, total_time, ["check", "archive_content"]
                )
                return 2

        self.print_result(
            status,
            f"cooking directory {dir_id.hex()} took {total_time:.2f}s "
            f"and succeeded.",
            total_time=total_time,
        )

        self._collect_prometheus_metrics(status_code, total_time, ["end", ""])
        return status_code
