from urllib import request
from requests import get, post

from consts import *

_1 = "http://127.0.0.1:12000"
_2 = "http://127.0.0.1:12001"

r = post(_1, json={
    TYPE: PREDICT,
    FILENAME: "COVID-997.png"
}).json()

# print(r)
# r = post(_1, json={
#     TYPE: PREDICT,
#     FILENAME: "COVID-991.png"
# }).json()

print(r)
