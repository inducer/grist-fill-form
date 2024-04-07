# Fill Forms with Existing Rows in Grist

This allows collecting form responses analogous to
[Grist Forms](https://www.getgrist.com/forms/), with the main difference
being that this focuses on adding data to an existing row, whereas Grist's
built-in forms appear to focus on adding new rows. Accordingly, this can
show data existing in the row to the user, to help them answer.

- Forms are configured in a YAML file. See [`config.yml`](config.yml)
  for an example. 
- Multiple forms can be configured by `NAME`, 
  this is the identifier under `forms`.
  This appears in the URL as `https://HOSTNAME/form/NAME/KEY`.
- The configured `key_column` identifies the column being searched
  for `KEY`. This identifies the row being edited and is expected
  to be unique.
- Forms have a Markdown header which is expanded as a 
  [Jinja](https://jinja.palletsprojects.com/) templates.
  Column values for the selected row are available as variables.
- Forms can optionally send a notification email when submitted.
  This email is likewise expanded as a Jinja template, and
  its sending can be made contingent on user-submitted data.
- Right now, only two form widgets are supported: `text` and `yesno`.
  There is no form validation beyond marking some fields optional.
- The UI is moderately pleasant-to-look-at Bootstrap 5.

Forms are public and require no authentication beyond knowledge of the `KEY`.

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
