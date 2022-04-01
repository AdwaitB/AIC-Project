# If you use run.sh to launch many peer nodes, you should comment below line
#client.lib.Input() in peer.py
#Input() in peer.go

NUM_NODES=16
START_ADDR=130.127.133.15
START_PORT=8000
SERVER_ADDR=130.127.133.15
SERVER_PORT=9999


for i in `seq 1 $NUM_NODES`
do
    go run peer.go $START_ADDR $(($i + $START_PORT)) $SERVER_ADDR:$SERVER_PORT 50 0 | tee node$(($i + $START_PORT)).log 2>&1 &
    sleep 1
done

