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

from typing import TYPE_CHECKING, List
from .types import BallotType
from elekto.core import schulze_d, schulze_p, schulze_rank

if TYPE_CHECKING:
    from models.sql import Ballot


class Election:
    NO_OPINION = 'No opinion'
    MAX_RANK = 100_000_000

    def __init__(self, candidates: List[str], ballots: BallotType, no_winners=1):
        self.candidates = candidates
        self.ballots = ballots
        self.no_winners = no_winners
        self.d = {}
        self.p = {}

    def schulze(self):
        self.d = schulze_d(self.candidates, self.ballots)
        self.p = schulze_p(self.candidates, self.d)
        self.ranks = schulze_rank(self.candidates, self.p, self.no_winners)

        return self

    @ staticmethod
    def build(candidates: list[dict], ballots: list['Ballot']):
        candidates = [c['ID'] for c in candidates]
        pref = {}

        for b in ballots:
            if b.voter not in pref.keys():
                pref[b.voter] = []
            if b.rank == Election.MAX_RANK:
                continue
            pref[b.voter].append((b.candidate, int(b.rank)))

        return Election(candidates, pref)

    @ staticmethod
    def from_csv(data: dict, no_winners: int):
        candidates = list(data.keys())
        ballots: BallotType = {}
        row_count = len(next(iter(data.values()), []))

        for v in range(row_count):
            ballots[v] = []
            for c in candidates:
                if data[c][v] == Election.NO_OPINION:
                    continue
                ballots[v].append((c, int(data[c][v])))

        return Election(candidates, ballots, no_winners)
