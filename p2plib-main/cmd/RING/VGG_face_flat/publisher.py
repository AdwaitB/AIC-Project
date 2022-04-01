import gc
gc.disable()

import random
import json
import sys
import time
import datetime

import logging
default_logger = logging.getLogger('tunnel.logger')
default_logger.setLevel(logging.CRITICAL)
default_logger.disabled = False

from ctypes import cdll
import ctypes

import pickle

FUNC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)

#to server
OP_RECV                      = 0x00
#OP_CLIENT_WAKE_UP            = 0x01
OP_CLIENT_READY              = 0x02
OP_CLIENT_UPDATE             = 0x03
OP_CLIENT_EVAL               = 0x04
#to client
OP_INIT                      = 0x05
OP_REQUEST_UPDATE            = 0x06
OP_STOP_AND_EVAL             = 0x07

def obj_to_pickle_string(x):
    import base64
    return base64.b64encode(pickle.dumps(x))

def pickle_string_to_obj(s):
    import base64
    #return pickle.loads(base64.b64decode(s))
    return pickle.loads(base64.b64decode(s, '-_'))

class GlobalModel(object):
    """docstring for GlobalModel"""
    def __init__(self):
        self.model = self.build_model()
        self.current_weights = self.model.get_weights()
        # for convergence check
        self.prev_train_loss = None

        # all rounds; losses[i] = [round#, timestamp, loss]
        # round# could be None if not applicable
        self.train_losses = []
        self.valid_losses = []
        self.train_accuracies = []
        self.valid_accuracies = []

        self.training_start_time = int(round(time.time()))
    
    def build_model(self):
        raise NotImplementedError()

    # client_updates = [(w, n)..]
    def update_weights(self, client_weights, client_sizes):
        #print(len(client_weights))
        import numpy as np
        new_weights = [np.zeros(w.shape) for w in self.current_weights]
        total_size = np.sum(client_sizes)

        #for w in self.current_weights:
        #    print(w.shape)

        total_size = np.sum(client_sizes)

        for c in range(len(client_weights)):
            for i in range(len(new_weights)):
                new_weights[i] += client_weights[c][i] * client_sizes[c] / total_size
        self.current_weights = new_weights        

    def aggregate_loss_accuracy(self, client_losses, client_accuracies, client_sizes):
        import numpy as np
        total_size = np.sum(client_sizes)
        # weighted sum
        aggr_loss = np.sum(client_losses[i] / total_size * client_sizes[i]
                for i in range(len(client_sizes)))
        aggr_accuraries = np.sum(client_accuracies[i] / total_size * client_sizes[i]
                for i in range(len(client_sizes)))
        return aggr_loss, aggr_accuraries

    # cur_round coule be None
    def aggregate_train_loss_accuracy(self, client_losses, client_accuracies, client_sizes, cur_round):
        cur_time = int(round(time.time())) - self.training_start_time
        aggr_loss, aggr_accuraries = self.aggregate_loss_accuracy(client_losses, client_accuracies, client_sizes)
        #print(cur_round)
        #print(cur_time)
        #print(aggr_loss)
        self.train_losses += [[cur_round, cur_time, aggr_loss]]
        self.train_accuracies += [[cur_round, cur_time, aggr_accuraries]]
        with open('stats.txt', 'w') as outfile:
            json.dump(self.get_stats(), outfile)
        return aggr_loss, aggr_accuraries

    # cur_round coule be None
    def aggregate_valid_loss_accuracy(self, client_losses, client_accuracies, client_sizes, cur_round):
        cur_time = int(round(time.time())) - self.training_start_time
        aggr_loss, aggr_accuraries = self.aggregate_loss_accuracy(client_losses, client_accuracies, client_sizes)
        self.valid_losses += [[cur_round, cur_time, aggr_loss]]
        self.valid_accuracies += [[cur_round, cur_time, aggr_accuraries]]
        with open('stats.txt', 'w') as outfile:
            json.dump(self.get_stats(), outfile)
        return aggr_loss, aggr_accuraries

    def get_stats(self):
        return {
            "train_loss": self.train_losses,
            "valid_loss": self.valid_losses,
            "train_accuracy": self.train_accuracies,
            "valid_accuracy": self.valid_accuracies
        }
        

class GlobalModel_VGG(GlobalModel):
    def __init__(self):
        super(GlobalModel_VGG, self).__init__()

    def build_model(self):
        # ~5MB worth of parameters
        from keras.models import Sequential
        from tensorflow.keras.applications import VGG16
        from keras.layers import GlobalMaxPooling2D,Input,Conv2D, MaxPooling2D, Flatten, Dense
        from keras.models import Model
        import tensorflow as tf
        import keras

        # IMAGE_WIDTH, IMAGE_HEIGHT = (224, 224)

        image_shape = (300,300,3)
        base_model = VGG16(
            input_shape=image_shape,
            include_top=False,
            weights='imagenet'
        )

        for layer in base_model.layers:
            layer.trainable = False

        n_labels = 2 # bc we are starting with this but there are actually 500

        inputs = Input(image_shape)
        x = base_model(inputs)

        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        # x = tf.keras.layers.Dense(2, name='dense_logits1',kernel_initializer='random_normal',bias_initializer='zeros')(x)
        # x = Flatten()(x)
        output = tf.keras.layers.Dense(2, activation='softmax', name='dense_logits2',kernel_initializer='random_normal',bias_initializer='zeros')(x)
        # x = Conv2D(1, 3)(x)
        # x = MaxPooling2D(pool_size=(2, 2))(x)
        # x = Dense(30, activation='relu')(x)
        # x = Dense(5, activation='softmax')(x)
        # output = tf.keras.layers.Activation('sigmoid', dtype='float32', name='predictions')(x)
        opt = tf.keras.optimizers.Adam(learning_rate=0.00001)
        model = Model(inputs= inputs, outputs=output)
        # model.summary()
        # model.compile(loss=keras.losses.categorical_crossentropy,
        #             optimizer=opt,
        #             metrics=['accuracy'])

        return model
        
# Federated Averaging algorithm with the server pulling from clients

class FLServer(object):
    ROUNDS_BETWEEN_VALIDATIONS = 2

    def __init__(self, global_model, host, port, bootaddr):
        self.global_model = global_model()

        self.host = host
        self.port = port
        import uuid
        self.model_id = str(uuid.uuid4())

        #####
        # training states
        self.current_round = -1  # -1 for not yet started
        self.current_round_client_updates = []
        self.eval_client_updates = []
        #####
      
        self.starttime = 0
        self.endtime = 0

        self.lib = cdll.LoadLibrary('./libp2p_peer.so')
        self.lib.Fedcomp_GR.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_byte]
        self.lib.Init_p2p.restype = ctypes.c_char_p

        self.register_handles()

        self.lib.Init_p2p(self.host.encode('utf-8'),int(self.port), int(1), bootaddr.encode('utf-8'))

        self.lib.Bootstrapping(bootaddr.encode('utf-8'))


    def register_handles(self):
 
        def on_req_global_model(data):
            print("on request global model\n")
            metadata = {
                    'model_json': self.global_model.model.to_json(),
                    'model_id': self.model_id,
                    'min_train_size':1200,
                    'data_split':(0.6, 0.3, 0.1), # train, test, valid
                    'epoch_per_round':1,
                    'batch_size':10
            }
            sdata = obj_to_pickle_string(metadata)

            self.lib.SendGlobalModel(sdata, sys.getsizeof(sdata))

        def on_client_update_done_publisher(data):
            print('on client_update_done_publisher\n')
            data = pickle_string_to_obj(data)

            #TODO : current_round should be passed from FL server

            # gather updates from members and discard outdated update
            self.current_round_client_updates += [data]
            self.current_round_client_updates[-1]['weights'] = pickle_string_to_obj(data['weights'])

            self.global_model.update_weights(
                [x['weights'] for x in self.current_round_client_updates],
                [x['train_size'] for x in self.current_round_client_updates],
            )
            aggr_train_loss, aggr_train_accuracy = self.global_model.aggregate_train_loss_accuracy(
                [x['train_loss'] for x in self.current_round_client_updates],
                [x['train_accuracy'] for x in self.current_round_client_updates],
                [x['train_size'] for x in self.current_round_client_updates],
                self.current_round
            )

            #filehandle = open("run.log", "a")
            #filehandle.write("aggr_train_loss"+str(aggr_train_loss)+'\n')
            #filehandle.write("aggr_train_accuracy"+str(aggr_train_accuracy)+'\n')
            #filehandle.close()

            if 'valid_loss' in self.current_round_client_updates[0]:
                aggr_valid_loss, aggr_valid_accuracy = self.global_model.aggregate_valid_loss_accuracy(
                [x['valid_loss'] for x in self.current_round_client_updates],
                [x['valid_accuracy'] for x in self.current_round_client_updates],
                [x['valid_size'] for x in self.current_round_client_updates],
                self.current_round
            )
            #filehandle = open("run.log", "a")
            #filehandle.write("aggr_valid_loss"+str(aggr_valid_loss)+'\n')
            #filehandle.write("aggr_valid_accuracy"+str(aggr_valid_accuracy)+'\n')
            #filehandle.close()
                   
            self.global_model.prev_train_loss = aggr_train_loss

        def on_client_eval_done_publisher(data):
            print ('on client_eval_done_publisher\n')
            data = pickle_string_to_obj(data)
            #filehandle = open("run.log", "a")
            #filehandle.write ('on client_eval' + str(sys.getsizeof(data))+'\n')
            #filehandle.close()

            if self.eval_client_updates is None:
                return

            self.eval_client_updates += [data]

            aggr_test_loss, aggr_test_accuracy = self.global_model.aggregate_loss_accuracy(
                [x['test_loss'] for x in self.eval_client_updates],
                [x['test_accuracy'] for x in self.eval_client_updates],
                [x['test_size'] for x in self.eval_client_updates],
            );
            #filehandle = open("run.log", "a")
            #filehandle.write("\naggr_test_loss"+str(aggr_test_loss)+'\n')
            #filehandle.write("aggr_test_accuracy"+str(aggr_test_accuracy)+'\n')
            #filehandle.write("== done ==\n")
            print("== done ==\n")
            print("\nfinal aggr_test_loss"+str(aggr_test_loss)+'\n')
            print("final aggr_test_accuracy"+str(aggr_test_accuracy)+'\n')
            #self.end = int(round(time.time()))
            #filehandle.write("end : " + str(self.end)+'\n')
            #print("end : " + str(self.end)+'\n')
            #filehandle.write("diff : " + str(self.end - self.starttime)+'\n')
            #print("diff : " + str(self.end - self.starttime)+'\n')
            #filehandle.write("== done ==\n")
            #filehandle.close()
            self.eval_client_updates = None  # special value, forbid evaling again

        global onreqglobalmodel
        onreqglobalmodel = FUNC(on_req_global_model)
        fnname="on_reqglobalmodel"
        self.lib.Register_callback(fnname.encode('utf-8'),onreqglobalmodel)

        global onclientupdatedonepublisher
        onclientupdatedonepublisher = FUNC(on_client_update_done_publisher)
        fnname="on_clientupdatedone_publisher"
        self.lib.Register_callback(fnname.encode('utf-8'),onclientupdatedonepublisher)

        global onclientevaldonepublisher
        onclientevaldonepublisher = FUNC(on_client_eval_done_publisher)
        fnname="on_clientevaldone_publisher"
        self.lib.Register_callback(fnname.encode('utf-8'),onclientevaldonepublisher)
 
if __name__ == '__main__':
    server = FLServer(GlobalModel_VGG, sys.argv[1], sys.argv[2], sys.argv[3])
    filehandle = open("run.log", "w")
    filehandle.write("listening on " + str(sys.argv[1]) + ":" + str(sys.argv[2]) + "\n");
    filehandle.close()
    server.lib.Input()
