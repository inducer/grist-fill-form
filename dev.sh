#! /bin/bash

export GRIST_FILLFORM_CONFIG="config.yml"
export SECRET_KEY="CHANGE_ME"

poetry run flask --app=fillform.app run --debug
