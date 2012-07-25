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
    
    metamanager1 = Host('metamanager1.xrd.test', '192.168.127.3', "52:54:00:65:44:65")
    manager1 = Host('manager1.xrd.test', '192.168.127.4', "52:54:00:65:44:66")
    manager2 = Host('manager2.xrd.test', '192.168.127.5', "52:54:00:65:44:67")
    ds1 = Host('ds1.xrd.test', '192.168.127.6', "52:54:00:65:44:68")
    ds2 = Host('ds2.xrd.test', '192.168.127.7', "52:54:00:65:44:69")
    ds3 = Host('ds3.xrd.test', '192.168.127.8', "52:54:00:65:44:70")
    ds4 = Host('ds4.xrd.test', '192.168.127.9', "52:54:00:65:44:71")
    client1 = Host('client1', '192.168.127.10', "52:54:00:65:44:72")
    
    #---------------------------------------------------------------------------
    # Additional host disk definitions
    #---------------------------------------------------------------------------
    metamanager1.disks =  [Disk('disk1', '59055800320', 'vdb')]
    manager1.disks =  [Disk('disk1', '59055800320', 'vdb')]
    manager2.disks =  [Disk('disk1', '59055800320', 'vdb')]
    ds1.disks =  [Disk('disk1', '59055800320', 'vdb')]
    ds2.disks =  [Disk('disk1', '59055800320', 'vdb')]
    ds3.disks =  [Disk('disk1', '59055800320', 'vdb')]
    ds4.disks =  [Disk('disk1', '59055800320', 'vdb')]
    client1.disks =  [Disk('disk1', '59055800320', 'vdb')]
 
    # Hosts to be included in the cluster
    hosts = [metamanager1, manager1, manager2, ds1, ds2, ds3, ds4, client1]


    net.addHosts(hosts)
    cluster.network = net
    cluster.addHosts(hosts)
    return cluster 
 
