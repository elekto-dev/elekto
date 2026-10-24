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
import re
import yaml
import markdown2 as markdown

from elekto import constants
from elekto.models.sql import Election

# to preserve the import consistency
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

# A bare value starting with @ (e.g. `slack: @alice`) is not valid YAML.
AT_VALUE = re.compile(r"^(\s*(?:-\s*)?[\w-]+:\s*)(@\S*)\s*$", re.MULTILINE)


def parse_yaml(yaml_path):
    """
    Loads a yaml from the system and return a dict

    Args:
        yaml_path (os.path): location of the yaml file

    Returns:
        dict: parsed yaml content in a dict
    """
    if os.path.exists(yaml_path) is False:
        return None

    return yaml.load(open(yaml_path, 'r').read(), Loader=Loader)


def parse_yaml_from_string(yaml_string):
    """
    Convert yaml string to yaml object (dict)

    Args:
        yaml_string (string): yaml string to be converted

    Returns:
        dict: parsed yaml dict object
    """
    return yaml.load(yaml_string, Loader=Loader)


def extract_candidate_info(md):
    """
    Extract candidates info from the given hybrid string

    Args:
        md (string): markdown string read from the candidate-xxxx.md file

    Returns:
        dict: candidate info as a dict
    """
    # TODO : check for wrong candidates strings
    info = md[md.find(
        constants.CAND_START_DEL) - 1 +
        len(constants.CAND_START_DEL):md.rfind(constants.CAND_END_DEL)]

    info = info.strip('-').strip('\n')
    info = AT_VALUE.sub(r"\1'\2'", info)

    return parse_yaml_from_string(info)


def extract_candidate_description(md):
    """
    Extract candidates description from the hybrid string

    Args:
        md (string): markdown string read from the candidate-xxxx.md file

    Returns:
        string: mardown description
    """
    desc = md.split(constants.CAND_END_DEL)[-1].strip('-').strip('\n')
    return desc


def sync(session, elections):
    """
    Sync db with the meta - add and delete old elections

    Args:
        session (object): database session
        elections (dict): list of all the elections from the meta

    Returns:
        string: returns a log
    """
    meta_elections = {e['key']: e for e in elections}
    log = "---------------------*=  Syncing started =*----------------------\n\n"

    # Delete election from the database that are not in the meta anymore
    try:
        elections = session.query(Election).all()
        for election in elections:
            if election.key not in meta_elections.keys():
                log += " - Deleted {} from the database.\n".format(election.key)
                session.delete(election)
    except:
        log += " x Error while querying to the database.\n"

    # Add the new added elections from the meta in the database.
    for e in meta_elections.keys():
        try:
            q = session.query(Election).filter_by(key=e).first()
            if q:
                q.name = meta_elections[e]['name']
            else:
                session.add(Election(key=e, name=meta_elections[e]['name']))
                # Add the entry to the log
                log += " + {} added in the database.\n".format(meta_elections[e]['name'])
        except:
            # Add error to the log
            log += " x while adding {} in the database, application ran in to error.\n"

    log += "\n\n---------------------*= Syncing completed *=--------------------"
    session.commit()

    return log

def parse_md(md, path=True):
    """
    Parse the mardown string
    """
    try:
        if path:
            md = open(md, 'r').read()
        return markdown.markdown(md, extras=['cuddled-lists'])
    except FileNotFoundError:
        return None
    except:
        return 'Markdown format not Correct'
