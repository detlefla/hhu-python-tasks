from attrs import define, Factory
from cattrs.preconf.pyyaml import make_converter as make_yaml_converter
# from cattrs.preconf.json import make_converter as make_json_converter
from fabric import Connection
from invoke import context
import logging
from pathlib import Path
import sys


logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)


@define
class RemoteHostInfo:
    hostname: str
    base_path: Path
    django_dir: Path
    user: str


@define
class BackupInfo:
    hostname: str
    directory: Path
    user: str
    filename_glob: str
    filename_pattern: str


@define
class SubPackageInfo:
    name: str
    workdir: Path


@define
class ProjectInfo:
    project_name: str
    project_id: int = 99
    src_path: Path | None = None
    package_name: str | None = None
    target: RemoteHostInfo | None = None
    python_version: str | None = None
    runserver_port: int | None = None
    wheelhouse: Path | None = Path("../wheels")
    backup: dict[str, BackupInfo] = Factory(dict)
    packages: list[SubPackageInfo] = Factory(list)
    editor_options: dict[str, list[str]] = Factory(dict)
    editor_files: list[Path] = Factory(list)
    
    def __attrs_post_init__(self):
        if self.src_path is None:
            self.src_path = Path("src") / self.project_name
        if self.package_name is None:
            self.package_name = self.project_name
        if self.python_version is None:
            self.python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        if self.runserver_port is None and self.project_id:
            self.runserver_port = 8000 + self.project_id


def get_options(ctx: context.Context) -> ProjectInfo:
    """Extracts project information from invoke context."""
    if "config_file" in ctx:
        filename = Path(ctx["config_file"]).expanduser()
        base = get_pyproject_path()
        if base is None:
            base = Path(".")
        filename = (base / filename).absolute()
        yaml_converter = make_yaml_converter()
        pi = yaml_converter.loads(open(filename), ProjectInfo)
        logger.info(f"reading configuration data from {filename}")
    else:
        ctx_info = {a.name: ctx[a.name]
                for a in ProjectInfo.__attrs_attrs__ if a.name in ctx}
        pi = ProjectInfo(**ctx_info)
    ctx["hhu_options"] = pi
    return pi


def get_pyproject_path(start: str | Path = ".") -> Path | None:
    """Tries to locate a pyproject.toml file and returns its path, None if not found."""
    p = Path(start).absolute()
    while True:
        if (p / "pyproject.toml").exists():
            return p
        if p == p.parent:
            break
        p = p.parent
    return None


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


####################################################################################################


data = """
---
project_name: hhunet
project_id: 22
src_path: hhunet
package_name: django-hhunet
target:
   hostname: hhunet.hhu.de
   base_path: /home/hhunet
   user: rlannert
python_version: "3.9"
wheelhouse: ~/projects/wheels
packages:
   -  name: django-zim-tools
      workdir: ../zimdj
   -  name: django-network-resources
      workdir: ../netres
   -  name: django-hhunet
      workdir: .

editor_options:
  joe: ["-joe_state", "-restore", "-nolocks"]
editor_files: [
  hhunet/urls.py,
  hhunet/views.py,
  ]
"""

def main():
    yaml_converter = make_yaml_converter()
    pi = yaml_converter.loads(data, ProjectInfo)
    print(repr(pi))
    print()
    print(yaml_converter.dumps(pi))


if __name__ == "__main__":
    main()
