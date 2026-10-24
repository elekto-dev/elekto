import base64
import urllib.parse
from unittest import mock

from flask.testing import FlaskClient
from freezegun import freeze_time

from elekto import APP, SESSION
from elekto.models.sql import User

from .mocks import MockUserResponse, MockTokenResponse
from .utils import get_csrf_token, is_authenticated, provision_session, create_user, user_exists, vote


def test_login_renders(client: FlaskClient):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Sign in with Github' in response.data


@mock.patch('elekto.controllers.authentication.authenticated', return_value=True)
def test_login_redirects_if_authenticated(auth_mock, client: FlaskClient):
    response = client.get('/login')
    assert response.status_code == 302
    assert response.headers['Location'] == '/app'
    assert b'You should be redirected automatically to the target URL: <a href="/app">/app</a>' in response.data


def test_logout_requires_authenticated_user(client: FlaskClient):
    response = client.get('/logout')
    assert response.status_code == 302
    assert '/login?r=' in response.headers['Location']
    assert b'You should be redirected automatically to the target URL: <a href="/login?r=' in response.data


def test_logout_flushes_session(client: FlaskClient):
    token = 'token'
    provision_session(client, token)

    # Verify the user is authenticated before logging out
    assert is_authenticated(client)

    # Logout
    logout_response = client.get('/logout')
    assert logout_response.status_code == 302
    # The valid redirect (for a user who was previously logged in) looks a lot like the one for unauthenticated users,
    # but can be identified by the redirect URL not having a URL query.
    assert logout_response.headers['Location'] == '/login'
    assert b'You should be redirected automatically to the target URL: <a href="/login"' in logout_response.data

    # After logout a login should be required again i.e. /login won't redirect
    assert not is_authenticated(client)


@mock.patch('authlib.oauth2.client.generate_token')
def test_github_login(token_mock, client: FlaskClient):
    oauth_token = 'fooBar42!'
    token_mock.return_value = oauth_token

    response = client.post('/oauth/github/login', data={'csrf_token': get_csrf_token(client)})
    assert response.status_code == 302

    query_map = {
        'response_type': 'code',
        'client_id': 'ghclientid',
        'scope': 'user:login,name',
        'state': oauth_token,
    }
    query_string = urllib.parse.urlencode(query_map)

    assert response.headers['Location'] == f'https://github.com/login/oauth/authorize?{query_string}'


@mock.patch('authlib.oauth2.client.generate_token')
@mock.patch('authlib.oauth2.client.OAuth2Client.fetch_token')
@mock.patch('requests.sessions.Session.get')
def test_github_login_with_redirect_for_existing_user(get_mock, fetch_token_mock, generate_token_mock, client: FlaskClient):
    """
    A 'redirect' URL is added to the session state if a user tries to navigate to an authentication-protected page
    without being logged in. This is a complete URL such as 'http://localhost:8000/app/elections' and is NOT included in
    the URL query string for the GitHub redirect.
    """
    oauth_token = 'fooBar42!'
    create_user(oauth_token)
    get_mock.return_value = MockUserResponse(json={
        'login': 'carson',
        'name': 'Carson Weeks',
        'access_token': '...',
    })
    fetch_token_mock.return_value = MockTokenResponse(json={
        'access_token': oauth_token,
    }).json()
    csrf_token = get_csrf_token(client)

    generate_token_mock.return_value = csrf_token

    redirect_url= 'http://localhost:8000/app/elections'
    encoded_redirect_url= base64.b64encode(redirect_url.encode('ascii')).decode('ascii').replace('/', '$')

    response = client.post(f'/oauth/github/login?r={encoded_redirect_url}', data={
        'csrf_token': csrf_token,
    })
    assert response.status_code == 302

    query_map = {
        'response_type': 'code',
        'client_id': 'ghclientid',
        'scope': 'user:login,name',
        'state': csrf_token,
    }
    query_string = urllib.parse.urlencode(query_map)

    assert response.headers['Location'] == f'https://github.com/login/oauth/authorize?{query_string}'

    # Assert the redirect URL is stored in the session and used in the GitHub callback.
    response = client.get(f'/oauth/github/callback?state={csrf_token}')
    assert response.status_code == 302
    assert response.headers['Location'] == redirect_url

    # Finally, user should be able to navigate to the dashboard.
    response = client.get("/app")
    assert response.status_code == 200
    assert b'Welcome! Carson Weeks' in response.data


@mock.patch('authlib.oauth2.client.generate_token')
@mock.patch('authlib.oauth2.client.OAuth2Client.fetch_token')
@mock.patch('requests.sessions.Session.get')
def test_github_login_with_redirect_for_new_user(get_mock, fetch_token_mock, generate_token_mock, client: FlaskClient):
    # Confirm the user doesn't yet exist.
    assert not user_exists('carson')

    oauth_token = 'fooBar42!'
    get_mock.return_value = MockUserResponse(json={
        'login': 'carson',
        'name': 'Carson Weeks',
        'access_token': '...',
    })
    fetch_token_mock.return_value = MockTokenResponse(json={
        'access_token': oauth_token,
    }).json()
    csrf_token = get_csrf_token(client)

    generate_token_mock.return_value = csrf_token

    redirect_url= 'http://localhost:8000/app/elections'
    encoded_redirect_url= base64.b64encode(redirect_url.encode('ascii')).decode('ascii').replace('/', '$')

    response = client.post(f'/oauth/github/login?r={encoded_redirect_url}', data={
        'csrf_token': csrf_token,
    })
    assert response.status_code == 302

    query_map = {
        'response_type': 'code',
        'client_id': 'ghclientid',
        'scope': 'user:login,name',
        'state': csrf_token,
    }
    query_string = urllib.parse.urlencode(query_map)

    assert response.headers['Location'] == f'https://github.com/login/oauth/authorize?{query_string}'

    # Assert the redirect URL is stored in the session and used in the GitHub callback.
    response = client.get(f'/oauth/github/callback?state={csrf_token}')
    assert response.status_code == 302
    assert response.headers['Location'] == redirect_url

    # Confirm the user was created.
    assert user_exists('carson')

    # Finally, user should be able to navigate to the dashboard.
    response = client.get("/app")
    assert response.status_code == 200
    assert b'Welcome! Carson Weeks' in response.data


@mock.patch('authlib.oauth2.client.generate_token')
@mock.patch('authlib.oauth2.client.OAuth2Client.fetch_token')
@mock.patch('requests.sessions.Session.get')
def test_github_login_fails_user_not_found(get_mock, fetch_token_mock, generate_token_mock, client: FlaskClient):
    # Confirm the user doesn't yet exist.
    assert not user_exists('carson')

    oauth_token = 'fooBar42!'
    # This mock simulates a failure in the call fetching the user's GitHub profile.
    get_mock.return_value = MockUserResponse(json={}, status_code=404)
    fetch_token_mock.return_value = MockTokenResponse(json={
        'access_token': oauth_token,
    }).json()
    csrf_token = get_csrf_token(client)

    generate_token_mock.return_value = csrf_token

    redirect_url= 'http://localhost:8000/app/elections'
    encoded_redirect_url= base64.b64encode(redirect_url.encode('ascii')).decode('ascii').replace('/', '$')

    response = client.post(f'/oauth/github/login?r={encoded_redirect_url}', data={
        'csrf_token': csrf_token,
    })
    assert response.status_code == 302

    query_map = {
        'response_type': 'code',
        'client_id': 'ghclientid',
        'scope': 'user:login,name',
        'state': csrf_token,
    }
    query_string = urllib.parse.urlencode(query_map)

    assert response.headers['Location'] == f'https://github.com/login/oauth/authorize?{query_string}'

    # Assert the redirect URL is stored in the session and used in the GitHub callback.
    response = client.get(f'/oauth/github/callback?state={csrf_token}')
    assert response.status_code == 302
    assert response.headers['Location'] == redirect_url

    # The user wasn't created as the GitHub fetch failed.
    assert not user_exists('carson')

    # User shouldn't be able to navigate to the dashboard as the authentication state couldn't be completed.
    response = client.get("/app")
    assert response.status_code == 302
    assert response.headers['Location'].startswith('/login?r=')


# TODO: Add tests that check case sensitivity in GitHub usernames. GitHub's usernames are case-insensitive, but Elekto does consider these case-sensitive. This is far from the only place in the codebase to test for case-sensitivity, but it's a start.


@freeze_time('2023-08-04')
@mock.patch('authlib.oauth2.client.generate_token')
@mock.patch('authlib.oauth2.client.OAuth2Client.fetch_token')
@mock.patch('requests.sessions.Session.get')
def test_github_login_ignores_login_case_for_existing_user(get_mock, fetch_token_mock, generate_token_mock,
                                                           client: FlaskClient, load_metadir):
    """A user whose GitHub login changed case keeps their existing account, and therefore their vote."""
    oauth_token = 'fooBar42!'
    create_user(oauth_token, username='Kalkayan')
    vote('Kalkayan', 'name_the_app')
    get_mock.return_value = MockUserResponse(json={'login': 'kalkayan', 'name': 'Kalkayan', 'access_token': '...'})
    fetch_token_mock.return_value = MockTokenResponse(json={'access_token': oauth_token}).json()
    csrf_token = get_csrf_token(client)
    generate_token_mock.return_value = csrf_token

    client.post('/oauth/github/login', data={'csrf_token': csrf_token})
    assert client.get(f'/oauth/github/callback?state={csrf_token}').status_code == 302

    with APP.app_context():
        assert [u.username for u in SESSION.query(User).all()] == ['Kalkayan']
    assert b'You have cast your vote.' in client.get('/app/elections/name_the_app').data
