#!/usr/bin/python
# Prepare an Azure provider account for CycleCloud usage.
import argparse
import tarfile
import json
import re
from random import SystemRandom
from string import ascii_letters, ascii_lowercase, digits
from subprocess import CalledProcessError, check_output 
from os import path, listdir, makedirs, chdir, fdopen, remove
from urllib2 import urlopen, Request
from urllib import urlretrieve
from shutil import rmtree, copy2, move, copytree
from tempfile import mkstemp, mkdtemp
from time import sleep


tmpdir = mkdtemp()
print "Creating temp directory " + tmpdir + " for installing CycleCloud"
cycle_root = "/opt/cycle_server"

def clean_up():
    rmtree(tmpdir)    

def _catch_sys_error(cmd_list):
    try:
        output = check_output(cmd_list)
        print cmd_list
        print output
    except CalledProcessError as e:
        print "Error with cmd: %s" % e.cmd
        print "Output: %s" % e.output
        raise


def account_and_cli_setup(tenant_id, application_id, application_secret, cycle_portal_account, cycle_portal_pw, cyclecloud_admin_pw, admin_user, azure_region):
    print "Setting up azure account in CycleCloud and initializing cyclecloud CLI"
    metadata_url = "http://169.254.169.254/metadata/instance?api-version=2017-08-01"
    metadata_req = Request(metadata_url, headers={"Metadata" : True})
    metadata_response = urlopen(metadata_req)
    vm_metadata = json.load(metadata_response)

    subscription_id = vm_metadata["compute"]["subscriptionId"]
    location = vm_metadata["compute"]["location"]
    resource_group = vm_metadata["compute"]["resourceGroupName"]

    random_suffix = ''.join(SystemRandom().choice(ascii_lowercase) for _ in range(14))

    storage_account_name = 'cyclecloud'  + random_suffix 

    azure_data = {
        "AzureEnvironment": azure_region,
        "AzureRMApplicationId": application_id,
        "AzureRMApplicationSecret": application_secret,
        "AzureRMSubscriptionId": subscription_id,
        "AzureRMTenantId": tenant_id,
        "AzureResourceGroup": resource_group,
        "DefaultAccount": True,
        "Location": location,
        "Name": "azure",
        "Provider": "azure",
        "ProviderId": subscription_id,
        "RMStorageAccount": storage_account_name,
        "RMStorageContainer": "cyclecloud"
    }

    app_setting_data = {
        "AdType": "Application.Setting",
        "Name": "cycleserver.sendAnonymizedData",
        "Value": True
    }
    app_setting_installation = {
        "AdType": "Application.Setting",
        "Name": "cycleserver.installation.complete",
        "Value": True
    }
    authenticated_user = {
        "AdType": "AuthenticatedUser",
        "Name": admin_user,
        "RawPassword": cyclecloud_admin_pw,
        "Superuser": True
    }
    site_name = {
        "AdType": "Application.Setting",
        "Name": "site_name",
        "Value": resource_group,
        "Category": "Support" 
    }
    portal_account = {
        "AdType": "Application.Setting",
        "Description": "The account login for this installation",
        "Value": cycle_portal_account,
        "Name": "support.account.login"
    }
    portal_login = {
        "AdType": "Application.Setting",
        "Description": "The account login for this installation",
        "Value": cycle_portal_pw,
        "Name": "support.account.password"
    }

    account_data = [
        app_setting_data,
        app_setting_installation,
        authenticated_user,        
        site_name,
        portal_account,
        portal_login 
    ]

    account_data_file = tmpdir + "/account_data.json"
    azure_data_file = tmpdir + "/azure_data.json"

    with open(account_data_file, 'w') as fp:
        json.dump(account_data, fp)

    with open(azure_data_file, 'w') as fp:
        json.dump(azure_data, fp)

    copy2(account_data_file, cycle_root + "/config/data/")

    # wait for the data to be imported
    password_flag = ("--password=%s" % cyclecloud_admin_pw) 
    sleep(5)

    print "Initializing cylcecloud CLI"
    _catch_sys_error(["/usr/bin/cyclecloud", "initialize", "--loglevel=debug", "--batch", "--url=https://localhost:8443", "--verify-ssl=false", "--username=" + admin_user, password_flag])    

    homedir = path.expanduser("~")
    cycle_config = homedir + "/.cycle/config.ini"
    with open(cycle_config, "a") as config_file:
        config_file.write("\n")
        config_file.write("[pogo azure-storage]\n")
        config_file.write("type = az\n")
        config_file.write("subscription_id = " + subscription_id+ "\n")
        config_file.write("tenant_id = " + tenant_id + "\n")
        config_file.write("application_id = " + application_id + "\n")
        config_file.write("application_secret = " + application_secret + "\n")
        config_file.write("matches = az://"+ storage_account_name + "/cyclecloud" + "\n") 


    print "Registering Azure subscription"
    # create the cloud provide account
    _catch_sys_error(["/usr/bin/cyclecloud", "account", "create", "-f", azure_data_file])

    # stash the cyclecloud configs into the admin_user account as well
    copytree(homedir + "/.cycle", "/home/" + admin_user + "/.cycle" )
    _catch_sys_error(["chown", "-R", admin_user , "/home/" + admin_user + "/.cycle"])




def start_cc():
    print "Starting CycleCloud server"
    cs_cmd = cycle_root + "/cycle_server"
    _catch_sys_error([cs_cmd, "start"])
    _catch_sys_error([cs_cmd, "await_startup"])
    _catch_sys_error([cs_cmd, "status"])

    # use iptables to foward 80 and 443 to 8080 and 8443 respectively
    _catch_sys_error(["iptables", "-A", "PREROUTING", "-t", "nat", "-i", "eth0", "-p", "tcp", "--dport", "80", "-j", "REDIRECT", "--to-port", "8080"])
    _catch_sys_error(["iptables", "-A", "PREROUTING", "-t", "nat", "-i", "eth0", "-p", "tcp", "--dport", "443", "-j", "REDIRECT", "--to-port", "8443"])

def _sslCert(randomPW):
    print "Generating self-signed SSL cert"
    _catch_sys_error(["/bin/keytool", "-genkey", "-alias", "CycleServer", "-keypass", randomPW, "-keystore", cycle_root + "/.keystore", "-storepass", randomPW, "-keyalg", "RSA", "-noprompt", "-dname", "CN=cycleserver.azure.com,OU=Unknown, O=Unknown, L=Unknown, ST=Unknown, C=Unknown"])
    _catch_sys_error(["chown", "cycle_server.", cycle_root+"/.keystore"])
    _catch_sys_error(["chmod", "600", cycle_root+"/.keystore" ])


def modify_cs_config():
    print "Editing CycleCloud server system properties file"
    # modify the CS config files
    cs_config_file = cycle_root + "/config/cycle_server.properties"

    randomPW = ''.join(SystemRandom().choice(ascii_letters + digits) for _ in range(16))
    # generate a self-signed cert
    _sslCert(randomPW)

    fh, tmp_cs_config_file = mkstemp()
    with fdopen(fh,'w') as new_config:
        with open(cs_config_file) as cs_config:
            for line in cs_config:
                if 'webServerMaxHeapSize=' in line:
                    new_config.write('webServerMaxHeapSize=4096M')
                elif 'webServerEnableHttps=' in line:
                    new_config.write('webServerEnableHttps=true')
                elif 'webServerRedirectHttp=' in line:
                    new_config.write('webServerRedirectHttp=true')
                elif 'webServerKeystorePass=' in line:
                    new_config.write('webServerKeystorePass=' + randomPW)
                elif 'webServerJvmOptions=' in line:
                    new_config.write(
                        'webServerJvmOptions=-Djava.net.preferIPv4Stack=true -Djava.net.preferIPv4Addresses=true')
                else:
                    new_config.write(line)

    remove(cs_config_file)
    move(tmp_cs_config_file, cs_config_file)

    #Ensure that the files are created by the cycleserver service user
    _catch_sys_error(["chown", "-R", "cycle_server.", cycle_root])


def generate_ssh_key(admin_user):
    print "Creating an SSH private key for VM access"
    homedir = path.expanduser("~")
    sshdir = homedir + "/.ssh"
    if not path.isdir(sshdir):
        makedirs(sshdir, mode=700) 
    
    sshkeyfile = sshdir + "/cyclecloud.pem"
    if not path.isfile(sshkeyfile):
        _catch_sys_error(["ssh-keygen", "-f", sshkeyfile, "-t", "rsa", "-b", "2048","-P", ''])

    # make the cyclecloud.pem available to the cycle_server process
    cs_sshdir = cycle_root + "/.ssh"
    cs_sshkeyfile = cs_sshdir + "/cyclecloud.pem"

    if not path.isdir(cs_sshdir):
        makedirs(cs_sshdir)
    
    if not path.isdir(cs_sshkeyfile):
        copy2(sshkeyfile, cs_sshkeyfile)
        _catch_sys_error(["chown", "-R", "cycle_server.", cs_sshdir])
        _catch_sys_error(["chmod", "700", cs_sshdir])

    # make the cyclecloud.pem available to the login user as well
    adminuser_sshdir = "/home/" + admin_user + "/.ssh"
    adminuser_sshkeyfile = adminuser_sshdir + "/cyclecloud.pem"

    if not path.isdir(adminuser_sshdir):
        makedirs(adminuser_sshdir)
    
    if not path.isdir(adminuser_sshkeyfile):
        copy2(sshkeyfile, adminuser_sshkeyfile)
        _catch_sys_error(["chown", "-R", admin_user, adminuser_sshdir])
        _catch_sys_error(["chmod", "700", adminuser_sshdir])


def cc_license(license_url):
    # get a license
    license_file = cycle_root + '/license.dat'
    print "Fetching temporary license from " + license_url
    urlretrieve(license_url, license_file)
    _catch_sys_error(["chown", "cycle_server.", license_file])


def download_install_cc(download_url, version):    
    chdir(tmpdir)
    cyclecloud_rpm = "cyclecloud-" + version + ".x86_64.rpm"
    cyclecloud_tar = "cyclecloud-" + version + ".linux64.tar.gz" 
    cc_url = download_url + "/" + version + "/" + cyclecloud_tar

    print "Downloading CycleCloud from " + cc_url
    urlretrieve (cc_url, cyclecloud_tar)

    cc_tar = tarfile.open(cyclecloud_tar, "r:gz")
    cc_tar.extractall(path=tmpdir)
    cc_tar.close()


    # CLI comes with an install script but that installation is user specific
    # rather than system wide. 
    # Downloading and installing pip, then using that to install the CLIs 
    # from source.
    print "Unzip and install CLI"
    _catch_sys_error(["unzip", "cycle_server/cli/cyclecloud-cli.zip"]) 
    for cli_install_dir in listdir("."):
        if path.isdir(cli_install_dir) and re.match("cyclecloud-cli-installer", cli_install_dir):
            print "Found CLI install DIR %s" % cli_install_dir
            chdir(cli_install_dir + "/packages")
            urlretrieve("https://bootstrap.pypa.io/get-pip.py", "get-pip.py")
            _catch_sys_error(["python", "get-pip.py"]) 
            _catch_sys_error(["pip", "install", "cyclecloud-cli-sdist.tar.gz"]) 
            _catch_sys_error(["pip", "install", "pogo-sdist.tar.gz"]) 

    chdir(tmpdir)
    _catch_sys_error(["cycle_server/install.sh", "--nostart"])


def install_pre_req():
    print "Installing pre-requisites for CycleCloud server"
    _catch_sys_error(["yum", "install", "-y", "java-1.8.0-openjdk-headless"])

def main():
    
    parser = argparse.ArgumentParser(description="usage: %prog [options]")


    parser.add_argument("--cycleCloudVersion",
                      dest="cycleCloudVersion",
                    #   required=True,
                      help="CycleCloud version to install")

    parser.add_argument("--downloadURL",
                      dest="downloadURL",
                    #   required=True,
                      help="Download URL for the Cycle install")

    parser.add_argument("--licenseURL",
                      dest="licenseURL",
                      help="Download URL for trial license")

    parser.add_argument("--azureRegion",
                      dest="azureRegion",
                      help="Azure Region [china|germany|public|usgov]")

    parser.add_argument("--tenantId",
                      dest="tenantId",
                      help="Tenant ID of the Azure subscription")

    parser.add_argument("--applicationId",
                      dest="applicationId",
                      help="Application ID of the Service Principal")

    parser.add_argument("--applicationSecret",
                      dest="applicationSecret",
                      help="Application Secret of the Service Principal")

    parser.add_argument("--cyclePortalAccount",
                      dest="cyclePortalAccount",
                      help="Email address of the account in the CycleCloud portal for checking out licenses")

    parser.add_argument("--cyclePortalPW",
                      dest="cyclePortalPW",
                      help="Password for the ccount in the CycleCloud portal")

    parser.add_argument("--cyclecloudAdminPW",
                      dest="cyclecloudAdminPW",
                      help="Admin user password for the cyclecloud application server")

    parser.add_argument("--adminUser",
                      dest="adminUser",
                      help="The local admin user for the CycleCloud VM")

    args = parser.parse_args()

    print("Debugging arguments: %s" % args)

    install_pre_req()
    download_install_cc(args.downloadURL, args.cycleCloudVersion) 
    generate_ssh_key(args.adminUser)
    modify_cs_config()
    cc_license(args.licenseURL)
    start_cc()
    account_and_cli_setup(args.tenantId, args.applicationId, args.applicationSecret, args.cyclePortalAccount, args.cyclePortalPW, args.cyclecloudAdminPW, args.adminUser, args.azureRegion)

    clean_up()


if __name__ == "__main__":
    main()




