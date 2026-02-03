from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ['https://www.googleapis.com/auth/drive']
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_console()

with open('token.pickle', 'wb') as token:
    pickle.dump(creds, token)

print('Token creado!')
