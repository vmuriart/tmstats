#!/usr/bin/env python
import json, cPickle as pickle, os.path, numpy, sys, copy, gzip
from collections import defaultdict
from welford import Welford

GAME_PATH="games"

GAME_FILENAME = "games.pickle.gz"

mapdict={
  u'126fe960806d587c78546b30f1a90853b1ada468': 'a', # Original
  u'95a66999127893f5925a5f591d54f8bcb9a670e6': 'b', # Fire & Ice, Side 1
  u'be8f6ebf549404d015547152d5f2a1906ae8dd90': 'c', # Fire & Ice, Side 2
  u'b109f78907d2cbd5699ced16572be46043558e41': 'd', # illegal map game=nan0002
  u'735b073fd7161268bb2796c1275abda92acd8b1a': 'e', # illegal map game=gareth44,expm28
  u'30b6ded823e53670624981abdb2c5b8568a44091': 'f'} # illegal map game=gareth45

blacklist=[
  "nan0002", #base_map=b109f78907d2cbd5699ced16572be46043558e41
  "gareth44", #base_map=735b073fd7161268bb2796c1275abda92acd8b1a
  "expm28", #base_map=735b073fd7161268bb2796c1275abda92acd8b1a
  "gareth45", #base_map=30b6ded823e53670624981abdb2c5b8568a44091
  "Bgg50", # bridged more than 3
  "DaveMattDouble2", # bridged more than 3
  "wayne", # invalid score tiles
  "JogaGREat5", # CM double pass bug
  "JogaGreat4", # CM double pass bug
  "PenisEnvy1", # CM double pass bug
  "JG9", # CM double pass bug
  "sky05", # CM double pass bug
  "JG10", # CM double pass bug
  "Terra4m", # CM double pass bug
  "Tools001", # CM double pass bug
  "DvMvRvB4", # CM double pass bug
  "marcelp24", # CM double pass bug
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

        self.parse_events()
        self.orders =  self.parse_order()
        self.options = {}
        self.score_tiles = {}
        self.parse_global( game["events"]["global"] )
        self.parse_players( game["factions"] )
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

    def parse_order( self ):
        result = {}
        for num in range(1, 8):
            key = "order:"+str(num)
            if key not in self.events:
                continue
            r = self.events[key]["round"].keys()
            r.remove("all")
            for k in r:
                result[str(k)] = num
        return result

    def parse_leech( self ):
        pw = []
        for k in self.parse_event( "leech:pw" ):
            pw.append(min(4, int(k/4)))
        return pw

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
        
        self.leech_pw = self.parse_leech()
        

    def parse_global( self, global_ ):
        for k,v in global_.items():
            if "option-" in k:
                opt_key = k.replace("option-", "")
                if opt_key.startswith("fire-and-ice-factions/variable_v"):
                    self.options["fire-and-ice-factions/variable"] = opt_key.replace("fire-and-ice-factions/variable_v", "")
                else:
                    self.options[opt_key] = '1'
            if "SCORE" in k:
                sid = int(k.replace("SCORE", ""))
                for r in range(1,7):
                    if str(r) in v["round"]:
                        self.score_tiles[str(r)] = sid
        #self.options["fi-factions/ice"] = 1 if "option-fire-and-ice-factions/ice" in global_ else 0
        #self.options["fi-factions/volcano"] = 1 if "option-fire-and-ice-factions/volcano" in global_ else 0
        #if "option-fire-and-ice-factions/variable_v5" in global_:
        #    self.self.options["fi-factions/variable"] = 5
        #elif "option-fire-and-ice-factions/variable_v4" in global_:
        #    self.self.options["fi-factions/variable"] = 4
        #elif "option-fire-and-ice-factions/variable_v3" in global_:
        #    self.self.options["fi-factions/variable"] = 3
        #elif "option-fire-and-ice-factions/variable_v2" in global_:
        #    self.self.options["fi-factions/variable"] = 2
        #elif "option-fire-and-ice-factions/variable" in global_:
        #    self.self.options["fi-factions/variable"] = 1
        #else:
        #    self.self.options["fi-factions/variable"] = 0
    def parse_players( self, factions ):
        players = []
        for faction in factions:
            if faction[u"player"] == None:
                players.append(u"anon-"+faction[u"faction"])
            else:
                players.append(faction[u"player"])
        self.multifaction = 1 if len(list(set(players))) != len(players) else 0
        #if self.multifaction == 1:
        #    print players

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
                print("Skipping irregular game: "+game["game"])
                continue
            for faction in f.keys():
                if faction[:6] == "nofact":
                    continue
                try:
                    s =  FactionStat( game, faction ) 
                    if s.BON: #Empty player count?
                        if s.multifaction == 0:
                            stats.append( s )
                        else:
                            print "Player of this game plays multi factions: "+s.game_id
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
    # all option at 2016-07-05
    #option-email-notify:
    #option-errata-cultist-power:
    #option-fire-and-ice-factions/ice:
    #option-fire-and-ice-factions/variable:
    #option-fire-and-ice-factions/variable_v2:
    #option-fire-and-ice-factions/variable_v3:
    #option-fire-and-ice-factions/variable_v4:
    #option-fire-and-ice-factions/variable_v5:
    #option-fire-and-ice-factions/volcano:
    #option-fire-and-ice-final-scoring:
    #option-loose-adjust-resource:
    #option-maintain-player-order:
    #option-mini-expansion-1:
    #option-shipping-bonus:
    #option-strict-chaosmagician-sh:
    #option-strict-darkling-sh:
    #option-strict-leech:
    #option-temple-scoring-tile:
    #option-variable-turn-order:

    #print faction.score_tiles
    key = ""
    key += str(faction.map_type) #0
    key += "0" if "errata-cultist-power" not in faction.options else "1" #1
    key += "0" if "mini-expansion-1" not in faction.options else "1" #2
    key += "0" if "shipping-bonus" not in faction.options else "1" #3
    key += "0" if "fire-and-ice-final-scoring" not in faction.options else "1" #4
    key += "0" if "fire-and-ice-factions/ice" not in faction.options else "1" #5
    key += "0" if "fire-and-ice-factions/volcano" not in faction.options else "1" #6
    key += "0" if "fire-and-ice-factions/variable" not in faction.options else str(faction.options["fire-and-ice-factions/variable"]) #7
    key += "0" if "variable-turn-order" not in faction.options else "1" #8
    key += "0" if "temple-scoring-tile" not in faction.options else "1" #9
    key += str(faction.score_tiles["1"]) #10
    key += str(faction.orders["1"]) #11
    key += str(fdict[faction.name]) #12
    key += str( faction.numplayers ) #13
    key += str( get_rating( faction.user, faction.name )) #14
    key += "".join( str(i) for i in tuple(faction.B[:,1])) #15-19
    key += str(faction.BON[0]) #20
    key += str(faction.leech_pw[1]) #21
    key += "".join( hex(i+1)[-1] for i in tuple(numpy.where( faction.FAV == 1 )[0])) #22-
    return key


def get_statpool( allstats, statfuncs ):
    statpool = {}
    statbase = [ Welford() for x in statfuncs ]
    for faction in allstats:
        if "1" not in faction.score_tiles:
            print "invalid score tiles: "+faction.game_id
            continue
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
