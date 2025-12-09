import msgspec
import os
from pathlib import Path
from typing import Any, Type


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
    project_groups: dict[str, ProjectGroup] = {}
    editable_packages: dict[str, EditablePackage] = {}


class Options(msgspec.Struct):
    config: Config
    project_dir: Path
    project_file: Path
    pyproject_data: dict
    project_group: str
    config_path: Path | None
    directory: Path
    verbose: bool
    dry_run: bool


def find_file(
        filename: str,
        start_dir: Path | None = None,
        ) -> Path | None:
    """Looks for a file with given name from start_dir upwards."""
    if start_dir is None:
        start_dir = Path.cwd()
    directory = start_dir
    while True:
        candidate = directory / filename
        if candidate.exists():
            return candidate
        parent = directory.parent
        if parent == directory:
            return None
        directory = parent


def decode_path(type: Type, obj: Any) -> Any:
    if type == Path:
        return Path(obj)
    else:
        return obj


def find_project_group(config: Config, pyproject_data: dict) -> str:
    deps: set[str] = set()
    for dep in pyproject_data["project"]["dependencies"]:
        dep = dep.split("[")[0]
        deps.add(dep)
    for name, pg in config.project_groups.items():
        if pg.main_package not in deps:
            continue
        for pkg in pg.needs:
            if pkg not in deps:
                continue
        break
    else:
        raise ValueError(f"could not identify project group from {deps}")
    return name


def get_options(
        config_file: Path,
        project: Path | None,
        directory: Path | None,
        project_group: str | None,
        
        dry_run: bool,
        verbose: bool,
        ) -> Options:
    
    if directory is None:
        directory = Path.cwd()
    else:
        directory = directory.expanduser().absolute()
        os.chdir(directory)
    
    config_file = config_file.expanduser().absolute()
    if config_file.exists():
        config_data = config_file.read_text()
        config = msgspec.yaml.decode(config_data, type=Config, dec_hook=decode_path)
    else:
        config = ConfigData()
    
    if project is None:
        project_file = find_file("pyproject.toml")
        if project_file is None:
            raise ValueError("no pyproject.toml file found")
        project_dir = project_file.parent
    else:
        project_dir = project.expanduser().absolute()
        if not project_dir.is_dir():
            raise ValueError(f"project “{project}” is not a directory")
        project_file = project_dir / "pyproject.toml"
        if not project_file.exists():
            raise ValueError(f"pyproject.toml file not found at {project}")
    
    pyproject_data = msgspec.toml.decode(project_file.read_text())
    
    if project_group is None:
        project_group = find_project_group(
                config = config,
                pyproject_data = pyproject_data,
                )
    else:
        if project_group not in config.project_groups:
            raise ValueError(f"project group {project_group} is undefined in config")
    
    # XXX all targets: insert current user if admin_user is None
    
    options = Options(
            config = config,
            project_dir = project_dir,
            project_file = project_file,
            pyproject_data = pyproject_data,
            project_group = project_group,
            config_path = config_file,
            directory = directory,
            dry_run = dry_run,
            verbose = verbose,
            )
    return options
