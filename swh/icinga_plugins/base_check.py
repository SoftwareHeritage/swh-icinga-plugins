# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


class BaseCheck:
    def __init__(self, obj):
        self.warning_threshold = obj.get(
            '_warning_threshold', self.DEFAULT_WARNING_THRESHOLD)
        self.critical_threshold = obj.get(
            '_critical_threshold', self.DEFAULT_CRITICAL_THRESHOLD)

    def get_status(self, value):
        if self.critical_threshold and value >= self.critical_threshold:
            return (2, 'CRITICAL')
        elif self.warning_threshold and value >= self.warning_threshold:
            return (1, 'WARNING')
        else:
            return (0, 'OK')
