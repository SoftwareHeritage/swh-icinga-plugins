# Copyright (C) 2019-2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

# WARNING: do not import unnecessary things here to keep cli startup time under
# control
import sys

import click

from swh.core.cli import CONTEXT_SETTINGS
from swh.core.cli import swh as swh_cli_group


@swh_cli_group.group(name="icinga_plugins", context_settings=CONTEXT_SETTINGS)
@click.option("-w", "--warning", type=int, help="Warning threshold.")
@click.option("-c", "--critical", type=int, help="Critical threshold.")
@click.pass_context
def icinga_cli_group(ctx, warning, critical):
    """Main command for Icinga plugins
    """
    ctx.ensure_object(dict)
    if warning:
        ctx.obj["warning_threshold"] = int(warning)
    if critical:
        ctx.obj["critical_threshold"] = int(critical)


@icinga_cli_group.group(name="check-vault")
@click.option(
    "--swh-storage-url", type=str, required=True, help="URL to an swh-storage HTTP API"
)
@click.option(
    "--swh-web-url", type=str, required=True, help="URL to an swh-web instance"
)
@click.option(
    "--poll-interval",
    type=int,
    default=10,
    help="Interval (in seconds) between two polls to the API, "
    "to check for cooking status.",
)
@click.pass_context
def check_vault(ctx, **kwargs):
    ctx.obj.update(kwargs)


@check_vault.command(name="directory")
@click.pass_context
def check_vault_directory(ctx):
    """Picks a random directory, requests its cooking via swh-web,
    and waits for completion."""
    from .vault import VaultCheck

    sys.exit(VaultCheck(ctx.obj).main())


@icinga_cli_group.group(name="check-deposit")
@click.option(
    "--server",
    type=str,
    default="https://deposit.softwareheritage.org/1",
    help="URL to the SWORD server to test",
)
@click.option("--username", type=str, required=True, help="Login for the SWORD server")
@click.option(
    "--password", type=str, required=True, help="Password for the SWORD server"
)
@click.option(
    "--collection",
    type=str,
    required=True,
    help="Software collection to use on the SWORD server",
)
@click.option(
    "--poll-interval",
    type=int,
    default=10,
    help="Interval (in seconds) between two polls to the API, "
    "to check for ingestion status.",
)
@click.pass_context
def check_deposit(ctx, **kwargs):
    ctx.obj.update(kwargs)


@check_deposit.command(name="single")
@click.option(
    "--archive", type=click.Path(), required=True, help="Software artefact to upload"
)
@click.option(
    "--metadata",
    type=click.Path(),
    required=True,
    help="Metadata file for the software artefact.",
)
@click.pass_context
def check_deposit_single(ctx, **kwargs):
    """Checks the provided archive and metadata file and be deposited."""
    from .deposit import DepositCheck

    ctx.obj.update(kwargs)
    sys.exit(DepositCheck(ctx.obj).main())
