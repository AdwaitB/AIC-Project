# AIC - Decentralized Federated Learning on the Edge for Healthcare
## Two datasets (from Kaggle): 
Covid Radiography Database (13808 images)
Healthcare Provider Fraud Detection Data (5410 claims)
### To run decentralized P2P: download all files and the corresponding datasets from Kaggle
- Place dataset files into p2p/cmd/RING/VGG_face_group. The dataset directly unzips from kaggle and the folder can be copied here.
- The dataloader for Covid dataset is already loaded, but for the Fraud dataset, use peer_copy.py
- Run the bootstrap node with the following command. 
  - go run bootstrap.go 127.0.0.1 9999
  - This code was tested on goland 1.18
- Run the publisher
  -  python3 publisher.py 127.0.0.1 9000 127.0.0.1:9999
  -  The first arguement is the localhost and the port where it should run.
  -  The third arguement is the ip and port of the bootstrap node.
-  Run the peers
   -  python3 peer.py 127.0.0.1 9001 127.0.0.1:9999
   -  python3 peer.py 127.0.0.1 9002 127.0.0.1:9999
   -  python3 peer.py 127.0.0.1 9003 127.0.0.1:9999
   -  python3 peer.py 127.0.0.1 9004 127.0.0.1:9999
   -  Similar to the publisher it takes the ip to run on and the bootstrap node's ip and port.
- Now to start the running of the FL do the following.
  - Create a new project on the publisher using `/newpjt`
  - Send advertisement to all nodes using `/sendAD`. Make sure that nodes have acked this.
  - Create the groups and the tree using `/group` on the publisher.
  - Start the FL by using `/active` on the publisher.
  - This should start the Decentralized FL.
### To simulate Federated Learning: run AIC_FL.ipynb on Google Colab
- Create a new session on colab and upload the notebook AIC_FL.ipynb
- Upload kaggle.json so that data can be uploaded.
- Run the notebook. It should be able to generate most of the graph.
- Some of the graphs are generated offline by saving the results. download any excess file and save it locally in results and then run the plotter.ipynb to get the results offline.

### How to use the UI
- Download the learned model from colab and store it in `service/covid_model.h5`.
- Start the flask server from the service folder by using the following command 
  - python3 service.py -p 12000
- Use the UI `service/ui.html` to upload and predict the files.