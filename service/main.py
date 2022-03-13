from urllib import request
from requests import get, post

from consts import *

_1 = "http://127.0.0.1:12001"
_2 = "http://127.0.0.1:12002"

r = post(_1, json={
    TYPE: CONFIG,
    CONFIG: {
        ISMASTER: True,
        PEERS: [_2]
    }
}).json()

print(r)

r = post(_2, json={
    TYPE: CONFIG,
    CONFIG: {
        ISMASTER: False,
        PEERS: [_1]
    }
}).json()

print(r)

r = post(_1, json={
    TYPE: MASTERSELECT
}).json()

print(r)
