# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import sys

import click

from swh.core.cli import CONTEXT_SETTINGS

from .vault import VaultCheck


@click.group(name='icinga_plugins', context_settings=CONTEXT_SETTINGS)
@click.option('--swh-storage-url', type=str,
              help='URL to an swh-storage HTTP API')
@click.option('--swh-web-url', type=str,
              help='URL to an swh-web instance')
@click.option('-w', '--warning', type=int,
              help='Warning threshold.')
@click.option('-c', '--critical', type=int,
              help='Critical threshold.')
@click.pass_context
def cli(ctx, swh_storage_url, swh_web_url, warning, critical):
    """Main command for Icinga plugins
    """
    ctx.ensure_object(dict)
    ctx.obj['swh_storage_url'] = swh_storage_url
    ctx.obj['swh_web_url'] = swh_web_url
    ctx.obj['warning_threshold'] = warning
    ctx.obj['critical_threshold'] = critical


@cli.group(name='check-vault')
@click.option('--poll-interval', type=int, default=10,
              help='Interval (in seconds) between two polls to the API, '
                   'to check for cooking status.')
@click.pass_context
def check_vault(ctx, poll_interval):
    ctx.obj['poll_interval'] = poll_interval


@check_vault.command(name='directory')
@click.pass_context
def check_vault_directory(ctx):
    """Picks a random directory, requests its cooking via swh-web,
    and waits for completion."""
    sys.exit(VaultCheck(ctx.obj).main())
