# SPDX-FileCopyrightText: 2024-present linuxdaemon <linuxdaemon.irc@gmail.com>
#
# SPDX-License-Identifier: MIT

import logging
from typing import TYPE_CHECKING, TextIO

import click
from gvm.connections import DebugConnection, UnixSocketConnection
from gvm.protocols.gmp import Gmp

from gvm_sync_targets import __version__
from gvm_sync_targets.models import GetTargetsResponse, ModelTransform
from gvm_sync_targets.util import get_all_hosts, read_lines

if TYPE_CHECKING:
    from gvm_sync_targets.models.targets_response import CreateTargetResponse


@click.group(
    context_settings={
        "help_option_names": ["-h", "--help"],
        "auto_envvar_prefix": "GVM",
    },
    invoke_without_command=True,
)
@click.version_option(version=__version__, prog_name="gvm-sync-targets")
@click.option("--username", show_envvar=True)
@click.option("--password", show_envvar=True)
@click.option(
    "--debug", is_flag=True, default=False, help="Enable debug logging"
)
@click.argument("hosts_file", type=click.File())
def gvm_sync_targets(
    username: str, password: str, debug: bool, hosts_file: TextIO
) -> None:
    if debug:
        logging.basicConfig(level="DEBUG", force=True)

    with Gmp(
        DebugConnection(UnixSocketConnection()),
        transform=ModelTransform(),
    ) as gmp:
        hosts = read_lines(hosts_file.read())
        gmp.authenticate(username, password)
        to_add = hosts.copy()
        to_remove: list[str] = []

        for host in get_all_hosts(gmp, details=True):
            ips = {
                identifier.value
                for identifier in host.identifiers.identifiers
                if identifier.name == "ip"
            }

            if len(ips) > 1:
                msg = f"Multiple IPs?: {ips}"
                raise ValueError(msg)

            for ip in ips:
                if ip in to_add:
                    to_add.remove(ip)
                else:
                    to_remove.append(host.uuid)

        for ip in set(to_add):
            gmp.create_host(ip)

        for uuid in set(to_remove):
            gmp.delete_host(uuid)

        targets: GetTargetsResponse = gmp.get_targets()
        for target in targets.targets:
            click.echo(target)

        resp: GetTargetsResponse = gmp.get_targets(
            filter_string='name="All Hosts"', tasks=True
        )

        if resp.targets:
            new_target: CreateTargetResponse = gmp.create_target(
                "All Hosts - temp", asset_hosts_filter=""
            )

            target = resp.targets[0]
            click.echo(target)
            task_ids = (
                [task.uuid for task in target.tasks.tasks]
                if target.tasks
                else []
            )

            for task_id in task_ids:
                gmp.modify_task(task_id, target_id=new_target.uuid)

            gmp.delete_target(target.uuid)
            gmp.modify_target(new_target.uuid, name="All Hosts")
        else:
            gmp.create_target("All Hosts", asset_hosts_filter="")

    click.echo(f"Added {len(to_add)} hosts, removed {len(to_remove)}.")
