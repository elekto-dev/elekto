import os
from datetime import datetime
from unittest import mock

import pytest
import yaml
from freezegun import freeze_time

from elekto import APP
from elekto import constants
from elekto.models.meta import Election


@pytest.fixture
def election(metadir):
    return Election('name_the_app')


@mock.patch('elekto.models.meta.F.abort')
def test_election_bad_path(abort):
    APP.config['META']['PATH'] = '/fake/path'

    Election('my_cool_election')
    abort.assert_called_once_with(404)


@freeze_time('2025-05-05')
def test_election_build(election):
    assert election.election['name'] == 'Select The Name of the Application'
    assert election.election['organization'] == 'CommunityBridge'
    assert election.election['start_datetime'] == datetime(2023, 8, 2, 0, 0)
    assert election.election['end_datetime'] == datetime(2023, 8, 28, 23, 59)
    assert election.election['no_winners'] == 1
    assert election.election['allow_no_opinion'] == True
    assert election.election['delete_after'] == False
    assert election.election['show_candidate_fields'] is None
    assert election.election['election_officers'] == ['kalkayan', 'jberkus', '007vedant']
    assert election.election['eligibility'] == 'Contributors to the elections software project are eligible.'
    assert election.election['exception_description'] == 'If you\'re not a contributor and want to vote on this anyway, file for an exception.'
    assert election.election['exceptions_due'] == datetime(2023, 8, 19, 23, 59)

    assert election.election['status'] == constants.ELEC_STAT_COMPLETED
    assert election.election['key'] == 'name_the_app'
    assert election.election['description'] == ('<h1>Help Name the App!</h1>\n'
 '\n'
 '<p>The new voting and elections application is almost ready, which means '
 "it's time to choose a name for it!  The names in this election have been "
 'picked from a list of ideas supplied by Kubernetes Contributor Experience.  '
 'No more name ideas are being accepted.</p>\n')


def test_election_build_exception_due_date_default(election):
    """Test the exception's due date defaults to the election's start date."""
    del election.election['exception_due']
    election.build()
    assert election.election['exception_due'] == election.election['start_datetime']


@pytest.mark.parametrize(
    'mock_date,expected_status',
    [
        ('2023-08-01', constants.ELEC_STAT_UPCOMING),
        ('2023-08-29', constants.ELEC_STAT_COMPLETED),
        ('2023-08-27', constants.ELEC_STAT_RUNNING),
    ]
)
def test_election_status_upcoming(mock_date, expected_status, election):
    with freeze_time(mock_date):
        assert election.status() == expected_status


def test_voters_are_lowercased_strings(election):
    # YAML reads an all-digit GitHub login (e.g. 249043822) as an int
    with open(os.path.join(election.path, 'voters.yaml'), 'w') as f:
        f.write('eligible_voters:\n  - SergeyKanzhelev\n  - 249043822\n')

    assert election.voters()['eligible_voters'] == ['sergeykanzhelev', '249043822']


def test_election_officers_are_lowercased_strings(election):
    path = os.path.join(election.path, 'election.yaml')
    with open(path) as f:
        config = yaml.safe_load(f)
    config['election_officers'] = ['JBerkus', 12345]
    with open(path, 'w') as f:
        yaml.safe_dump(config, f)

    assert election.build()['election_officers'] == ['jberkus', '12345']


def test_show_fields_empty(election):
    election.election['show_candidate_fields'] = []
    assert election.showfields() == {}


def test_show_fields(election):
    election.election['show_candidate_fields'] = ['name']
    assert election.showfields() == {'name': ''}


def make_candidate(name: str, lang: str, identifier: str | None = None) -> dict:
    if identifier is None:
        identifier = name

    return {
        'name': name,
        'ID': identifier,
        'key': identifier,
        'info': [{
            'Language': lang
        }]
    }


@pytest.fixture
def candidates() -> list[dict]:
    return [
        make_candidate('delectus', 'Latin'),
        make_candidate('e6n', 'Leetspeak'),
        make_candidate('elekto', 'Esperanto'),
        make_candidate('Not CIVS', 'English', identifier='notcivs'),
        make_candidate('Ribemont', 'French', identifier='ribemont'),
    ]


def compare_candidates(candidates_a: list[dict], candidates_b: list[dict]) -> bool:
    return (
            all(candidate in candidates_b for candidate in candidates_a) and
            all(candidate in candidates_a for candidate in candidates_b)
    )


def test_candidates(election, candidates):
    assert compare_candidates(election.candidates(), candidates)


def test_candidates_orders_differ(election):
    """Assert that the candidates are ordered differently each time."""
    candidates_a = election.candidates()
    candidates_b = election.candidates()

    while candidates_b == candidates_a:
        # The chance of random.shuffle sorting in the same order multiple times in a row is slim, but never zero.
        # If this happens, repeat the population of candidates_b until random.shuffle came to a different result.
        candidates_b = election.candidates()

    assert candidates_a != candidates_b
    assert compare_candidates(candidates_a, candidates_b)


@mock.patch('elekto.models.meta.open')
def test_candidates_raises(open_mock, election):
    open_mock.side_effect = IOError

    with pytest.raises(Exception) as e:
        election.candidates()
        assert 'Invalid candidate file: candidate-delectus.md' in str(e)


@mock.patch('elekto.models.meta.F.abort')
def test_candidate_does_not_exist(abort, election):
    election.candidate('fake')
    abort.assert_called_once_with(404)


@mock.patch('elekto.models.meta.F.abort')
def test_candidate_not_a_file(abort, election, metadir):
    path = os.path.join(str(metadir), 'somedir')
    os.mkdir(path)

    os.path.exists(path)
    election.candidate('somedir')
    abort.assert_called_once_with(404)


def test_candidate(election):
    election.election['show_candidate_fields'] = ['Language']
    candidate = election.candidate('e6n')

    assert candidate['name'] == 'e6n'
    assert candidate['ID'] == 'e6n'
    assert candidate['key'] == 'e6n'
    assert candidate['info'] == [{'Language': 'Leetspeak'}]
    assert candidate['fields']['Language'] == 'Leetspeak'


def test_candidate_show_no_fields(election):
    election.election['show_candidate_fields'] = []
    candidate = election.candidate('e6n')

    assert candidate['name'] == 'e6n'
    assert candidate['ID'] == 'e6n'
    assert candidate['key'] == 'e6n'
    assert candidate['info'] == [{'Language': 'Leetspeak'}]
    assert candidate['fields'] == {}
