from ClusterManager import Cluster, Network, Host

def getCluster():
    cluster = Cluster()
    #---------------------------------------------------------------------------
    # Global names
    # Used commonly in network definition and hosts definition
    #---------------------------------------------------------------------------
    cluster.name = 'cluster_remote'
    cluster.defaultHost.diskImage = '/var/tmp/virt-images/lt_slc5_refslave.img'

    network_name = 'net1_xrd'
    #---------------------------------------------------------------------------
    # Network definition
    #---------------------------------------------------------------------------
    net = Network()
    net.bridgeName = 'virbr90'
    net.name = network_name
    net.ip = '192.168.130.1'
    net.netmask = '255.255.255.0'
    net.DHCPRange = ('192.168.130.2', '192.168.130.254')

    h1 = Host('new1', '192.168.130.2', "52:54:00:65:44:69",
              ramSize='524288', arch='x86_64', net="net1_xrd")
    h2 = Host('new2', '192.168.130.2', "52:54:00:65:44:70",
              net="net1_xrd", diskImage="/var/tmp/virt-images/non-existsing")

    net.addHosts([h1, h2])
    cluster.network = net
    cluster.addHosts([h1, h2])

    return cluster

