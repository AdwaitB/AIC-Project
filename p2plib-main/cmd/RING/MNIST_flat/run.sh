NUM_NODES=7
START_ADDR=130.127.133.26
START_PORT=8000
SERVER_ADDR=130.127.133.26
SERVER_PORT=9999

for i in `seq 1 $NUM_NODES`
do
    #python3 peer.py $START_ADDR $(($i + $START_PORT)) $SERVER_ADDR:$SERVER_PORT | tee node$(($i + $START_PORT)).log 2>&1 &
    python3 peer.py $START_ADDR $(($i + $START_PORT)) $SERVER_ADDR:$SERVER_PORT &
    sleep 1
done
