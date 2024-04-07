# Fill Forms with Existing Rows in Grist

This allows collecting form responses analogous to
[Grist Forms](https://www.getgrist.com/forms/), with the main difference
being that this focuses on adding data to an existing row, whereas Grist's
built-in forms appear to focus on adding new rows. Accordingly, this can
show data existing in the row to the user, to help them answer.

Forms are configured in a YAML file. See [`config.yml`](config.yml)
for an example.

To run, first run `poetry install` (see [poetry
docs](https://python-poetry.org/docs/)), then run `dev.sh`. Generalize/deploy
from there.

## UWSGI config for deployment

```
[uwsgi]
plugins = python311
socket = /tmp/uwsgi-grist-fill.sock

env = GRIST_FILLFORM_CONFIG=/home/grist-fill/grist-fill-form/config.yml
env = SECRET_KEY=CHANGE_ME

chdir = /home/grist-fill/grist-fill-form
module=fillform.app:app
uid = grist-fill
gid = grist-fill
need-app = 1
workers = 1
virtualenv=/home/grist-fill/grist-fill-form/.venv
buffer-size = 16384
```
