from XrdTest.ClusterUtils import Cluster, Network, Host

def getCluster():
    cluster = Cluster()
    #---------------------------------------------------------------------------
    # Global names
    # Used commonly in network definition and hosts definition
    #---------------------------------------------------------------------------
    cluster.name = 'cluster_remote'
    network_name = 'net1_xrd'
    
    #---------------------------------------------------------------------------
    # Network definition
    #---------------------------------------------------------------------------
    net = Network()
    net.bridgeName = 'virbr91'
    net.name = network_name
    net.ip = '192.168.127.1'
    net.netmask = '255.255.255.0'
    net.DHCPRange = ('192.168.127.2', '192.168.127.254')

    h1 = Host('slave1', '192.168.127.3', "52:54:00:65:44:65",
              ramSize='1048576', arch='x86_64', net="net1_xrd")
    h2 = Host('slave2', '192.168.127.4', "52:54:00:65:44:66",
              ramSize='1048576', arch='x86_64', net="net1_xrd")
    h3 = Host('slave3', '192.168.127.5', "52:54:00:65:44:67",
              ramSize='1048576', arch='x86_64', net="net1_xrd")
#    h4 = Host('slave4', '192.168.127.6', "52:54:00:65:44:68",
#              ramSize='1048576', arch='x86_64', net="net1_xrd")
 
    hosts = [h1, h2, h3]
    net.addHosts(hosts)
    cluster.network = net
    cluster.addHosts(hosts)
    
    cluster.defaultHost.diskImage = '/var/lib/libvirt/images/xrd_testslave_ref.img'
    cluster.defaultHost.arch = 'x86_64'
    cluster.defaultHost.ramSize = '524288'
    cluster.defaultHost.net = network_name

    return cluster

