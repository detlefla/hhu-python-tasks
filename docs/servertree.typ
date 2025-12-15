#import "@preview/treet:1.0.0": tree-list

#set document(title: "Filesystem tree on Django server")
#title("Filesystem tree for Django project (HHUnet)")
#let c-r(it) = {
  set text(0.8em, font: "DejaVu Sans Mono", stroke: blue, weight: 100)
  it
}

= Server

`/` \
#tree-list[
- `home/`
  - `hhunet/`
    - `versions/`
      - `active/` → `deploy-XX-YY`
      - `deploy-XX-YY/`
        - `wheels/` _(rsync'ed here)_
          - `django_hhunet-2.6.3-py3-none-any.whl`
          - `django_network_resources-0.19.4-py3-none-any.whl`
          - …
        - `.python-version`
        - `.venv/`
        - `pyproject.toml`
        - `uv.lock`
      - `deploy-XX-ZZ/`
        - …
    - `django/`
      - `local_django_settings.py` _(server settings)_
      - `logs/`
      - `sitemedia/` _(Upload-Daten)_
      - `sitestatic/` _(generiert)_
      - `static_external/` _(von ext-res verwaltet)_
        - `external/`
          - `css/`
          - `fonts/`
          - `js/`
]

#pagebreak()
= Development environment example

== Overview
The project base directory, here `~/projects/hhunet/`, is arbitrary.

`~` \
#tree-list[
- `projects/`
  - `hhunet/`
    - `hhu_tasks_config.yaml` _(marker for project group tree)_
    - `local_django_settings.yaml` _(debug settings for local db)_
    - `local_django_settings_prod` _(no-debug settings for local db)_
    - `dev/` _(dev combinations of branches, Python versions etc. for runserver)_
    - `stage/` _(prepared for deployment)_
    - `versions/` _(production-like deployments)_
    - `django/` _(Django runtime files: `site*` etc., dev settings)_
    - `PACKAGE1/`
      - `master/`
      - `f-myfeature/`
    - `PACKAGE2/`
      - `master/`
    - …
]

#pagebreak()
== More detailed directory list

`~` \
#tree-list[
- `projects/`
  - `hhunet/`
    - `hhu_tasks_config.yaml` _(marker for project group tree)_
    - `local_django_settings.yaml` _(debug settings for local db)_
    - `local_django_settings_prod` _(no-debug settings for local db)_
    - `dev/`
      - `DEVNAME1/`
        - `pyproject.toml`
      - …
    - `stage/`
      - `deploy-XX-YY/`
        - `pyproject.toml`
        - `wheels/` _(wheels are collected here)_
      - …
    - `versions/`
      - `local_django_settings.py` _(with local db, no `DEBUG`)_
      - `active/` → `deploy-XX-YY`
      - `deploy-XX-YY/`
        - `wheels/` _(wheels are copied here)_
          - `asgiref-3.11.0-py3-none-any.whl`
          - …
          - `django_hhunet-2.6.3-py3-none-any.whl`
          - `django_network_resources-0.19.4-py3-none-any.whl`
          - …
        - `.python-version`
        - `.venv/`
        - `pyproject.toml`
        - `uv.lock`
    - `django/`
      - `local_django_settings.py` _(with local db, `DEBUG=True`)_
      - `local_django_prod_settings.py` _(with local db, no `DEBUG`)_
      - `logs/`
      - `sitemedia/` _(Upload-Daten)_
      - `sitestatic/` _(generiert)_
      - `static_external/` _(von ext-res verwaltet)_
        - `external/`
          - `css/`
          - `fonts/`
          - `js/`
    - `hhunet/`
      - `master/`
        - `pyproject.toml`
        - `README.md`
        - `LICENSE`
        - `src/`
          - `hhunet/`
            - `urls.py`
            - `models.py`
            - `views.py`
            - `templates/`
              - `hhunet/`
                - `base.html`
                - …
            - …
    - `netres/`
      - `master/`
        - `pyproject.toml`
        - …
    - `zimdj/`
      - `master/`
        - `pyproject.toml`
        - …
]

#pagebreak()
== Task management commands
/*
```sh
hhu-tasks run [--name=py313] hhunet showmigrations

hhu-tasks runserver [--name=py313]

hhu-tasks stage [--name=1210] [--dev=py313]

hhu-tasks run --staged [--name=1210] hhunet check

hhu-tasks deploy [--name=1210] [@hhunet]

hhu-tasks run --deployed [--name=1210] hhunet check
```

*Tested as follows:*
*/
```sh
cd ~/projects/hhunet/hhunet/master

export UV_PROJECT=~/projects/hhunet/dev312

hhu-tasks stage 1210
      
DJANGO_SETTINGS_MODULE=local_django_settings_prod \
   uv run --project ../../stage/1210 hhunet check
      
hhu-tasks deploy
      
DJANGO_SETTINGS_MODULE=local_django_settings_prod \
   uv run --project ../../versions/1210 hhunet check
```

#pagebreak()
== Where configuration and context data is found

/ Current development project:
  determines software configuration (venv) and Python version,
  identifies editable source trees and their branches,
  found through:
  + hhu-tasks commandline argument `--project`
  + environment variable `HHU_PROJECT`
  + environment variable `UV_PROJRCT`
  + searching for a `pyproject.toml` file from current directory upwards

/ Staging project for deployment:
  determines the set of wheels to be collected for the installation on
  a target system and is selected:
  + through the hhu-tasks commandline argument `--name` as subdirectory name
  + as the alphanumerically highest subdirectory

/ Django environment:
  contains the `sitemedia`, `sitestatic`, and `static_external` directories
  and the primary settings file; it is assumed in the directory given by
  + hhu-tasks `--directory` commandline argument
  + environment variable `HHU_DIRECTORY`
  + environment variable `UV_DIRECTORY`
  + the current directory at hhu-tasks invocation
  or its nearest parent where the local Django settings file is found
  whose name is
  + in the environment variable `DJANGO_SETTINGS_MODULE` or
  + `local_django_settings.py`

/ hhu-tasks settings:
  specify a non-standard directory layout, the names and locations of editable
  modules to install into a development project, information on remote hosts
  where deployments can be made, and some options for hhu-tasks subcommands;
  they are assumed in a file
  + given as hhu-tasks commandline argument `--config-file`
  + in a file `hhu_tasks.yaml` in the directory given by
    + hhu-tasks `--directory` commandline argument
    + environment variable `HHU_DIRECTORY`
    + environment variable `UV_DIRECTORY`
    + the current directory at hhu-tasks invocation
    or its nearest parent
