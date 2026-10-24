# Copyright 2020 The Elekto Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Author(s):         Manish Sahani <rec.manish.sahani@gmail.com>

import datetime

import flask as F
from flask_wtf.csrf import CSRFProtect

from elekto.models import sql
from elekto.version import __version__

APP = F.Flask(__name__)
APP.config.from_object('config')
csrf = CSRFProtect(APP)
SESSION = sql.create_session(APP.config.get('DATABASE_URL'))  # database

from elekto.models import meta  # noqa - imports SESSION from here
from elekto import utils  # noqa - imports SESSION from here


@APP.before_request
def before_request():
    # Add APP name and other organization based configration in the global
    # request object
    F.g.NAME = APP.config.get('NAME')

    # When you import jinja2 macros, they get cached which is annoying for
    # local development, so wipe the cache every request.
    if APP.config.get('DEBUG') or 'localhost' in F.request.host_url:
        APP.jinja_env.cache = {}

    # Set Session
    utils.set_session(APP)


@APP.teardown_appcontext
def destroy_session(exception=None):
    # Remove the database session
    SESSION.remove()


@APP.context_processor
def inject_version():
    return dict(elekto_version=__version__,
                current_year=datetime.datetime.now().year)


####
# Controllers

import elekto.controllers  # noqa - this circular import is fine
