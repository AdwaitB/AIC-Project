import os

from random import randint
from requests import get, post

from flask import request, render_template

import numpy as np

import cv2

import tensorflow as tf
from tensorflow.keras.models import load_model

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

def uploadImage(json={}, app=None):
    if request.method == "POST":
        if request.files:
            image = request.files["image"]
            image.save(os.path.join(app.config["IMAGE_UPLOADS"], image.filename))
            return render_template("upload_image.html", uploaded_image=image.filename)
    return render_template("upload_image.html")

def predict(json={}, app=None):
    model = load_model("./service/covid_model.h5", compile=True)
    filename = json[FILENAME]
    image = cv2.imread("./service/images/" + filename)

    if image is not None:
        json[STATUS] = SUCCESS
        image = np.array(cv2.resize(image, (70, 70)) / 255.0)
        json[PREDICTION] = np.argmax(model.predict([image]), axis=1)
    
    return json

def ping(json={}, app=None):
    json[TYPE] = PONG
    json[CONFIG] = config.getDict()
    json[STATUS] = SUCCESS
    return json

def init(json={}, app=None):
    json[STATUS] = SUCCESS
    return json

def vote(json={}, app=None):
    json[MYVOTE] = randint(0, 10**10)
    json[STATUS] = SUCCESS
    return json

def masterSelect(json={}, app=None):
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

def configUpdate(json={}, app=None):
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

def shutdown(json={}, app=None):
    json[STATUS] = SUCCESS
    return json