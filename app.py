import os
import sqlite3
import uuid
import random
import json
import qrcode
import io
import base64
from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-123')

# Render-specific database path
def get_db_path():
    return '/tmp/tambola.db' if 'RENDER' in os.environ else 'tambola.db'

def init_db():
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  device_id TEXT UNIQUE NOT NULL,
                  ticket_data TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def generate_ticket():
    ticket = [[0]*9 for _ in range(3)]
    
    for col in range(9):
        start_num = col * 10 + 1
        end_num = start_num + 9
        if col == 0:
            start_num, end_num = 1, 9
        elif col == 8:
            start_num, end_num = 80, 90
            
        numbers = random.sample(range(start_num, end_num+1), 3)
        numbers.sort()
        positions = random.sample([0,1,2], 3)
        
        for i, pos in enumerate(positions):
            ticket[pos][col] = numbers[i]
    
    return ticket

def generate_qr(url):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()

@app.route('/')
def index():
    if 'device_id' not in session:
        session['device_id'] = str(uuid.uuid4())
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE device_id = ?', [session['device_id']]).fetchone()
    db.close()
    
    if user:
        return redirect('/ticket')
    
    qr_url = request.url_root + 'register'
    qr_code = generate_qr(qr_url)
    
    return render_template('index.html', qr_code=qr_code, qr_url=qr_url)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'device_id' not in session:
        session['device_id'] = str(uuid.uuid4())
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE device_id = ?', [session['device_id']]).fetchone()
    
    if user:
        db.close()
        return redirect('/ticket')
    
    if request.method == 'POST':
        name = request.form['name'].strip()
        if name:
            ticket = generate_ticket()
            try:
                db.execute('INSERT INTO users (name, device_id, ticket_data) VALUES (?, ?, ?)',
                          [name, session['device_id'], json.dumps(ticket)])
                db.commit()
                db.close()
                return redirect('/ticket')
            except sqlite3.IntegrityError:
                db.close()
                return redirect('/ticket')
    
    db.close()
    return render_template('register.html')

@app.route('/ticket')
def show_ticket():
    if 'device_id' not in session:
        return redirect('/')
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE device_id = ?', [session['device_id']]).fetchone()
    db.close()
    
    if not user:
        return redirect('/register')
    
    ticket = json.loads(user['ticket_data'])
    return render_template('ticket.html', ticket=ticket, user_name=user['name'])

@app.route('/admin')
def admin():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    db.close()
    
    user_list = []
    for user in users:
        user_list.append({
            'name': user['name'],
            'ticket': json.loads(user['ticket_data']),
            'created_at': user['created_at']
        })
    
    return render_template('admin.html', users=user_list)

# Health check endpoint for Render
@app.route('/health')
def health():
    return 'OK'

# Initialize database when app starts
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
