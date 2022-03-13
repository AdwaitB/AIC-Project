from operator import truediv
from random import randint
from requests import get, post

from consts import *

class Config:
    isMaster = False
    peers = []

    def getDict(self):
        retDict = {}

        for key in dir(self):
            if key.startswith("__") or key.startswith("_"):
                continue
        
            attr = getattr(self, key)
            if not callable(attr):
                retDict[key] = getattr(self, key)
        
        return retDict


config = Config()

def ping(json={}):
    json[TYPE] = PONG
    json[CONFIG] = config.getDict()
    json[STATUS] = SUCCESS
    return json

def init(json={}):
    json[STATUS] = SUCCESS
    return json

def vote(json={}):
    json[MYVOTE] = randint(0, 10**10)
    json[STATUS] = SUCCESS
    return json

def masterSelect(json={}):
    if not config.isMaster:
        return {STATUS: FAILURE} 

    requestData = {TYPE: VOTE}
    maxVote = -1
    newMaster = None

    for ip in config.peers:
        response = post(ip, json=requestData).json()
        if response[STATUS] != SUCCESS:
            continue

        if response[MYVOTE] > maxVote:
            maxVote = response[MYVOTE]
            newMaster = ip
    
    if newMaster is not None:
        requestData = get(newMaster).json()
        response = post(newMaster, json={TYPE:CONFIG, CONFIG:{ISMASTER:True}}).json()

        print(response)

        if response[STATUS] == SUCCESS:
            config.isMaster = False
            json[NEWMASTER] = newMaster
        else:
            return {STATUS: FAILURE}
        
        json[STATUS] = SUCCESS
        return json
    else:
        return {STATUS: FAILURE} 

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

def shutdown(json={}):
    json[STATUS] = SUCCESS
    return json