import re
from datetime import datetime
from unittest import mock

import pytest
from bs4 import BeautifulSoup
from flask.testing import FlaskClient
from freezegun import freeze_time
from pytest_mock import MockerFixture

from ..conftest import KDF_KEY_MOCK
from elekto.models import meta
from .utils import provision_session, vote, get_csrf_token, ENCRYPTED_MESSAGE, create_user
from elekto import APP, SESSION, constants
from elekto.models.sql import User, Election, Voter, Request


# -------------------------------------------------------------------------------------------------------------------- #
#                                                          /app                                                        #
# -------------------------------------------------------------------------------------------------------------------- #
def test_dashboard(client: FlaskClient):
    token="token"
    with APP.app_context():
        SESSION.add(User(username="carson",
                             name="Carson Weeks",
                             token=token,
                             token_expires_at=datetime.max))
        SESSION.commit()
    with client.session_transaction() as session:
        session[constants.AUTH_STATE] = token
    response = client.get("/app")
    assert response.status_code == 200
    assert b'Welcome! Carson Weeks' in response.data
    assert b'Sit back and Relax, there is not to do yet.' in response.data

def test_unauthenticated_dashboard(client: FlaskClient):
    with client.session_transaction() as session:
        session[constants.AUTH_STATE] = None
    response = client.get("/app")
    assert response.status_code == 302

def test_elections_running_dashboard(client: FlaskClient, mocker: MockerFixture):
    mocker.patch("elekto.meta.Election.where", return_value=[{"name": "Demo Election", 
                                                              "organization": "kubernetes", 
                                                              "start_datetime": datetime.min, 
                                                              "end_datetime": datetime.max}])
    token="token"
    with APP.app_context():
        SESSION.add(User(username="carson",
                             name="Carson Weeks",
                             token=token,
                             token_expires_at=datetime.max))
        SESSION.commit()
    with client.session_transaction() as session:
        session[constants.AUTH_STATE] = token
    response = client.get("/app")
    assert response.status_code == 200
    assert b"Demo Election" in response.data 
    assert not b"Sit back and Relax, there is not to do yet." in response.data


# -------------------------------------------------------------------------------------------------------------------- #
#                                                     /app/elections                                                   #
# -------------------------------------------------------------------------------------------------------------------- #
def test_list_elections(client: FlaskClient, load_metadir):
    """
    Be aware /app/elections shows the Elections from the metadata, not as stored in the database.
    """
    provision_session(client, token='...')
    elections = meta.Election.all()

    # Sort the elections in the desired way, so we implicitly can check if the frontend orders the elections correctly.
    elections.sort(key=lambda e: e["start_datetime"], reverse=True)

    assert len(elections) == 3

    response = client.get('/app/elections')
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, 'html.parser')
    subtitle_text = soup.find('p', attrs={'class': 'banner-subtitle space-lr'}).text.strip()
    assert 'Index for all the elections contained by the repository.' in subtitle_text

    links = soup.find_all('a', attrs={'class': 'color-primary'})
    assert len(links) == 3

    for election, link in zip(elections, links):
        key = election['key']
        href = f'/app/elections/{key}'
        assert link['href'] == href
        assert link.text.strip() == election['name']


@mock.patch("elekto.controllers.elections.meta.Election.all")
def test_list_elections_empty(all_mock, client: FlaskClient):
    all_mock.return_value = []  # Mock the meta directory being empty.
    provision_session(client, token='...')

    response = client.get('/app/elections')
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, 'html.parser')
    title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert 'No Elections found' in title_text


@pytest.mark.parametrize(
    'status,n_elections',
    [
        (constants.ELEC_STAT_COMPLETED, 3),
        (constants.ELEC_STAT_RUNNING, 0),
        (constants.ELEC_STAT_UPCOMING, 0),
    ]
)
def test_list_elections_with_status(status: str, n_elections: int, client: FlaskClient, load_metadir):
    provision_session(client, token='...')

    response = client.get(f'/app/elections?status={status}')
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, 'html.parser')
    links = soup.find_all('a', attrs={'href': re.compile('^/app/elections/')})
    assert len(links) == n_elections

    breadcrumb_text = soup.find('span', attrs={'class': f'badge badge-{status}'}).text.strip()
    assert breadcrumb_text == status


# -------------------------------------------------------------------------------------------------------------------- #
#                                              /app/elections/<eid>                                                    #
#                                                                                                                      #
#                                                                                                                      #
# When rendering an election's detail page, the following factors are at play:                                         #
# - The election must exist.                                                                                           #
# - Candidates are generated by a for-loop. No special message is shown if the number of candidates is zero.           #
#   - The rendering order of candidates can vary.                                                                      #
# - If the election is running and the user is in the eligible voters, some additional content is shown. This content  #
#   is different if the user has or hasn't voted.                                                                      #
# - If the election has been completed and results are available, the 'Results' link is shown.                         #
# - If the election has been completed and results are not available, a disabled button is shown.                      #
# - If the user is one of the election's officers, an 'Admin' button is shown.                                         #
# -------------------------------------------------------------------------------------------------------------------- #
def test_election_detail_not_found(client: FlaskClient):
    provision_session(client, token='...')
    response = client.get(f'/app/elections/12345')
    assert response.status_code == 200  # Status code is HTTP200, despite the message being a Server Error.
    soup = BeautifulSoup(response.data, 'html.parser')
    title_text = soup.find('title').text.strip()
    assert title_text == '500 - Server Error | Elekto'


@pytest.mark.parametrize(
    'election_key,has_results,n_candidates',
    [
        ('name_the_app', True, 5),
        ('2021---TOC', False, 2),
    ]
)
def test_election_detail_completed(election_key: str, has_results: bool, n_candidates: int, client: FlaskClient, load_metadir):
    """An election that has been completed. User is not eligible for any of these elections."""
    provision_session(client, token='...')
    election = meta.Election(key=election_key)

    response = client.get(f'/app/elections/{election_key}')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert title_text == election.election['name']

    subtitle_text = soup.find('p', attrs={'class': 'banner-subtitle space-lr mb-2rem'}).text.strip()
    assert subtitle_text == election.election['organization'] + '\n|\ncompleted\n|\nNot eligible'

    description_html = soup.find('div', attrs={'class': 'description space-lr pb-0'})
    description_title = description_html.find('h1').text.strip()
    description_p = description_html.find('p').text.strip()

    assert description_title in election.election['description']
    # Only check the first couple of characters to prevent having to deal with rendering differences in the HTML.
    assert description_p[0:10] in election.election['description']

    links = soup.find_all('a', text='profile', attrs={'href': re.compile(f'^/app/elections/{election_key}/candidates')})
    assert len(links) == n_candidates

    if has_results:
        assert soup.find('a', text='Results', attrs={'class': 'btn btn-dark', 'disabled': False}) is not None
    else:
        assert soup.find('button', text='Results (not published)', attrs={'class': 'btn btn-dark', 'disabled': True}) is not None


@freeze_time('2023-08-04')
@pytest.mark.parametrize(
    'has_voted',
    [True, False],
)
def test_election_detail_running_voter_eligible(has_voted: bool, client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')

    if has_voted:
        # Create a Voter record for the authenticated user to simulate the user has voted.
        vote('kalkayan', 'name_the_app')

    response = client.get('/app/elections/name_the_app')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    disclaimer_text = soup.find('p', attrs={'class': 'disclaimer space-lr mt-1rem'}).text.strip()

    if has_voted:
        assert 'You have cast your vote.' in disclaimer_text
    else:
        assert 'You have not yet voted in this election.' in disclaimer_text


@freeze_time('2023-08-04')
def test_election_detail_running_voter_not_eligible(client: FlaskClient, load_metadir):
    provision_session(client, token='...')

    response = client.get('/app/elections/name_the_app')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    disclaimer_text = soup.find('p', attrs={'class': 'disclaimer space-lr mt-1rem'}).text.strip()
    assert 'If you wish to participate in the' in disclaimer_text


@freeze_time('2023-08-04')
def test_election_detail_running_user_is_admin(client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')
    response = client.get('/app/elections/name_the_app')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    assert soup.find('a', text='Admin', attrs={'class': 'btn btn-dark', 'href': '/app/elections/name_the_app/admin/'}) is not None


@pytest.mark.parametrize(
    'frozen_date,expected',
    [
        ('2023-08-01', 'Voting starts at 2023-08-02 00:00:00 UTC and ends at 2023-08-28 23:59:00 UTC.'),
        ('2023-08-04', 'Voting started at 2023-08-02 00:00:00 UTC and is open until 2023-08-28 23:59:00 UTC.'),
        ('2023-09-01', 'Voting started at 2023-08-02 00:00:00 UTC and ended at 2023-08-28 23:59:00 UTC.'),
    ],
    ids=['upcoming', 'running', 'completed'],
)
def test_election_detail_voting_period(frozen_date: str, expected: str, client: FlaskClient, load_metadir):
    """The voting period sentence uses the tense that matches the election status."""
    with freeze_time(frozen_date):
        provision_session(client, token='...', username='kalkayan')
        response = client.get('/app/elections/name_the_app')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    disclaimer_text = ' '.join(soup.find('p', attrs={'class': 'disclaimer space-lr mt-1rem'}).text.split())
    assert expected in disclaimer_text


# -------------------------------------------------------------------------------------------------------------------- #
#                                      /app/elections/<eid>/candidates/<cid>                                           #
# -------------------------------------------------------------------------------------------------------------------- #
def test_elections_candidate(client: FlaskClient, load_metadir):
    provision_session(client, token='...')

    response = client.get('/app/elections/2021---GB/candidates/dims')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert title_text == 'Davanum Srinivas'

    expected_subtitles = [
        'dims | Running for Select our 2021 General Board Rep',
        'employer | VMware',
    ]
    subtitles = soup.find_all('p', attrs={'class': 'banner-subtitle space-lr'})

    for expected_subtitle, subtitle in zip(expected_subtitles, subtitles):
        assert subtitle.text.strip() == expected_subtitle

    description_text = soup.find('div', attrs={'class': 'description space-lr'}).text.strip()
    assert description_text == 'Davanum Srinivas is a current member of the Steering Committee, and has been a member of the CNCF TOC.'


# -------------------------------------------------------------------------------------------------------------------- #
#                                            /app/elections/<eid>/vote                                                 #
# -------------------------------------------------------------------------------------------------------------------- #
def test_elections_voting_thankyou_redirect(client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')

    # Create a Voter record for the authenticated user to simulate the user has voted.
    vote('kalkayan', 'name_the_app')

    response = client.get('/app/elections/name_the_app/vote')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert title_text == 'You have already voted'

    message_text = soup.find('p', attrs={'class': 'space-lr ml-5px'}).text.strip()
    message_text = re.sub(' +', ' ', message_text)
    assert message_text == 'To re-cast your vote, please visit the election page.'


@mock.patch('elekto.controllers.elections.encrypt')
def test_elections_voting_post(encrypt_mock, client: FlaskClient, load_metadir):
    encrypt_mock.return_value = ENCRYPTED_MESSAGE
    provision_session(client, token='...', username='kalkayan')

    ballot_votes = {
        'candidate@delectus': 4,
        'candidate@e6n': 3,
        'candidate@elekto': 1,
        'candidate@notcivs': 2,
        'candidate@ribemont': 100000000,
    }

    response = client.post('/app/elections/name_the_app/vote', data={
        'csrf_token': get_csrf_token(client, path='/app/elections/name_the_app/vote'),
        'password': '<PASSWORD>',
        **ballot_votes,
    })
    assert response.status_code == 302
    assert response.headers['Location'] == '/app/elections/name_the_app/confirmation'

    encrypt_mock.assert_called_once_with(mock.ANY, '<PASSWORD>', mock.ANY)

    # Check if all expected data was written to the database.
    with APP.app_context():
        user_id = SESSION.query(User).filter_by(username='kalkayan').one().id
        voter = SESSION.query(Voter).filter_by(user_id=user_id).one()
        assert voter.ballot_id == ENCRYPTED_MESSAGE

        ballots = SESSION.query(Election).filter_by(key='name_the_app').one().ballots

    assert len(ballots) == 5

    for i, k in enumerate(ballot_votes):
        form_data_rank = ballot_votes[k]
        stored_rank = ballots[i].rank
        assert form_data_rank == stored_rank


def test_elections_voting_get(client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')
    election = meta.Election(key='name_the_app').election
    candidates = meta.Election(key='name_the_app').candidates()

    response = client.get('/app/elections/name_the_app/vote')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert title_text == election['name']

    subtitle_text = soup.find('p', attrs={'class': 'banner-subtitle space-lr mb-2rem'}).text.strip()
    assert subtitle_text == election['organization'] + '\n|\n' + election['status']

    for candidate in candidates:
        key = candidate['key']
        div = soup.find('div', id=f'div-{key}')
        select = div.find('select', attrs={'name': f'candidate@{key}'})

        options = select.find_all('option')
        assert len(options) == len(candidates) + 1


# -------------------------------------------------------------------------------------------------------------------- #
#                                          /app/elections/<eid>/vote/view                                              #
# -------------------------------------------------------------------------------------------------------------------- #
@mock.patch('elekto.core.encryption.pwhash.argon2i.kdf', return_value=KDF_KEY_MOCK)
def test_elections_view(kdf_mock, client: FlaskClient, load_metadir):  # Slow
    provision_session(client, token='...', username='kalkayan')

    ballot_votes = {
        'candidate@delectus': 4,
        'candidate@e6n': 3,
        'candidate@elekto': 1,
        'candidate@notcivs': 2,
        'candidate@ribemont': 100000000,
    }

    csrf_token = get_csrf_token(client, path='/app/elections/name_the_app/vote')
    response = client.post('/app/elections/name_the_app/vote', data={
        'csrf_token': csrf_token,
        'password': '<PASSWORD>',
        **ballot_votes,
    })
    assert response.status_code == 302

    # Once the voting has been done, navigate to the page to view the user's cast votes.
    response = client.post('/app/elections/name_the_app/vote/view', data={
        'csrf_token': csrf_token,
        'password': '<PASSWORD>',
    })
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    ballot_divs = soup.find_all('div', attrs={'class': 'boxed-hover row'})
    assert len(ballot_divs) == len(ballot_votes)

    for k, rank in ballot_votes.items():
        key = k.split('@')[-1]
        h6s = ballot_divs.pop(0).find_all('h6')
        assert len(h6s) == 2
        assert h6s[0].text.strip() == key
        assert h6s[1].text.strip() == str(rank)


@mock.patch('elekto.controllers.elections.decrypt')
def test_elections_view_error(decrypt_mock, client: FlaskClient, load_metadir):
    decrypt_mock.side_effect = Exception
    provision_session(client, token='...', username='kalkayan')

    response = client.post('/app/elections/name_the_app/vote/view', data={
        'csrf_token': get_csrf_token(client, path='/app/elections/name_the_app/vote'),
        'password': '<PASSWORD>',
    })
    assert response.status_code == 302
    assert response.headers['Location'] == '/app/elections/name_the_app'


# -------------------------------------------------------------------------------------------------------------------- #
#                                          /app/elections/<eid>/vote/edit                                              #
# -------------------------------------------------------------------------------------------------------------------- #
@mock.patch('elekto.core.encryption.pwhash.argon2i.kdf', return_value=KDF_KEY_MOCK)
def test_elections_edit(kdf_mock, client: FlaskClient, load_metadir):  # Slow
    provision_session(client, token='...', username='kalkayan')

    ballot_votes = {
        'candidate@delectus': 4,
        'candidate@e6n': 3,
        'candidate@elekto': 1,
        'candidate@notcivs': 2,
        'candidate@ribemont': 100000000,
    }

    csrf_token = get_csrf_token(client, path='/app/elections/name_the_app/vote')
    response = client.post('/app/elections/name_the_app/vote', data={
        'csrf_token': csrf_token,
        'password': '<PASSWORD>',
        **ballot_votes,
    })
    assert response.status_code == 302

    with APP.app_context():
        user_id = SESSION.query(User).filter_by(username='kalkayan').one().id
        assert SESSION.query(Voter).filter_by(user_id=user_id).count() == 1
        assert len(SESSION.query(Election).filter_by(key='name_the_app').one().ballots) == 5

    # Once the voting has been done, navigate to the page to delete the user's vote/ballots.
    response = client.post('/app/elections/name_the_app/vote/edit', data={
        'csrf_token': csrf_token,
        'password': '<PASSWORD>',
    })
    assert response.status_code == 302
    assert response.headers['Location'] == '/app/elections/name_the_app'

    with APP.app_context():
        user_id = SESSION.query(User).filter_by(username='kalkayan').one().id
        assert SESSION.query(Voter).filter_by(user_id=user_id).count() == 0
        assert SESSION.query(Election).filter_by(key='name_the_app').one().ballots == []


@mock.patch('elekto.controllers.elections.decrypt')
def test_elections_edit_error(decrypt_mock, client: FlaskClient, load_metadir):
    decrypt_mock.side_effect = Exception
    provision_session(client, token='...', username='kalkayan')

    response = client.post('/app/elections/name_the_app/vote/edit', data={
        'csrf_token': get_csrf_token(client, path='/app/elections/name_the_app/vote'),
        'password': '<PASSWORD>',
    })
    assert response.status_code == 302
    assert response.headers['Location'] == '/app/elections/name_the_app'


# -------------------------------------------------------------------------------------------------------------------- #
#                                         /app/elections/<eid>/confirmation                                            #
# -------------------------------------------------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    'has_voted',
    [True, False]
)
def test_elections_confirmation_page(has_voted: bool, client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')

    if has_voted:
        vote('kalkayan', 'name_the_app')

    response = client.get('/app/elections/name_the_app/confirmation')

    if has_voted:
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, 'html.parser')
        title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
        assert title_text == 'Thank you for voting in Select The Name of the Application'
    else:
        assert response.status_code == 302
        assert response.headers['Location'] == '/app/elections/name_the_app'


# -------------------------------------------------------------------------------------------------------------------- #
#                                           /app/elections/<eid>/results/                                              #
# -------------------------------------------------------------------------------------------------------------------- #
def test_elections_results(client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')
    response = client.get('/app/elections/name_the_app/results/')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')
    desc_text = soup.find('div', attrs={'class': 'description'}).text.strip()
    assert 'This election ran from' in desc_text


# -------------------------------------------------------------------------------------------------------------------- #
#                                          /app/elections/<eid>/exception                                              #
# -------------------------------------------------------------------------------------------------------------------- #
@freeze_time('2023-08-12')
def test_elections_exception_user_already_has_exception(client: FlaskClient, load_metadir):
    provision_session(client, token='...')

    with APP.app_context():
        user_id = SESSION.query(User).filter_by(username='carson').one().id
        election = SESSION.query(Election).filter_by(key='2021---GB').first()
        req = Request(
            user_id=user_id,
            name='...',
            email='...',
            chat='...',
            description='...',
            comments='...',
        )
        election.requests.append(req)
        SESSION.commit()

    response = client.get('/app/elections/2021---GB/exception')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')
    title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert title_text == 'You have already requested an exception.'


@freeze_time('2023-08-12')
def test_elections_exception_post(client: FlaskClient, load_metadir):
    provision_session(client, token='...')

    with APP.app_context():
        user_id = SESSION.query(User).filter_by(username='carson').one().id
        req = SESSION.query(Request).filter_by(user_id=user_id).first()
        assert req is None

    response = client.post('/app/elections/2021---GB/exception', data={
        'csrf_token': get_csrf_token(client, path='/app/elections/2021---GB/exception'),
        'name': 'Carson Weeks',
        'email': 'carson@example.com',
        'chat': 'carson',
        'description': 'yyy',
        'comments': 'zzz',
    })
    assert response.status_code == 302
    assert response.headers['Location'] == '/app/elections/2021---GB'

    with APP.app_context():
        req = SESSION.query(Request).filter_by(user_id=user_id).first()
        assert req.user_id == user_id
        assert req.name == 'Carson Weeks'
        assert req.email == 'carson@example.com'
        assert req.chat == 'carson'
        assert req.description == 'yyy'
        assert req.comments == 'zzz'


@freeze_time('2023-08-12')
def test_elections_exception_get(client: FlaskClient, load_metadir):
    provision_session(client, token='...')

    response = client.get('/app/elections/2021---GB/exception')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')
    title_text = soup.find('h3', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert title_text == 'Voter Exception form for Select our 2021 General Board Rep'
    assert soup.find('form') is not None


# -------------------------------------------------------------------------------------------------------------------- #
#                                            /app/elections/<eid>/admin/                                               #
# -------------------------------------------------------------------------------------------------------------------- #
def test_elections_admin(client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')

    response = client.get('/app/elections/2021---GB/admin/')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert title_text == 'Election Officer\'s Dashboard'


# -------------------------------------------------------------------------------------------------------------------- #
#                                      /app/elections/<eid>/admin/exception/<rid>                                      #
# -------------------------------------------------------------------------------------------------------------------- #
@freeze_time('2023-08-12')
def test_elections_admin_review_cycle(client: FlaskClient, load_metadir):
    """Test both reading and toggling the request's status."""
    provision_session(client, token='...', username='kalkayan')

    # Test a non-existent Request ID is accepted and causes an error.
    response = client.get('/app/elections/2021---GB/admin/exception/0')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')
    title_text = soup.find('title').text.strip()
    assert title_text == '500 - Server Error | Elekto'

    # Test reading an existing exception request.
    create_user('...', username='carson')

    with APP.app_context():
        user_id = SESSION.query(User).filter_by(username='carson').one().id
        election = SESSION.query(Election).filter_by(key='2021---GB').first()
        req = Request(
            user_id=user_id,
            name='...',
            email='...',
            chat='...',
            description='...',
            comments='...',
        )
        election.requests.append(req)
        SESSION.commit()
        req_id = req.id

    response = client.get(f'/app/elections/2021---GB/admin/exception/{req_id}')
    assert response.status_code == 200
    csrf_token = response.data.decode('utf8').split('csrf_token" value="')[1].split('"')[0]
    soup = BeautifulSoup(response.data, 'html.parser')
    assert soup.find('span', attrs={'class': 'badge badge-upcoming'}) is not None

    # Set the status to 'completed'
    response = client.post(f'/app/elections/2021---GB/admin/exception/{req_id}', data={'csrf_token': csrf_token})
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')
    assert soup.find('span', attrs={'class': 'badge badge-completed'}) is not None

    # Reset the status to 'upcoming'
    response = client.post(f'/app/elections/2021---GB/admin/exception/{req_id}', data={'csrf_token': csrf_token})
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')
    assert soup.find('span', attrs={'class': 'badge badge-upcoming'}) is not None


# -------------------------------------------------------------------------------------------------------------------- #
#                                          /app/elections/<eid>/admin/results                                          #
# -------------------------------------------------------------------------------------------------------------------- #
def test_elections_admin_results(client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')

    response = client.get('/app/elections/2021---GB/admin/results')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')
    h4_title = soup.find('h4', attrs={'class': 'title'}).text.strip().replace(' ', '').replace('\n\n', ' ')
    # Review the candidates piece by piece as there is no fixed order in rendering.
    assert all(part in h4_title.split() for part in '🎉 dims paris aaron'.split())


# -------------------------------------------------------------------------------------------------------------------- #
#                                          /app/elections/<eid>/admin/download                                         #
# -------------------------------------------------------------------------------------------------------------------- #
def test_elections_admin_download(client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')

    response = client.get('/app/elections/2021---GB/admin/download')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/csv; charset=utf-8'
    assert response.headers['Content-Disposition'] == 'attachment; filename=ballots.csv'
