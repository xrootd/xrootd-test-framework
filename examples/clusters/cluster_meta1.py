from XrdTest.ClusterUtils import Cluster, Network, Host

def getCluster():
    cluster = Cluster()
    
    cluster.name = 'cluster_meta1'
    network_name = 'net_meta1'

    #---------------------------------------------------------------------------
    # Network definition
    #---------------------------------------------------------------------------
    net = Network()
    net.bridgeName = 'virbr92'
    net.name = network_name
    net.ip = '192.168.123.1'
    net.netmask = '255.255.255.0'
    net.DHCPRange = ('192.168.123.2', '192.168.123.254')

    h1 = Host('slave1', '192.168.123.2', '52:54:00:E0:FD:17', \
              net="net_meta1")
#    h2 = Host('slave2.xrd.test', '192.168.123.3', '52:54:00:E1:FD:17', \
#              net="net_meta1")
#    h3 = Host('man2.xrd.test', '192.168.123.4', '52:54:00:E2:FD:17', \
#              net="net_meta1")
#    h4 = Host('srv1.xrd.test', '192.168.123.5', '52:54:00:E3:FD:17', \
#              net="net_meta1")
#    #h5 = Host('srv2.xrd.test', '192.168.123.6', '52:54:00:E4:FD:17')
#    h6 = Host('srv3.xrd.test', '192.168.123.6', '52:54:00:E5:FD:17', \
#              net="net_meta1")
##   h7 = Host('srv4.xrd.test', '192.168.123.7', '52:54:00:E6:FD:17')
#    h8 = Host('client.xrd.test', '192.168.123.8', '52:54:00:E7:FD:17', \
#              net="net_meta1")

    hosts = [h1]
    net.addHosts(hosts)
    cluster.network = net

    #---------------------------------------------------------------------------
    # Cluster machines definitions
    #---------------------------------------------------------------------------
    cluster.defaultHost.diskImage = '/var/lib/libvirt/images/xrd_testslave_ref.img'
    cluster.defaultHost.arch = 'x86_64'
    cluster.defaultHost.ramSize = '1048576'
    cluster.defaultHost.net = network_name

    cluster.addHosts(hosts)
    return cluster
