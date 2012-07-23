from XrdTest.ClusterUtils import Cluster, Network, Host, Disk 

def getCluster():
    cluster = Cluster()
    #---------------------------------------------------------------------------
    # Global names
    # Used commonly in network and host definitions
    #---------------------------------------------------------------------------
    cluster.name = 'cluster_001' 
    network_name = 'net_001'
    
    # Cluster defaults
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
    h1 = Host('slave1', '192.168.127.3', "52:54:00:65:44:65", ramSize='1048576', 
              arch='x86_64', net="net_001")
    h2 = Host('slave2', '192.168.127.4', "52:54:00:65:44:66", ramSize='1048576', 
              arch='x86_64', net="net_001")
    h3 = Host('slave3', '192.168.127.5', "52:54:00:65:44:67", ramSize='1048576', 
              arch='x86_64', net="net_001", cacheBootImage=False)
    
    #---------------------------------------------------------------------------
    # Additional host disk definitions
    #---------------------------------------------------------------------------
    h1.disks =  [
                 Disk('disk1', size='59055800320'),
                 Disk('disk2', size='59055800320')
                ]
    h2.disks =  [
                 Disk('disk1', size='59055800320')
                ]
    h3.disks =  [
                 Disk('disk1', size='59055800320', cache=False),
                 Disk('disk2', size='59055800320', cache=False)
                ]
 
    # Hosts to be included in the cluster
    hosts = [h1, h2, h3]


    net.addHosts(hosts)
    cluster.network = net
    cluster.addHosts(hosts)
    return cluster 
 
