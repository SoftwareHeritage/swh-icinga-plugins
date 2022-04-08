# Copyright (C) 2019-2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information
import atexit
from typing import Any, Dict, List

from prometheus_client import CollectorRegistry, Gauge, Summary, write_to_textfile


class BaseCheck:
    DEFAULT_WARNING_THRESHOLD = 60
    DEFAULT_CRITICAL_THRESHOLD = 120
    PROMETHEUS_METRICS_BASENAME = "swh_e2e_"

    def __init__(self, obj: Dict[str, str], application: str):
        self.warning_threshold = float(
            obj.get("warning_threshold", self.DEFAULT_WARNING_THRESHOLD)
        )
        self.critical_threshold = float(
            obj.get("critical_threshold", self.DEFAULT_CRITICAL_THRESHOLD)
        )
        self.prometheus_enabled = obj.get("prometheus_enabled")
        self.prometheus_exporter_directory = obj.get("prometheus_exporter_directory")
        self.environment = obj.get("environment")
        self.application = application

        # A new registry is created to not export the default process metrics
        self.registry = CollectorRegistry()

        self.prometheus_metrics: Dict[str, Any] = {}

        atexit.register(self.save_prometheus_metrics)

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

    def collect_prometheus_metric(
        self, name: str, value: float, labels: List[str] = []
    ):
        g = self.prometheus_metrics.get(self.PROMETHEUS_METRICS_BASENAME + name)

        if g is None:
            raise ValueError(f"No metric {name} found")

        g.labels(*self._get_label_values(labels)).set(value)

    def _get_label_values(self, labels: List[str]) -> List[str]:
        label_list = []

        if self.environment:
            label_list.append(self.environment)

        if self.application is None:
            raise ValueError("Application name must be specified")
        label_list.append(self.application)

        return label_list + labels

    def _get_label_names(self, values: List[str] = []) -> List[str]:
        full_list = []

        if self.environment:
            full_list.append(self.environment)
        full_list.append("application")

        full_list += values

        return full_list

    def register_prometheus_summary(
        self, name: str, unit: str, labels: List[str] = []
    ) -> None:
        full_name = self.PROMETHEUS_METRICS_BASENAME + name

        self.prometheus_metrics[full_name] = Summary(
            full_name,
            "",
            registry=self.registry,
            unit=unit,
            labelnames=self._get_label_names(labels),
        )

    def register_prometheus_gauge(
        self, name: str, unit: str, labels: List[str] = []
    ) -> None:
        full_name = self.PROMETHEUS_METRICS_BASENAME + name

        self.prometheus_metrics[full_name] = Gauge(
            name=full_name,
            documentation="",
            registry=self.registry,
            unit=unit,
            labelnames=self._get_label_names(labels),
        )

    def save_prometheus_metrics(self) -> None:
        """Dump on disk the .prom file containing the
        metrics collected during the check execution.

        It's a callback method triggered by the atexit
        declared in the constructor."""
        if self.prometheus_enabled:
            assert self.prometheus_exporter_directory is not None

            filename = (
                self.prometheus_exporter_directory + "/" + self.application + ".prom"
            )
            write_to_textfile(filename, self.registry)
