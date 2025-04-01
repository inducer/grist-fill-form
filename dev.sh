#! /bin/bash

export GRIST_FILLFORM_CONFIG="config.yml"
export SECRET_KEY="CHANGE_ME"

uv run flask --app=fillform.app run --debug
