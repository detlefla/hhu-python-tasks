from fabric import Connection
from invoke import context
import os
from pathlib import Path
from types import SimpleNamespace as SN
from typing import Any
import yaml


def get_versionfile_path(ctx: context.Context) -> Path:
    """Returns the path of the version file."""
    options = ctx["hhu_options"]
    p = get_pyproject_path() / options.src_path / "VERSION"
    return p


def get_version(ctx: context.Context) -> str:
    """Returns the version string from the source tree."""
    return get_versionfile_path(ctx).read_text().strip()


def get_wheelname(ctx: context.Context) -> str:
    """Determines the name of the wheel to be built."""
    options = ctx["hhu_options"]
    version = get_version(ctx)
    package_name = to_snake_case(options.package_name)
    return f"{package_name}-{version}-py3-none-any.whl"


def get_conf(ctx: context.Context, name: str, default: Any = None) -> Any:
    """Returns configuration option value."""
    options = ctx["hhu_options"]
    if name in ctx.config:
        value = ctx.config[name]
    else:
        if "config_options" not in ctx:
            p = Path(f"~/.local/hhu/{options.project_name}.yaml").expanduser()
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
    options = ctx["hhu_options"]
    dry_run = ctx["run"]["dry"]
    for pkg_info in options.packages:
        env_key = pkg_info.name.upper()
        env_value = pkg_info.workdir
        if dry_run:
            print(f"would export {env_key}={env_value}")
        else:
            os.environ[env_key] = str(env_value)


def get_local_paths(ctx: context.Context,
        *,
        did: str | None = None,
        base: Path | None = None,
        ) -> SN:
    """Determines paths to deployment-specific local directories and files."""
    options = ctx["hhu_options"]
    root = get_pyproject_path()
    local = SN(
            temp_venv = root / "deploy" / "venv",
            wheelhouse = options.wheelhouse,
            req_prod_in = root / "requirements" / "prod.in",
            req_prod_txt = root / "requirements" / "prod.txt",
            private = root / "private",
            base_private = options.private_files,
            )
    if did is not None:
        local.deploy = root / "deploy" / did
        local.req_prod = root / "deploy" / did / f"requirements.txt"
        local.wheels = root / "deploy" / did / f"wheels"
    return local


def get_paths(ctx: context.Context,
        *,
        did: str,
        ) -> SN:
    """Determines paths to deployment-specific remote and local directories and files."""
    options = ctx["hhu_options"]
    base = options.target.base_path
    django = options.target.django_dir
    paths = SN(
            target = SN(
                base = base,
                project = django,
                ext_res = django / "static_external" / "external",
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
    paths.local = get_local_paths(ctx, did=did)
    return paths


def get_pyproject_path(start: str | Path = ".") -> Path:
    """Tries to locate a pyproject.toml file and returns its path, None if not found."""
    cwd = Path(start).absolute()
    p = cwd
    while True:
        if (p / "pyproject.toml").exists():
            return p
        if p == p.parent:
            break
        p = p.parent
    return cwd


def to_snake_case(name: str) -> str:
    """Converts kebab-case name to snake case."""
    return name.replace("-", "_")


class Result:
    """Fake fabric.Connection result object"""
    def __init__(self, command: str, connection: Connection):
        self.command = command
        self.connection = connection
        self.ok = True
        self.stdout = ""
        self.stderr = ""


def run(ctx: context.Context,
        *args,
        dry_run: bool = False,
        **kwargs):
    """Runs a command on localhost."""
    if ctx["run"]["dry"] or dry_run:
        print("would run", repr(args), repr(kwargs))
    else:
        if ctx["run"]["echo"]:
            print("running:", repr(args), repr(kwargs))
        ctx.run(*args, **kwargs)


def remote(ctx: context.Context,
        command: str,
        *,
        host: str | None = None,
        user: str | None = None,
        run_always: bool = False,
        hide: bool = False,
        dry_run: bool = False,
        ) -> Result:
    """Runs a command on the remote host."""
    dry_run = dry_run or ctx["run"]["dry"]
    options = ctx["hhu_options"]
    if options.target is None:
        print("[red]no target host configured")
        raise ValueError("no target host")
    if host is None:
        host = options.target.hostname
    conn = Connection(host)
    sshconf = Path("~/.ssh/config").expanduser().absolute()
    conn.ssh_config_path=str(sshconf)
    if user is None:
        user = options.target.user
    if user is not None:
        conn.user = user
    if dry_run:
        if run_always:
            print(f"will run on {host}: {command}")
            result = conn.run(command, hide=hide)
        else:
            print(f"would run on {host}: {command}")
            result = Result(command=command, connection=conn)
    else:
        if ctx["run"]["echo"]:
            print(f"{conn.user}@{conn.host} running {command}")
        result = conn.run(command, hide=hide)
    return result
