// CycleCloud environment buiding template

param spTenantId string
param spAppId string
@secure()
param spAppSecret string
param keySSHpublic string
param userName string = 'cycleadmin'
@secure()
param userPass string

param curlocation string = resourceGroup().location
param prefixDeploy string = 'af${uniqueString(resourceGroup().id)}'
param prefixIPaddr string = '10.18'     //Will create 10.18.0.0/16 VNet accordingly
param boolStAcctdeploy bool = true
param nameStAcct string = toLower('${prefixDeploy}')
param boolANFdeploy bool = false
param sizeANFinTB int = 4
param cidrWhitelist string = '0.0.0.0/0'
param typeSovereign string = 'public'

var skuCycleVM = 'Standard_D4s_v3'   
var skuCycleDisk = 'Standard_LRS'       //Option:  Premium_LRS
var nameVM = '${prefixDeploy}-cycleVM'
var nameNIC = '${prefixDeploy}-cycleNIC'
var nameNSG = '${prefixDeploy}-cycleNSG'
var nameIP = '${prefixDeploy}-cycleIP'
var nameRg = resourceGroup().name
var nameANFacct = '${prefixDeploy}-anfacct'
var nameANFcapool = '${prefixDeploy}-pool'
var nameANFvol = 'volprotein'

resource cyclevnet 'Microsoft.Network/virtualNetworks@2021-05-01' = {
  name:'${prefixDeploy}-cyclevnet'
  location: curlocation
  properties: {
    addressSpace: {
      addressPrefixes: [
        '${prefixIPaddr}.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'cycle'
        properties: {
          addressPrefix: '${prefixIPaddr}.1.0/24'
        }
      }
      {
        name: 'anf'
        properties: {
          addressPrefix: '${prefixIPaddr}.2.0/24'
          delegations: [
            { 
              name: 'Microsoft.NetApp.volumes'
              properties: {
                serviceName: 'Microsoft.NetApp/volumes'
              }                            
            }
          ]
        }
      }
      {
        name: 'user'
        properties: {
          addressPrefix: '${prefixIPaddr}.3.0/24'
        }
      }
      {
        name: 'compute'
        properties: {
          addressPrefix: '${prefixIPaddr}.4.0/22'
        }
      }
    ]
  }
}

resource cycleEIP 'Microsoft.Network/publicIPAddresses@2021-05-01' = {
  name: nameIP
  location: curlocation
  properties: {
    publicIPAddressVersion: 'IPv4'
    publicIPAllocationMethod: 'Static'
    idleTimeoutInMinutes: 4
    dnsSettings: {
      domainNameLabel: toLower('${prefixDeploy}')
    }
  }
}

resource cycleNSG 'Microsoft.Network/networkSecurityGroups@2021-05-01' = {
  name: nameNSG
  location: curlocation
  properties: {
    securityRules: [
      {
        name: 'AllowSecuredCyclePortalInBound'
        properties: {
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: cidrWhitelist
          destinationAddressPrefix: 'VirtualNetwork'
          priority: 1000
        } 
      }
      {
        name: 'AllowCyclePortalInBound'
        properties: {
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: cidrWhitelist
          destinationAddressPrefix: 'VirtualNetwork'
          priority: 1001
        }
      }
      {
        name: 'AllowSSHLink'
        properties: {
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: cidrWhitelist
          destinationAddressPrefix: '*'
          priority: 1002
        }
      }
    ]
  }
}

resource cycleNIC 'Microsoft.Network/networkInterfaces@2021-05-01' = {
  name: nameNIC
  location: curlocation
  properties: {    
    enableAcceleratedNetworking: false
    enableIPForwarding: false
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          primary: true
          privateIPAddressVersion: 'IPv4'
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: {
            id: cycleEIP.id            
          }
          subnet: {
            id: cyclevnet.properties.subnets[0].id
          }
        }
      }
    ]
    networkSecurityGroup: {
      id: cycleNSG.id
    }       
  }
}

resource cycleStAcct 'Microsoft.Storage/storageAccounts@2021-08-01' = if (boolStAcctdeploy) {
  name: nameStAcct
  location: curlocation
  sku: {
    name: 'Standard_ZRS'
  }
  kind: 'StorageV2'
}

resource anfAcct 'Microsoft.NetApp/netAppAccounts@2021-10-01' = if (boolANFdeploy) {
  name: nameANFacct
  location: curlocation
}

resource anfPool 'Microsoft.NetApp/netAppAccounts/capacityPools@2021-10-01' = if (boolANFdeploy) {
  name: nameANFcapool
  location: curlocation
  parent: anfAcct
  properties: {
    serviceLevel: 'Premium'
    size: sizeANFinTB*1024*1024*1024*1024
  }
}

resource anfVolume 'Microsoft.NetApp/netAppAccounts/capacityPools/volumes@2021-10-01' = if (boolANFdeploy) {
  name: nameANFvol
  location: curlocation
  parent: anfPool
  properties: {
    creationToken: nameANFvol
    subnetId: cyclevnet.properties.subnets[1].id
    usageThreshold: sizeANFinTB*920*1024*1024*1024    //alerting at 90%
    exportPolicy: {
      rules: [
        {
          ruleIndex: 1
          allowedClients: '${prefixIPaddr}.0.0/16'
          nfsv3: false
          nfsv41: true                    
          unixReadWrite: true
          unixReadOnly: false
          cifs: false
        }
      ]
    }
    protocolTypes: [
      'NFSv4.1'
    ]
  }
}

resource cycleVM 'Microsoft.Compute/virtualMachines@2021-11-01' = {
  name: nameVM
  location: curlocation
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: skuCycleVM      
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: cycleNIC.id
        }
      ]
    }
    osProfile: {
      adminUsername: userName
      computerName: nameVM
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              keyData: keySSHpublic
              path: '/home/${userName}/.ssh/authorized_keys'
            }
          ]
        }
      }
    }
    storageProfile: {
      dataDisks: [
        {
          caching: 'ReadOnly'
          createOption: 'Empty'
          diskSizeGB: 128
          lun: 0
          managedDisk: {
            storageAccountType: skuCycleDisk
          }
        }
      ]
      imageReference: {
        offer: 'CentOS-HPC'
        publisher: 'OpenLogic'
        sku: '8_1'
        version: 'latest'        
      }
      osDisk: {
        createOption: 'FromImage'
        caching: 'ReadWrite'
        managedDisk: {
          storageAccountType: skuCycleDisk          
        }
        osType: 'Linux'
      } 
    }
  }  
}

var cyclefqdn = cycleEIP.properties.dnsSettings.fqdn
resource cycleVMExtension 'Microsoft.Compute/virtualMachines/extensions@2021-11-01' = {
  name: 'CycleExtension'
  location: curlocation
  parent: cycleVM  
  properties: {
    autoUpgradeMinorVersion: true
    protectedSettings: {
      commandToExecute: 'python3 cyclecloud_install.py --acceptTerms --applicationSecret ${spAppSecret} --applicationId ${spAppId} --tenantId ${spTenantId} --azureSovereignCloud ${typeSovereign} --username ${userName} --password ${userPass} --publickey "${keySSHpublic}" --hostname ${cyclefqdn} --storageAccount ${nameStAcct} --resourceGroup ${nameRg} --useLetsEncrypt --webServerPort 80 --webServerSslPort 443 --webServerMaxHeapSize 4096M'      
    }
    publisher: 'Microsoft.Azure.Extensions'
    settings: {
      fileUris: [
        'https://raw.githubusercontent.com/CycleCloudCommunity/cyclecloud_arm/feature/update_cyclecloud_install/cyclecloud_install.py'        
      ]
    }
    type: 'CustomScript'
    typeHandlerVersion: '2.0'
  }  
}

output anfExportIP string = boolANFdeploy ? anfVolume.properties.mountTargets[0].ipAddress : '' 
output urlCycleCloud string = 'https://${cyclefqdn}'
