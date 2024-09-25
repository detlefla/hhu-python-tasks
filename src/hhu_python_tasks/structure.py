from attrs import define, Factory
from cattrs.preconf.pyyaml import make_converter as make_yaml_converter
# from cattrs.preconf.json import make_converter as make_json_converter
from fabric import Connection
from invoke import context
import logging
from pathlib import Path
import sys

from .utils import get_pyproject_path


logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)


@define
class RemoteHostInfo:
    hostname: str
    base_path: Path
    django_dir: Path
    user: str
    
    def __attrs_post_init__(self):
        if isinstance(self.base_path, str):
            self.base_path = Path(self.base_path)
        if isinstance(self.django_dir, str):
            self.django_dir = Path(self.django_dir)


@define
class BackupInfo:
    hostname: str
    directory: Path
    user: str
    filename_glob: str
    filename_pattern: str
    
    def __attrs_post_init__(self):
        if isinstance(self.directory, str):
            self.directory = Path(self.directory)


@define
class SubPackageInfo:
    name: str
    workdir: Path
    
    def __attrs_post_init__(self):
        if isinstance(self.workdir, str):
            self.workdir = Path(self.workdir)


@define
class ProjectInfo:
    project_name: str
    project_id: int = 99
    src_path: Path | None = None
    private_files: Path | None = None
    package_name: str | None = None
    target: RemoteHostInfo | None = None
    python_version: str | None = None
    runserver_port: int | None = None
    wheelhouse: Path | None = None
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
        if self.wheelhouse is None:
            self.wheelhouse = get_pyproject_path() / "wheels"
        # cattrs doesn't deliver Path instances??
        if isinstance(self.src_path, str):
            self.src_path = Path(self.src_path)
        if isinstance(self.private_files, str):
            self.private_files = Path(self.private_files)
        if isinstance(self.wheelhouse, str):
            self.wheelhouse = Path(self.wheelhouse)


def get_options(ctx: context.Context) -> ProjectInfo:
    """Extracts project information from invoke context."""
    pi: ProjectInfo
    if "config_file" in ctx:
        filename = Path(ctx["config_file"]).expanduser()
        base = get_pyproject_path()
        if base is None:
            base = Path(".")
        filename = (base / filename).absolute()
        yaml_converter = make_yaml_converter()
        pi = yaml_converter.loads(filename.read_text(), ProjectInfo)
        logger.info(f"reading configuration data from {filename}")
    else:
        ctx_info = {a.name: ctx[a.name]
                for a in ProjectInfo.__attrs_attrs__ if a.name in ctx}
        pi = ProjectInfo(**ctx_info)
    ctx["hhu_options"] = pi
    return pi


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
