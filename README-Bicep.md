# IaC-CycleCloud： Bicep template for Azure CycleCloud environment building

## Pre-requisites
· Enter "Cloud Shell" in console top-right or use your bastion terminal with [Azure CLI installed](https://docs.microsoft.com/en-us/azure/azure-resource-manager/bicep/install#azure-cli).

· Has a SSH Keypair created in [Azure portal](https://docs.microsoft.com/en-us/azure/virtual-machines/ssh-keys-portal) or [using CLI](https://docs.microsoft.com/en-us/azure/cyclecloud/how-to/install-arm?view=cyclecloud-8#ssh-keypair).

## Setup
1. Create service principal 
 
```shell
az ad sp create-for-rbac --name CycleCloudApp --years 1
```

The output will display a number of parameters. You will need to save the appId, password, and tenant:

 ```
"appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
"displayName": "CycleCloudApp",
"name": "http://CycleCloudApp",
"password": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
"tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

2. Execute:
	
```shell	
git clone https://github.com/CycleCloudCommunity/cyclecloud_arm.git 
cd HPC-IaC-Garage/IaC-CycleCloud

AF2TenantID = '<your-tenant-id>'
AF2AppID = '<your-app-id>'
AF2AppSecret = '<your-app-secret>'
AF2UserPass = '<yourpass>'
AF2SSHPublic = '<your-ssh-publickey>'
az group create --name rgHPC --location southeastasia
az deployment group create -g rgHPC --template-file ./HPC-IaC-Garage/IaC-CycleCloud/cyclecloudiac.bicep --parameters spTenantId=$AF2TenantID spAppId=$AF2AppID spAppSecret=$AF2AppSecret keySSHpublic=$AF2SSHPublic userPass=$AF2UserPass 
```

3. Wait 10-20 minutes.

4. Check  the ready resources. Go to console page "Home->Resource groups->rgHPC->Deployments" to check the resource created in rgHPC. Find the cycleVM's public IP/DNS name to visit CycleCloud console by browser.

5. Customize your deployment by parameters appending:
a. IP scope prefix can be defined by parameter "prefixIPaddr='10.163'" to avoid CIDR collision.
b. Can deploy an ANF volume for further HPC cluster using through "boolANFdeploy=true" and select the volume size as "sizeANFinTB=8"
c. Can define the whitelisted IP cidr for CycleCloud portal access to enhance security, as "cidrWhitelist='167.220.0.0/16'".
d. Template will create a new storage account. Can disable this building by "boolStAcctdeploy=false" and provide the existed storage account by "nameStAcct='<yourStAcctname>'"

For example: 

```shell
az deployment group create -g rgHPC --template-file ./HPC-IaC-Garage/IaC-CycleCloud/cyclecloudiac.bicep --parameters spTenantId=$AF2TenantID spAppId=$AF2AppID spAppSecret=$AF2AppSecret keySSHpublic=$AF2SSHPublic userPass=$AF2UserPass prefixIPaddr='10.163' boolANFdeploy=true sizeANFinTB=4 cidrWhitelist='xx.xx.0.0/16' boolStAcctdeploy=false nameStAcct='<exist-storageaccount>'
```

6. Tear down

```shell
az group delete -g rgHPC
```




