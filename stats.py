#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Terra Mystica Online stats summarizer"""

import copy
import gzip
import json
import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np

from welford import Welford

PACKAGE_DIR = Path(__file__).parent
GAME_PATH = PACKAGE_DIR / 'games'
GAME_FILENAME = PACKAGE_DIR / 'games.pickle.gz'

MAPDICT = {
    '126fe960806d587c78546b30f1a90853b1ada468': 'a',  # Original
    '95a66999127893f5925a5f591d54f8bcb9a670e6': 'b',  # Fire & Ice, Side 1
    'be8f6ebf549404d015547152d5f2a1906ae8dd90': 'c',  # Fire & Ice, Side 2
    'b109f78907d2cbd5699ced16572be46043558e41': 'd',  # testing map game=nan0002
    '735b073fd7161268bb2796c1275abda92acd8b1a': 'e',  # testing map game=gareth44,
    # expm28
    '30b6ded823e53670624981abdb2c5b8568a44091': 'f',  # testing map game=gareth45
    'b8a54c8e8ea3f50867297da35be5c01b9a6791d2': 'g',  # Loon Lakes v1.3
    'c07f36f9e050992d2daf6d44af2bc51dca719c46': 'h',  # Loon Lakes v1.5
    'fdb13a13cd48b7a3c3525f27e4628ff6905aa5b1': 'i',  # Loon Lakes v1.6
    '224736500d20520f195970eb0fd4c41df040c08c': 'j',  # Fjords v1.0
}

BLACKLIST = [
    'nan0002',  # testing map b109f78907d2cbd5699ced16572be46043558e41
    'gareth44',  # testing map 735b073fd7161268bb2796c1275abda92acd8b1a
    'expm28',  # testing map 735b073fd7161268bb2796c1275abda92acd8b1a
    'gareth45',  # testing map 30b6ded823e53670624981abdb2c5b8568a44091
    'Bgg50',  # bridged more than 3
    'DaveMattDouble2',  # bridged more than 3
    'wayne',  # invalid score tiles
    'JogaGREat5',  # CM double pass bug
    'JogaGreat4',  # CM double pass bug
    'PenisEnvy1',  # CM double pass bug
    'JG9',  # CM double pass bug
    'sky05',  # CM double pass bug
    'JG10',  # CM double pass bug
    'Terra4m',  # CM double pass bug
    'Tools001',  # CM double pass bug
    'DvMvRvB4',  # CM double pass bug
    'marcelp24',  # CM double pass bug
    '5',  # S1(SPD>>2) at Round5
    '0627puyo',  # early PBF
    '10',  # early PBF
    '17',  # early PBF
    '19',  # early PBF
    '20',  # early PBF
    '23',  # early PBF
    '24',  # early PBF
    '26',  # early PBF
    '27',  # early PBF
    # '5', # early PBF
    '8',  # early PBF
    '9',  # early PBF
    'BlaGame11',  # early PBF
    'BlaGame8',  # early PBF
    'IBGPBF5',  # early PBF
    'Noerrorpls',  # early PBF
    'gamecepet',  # early PBF
    'gareth2',  # early PBF
    'nyobagame',  # early PBF
    'pbc1',  # early PBF
    'pbc2',  # early PBF
    'pbc3',  # early PBF
    'skelly1',  # early PBF
    'skelly1a',  # early PBF
    'skelly1b',  # early PBF
    'skelly1c',  # early PBF
    'skelly1d',  # early PBF
    'skelly1e',  # early PBF
    'skelly1f',  # early PBF
    'skelly1',  # early PBF
    'verandi1',  # early PBF
    'verandi2',  # early PBF
]

FDICT = {
    'acolytes': 'a',
    'alchemists': 'b',
    'auren': 'c',
    'chaosmagicians': 'd',
    'cultists': 'e',
    'darklings': 'f',
    'dragonlords': 'g',
    'dwarves': 'h',
    'engineers': 'i',
    'fakirs': 'j',
    'giants': 'k',
    'halflings': 'l',
    'icemaidens': 'm',
    'mermaids': 'n',
    'nomads': 'o',
    'riverwalkers': 'p',
    'shapeshifters': 'q',
    'swarmlings': 'r',
    'witches': 's',
    'yetis': 't'
}


class FactionStat(object):
    """faction status in game result"""

    def __init__(self, game, name):
        self.game_id = game['game']
        self.name = name
        self.globals = game['events']['global']
        fac_events = game['events']['faction'][name]
        self.user = game['factions2'][name]
        self.score = fac_events['vp']['round']['all'] + 20
        self.numplayers = game['player_count']
        avgscore = float(game['events']['faction']['all']['vp']['round']['all']) / self.numplayers + 20
        self.margin = self.score - avgscore
        self.map_type = MAPDICT[game['base_map']]
        self.all_bons = self.parse_picked_bonus(game['events']['faction']['all'])

        self.parse_events(fac_events)
        self.orders = self.parse_order(fac_events)
        self.options = {}
        self.score_tiles = {}
        self.parse_global(game['events']['global'])
        self.parse_players(game['factions'])
        self.num_nofactions = game['player_count'] - game['events']['global']['faction-count']['round']['all']
        self.rank_in_game = 1
        self.period = game['last_update'][2:4] + hex(int(game['last_update'][5:7]))[2]

    def parse_event(self, events, event_id):
        if event_id not in events:
            return np.zeros(7)
        r = defaultdict(int, events[event_id]['round'])
        return np.array((r['0'], r['1'], r['2'], r['3'], r['4'], r['5'], r['6']))

    def parse_favor(self, events, num):
        key = f'favor:FAV{num}'
        if key not in events:
            return 9
        r = list(events[key]['round'].keys())
        r.remove('all')
        return int(r[0])

    def parse_favors(self, events):
        return np.array([self.parse_favor(events, i) for i in range(1, 13)])

    def parse_town(self, events, num):
        key = 'town:TW' + str(num)
        if key not in events:
            return 0
        r = list(events[key]['round'].keys())
        r.remove('all')
        return int(r[0])

    def parse_towns(self, events):
        np.array([self.parse_town(events, i) for i in range(1, 9)])

    def parse_bonus(self, events):
        return tuple(np.where(np.array([self.parse_event(events, 'pass:BON' + str(i)) for i in range(1, 11)]).transpose() == 1)[1])

    def parse_picked_bonus(self, events):
        data = np.zeros(11)
        for i in range(1, 11):
            data[i] = max(self.parse_event(events, 'pass:BON' + str(i)))
        return data

    def parse_allbonus(self, events, num):
        key = 'pass:BON' + str(num)
        if key not in events:
            return np.zeros(7)
        r = defaultdict(int, events[key]['round'])
        return np.array((r['0'], r['1'], r['2'], r['3'], r['4'], r['5'], r['6']))

    def parse_order(self, events):
        result = {}
        for num in range(1, 8):
            key = 'order:' + str(num)
            if key not in events:
                continue
            r = list(events[key]['round'].keys())
            r.remove('all')
            for k in r:
                result[str(k)] = num
        return result

    def parse_leech(self, events):
        pw = []
        for k in self.parse_event(events, 'leech:pw'):
            pw.append(min(4, int(k / 4)))
        return pw

    def parse_events(self, events):
        D_evt = self.parse_event(events, 'build:D')
        TP_evt = self.parse_event(events, 'upgrade:TP')
        TE_evt = self.parse_event(events, 'upgrade:TE')
        SA_evt = self.parse_event(events, 'upgrade:SA')
        SH_evt = self.parse_event(events, 'upgrade:SH')

        # upgrade path...
        D = np.cumsum(D_evt - TP_evt)
        TP = np.cumsum(TP_evt - TE_evt - SH_evt)
        TE = np.cumsum(TE_evt - SA_evt)
        SA = np.cumsum(SA_evt)
        SH = np.cumsum(SH_evt)

        # each building, each round
        self.builts = np.array((D, TP, TE, SA, SH), dtype=int)

        # each FAV, which round (if any)
        self.favs = self.parse_favors(events)

        # each TW, which round (if any)
        self.towns = self.parse_towns(events)

        # each round, which BON
        self.bonus = self.parse_bonus(events)

        self.leech_pw = self.parse_leech(events)

    def parse_global(self, global_):
        for k, v in global_.items():
            if 'option-fire-and-ice-final-scoring' in k:
                continue

            if 'option-' in k:
                opt_key = k.replace('option-', '')
                if opt_key.startswith('fire-and-ice-factions/variable_v'):
                    self.options['fire-and-ice-factions/variable'] = opt_key.replace('fire-and-ice-factions/variable_v', '')
                else:
                    self.options[opt_key] = '1'

            if 'SCORE' in k:
                sid = int(k.replace('SCORE', ''))
                for r in range(1, 7):
                    if str(r) in v['round']:
                        self.score_tiles[str(r)] = sid

            # Greatest Distance
            if 'scoring-connected-distance' in k:
                self.options['fire-and-ice-final-scoring'] = 1

            # Stronghold and Sanctuary
            if 'scoring-connected-sa-sh-distance' in k:
                self.options['fire-and-ice-final-scoring'] = 2

            # Outposts
            if 'scoring-building-on-edge' in k:
                self.options['fire-and-ice-final-scoring'] = 3

            # Settlements
            if 'scoring-connected-clusters' in k:
                self.options['fire-and-ice-final-scoring'] = 4
        self.dropped_players = global_['drop-faction']['all'] if 'drop-faction' in global_ and 'all' in global_['drop-faction'] else 0

    def parse_players(self, factions):
        players = []
        for faction in factions:
            if faction['player'] is None:
                players.append('anon-' + faction['faction'])
            else:
                players.append(faction['player'])

            if faction['faction'] == 'yetis' or faction['faction'] == 'icemaidens':
                if 'fire-and-ice-factions/ice' not in self.options:
                    self.options['fire-and-ice-factions/ice'] = 1

            if faction['faction'] == 'dragonlords' or faction['faction'] == 'acolytes':
                if 'fire-and-ice-factions/volcano' not in self.options:
                    self.options['fire-and-ice-factions/volcano'] = 1

            if faction['faction'] == 'shapeshifters' or faction['faction'] == 'riverwalkers':
                if 'fire-and-ice-factions/variable' not in self.options:
                    self.options['fire-and-ice-factions/variable'] = 1

        self.multifaction = 1 if len(list(set(players))) != len(players) else 0


def load():
    """Try to load from pickled data."""
    allstats = []
    if GAME_FILENAME.is_file():
        with gzip.open(GAME_FILENAME) as game_file:
            print("loading... ")
            allstats = pickle.load(game_file)
            print("done!")
    return allstats


def save(allstats):
    print("saving... ")
    with gzip.open(GAME_FILENAME, 'w+') as game_file:
        pickle.dump(allstats, game_file)
    print("done!")


def parse_game_file(game_fn):
    if debug:
        print("game_id,faction,result_key,vp,margin,R1,R2,R3,R4,R5,R6")

    stats = []
    if game_fn.suffix == 'gz':
        openfunc = gzip.open
    else:
        openfunc = open
    with openfunc(game_fn) as game_file:
        print("parsing ", game_fn, "...")
        games = json.load(game_file)
        for game in games:
            f = dict([(i['faction'], i['player']) for i in game['factions']])
            if 'player1' in f or 'player2' in f or 'player3' in f or 'player4' in f or 'player5' in f or 'player6' in f or 'player7' in f:
                print("Skipping game with incomplete players:", game['game'])
                continue
            game['factions2'] = f

            if game['game'] in BLACKLIST:
                print("Skipping irregular game:", game['game'])
                continue

            if 'drop-faction' in game['events']['global']:
                print("Skipping the game has dropped players:", game['game'])
                continue

            factions = []
            for faction in f.keys():
                if faction[:6] == 'nofact':
                    continue
                try:
                    s = FactionStat(game, faction)
                    if s.bonus:  # Empty player count?
                        if s.multifaction > 0:
                            print("Player of this game plays multi factions:", s.game_id)
                            break
                        elif s.num_nofactions > 0:
                            print("Game with NoFaction:", s.game_id)
                            break
                        else:
                            factions.append(s)
                except KeyError as e:
                    print(game_fn, "failed! (", faction, "didn't have", str(e.args), ")")

            for faction1 in factions:
                for faction2 in factions:
                    if faction1.score < faction2.score:
                        faction1.rank_in_game += 1

            if debug:
                for s in factions:
                    print(game['game'] + ',' + s.name + ',' + get_key(s) + ',' + str(s.score) + ',' + str(s.margin) + ',' + str(s.score_tiles['1']) + ',' + str(s.score_tiles['2']) + ',' + str(s.score_tiles['3']) + ',' + str(s.score_tiles['4']) + ',' + str(s.score_tiles['5']) + ',' + str(s.score_tiles['6']))

            stats += factions

    fn = game_fn.stem
    stats_fn = 'docs/stats' + fn[2:4] + fn[5:7] + '.json'
    stats_fn = Path(stats_fn)
    if not stats_fn.is_file():
        save_stats(compute_stats(stats, get_key), stats_fn)
    return stats


def parse_games(game_list=None):
    allstats = []
    if not game_list:
        game_list = GAME_PATH.iterdir()
    for game in game_list:
        try:
            if game.suffix == '.json':
                allstats.extend(parse_game_file(game))
            else:
                print(game, "is not matched")
        except KeyboardInterrupt:
            break
    return allstats


#####
# Here and below are parsing stats into web json
#####


def get_rating(player, faction):
    if player not in ratings:
        return 0
    if 'score' not in ratings[player]:
        return 0
    score = ratings[player]['score']
    if score < 1000:
        return 1
    elif score < 1100:
        return 2
    elif score < 1250:
        return 3
    else:
        return 4


def get_key(faction):
    # all option at 2016-07-05
    # option-email-notify:
    # option-errata-cultist-power:
    # option-fire-and-ice-factions/ice:
    # option-fire-and-ice-factions/variable:
    # option-fire-and-ice-factions/variable_v2:
    # option-fire-and-ice-factions/variable_v3:
    # option-fire-and-ice-factions/variable_v4:
    # option-fire-and-ice-factions/variable_v5:
    # option-fire-and-ice-factions/volcano:
    # option-fire-and-ice-final-scoring:
    # option-loose-adjust-resource:
    # option-maintain-player-order:
    # option-mini-expansion-1:
    # option-shipping-bonus:
    # option-strict-chaosmagician-sh:
    # option-strict-darkling-sh:
    # option-strict-leech:
    # option-temple-scoring-tile:
    # option-variable-turn-order:

    # print(faction.score_tiles)
    key = ''
    key += str(faction.map_type)  # 0
    key += '0' if 'errata-cultist-power' not in faction.options else '1'  # 1
    key += '0' if 'mini-expansion-1' not in faction.options else '1'  # 2
    key += '0' if 'shipping-bonus' not in faction.options else '1'  # 3
    key += '0' if 'fire-and-ice-final-scoring' not in faction.options else str(faction.options['fire-and-ice-final-scoring'])  # 4
    key += '0' if 'fire-and-ice-factions/ice' not in faction.options else '1'  # 5
    key += '0' if 'fire-and-ice-factions/volcano' not in faction.options else '1'  # 6
    key += '0' if 'fire-and-ice-factions/variable' not in faction.options else str(faction.options['fire-and-ice-factions/variable'])  # 7
    key += '0' if 'variable-turn-order' not in faction.options else '1'  # 8
    key += '0' if 'temple-scoring-tile' not in faction.options else '1'  # 9
    key += str(faction.score_tiles['1'])  # 10
    key += str(faction.orders['1'])  # 11
    key += str(FDICT[faction.name])  # 12
    key += str(faction.numplayers)  # 13
    key += str(get_rating(faction.user, faction.name))  # 14
    key += ''.join(str(i) for i in tuple(faction.builts[:, 1]))  # 15-19
    key += str(faction.bonus[0])  # 20
    key += str(faction.leech_pw[1])  # 21
    # key += str(faction.rank_in_game) #
    key += faction.period  # 22-24
    key += ''.join(hex(i + 1)[2] for i in tuple(np.where(faction.favs <= 1)[0]))  # 25-
    # print(faction.favs)
    return key


def get_key2(faction):
    # all option at 2016-07-05
    # option-email-notify:
    # option-errata-cultist-power:
    # option-fire-and-ice-factions/ice:
    # option-fire-and-ice-factions/variable:
    # option-fire-and-ice-factions/variable_v2:
    # option-fire-and-ice-factions/variable_v3:
    # option-fire-and-ice-factions/variable_v4:
    # option-fire-and-ice-factions/variable_v5:
    # option-fire-and-ice-factions/volcano:
    # option-fire-and-ice-final-scoring:
    # option-loose-adjust-resource:
    # option-maintain-player-order:
    # option-mini-expansion-1:
    # option-shipping-bonus:
    # option-strict-chaosmagician-sh:
    # option-strict-darkling-sh:
    # option-strict-leech:
    # option-temple-scoring-tile:
    # option-variable-turn-order:

    # print(faction.score_tiles)
    key = ''
    key += str(faction.map_type)  # 0
    key += '0' if 'errata-cultist-power' not in faction.options else '1'  # 1
    key += '0' if 'mini-expansion-1' not in faction.options else '1'  # 2
    key += '0' if 'shipping-bonus' not in faction.options else '1'  # 3
    key += '0' if 'fire-and-ice-final-scoring' not in faction.options else str(faction.options['fire-and-ice-final-scoring'])  # 4
    key += '0' if 'fire-and-ice-factions/ice' not in faction.options else '1'  # 5
    key += '0' if 'fire-and-ice-factions/volcano' not in faction.options else '1'  # 6
    key += '0' if 'fire-and-ice-factions/variable' not in faction.options else str(faction.options['fire-and-ice-factions/variable'])  # 7
    key += '0' if 'variable-turn-order' not in faction.options else '1'  # 8
    key += '0' if 'temple-scoring-tile' not in faction.options else '1'  # 9
    key += str(faction.score_tiles['1'])  # 10
    key += str(faction.score_tiles['2'])  # 11
    key += str(faction.score_tiles['3'])  # 12
    key += str(faction.score_tiles['4'])  # 13
    key += str(faction.score_tiles['5'])  # 14
    key += str(faction.score_tiles['6'])  # 15
    key += str(faction.orders['1'])  # 16
    key += str(FDICT[faction.name])  # 17
    key += str(faction.numplayers)  # 18
    key += str(get_rating(faction.user, faction.name))  # 19
    key += ''.join('%d' % faction.all_bons[i] for i in range(1, 11))  # 20-29
    key += faction.period  # 30-32
    return key


def get_statpool(allstats, statfuncs, key_func=get_key):
    statpool = {}
    statbase = [Welford() for x in statfuncs]
    for faction in allstats:
        if '1' not in faction.score_tiles:
            print("invalid score tiles:", faction.game_id)
            continue
        key = key_func(faction)
        stats = statpool.setdefault(key, copy.deepcopy(statbase))

        for i, statfunc in enumerate(statfuncs):
            stats[i](statfunc(faction))

    return statpool


def compute_stats(allstats, key_func):
    return get_statpool(
        allstats,
        [
            lambda fact: float(fact.score),
            lambda fact: float(fact.margin)
        ],
        key_func
    )


def save_stats(statpool, filename=None):
    def jsonify(x):
        """Handles welford stats"""
        if x.n == 1:
            return x.M1
        else:
            return x.n, x.M1, x.M2, x.M3, x.M4

    if filename is None:
        filename = Path('docs/stats.json')

    with open(filename, 'w+') as f:
        json.dump(statpool, f, default=jsonify, indent=2)


if __name__ == '__main__':
    debug = False

    try:
        with open('ratings.json') as f:
            ratings = json.load(f)['players']
    except:
        print("Warning! Download http://terra.snellman.net/data/ratings.json to get player ratings")
        ratings = {}

    allstats = load()
    if not allstats:
        if not GAME_PATH.is_dir():
            print(f"You should download some games (see http://terra.snellman.net/data/events/) to {str(GAME_PATH)}")
            exit(1)
        allstats = parse_games()
        # save(allstats)

    print("Computing...")
    save_stats(compute_stats(allstats, get_key), 'docs/stats.json')

    save_stats(compute_stats(allstats, get_key2), 'docs/chooser.json')
    print("Finished")
