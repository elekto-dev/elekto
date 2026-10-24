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

import flask as F

from functools import wraps
from elekto import SESSION, constants
from elekto.models.sql import Election
from elekto.models import meta
from datetime import datetime


def admin_guard(f):
    """
    Middleware (guard): checks if the current authorized user is election
    officer or not.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'eid' not in kwargs.keys() or F.g.user.username.lower() \
                not in meta.Election(kwargs['eid']).get()['election_officers']:
            F.flash('You are not an Election officer')
            return F.abort(401)
        return f(*args, **kwargs)
    return decorated_function


def voter_guard(f):
    """
    Middleware (guard): checks if the current authorized user is in the voters
    list of the election or not.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'eid' not in kwargs.keys():
            return F.abort(404)

        election = meta.Election(kwargs['eid'])
        voters = election.voters()

        if F.g.user.username.lower() not in voters['eligible_voters']:
            return F.render_template('errors/not_eligible.html',
                                     election=election.get())
        return f(*args, **kwargs)
    return decorated_function


def exception_guard(f):
    """
    Middleware (guard): checks if the current authorized user can created an
    exception request
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'eid' not in kwargs.keys():
            return F.abort(404)

        election = meta.Election(kwargs['eid'])
        voters = election.voters()

        if election.get()['exception_due'] < datetime.now():
            F.flash('Not accepting any exception request.')
            return F.redirect(F.url_for('elections_single', eid=kwargs['eid']))

        if F.g.user.username.lower() in voters['eligible_voters']:
            F.flash('You are already eligible to vote in the election.')
            return F.redirect(F.url_for('elections_single', eid=kwargs['eid']))

        return f(*args, **kwargs)
    return decorated_function


def has_completed_condition(f):
    """
    Middleware (condition): checks if the current election has completed or not
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'eid' not in kwargs.keys():
            return F.abort(404)

        election = meta.Election(kwargs['eid']).get()
        if election['status'] != constants.ELEC_STAT_COMPLETED:
            return F.render_template('errors/message.html',
                                     title='The election is not completed yet',
                                     message='The application needs election to be \
                                     over first.')
        return f(*args, **kwargs)
    return decorated_function


def has_voted_condition(f):
    """
    Middleware (condition): checks if the current authorized user has voted
    before or not
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'eid' not in kwargs.keys():
            return F.abort(404)
        e = SESSION.query(Election).filter_by(key=kwargs['eid']).first()

        if F.g.user.id not in [v.user_id for v in e.voters]:
            F.flash('You have not voted yet')
            return F.redirect(F.url_for('elections_single', eid=kwargs['eid']))

        return f(*args, **kwargs)
    return decorated_function
