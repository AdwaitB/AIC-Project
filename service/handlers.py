from consts import *

def ping(json):
    json[TYPE] = PONG
    json[STATUS] = SUCCESS
    return json

def init(json):
    json[STATUS] = SUCCESS
    return json
