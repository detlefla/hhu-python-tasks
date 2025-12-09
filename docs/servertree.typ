#import "@preview/treet:1.0.0": tree-list

#set document(title: "Filesystem tree on Django server")
#title("Filesystem tree for Django project (HHUnet)")

= Server

`/` \
#tree-list[
- `home/`
  - `hhunet/`
    - `versions/`
      - `active/` → `deploy-XX-YY`
      - `deploy-XX-YY/`
        - `wheels/`
          - `django_hhunet-2.6.3-py3-none-any.whl`
          - `django_network_resources-0.19.4-py3-none-any.whl`
          - …
        - `project/`
          - `.python-version`
          - `.venv/`
          - `pyproject.toml`
          - `uv.lock`
    - `django/`
      - `local_django_settings.py`
      - `logs/`
      - `sitemedia/` (Upload-Daten)
      - `sitestatic/` (generiert)
      - `static_external/`
        - `external/`
          - `css/`
          - `fonts/`
          - `js/`
]

#pagebreak()
= Development environment

`~` \
#tree-list[
- `projects/`
  - `hhunet/`
    - `versions/`
      - `active/` → `deploy-XX-YY`
      - `deploy-XX-YY/`
        - `wheels/`
          - `django_hhunet-2.6.3-py3-none-any.whl`
          - `django_network_resources-0.19.4-py3-none-any.whl`
          - …
        - `project/`
          - `.python-version`
          - `.venv/`
          - `pyproject.toml`
          - `uv.lock`
    - `django/`
      - `local_django_settings.py`
      - `logs/`
      - `sitemedia/` (Upload-Daten)
      - `sitestatic/` (generiert)
      - `static_external/`
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
