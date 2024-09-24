from invoke import Collection, context, Exit, task

import base64
from hashlib import sha384
import logging
import os
from pathlib import Path
import re
from rich import print
from semantic_version import Version
import subprocess
import sys
from types import SimpleNamespace as SN
from typing import Any, Optional
import uuid_utils as uuid
import yaml

from .structure import get_options, remote, run

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

# XXX
PROJECT = "hhunet"
PROJECT_ID = 22
ROOT_DIR = Path(__file__).parent
SUB_DIR = "hhunet"
PACKAGE = "django-hhunet"


def _get_versionfile_path() -> Path:
    return ROOT_DIR / SUB_DIR / "VERSION"


def _get_version() -> str:
    return _get_versionfile_path().read_text().strip()


def _get_wheelname() -> str:
    version = _get_version()
    try:
        package_name = PACKAGE
    except NameError:
        package_name = PROJECT
    package_name = package_name.replace("-", "_")
    return f"{package_name}-{version}-py3-none-any.whl"


def _get_conf(ctx: context.Context, name: str, default: Any = None) -> Any:
    """Returns configuration option value."""
    if name in ctx.config:
        value = ctx.config[name]
    else:
        if "config_options" not in ctx:
            p = Path(f"~/.local/hhu/{PROJECT}.yaml").expanduser()
            if p.exists():
                with open(p) as f:
                    conf = yaml.safe_load(f)
            else:
                conf = {}
            ctx["config_options"] = conf
        value = ctx["config_options"].get(name, default)
    return value


def set_editable_paths(ctx: context.Context) -> None:
    """Exports subpackage locations to the environment."""
    dry_run = ctx["run"]["dry"]
    packages = ctx.get("packages", {})
    for name, info in packages.items():
        env_key = name.upper()
        env_value = info["workdir"]
        if dry_run:
            print(f"would export {env_key}={env_value}")
        else:
            os.environ[env_key] = env_value


def get_local_paths(ctx: context.Context,
        *,
        did: str | None = None,
        root: Path | None = None,
        base: Path | None = None,
        ) -> SN:
    """Determines paths to deployment-specific local directories and files."""
    if root is None:
        root = Path(__file__).parent
    if base is None:
        base = Path(ctx.get("project_base", root))
    local = SN(
            temp_venv = root / "deploy" / "venv",
            wheelhouse = base / "wheels",
            req_prod_in = root / "requirements" / "prod.in",
            req_prod_txt = root / "requirements" / "prod.txt",
            base_private = base / "private",
            private = root / "private",
            )
    if did is not None:
        local.deploy = root / "deploy" / did
        local.req_prod = root / "deploy" / did / f"requirements.txt"
        local.wheels = root / "deploy" / did / f"wheels"
    return local


def get_paths(ctx: context.Context,
        *,
        did: str,
        root: Path | None = None,
        ) -> SN:
    """Determines paths to deployment-specific remote and local directories and files."""
    base = Path(ctx.get("target_path", Path("/home") / PROJECT))
    paths = SN(
            target = SN(
                base = base,
                project = base / "django",
                ext_res = base / "django" / "static_external" / "external",
                logs = base / "logs",
                venvs = base / "venvs",
                venv = base / "venvs" / f"v-{did}",
                venv_act = base / "venvs" / "active",
                wheels = base / "wheels",
                wheelhouse = base / "wheels" / f"wh-{did}",
                wheels_act = base / "wheels" / "active",
                reqs = base / "requirements",
                req_prod = base / "requirements" / f"req-{did}.txt",
                )
            )
    paths.local = get_local_paths(ctx, did=did, root=root)
    return paths


################################################################################
###
### building and deploying


def check_branch(branch: str) -> None:
    retcd, output = subprocess.getstatusoutput("git branch")
    if retcd:
        print(f"[#f0c000]not inside a git tree – branch not checked")
    else:
        # we are inside a git tree
        for branch_line in output.splitlines():
            indicator, branch_name = branch_line.split(None, 1)
            if indicator == "*" and branch_name != branch:
                print(f"[red]currently on git branch “{branch_name}” instead of “{branch}”")
                raise ValueError("wrong branch")


################################################################################
### 
### backup management


@task(help={
        "location": "backup definition from invoke.yaml; default: \"server\"",
        })
def show_backups(ctx, location="server"):
    """List existing backups."""
    options = get_options(ctx)
    if (loc_conf := options.backup.get(location)) is None:
        raise ValueError(f"unknown location '{location}'")
    command = f"ls -l {loc_conf.directory}/{loc_conf.filename_glob}"
    remote(ctx, command, host=loc_conf.hostname, user=loc_conf.user)


@task(help={
        "location": "backup definition from invoke.yaml; default: \"server\"",
        })
def clean_backups(ctx, location="server"):
    """Remove backup archives older than 30 days except one per month."""
    options = get_options(ctx)
    dry_run = ctx["run"]["dry"]
    if (loc_conf := options.backup.get(location)) is None:
        raise ValueError(f"unknown location '{location}'")
    command = f"ls {loc_conf.directory}/{loc_conf.filename_glob}"
    result = remote(ctx, command, host=loc_conf.hostname, user=loc_conf.user,
            hide=True, run_always=True)
    files = []
    re_filename = re.compile(f"{loc_conf.directory}/{loc_conf.filename_pattern}")
    for name in result.stdout.splitlines():
        m = re_filename.match(name)
        if m:
            year = m.group("year")
            iyear = int(year)
            if iyear < 100:
                iyear += 1900
                if iyear < 1950:
                    iyear += 100
            year = "%04d" % iyear
            month = m.group("month")
            day = m.group("day")
            files.append((year, month, day, name))
        else:
            print(f"no match with {re_filename}: '{name}'")
    files.sort()
    remainers = {}
    remainlist = []
    remaincount = len(files) - 30
    n = 0
    for year, month, day, name in files:
        n += 1
        if n > remaincount:
            remainlist.append(name)
            continue
        if (year, month) not in remainers:
            remainers[year, month] = name
            continue
        command = f"rm {name}"
        result = remote(ctx, command, host=loc_conf.hostname, user=loc_conf.user,
                dry_run=dry_run)
        if result.ok:
            print(f"removed: {name}")
    
    if dry_run:
        print()
        for year, month in remainers.keys():
            name = remainers[year, month]
            print(f"keep: {name}")
        for name in remainlist:
            print(f"keep: {name}")


################################################################################
###
### requirements / venv management


@task(help={
        "mode": "select requirements file, e.g. \"prod\" for requirements/prod.txt and prod.in; default: \"dev\"",
        "hashes": "whether the txt file should contain package hashes; default: False",
        "upgrade": "comma-separated list of packages to upgrade",
        "use-wheeldir": "get packages from the wheelhouse directory",
        })
def upgrade_requirements(ctx, mode="dev", hashes=False, upgrade="", use_wheeldir=False):
    """Upgrade requirements txt file"""
    hashes = "--generate-hashes" if hashes else ""
    if upgrade:
        upgrades = " ".join(f"-P {package}" for package in upgrade.split(","))
    else:
        upgrades = "-U"
    
    paths = get_paths(ctx)
    wheel_dir = paths.local.wheelhouse
    with ctx.cd(str(ROOT_DIR)):
        run(ctx, f"uv pip compile {upgrades} {hashes} --extra-index-url {wheel_dir}"
            f" -o requirements/{mode}.txt"
            f" requirements/{mode}.in")


@task(help={
        "mode": "select requirements file, e.g. \"prod\" for requirements/prod.txt and prod.in; default: \"dev\"",
        })
def upgrade_venv(ctx, mode="dev"):
    """Upgrade current venv from requirements/{mode}.txt file"""
    with ctx.cd(str(ROOT_DIR)):
        run(ctx, f"uv pip sync requirements/{mode}.txt")


################################################################################
### 
### Generate, deploy, and install wheels


def deploy_prep(ctx: context.Context, did: str, paths: SN) -> None:
    """Prepares a deployment."""
    dry_run = ctx["run"]["dry"]
    
    if dry_run:
        print(f"would create directory {paths.local.deploy}")
        print(f"wourd copy {paths.local.req_prod_txt} to {paths.local.req_prod}")
        print(f"would create directory {paths.local.wheels}")
    else:
        paths.local.deploy.mkdir(parents=True, exist_ok=True)
        paths.local.req_prod.write_bytes(paths.local.req_prod_txt.read_bytes())
        paths.local.wheels.mkdir(parents=True, exist_ok=True)


def deploy_add_wheel(
        ctx: context.Context,
        did: str,
        paths: SN,
        version: str | None = None,
        ) -> None:
    """Adds wheel of current package to deployment wheelhouse."""
    verb = "-v" if ctx["run"]["echo"] else ""
    dry_run = ctx["run"]["dry"]
    
    if version is None:
        version = Path(f"{SUB_DIR}/VERSION").read_text().strip()
        print(f"[green]deploying version {version}[/green]")
    glob = f"{PACKAGE.replace('-', '_')}-{version}-*.whl"
    wheelnames = list(paths.local.wheelhouse.glob(glob))
    if not wheelnames:
        if dry_run:
            print(f"[#f0c000]deployable wheel not found in {paths.local.wheelhouse}/")
            wheelnames = [paths.local.wheelhouse / glob]
        else:
            print(f"[red]deployable wheel not found in {paths.local.wheelhouse}/[/red]")
            raise ValueError("wheel not found")
    wheelnames.sort()
    wheelname = wheelnames[-1]
    if len(wheelnames) > 1:
        print(f"[#f0c000]more than one usable wheel found, using {wheelname}[/]")
    run(ctx, f"cp {verb} {wheelname} {paths.local.wheels / wheelname.parts[-1]}")


def deploy_add_reqs(
        ctx: context.Context,
        did: str,
        paths: SN,
        python_version: str | None = None,
        ) -> None:
    """Adds required wheels to the local wheelhouse."""
    if python_version is None:
        py_opt = ""
        py_vopt = ""
        py_name = "python3"
    else:
        py_opt = f"--python-version {python_version}"
        py_vopt = f"-p python{python_version}"  # uv venv wants it this way
        py_name = f"python{python_version}"
    if paths.local.temp_venv.exists():
        run(ctx, f"rm -rf {paths.local.temp_venv}")
    run(ctx, f"uv venv {py_vopt} {paths.local.temp_venv}")
    run(ctx, f"VIRTUAL_ENV={paths.local.temp_venv} " +
            f"uv pip install {py_opt} --prefix {paths.local.temp_venv} -r {paths.local.req_prod} " +
            f"-f {paths.local.wheelhouse} pip django-hhunet"
            )
    run(ctx, f"{paths.local.temp_venv}/bin/{py_name} -m pip wheel -w {paths.local.wheels} " +
            f"-f {paths.local.wheelhouse} -r {paths.local.req_prod}")


def deploy_prep_remote(
        ctx: context.Context,
        did: str,
        paths: SN,
        ) -> None:
    """Prepares remote host for deployment."""
    remote(ctx, f"mkdir -m 751 -p {paths.target.venvs} {paths.target.reqs} {paths.target.wheels_act}")
    remote(ctx, f"cp -aL {paths.target.wheels_act} {paths.target.wheelhouse}")


def deploy_copy_remote(
        ctx: context.Context,
        did: str,
        paths: SN,
        python_version: str | None = None,
        ) -> None:
    """Copies wheels to remote host and installs into venv."""
    options = ctx["hhu_options"]
    if options.target is None:
        print("[red]no target host configured")
        raise ValueError("no target host")
    if python_version is None:
        py = "python3"
        py_opt = ""
    else:
        py = f"python{python_version}"
        py_opt = f"--python {py}"
    target = f"{target.user}@{target.hostname}"
    remote(ctx, f"uv venv {py_opt} --prompt {did[:8]} {paths.target.venv}")
    run(ctx, f"scp {paths.local.req_prod} {target}:{paths.target.req_prod}")
    run(ctx, f"rsync -avxc --delete {paths.local.wheels}/ {target}:{paths.target.wheelhouse}/")
    remote(ctx, f"VIRTUAL_ENV={paths.target.venv} uv pip install {py_opt} --no-index " +
            f"-f {paths.target.wheelhouse} -r {paths.target.req_prod} {PACKAGE}")


def deploy_act_remote(
        ctx: context.Context,
        did: str,
        paths: SN,
        python_version: str | None = None,
        collectstatic: bool = False,
        ) -> None:
    """Activates deployment on remote host."""
    remote(ctx, f"{paths.target.venv / 'bin' / 'python'} {paths.target.project / 'manage.py'} check")
    remote(ctx, f"{paths.target.venv / 'bin' / 'python'} {paths.target.project / 'manage.py'} migrate")
    if collectstatic:
        remote(ctx, f"{paths.target.venv / 'bin' / 'python3'} {paths.target.project / 'manage.py'} collectstatic")
    remote(ctx, f"ln -sfn {paths.target.wheelhouse.parts[-1]} {paths.target.wheels_act}")
    remote(ctx, f"ln -sfn {paths.target.venv.parts[-1]} {paths.target.venv_act}")


@task(help={
        "deployment_id": "unique identifier for this deployment (default: auto-generated UUID)",
        "version": "version of the (previously built) wheel to deploy (default: from source)",
        "install": "transfer wheels to remote host and create a new venv (default: True)",
        "activate": "make new venv on remote the active one, migrate, and collectstatic (unless suppressed) (default: True)",
        "cleanup": "remove local deployment directory (with deployment-id) (default: True)",
        "collectstatic": "run “manage.py collectstatic” on remote if --activate is specified (default: True)",
        "python_version": "Python version to use, e.g. “3.12”",
        })
def deploy_package(
        ctx: context.Context,
        deployment_id: str | None = None,
        version: str | None = None,
        install: bool = True,
        activate: bool = True,
        cleanup: bool = True,
        collectstatic: bool = True,
        python_version: str | None = None,
        ) -> None:
    """Deploy package to target host, optionally installing it."""
    options = get_options(ctx)
    if deployment_id is None:
        did = str(uuid.uuid7())
    else:
        did = deployment_id
    print(f"[green]deployment id is “{did}”[/green]")
    
    if python_version is None:
        python_version = ctx.get("python_version")
    
    paths = get_paths(ctx, did=did)
    
    try:
        deploy_prep(ctx, did, paths)
        deploy_add_wheel(ctx, did, paths, version=version)
        deploy_add_reqs(ctx, did, paths, python_version=python_version)
        if install:
            deploy_prep_remote(ctx, did, paths)
            deploy_copy_remote(ctx, did, paths, python_version=python_version)
            if activate:
                deploy_act_remote(ctx, did, paths, collectstatic=collectstatic)
    
    finally:
        if cleanup:
            print("[green]cleaning up …[/green]")
            cleandir = paths.local.deploy
            run(ctx, f"rm -rf {cleandir}/")
            print("[green]done[/green]")


@task
def install_package_files(
        ctx: context.Context,
        ) -> None:
    """Installs global package files on target."""
    options = get_options(ctx)
    if options.target is None:
        print("[red]no target host configured")
        raise ValueError("no target host")
    target = f"{options.target.user}@{options.target.hostname}:{options.target.django_dir}"
    paths = get_paths(ctx, did="_")
    files = [
            "settings/common.py",
            "settings/prod.py",
            "settings/__init__.py",
            "urls.py",
            "manage_prod.py",
            ]
    for f in files:
        run(ctx, f"scp {f} {target}:{paths.target.project}")


@task
def deploy_uv(ctx: context.Context) -> None:
    """Deploys the local uv binary on the server (in /usr/local/bin)"""
    options = get_options(ctx)
    if options.target is None:
        print("[red]no target host configured")
        raise ValueError("no target host")
    target = f"{options.target.user}@{options.target.hostname}"
    run(ctx, f"scp ~/.cargo/bin/uv {target}:/usr/local/bin/")
