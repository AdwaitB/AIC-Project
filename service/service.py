import argparse

from flask import Flask, request

PORT = "PORT"

app = Flask(__name__)

@app.route('/', methods=['POST'])
def default():
    if getattr(request, "json") is None:
        return {}
    else:
        return request.json

if __name__=='__main__':
    parser = argparse.ArgumentParser(description="sample argument parser")
    parser.add_argument('-p', '--port', type=int, required=True, dest=PORT)
    parsedArgs = parser.parse_args()
    
    app.run(debug=True, port=parsedArgs.PORT)
