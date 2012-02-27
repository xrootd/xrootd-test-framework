from ClusterManager import Cluster, Network, Host
from copy import copy

def getCluster():
    cluster = Cluster()
    #---------------------------------------------------------------------------
    # Global names
    # Used commonly in network definition and hosts definition
    #---------------------------------------------------------------------------
    cluster.name = 'cluster1'
    cluster.diskImage = '/data/virtual/images/lt_slc5_refslave.img'

    network_name = 'net1.xrdtest'

    host1_mac = '52:54:00:65:44:69'
    host2_mac = '52:54:00:A3:F9:73'
    host3_mac = '52:54:00:E8:FD:17'
    #---------------------------------------------------------------------------
    # Network definition
    #---------------------------------------------------------------------------
    net = Network()
    net.bridgeName = 'virbr90'
    net.name = network_name
    net.ip = '192.168.130.1'
    net.netmask = '255.255.255.0'
    net.DHCPRange = ('192.168.130.2', '192.168.130.254')

    h1 = (host1_mac, '192.168.130.2', 'new1')
    #h2 = (host2_mac, '192.168.130.3', 'new2.xrd.test')
    #h3 = (host3_mac, '192.168.130.4', 'new3.xrd.test')
    net.addHost(h1)
    #net.addHost(h2)
    #net.addHost(h3)

    cluster.network = net
    #---------------------------------------------------------------------------
    # Cluster machines definitions
    #---------------------------------------------------------------------------
    host1 = Host()
    host1.name = 'new1'
    host1.ramSize = '524288'
    host1.arch = 'x86_64'
    host1.uuid = '1fb103a6-8873-e114-a3d5-8bd89bcbac7f'
    host1.sourceNetwork = network_name
    host1.macAddress = host1_mac

    #---------------------------------------------------------------------------
    host2 = copy(host1)
    host2.name = 'new2.xrd.test'
    host2.uuid = '1fb103a6-8873-e114-a3d5-8bd89bcbac80'
    host2.macAddress = host2_mac

    
    cluster.addHost(host1)
    #cluster.addHost(host2)
    #cluster.addHost(host3)

    return cluster
