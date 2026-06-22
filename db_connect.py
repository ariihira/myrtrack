import os
import mysql.connector
from dotenv import load_dotenv

# Load the variables from your .env file
load_dotenv()

def connection():
    """
    Creates and returns a connection to your MySQL database.
    """
    db = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3307)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME"),
        charset='utf8mb4',
        collation='utf8mb4_general_ci'
    )

    # dictionary=True is the 'magic' that lets you use group.group_name 
    # instead of group[1] in your HTML templates.
    cursor = db.cursor(dictionary=True)
    
    return db, cursor