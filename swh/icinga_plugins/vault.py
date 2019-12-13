# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import time

import requests

from swh.storage import get_storage


class NoDirectory(Exception):
    pass


class VaultCheck:
    def __init__(self, obj):
        self._swh_storage = get_storage('remote', url=obj['swh_storage_url'])
        self._swh_web_url = obj['swh_web_url']
        self._poll_interval = obj['poll_interval']

    def _url_for_dir(self, dir_id):
        return self._swh_web_url + f'/api/1/vault/directory/{dir_id.hex()}/'

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
            print('VAULT CRITICAL - No directory exists in the archive')
            return 2

        start_time = time.time()
        response = requests.post(self._url_for_dir(dir_id))
        assert response.status_code == 200, (response, response.text)
        result = response.json()
        while result['status'] in ('new', 'pending'):
            time.sleep(self._poll_interval)
            response = requests.get(self._url_for_dir(dir_id))
            assert response.status_code == 200, (response, response.text)
            result = response.json()

        end_time = time.time()
        total_time = end_time - start_time

        if result['status'] == 'done':
            print(f'VAULT OK - cooking directory {dir_id.hex()} '
                  f'took {total_time:.2f}s and succeeded.')
            print(f"| 'total time' = {total_time:.2f}s")
            return 0
        elif result['status'] == 'failed':
            print(f'VAULT CRITICAL - cooking directory {dir_id.hex()} '
                  f'took {total_time:.2f}s and failed with: '
                  f'{result["progress_message"]}')
            print(f"| 'total time' = {total_time:.2f}s")
            return 3
        else:
            print(f'VAULT CRITICAL - cooking directory {dir_id.hex()} '
                  f'took {total_time:.2f}s and resulted in unknown: '
                  f'status: {result["status"]}')
            print(f"| 'total time' = {total_time:.2f}s")
            return 3
