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

import os
import random
import subprocess
import flask as F

from datetime import datetime

from elekto import APP, constants
from elekto.models import utils


class Meta:
    """
    Meta is the base class for all the yaml files based backend, the class is
    responsible for syncing application with meta repository (sidecar or local)
    and provides the utils to read data (YAML) files.
    """

    def __init__(self, config):
        self.META = os.path.abspath(config['PATH'])
        self.ELECDIR = config['ELECDIR']
        self.REMOTE = config['REMOTE']
        self.BRANCH = config['BRANCH']
        self.SECRET = config['SECRET']
        self.git = '/usr/bin/git'

    def clone(self):
        subprocess.run([self.git, 'clone', '-b', self.BRANCH, '--', self.REMOTE, self.META], check=True)

    def pull(self):
        subprocess.run([self.git, '--git-dir', '{}/.git'.format(self.META),'--work-tree', self.META, 'pull', '--ff-only', 'origin', self.BRANCH], check=True)


class Election(Meta):
    DES = 'election_desc.md'
    RES = 'results.md'
    YML = 'election.yaml'
    VOT = 'voters.yaml'

    def __init__(self, key):
        Meta.__init__(self, APP.config['META'])
        self.store = os.path.join(self.META, self.ELECDIR)
        self.path = os.path.join(self.store, key.replace('---','/'))
        self.key = key
        self.election = {}

        if not os.path.exists(self.path):
            F.abort(404)
        else:
            self.build()

    @staticmethod
    def all():
        """
        Get all elections in the repository

        Returns:
            list: list of all the elections
        """
        meta = Meta(APP.config['META'])
        path = os.path.join(meta.META, meta.ELECDIR)
        keys = Election.listelecdirs(path)

        return [Election(k).get() for k in keys]

    @staticmethod
    def where(key, value):
        return [r for r in Election.all() if r[key] == value]

    @staticmethod
    def listelecdirs(path):
        """Return the set of election directories"""
        elecdirs = []
        for root, dirs, files in os.walk(path, topdown=True):
           for name in dirs:
               if os.path.exists(os.path.join(root, name, Election.YML)):
                   """append each election directory to the list of directories
                   and make nested dirs url-safe"""
                   curdir = os.path.relpath(os.path.join(root, name),path)
                   safedir = curdir.replace('/','---')
                   elecdirs.append(safedir)

        return elecdirs

    def get(self):
        if not os.path.exists(self.path) or not os.path.isdir(self.path):
            return F.abort(404)
        return self.build()

    def build(self):
        self.election = utils.parse_yaml(os.path.join(self.path, Election.YML))
        self.election['status'] = self.status()
        self.election['key'] = self.key
        self.election['description'] = self.description()
        self.election['results'] = self.results()
        # GitHub logins are case-insensitive; compare against lowercased lists.
        # See: https://github.com/elekto-dev/elekto/issues/84
        self.election['election_officers'] = [
            str(o).lower() for o in self.election.get('election_officers') or []]

        if 'exception_due' not in self.election.keys():
            self.election['exception_due'] = self.election['start_datetime']
        return self.election

    def status(self):
        start = self.election['start_datetime']
        end = self.election['end_datetime']
        now = datetime.now()

        if now < start:
            return constants.ELEC_STAT_UPCOMING
        elif end < now:
            return constants.ELEC_STAT_COMPLETED
        else:
            return constants.ELEC_STAT_RUNNING

    def description(self):
        return utils.parse_md(os.path.join(self.path, Election.DES))

    def results(self):
        return utils.parse_md(os.path.join(self.path, Election.RES))

    def voters(self):
        voters = utils.parse_yaml(os.path.join(self.path, Election.VOT))
        if voters:
            voters['eligible_voters'] = [
                str(v).lower() for v in voters.get('eligible_voters') or []]
        return voters
        
    def showfields(self):
        # FIXME: show_candidate_fields could be None (as is the case in the name_the_app example meta), leading to an
        #  error if showfields() is called. See: https://github.com/elekto-dev/elekto/issues/98
        return dict.fromkeys(self.election['show_candidate_fields'], '')

    def candidates(self):
        """
        Build candidates and a list of candidates in random order
        """
        files = [k for k in os.listdir(self.path) if k.startswith('candidate')]
        candidates = []
        for f in files:
            md = open(os.path.join(self.path, f)).read()
            try:
                c = utils.extract_candidate_info(md)
                c['key'] = c['ID']
                candidates.append(c)
            except:
                raise Exception("Invalid candidate file : {}".format(f))

        # As per the specifications the candidates must!! be in random order
        random.shuffle(candidates)

        return candidates

    def candidate(self, cid):
        path = os.path.join(self.path, 'candidate-{}.md'.format(cid))
        if not os.path.exists(path) or not os.path.isfile(path):
            return F.abort(404)

        md = open(path).read()
        candidate = utils.extract_candidate_info(md)
        candidate['key'] = cid
        candidate['description'] = utils.parse_md(
            utils.extract_candidate_description(md), False)
        # return only the candidate optional fields that are listed in show_candidate_fields
        # unfilled fields are returned as '' so the label still displays
        candidate['fields'] = self.showfields()
        for info in candidate['info']:
            field = list(info.keys())[0]
            if field in candidate['fields']:
                candidate['fields'][field] = info[field]
        return candidate
