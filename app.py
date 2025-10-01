import sqlite3
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS  # <-- 1. IMPORT THE LIBRARY
import os

# --- 1. INITIAL SETUP ---
app = Flask(__name__)
CORS(app)  # <-- 2. ENABLE CORS FOR YOUR APP
DATABASE = 'database.db'

# --- Database Helper Functions ---

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DATABASE)
    # This line allows you to access columns by name (like a dictionary)
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


# --- 3. API ENDPOINTS (User Management) ---

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not all(key in data for key in ['name', 'email', 'password', 'role']):
        return jsonify({'message': 'Missing required fields!'}), 400

    # Check if user already exists
    user = query_db("SELECT * FROM Users WHERE email = ?", (data['email'],), one=True)
    if user:
        return jsonify({'message': 'Email already registered!'}), 409

    hashed_password = generate_password_hash(data['password'], method='pbkdf2:sha256')
    
    # Insert new user into the database
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


# --- 4. API ENDPOINTS (Notes and Purchases) ---

@app.route('/notes', methods=['POST'])
def upload_note():
    data = request.get_json()
    if not all(key in data for key in ['title', 'subject', 'price', 'seller_id']):
        return jsonify({'message': 'Missing required fields for note upload!'}), 400
    
    # Check if the user is a seller
    seller = query_db("SELECT * FROM Users WHERE user_id = ? AND role = 'seller'", (data['seller_id'],), one=True)
    if not seller:
        return jsonify({'message': 'Seller not found or user is not a seller!'}), 404

    execute_db("INSERT INTO Notes (title, subject, description, price, seller_id, file_link, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
               (data['title'], data['subject'], data.get('description', ''), data['price'], data['seller_id'], 'uploads/placeholder.pdf'))

    return jsonify({'message': 'Note uploaded successfully and is pending admin approval.'}), 201

@app.route('/notes', methods=['GET'])
def browse_notes():
    notes_list = query_db("SELECT note_id, title, subject, description, price, seller_id FROM Notes WHERE status = 'approved'")
    # Convert list of Row objects to a list of dictionaries
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

    # This INSERT will automatically fire the SQL trigger you created
    execute_db("INSERT INTO Transactions (buyer_id, note_id, amount) VALUES (?, ?, ?)",
               (data['buyer_id'], data['note_id'], note_to_buy['price']))

    return jsonify({'message': 'Purchase successful!', 'download_link': note_to_buy['file_link']}), 200


# --- 5. API ENDPOINTS (Admin Functionality) ---

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


# --- 6. MAIN EXECUTION ---
if __name__ == '__main__':
    # You don't need db.create_all() anymore. The database schema
    # is now fully managed by your SQL commands.
    app.run(debug=True)

