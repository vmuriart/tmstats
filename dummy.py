#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Terra Mystica Online stats summarizer"""

import json
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent
GAME_PATH = PACKAGE_DIR / 'games'


def format_dict(d):
    """Format dictionary to make it simple to read."""
    filename = 'blah.json'
    with open(filename, 'w+') as f:
        json.dump(d, f, separators=(',', ': '), indent=4, sort_keys=True)


game_file = GAME_PATH / '2017-12.json'
with open(game_file) as f:
    games = json.load(f)
format_dict(games)
