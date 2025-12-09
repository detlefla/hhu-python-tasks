import cyclopts
import msgspec
import os
from pathlib import Path
try:
    from uuid import uuid7
except ImportError:
    from uuid_extension import uuid7
import xdg_base_dirs

from . import VERSION
from .commands import LocalRunner, SshRunner
from .options import get_options


APP_NAME = "hhu-tasks"
ENV_CONFIG = "HHU_CONFIG"
ENV_PROJECT = "HHU_PROJECT"
DEFAULT_CONFIG = xdg_base_dirs.xdg_config_home() / "hhu_tasks_config.yaml"
app = cyclopts.App(
        name = APP_NAME,
        version = VERSION,
        config = [
            cyclopts.config.Env("HHU_TASKS_"),
            cyclopts.config.Yaml(
                "hhu_tasks_config.yaml",
                search_parents = True,
                use_commands_as_keys = False,
                ),
            ]
        )


@app.command
def stage(
        target: str,
        name: str | None = None,
        project_group: str | None = None,
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path = DEFAULT_CONFIG,
        dry_run: bool = False,
        verbose: bool = False,
        ) -> None:
    """Deploy application to local directory or remote host"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            project_group = project_group,
            dry_run = dry_run,
            verbose = verbose,
            )
    # XXX get Python version from project or elsewhere …
    project_group_info = options.config.project_groups[options.project_group]
    if target.startswith("@"):
        targets = project_group_info.targets
        if target not in targets:
            raise ValueError("project group {options.project_group} has no target {target}")
        target_info = targets[target]
        host = target_info.host
        user = target_info.admin_user
        remdir = target_info.django_base / "versions"
        runner = SshRunner(hostname=host, remote_user=user,
                dry_run=dry_run, verbose=verbose)
    else:
        target_dir = Path(target).expanduser().absolute()
        host = None
        user = None
        remdir = target_dir / "versions"
        runner = LocalRunner(dry_run=dry_run, verbose=verbose)
    
    if name is None:
        deploy_id = str(uuid7())[:18].replace("-", "")
    else:
        deploy_id = name
    
    depldir = remdir / deploy_id
    
    runner.run(["mkdir", "-p", depldir])
    # XXX use Python version here
    runner.run(["uv", "init", "--bare", "--python", "3.12", depldir])
    
    local_modules = project_group_info.needs.copy()
    local_modules.append(project_group_info.main_package)
    for module in local_modules:
        module_path = options.config.editable_packages[module].location
        module_path = module_path.expanduser()
        runner.run(["uv", "build", "--project", module_path])
        prod_path = f"{module_path}[prod]"
        runner.run(["uv", "add", "--project", depldir, "--editable", prod_path])
    print(f"echo installation needs local_django_settings.py in production version")


@app.command
def deploy(
        target: str,
        name: str | None = None,
        project_group: str | None = None,
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path = DEFAULT_CONFIG,
        dry_run: bool = False,
        verbose: bool = False,
        ) -> None:
    """Deploy application to local directory or remote host"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            project_group = project_group,
            dry_run = dry_run,
            verbose = verbose,
            )
    # XXX get Python version from project or elsewhere …
    project_group_info = options.config.project_groups[options.project_group]
    if target.startswith("@"):
        targets = project_group_info.targets
        if target not in targets:
            raise ValueError("project group {options.project_group} has no target {target}")
        target_info = targets[target]
        host = target_info.host
        user = target_info.admin_user
        remdir = target_info.django_base / "versions"
        runner = SshRunner(hostname=host, remote_user=user,
                dry_run=dry_run, verbose=verbose)
    else:
        target_dir = Path(target).expanduser().absolute()
        host = None
        user = None
        remdir = target_dir / "versions"
        runner = LocalRunner(dry_run=dry_run, verbose=verbose)
    
    if name is None:
        deploy_id = str(uuid7())[:18].replace("-", "")
    else:
        deploy_id = name
    depldir = remdir / deploy_id
    
    runner.run(["wheel-getter", "--directory", options.project_dir])
    runner.run(["mkdir", "-p", remdir])
    # XXX user Python version here
    runner.run(["uv", "init", "--bare", "--python", "3.12", depldir])
    local_wheels = options.project_dir / "wheels"
    remote_wheels = depldir / "wheels"
    runner.run(["mkdir", remote_wheels])  # XXX within previous mkdir??
    # XXX unify rsync
    if host:
        runner.run(["rsync", "-avxc", f"{local_wheels}/",
                f"{user}@{host}:{depldir}/wheels/",
                f"--copy-dest={remdir}/active/",
                ])
    else:
        runner.run(["cp", "-R", local_wheels, depldir])
    main_pkg = f"{project_group_info.main_package}[prod]"
    runner.run(["uv", "add", "--project", depldir, main_pkg, "--no-index",
            "--find-links", depldir / "wheels"])
    
    print(f"echo needs local_django_settings.py in production version")


@app.command
def activate(
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path = DEFAULT_CONFIG,
        dry_run: bool = False,
        verbose: bool = False,
        ) -> None:
    """Activate deployed application"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            dry_run = dry_run,
            verbose = verbose,
            )


@app.command
def new_branch(
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path = DEFAULT_CONFIG,
        dry_run: bool = False,
        verbose: bool = False,
        ) -> None:
    """Deploy application to local directory or remote host"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            dry_run = dry_run,
            verbose = verbose,
            )


@app.command
def release(
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path = DEFAULT_CONFIG,
        dry_run: bool = False,
        verbose: bool = False,
        ) -> None:
    """Deploy application to local directory or remote host"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            dry_run = dry_run,
            verbose = verbose,
            )
