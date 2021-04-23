#!/usr/bin/env python

"""
Simple script to manage Zoom users via API. 

Usage: 
    python zoom.py -f input.json -o output.csv

Options:
    -h --help
    -f --file	Input file (required)
    -o --out	Output file (required)

Environment specific script constants are stored in this 
config file: zoom_settings.py
    
Input:

Input file is expected to be in JSON format (e.g. input.json).
with these 6 required data fields:
{
    "useractions": [
        {
            "action": "delete",
            "username": "testuserj",
            "newusername": "testuserj",
            "loginDisabled": "False",
            "givenName": "John",
            "sn": "Testuser"
        }
    ] 
}
where action can be update/delete/listusers. 
NOTE: Update action removes the PRO license from the user if 
"loginDisabled" is set to "True".

Output:

Output file (e.g. output.csv) will have these fields:

action, username, result (ERROR/SUCCESS: reason)

Logging:

Script creates a detailed zoom.log

All errors are also printed to stdout.

Author: A. Ablovatski
Email: ablovatski@dgmail.com
Date: 09/09/2020
"""

from __future__ import print_function
import sys
import traceback
import json
import csv
import argparse
import logging
import textwrap
import jwt
import requests
from time import time

def main(argv):
    """This is the main body of the script"""
    
    # Setup the log file
    logging.basicConfig(
        filename='zoom.log',level=logging.DEBUG, 
        format='%(asctime)s, %(levelname)s: %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S')

    # Get Zoom creds and other constants from this settings file
    config_file = 'zoom_settings.py'
    
    if not readConfig(config_file):
        logging.error("unable to parse the settings file")
        sys.exit()
    
    # Parse script arguments
    parser = argparse.ArgumentParser()                                               

    parser.add_argument("--file", "-f", type=str, required=True, 
                        help="Input JSON file with user actions and params")
    parser.add_argument("--out", "-o", type=str, required=True, 
                        help="Output file with results of Zoom user actions")

    try:
        args = parser.parse_args()
        
    except SystemExit:
        logging.error("required arguments missing - " \
                        "provide input and output file names")
        sys.exit()

    # Read input from json file
    in_file = args.file
    # Write output to csv file
    out_file = args.out
    
    try:
        f_in = open(in_file, 'rb')
        logging.info("opened input file: {0}".format(in_file))
        f_out = open(out_file, 'wb')
        logging.info("opened output file: {0}".format(out_file))
        reader = json.load(f_in)
        writer = csv.writer(f_out)
        writer.writerow(['action','username','result'])

        for row in reader["useractions"]:
            result = ''
            # Select what needs to be done
            if row["action"] == 'update':
                result = update(str(row["username"]), str(row["newusername"]), 
                                str(row["loginDisabled"]), 
                                str(row["givenName"]), str(row["sn"]))
            elif row["action"] == 'delete':
                result = delete(str(row["username"]))
            elif row["action"] == 'listusers':
                result = listusers()
            else:
                print("ERROR: unrecognized action: {0}".format(row["action"]))
                logging.error("unrecognized action: {0}".format(row["action"]))
                result = "ERROR: Unrecognized action."
            
            # Write the result to the output csv file
            writer.writerow([row["action"], row["username"], result])
            
    except IOError:
        print("ERROR: Unable to open input/output file!")
        logging.critical("file not found: {0} or {1}".format(in_file, out_file))
        
    except Exception as e:
        traceb = sys.exc_info()[-1]
        stk = traceback.extract_tb(traceb, 1)
        fname = stk[0][3]
        print("ERROR: unknown error while processing line '{0}': " \
                "{1}".format(fname,e))
        logging.critical("unknown error while processing line '{0}': " \
                "{1}".format(fname,e))
        
    finally:
        f_in.close()
        logging.info("closed input file: {0}".format(in_file))
        f_out.close()
        logging.info("closed output file: {0}".format(out_file))
        
    return


def update(username, newusername, loginDisabled, givenName, sn):
    """This function updates a user (loginDisable attribute
    only adds/removes the PRO license)"""

    # Check if any of the arguments are missing
    params = locals()
    
    for _item in params:
        if str(params[_item]) == "":
            print("ERROR: unable to update user {0} because {1} is missing " \
                    "a value".format(username, _item))
            logging.error("unable to update user {0} because {1} is missing " \
                            "a value".format(username, _item))
            result = "ERROR: Missing an expected input value for " \
                        + _item + " in input file."
            return result

    
    # Create user email
    upn = username + "@" + "xyz.com"
    id = findUserId(upn)
    
    if not id:
        print("ERROR: user does not exist in Zoom: {0}".format(username))
        logging.error("user does not exist in Zoom: {0}".format(username))
        result = "ERROR: user could not be found in Zoom!"
        return result
    
    # If newusername is diferent
    if username != newusername:
        
        # Rename the user
        try:
            
            # Check if the new user name already exists
            upnew = newusername + "@" + "xyz.com"
            
            if findUserId(upnew):
                print("ERROR: cannot rename user - user already exists: {0}" \
                        .format(newusername))
                logging.error("cannot rename user - user already exists: {0}" \
                                .format(newusername))
                result = "ERROR: username already taken!"
                return result
            
            # Connect to Zoom API
            # Set the header
            headers = {'authorization': 'Bearer %s' % generateToken(),
                   'content-type': 'application/json'}
                   
            # Do the renaming
            payload = {"first_name": givenName, "last_name": sn}
            response = requests.patch('https://api.zoom.us/v2/users/' 
                                + str(id), json=payload, headers=headers)
            # update user email address
            payload = {"email": upnew}
            response = requests.put('https://api.zoom.us/v2/users/' 
                        + str(id) + '/email', json=payload, headers=headers)
            # Check if the request succeeded
            if response.status_code != 204:
                logging.error("user {0} was not renamed in Zoom".format(upn))
                print("ERROR: Could not rename user in Zoom: {0}".format(upn))
                result = "ERROR: could not rename Zoom user."
            else:
                # Log user update
                logging.info("user renamed in Zoom: {0}".format(username))
                print("SUCCESS: User {0} renamed in Zoom".format(username))
                result = "SUCCESS: user was renamed in Zoom."

            
        except Exception as e:
            print("ERROR: Could not rename user in Zoom: {0}".format(e))
            logging.error("Zoom user rename failed for: {0}: {1}" \
                        .format(username,e))
            result = "ERROR: Could not rename Zoom user."
            return result
    
    # User type 1 - basic, 2 - licensed
    if loginDisabled == "True":
        type = "1"
    else:
        type = "2"

    # License or de-license the user
    try:
        # Set the header
        headers = {'authorization': 'Bearer %s' % generateToken(),
               'content-type': 'application/json'}
        
        # Connect to Zoom API
        payload = {"type": type}
        response = requests.patch('https://api.zoom.us/v2/users/' 
                            + str(id), json=payload, headers=headers)

        # Check if the request succeeded
        if response.status_code != 204:
            logging.error("user {0} was not updated in Zoom".format(upn))
            print("ERROR: Could not update user in Zoom: {0}".format(upn))
            result = "ERROR: could not update Zoom user."
        else:
            # Log user update
            logging.info("user updated in Zoom: {0}".format(username))
            print("SUCCESS: User {0} updated in Zoom".format(username))
            result = "SUCCESS: user was updated in Zoom."

    except Exception as e:
        print("ERROR: Could not update user in Zoom: {0}".format(e))
        logging.error("Zoom update failed for: {0}: {1}".format(username,e))
        result = "ERROR: Could not update Zoom user."
        return result
    
    return result


def delete(username):
    """This function deletes a user from Zoom"""

    # Check if the argument is missing
    if str(username) == "":
        print("ERROR: unable to delete user because username argument " \
                "is missing a value")
        logging.error("unable to delete user because username argument " \
                        "is missing a value")
        result = "ERROR: Missing an expected input value for username " \
                    "in input file."
        return result

    # Build user email
    upn = username + "@" + "xyz.com"
    id = findUserId(upn)
    
    if not id:
        print("ERROR: user does not exist in Zoom: {0}".format(username))
        logging.error("user does not exist in Zoom: {0}".format(username))
        result = "ERROR: user could not be found in Zoom!"
        return result
        
    # Delete user if all is OK
    try:
        # Build header
        headers = {'authorization': 'Bearer %s' % generateToken(),
               'content-type': 'application/json'}
        
        # Connect to Zoom API
        response = requests.delete('https://api.zoom.us/v2/users/' 
                            + str(id), headers=headers)

        if response.status_code != 204:
            logging.error("user was not deleted in Zoom: {0}" \
                    .format(username))
            print("ERROR: User {0} was not deleted in Zoom" \
                    .format(username))
            result = "ERROR: could not delete user in Zoom."
        else:
            logging.info("user deleted in Zoom: {0}".format(username))
            print("SUCCESS: User {0} deleted in Zoom".format(username))
            result = "SUCCESS: user deleted in Zoom."

    except Exception as e:
        print("ERROR: unknown error while deleting user: {0}".format(e))
        logging.error("unknown error while deleting user {0}: {1}" \
                        .format(username,e))
        result = "ERROR: Could not delete Zoom user."
    
    return result


def listusers():
    """This function lists all users in Zoom"""
    
    # Get the list of all users in Zoom
    try:
        # Build header
        headers = {'authorization': 'Bearer %s' % generateToken(),
               'content-type': 'application/json'}
                
        # Need to check if we need to get next page of results
        currentPage = 1
        PagesLeft = 1

        while PagesLeft:
            # Connect to Zoom API to pull currentPage
            response = requests.get('https://api.zoom.us/v2/users?page_size=300' 
                        + "&page_number=" + str(currentPage), headers=headers)

            if response.status_code != 200:
                logging.error("did not get list of Zoom users")
                print("ERROR: did not get list of Zoom users")
                result = "ERROR: did not get list of Zoom users."
                break
            else:
                data = response.text
                jsondata = json.loads(data)
                if currentPage == 1:
                    print("id,first_name,last_name,email,type,status")
                    
                for user in jsondata['users']:
                    print(u','.join((user['id'], user['first_name'], 
                        user['last_name'], user['email'], str(user['type']), 
                        user['status'])).encode('utf-8'))

                currentPage += 1
                PagesLeft = jsondata['page_count'] - jsondata['page_number']
            
            logging.info("got the list of Zoom users")
            result = "SUCCESS: got the list of Zoom users."

    except Exception as e:
        print("ERROR: unknown error while getting the list of Zoom users: {0}" \
                .format(e))
        logging.error("unknown error while getting the list of Zoom users: {0}" \
                .format(e))
        result = "ERROR: Could not get the list of Zoom users."
    
    return result

    
def readConfig(config_file):
    """Function to import the config file"""
    
    if config_file[-3:] == ".py":
        config_file = config_file[:-3]
    zoomsettings = __import__(config_file, globals(), locals(), [])
    
    # Read settings and set globals
    try: 

        global API_KEY
        global API_SEC

        API_KEY = zoomsettings.API_KEY
        API_SEC = zoomsettings.API_SEC

    except Exception as e:
        logging.error("unable to parse settings file")
        print("ERROR: unable to parse the settings file: {0}".format(e))
        return False
        
    return True


def generateToken():
    token = jwt.encode(
        # Create a payload of the token containing API Key & 
        # expiration time (5 min)
        {"iss": API_KEY, "exp": time() + 300},
        # Secret used to generate token signature
        API_SEC,
        # Specify the hashing alg
        algorithm='HS256'
        # Convert token to utf-8
    ).decode('utf-8')

    return token


def findUserId(upn):
    """Do a quick check if the user already exists"""
        
    # Build header
    headers = {'authorization': 'Bearer %s' % generateToken(),
           'content-type': 'application/json'}
    
    # Connect to Zoom API
    # GET https://api.zoom.us/v2/users/email
    try:

        response = requests.get('https://api.zoom.us/v2/users/' 
                        + upn, headers=headers)

        if response.status_code == 200:
            data = response.text
            if upn not in data:
                return False
            
            data = str(data).split(",")
            id_lst = data[0].split(":")

            if id_lst[0] == '{"id"':
                id = id_lst[1]
                id = id.replace('"', '')
            else:
                id = False
        elif response.status_code == 404:
            id = False
        else:
            id = False
            print("ERROR: Zoom service did not respond correctly")
            logging.error("Zoom service returned: {0}" \
                            .format(response.status_code))

    except Exception as e:
        print("ERROR: problem with user search in Zoom: {0}".format(e))
        logging.error("problem searching for {0} in Zoom: {1}".format(upn,e))
        
    return id


if __name__ == "__main__":
    main(sys.argv)
