import pytest

from elekto.core.election import Election
from test.factories import ElectionFactory, BallotFactory


@pytest.fixture
def election_data() -> dict:
    return {
        'A': [3, 1, 2],
        'B': [2, 3, Election.NO_OPINION],
        'C': [1, 2, 3],
    }


@pytest.fixture
def candidates() -> list[dict]:
    return [
        {
            'name': 'Aaron Crickenberker',
            'ID': 'aaron'
        },
        {
            'name': 'Davanum Srinivas',
            'ID': 'dims'
        },
        {
            'name': 'Paris Pittman',
            'ID': 'paris'
        }
    ]


def test_election_from_csv(election_data: dict):
    election = Election.from_csv(election_data, no_winners=1)
    assert election.candidates == ['A', 'B', 'C']
    assert election.ballots == {
        0: [('A', 3), ('B', 2), ('C', 1)],
        1: [('A', 1), ('B', 3), ('C', 2)],
        2: [('A', 2), ('C', 3)]
    }


def test_election_from_csv_empty():
    election = Election.from_csv({}, no_winners=1)
    assert election.candidates == []
    assert election.ballots == {}
    assert election.no_winners == 1


def test_election_build(candidates):
    stored_election = ElectionFactory.create()

    # Simulate three different voters, each casting three ballots
    voters = ['x', 'y', 'z'] * 3  # Voters are usually UUID strings
    ranks = [1, 2, 2, 2, 1, 1, 3, 3, 3]

    # Generate three ballots for each candidate
    for candidate in candidates:
        BallotFactory.create(candidate=candidate['ID'], election=stored_election, voter=voters.pop(0), rank=ranks.pop(0))
        BallotFactory.create(candidate=candidate['ID'], election=stored_election, voter=voters.pop(0), rank=ranks.pop(0))
        BallotFactory.create(candidate=candidate['ID'], election=stored_election, voter=voters.pop(0), rank=ranks.pop(0))

    # Build the election and assert all is as expected
    election = Election.build(
        candidates=candidates,
        ballots=stored_election.ballots,
    )
    assert election.candidates == ['aaron', 'dims', 'paris']
    assert election.ballots == {
        'x': [('aaron', 1), ('dims', 2), ('paris', 3)],
        'y': [('aaron', 2), ('dims', 1), ('paris', 3)],
        'z': [('aaron', 2), ('dims', 1), ('paris', 3)]
    }


def test_election_build_ignores_max_rank_ballots(candidates):
    stored_election = ElectionFactory.create()
    BallotFactory.create_batch(10, rank=Election.MAX_RANK)

    election = Election.build(
        candidates=candidates,
        ballots=stored_election.ballots,
    )
    assert election.ballots == {}
