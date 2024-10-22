import pandas as pd
import sqlite3
import speech_recognition as sr
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from flask import Flask, request, jsonify

# Initialize SQLite connection
def get_db_connection():
    conn = sqlite3.connect('INSTRUCTOR.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Sample data for intents and phrases
data = {
    'text': [
        # Check Account Balance
        "What's my account balance?",
        "Can you show me my balance?",
        "Check my current balance.",
        "I want to see my bank balance.",
        "Show me the available balance.",
        # Transfer Money
        "Transfer money to John.",
        "Send $500 to my savings account.",
        "I need to transfer funds to my checking account.",
        "Move $1000 to account number 123456.",
        "I want to transfer money.",
        # Get Last Five Transactions
        "Show my last five transactions.",
        "What are my recent transactions?",
        "Can I see my previous transactions?",
        "Display the last five transactions.",
        "I want to check my transaction history."
    ],
    'intent': [
        "CheckBalance", "CheckBalance", "CheckBalance", "CheckBalance", "CheckBalance",
        "TransferMoney", "TransferMoney", "TransferMoney", "TransferMoney", "TransferMoney",
        "GetLastTransactions", "GetLastTransactions", "GetLastTransactions", "GetLastTransactions", "GetLastTransactions"
    ]
}

df = pd.DataFrame(data)

# Splitting the data
X = df['text']
y = df['intent']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Vectorizing text data
vectorizer = TfidfVectorizer()
X_train_vec = vectorizer.fit_transform(X_train)
X_test_vec = vectorizer.transform(X_test)

# Training the model
model1 = LogisticRegression()
model1.fit(X_train_vec, y_train)

# Making predictions
y_pred = model1.predict(X_test_vec)

# Evaluating the model
print(classification_report(y_test, y_pred))

def predict_intent(text):
    text_vec = vectorizer.transform([text])
    prediction = model1.predict(text_vec)
    return prediction[0]

# Create database and tables if they do not exist
def initialize_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Creating INSTRUCTOR table
    cursor.execute('''CREATE TABLE IF NOT EXISTS INSTRUCTOR (
        ACC_NUM INTEGER PRIMARY KEY NOT NULL, 
        FNAME VARCHAR(20), 
        LNAME VARCHAR(20), 
        ACC_TYPE VARCHAR(20),  
        BAL FLOAT
    );''')

    # Inserting values into INSTRUCTOR table if empty
    cursor.execute("SELECT COUNT(*) FROM INSTRUCTOR")
    if cursor.fetchone()[0] == 0:  # Check if the table is empty
        cursor.execute('''INSERT INTO INSTRUCTOR values 
            (123, 'lok', 'chandra', 'SAVING', 5000),
            (234, 'pawan', 'sai', 'SAVING', 10000),
            (135,'Surendra','Goud','SAVINGS',5000)
        ''')
    
    # Creating TRANSACTION_HISTORY table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS TRANSACTION_HISTORY (
            TRANSACTION_ID INTEGER PRIMARY KEY AUTOINCREMENT,
            ACC_NUM INTEGER,
            SENT_TO_NUM INTEGER,
            TRANSACTION_TYPE TEXT,
            AMOUNT FLOAT,
            TIMESTAMP DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ACC_NUM) REFERENCES INSTRUCTOR (ACC_NUM)
        );
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

# Function to send money
def send_money(cursor, from_acc_num, to_acc_num, amount):
    try:
        cursor.execute("SELECT BAL FROM INSTRUCTOR WHERE ACC_NUM = ?", (from_acc_num,))
        from_account = cursor.fetchone()

        cursor.execute("SELECT BAL FROM INSTRUCTOR WHERE ACC_NUM = ?", (to_acc_num,))
        to_account = cursor.fetchone()

        if from_account is None or to_account is None:
            return "Please enter a valid account number."

        if from_account[0] < amount:
            return "Insufficient balance."

        new_from_balance = from_account[0] - amount
        cursor.execute("UPDATE INSTRUCTOR SET BAL = ? WHERE ACC_NUM = ?", (new_from_balance, from_acc_num))

        new_to_balance = to_account[0] + amount
        cursor.execute("UPDATE INSTRUCTOR SET BAL = ? WHERE ACC_NUM = ?", (new_to_balance, to_acc_num))

        cursor.execute("INSERT INTO TRANSACTION_HISTORY (ACC_NUM, SENT_TO_NUM, TRANSACTION_TYPE, AMOUNT) VALUES (?, ?, ?, ?)",
                       (from_acc_num, to_acc_num, 'Debit', amount))  # Debit for sender
        cursor.execute("INSERT INTO TRANSACTION_HISTORY (ACC_NUM, SENT_TO_NUM, TRANSACTION_TYPE, AMOUNT) VALUES (?, ?, ?, ?)",
                       (to_acc_num, from_acc_num, 'Credit', amount))  # Credit for receiver

        cursor.connection.commit()
        return f"Transaction successful: ${amount:.2f} sent from account {from_acc_num} to account {to_acc_num}."

    except Exception as e:
        cursor.connection.rollback()
        return f"Transaction failed: {e}"

# Function to fetch transaction history
def fetch_transaction_history(cursor, acc_num):
    cursor.execute("""
        SELECT TRANSACTION_ID, TRANSACTION_TYPE, AMOUNT, SENT_TO_NUM, TIMESTAMP
        FROM TRANSACTION_HISTORY
        WHERE ACC_NUM = ?
        ORDER BY TIMESTAMP DESC
    """, (acc_num,))

    transactions = cursor.fetchall()
    if transactions:
        history = []
        for transaction in transactions:
            transaction_id, transaction_type, amount, sent_to_num, timestamp = transaction
            history.append(f"ID: {transaction_id}, Type: {transaction_type}, Amount: ${amount:.2f}, "
                          f"Sent Money To: {sent_to_num if sent_to_num else 'N/A'}, Time: {timestamp}")
        return "\n".join(history)
    else:
        return "No transaction history found for this account."

# Function to get account balance
def get_balance(cursor, acc_num):
    cursor.execute("SELECT BAL FROM INSTRUCTOR WHERE ACC_NUM = ?", (acc_num,))
    balance = cursor.fetchone()

    if balance is not None:
        return balance[0]
    else:
        return "Account number does not exist."

# Flask app routes
app = Flask(__name__)

@app.route('/intent', methods=['POST'])
def handle_intent():
    command = request.json.get('command')
    print(command)
    if command:
        intent = predict_intent(command)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if intent == "TransferMoney":
            response = process_transfer_command(command, cursor)
        elif intent == "CheckBalance":
            response = get_balance(cursor, 123)  # Replace with user account number
        elif "transaction history" in command.lower():
            response = fetch_transaction_history(cursor, 123)  # Replace with user account number
        else:
            response = "Sorry, I didn't understand that."
        
        cursor.close()
        conn.close()
        return jsonify({'response': response})
    
    return jsonify({'response': "No command received."})

# Function to process transfer command
def process_transfer_command(command, cursor):
    words = command.split()
    try:
        amount = float(words[1])  # Assumes "transfer <amount> to <name>"
        name = words[3]  # Assumes the name is the fourth word
        
        query = "SELECT ACC_NUM FROM INSTRUCTOR WHERE FNAME = ? COLLATE NOCASE;"
        cursor.execute(query, (name,))
        results = cursor.fetchall()

        if not results:
            return f"No account found with the name '{name}'."
        else:
            to_acc_num = results[0][0]  # Get the first account number
            from_acc_num = 123  # The account number you want to send from
            return send_money(cursor, from_acc_num, to_acc_num, amount)

    except (IndexError, ValueError):
        return "Please make sure to say the amount and the recipient's name correctly."

if __name__ == '__main__':
    initialize_db()  # Create database and tables if not exists
    app.run(debug=True, port=5000)

# Clean up on exit
try:
    cursor_obj.close()
    conn.close()
except Exception as e:
    print(f"Error closing database: {e}")
