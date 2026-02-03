from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ['https://www.googleapis.com/auth/drive']
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)

auth_url, _ = flow.authorization_url(prompt='consent')

print('\n1. Abre esta URL en tu navegador:\n')
print(auth_url)
print('\n2. Autoriza y copia la URL completa de la pagina final')
print('   (aunque diga que no se puede conectar)\n')

redirect_url = input('Pega aqui la URL completa: ')

flow.fetch_token(authorization_response=redirect_url)

with open('token.pickle', 'wb') as token:
    pickle.dump(flow.credentials, token)

print('\nToken creado!')
