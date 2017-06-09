# Proxy_Herd
This is a proxy herd consists of 5 servers with the following name and port number:

| Name    | Port  |
|---------|------:|
|Alford   | 12810 |
|Ball     | 12811 |
|Hamilton | 12812 |
|Holiday  | 12813 |
|Welsh    | 12814 |

Start.sh will start all five servers.

Each server will accept TCP connections from clients that emulate mobile devices with IP addresses and DNS names.

Client can send request of the forms: 
```
IAMAT clientID longitude altitude
WHATSAT clientID radius numberOfPlaces
```
If IAMAT request received, server will update the location of clientID to the given GPS location and flood this information to its neighbor servers. 

If WHATSAT request received, server will consult the GOOGLE PLACES API to get the restaurant information around the clientID within the given radius, and pass this information back to client.
