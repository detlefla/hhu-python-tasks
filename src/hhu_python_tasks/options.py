import logging
import msgspec
import os
from pathlib import Path
import sys
from typing import Any, Type


PROJECT_CONFIG = "hhu_tasks.yaml"

# names of used environment variables
ENV_HHU_DIRECTORY = "HHU_DIRECTORY"
ENV_UV_DIRECTORY = "UV_DIRECTORY"
ENV_HHU_PROJECT = "HHU_PROJECT"
ENV_UV_PROJECT = "UV_PROJECT"

logger = logging.getLogger("hhu_tasks")


class Target(msgspec.Struct):
    host: str | None = None
    admin_user: str | None = None
    app_user: str | None = None
    django_base: Path | None = None
    use_systemd: bool = True
    python_version: str | None = None
    backup_directory: Path | None = None
    backup_filename_glob: str | None = None


class ProjectGroup(msgspec.Struct):
    main_package: str
    needs: list[str] = []
    project_id: int | None = None
    targets: dict[str, Target] = {}


class EditablePackage(msgspec.Struct):
    location: Path
    editor_options: dict[str, list[str]] = {}
    editor_files: list[Path] = []


class Config(msgspec.Struct):
    main_package: str
    needs: list[str] = []
    project_id: int | None = None
    management_command: str = "./manage.py"
    targets: dict[str, Target] = {}
    editable_packages: dict[str, EditablePackage] = {}


class Options(msgspec.Struct):
    config: Config
    base_dir: Path
    project_dir: Path
    project_file: Path
    pyproject_data: dict
    python_version: str
    config_path: Path | None
    directory: Path
    verbose: bool
    dry_run: bool
    debug: bool


def find_file(
        filename: str | Path,
        start_dir: Path | None = None,
        ) -> Path | None:
    """Looks for a file with given name from start_dir upwards."""
    if start_dir is None:
        start_dir = Path.cwd()
    directory = start_dir
    filename = str(filename)
    while True:
        candidate = directory / filename
        if candidate.exists():
            logger.debug("finding file “%s” at “%s”", filename, candidate.parent)
            return candidate
        parent = directory.parent
        if parent == directory:
            return None
        directory = parent


def decode_path(type: Type, obj: Any) -> Any:
    """Converts objects to Path type for msgspec decoding."""
    if type == Path:
        return Path(obj)
    else:
        return obj


def get_options(
        *,
        config_file: Path | None,
        project: Path | None,
        directory: Path | str | None,
        python_version: str | None,
        dry_run: bool,
        verbose: bool,
        debug: bool,
        ) -> Options:
    """Processes subcommand options in a standard way."""
    
    # control logger
    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
    
    # make relative paths absolute before changing directory
    if config_file is not None:
        config_file = config_file.expanduser().absolute()
    if project is not None:
        project = project.expanduser().absolute()
    
    # get directory to change to
    if directory is None:
        directory = os.environ.get(ENV_HHU_DIRECTORY)
    if directory is None:
        directory = os.environ.get(ENV_UV_DIRECTORY)
    if directory is None:
        directory = Path.cwd()
    else:
        directory = Path(directory)
        directory = directory.expanduser().absolute()
        os.chdir(directory)
        logger.debug("changed into directory %s", directory)
    
    # find project config file
    if config_file is None:
        config_file = find_file(PROJECT_CONFIG)
    elif not config_file.is_absolute():
        config_file = find_file(str(config_file))
    else:
        config_file = config_file.expanduser()
    if config_file is not None and config_file.exists():
        base_dir = config_file.parent
        config_data = config_file.read_text()
        logger.debug("reading config file %s", config_file)
        config = msgspec.yaml.decode(
                config_data,
                type=Config,
                dec_hook=decode_path,
                )
        logger.info("using config file %s", config_file)
    else:
        config = Config(main_package="")
        base_dir = Path.cwd()
        logger.info("using no config file")
    
    # find project file
    if project is None:
        project_env = os.environ.get(ENV_HHU_PROJECT)
        if project_env:
            project = Path(project_env).expanduser().absolute()
    if project is None:
        project_env = os.environ.get(ENV_UV_PROJECT)
        if project_env:
            project = Path(project_env).expanduser().absolute()
    if project is None:
        project_file = find_file("pyproject.toml")
        if project_file is None:
            raise ValueError("no pyproject.toml file found")
        project_dir = project_file.parent
    else:
        project_dir = project
        if not project_dir.is_dir():
            raise ValueError(f"project “{project}” is not a directory")
        project_file = project_dir / "pyproject.toml"
        if not project_file.exists():
            raise ValueError(f"pyproject.toml file not found at {project}")
    logger.info("working with project file %s", project_file)
    
    pyproject_data = msgspec.toml.decode(project_file.read_text())
    logger.debug("using project file %s", project_file)
    if not config.main_package:
        config.main_package = pyproject_data["project"]["name"]  # fake entry
    
    if python_version is None:
        py_vers = project_dir / "python.version"
        if py_vers.exists():
            python_version = py_vers.read_text()
        else:
            vi = sys.version_info
            python_version = f"{vi.major}.{vi.minor}"
    logger.info("using Python version %s", python_version)
    
    options = Options(
            config = config,
            base_dir = base_dir,
            project_dir = project_dir,
            project_file = project_file,
            pyproject_data = pyproject_data,
            python_version = python_version,
            config_path = config_file,
            directory = directory,
            dry_run = dry_run,
            verbose = verbose,
            debug = debug,
            )
    return options
