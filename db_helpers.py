import os
import mysql.connector
from dotenv import load_dotenv

# load .env in same folder
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASS", "")
}

BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.getenv("BACKUP_DIR", "../backups")))
MYSQLDUMP_PATH = os.getenv("MYSQLDUMP_PATH", "mysqldump")
MYSQL_PATH = os.getenv("MYSQL_PATH", "mysql")

# ensure backup dir exists
os.makedirs(BACKUP_DIR, exist_ok=True)

def get_connection(database=None):
    cfg = DB_CONFIG.copy()
    if database:
        cfg["database"] = database
    return mysql.connector.connect(**cfg)
