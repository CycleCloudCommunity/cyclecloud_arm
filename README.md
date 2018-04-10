# CycleCloud ARM 
Deploying Azure CycleCloud into a subscription using an Azure Resource Manager template

## Introduction
- This repo contains an ARM template for deploying Azure CycleCloud.
- There are two ARM templates in here: 
    - `deploy-vnet.json` creates a VNET with 3 separate subnets:
        1. `cycle`: The subnet in which the CycleCloud server is started in.
        2. `compute`: A /22 subnet for the HPC clusters
        3. `user`: The subnet for creating login nodes.
    - `deploy-cyclecloud.json` provisions and sets up the CycleCloud application server.
- If you have a VNET (or subnets) that you want to deploy in, you can skip the the Vnet deployment. 


## Pre-requisites
1. [Azure CLI 2.0](https://docs.microsoft.com/en-us/cli/azure/overview?view=azure-cli-latest) installed and configured with an Azure subscription

2. [Service principal in your Azure Active Directory](https://docs.microsoft.com/en-us/cli/azure/create-an-azure-service-principal-azure-cli?view=azure-cli-latest)

- Using the AZ CLI:
```
    $ az ad sp create-for-rbac --name CycleCloudApp --years 1
    {
        "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "displayName": "CycleCloudApp",
        "name": "http://CycleCloudApp",
        "password": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    }
```
- Save the output -- you'll need the appId, password and tenant id.

3. Azure subscription ID. 
- The easiest way to retrieve it:
```
        $ az account list -o table
```

4. The installation and license URLs for CycleCloud (Request this from your Microsoft or Cycle representative)

5. [Optional] A login into the Cycle portal - used for checking out site specific licenses


## Using the templates

* Clone the repo 

        $ git clone https://github.com/CycleCloudCommunity/cyclecloud_arm.git

### Create a Resource Group and VNET
* *_If you already have a VNET in a Resource Group that you would like to deploy CycleCloud in, skip this step and use the VNET and resource group in the next section_*

* Create a resource group in the region of your choice:

        $ az group create --name "{RESOURCE-GROUP}" --location "{REGION}"

* Build the Virtual Network and subnets. By default the vnet is named **cyclevnet** . 

        $ az group deployment create --name "vnet_deployment" --resource-group "{RESOURCE-GROUP}" --template-file deploy-vnet.json --parameters params-vnet.json

### Deploy CycleCloud

1. Edit `params-cyclecloud.json`, updating these parameters: 

* `cycleDownloadURL`: The download URL for the CycleCloud installation files. Get this from your Microsoft or Cycle rep.
* `cyclePortalAccount`: The email address registered with a [Cycle Portal](https://portal.cyclecomputing.com) account 
* `cyclePortalPW`: The password for the Cycle Portal account above.
* `cycleLicenseURL`: The URL to a temporary license for CycleCloud. Get this from your Microsoft or Cycle rep.
* `rsaPublicKey`: The public key staged into the Cycle and Jumpbox VMs
* The follwing attributes from the service principal: `applicationSecret`, `tenantId`, `applicationId`
*  `cyclecloudAdminPW`: Specifiy a password for the `admin` user for the Cyclecloud application server. The password needs to meet the following specifications: 

        Between 3-8 characters and meeting three of the following four conditions:
        - Contains an upper case character
        - Contains a lower case character
        - Contains a number
        - Contains a special character: @ # $ % ^ & * - _ ! + = [ ] { } | \ : ' , . ? ` ~ " ( ) ;

2. Deploy the jumpbox and CycleCloud server:

        $ az group deployment create --name "cyclecloud_deployment" --resource-group "{RESOURCE-GROUP}" --template-file deploy-cyclecloud.json --parameters params-cyclecloud.json

The deployment process runs the installation script `cyclecloud_install.py` as a custom extension script, which installs and sets up CycleCloud.

## Login to the CycleCloud application server

* To connect to the CycleCloud webserver, first retrieve the FQDN of the CycleServer VM from the Azure Portal, then browse to https://cycleserverfqdn/. The installation uses a self-signed SSL certificate which may show up with a warning in your browser.
_You could also reach the webserver through the VM's public IP address:_

        az vm list-ip-addresses -o table -g ${RESOURCE-GROUP} 

* Login to the webserver using the `admin` user, and the `cyclecloudAdminPW` password defined in the `params-cyclecloud.json` parameters file.
* 



## Using the CycleCloud CLI
* The CycleCloud CLI is required for importing custom cluster templates, and is installed in the **cycleserver** VM. SSH access into this VM is not directly accessible -- you have to first SSH into the admin jumpbox to reach it.

* In the Azure portal, retrieve the full DNS name of the CycleCloud server. You can then SSH on it with the **cycleadmin** user with the SSH key you provided. Once on the CycleCloud server, test the CycleCloud CLI

        $ cyclecloud locker list


## Check installation logs

* The Cycle Server installation logs are located in the /var/lib/waagent/custom-script/download/0 directory.

# Create your cluster

* Build your cluster in Cycle by using the provided templates

