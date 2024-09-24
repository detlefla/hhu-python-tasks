from invoke import Collection, context, Exit, task

import base64
from hashlib import sha384
from fabric import Connection
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
# from django_tasks import *

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)


from .project_tasks import *  # noqa
from .structure import get_options, remote, run


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
        root: Path = ROOT_DIR,
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


def check_branch(ctx: context.Context, branch: str) -> None:
    """Checks if we are on the correct (master) git branch."""
    dry_run = ctx["run"]["dry"]
    
    retcd, output = subprocess.getstatusoutput("git branch")
    if retcd:
        print(f"[#f0c000]not inside a git tree – branch not checked")
    else:
        # we are inside a git tree
        for branch_line in output.splitlines():
            indicator, branch_name = branch_line.split(None, 1)
            if indicator == "*" and branch_name != branch:
                if dry_run:
                    print(f"[#f0c000]currently on git branch “{branch_name}” instead of “{branch}”")
                else:
                    print(f"[red]currently on git branch “{branch_name}” instead of “{branch}”")
                    raise ValueError("wrong branch")


@task(help={
        "level": "level of version increment (major, minor or patch; default: minor)",
        "branch": "if within a git tree, restrict operation to this branch (default: master)",
        "set_tag": "create a git tag for the new version (default: True)",
        })
def inc_version(ctx: context.Context,
        level: str = "minor",
        branch: str = "master",
        set_tag: bool = True,
        ) -> None:
    """Increment package version"""
    dry_run = ctx["run"]["dry"]
    
    check_branch(ctx, branch)
    
    v = Version(_get_version())
    if level == "patch":
        v = v.next_patch()
    elif level == "minor":
        v = v.next_minor()
    elif level == "major":
        v = v.next_major()
    else:
        raise AssertionError(f"unknown version level “{level}”")
    if ctx["run"]["dry"]:
        print(f"new version would be “{v}”")
    else:
        if dry_run:
            print(f"would write “{v}” to {_get_versionfile_path()}")
        else:
            p = _get_versionfile_path().write_text(str(v))
            print(f"[green]new version is {v}")
    
    # set git tag if requested (and possible)
    if set_tag:
        run(ctx, f"git tag -m 'new version (level {level})' 'v{v}'")
        if not dry_run:
            print(f"[green]tag “v{v}” set")

# ns.add_task(inc_version)


@task(help={
        "python": "the Python executable (default: the one running this command)",
        "branch": "if within a git tree, restrict operation to this branch (default: master)",
        })
def make_wheel(ctx: context.Context,
        python: str = "",
        branch: str = "master",
        ) -> None:
    """Create a wheel and move it into the wheelhouse"""
    wheelname = _get_wheelname()
    if python == "":
        python = sys.executable
    
    check_branch(ctx, branch)
    
    local_paths = get_local_paths(ctx)
    
    if (local_paths.wheelhouse / wheelname).exists():
        if ctx["run"]["dry"]:
            print(f"Warning: wheel {wheelname} exists – increment version number!")
        else:
            raise AssertionError(f"wheel {wheelname} exists – forgot to increment version number?")
    
    with ctx.cd(str(ROOT_DIR)):
        run(ctx, f"mkdir -p {local_paths.wheelhouse}")
        run(ctx, f"rm -f dist/*")
        run(ctx, f"python -m build")
        run(ctx, f"cp -v dist/*.whl {local_paths.wheelhouse}")
        run(ctx, f"rm -rf {PROJECT}.egg-info")

# ns.add_task(make_wheel)


################################################################################
###
### messages updates 


@task(help={
        "language": "code of the language to create translations for",
        })
def make_messages(ctx, language="de"):
    """Extract translation strings from Python sources and Django templates."""
    path = Path(__file__).absolute().parent
    with ctx.cd(str(path / "hhunet")):  # XXX
        ctx.run(f"./manage.py makemessages -l {language}")

# ns.add_task(make_messages)


@task
def compile_messages(ctx):
    """Compile django.po into django.mo files."""
    path = Path(__file__).absolute().parent
    with ctx.cd(str(path / "hhunet")):  # XXX
        ctx.run("../manage.py compilemessages")
# msgfmt -o hhunet/locale/de/LC_MESSAGES/django.mo hhunet/locale/de/LC_MESSAGES/django.po

# ns.add_task(compile_messages)


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
    
    paths = get_paths(ctx, did="x")
    wheel_dir = paths.local.wheelhouse
    with ctx.cd(str(ROOT_DIR)):
        run(ctx, f"uv pip compile {upgrades} {hashes} -f {wheel_dir}"
            f" -o requirements/{mode}.txt"
            f" requirements/{mode}.in")

# ns.add_task(upgrade_requirements)


@task(help={
        "mode": "select requirements file, e.g. \"prod\" for requirements/prod.txt and prod.in; default: \"dev\"",
        })
def upgrade_venv(ctx, mode="dev"):
    """Upgrade current venv from requirements/{mode}.txt file"""
    with ctx.cd(str(ROOT_DIR)):
        run(ctx, f"uv pip sync requirements/{mode}.txt")

# ns.add_task(upgrade_venv)


################################################################################
###
### development tools


@task
def runserver(ctx):
    """Run the development HTTP server"""
    manage = ROOT_DIR / "manage.py"
    envvars = _get_conf(ctx, "dev_env_vars")
    if envvars:
        envvars += " "
    else:
        envvars = ""
    offset = _get_conf(ctx, "project_id", PROJECT_ID)
    port = _get_conf(ctx, "dev_runserver_port", 8000 + offset)
    
    run(ctx, f"{envvars}{manage} runserver_plus --no-color --keep-meta-shutdown {port}", pty=True)

# ns.add_task(runserver)


@task(help={
        "print_sql": "print SQL queries as they are executed",
        })
def shell(ctx, print_sql=False):
    """Run the shell plus tool"""
    manage = ROOT_DIR / "manage.py"
    envvars = ctx.get("dev_env_vars")
    if envvars:
        envvars += " "
    else:
        envvars = ""
    sql_option = "--print-sql" if print_sql else ""
    if Path(f"~/.ipython/profile_{PROJECT}/").expanduser().is_dir():
        profile_option = f"-- --profile={PROJECT}"
    else:
        profile_option = ""
    run(ctx, f"{envvars}{manage} shell_plus --ipython {sql_option} {profile_option}", pty=True)

# ns.add_task(shell)


@task(help={
        "editor": "name (or path) of the editor program; default taken from $EDITOR",
        })
def edit(ctx, editor=""):
    """Start editor and load a convenient set of source files"""
    editor = editor or os.environ.get("EDITOR")
    options = " ".join(ctx.get("editor_options", {}).get(editor, []))
    files = " ".join(ctx.get("editor_files", []))
    with ctx.cd(str(ROOT_DIR)):
        run(ctx, f"{editor} {options} {files}", pty=False)

# ns.add_task(edit)


@task
def dmypy(ctx):
    """Start mypy daemon for the standard editor files"""
    files = ctx.get("editor_files", [])
    files = [f for f in files if f.endswith(".py")]
    with ctx.cd(str(ROOT_DIR)):
        if ctx["run"]["dry"]:
            files_string = " ".join(files)
            print(f"would exec dmypy run -- {files_string}")
        else:
            os.execlp("dmypy", "dmypy", "run", "--", *files)

# ns.add_task(dmypy)


@task
def type_check(ctx):
    """Run the standard editor files through the type-checker daemon"""
    files = ctx.get("editor_files", [])
    files = [f for f in files if f.endswith(".py")]
    with ctx.cd(str(ROOT_DIR)):
        if ctx["run"]["dry"]:
            files_string = " ".join(files)
            print(f"would exec dmypy check -- {files_string}")
        else:
            os.execlp("dmypy", "dmypy", "check", "--", *files)

# ns.add_task(type_check)


@task
def notebook(ctx):
    """Run a jupyter notebook server for this project"""
    manage = ROOT_DIR / "manage.py"
    envvars = ctx.get("dev_env_vars")
    if envvars:
        envvars += " "
    else:
        envvars = ""
    offset = _get_conf(ctx, "project_id", PROJECT_ID)
    port = _get_conf(ctx, "dev_runserver_port", 8900 + offset)
    if Path(f"~/.ipython/profile_{PROJECT}/").expanduser().is_dir():
        profile_option = f"--profile={PROJECT}"
    else:
        profile_option = ""
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    run(ctx, f"{envvars}{manage} shell_plus --notebook -- --port={port} {profile_option}",
            pty=True)

# ns.add_task(notebook)


@task
def push(ctx):
    """Push new revision to all repositories"""
    for cmd in ctx.get("versioning_options", {}):
        for target in ctx["versioning_options"][cmd].get("repos"):
            run(ctx, f"{cmd} push {target}", warn=True)

# ns.add_task(push)


# @task
# def debug_context(ctx):
#     """Debugging aid"""
#     print(ctx)
#
# ns.add_task(debug_context)
