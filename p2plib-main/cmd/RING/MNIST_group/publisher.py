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
        import numpy as np
        new_weights = [np.zeros(w.shape) for w in self.current_weights]
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
        

class GlobalModel_MNIST_CNN(GlobalModel):
    def __init__(self):
        super(GlobalModel_MNIST_CNN, self).__init__()

    def build_model(self):
        # ~5MB worth of parameters
        from keras.models import Sequential
        from keras.layers import Dense, Dropout, Flatten
        from keras.layers import Conv2D, MaxPooling2D
        model = Sequential()
        #model.add(Conv2D(32, kernel_size=(3, 3), #16.2MB
        model.add(Conv2D(64, kernel_size=(3, 3), #33MB
        #model.add(Conv2D(128, kernel_size=(3, 3), #68MB
        #model.add(Conv2D(256, kernel_size=(3, 3), #144MB
        #model.add(Conv2D(512, kernel_size=(3, 3), #320MB
                         activation='relu',
                         input_shape=(28, 28, 1)))
        #model.add(Conv2D(64, (3, 3), activation='relu'))
        model.add(Conv2D(128, (3, 3), activation='relu'))
        #model.add(Conv2D(256, (3, 3), activation='relu'))
        #model.add(Conv2D(512, (3, 3), activation='relu'))
        #model.add(Conv2D(1024, (3, 3), activation='relu'))
        model.add(MaxPooling2D(pool_size=(2, 2)))
        model.add(Dropout(0.25))
        model.add(Flatten())
        model.add(Dense(128, activation='relu'))
        model.add(Dropout(0.5))
        model.add(Dense(10, activation='softmax'))

        import tensorflow.keras as keras
        model.compile(loss=keras.losses.categorical_crossentropy,
                      optimizer=keras.optimizers.Adadelta(),
                      metrics=['accuracy'])
        return model

        
# Federated Averaging algorithm with the server pulling from clients

class FLServer(object):
    #MIN_NUM_WORKERS = 7 # total clients (publisher is not included here) obsolete
    #MAX_NUM_ROUNDS = 3 #obsolete
    NUM_CLIENTS_CONTACTED_PER_ROUND = 1 #obsolete #publisher doesn't command. FL server decide.
    ROUNDS_BETWEEN_VALIDATIONS = 2 #obsolete

    def __init__(self, global_model, host, port, bootaddr):
        self.global_model = global_model()

        #self.ready_client_sids = set() #obsolete
        #self.wakeup_client_sids = set() #obsolete
        #self.ready_lower_clients = 0 #obsolete
        #self.wakeup_lower_clients = 0 #obsolete

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
                    #'opcode' : "request_round",
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
            #filehandle = open("run.log", "a")
            #filehandle.write ('on client_update: datasize :' + str(sys.getsizeof(data))+'\n')

            #TODO multi client
            #filehandle.write("handle client_update", request.sid)
            #for x in data:
            #    if x != 'weights':
            #        print(x, data[x])
                    #filehandle.write (str(x)+ " " +str(data[x]) + '\n')
            #filehandle.close()

            # gather updates from members and discard outdated update
            if data['round_number'] == self.current_round:
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

            #TODO : this comment is for test
            #if self.global_model.prev_train_loss is not None and \
            #        (self.global_model.prev_train_loss - aggr_train_loss) / self.global_model.prev_train_loss < .01:
            #    # converges
            #    filehandle = open("run.log", "a")
            #    filehandle.write("converges! starting test phase..")
            #    filehandle.close()
            #    self.stop_and_eval()
            #    return
                    
            self.global_model.prev_train_loss = aggr_train_loss

            #if self.current_round >= FLServer.MAX_NUM_ROUNDS:
            #    self.stop_and_eval()
            #else:
            #    self.train_next_round()

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
 
    # Note: we assume that during training the #workers will be >= MIN_NUM_WORKERS
    def train_next_round(self):
        self.current_round += 1
        # buffers all client updates
        self.current_round_client_updates = []

        #filehandle = open("run.log", "a")
        #filehandle.write("### Round "+str(self.current_round)+"###\n")
        print("### Round "+str(self.current_round)+"###\n")
        #client_sids_selected = random.sample(list(self.ready_client_sids), FLServer.NUM_CLIENTS_CONTACTED_PER_ROUND)
        #filehandle.write("request updates to"+str(client_sids_selected)+'\n')
        #print("request updates to"+str(client_sids_selected)+'\n')
        #filehandle.close()

        metadata = {
            #'opcode': "request_update",
            'model_id': self.model_id,
            'round_number': self.current_round,
            'current_weights': obj_to_pickle_string(self.global_model.current_weights),
            'run_validation': self.current_round % FLServer.ROUNDS_BETWEEN_VALIDATIONS == 0
        }
        sdata = obj_to_pickle_string(metadata)
        self.lib.Fedcomp_GR(sdata, sys.getsizeof(sdata), OP_REQUEST_UPDATE)
        print("request_update sent\n")

    def stop_and_eval(self):
        self.eval_client_updates = []
        metadata = {
            #'opcode': "stop_and_eval",
            'model_id': self.model_id,
            'current_weights': obj_to_pickle_string(self.global_model.current_weights)
        }
        sdata = obj_to_pickle_string(metadata)
        self.lib.Fedcomp_GR(sdata, sys.getsizeof(sdata), OP_STOP_AND_EVAL)

if __name__ == '__main__':
    server = FLServer(GlobalModel_MNIST_CNN, sys.argv[1], sys.argv[2], sys.argv[3])
    filehandle = open("run.log", "w")
    filehandle.write("listening on " + str(sys.argv[1]) + ":" + str(sys.argv[2]) + "\n");
    filehandle.close()
    server.lib.Input()
