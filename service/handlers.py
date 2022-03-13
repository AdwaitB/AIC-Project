from consts import *

class Config:
    isMaster = False
    scanSet = []

    def getDict(self):
        retDict = {}

        for key in dir(self):
            if key.startswith("__") or key.startswith("_"):
                continue
            else:
                attr = getattr(self, key)
                if not callable(attr):
                    retDict[key] = getattr(self, key)
        
        return retDict


config = Config()

def ping(json={}):
    json[TYPE] = PONG
    json[STATUS] = SUCCESS
    return json

def init(json={}):
    json[STATUS] = SUCCESS
    return json

def configUpdate(json={}):
    if CONFIG not in json:
        return {STATUS: FAILURE}
    
    for key in json[CONFIG].keys():
        if key.startswith("__") or key.startswith("_"):
            continue

        if key in dir(config):
            setattr(config, key, json[CONFIG][key])

    json[STATUS] = SUCCESS
    json[CONFIG] = config.getDict()
    return json
