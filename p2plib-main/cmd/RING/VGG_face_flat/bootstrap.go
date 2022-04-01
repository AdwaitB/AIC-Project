package main

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"github.com/theued/p2plib"
	"github.com/theued/p2plib/dual"
	"io"
	"os"
	"strings"
	"time"
	"net"
	"go.uber.org/zap"
	"encoding/json"
	"strconv"
	"math/rand"
	"runtime"
)

// printedLength is the total prefix length of a public key associated to a chat users ID.
const printedLength = 8

var (
        node *p2plib.Node
	overlay *dual.Protocol
	events dual.Events
	max_peers=50
	discoverInterval = 10 //sec
	num_fail_download = 0
)

type chatMessage struct {
	Opcode byte
	Contents []byte
}

func (m chatMessage) Marshal() []byte {
	return append([]byte{m.Opcode}, m.Contents...)
}

func unmarshalChatMessage(buf []byte) (chatMessage, error) {
	return chatMessage{Opcode: buf[0], Contents: buf[1:]}, nil
}

// check panics if err is not nil.
func check(err error) {
	if err != nil {
		panic(err)
	}
}

func choose(peers []p2plib.ID, entry []string) ([]p2plib.ID, []p2plib.ID) {
    var first []p2plib.ID
    var second []p2plib.ID

    //fmt.Printf(" need to choose : %v \n",entry)
    for _, eid := range entry {
        for _, id := range peers {
            if id.ID.String() == eid {
                first = append(first,id)
            }else{
                second = append(second,id)
            }
        }
    }
    //fmt.Printf(" after choose first : %v \n",first)
    return first, second
}

func remove(peers []p2plib.ID, entry []string) []p2plib.ID {
    //fmt.Printf(" need to remove : %v \n",entry)
    removed := 0
    for _, eid := range entry {
        for k, id := range peers {
            if id.ID.String() == eid {
                peers[k] = peers[len(peers)-1]
                removed++
            }
        }
        peers = peers[:len(peers)-removed]
        removed=0
    }
    //fmt.Printf(" after remove : %v \n",peers)
    return peers
}

func findRandMember(push int, len_peers int, peers []p2plib.ID) ([]p2plib.ID,[]p2plib.ID) {
    //fmt.Printf(" findRandMember len_peers:%d\n",len_peers)
    rnums := make(map[int]int, 0)
    for {
        rnum := rand.Intn(len_peers)
        rnums[rnum]=rnum
        if len(rnums) == push{
            break
        }
    }

    pushlist := make([]p2plib.ID, 0)
    pulllist := make([]p2plib.ID, 0)
    for k, id := range peers {
        if _, ok := rnums[k]; ok {
            pushlist = append(pushlist, id)
        }else{
            pulllist = append(pulllist, id)
        }
    }

    return pushlist, pulllist
}

func gossip_BC(uuid []byte, data []byte, avoid []string, msgtype byte, targetid p2plib.ID) {
     peers := overlay.Table_bc().Peers()
     if len(avoid) > 0 {
          peers = remove(overlay.Table_bc().Peers(),avoid)
     }

     len_peers := len(peers)
     if len_peers == 0 {
	 //fmt.Printf("gossip_BC: no peers to broadcast len_peers:%d\n",len_peers)
	 return
     }

     //push := math.Sqrt(float64(len_peers))
     push := len_peers/2
     if push == 0 {
         push = 1
     }
     pushlist, pulllist := findRandMember(push, len_peers, peers)
     //fmt.Printf("gossip_BC : pushlist:%d, pulllist:%d\n",len(pushlist), len(pulllist))

     list := make([]string,0)
     for _, id := range pushlist {
	 list = append(list,id.ID.String())
     }
     list = append(list,avoid...)

     listdata, _ := json.Marshal(list)
     length := len(listdata)

     for _, id := range pushlist {
	 sendmsg(uuid, data, length, listdata, id, dual.OP_GOSSIP_PUSH, msgtype, targetid)
     }

     for _, id := range pulllist {
	 sendmsg(uuid, data, length, listdata, id, dual.OP_GOSSIP_PULL_REQ, msgtype, targetid)
     }
}

func sendmsg(uuid []byte, data []byte, length int, listdata []byte, id p2plib.ID, opcode byte, msgtype byte, targetid p2plib.ID) {
         ctx, cancel := context.WithCancel(context.Background())
	 err := node.SendMessage(ctx, id.Address, dual.GossipMessage{Opcode: opcode, Type: msgtype, UUID: uuid, Count: uint32(length), TargetID: targetid, List: listdata, Contents: data })
         //fmt.Printf("Send message to %s(%s)\n",id.Address,id.ID.String()[:printedLength],)
         cancel()
         if err != nil {
              fmt.Printf("Failed to send message to %s(%s). Skipping... [error: %s]\n",
                         id.Address,
                         id.ID.String()[:printedLength],
                         err,
              )
              //continue
         }
}

func requestDownload(uuid []byte, preferred []string) (dual.DownloadMessage, bool) {
     var firstcontact []p2plib.ID
     var secondcontact []p2plib.ID
     peers := overlay.Table_bc().Peers()
     if len(preferred) > 0 {
          // choose preferred ones first. preferred ones are firstcontact 
         firstcontact, secondcontact = choose(overlay.Table_bc().Peers(),preferred)
     }else{
	 firstcontact = peers
     }

     for _, id := range firstcontact {
	 // if I receive item during this search, I stop the search.
	 if overlay.HasSeenPush(node.ID(), uuid) || overlay.HasUUID(uuid) { // check if we have received
             //fmt.Printf("I receive item. Stop Searching\n")
             return overlay.GetItem(), true
         }
         ctx, cancel := context.WithCancel(context.Background())
         //ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	 /*
         fmt.Printf("Send pull message to %s(%s) and Waiting..\n",
                    id.Address,
                    id.ID.String()[:printedLength],
         )
	 */
         obj, err := node.RequestMessage(ctx, id.Address, dual.Request{UUID: uuid})
                  cancel()
         if err != nil {
              fmt.Printf("Failed to send message to %s(%s). Skipping... [error: %s]\n",
                         id.Address,
                         id.ID.String()[:printedLength],
                         err,
              )
              continue
         }
         switch msg := obj.(type) {
              case dual.DownloadMessage:
                   msg, ok := obj.(dual.DownloadMessage)
                   if !ok {
                       fmt.Printf("download message broken\n")
                       break
                   }
                   //fmt.Printf("firstcontact download hit\n")
                   return msg, true
              case dual.Deny:
                   //fmt.Printf("firstcontact download not hit\n")
         }
     }

     for _, id := range secondcontact {
	 // if I receive item during this search, I stop the search.
	 if overlay.HasSeenPush(node.ID(), uuid) || overlay.HasUUID(uuid) { // check if we have received
             //fmt.Printf("I receive item. Stop Searching\n")
             return overlay.GetItem(), true
         }
         ctx, cancel := context.WithCancel(context.Background())
         //ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	 /*
         fmt.Printf("Send pull message to %s(%s) and Waiting..\n",
                    id.Address,
                    id.ID.String()[:printedLength],
         )
	 */
         obj, err := node.RequestMessage(ctx, id.Address, dual.Request{UUID: uuid})
                  cancel()
         if err != nil {
              fmt.Printf("Failed to send message to %s(%s). Skipping... [error: %s]\n",
                         id.Address,
                         id.ID.String()[:printedLength],
                         err,
              )
              continue
         }
         switch msg := obj.(type) {
              case dual.DownloadMessage:
                   msg, ok := obj.(dual.DownloadMessage)
                   if !ok {
                       fmt.Printf("download message broken\n")
                       break
                   }
                   //fmt.Printf("download hit\n")
                   return msg, true
              case dual.Deny:
                   //fmt.Printf("secondcontact download not hit\n")
         }
     }
     return dual.DownloadMessage{}, false
}

func on_recv_gossip_push(msg dual.GossipMessage, ctx p2plib.HandlerContext) {
    //fmt.Printf("onRecvGossipPush: OP_GOSSIP_PUSH RECEIVE ITEM count:%d\n",msg.Count)

    list := make([]string,0)
/*
    // list contains pushed ones. So, it is an avoid list to push receiver
    if msg.Count != 0{
        err := json.Unmarshal(msg.List, &list)
        if err != nil {
            fmt.Printf("Error on decode process: %v\n", err)
        }
	//fmt.Println(list)
    }
*/
    // send push and pull req
    list = append(list,ctx.ID().ID.String())
    gossip_BC(msg.UUID, msg.Contents, list, msg.Type, p2plib.ID{})
}

func on_recv_gossip_pullreq(msg dual.GossipMessage, ctx p2plib.HandlerContext) {
    //fmt.Printf("OnRecvGossipPullReq: OP_GOSSIP_PULL_REQ count:%d\n",msg.Count)

    //go func() {
	// list contains pushed ones. So, it is a perferred list to pull req receiver
        list := make([]string,0)
	/*
        if msg.Count != 0{
            err := json.Unmarshal(msg.List, &list)
            if err != nil {
                fmt.Printf("Error on decode process: %v\n", err)
            }
	    //fmt.Println(list)
        }
	*/

        maxtry := 10
        i := 0
        for i < maxtry {
            // RequestMessage to download data
            dmsg, rst := requestDownload(msg.UUID, list)

            if rst {
                //fmt.Printf("Got Download RECEIVE ITEM\n")
                // save item for incoming pull request
                overlay.SetItem(dmsg)
                overlay.SetUUID(dmsg.UUID)

                // send push and pull req
                //list = append(list,node.ID().ID.String())
                gossip_BC(msg.UUID, msg.Contents, list, msg.Type,  p2plib.ID{})

	        return
            }else{
                //fmt.Printf("fail to download.\n")
	        time.Sleep(300 * time.Millisecond)
            }
            i++
         }
    //}()
}

func init_p2p(host string, port int, publicIP string){
        var err error

	//fmt.Printf("host : %s port : %d \n",host,port)

        logger, _ := zap.NewProduction()
	// Create a new configured node.
	node, err = p2plib.NewNode(
		p2plib.WithNodeBindHost(net.ParseIP(host)),
		p2plib.WithNodeBindPort(uint16(port)),
		p2plib.WithNodeAddress(publicIP),
		p2plib.WithNodeMaxRecvMessageSize(1<<24), //16MB
		p2plib.WithNodeMaxInboundConnections(1000),
                p2plib.WithNodeMaxOutboundConnections(1000),
		p2plib.WithNodeLogger(logger),
	)
	check(err)

	// Register the chatMessage Go type to the node with an associated unmarshal function.
        node.RegisterMessage(chatMessage{}, unmarshalChatMessage)

	// Instantiate dual.
	events = dual.Events{
	        OnPeerAdmitted_bc: func(id p2plib.ID) {
	                fmt.Printf("bootstrap : a new peer %s(%s).\n", id.Address, id.ID.String()[:printedLength])
	        },
		OnPeerEvicted: func(id p2plib.ID) {
			fmt.Printf("Forgotten a peer %s(%s).\n", id.Address, id.ID.String()[:printedLength])
		},
		// gossip messaging
                OnRecvGossipPush: on_recv_gossip_push,
                OnRecvGossipPullReq: on_recv_gossip_pullreq,
	}

	overlay = dual.New(dual.WithProtocolEvents(events),
	                   dual.WithProtocolMaxNeighborsBC(max_peers),)

	// Bind dual to the node.
	node.Bind(overlay.Protocol())

        //fmt.Printf("start listen\n")
	// Have the node start listening for new peers.
	check(node.Listen())

	// Print out the nodes ID and a help message comprised of commands.
	//help(node)

        //go startPeriodicDiscover()

        fmt.Printf("init done\n")
}

func bootstrapping(serveraddr string) {
        //fmt.Printf("start bootstrap %s\n",serveraddr)
	// Ping nodes to initially bootstrap and discover peers from.
	bootstrap(serveraddr)

        //fmt.Printf("start discover\n")
	// Attempt to discover peers if we are bootstrapped to any nodes.
	discover(overlay)
	//overlay.Peers_bc()

}

func startPeriodicDiscover() {
        var len_peers int

	for {
	    time.Sleep(time.Duration(discoverInterval) * time.Second)
            len_peers = len(overlay.Table_bc().Peers())
	    if len_peers < max_peers {
	        ids := overlay.DiscoverRandom(true)
	        var str []string
	        for _, id := range ids {
		    str = append(str, fmt.Sprintf("%s(%s)", id.Address, id.ID.String()[:printedLength]))
	        }
/*
	        if len(ids) > 0 {
		    fmt.Printf("Discovered %d peer(s): [%v]\n", len(ids), strings.Join(str, ", "))
	        } else {
		    fmt.Printf("Did not discover any peers.\n")
	        }
*/
	    }
	}
}

func Input() {
	r := bufio.NewReader(os.Stdin)

	for {
		buf, _, err := r.ReadLine()
		if err != nil {
			if errors.Is(err, io.EOF) {
				return
			}

			check(err)
		}

		line := string(buf)
		if len(line) == 0 {
			continue
		}

                fmt.Printf(line)
		chat(line)
	}
}

// help prints out the users ID and commands available.
func help(node *p2plib.Node) {
	fmt.Printf("Your ID is %s(%s). Type '/discover' to attempt to discover new "+
		"peers, or '/peers' to list out all peers you are connected to.\n",
		node.ID().Address,
		node.ID().ID.String()[:printedLength],
	)
}

// bootstrap pings and dials an array of network addresses which we may interact with and  discover peers from.
func bootstrap(addr string) {
                fmt.Printf("run bootstrap on %s\n", addr)
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		_, err := node.Ping(ctx, addr)
		cancel()

		if err != nil {
			fmt.Printf("Failed to ping bootstrap node (%s). Skipping... [error: %s]\n", addr, err)
		}
}

// discover uses Kademlia to discover new peers from nodes we already are aware of.
func discover(overlay *dual.Protocol) {
	ids := overlay.DiscoverLocal(true)

	var str []string
	for _, id := range ids {
		str = append(str, fmt.Sprintf("%s(%s)", id.Address, id.ID.String()[:printedLength]))
	}
/*
	if len(ids) > 0 {
		fmt.Printf("Discovered %d peer(s): [%v]\n", len(ids), strings.Join(str, ", "))
	} else {
		fmt.Printf("Did not discover any peers.\n")
	}
*/
}

func chat(line string) {
	switch line {
	case "/discover":
		discover(overlay)
		return
	case "/peers_bc":
		overlay.Peers_bc() // show backbone overlay routing table
		return
	default:
	}

	if strings.HasPrefix(line, "/") {
		help(node)
		return
	}

}

func main() {
        // args[0] = host IP 
        // args[1] = host Port 
	// args[2] = host Public Address(IP:Port) if host IP is private and behind NAT
        runtime.GOMAXPROCS(runtime.NumCPU())
        args := os.Args[1:]
        port, err := strconv.Atoi(args[1])
	if err != nil {
	    // Add code here to handle the error!
	}

	if len(args) > 2 {
            init_p2p(string(args[0]), port, string(args[2]))
        }else{
            init_p2p(string(args[0]), port, "")
        }

        // block here
        Input() // simulation many bench on the same physical node causes error on stdin
}


