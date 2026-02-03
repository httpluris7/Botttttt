from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ['https://www.googleapis.com/auth/drive']
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)

auth_url, _ = flow.authorization_url(prompt='consent')

with open('url.txt', 'w') as f:
    f.write(auth_url)

print('URL guardada en url.txt')
print('Ejecuta: cat url.txt')

redirect_url = input('Pega aqui la URL completa: ')

flow.fetch_token(authorization_response=redirect_url)

with open('token.pickle', 'wb') as token:
    pickle.dump(flow.credentials, token)

print('Token creado!')
