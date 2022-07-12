import msal
import sys
import pyodbc
import struct
from msal_extensions import *
import pandas as pd

def query(shortname, sql):

    username = shortname.upper()+'@equinor.com' #SHORTNAME@equinor.com -- short name should be in Capital
    tenantID = '3aa4a235-b6e2-48d5-9195-7fcf05b459b0'
    authority = 'https://login.microsoftonline.com/' + tenantID
    clientID = '9ed0d36d-1034-475a-bdce-fa7b774473fb'
    scopes = ['https://database.windows.net/.default']
    result = None
    accounts = None 
    myAccount = None
    idTokenClaims = None

    def msal_persistence(location, fallback_to_plaintext=False):
        """Build a suitable persistence instance based your current OS"""
        if sys.platform.startswith('win'):
            return FilePersistenceWithDataProtection(location)
        if sys.platform.startswith('darwin'):
            return KeychainPersistence(location, "my_service_name", "my_account_name")
        return FilePersistence(location)

    def msal_cache_accounts(clientID, authority):
        # Accounts
        persistence = msal_persistence("token_cache.bin")
        print("Is this MSAL persistence cache encrypted?", persistence.is_encrypted)
        cache = PersistedTokenCache(persistence)
        
        app = msal.PublicClientApplication(client_id=clientID, authority=authority, token_cache=cache)
        accounts = app.get_accounts()
        return accounts

    def msal_delegated_interactive_flow(scopes, prompt=None, login_hint=None, domain_hint=None):
        persistence = msal_persistence("token_cache.bin")
        cache = PersistedTokenCache(persistence)
        app = msal.PublicClientApplication(clientID, authority=authority, token_cache=cache)
        result = app.acquire_token_interactive(scopes=scopes, prompt=prompt, login_hint=login_hint, domain_hint=domain_hint )
        return result

    def msal_delegated_refresh(clientID, scopes, authority, account):
        persistence = msal_persistence("token_cache.bin")
        cache = PersistedTokenCache(persistence)
        
        app = msal.PublicClientApplication(
            client_id=clientID, authority=authority, token_cache=cache)
        result = app.acquire_token_silent_with_error(
            scopes=scopes, account=account)
        return result

    def connect_to_db(result):
        global conn

        try:
            # Request
            SQL_COPT_SS_ACCESS_TOKEN = 1256 
            server = 'pdmprod.database.windows.net'
            database="pdm"
            driver = 'ODBC Driver 18 for SQL Server'
            connection_string = 'DRIVER='+driver+';SERVER='+server+';DATABASE='+database

            #get bytes from token obtained
            tokenb = bytes(result['access_token'], 'UTF-8')
            exptoken = b'';
            for i in tokenb:
                exptoken += bytes({i});
                exptoken += bytes(1);

            tokenstruct = struct.pack("=i", len(exptoken)) + exptoken;
            print('Connecting toDatabase')
            conn = pyodbc.connect(connection_string, attrs_before = { SQL_COPT_SS_ACCESS_TOKEN:tokenstruct })

        except Exception as err:
            print('Connection to db : ', err)    

    accounts = msal_cache_accounts(clientID, authority)

    if accounts:
        for account in accounts:
            if account['username'] == username:
                myAccount = account
                print("Found account in MSAL Cache: " + account['username'])
                print("Attempting to obtain a new Access Token using the Refresh Token")
                result = msal_delegated_refresh(clientID, scopes, authority, myAccount)

                if result is None:
                    # Get a new Access Token using the Interactive Flow
                    print("Interactive Authentication required to obtain a new Access Token.")
                    result = msal_delegated_interactive_flow(scopes=scopes, domain_hint=tenantID)   
    else:
        # No accounts found in the local MSAL Cache
        # Trigger interactive authentication flow
        print("First authentication")
        result = msal_delegated_interactive_flow(scopes=scopes, domain_hint=tenantID)
        idTokenClaims = result['id_token_claims']
        username = idTokenClaims['preferred_username']



    if result:
        if result["access_token"]:
            connect_to_db(result)

            #  Query Database
            print('Querying database')
            #cursor = conn.cursor()
            #cursor.execute('SELECT top 1 * FROM [PDMVW].wb_prod_day')
            
            #for i in cursor:
            #    print(i)
            df = pd.read_sql(sql, conn)
            return df