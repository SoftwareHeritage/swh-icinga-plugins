# Copyright (C) 2019-2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import pytest


@pytest.fixture
def mocked_time(mocker):
    start_time = 1646413359.0  # 2022-03-04-17:02:39Z

    time_offset = 0

    def fake_sleep(seconds):
        nonlocal time_offset
        time_offset += seconds

    def fake_time():
        return start_time + time_offset

    mocker.patch("time.sleep", side_effect=fake_sleep)
    mocker.patch("time.time", side_effect=fake_time)
