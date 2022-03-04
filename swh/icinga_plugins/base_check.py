# Copyright (C) 2019-2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from typing import Dict


class BaseCheck:
    DEFAULT_WARNING_THRESHOLD = 60
    DEFAULT_CRITICAL_THRESHOLD = 120

    def __init__(self, obj: Dict[str, str]) -> None:
        self.warning_threshold = float(
            obj.get("warning_threshold", self.DEFAULT_WARNING_THRESHOLD)
        )
        self.critical_threshold = float(
            obj.get("critical_threshold", self.DEFAULT_CRITICAL_THRESHOLD)
        )

    def get_status(self, value):
        if self.critical_threshold and value >= self.critical_threshold:
            return (2, "CRITICAL")
        elif self.warning_threshold and value >= self.warning_threshold:
            return (1, "WARNING")
        else:
            return (0, "OK")

    def print_result(self, status_type, status_string, **metrics):
        print(f"{self.TYPE} {status_type} - {status_string}")
        for (metric_name, metric_value) in sorted(metrics.items()):
            print(f"| '{metric_name}' = {metric_value:.2f}s")
