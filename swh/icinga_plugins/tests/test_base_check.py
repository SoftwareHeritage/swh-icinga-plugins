# Copyright (C) 2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import pytest

from swh.icinga_plugins.base_check import BaseCheck


def test_inexistent_metric():
    base_check = BaseCheck({}, "test")

    with pytest.raises(ValueError, match="No metric unknown found"):
        base_check.collect_prometheus_metric("unknown", 10, [])


def test_environment():
    base_check = BaseCheck({"environment": "pytest"}, "test")

    with pytest.raises(ValueError, match="No metric unknown found"):
        base_check.collect_prometheus_metric("unknown", 10, [])


def test_application_not_defined():
    base_check = BaseCheck({"environment": "pytest"}, "test")
    base_check.register_prometheus_gauge("gauge", "seconds")
    base_check.application = None

    with pytest.raises(ValueError, match="Application name must be specified"):
        base_check.collect_prometheus_metric("gauge", 10, [])


def test_save_without_directory(tmpdir):
    config = {
        "prometheus_enabled": True,
    }

    base_check = BaseCheck(config, "test")

    with pytest.raises(AssertionError):
        base_check.save_prometheus_metrics()


def test_save(tmpdir):
    application = "my_application"
    config = {
        "prometheus_enabled": True,
        "prometheus_exporter_directory": tmpdir.strpath,
    }

    base_check = BaseCheck(config, application)
    base_check.register_prometheus_gauge("gauge", "count")
    base_check.collect_prometheus_metric("gauge", 10)
    base_check.save_prometheus_metrics()

    assert f"{tmpdir.strpath}/{application}.prom" in tmpdir.listdir()
