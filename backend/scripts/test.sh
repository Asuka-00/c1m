#!/usr/bin/env bash

set -e
set -x

FASTAPI_ENV=development coverage run -m pytest
coverage report
coverage html --title "${@-coverage}"
