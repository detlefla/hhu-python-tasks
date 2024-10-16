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
from .structure import get_options
from .utils import *


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
            parts = branch_line.split(None, 1)
            if len(parts) != 2:
                # no usable branch
                continue
            indicator, branch_name = parts
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
        commit: bool = True,
        set_tag: bool = True,
        ) -> None:
    """Increment package version"""
    options = get_options(ctx)
    dry_run = ctx["run"]["dry"]
    
    check_branch(ctx, branch)
    
    v = Version(get_version(ctx))
    if level == "patch":
        v = v.next_patch()
    elif level == "minor":
        v = v.next_minor()
    elif level == "major":
        v = v.next_major()
    else:
        raise AssertionError(f"unknown version level “{level}”")
    filepath = get_versionfile_path(ctx)
    if ctx["run"]["dry"]:
        print(f"new version would be “{v}”")
    else:
        if dry_run:
            print(f"would write “{v}” to {get_versionfile_path(ctx)}")
        else:
            filepath.write_text(str(v))
            print(f"[green]new version is {v}")
            if commit:
                run(ctx, f"git commit -m 'bumped version to “{v}”' {filepath}")
    
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
    options = get_options(ctx)
    wheelname = get_wheelname(ctx)
    if python == "":
        python = sys.executable
    
    check_branch(ctx, branch)
    
    local_paths = get_local_paths(ctx)
    if os.environ.get("DEBUG_INV"):
        print(options)
        print(local_paths)
    
    if (local_paths.wheelhouse / wheelname).exists():
        if ctx["run"]["dry"]:
            print(f"Warning: wheel {wheelname} exists – increment version number!")
        else:
            raise AssertionError(f"wheel {wheelname} exists – forgot to increment version number?")
    
    with ctx.cd(str(get_pyproject_path())):
        run(ctx, f"mkdir -p {local_paths.wheelhouse}")
        run(ctx, f"rm -f dist/*")
        run(ctx, f"python -m build")
        run(ctx, f"cp -v dist/*.whl {local_paths.wheelhouse}")
        run(ctx, f"rm -rf *.egg-info")

# ns.add_task(make_wheel)


################################################################################
###
### messages updates 


@task(help={
        "language": "code of the language to create translations for",
        })
def make_messages(ctx, language="de"):
    """Extract translation strings from Python sources and Django templates."""
    options = get_options(ctx)
    base_path = get_pyproject_path()
    manage = base_path / "manage.py"
    sources = (base_path / options.src_path).absolute()
    with ctx.cd(str(sources)):
        ctx.run(f"./manage.py makemessages -l {language}")

# ns.add_task(make_messages)


@task
def compile_messages(ctx):
    """Compile django.po into django.mo files."""
    options = get_options(ctx)
    base_path = get_pyproject_path()
    manage = base_path / "manage.py"
    sources = (base_path / options.src_path).absolute()
    with ctx.cd(str(sources)):
        ctx.run("{manage} compilemessages")
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
    options = get_options(ctx)
    hashes = "--generate-hashes" if hashes else ""
    if upgrade:
        upgrades = " ".join(f"-P {package}" for package in upgrade.split(","))
    else:
        upgrades = "-U"
    
    local_paths = get_local_paths(ctx, did="x")
    wheel_dir = local_paths.wheelhouse
    with ctx.cd(str(get_pyproject_dir())):
        run(ctx, f"uv pip compile {upgrades} {hashes} -f {wheel_dir}"
            f" -o requirements/{mode}.txt"
            f" requirements/{mode}.in")

# ns.add_task(upgrade_requirements)


@task(help={
        "mode": "select requirements file, e.g. \"prod\" for requirements/prod.txt and prod.in; default: \"dev\"",
        })
def upgrade_venv(ctx, mode="dev"):
    """Upgrade current venv from requirements/{mode}.txt file"""
    with ctx.cd(str(get_pyproject_dir())):
        run(ctx, f"uv pip sync requirements/{mode}.txt")

# ns.add_task(upgrade_venv)


################################################################################
###
### development tools


@task
def runserver(ctx):
    """Run the development HTTP server"""
    options = get_options(ctx)
    manage = get_pyproject_path() / "manage.py"
    envvars = get_conf(ctx, "dev_env_vars")  # XXX remove this and other occurrences
    if envvars:
        envvars += " "
    else:
        envvars = ""
    port = options.runserver_port
    
    run(ctx, f"{envvars}{manage} runserver_plus --no-color --keep-meta-shutdown {port}", pty=True)

# ns.add_task(runserver)


@task(help={
        "print_sql": "print SQL queries as they are executed",
        })
def shell(ctx, print_sql=False):
    """Run the shell plus tool"""
    options = get_options(ctx)
    manage = get_pyproject_path() / "manage.py"
    envvars = ctx.get("dev_env_vars")
    if envvars:
        envvars += " "
    else:
        envvars = ""
    sql_option = "--print-sql" if print_sql else ""
    if Path(f"~/.ipython/profile_{options.project_name}/").expanduser().is_dir():
        profile_option = f"-- --profile={options.project_name}"
    else:
        profile_option = ""
    run(ctx, f"{envvars}{manage} shell_plus --ipython {sql_option} {profile_option}", pty=True)

# ns.add_task(shell)


@task(help={
        "editor": "name (or path) of the editor program; default taken from $EDITOR",
        })
def edit(ctx, editor=""):
    """Start editor and load a convenient set of source files"""
    options = get_options(ctx)
    local_options = ctx["hhu_local_options"]
    editor = editor or os.environ.get("EDITOR") or list(local_options.editor_options.keys())[0]
    if local_options.editor_options:
        editor_options = " ".join(local_options.editor_options[editor])
    else:
        editor_options = ""
    files = " ".join(str(f) for f in local_options.editor_files)
    with ctx.cd(str(get_pyproject_path())):
        run(ctx, f"{editor} {editor_options} {files}", pty=False)

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
    options = get_options(ctx)
    manage = get_pyproject_path() / "manage.py"
    envvars = get_conf(ctx, "dev_env_vars")
    if envvars:
        envvars += " "
    else:
        envvars = ""
    port = options.runserver_port
    if envvars:
        envvars += " "
    else:
        envvars = ""
    if Path(f"~/.ipython/profile_{options.project_name}/").expanduser().is_dir():
        profile_option = f"--profile={options.project_name}"
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


########################## Debug ##########################


def debug_context(ctx):
    """Debugging aid"""
    options = get_options(ctx)
    print(f"{options=}\n\n{ctx=}")

if os.environ.get("DEBUG_INV"):
    debug_context = task()(debug_context)

# ns.add_task(debug_context)
