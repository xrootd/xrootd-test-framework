from XrdTest.ClusterUtils import Cluster, Network, Host, Disk 

def getCluster():
    cluster = Cluster()
    #---------------------------------------------------------------------------
    # Global names
    #---------------------------------------------------------------------------
    cluster.name = 'cluster_001_mm' 
    network_name = cluster.name + '_net'
    
    #---------------------------------------------------------------------------
    # Cluster defaults
    #
    # The bootImage parameter is relative to the storage_pool location as given
    # in the hypervisor config file.
    #---------------------------------------------------------------------------
    cluster.defaultHost.bootImage = 'slc6_testslave_ref.img'
    cluster.defaultHost.cacheBootImage = True
    cluster.defaultHost.arch = 'x86_64'
    cluster.defaultHost.ramSize = '1048576'
    cluster.defaultHost.net = network_name
    
    #---------------------------------------------------------------------------
    # Network definition
    #---------------------------------------------------------------------------
    net = Network()
    net.bridgeName = 'virbr_001_mm'
    net.name = network_name
    net.ip = '192.168.128.1'
    net.netmask = '255.255.255.0'
    net.DHCPRange = ('192.168.128.2', '192.168.128.254')

    #---------------------------------------------------------------------------
    # Host definitions
    #---------------------------------------------------------------------------
    metamanager1 = Host('metamanager1.xrd.test', '192.168.128.3', "52:54:00:65:44:65")
    manager1 = Host('manager1.xrd.test', '192.168.128.4', "52:54:00:65:44:66")
    manager2 = Host('manager2.xrd.test', '192.168.128.5', "52:54:00:65:44:67")
    ds1 = Host('ds1.xrd.test', '192.168.128.6', "52:54:00:65:44:68")
    ds2 = Host('ds2.xrd.test', '192.168.128.7', "52:54:00:65:44:69")
    ds3 = Host('ds3.xrd.test', '192.168.128.8', "52:54:00:65:44:70")
    ds4 = Host('ds4.xrd.test', '192.168.128.9', "52:54:00:65:44:71")
    client1 = Host('client1.xrd.test', '192.168.128.10', "52:54:00:65:44:72")
    
    #---------------------------------------------------------------------------
    # Additional host disk definitions
    #
    # As per the libvirt docs, the device name given here is not guaranteed to 
    # map to the same name in the guest OS. Incrementing the device name works
    # (i.e. disk1 = vda, disk2 = vdb etc.).
    #---------------------------------------------------------------------------
    metamanager1.disks =  [Disk('disk1', '5G', device='vda', mountPoint='/data')]
    manager1.disks =  [Disk('disk1', '5G', device='vda', mountPoint='/data')]
    manager2.disks =  [Disk('disk1', '5G', device='vda', mountPoint='/data')]
    ds1.disks =  [Disk('disk1', '5G', device='vda', mountPoint='/data'), Disk('disk2', '5G', 'vdb', mountPoint='/data2')]
    ds2.disks =  [Disk('disk1', '5G', device='vda', mountPoint='/data')]
    ds3.disks =  [Disk('disk1', '5G', device='vda', mountPoint='/data')]
    ds4.disks =  [Disk('disk1', '5G', device='vda', mountPoint='/data')]
    client1.disks =  [Disk('disk1', '5G', device='vda', mountPoint='/data')]

    # Hosts to be included in the cluster
    hosts = [metamanager1, manager1, manager2, ds1, ds2, ds3, ds4, client1]

    net.addHosts(hosts)
    cluster.network = net
    cluster.addHosts(hosts)
    return cluster 
 
