import sys, json, time, conf
from twisted.internet.protocol import Protocol, ClientFactory
from twisted.internet.protocol import Factory
from twisted.protocols.basic import LineReceiver
from twisted.web.client import getPage
from twisted.python import log
from twisted.application import service, internet
from twisted.internet import reactor


serverAssociations = {
    'Alford': ['Hamilton', 'Welsh'],
    'Ball': ['Holiday', 'Welsh'],
    'Hamilton': ['Alford', 'Holiday'],
    'Holiday': ['Ball', 'Hamilton'],
    'Welsh': ['Alford', 'Ball']
}


def checkFloat(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def checkInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

def checkGPS(s):
    s = s.replace('+',' ').replace('-', ' ').split()
    if len(s) == 2:
        return checkFloat(s[0]) and checkFloat(s[1])
    else:
        return False

class ProxyHerd(LineReceiver):

    def __init__(self, factory):
        self.factory = factory 
        self.serverID = factory.serverID
        self.log = self.factory.log

    def connectionMade(self):
        self.factory.numProtocols = self.factory.numProtocols + 1
        if not self.log.closed:
            self.log.write("A connection made! There are currently %d open connections.\n" %(self.factory.numProtocols,))

    def connectionLost(self, reason):
        self.factory.numProtocols = self.factory.numProtocols - 1
        if not self.log.closed:
            self.log.write("A connection lost. There are cuurently %d open connections.\n" %(self.factory.numProtocols,))

    def lineReceived(self, data):
        splitData = data.split()
        if len(splitData) > 0:
            self.log.write("Received Request:\n {0}\n".format(data))
            if splitData[0] == "IAMAT" and len(splitData) == 4:
                self.handleIAMAT(data)
            elif splitData[0] == "WHATSAT" and len(splitData) == 4:
                self.handleWHATSAT(data)
            elif splitData[0] == "AT" and len(splitData) == 6:
                self.handleAT(data)
            else:
                self.respondToERROR(data)

    def handleIAMAT(self, request):
        splitData = request.split()
        clientID = splitData[1]
        GPS = splitData[2]
        requestTime = splitData[3]

        if not (checkGPS(GPS) and checkFloat(requestTime)):
            self.respondToERROR(request)
            return

        timeDiff = time.time() - float(requestTime)
        response = self.formatAtResp(self.factory.serverID, timeDiff, clientID, GPS, requestTime)
        self.updateClientInfo(response, clientID, self.factory.serverID, timeDiff, GPS, requestTime)

    def handleWHATSAT(self, request):
        splitData = request.split()
        clientID = splitData[1]

        #check if all arguments are valid
        if not (checkInt(splitData[2]) and checkInt(splitData[3])):
            self.respondToERROR(request)
            return

        radius = int(splitData[2])*1000
        maxInfoNum = int(splitData[3])

        if clientID not in self.factory.clients:
            self.respondToERROR(request)
            return

        if radius > 50000 or maxInfoNum > 20:
            self.respondToERROR(request)
            return

        GPS = self.factory.clients[clientID][2].replace("-", " -").replace("+", " +").split()

        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={longitude},{latitude}&radius={radius}&&key={key}".format(
            longitude = GPS[0], latitude = GPS[1], radius = radius, key = conf.API_KEY)
        d = getPage(url).addCallback(self.formatGoogleResp, maxInfoNum = maxInfoNum, clientID = clientID)
        d.addErrback(self.respondToERROR, data = request)

    def handleAT(self, request):
        splitData = request.split()
        serverID = splitData[1]
        timeDiff = splitData[2]
        clientID = splitData[3]
        GPS = splitData[4]
        requestTime = splitData[5]
        #check if all arguments are valid
        if not (serverID in conf.PORT_NUM and checkFloat(timeDiff[1:]) and checkGPS(GPS) and checkFloat(requestTime)):
            self.respondToERROR(request)
            return

        self.updateClientInfo(request, clientID, serverID, timeDiff, GPS, requestTime)

    def updateClientInfo(self, response, clientID, serverID, timeDiff, GPS, requestTime):
        #update and flood the client info only if the given client info is the newest, to avoid infinitely flooding
        if clientID not in self.factory.clients or requestTime > self.factory.clients[clientID][3]:
            self.factory.clients[clientID] = serverID, timeDiff, GPS, requestTime
            self.sendLine(response)
            if not self.log.closed:
                self.log.write("Respond:\n{0}\n".format(response))
            if not self.log.closed:
                self.log.write("Updated client {0}'s info\n".format(clientID))
            self.flood(response)

    def respondToERROR(self, data):
        self.sendLine("? {0}".format(data))
        self.log.write("Respond:\n? {0}\n".format(data))

    def formatAtResp(self, serverID, timeDiff, clientID, GPS, requestTime):
        if timeDiff > 0: 
            timeDiff = "+" + str(timeDiff)
        else: 
            timeDiff = str(timeDiff)
        return "AT {0} {1} {2} {3} {4}".format(serverID, timeDiff, clientID, GPS, requestTime)

    def formatGoogleResp(self, data, maxInfoNum, clientID):
        rawData = json.loads(data)
        rawData["results"] = rawData["results"][:maxInfoNum]
        JSONData = json.dumps(rawData, indent = 4, separators = (',', ': '))
        clientInfo = self.factory.clients[clientID]
        AtResp = self.formatAtResp(clientInfo[0], clientInfo[1], clientID, clientInfo[2], clientInfo[3])
        self.sendLine("{0}\n{1}".format(AtResp, JSONData))
        self.log.write("Respond:\n{0}\n{1}\n".format(AtResp, JSONData))

    def flood(self, data):
        for neighbor in serverAssociations[self.factory.serverID]:
            reactor.connectTCP("localhost", conf.PORT_NUM[neighbor], FloodFactory(data, neighbor, self.log))
            self.log.write("Try to flood the info to Server {0}\n".format(neighbor))


class ProxyHerdFactory(Factory):

    def __init__(self, serverID):
        self.numProtocols = 0
        self.serverID = serverID
        #map clientID to serverID, timediff, GPS, requestTime
        self.clients = {}
        self.file = serverID + ".log"

    def buildProtocol(self, addr):
        return ProxyHerd(self)

    def startFactory(self):
        self.log = open(self.file, "a")
        self.log.write("Server {0} Started\n".format(self.serverID))

    def stopFactory(self):
        self.log.write("Server {0} Shut Down\n\n".format(self.serverID))
        self.log.close()

#build a new protocol which will only send the flood message to the neighbor servers
class Flood(LineReceiver):
    def __init__(self, factory, data):
        self.factory = factory
        self.data = data

    def connectionMade(self):
        self.sendLine(self.data)
        self.factory.log.write("Flooded the info to {0}\n".format(self.factory.targetID))
        self.transport.loseConnection()


class FloodFactory(ClientFactory):
    def __init__(self, data, targetID, log):
        self.data = data
        self.log = log
        self.targetID = targetID

    def buildProtocol(self, addr):
        return Flood(self, self.data)

    def clientConnectionFail(self, connector, reason):
        self.log.write("Failed to flood the info to {0}\n".format(self.targetID))


def main():
    if len(sys.argv) != 2:
        print "usage: server serverID"
        exit(1)

    port_num = conf.PORT_NUM[sys.argv[1]]
    reactor.listenTCP(port_num, ProxyHerdFactory(sys.argv[1]))
    reactor.run()


if __name__ == "__main__": main()

