from typing import Optional, cast

import click
from noneprompt import Choice, ListPrompt, InputPrompt, CancelledError

from nb_cli import _
from nb_cli.config import GLOBAL_CONFIG
from nb_cli.cli.utils import find_exact_package
from nb_cli.cli import (
    CLI_DEFAULT_STYLE,
    ClickAliasedGroup,
    back_,
    exit_,
    run_sync,
    run_async,
)
from nb_cli.handlers import (
    list_drivers,
    call_pip_update,
    call_pip_install,
    call_pip_uninstall,
    format_package_results,
)


@click.group(
    cls=ClickAliasedGroup, invoke_without_command=True, help=_("Manage bot driver.")
)
@click.pass_context
@run_async
async def driver(ctx: click.Context):
    if ctx.invoked_subcommand is not None:
        return

    command = cast(ClickAliasedGroup, ctx.command)

    choices: list[Choice[click.Command]] = []
    for sub_cmd_name in await run_sync(command.list_commands)(ctx):
        if sub_cmd := await run_sync(command.get_command)(ctx, sub_cmd_name):
            choices.append(
                Choice(
                    sub_cmd.help
                    or _("Run subcommand {sub_cmd.name!r}").format(sub_cmd=sub_cmd),
                    sub_cmd,
                )
            )
    if ctx.parent and ctx.parent.params.get("can_back_to_parent", False):
        _exit_choice = Choice(_("Back to top level."), back_)
    else:
        _exit_choice = Choice(_("Exit NB CLI."), exit_)
    choices.append(_exit_choice)

    while True:
        try:
            result = await ListPrompt(
                _("What do you want to do?"), choices=choices
            ).prompt_async(style=CLI_DEFAULT_STYLE)
        except CancelledError:
            result = _exit_choice

        sub_cmd = result.data
        if sub_cmd == back_:
            return
        ctx.params["can_back_to_parent"] = True
        await run_sync(ctx.invoke)(sub_cmd)


@driver.command(
    name="list", help=_("List nonebot drivers published on nonebot homepage.")
)
@click.option(
    "--include-unpublished",
    is_flag=True,
    default=False,
    flag_value=True,
    help=_("Whether to include unpublished drivers."),
)
@run_async
async def list_(include_unpublished: bool = False):
    drivers = await list_drivers(include_unpublished=include_unpublished)
    if include_unpublished:
        click.secho(_("WARNING: Unpublished drivers may be included."), fg="yellow")
    click.echo(format_package_results(drivers))


@driver.command(help=_("Search for nonebot drivers published on nonebot homepage."))
@click.option(
    "--include-unpublished",
    is_flag=True,
    default=False,
    flag_value=True,
    help=_("Whether to include unpublished drivers."),
)
@click.argument("name", nargs=1, default=None)
@run_async
async def search(name: Optional[str], include_unpublished: bool = False):
    if name is None:
        name = await InputPrompt(_("Driver name to search:")).prompt_async(
            style=CLI_DEFAULT_STYLE
        )
    drivers = await list_drivers(name, include_unpublished=include_unpublished)
    if include_unpublished:
        click.secho(_("WARNING: Unpublished drivers may be included."), fg="yellow")
    click.echo(format_package_results(drivers))


@driver.command(
    aliases=["add"],
    context_settings={"ignore_unknown_options": True},
    help=_("Install nonebot driver to current project."),
)
@click.option(
    "--include-unpublished",
    is_flag=True,
    default=False,
    flag_value=True,
    help=_("Whether to include unpublished drivers."),
)
@click.argument("name", nargs=1, default=None)
@click.argument("pip_args", nargs=-1, default=None)
@run_async
async def install(
    name: Optional[str],
    pip_args: Optional[list[str]],
    include_unpublished: bool = False,
):
    try:
        driver = await find_exact_package(
            _("Driver name to install:"),
            name,
            await list_drivers(include_unpublished=include_unpublished),
        )
    except CancelledError:
        return

    if include_unpublished:
        click.secho(
            _(
                "WARNING: Unpublished drivers may be installed. "
                "These drivers may be unmaintained or unusable."
            ),
            fg="yellow",
        )

    if driver.project_link:
        proc = await call_pip_install(driver.project_link, pip_args)
        if await proc.wait() != 0:
            click.secho(
                _(
                    "Errors occurred in installing driver {driver.name}. Aborted."
                ).format(driver=driver),
                fg="red",
            )
            return

    try:
        GLOBAL_CONFIG.add_dependency(driver)
    except RuntimeError as e:
        click.echo(
            _("Failed to add driver {driver.name} to dependencies: {e}").format(
                driver=driver, e=e
            )
        )


@driver.command(
    context_settings={"ignore_unknown_options": True}, help=_("Update nonebot driver.")
)
@click.option(
    "--include-unpublished",
    is_flag=True,
    default=False,
    flag_value=True,
    help=_("Whether to include unpublished drivers."),
)
@click.argument("name", nargs=1, default=None)
@click.argument("pip_args", nargs=-1, default=None)
@run_async
async def update(
    name: Optional[str],
    pip_args: Optional[list[str]],
    include_unpublished: bool = False,
):
    try:
        driver = await find_exact_package(
            _("Driver name to update:"),
            name,
            await list_drivers(include_unpublished=include_unpublished),
        )
    except CancelledError:
        return

    if include_unpublished:
        click.secho(
            _(
                "WARNING: Unpublished drivers may be installed. "
                "These drivers may be unmaintained or unusable."
            ),
            fg="yellow",
        )

    if driver.project_link:
        proc = await call_pip_update(driver.project_link, pip_args)
        if await proc.wait() != 0:
            click.secho(
                _("Errors occurred in updating driver {driver.name}. Aborted.").format(
                    driver=driver
                ),
                fg="red",
            )
            return

    try:
        GLOBAL_CONFIG.update_dependency(driver)
    except RuntimeError as e:
        click.echo(
            _("Failed to update driver {driver.name} to dependencies: {e}").format(
                driver=driver, e=e
            )
        )


@driver.command(
    aliases=["remove"],
    context_settings={"ignore_unknown_options": True},
    help=_("Uninstall nonebot driver from current project."),
)
@click.argument("name", nargs=1, default=None)
@click.argument("pip_args", nargs=-1, default=None)
@run_async
async def uninstall(name: Optional[str], pip_args: Optional[list[str]]):
    try:
        driver = await find_exact_package(
            _("Driver name to uninstall:"),
            name,
            await list_drivers(
                include_unpublished=True  # unpublished modules are always removable
            ),
        )
    except CancelledError:
        return

    try:
        GLOBAL_CONFIG.remove_dependency(driver)
        GLOBAL_CONFIG.add_dependency("nonebot2")  # hold a nonebot2 package
    except RuntimeError as e:
        click.echo(
            _("Failed to remove driver {driver.name} from dependencies: {e}").format(
                driver=driver, e=e
            )
        )

    if package := driver.project_link:
        if package.startswith("nonebot2[") and package.endswith("]"):
            package = package[9:-1]

        proc = await call_pip_uninstall(package, pip_args)
        await proc.wait()
