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
import base64

from datetime import datetime, timedelta
from sqlalchemy import func
from authlib.integrations.requests_client import OAuth2Session

from elekto import constants, APP, SESSION
from elekto.models.sql import User
from elekto.middlewares.auth import authenticated, csrf_guard, auth_guard


def oauth_session(vendor):
    """
    Create and return an OAuth2Session for the given vendor

    Args:
        vendor (dict): OAuth Vendor config with id, secret and scope

    Returns:
        OAuth2Session: OAuth2Session's object
    """
    return OAuth2Session(vendor['client_id'],
                         vendor['client_secret'],
                         scope=github['scope'])


# Common Login Routes


@APP.route('/login', methods=['GET'])
def render_login_page():
    # If the user is already is authenticated redirect it to the dashboard
    if authenticated():
        return F.redirect('/app')

    return F.render_template('login.html')


@APP.route('/logout', methods=['GET', 'POST'])
@auth_guard
def logout():
    # Remove the authentication token from user
    F.g.user.token = None
    F.g.user.token_expires_at = None
    SESSION.commit()

    # Remove the authentication token from current session
    F.session.pop(constants.AUTH_STATE)
    return F.redirect('/login')


# OAuth Routes
#
# It's very common for other organizations to use SSO or other vendor of their
# choice therefore please use the following route pattern for specifying other
# OAuth - /oauth/<vendor>/login and /oauth/<vendor>/callback

# Github
github = APP.config.get('GITHUB')


@APP.route('/oauth/github/login', methods=['POST'])
def oauth_github_login():
    client = oauth_session(github)
    uri, state = client.create_authorization_url(
        constants.GITHUB_AUTHORIZE)
    F.session[constants.CSRF_STATE] = state  # Enable CSRF protection
    # Set the redirect url
    if 'r' in F.request.args.keys():
        r = F.request.args.get('r').replace('$', '/').encode('ascii')
        redirect = base64.b64decode(r).decode('ascii')
        F.session['redirect'] = redirect

    return F.redirect(uri)


@APP.route(github['redirect'])
@csrf_guard
def oauth_github_redirect():
    client = oauth_session(github)
    token = client.fetch_token(constants.GITHUB_ACCESS,
                               authorization_response=F.request.url)
    oauthsession = OAuth2Session(client_id=github['client_id'],
                                 client_secret=github['client_secret'],
                                 token=token)
    resp = oauthsession.get(constants.GITHUB_PROFILE)
    if resp.status_code != 200:
        F.g.user = None
        F.g.auth = False

        # If GitHub couldn't fetch the user (who just now granted Elekto access to their GitHub profile), try to flush
        # the auth state from the session. Likely this isn't set, so a membership test is performed before doing the
        # pop(...) call.
        if constants.AUTH_STATE in F.session.keys():
            F.session.pop(constants.AUTH_STATE)
    else:
        data = resp.json()
        expries = datetime.now() + timedelta(days=1)
        # Match case-insensitively so a login whose case changed keeps its account (and its vote).
        # See: https://github.com/elekto-dev/elekto/issues/84
        query = SESSION.query(User).filter(
            func.lower(User.username) == data['login'].lower()).order_by(User.id).first()
        if query:
            query.token = token['access_token']
            query.token_expires_at = expries
        else:
            SESSION.add(User(username=data['login'],
                             name=data['name'],
                             token=token['access_token'],
                             token_expires_at=expries))
        SESSION.commit()
        # Add user's authentication token to the flask session
        F.session[constants.AUTH_STATE] = token['access_token']
        F.g.auth = True

    redirect = '/app'
    if 'redirect' in F.session.keys():
        redirect = F.session['redirect']
        F.session.pop('redirect')

    return F.redirect(redirect)
