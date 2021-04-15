# Copyright (C) 2019-2021  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from typing import List

from click.testing import CliRunner, Result

from swh.icinga_plugins.cli import icinga_cli_group


def invoke(args: List[str], catch_exceptions: bool = False) -> Result:
    """Invoke icinga plugin main cli command with args"""
    runner = CliRunner()
    result = runner.invoke(icinga_cli_group, args)
    if not catch_exceptions and result.exception:
        print(result.output)
        raise result.exception
    return result
