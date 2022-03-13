import argparse
import copy

from flask import Flask, request

from handlers import *
from consts import *

apiTypeMappings = {
    "PING":     ping,
    "INIT":     init,
    "CONFIG":   configUpdate
}

app = Flask(__name__)

@app.route('/', methods=['POST'])
def post_():
    if (getattr(request, "json") is None) or \
        (TYPE not in request.json) or \
            (request.json[TYPE] not in apiTypeMappings.keys()):
        return {STATUS: FAILURE}

    requestCopy = copy.deepcopy(request.json)
    requestCopy[STATUS] = FAILURE
    return apiTypeMappings[requestCopy[TYPE]](requestCopy)

@app.route('/', methods=['GET'])
def get_():
    return ping()

if __name__=='__main__':
    parser = argparse.ArgumentParser(description="sample argument parser")
    parser.add_argument('-p', '--port', type=int, required=True, dest=PORT)
    parsedArgs = parser.parse_args()
    
    app.run(debug=True, port=parsedArgs.PORT)
