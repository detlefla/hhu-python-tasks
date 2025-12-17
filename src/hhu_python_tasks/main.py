import cyclopts
import logging
import msgspec
import os
from pathlib import Path
from rich import print
from rich.logging import RichHandler
import subprocess
from uuid_extension import uuid7
import xdg_base_dirs

from . import VERSION
from .commands import LocalRunner, SshRunner
from .options import get_options


APP_NAME = "hhu-tasks"
ENV_CONFIG = "HHU_CONFIG"
ENV_PROJECT = "HHU_PROJECT"
DEFAULT_CONFIG = xdg_base_dirs.xdg_config_home() / "hhu_tasks_config.yaml"


logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
        )
logger = logging.getLogger("hhu_tasks")
app = cyclopts.App(
        name = APP_NAME,
        version = VERSION,
#        config = [
#            cyclopts.config.Env("HHU_TASKS_"),
#            cyclopts.config.Yaml(
#                "hhu_tasks_config.yaml",
#                search_parents = True,
#                use_commands_as_keys = False,
#                ),
#            ],
        )


@app.command
def stage(
        name: str | None = None,
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path | None = None,
        python_version: str | None = None,
        dry_run: bool = False,
        verbose: bool = False,
        debug: bool = False,
        ) -> None:
    """Deploy application to local directory or remote host"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            python_version = python_version,
            dry_run = dry_run,
            verbose = verbose,
            debug = debug,
            )
    
    if name is None:
        deploy_id = str(uuid7())[:18].replace("-", "")
    else:
        deploy_id = name
    
    target_dir = options.base_dir / "stage"
    deploy_dir = target_dir / deploy_id
    
    runner = LocalRunner(dry_run=dry_run, verbose=verbose)
    
    runner.run(["mkdir", "-p", deploy_dir])
    runner.run(["uv", "init", "--bare", "--python", options.python_version, deploy_dir])
    runner.run(["uv", "python", "pin", "--project", deploy_dir, options.python_version])
    
    local_modules = options.config.needs.copy()
    local_modules.append(options.config.main_package)
    for module in local_modules:
        module_path = options.config.editable_packages[module].location
        module_path = module_path.expanduser()
        runner.run(["uv", "build", "--project", module_path])
        prod_path = f"{module_path}[prod]"
        runner.run(["uv", "add", "--project", deploy_dir, "--editable", prod_path])


@app.command
def deploy(
        target: str | None = None,
        name: str | None = None,
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path | None = None,
        python_version: str | None = None,
        dry_run: bool = False,
        verbose: bool = False,
        debug: bool = False,
        ) -> None:
    """Deploy application to local directory or remote host"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            python_version = python_version,
            dry_run = dry_run,
            verbose = verbose,
            debug = debug,
            )
    
    if name is not None:
        deploy_id = name
    else:
        hi_name = ""
        stages = options.base_dir / "stage"
        for n in stages.iterdir():
            if not (stages / n).is_dir():
                continue
            n_str = str(n.name)
            if n_str > hi_name:
                hi_name = n_str
        if not hi_name:
            raise ValueError("no staging project found")
        deploy_id = hi_name
    # print(f"{options.base_dir=}, {deploy_id=}, {hi_name=}")
    staging_dir = options.base_dir / "stage" / deploy_id
    
    remote_deployment = False
    runner: SshRunner | LocalRunner
    if target and target.startswith("@"):
        targets = options.config.targets
        if target not in targets:
            raise ValueError("project group {options.project_group} has no target {target}")
        target_info = targets[target]
        host = target_info.host
        if not host:
            raise ValueError("no host given for target {target}")
        user = target_info.admin_user
        if not user:
            raise ValueError("no admin user given for target {target}")
        django_base = target_info.django_base or Path("/home") / str(target_info.app_user)
        target_dir = django_base / "versions"
        deploy_dir = target_dir / deploy_id
        runner = SshRunner(hostname=host, remote_user=user,
                dry_run=dry_run, verbose=verbose)
        remote_deployment = True
        local_runner = LocalRunner(dry_run=dry_run, verbose=verbose)
    else:
        if target is None:
            target_dir = options.base_dir / "versions"
        else:
            target_dir = Path(target).expanduser().absolute()
        deploy_dir = target_dir / deploy_id
    
        runner = LocalRunner(dry_run=dry_run, verbose=verbose)
        local_runner = runner
    
    local_runner.run(["wheel-getter", "--directory", staging_dir])
    runner.run(["mkdir", "-p", target_dir])
    runner.run(["uv", "init", "--bare", "--python", options.python_version, deploy_dir])
    runner.run(["uv", "python", "pin", "--project", deploy_dir, options.python_version])
    local_wheels = staging_dir / "wheels"
    remote_wheels = deploy_dir / "wheels"
    runner.run(["mkdir", remote_wheels])  # XXX within previous mkdir??
    
    runner.put_dir(local_wheels, remote_wheels, target_dir / "active")
    
    main_pkg = f"{options.config.main_package}[prod]"
    runner.run(["uv", "add", "--project", deploy_dir, main_pkg, "--no-index",
            "--find-links", deploy_dir / "wheels"])


@app.command
def activate(
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path | None = None,
        python_version: str | None = None,
        dry_run: bool = False,
        verbose: bool = False,
        debug: bool = False,
        ) -> None:
    """Activate deployed application – not implemented"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            python_version = python_version,
            dry_run = dry_run,
            verbose = verbose,
            debug = debug,
            )


@app.command
def new_branch(
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path | None = None,
        python_version: str | None = None,
        dry_run: bool = False,
        verbose: bool = False,
        debug: bool = False,
        ) -> None:
    """Create a new branch for git checkout – not implemented"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            python_version = python_version,
            dry_run = dry_run,
            verbose = verbose,
            debug = debug,
            )


@app.command
def runserver(
        port: int | None = None,
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path | None = None,
        python_version: str | None = None,
        dev: bool = True,
        dry_run: bool = False,
        verbose: bool = False,
        debug: bool = False,
        ) -> None:
    """Run Django development server"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            python_version = python_version,
            dry_run = dry_run,
            verbose = verbose,
            debug = debug,
            )
    if port is None:
        project_id = options.config.project_id
        if project_id is None:
            port = 8099
        else:
            port = 8000 + project_id
        if dev:
            subcmd = "runserver_plus"
        else:
            subcmd = "runserver"
    cmd = [
            "uv", "run",
            "--project", options.project_dir,
            "--python", options.python_version,
            options.config.management_command,
            subcmd, str(port),
            ]
    str_cmd = [str(c) for c in cmd]
    if dry_run:
        print(f"would execute: {' '.join(str_cmd)}")
        return
    subprocess.run(str_cmd, check=True)


@app.command
def release(
        project: Path | None = None,
        directory: Path | None = None,
        config_file: Path = DEFAULT_CONFIG,
        python_version: str | None = None,
        dry_run: bool = False,
        verbose: bool = False,
        debug: bool = False,
        ) -> None:
    """Make new release – not implemented"""
    options = get_options(
            project = project,
            directory = directory,
            config_file = config_file,
            python_version = python_version,
            dry_run = dry_run,
            verbose = verbose,
            debug = debug,
            )

# def run(MODE, SCRIPT, PARAMS, [--name=NAME])
