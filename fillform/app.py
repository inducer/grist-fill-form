from __future__ import annotations

import os
from dataclasses import dataclass
from functools import partial
from time import time
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

import yaml
from flask import Flask, Response, flash, request
from granian.utils.proxies import wrap_wsgi_with_proxy_headers
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel
from pygrist_mini import GristClient


if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence


UTC = ZoneInfo("UTC")


class WidgetConfig(BaseModel):
    column: str
    type: Literal["text", "yesno"]
    label: str | None = None
    optional: bool = False


class FormConfig(BaseModel):
    grist_root_url: str
    grist_api_key_file: str
    grist_doc_id: str
    table: str
    key_column: str
    response_time_column: str
    timezone: str | None = None
    allow_resubmit: bool = False
    header_markdown: str
    notify_from: str | None = None
    notify_to: str | None = None
    notify_if: str | None = None
    notify_subject: str | None = None
    notify_email: str | None = None
    widgets: list[WidgetConfig]


class Config(BaseModel):
    forms: dict[str, FormConfig]


flask_app = Flask(__name__)
flask_app.secret_key = os.environ["SECRET_KEY"]

app = wrap_wsgi_with_proxy_headers(flask_app)


def get_config() -> Config:
    with open(os.environ["GRIST_FILLFORM_CONFIG"]) as inf:
        data = yaml.safe_load(inf)
        return Config.model_validate(data)


CONFIG = get_config()

MSG_CAT_TO_BOOTSTRAP = {
    "error": "danger",
    "message": "primary",
    "warning": "warning",
}


def get_flashed_messages():
    from flask import get_flashed_messages
    msgs = {
        (MSG_CAT_TO_BOOTSTRAP.get(cat, "primary"), msg)
        for cat, msg in get_flashed_messages(with_categories=True)
    }

    return msgs


# based on https://stackoverflow.com/a/76636602
def exec_with_return(
        code: str, location: str, globals: dict[str, object] | None,
        locals: dict[str, object] | None = None,
        ) -> Any:
    import ast
    a = ast.parse(code)
    last_expression = None
    if a.body:
        if isinstance(a_last := a.body[-1], ast.Expr):
            last_expression = ast.unparse(a.body.pop())
        elif isinstance(a_last, ast.Assign):
            last_expression = ast.unparse(a_last.targets[0])
        elif isinstance(a_last, (ast.AnnAssign, ast.AugAssign)):
            last_expression = ast.unparse(a_last.target)
    compiled_code = compile(ast.unparse(a), location, "exec")
    exec(compiled_code, globals, locals)  # noqa: S102
    if last_expression:
        return eval(last_expression, globals, locals)


def send_notify(
            jinja_env: Environment,
            form_config: FormConfig,
            row_data: dict[str, Any],
        ) -> None:
    import smtplib
    from email.message import EmailMessage

    if form_config.notify_if is not None:
        do_notify = exec_with_return(form_config.notify_if, "notify_if", row_data)
        if not do_notify:
            return

    assert form_config.notify_email is not None
    assert form_config.notify_subject is not None

    msg = EmailMessage()
    msg.set_content(jinja_env
                    .from_string(form_config.notify_email)
                    .render(**row_data))

    import re
    msg["Subject"], _ = (
        re.subn(r"\s+", " ",
                jinja_env
                .from_string(form_config.notify_subject)
                .render(**row_data)))

    msg["From"] = form_config.notify_from
    msg["To"] = form_config.notify_to

    s = smtplib.SMTP("localhost")
    s.send_message(msg)
    s.quit()


def respond_with_message(
            jinja_env: Environment,
            msg: str,
            category: Literal["error", "message"] = "message",
            status: int | None = None,
        ) -> Response:
    flash(msg, category)
    resp_text = (jinja_env
            .get_template("base.html")
            .render(messages=get_flashed_messages()))

    return Response(resp_text, status)


@dataclass(frozen=True)
class Widget:
    id: str
    label: str
    type: str
    value: str | None
    validation_message: str | None


def render_form(
            form_config: FormConfig,
            row: Mapping[str, Any],
            form_data: Mapping[str, Any] | None = None
        ) -> tuple[bool, Sequence[Widget], dict[str, object]]:

    valid = form_data is not None

    widgets = []
    user_input = {}
    for widget in form_config.widgets:
        col = widget.column

        if form_data is None:
            valid_msg = None
            val = row[col]
        else:
            valid_msg = None

            val = form_data.get(col)
            if not widget.optional and not val:
                valid_msg = "This field is required."

            if not valid_msg:
                if widget.type == "yesno":
                    if val not in ["0", "1"]:
                        valid_msg = "Invalid input."
                    else:
                        user_input[col] = bool(int(form_data[col]))

                elif widget.type == "text":
                    user_input[col] = val if val else ""

                else:
                    raise AssertionError("invalid widget type")

        if valid_msg:
            valid = False

        widgets.append(Widget(
                           id=col,
                           label=(widget.label
                               if widget.label else col.replace("_", " ")),
                           type=widget.type,
                           value=val if val else "",
                           validation_message=valid_msg,
                       ))

    return valid, widgets, user_input


def format_date_timestamp(
            tstamp: float,
            format: str = "%Y-%m-%d",
        ) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(tstamp, tz=UTC).date()
    return dt.strftime(format)


def format_timestamp(
            tstamp: float,
            format: str = "%c",
            timezone: ZoneInfo | None = None
        ) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(tstamp, tz=timezone)
    return dt.strftime(format)


@flask_app.route("/form/<name>/<key>", methods=["GET", "POST"])
def fill_form(name: str, key: str):
    jinja_env = Environment(
        loader=PackageLoader("fillform"),
        autoescape=select_autoescape(),
        undefined=StrictUndefined)

    if name not in CONFIG.forms:
        return respond_with_message(jinja_env, "Not found", "error", status=404)

    form_config = CONFIG.forms[name]

    if form_config.timezone is not None:
        from zoneinfo import ZoneInfo
        from_ts: Callable[[float, str], str] = partial(
                    format_timestamp,
                    timezone=ZoneInfo(form_config.timezone))
    else:
        from warnings import warn
        warn("'timezone' key not specified, timestamps will be local", stacklevel=1)
        from_ts = format_timestamp

    jinja_env.filters["format_timestamp"] = from_ts
    jinja_env.filters["format_date_timestamp"] = format_date_timestamp

    grist_root_url = form_config.grist_root_url
    with open(form_config.grist_api_key_file) as inf:
        grist_api_key = inf.read().strip()
    grist_doc_id = form_config.grist_doc_id

    grist_client = GristClient(grist_root_url, grist_api_key, grist_doc_id)

    rows = grist_client.get_records(
              form_config.table,
              filter={form_config.key_column: [key]})
    if not rows:
        return respond_with_message(jinja_env, "Not found", "error", status=404)
    if len(rows) > 1:
        return respond_with_message(
            jinja_env, "More than one record found for request key", "error",
            status=500)

    row_data, = rows
    row = row_data["fields"]
    row_id = row_data["id"]

    header_markdown_expanded = (jinja_env
        .from_string(form_config.header_markdown)
        .render(**row))
    from markdown import markdown
    header_html = markdown(header_markdown_expanded, extensions=["extra"])

    allow_resubmit = form_config.allow_resubmit

    if request.method == "GET":
        if row[form_config.response_time_column] is not None:
            if allow_resubmit:
                flash("Your response has previously been recorded. "
                      "You may update your submission below.")
            else:
                return respond_with_message(
                    jinja_env, "Your response has previously been recorded. ", "error")

        _valid, widgets, _data = render_form(form_config, row)

        html = jinja_env.get_template("index.html").render(
            messages=get_flashed_messages(),
            was_validated=False,
            header=header_html,
            widgets=widgets
        )

        return Response(html)

    elif request.method == "POST":
        if not allow_resubmit and row[form_config.response_time_column] is not None:
            return respond_with_message(
                jinja_env,
                "Your response has previously been submitted. "
                "The present response has not been recorded.", "error")

        valid, widgets, user_input = render_form(form_config, row, request.form)
        if not valid:
            html = jinja_env.get_template("index.html").render(
                messages=get_flashed_messages(),
                was_validated=True,
                header=header_html,
                widgets=widgets
            )

            return Response(html, 400)

        # {{{ notification email

        if (form_config.notify_to is not None
                and form_config.notify_from is not None):
            notify_data = dict(row)
            notify_data.update(user_input)
            send_notify(jinja_env, form_config, notify_data)

        # }}}

        row_updates: dict[str, object] = {
                form_config.response_time_column: time(),
        }
        row_updates.update(user_input)

        grist_client.patch_records(form_config.table, [(row_id, row_updates)])

        return respond_with_message(
                jinja_env, "Thank you for submitting your response.")
    else:
        raise ValueError(f"unexpected method {request.method}")


# vim: foldmethod=marker
