import argparse
import copy

from flask import Flask, request

from handlers import ping, init
from consts import *

apiTypeMappings = {
    "PING":     ping,
    "INIT":     init  
}

app = Flask(__name__)

@app.route('/', methods=['POST'])
def default():
    if (getattr(request, "json") is None) or \
        (TYPE not in request.json) or \
            (request.json[TYPE] not in apiTypeMappings.keys()):
        return {STATUS: FAILURE}
    
    print()

    requestCopy = copy.deepcopy(request.json)
    requestCopy[STATUS] = FAILURE
    return apiTypeMappings[requestCopy[TYPE]](requestCopy)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description="sample argument parser")
    parser.add_argument('-p', '--port', type=int, required=True, dest=PORT)
    parsedArgs = parser.parse_args()
    
    app.run(debug=True, port=parsedArgs.PORT)
