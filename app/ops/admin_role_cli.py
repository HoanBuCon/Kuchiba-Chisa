"""Grant or revoke the Admin role from the server shell (SEC-ADM-001, ROLE-010).

Usage (on the server, never through the API):
    scripts/ops/app_python.sh -m app.ops.admin_role_cli grant --account-id <uuid> --reason "<why>"
    scripts/ops/app_python.sh -m app.ops.admin_role_cli revoke --account-id <uuid> --reason "<why>"

This is the only code path that can change `role:admin:*`. It refuses to run inside the
API process and records `cli:<operator>@<host>` as the actor.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import socket
import sys
import uuid
from collections.abc import Sequence

from app.application.security.authz_service import (
    AccountNotFoundError,
    AuthzService,
    GrantIneligibleError,
    RoleChangeRejectedError,
)

API_PROCESS_MODULE = "app.main"
ACTOR_MAX_CHARS = 64
EXIT_OK = 0
EXIT_REFUSED = 2


class ApiProcessError(RuntimeError):
    """The CLI was started from a process that serves the API."""


def refuse_inside_api_process() -> None:
    if API_PROCESS_MODULE in sys.modules:
        raise ApiProcessError("the admin role CLI must not run inside the API process")


def cli_actor() -> str:
    return f"cli:{getpass.getuser()}@{socket.gethostname()}"[:ACTOR_MAX_CHARS]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grant or revoke the Admin role.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("grant", "revoke"):
        command = commands.add_parser(name)
        command.add_argument("--account-id", type=uuid.UUID, required=True)
        command.add_argument("--reason", required=True)
    return parser


async def run_command(
    service: AuthzService, session: object, command: str, account_id: uuid.UUID, reason: str
) -> str:
    actor = cli_actor()
    if command == "grant":
        await service.grant_admin(session, account_id=account_id, granted_by=actor, reason=reason)
        return f"granted admin to {account_id}"
    revoked = await service.revoke_admin(
        session, account_id=account_id, revoked_by=actor, reason=reason
    )
    return f"revoked admin from {account_id}" if revoked else f"{account_id} was not an admin"


async def _execute(args: argparse.Namespace) -> int:
    from app.application.dependencies import container
    from app.infrastructure.database.engine import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        try:
            message = await run_command(
                container.authz_service, session, args.command, args.account_id, args.reason
            )
        except (AccountNotFoundError, GrantIneligibleError, RoleChangeRejectedError) as error:
            await session.rollback()
            sys.stderr.write(f"refused: {error.__class__.__name__} {error}".strip() + os.linesep)
            return EXIT_REFUSED
        await session.commit()
    sys.stdout.write(message + os.linesep)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    refuse_inside_api_process()
    args = build_parser().parse_args(argv)
    return asyncio.run(_execute(args))


if __name__ == "__main__":
    raise SystemExit(main())
