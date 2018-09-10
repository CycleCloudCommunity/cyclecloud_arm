#!/usr/bin/python
# Prepare an Azure provider account for CycleCloud usage.
import argparse
import tarfile
import json
import re
import random
import sys
from string import ascii_letters, ascii_uppercase, ascii_lowercase, digits
from subprocess import CalledProcessError, check_output
from os import path, listdir, makedirs, chdir, fdopen, remove
from urllib2 import urlopen, Request, HTTPError, URLError
from urllib import urlretrieve
from shutil import rmtree, copy2, move, copytree
from tempfile import mkstemp, mkdtemp
from time import sleep


tmpdir = mkdtemp()
print "Creating temp directory " + tmpdir + " for installing CycleCloud"
cycle_root = "/opt/cycle_server"
cs_cmd = cycle_root + "/cycle_server"


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


def reset_installation():
    # reset the installation status so the splash screen re-appears
    print "Resetting installation"
    sql_statement = 'update Application.Setting set Value = false where name ==\"cycleserver.installation.complete\"'
    _catch_sys_error(
        ["/opt/cycle_server/cycle_server", "execute", sql_statement])

def setup_admin_user(admin_username, admin_userpasswd):
    '''
    This block completes the setup process for CycleCloud, so that it can automatically be used and scripted against 
    without any manual intervention. 
    Creates a admin user account in CycleCloud, and registers the CLI for the admin user.
    The admin user is the username used to create the Azure CycleCloud server.
    '''
    login_user = {
        "AdType": "AuthenticatedUser",
        "Name": admin_username,
        "RawPassword": admin_userpasswd,
        "Superuser": True
    }
    login_user_data = [login_user]

    login_user_data_file = tmpdir + "/login_user_data.json"

    with open(login_user_data_file, 'w') as fp:
        json.dump(login_user_data, fp)

    copy2(login_user_data_file, cycle_root + "/config/data/")


def create_user_credential(username):
    authorized_keyfile = "/home/" + username + "/.ssh/authorized_keys"
    public_key = ""
    with open(authorized_keyfile, 'r') as pubkeyfile:
        public_key = pubkeyfile.read()

    credential_record = {
        "PublicKey": public_key,
        "AdType": "Credential",
        "CredentialType": "PublicKey",
        "Name": username + "/public"
    }
    credential_data_file = tmpdir + "/credential.json"
    with open(credential_data_file, 'w') as fp:
        json.dump(credential_record, fp)

    copy2(credential_data_file, cycle_root + "/config/data/")


def register_azure_subscription(vm_metadata, tenant_id, application_id, application_secret, admin_user, azure_cloud, accept_terms, password):
    print "Setting up azure account in CycleCloud and initializing cyclecloud CLI"

    cyclecloud_admin_pw = ""

    if password:
        print 'Password specified, using it as the admin password'
        cyclecloud_admin_pw = password
    else:
        random_pw_chars = ([random.choice(ascii_lowercase) for _ in range(20)] +
                           [random.choice(ascii_uppercase) for _ in range(20)] +
                           [random.choice(digits) for _ in range(10)])
        random.shuffle(random_pw_chars)
        cyclecloud_admin_pw = ''.join(random_pw_chars)

    app_setting_installation = {
        "AdType": "Application.Setting",
        "Name": "cycleserver.installation.complete",
        "Value": True
    }
    initial_user = {
        "AdType": "Application.Setting",
        "Name": "cycleserver.installation.initial_user",
        "Value": admin_user
    }
    authenticated_user = {
        "AdType": "AuthenticatedUser",
        "Name": 'root',
        "RawPassword": cyclecloud_admin_pw,
        "Superuser": True
    }
    account_data = [
        authenticated_user,
        initial_user,
        app_setting_installation
    ]

    account_data_file = tmpdir + "/account_data.json"

    with open(account_data_file, 'w') as fp:
        json.dump(account_data, fp)

    copy2(account_data_file, cycle_root + "/config/data/")
    # wait for the data to be imported
    sleep(5)

    subscription_id = vm_metadata["compute"]["subscriptionId"]
    location = vm_metadata["compute"]["location"]
    resource_group = vm_metadata["compute"]["resourceGroupName"]

    random_suffix = ''.join(random.SystemRandom().choice(
        ascii_lowercase) for _ in range(14))

    storage_account_name = 'cyclecloud' + random_suffix
    azure_data = {
        "Environment": azure_cloud,
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

    azure_data_file = tmpdir + "/azure_data.json"
    with open(azure_data_file, 'w') as fp:
        json.dump(azure_data, fp)

    password_flag = ("--password=%s" % cyclecloud_admin_pw)

    print "Initializing cyclecloud CLI"
    _catch_sys_error(["/usr/local/bin/cyclecloud", "initialize", "--loglevel=debug", "--batch",
                      "--url=https://localhost", "--verify-ssl=false", "--username=root", password_flag])

    homedir = path.expanduser("~")
    pogo_config = homedir + "/.cycle/pogo.ini"
    with open(pogo_config, "w") as pogo_config_file:
        pogo_config_file.write("\n")
        pogo_config_file.write("[pogo azure-storage]\n")
        pogo_config_file.write("type = az\n")
        pogo_config_file.write("subscription_id = " + subscription_id + "\n")
        pogo_config_file.write("tenant_id = " + tenant_id + "\n")
        pogo_config_file.write("application_id = " + application_id + "\n")
        pogo_config_file.write("application_secret = " + application_secret + "\n")
        pogo_config_file.write("matches = az://" +
                          storage_account_name + "/cyclecloud" + "\n")

    print "Registering Azure subscription"
    # create the cloud provide account
    _catch_sys_error(["/usr/local/bin/cyclecloud", "account",
                      "create", "-f", azure_data_file])

    # create a pogo.ini for the admin_user so that cyclecloud project upload works
    admin_user_cycledir = "/home/" + admin_user + "/.cycle"
    if not path.isdir(admin_user_cycledir):
        makedirs(admin_user_cycledir, mode=700)

    pogo_config = admin_user_cycledir + "/pogo.ini"

    with open(pogo_config, "w") as pogo_config:
        pogo_config.write("[pogo azure-storage]\n")
        pogo_config.write("type = az\n")
        pogo_config.write("subscription_id = " + subscription_id + "\n")
        pogo_config.write("tenant_id = " + tenant_id + "\n")
        pogo_config.write("application_id = " + application_id + "\n")
        pogo_config.write("application_secret = " + application_secret + "\n")
        pogo_config.write("matches = az://" +
                          storage_account_name + "/cyclecloud" + "\n")

    _catch_sys_error(["chown", "-R", admin_user, admin_user_cycledir])
    _catch_sys_error(["chmod", "-R", "700", admin_user_cycledir])


def letsEncrypt(fqdn, location):
    # FQDN is assumed to be in the form: hostname.location.cloudapp.azure.com
    # fqdn = hostname + "." + location + ".cloudapp.azure.com"
    sleep(60)
    try:
        cmd_list = [cs_cmd, "keystore", "automatic", "--accept-terms", fqdn]
        output = check_output(cmd_list)
        print cmd_list
        print output
    except CalledProcessError as e:
        print "Error getting SSL cert from Lets Encrypt"
        print "Proceeding with self-signed cert"


def get_vm_metadata():
    metadata_url = "http://169.254.169.254/metadata/instance?api-version=2017-08-01"
    metadata_req = Request(metadata_url, headers={"Metadata": True})

    for i in range(30):
        print "Fetching metadata"
        metadata_response = urlopen(metadata_req, timeout=2)

        try:
            return json.load(metadata_response)
        except ValueError as e:
            print "Failed to get metadata %s" % e
            print "    Retrying"
            sleep(2)
            continue
        except:
            print "Unable to obtain metadata after 30 tries"
            return None

def restart_cc():
    print "Restarting CycleCloud server"
    _catch_sys_error([cs_cmd, "restart"])
    _catch_sys_error([cs_cmd, "await_startup"])
    _catch_sys_error([cs_cmd, "status"])


def modify_cs_config():
    print "Editing CycleCloud server system properties file"
    # modify the CS config files
    cs_config_file = cycle_root + "/config/cycle_server.properties"

    fh, tmp_cs_config_file = mkstemp()
    with fdopen(fh, 'w') as new_config:
        with open(cs_config_file) as cs_config:
            for line in cs_config:
                if line.startswith('webServerMaxHeapSize='):
                    new_config.write('webServerMaxHeapSize=4096M')
                elif line.startswith('webServerPort='):
                    new_config.write('webServerPort=80')
                elif line.startswith('webServerSslPort='):
                    new_config.write('webServerSslPort=443')
                elif line.startswith('webServerEnableHttps='):
                    new_config.write('webServerEnableHttps=true')
                else:
                    new_config.write(line)

    remove(cs_config_file)
    move(tmp_cs_config_file, cs_config_file)

    #Ensure that the files are created by the cycleserver service user
    _catch_sys_error(["chown", "-R", "cycle_server.", cycle_root])


def main():

    parser = argparse.ArgumentParser(description="usage: %prog [options]")

    parser.add_argument("--cyclecloudVersion",
                        dest="cyclecloudVersion",
                        #   required=True,
                        help="CycleCloud version to install")

    parser.add_argument("--downloadURL",
                        dest="downloadURL",
                        #   required=True,
                        help="Download URL for the Cycle install")

    parser.add_argument("--azureSovereignCloud",
                        dest="azureSovereignCloud",
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

    parser.add_argument("--username",
                        dest="username",
                        help="The local admin user for the CycleCloud VM")

    parser.add_argument("--hostname",
                        dest="hostname",
                        help="The short public hostname assigned to this VM (or public IP), used for LetsEncrypt")

    parser.add_argument("--acceptTerms",
                        dest="acceptTerms",
                        action="store_true",
                        help="Accept Cyclecloud terms and do a silent install")

    parser.add_argument("--password",
                        dest="password",
                        help="The password for the CycleCloud UI user")

    args = parser.parse_args()

    print("Debugging arguments: %s" % args)

    modify_cs_config()
    restart_cc()
    # create_initial_user()
    create_user_credential(args.username)

    vm_metadata = get_vm_metadata()

    if vm_metadata is not None:
        letsEncrypt(args.hostname, vm_metadata["compute"]["location"])
        try:
            register_azure_subscription(vm_metadata, args.tenantId, args.applicationId,
                            args.applicationSecret, args.username, args.azureSovereignCloud, args.acceptTerms, args.password)
        except:
            e = sys.exc_info()[0]
            print ("Error registering azure subscription. %s. Check the service principal credentials. Skipping registration." % e)
    else:
        print "Failed to get VM metadata, skipping lets encrypt and azure subscription registrations. Please perform these steps manually."

    if args.acceptTerms and args.password:
        setup_admin_user(args.username, args.password)
    else:
        reset_installation()

    clean_up()


if __name__ == "__main__":
    main()

