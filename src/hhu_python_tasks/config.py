from enum import Enum, StrEnum
import logging
import msgspec
from pathlib import Path
from pyproject_parser import PyProject
import xdg_base_dirs


VENDOR = "de.hhu"
APP = "tasks"
DATA_DIR = xdg_base_dirs.xdg_data_home() / VENDOR / "wheels"
CONFIG_DIRS = [
        d / VENDOR / APP
        for d in [xdg_base_dirs.xdg_config_home()] + xdg_base_dirs.xdg_config_dirs()
        ]
CONFIG_EXTS = [".yaml", ".toml", ".json"]


class LogLevel(Enum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARN
    ERROR = logging.ERROR


class RunMode(StrEnum):
    CLI = "cli"
    INV = "invoke"
    INFRA = "pyinfra"
    SUBP = "subprocess"
    TUI = "tui"


class TargetInfo(msgspec.Struct):
    host: str
    remote_user: str
    base_path: Path | None = None
    django_path: Path | None = None
    service_names: list[str] = []
    backup_dir: Path | None = None
    backup_glob: str | None = None
    backup_pattern: str | None = None


class TasksOptions(msgspec.Struct):
    dry_run: bool = False
    verbose: bool = False
    log_level: LogLevel = LogLevel.WARN
    targets: dict[str, TargetInfo] = {}
    wheelhouse: Path = DATA_DIR


class RunOptions(msgspec.Struct):
    run_mode: RunMode
    project_name: str
    project_dir: Path
    project_info: PyProject
    options: TasksOptions


def get_wheeldir(runopts: RunOptions) -> Path:
    """Returns a path for the (user-global) wheel directory, created if necessary."""
    wheeldir = runopts.options.wheelhouse
    if not wheeldir.exists() and not runopts.options.dry_run:
        wheeldir.mkdir(mode=0o750, parents=True, exist_ok=True)
    return wheeldir

# def 