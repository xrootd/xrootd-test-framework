from XrdTest.ClusterUtils import Cluster, Network, Host, Disk 

def getCluster():
    cluster = Cluster()
    #---------------------------------------------------------------------------
    # Global names
    #---------------------------------------------------------------------------
    cluster.name = 'cluster_001' 
    network_name = 'net_001'
    
    #---------------------------------------------------------------------------
    # Cluster defaults
    #---------------------------------------------------------------------------
    cluster.defaultHost.bootImage = '/var/lib/libvirt/images/xrd_testslave_ref.img'
    cluster.defaultHost.cacheBootImage = True
    cluster.defaultHost.arch = 'x86_64'
    cluster.defaultHost.ramSize = '1048576'
    cluster.defaultHost.net = network_name
    
    #---------------------------------------------------------------------------
    # Network definition
    #---------------------------------------------------------------------------
    net = Network()
    net.bridgeName = 'virbr_001'
    net.name = network_name
    net.ip = '192.168.127.1'
    net.netmask = '255.255.255.0'
    net.DHCPRange = ('192.168.127.2', '192.168.127.254')

    #---------------------------------------------------------------------------
    # Host definitions
    #---------------------------------------------------------------------------
    
    metamanager1 = Host('metamanager1', '192.168.127.3', "52:54:00:65:44:65",  net="net_001")
    manager1 = Host('manager1', '192.168.127.4', "52:54:00:65:44:66", net="net_001")
    manager2 = Host('manager2', '192.168.127.5', "52:54:00:65:44:67", net="net_001")
    ds1 = Host('ds1', '192.168.127.6', "52:54:00:65:44:68", net="net_001")
    ds2 = Host('ds2', '192.168.127.7', "52:54:00:65:44:69", net="net_001")
    ds3 = Host('ds3', '192.168.127.8', "52:54:00:65:44:70", net="net_001")
    ds4 = Host('ds4', '192.168.127.9', "52:54:00:65:44:71", net="net_001")
    client1 = Host('client1', '192.168.127.10', "52:54:00:65:44:72", net="net_001")
    
    #---------------------------------------------------------------------------
    # Additional host disk definitions
    #---------------------------------------------------------------------------
    metamanager1.disks =  [Disk('disk1', size='59055800320')]
    manager1.disks =  [Disk('disk1', size='59055800320')]
    manager2.disks =  [Disk('disk1', size='59055800320')]
    ds1.disks =  [Disk('disk1', size='59055800320')]
    ds2.disks =  [Disk('disk1', size='59055800320')]
    ds3.disks =  [Disk('disk1', size='59055800320')]
    ds4.disks =  [Disk('disk1', size='59055800320')]
    client1.disks =  [Disk('disk1', size='59055800320')]
 
    # Hosts to be included in the cluster
    hosts = [metamanager1, manager1, manager2, ds1, ds2, ds3, ds4, client1]


    net.addHosts(hosts)
    cluster.network = net
    cluster.addHosts(hosts)
    return cluster 
 
