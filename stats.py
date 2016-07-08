#!/usr/bin/env python
import json, cPickle as pickle, os.path, numpy, sys, copy, gzip
from collections import defaultdict
from welford import Welford

GAME_PATH="games"

GAME_FILENAME = "games.pickle.gz"

mapdict={
  u'126fe960806d587c78546b30f1a90853b1ada468': 0, # Original
  u'95a66999127893f5925a5f591d54f8bcb9a670e6': 1, # Fire & Ice, Side 1
  u'be8f6ebf549404d015547152d5f2a1906ae8dd90': 2, # Fire & Ice, Side 2
  u'b109f78907d2cbd5699ced16572be46043558e41': 3, # illegal map game=nan0002
  u'735b073fd7161268bb2796c1275abda92acd8b1a': 4, # illegal map game=gareth44,expm28
  u'30b6ded823e53670624981abdb2c5b8568a44091': 5} # illegal map game=gareth45

blacklist=[
  "nan0002", #base_map=b109f78907d2cbd5699ced16572be46043558e41
  "gareth44", #base_map=735b073fd7161268bb2796c1275abda92acd8b1a
  "expm28", #base_map=735b073fd7161268bb2796c1275abda92acd8b1a
  "gareth45", #base_map=30b6ded823e53670624981abdb2c5b8568a44091
  "Bgg50", # bridged more than 3
  "DaveMattDouble2", # bridged more than 3
  ]

class FactionStat(object):
    def __init__(self, game, name ):
        self.game_id = game["game"]
        self.name = name
        self.globals = game["events"]["global"]
        self.events = game["events"]["faction"][name]
        self.user  = game["factions2"][name]
        self.score = self.events["vp"]["round"]["all"]+20
        self.numplayers = game["player_count"]
        avgscore = float( game["events"]["faction"]["all"]["vp"]["round"]["all"] ) / self.numplayers + 20
        self.margin = self.score  - avgscore
        self.map_type = mapdict[game["base_map"]]
        self.additional_score = 1 if "option-fire-and-ice-final-scoring" in game["events"]["global"] else 0
        self.ice_available = 1 if "option-fire-and-ice-factions/ice" in game["events"]["global"] else 0
        self.volcano_available = 1 if "option-fire-and-ice-factions/volcano" in game["events"]["global"] else 0
        if "option-fire-and-ice-factions/variable_v5" in game["events"]["global"]:
            self.variable_version = 5
        elif "option-fire-and-ice-factions/variable_v4" in game["events"]["global"]:
            self.variable_version = 4
        elif "option-fire-and-ice-factions/variable_v3" in game["events"]["global"]:
            self.variable_version = 3
        elif "option-fire-and-ice-factions/variable_v2" in game["events"]["global"]:
            self.variable_version = 2
        elif "option-fire-and-ice-factions/variable" in game["events"]["global"]:
            self.variable_version = 1
        else:
            self.variable_version = 0

        self.parse_events()
        self.orders = numpy.array( [ self.parse_order( i ) for i in range(1,8) ] )
        self.parse_global( game["events"]["global"] )
        del self.events #don't need this anymore!

    def parse_event(self, evt ):
        if evt not in self.events:
            return numpy.zeros( 7 )
        r = defaultdict(int,self.events[evt]["round"])
        return numpy.array((r["0"],r["1"],r["2"],r["3"],r["4"],r["5"],r["6"] ))

    def parse_favor( self, num ):
        key = "favor:FAV"+str(num)
        if key not in self.events:
            return 0
        r = self.events[key]["round"].keys()
        r.remove("all")
        return int(r[0])

    def parse_town( self, num ):
        key = "town:TW"+str(num)
        if key not in self.events:
            return 0
        r = self.events[key]["round"].keys()
        r.remove("all")
        return int(r[0])

    def parse_bonus( self, num ):
        key = "pass:BON"+str(num)
        if key not in self.events:
            return numpy.zeros( 7 )
        r = defaultdict(int,self.events[key]["round"])
        return numpy.array((r["0"],r["1"],r["2"],r["3"],r["4"],r["5"],r["6"] ))

    def parse_order( self, num ):
        key = "order:"+str(num)
        if key not in self.events:
            return numpy.zeros( 6 )
        r = defaultdict(int,self.events[key]["round"])
        return numpy.array((r["1"]*num,r["2"]*num,r["3"]*num,r["4"]*num,r["5"]*num,r["6"]*num ))

    def parse_events( self ):
        D_evt  = self.parse_event( "build:D" )
        TP_evt = self.parse_event( "upgrade:TP" )
        TE_evt = self.parse_event( "upgrade:TE" )
        SA_evt = self.parse_event( "upgrade:SA" )
        SH_evt = self.parse_event( "upgrade:SH" )

        #upgrade path...
        D  = numpy.cumsum( D_evt  - TP_evt )
        TP = numpy.cumsum( TP_evt - TE_evt - SH_evt )
        TE = numpy.cumsum( TE_evt - SA_evt )
        SA = numpy.cumsum( SA_evt )
        SH = numpy.cumsum( SH_evt )

        #each building, each round
        self.B = numpy.array( ( D, TP, TE, SA, SH ), dtype=int )
        #each FAV, which round (if any)
        self.FAV = numpy.array( [ self.parse_favor( i ) for i in range(1,13) ] )
        #each TW, which round (if any)
        self.TW  = numpy.array( [ self.parse_town( i ) for i in range(1,9) ] )
        #each round, which BON
        self.BON = tuple( numpy.where( numpy.array( [ self.parse_bonus( i ) for i in range(1,11) ] ).transpose() == 1 )[1] )
        
        self.leech_pw = self.parse_event( "leech:pw" )

    def parse_global( self, global_ ):
        self.options = {}
        self.score_tiles = {}
        for k,v in global_.items():
            if "options-" in k:
                opt_key = k.replace("options-", "")
                if opt_key.startwith("fire-and-ice-factions/variable_v"):
                    self.options["option-fire-and-ice-factions/variable"] = int(opt_key.replace("fire-and-ice-factions/variable_v", ""))
                else:
                    self.options[opt_key] = 1
            if "SCORE" in k:
                sid = int(k.replace("SCORE", ""))
                for r in range(1,7):
                    if str(r) in v["round"]:
                        self.score_tiles[str(r)] = sid

def load():
    allstats = []
    #Try to load from pickle
    if os.path.isfile( GAME_FILENAME ):
        with gzip.open( GAME_FILENAME ) as game_file:
            print "loading... ",
            sys.stdout.flush()
            allstats = pickle.load( game_file )
            print "done!"
    return allstats

def save( allstats ):
    print "saving... ",
    sys.stdout.flush()
    with gzip.open( GAME_FILENAME, "w+" ) as game_file:
        pickle.dump( allstats, game_file ) 
    print( "done!")

def parse_game_file( game_fn ):
    stats = []
    if game_fn[-2:] == "gz":
        openfunc = gzip.open
    else:
        openfunc = open
    with openfunc( game_fn ) as game_file:
        print( "parsing " + game_fn + "..." )
        games = json.load( game_file )
        for game in games:
            f = dict( [(i["faction"],i["player"]) for i in game["factions"]])
            if "player1" in f or "player2" in f or "player3" in f or "player4" in f or "player5" in f or "player6" in f or "player7" in f:
                print("Skpping game with incomplete players...")
                continue
            game["factions2"] = f;
            if game["game"] in blacklist:
                print("Skipping illegal game:"+game["game"])
                continue
            for faction in f.keys():
                if faction[:6] == "nofact":
                    continue
                try:
                    s =  FactionStat( game, faction ) 
                    if s.BON: #Empty player count?
                        stats.append( s )
                except KeyError,e :
                    print( game_fn + " failed! ("+faction+" didn't have "+str(e.args)+")" )
                    import pdb
                    pdb.set_trace()
    return stats

def parse_games( game_list = None ):
    allstats = []
    if not game_list:
        game_list = map( lambda g: GAME_PATH + os.path.sep + g, os.listdir( GAME_PATH ) )
    for game in game_list:
        try:
            if '.json' in game:
                allstats.extend( parse_game_file( game ) )
            else:
                print game, "is not matched"
        except KeyboardInterrupt, e:
            break
        #except TypeError, e:
        #    print game, "is not game json"
        #    continue
    return allstats


"""
Here and below are parsing stats into web json
"""


try:
    with open( "ratings.json" ) as f:
        ratings = json.load( f )["players"]
except:
    print("Warning! Download http://terra.snellman.net/data/ratings.json to get player ratings")
    ratings = {}

def get_rating( player, faction ):
    if player not in ratings:
        return 0
    if "faction_breakdown" not in ratings[player]:
        return 0
    if faction not in ratings[player]["faction_breakdown"]:
        return 0
    score = ratings[player]["faction_breakdown"][faction]["score"]
    if score < -37:
        return 0
    elif score < 0:
        return 1
    elif score < 37:
        return 2
    else:
        return 3


fdict= {u'acolytes': 'a',
 u'alchemists': 'b',
 u'auren': 'c',
 u'chaosmagicians': 'd',
 u'cultists': 'e',
 u'darklings': 'f',
 u'dragonlords': 'g',
 u'dwarves': 'h',
 u'engineers': 'i',
 u'fakirs': 'j',
 u'giants': 'k',
 u'halflings': 'l',
 u'icemaidens': 'm',
 u'mermaids': 'n',
 u'nomads': 'o',
 u'riverwalkers': 'p',
 u'shapeshifters': 'q',
 u'swarmlings': 'r',
 u'witches': 's',
 u'yetis': 't'}

def get_key( faction ):
    #print faction.score_tiles
    key = ""
    key += str(faction.map_type)
    key += str(faction.additional_score)
    key += str(faction.score_tiles["1"])
    key += str(faction.orders[1])
    key += str(fdict[faction.name])
    key += str( faction.numplayers )
    key += str( get_rating( faction.user, faction.name ))
    key += "".join( str(i) for i in tuple(faction.B[:,1]))
    key += str(faction.BON[0])
    key += "{0:0>2}".format(int(faction.leech_pw[1]))
    key += "".join( hex(i+1)[-1] for i in tuple(numpy.where( faction.FAV == 1 )[0]))
    return key


def get_statpool( allstats, statfuncs ):
    statpool = {}
    statbase = [ Welford() for x in statfuncs ]
    for faction in allstats:
        if "1" not in faction.score_tiles:
            print "invalid score tiles:"+faction.game_id
        key  = get_key(faction)
        stats = statpool.setdefault( key, copy.deepcopy( statbase ) )
        for i,statfunc in enumerate(statfuncs):
            stats[i]( statfunc( faction ) )
    return statpool


"""
Deprecated
def compute_vp_stats( allstats ):
    vp_stats = {}
    vp_factstats = {}
    for game,factions in allstats.items():
        for faction in factions:
            for source,vp in faction.vp_source.items():
                vp_stats.setdefault(source,Welford())(vp)
                vp_factstats.setdefault(faction.name,dict()).setdefault(source,Welford())(vp)
    return vp_stats, vp_factstats
"""

def compute_stats( allstats ):
    return get_statpool( allstats, [ lambda fact: float(fact.score), lambda fact: float(fact.margin)] )

def save_stats( statpool, filename = "stats.json" ):
    def jsonify( x ):
        """Handles welford stats"""
        if x.n == 1:
            return int(10*x.M1)
        else:
            return [x.n,int(10*x.M1),int(10*x.M2),int(10*x.M3),int(10*x.M4)]

    with open( filename, "w+") as f:
        json.dump( statpool, f, default = jsonify )

if __name__ == "__main__":
    allstats = load()
    if not allstats:
        if not os.path.isdir( GAME_PATH ):
            print( "You should download some games (see http://terra.snellman.net/data/events/ ) to "+GAME_PATH )
            exit(1)
        allstats = parse_games()
        #save( allstats )
    print "Computing...",
    statpool = compute_stats( allstats )
    print "Finished"
    save_stats( statpool )
