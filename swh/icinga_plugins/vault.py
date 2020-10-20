# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import time

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
        super().__init__(obj)
        self._swh_storage = get_storage("remote", url=obj["swh_storage_url"])
        self._swh_web_url = obj["swh_web_url"]
        self._poll_interval = obj["poll_interval"]

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
                return 2

        if result["status"] == "done":
            (status_code, status) = self.get_status(total_time)
            self.print_result(
                status,
                f"cooking directory {dir_id.hex()} took {total_time:.2f}s "
                f"and succeeded.",
                total_time=total_time,
            )
            return status_code
        elif result["status"] == "failed":
            self.print_result(
                "CRITICAL",
                f"cooking directory {dir_id.hex()} took {total_time:.2f}s "
                f'and failed with: {result["progress_message"]}',
                total_time=total_time,
            )
            return 2
        else:
            self.print_result(
                "CRITICAL",
                f"cooking directory {dir_id.hex()} took {total_time:.2f}s "
                f'and resulted in unknown status: {result["status"]}',
                total_time=total_time,
            )
            return 2
