import sqlite3
import os
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_cors import CORS

# --- 1. INITIAL SETUP ---
app = Flask(__name__)
CORS(app) 
DATABASE = 'database.db'

# Configuration for file uploads
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Database Helper Functions ---

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def query_db(query, args=(), one=False):
    """Helper function to run SELECT queries."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    """Helper function to run INSERT, UPDATE, or DELETE queries."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    conn.close()

# --- API ENDPOINTS (User Management) ---

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not all(key in data for key in ['name', 'email', 'password', 'role']):
        return jsonify({'message': 'Missing required fields!'}), 400

    user = query_db("SELECT * FROM Users WHERE email = ?", (data['email'],), one=True)
    if user:
        return jsonify({'message': 'Email already registered!'}), 409

    hashed_password = generate_password_hash(data['password'], method='pbkdf2:sha256')
    
    execute_db("INSERT INTO Users (name, email, password, role) VALUES (?, ?, ?, ?)",
               (data['name'], data['email'], hashed_password, data['role']))

    return jsonify({'message': 'New user created successfully!'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not all(key in data for key in ['email', 'password']):
        return jsonify({'message': 'Missing email or password!'}), 400

    user = query_db("SELECT * FROM Users WHERE email = ?", (data['email'],), one=True)
    
    if not user or not check_password_hash(user['password'], data['password']):
        return jsonify({'message': 'Login failed! Check email and password.'}), 401
    
    return jsonify({
        'message': 'Login successful!',
        'user': {'user_id': user['user_id'], 'name': user['name'], 'email': user['email'], 'role': user['role']}
    }), 200

# --- API ENDPOINTS (Notes and Purchases) ---

@app.route('/notes', methods=['POST'])
def upload_note():
    required_fields = ['title', 'subject', 'price', 'seller_id']
    if not all(field in request.form for field in required_fields):
        return jsonify({'message': 'Missing required form fields!'}), 400
    if 'note_file' not in request.files:
        return jsonify({'message': 'No file part in the request!'}), 400

    file = request.files['note_file']
    
    if file.filename == '':
        return jsonify({'message': 'No selected file!'}), 400

    title = request.form['title']
    subject = request.form['subject']
    price = request.form['price']
    seller_id = request.form['seller_id']
    description = request.form.get('description', '')

    seller = query_db("SELECT * FROM Users WHERE user_id = ? AND role = 'seller'", (seller_id,), one=True)
    if not seller:
        return jsonify({'message': 'Seller not found or user is not a seller!'}), 404

    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        execute_db("INSERT INTO Notes (title, subject, description, price, seller_id, file_link, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                   (title, subject, description, price, seller_id, file_path))

        return jsonify({'message': 'Note uploaded successfully and is pending admin approval.'}), 201

    return jsonify({'message': 'File error occurred!'}), 400

@app.route('/notes', methods=['GET'])
def browse_notes():
    notes_list = query_db("SELECT note_id, title, subject, description, price, seller_id FROM Notes WHERE status = 'approved'")
    notes_dict = [dict(note) for note in notes_list]
    return jsonify({'notes': notes_dict})

@app.route('/purchase', methods=['POST'])
def purchase_note():
    data = request.get_json()
    if not all(key in data for key in ['buyer_id', 'note_id']):
        return jsonify({'message': 'Buyer ID and Note ID are required!'}), 400
        
    note_to_buy = query_db("SELECT price, file_link FROM Notes WHERE note_id = ? AND status = 'approved'", (data['note_id'],), one=True)
    if not note_to_buy:
        return jsonify({'message': 'Note not found or not available for purchase!'}), 404

    execute_db("INSERT INTO Transactions (buyer_id, note_id, amount) VALUES (?, ?, ?)",
               (data['buyer_id'], data['note_id'], note_to_buy['price']))

    filename = os.path.basename(note_to_buy['file_link']) 
    download_url = f"/uploads/{filename}"

    return jsonify({'message': 'Purchase successful!', 'download_link': download_url}), 200

# --- Endpoint to serve/download the uploaded files ---
@app.route('/uploads/<path:filename>', methods=['GET'])
def download_file(filename):
    """Serves a file from the upload directory."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# --- API ENDPOINTS (Admin Functionality) ---

@app.route('/admin/notes/pending', methods=['GET'])
def get_pending_notes():
    pending_notes = query_db("SELECT note_id, title, subject, seller_id FROM Notes WHERE status = 'pending'")
    return jsonify({'pending_notes': [dict(note) for note in pending_notes]})

@app.route('/admin/notes/<int:note_id>/approve', methods=['PUT'])
def approve_note(note_id):
    execute_db("UPDATE Notes SET status = 'approved' WHERE note_id = ?", (note_id,))
    return jsonify({'message': f'Note {note_id} has been approved.'})

@app.route('/admin/notes/<int:note_id>/reject', methods=['PUT'])
def reject_note(note_id):
    execute_db("UPDATE Notes SET status = 'rejected' WHERE note_id = ?", (note_id,))
    return jsonify({'message': f'Note {note_id} has been rejected.'})

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    app.run(debug=True)
