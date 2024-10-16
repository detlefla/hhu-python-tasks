from attrs import define, Factory
from cattrs import structure
from cattrs.preconf.pyyaml import make_converter as make_yaml_converter
# from cattrs.preconf.json import make_converter as make_json_converter
from fabric import Connection
from invoke import context
import logging
import os
from pathlib import Path
import sys
from typing import Literal

from .utils import get_pyproject, get_pyproject_path, to_snake_case


logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)


@define
class RemoteHostInfo:
    hostname: str
    base_path: Path
    django_dir: Path
    user: str
    service_name: str | None = None  # None: equal to project_name
    service_start: Literal["systemd"] | Literal["supervisord"] = "systemd"


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
    project_name: str | None = None
    project_id: int = 99
    private_files: Path | None = None
    package_name: str | None = None
    target: RemoteHostInfo | None = None
    python_version: str | None = None
    runserver_port: int | None = None
    wheelhouse: Path | None = "wheels"
    backup: dict[str, BackupInfo] = Factory(dict)
    packages: list[SubPackageInfo] = Factory(list)
    
    def __attrs_post_init__(self):
        if self.package_name is None:
            self.package_name = self.project_name
        if self.python_version is None:
            self.python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        if self.runserver_port is None and self.project_id:
            self.runserver_port = 8000 + self.project_id
        if self.target is not None and self.target.service_name is None:
            self.target.service_name = self.project_name


@define
class LocalInfo:
    editor_options: dict[str, list[str]] = Factory(dict)
    editor_files: list[Path] = Factory(list)


# Configuration files:
#
# -  invoke.yaml:
#       automatically read by ``inv`` command, optional, may contain
#
#       -  src_path: path to the source directory (default: src/PACKAGE)
#       -  local config: path to a local, unversioned configuration file (default:
#          ``hhu_tasks_local.yaml``)
#       -  config_file: path to or name of a project config file (default: ``hhu_tasks.yaml``)
#       -  search_config: boolean, specifies whether to search for a project config file
#          above the pyproject.toml directory (default: false)
#
# -  hhu_tasks.yaml:
#       project-global configuration, described by ProjectInfo; data 
#
# -  hhu_tasks_local.yaml:
#       package-local configuration, private to the user (unversioned)
#
# All these files are optional.
#
# Their contents (or defaults) are inserted into the context with the keys "hhu_options"
# and "hhu_local_options", respectively.


def get_options(ctx: context.Context) -> ProjectInfo:
    """Extracts project information from invoke context."""
    project_info: ProjectInfo | None = None
    local_info: LocalInfo
    
    src_path: str | None = ctx.get("src_path")
    local_config: str = ctx.get("local_config", "hhu_tasks_local.yaml")
    config_file: str = ctx.get("config_file", "hhu_tasks.yaml")
    search_config: bool = bool(ctx.get("search_config", False))
    
    yaml_converter = make_yaml_converter()
    base = get_pyproject_path() or Path(".")
    pyp = get_pyproject(base / "pyproject.toml")
    ctx["pyproject"] = pyp
    
    # Try to read local configuration
    local_conf_path = base / local_config
    if local_conf_path.exists():
        logger.info(f"reading local configuration data from {local_conf_path}")
        local_info = yaml_converter.loads(local_conf_path.read_text(), LocalInfo)
    else:
        local_info = LocalInfo()
    ctx["hhu_local_options"] = local_info
    
    # Try to read project configuration
    project_conf_path = Path(config_file)
    if not project_conf_path.is_absolute() and search_config:
        search_dir = base
        while True:
            p = search_dir / config_file
            if p.exists():
                print(f"reading configuration data from {p}")
                project_info = yaml_converter.loads(p.read_text(), ProjectInfo)
                break
            prev_dir = search_dir
            search_dir = search_dir.parent
            if prev_dir == search_dir:
                # no chance of going further upwards
                p = base / config_file
                break
    else:
        p = base / project_conf_path
        if p.exists():
            print(f"reading configuration data from {p}")
            project_info = yaml_converter.loads(p.read_text(), ProjectInfo)
    
    if project_info is None:
        project_name = pyp.project["name"] if pyp.project is not None else ""
        project_info = ProjectInfo(project_name=project_name)
    elif project_info.project_name is None:
        project_name = pyp.project["name"] if pyp.project is not None else ""
        project_info.project_name = project_name
    ctx["hhu_options"] = project_info
    ctx["hhu_options_base"] = p.parent
    
    if os.environ.get("DEBUG_INV"):
        print("get_options:", f"{ctx['hhu_options']=}", f"{ctx['hhu_options_base']=}, {base=}")
    
    return project_info
