import os
import requests
from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
PGDATABASE = os.getenv('PGDATABASE')
PGHOST = os.getenv('PGHOST')
PGPASSWORD = os.getenv('PGPASSWORD')
PGUSER = os.getenv('PGUSER')

REDIRECT_URI = 'https://followchecker.naqa-aws.com/callback'        # http://localhost:5000/callback
SCOPE = 'user:read:follows'
AUTH_URL = 'https://id.twitch.tv/oauth2/authorize'
TOKEN_URL = 'https://id.twitch.tv/oauth2/token'
API_URL = 'https://api.twitch.tv/helix'

# Construct database URLs
DATABASE_URL = f'postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}/{PGDATABASE}'

# Create Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)     # Requis pour le support des sessions

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define FollowedStreamer model
class FollowedStreamer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)
    broadcaster_name = db.Column(db.String(50), nullable=False)
    followed_at = db.Column(db.Date, nullable=False)

# Create database tables
with app.app_context():
    db.create_all()

@app.route('/', methods=['GET', 'POST'])
def index() -> str:
    """Render the main page."""
    error = None
    STATE = os.urandom(16).hex()        # Permet de se protéger contre les attaques CSRF
    if request.method == 'POST':
        session['username'] = request.form.get('username')       # Stocke le nom d'utilisateur dans la session
        if session['username']:
            auth_url = f'{AUTH_URL}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope={SCOPE}&state={STATE}'
            return redirect(auth_url)       # Redirige l'utilisateur vers la page d'autorisation twitch
        else:
            error = "ERROR : You must enter a username."
    return render_template('index.html', error=error)       # error=error Permet d'utiliser la variable error dans le template

@app.route('/callback', methods=['GET'])
def callback() -> str:
    """Handle the callback from Twitch."""
    if 'username' not in session:
        return redirect(url_for('index'))
    code = request.args.get('code')     # Récupère le code d'autorisation de Twitch dans l'URL de redirection
    if code:
        try:
            access_token = get_access_token(code)
            user_id = get_user_id(session['username'], access_token)
            followed_streamers = get_followed_streamers(user_id, access_token)
            if followed_streamers is None:
                return "An error occurred while retrieving followed streamers."
            return render_template('streamers.html', streamers=followed_streamers)
            
        except KeyError:        # Si actualisation de la page, on retourne à l'index.html
            return redirect(url_for('index'))
    else:
        return redirect(url_for('index'))

def get_access_token(code):
    """Exchange the code for an access token."""
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI
    }
    response = requests.post(TOKEN_URL, data=data)      # data=data permet de passer les données de formulaire dans une requete POST via requests
    return response.json()['access_token']

def get_user_id(username, access_token):
    """Get the user ID from the username."""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Client-Id': CLIENT_ID
    }
    response = requests.get(f'{API_URL}/users?login={username}', headers=headers)       # headers=headers permet de passer les données de formulaire dans une requete GET via requests
    data = response.json()
    if 'data' in data and data['data']:     # Vérifie si la clé 'data' est présente dans le dictionnaire et si elle n'est pas vide
        return data['data'][0]['id']
    else:
        return None

def get_followed_streamers(user_id, access_token):
    """Get the list of followed streamers."""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Client-Id': CLIENT_ID
    }
    url = f'{API_URL}/channels/followed?user_id={user_id}'
    followed_streamers = []
    while url:
        response = requests.get(url, headers=headers)
        data = response.json()
        if 'data' in data:
            for streamer in data['data']:
                followed_streamers.append({
                    'broadcaster_name': streamer['broadcaster_name'],
                    'followed_at': streamer['followed_at'].split('T')[0]        # format complet : 2024-07-21T09:34:32Z (on ne garde que la date)
                })
                # Save to the database
                followed_streamer = FollowedStreamer(
                    user_id=user_id,
                    broadcaster_name=streamer['broadcaster_name'],
                    followed_at=streamer['followed_at'].split('T')[0]
                )
                db.session.add(followed_streamer)
            db.session.commit()
        else:
            return None
        url = None
        if 'pagination' in data and 'cursor' in data['pagination']:     # Continue à faire des requêtes à l'API Twitch jusqu'à ce qu'il n'y ait plus de curseur         
            url = f'{API_URL}/channels/followed?user_id={user_id}&after={data["pagination"]["cursor"]}'
    return followed_streamers

if __name__ == '__main__':
    app.run(host='0.0.0.0')