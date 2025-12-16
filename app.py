from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import mysql.connector
import os
import subprocess
from datetime import datetime

# ================= APP SETUP =================
app = Flask(__name__, static_url_path="", static_folder=".")
CORS(app)

# ================= CONFIG =================
MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = ""   # add password if you have one

# XAMPP PATHS (IMPORTANT)
MYSQL_PATH = r"C:\Xampps\mysql\bin\mysql.exe"
MYSQLDUMP_PATH = r"C:\Xampps\mysql\bin\mysqldump.exe"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_FOLDER = os.path.join(BASE_DIR, "backups")
os.makedirs(BACKUP_FOLDER, exist_ok=True)

# ================= HELPER =================
def get_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD
    )

# ================= FRONTEND =================
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

# ================= LIST DATABASES =================
# ================= LIST DATABASES =================
@app.route("/list_databases")
def list_databases():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SHOW DATABASES")
    all_dbs = [db[0] for db in cursor.fetchall()]

    databases = []
    for db in all_dbs:
        if db in ("information_schema", "mysql", "performance_schema", "sys"):
            continue

        cursor2 = conn.cursor()
        # Get number of tables
        cursor2.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
            (db,)
        )
        tables_count = cursor2.fetchone()[0]

        # Get database size in KB
        cursor2.execute("""
            SELECT SUM(data_length + index_length) 
            FROM information_schema.tables 
            WHERE table_schema = %s
        """, (db,))
        size_bytes = cursor2.fetchone()[0] or 0
        size_kb = round(size_bytes / 1024, 2)

        cursor2.close()

        databases.append({
            "name": db,
            "tables": tables_count,
            "size_kb": size_kb
        })

    cursor.close()
    conn.close()

    return jsonify({"databases": databases})

# ================= LIST TABLES IN DATABASE =================
@app.route("/list_tables", methods=["POST"])
def list_tables():
    data = request.json
    database = data.get("database")
    
    if not database:
        return jsonify({"success": False, "error": "Database name required"})

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database
        )
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        return jsonify({"success": True, "tables": tables})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()


# ================= CREATE DATABASE =================
@app.route("/create_db", methods=["POST"])
def create_db():
    name = request.json.get("database")
    if not name:
        return jsonify({"success": False, "error": "Database name required"})

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE DATABASE `{name}`")
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()

# ================= CREATE TABLE =================
@app.route("/create_table", methods=["POST"])
def create_table():
    data = request.json
    database = data.get("database")
    table = data.get("table")
    columns = data.get("columns")

    if not database or not table or not columns:
        return jsonify({"success": False, "error": "Missing parameters"})

    column_defs = []
    primary_keys = []
    auto_increment_used = False

    for col in columns:
        name = col["name"]
        col_type = col["type"].upper()
        length = col.get("length")

        # Base column definition
        col_def = f"`{name}` {col_type}"

        if col_type == "VARCHAR":
            col_def += f"({length or 255})"

        # AUTO_INCREMENT rules
        if col.get("auto_increment"):
            if col_type not in ("INT", "BIGINT"):
                return jsonify({
                    "success": False,
                    "error": f"AUTO_INCREMENT not allowed on {col_type} column '{name}'"
                })
            if auto_increment_used:
                return jsonify({
                    "success": False,
                    "error": "Only one AUTO_INCREMENT column is allowed"
                })
            auto_increment_used = True
            col_def += " AUTO_INCREMENT"

        column_defs.append(col_def)

        if col.get("primary"):
            primary_keys.append(f"`{name}`")

    # AUTO_INCREMENT must be PRIMARY KEY
    if auto_increment_used and not primary_keys:
        return jsonify({
            "success": False,
            "error": "AUTO_INCREMENT column must be PRIMARY KEY"
        })

    if primary_keys:
        column_defs.append(f"PRIMARY KEY ({', '.join(primary_keys)})")

    create_sql = f"""
        CREATE TABLE `{table}` (
            {', '.join(column_defs)}
        )
    """

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database
        )
        cursor = conn.cursor()
        cursor.execute(create_sql)
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()

# ================= RENAME TABLE =================
@app.route("/rename_table", methods=["POST"])
def rename_table():
    data = request.json
    database = data.get("database")
    old_name = data.get("old_name")
    new_name = data.get("new_name")

    if not database or not old_name or not new_name:
        return jsonify({"success": False, "error": "Missing parameters"})

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database
        )
        cursor = conn.cursor()
        cursor.execute(f"RENAME TABLE `{old_name}` TO `{new_name}`")
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()

# ================= DROP TABLE =================
@app.route("/drop_table", methods=["POST"])
def drop_table():
    data = request.json
    database = data.get("database")
    table = data.get("table")

    if not database or not table:
        return jsonify({"success": False, "error": "Database and table required"})

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database
        )
        cursor = conn.cursor()
        cursor.execute(f"DROP TABLE `{table}`")
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()



# ================= DROP DATABASE =================
@app.route("/drop_db", methods=["POST"])
def drop_db():
    name = request.json.get("database")
    if not name:
        return jsonify({"success": False, "error": "Database name required"})

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DROP DATABASE `{name}`")
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()

# ================= BACKUP DATABASE =================
@app.route("/backup_db", methods=["POST"])
def backup_db():
    dbname = request.json.get("database")
    if not dbname:
        return jsonify({"success": False, "error": "Database name required"})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(
        BACKUP_FOLDER,
        f"{dbname}_{timestamp}.sql"
    )

    cmd = [MYSQLDUMP_PATH, f"-u{MYSQL_USER}"]
    if MYSQL_PASSWORD:
        cmd.append(f"-p{MYSQL_PASSWORD}")
    cmd.append(dbname)

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                check=True
            )
        return jsonify({
            "success": True,
            "file": os.path.basename(output_file)
        })
    except subprocess.CalledProcessError as e:
        return jsonify({
            "success": False,
            "error": e.stderr.decode()
        })

# ================= LIST BACKUPS =================
@app.route("/list_backups")
def list_backups():
    backups = []
    for f in os.listdir(BACKUP_FOLDER):
        if f.endswith(".sql"):
            path = os.path.join(BACKUP_FOLDER, f)
            backups.append({
                "file": f,
                "size_kb": round(os.path.getsize(path) / 1024, 2),
                "modified": datetime.fromtimestamp(
                    os.path.getmtime(path)
                ).strftime("%Y-%m-%d %H:%M:%S")
            })
    return jsonify({"backups": backups})

# ================= RESTORE DATABASE =================
# ================= RESTORE BACKUP =================
@app.route("/restore", methods=["POST"])
def restore():
    data = request.json
    file = data.get("file")
    target_db = data.get("target_db")
    
    if not file or not target_db:
        return jsonify({"success": False, "error": "Missing file or target DB"})

    filepath = os.path.join(BACKUP_FOLDER, file)
    if not os.path.exists(filepath):
        return jsonify({"success": False, "error": "Backup file not found"})

    # CREATE DATABASE FIRST
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{target_db}`")
    conn.commit()
    cursor.close()
    conn.close()

    # RUN MYSQL RESTORE
    mysql_path = r"C:\Xampps\mysql\bin\mysql.exe"
    cmd = f'"{mysql_path}" -u{MYSQL_USER} {target_db} < "{filepath}"'

    try:
        subprocess.run(cmd, shell=True, check=True)

        # DELETE THE BACKUP FILE AFTER RESTORE
        os.remove(filepath)

        return jsonify({"success": True, "message": f"Restored to {target_db} and backup removed."})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": str(e)})

# ================= DELETE BACKUP =================
@app.route("/delete_backup", methods=["POST"])
def delete_backup():
    data = request.json
    file = data.get("file")

    if not file:
        return jsonify({"success": False, "error": "No backup file specified"})

    filepath = os.path.join(BACKUP_FOLDER, file)
    if not os.path.exists(filepath):
        return jsonify({"success": False, "error": "Backup file not found"})

    try:
        os.remove(filepath)
        return jsonify({"success": True, "message": f"Backup {file} deleted."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ================= LIST USERS =================
# ================= LIST USERS =================
@app.route("/list_users")
def list_users():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT User, Host FROM mysql.user")
    users_raw = cursor.fetchall()

    users = []
    for u in users_raw:
        cursor.execute(f"SHOW GRANTS FOR '{u['User']}'@'{u['Host']}'")
        grants_raw = [list(g.values())[0] for g in cursor.fetchall()]

        privileges = []
        for g in grants_raw:
            if "GRANT" in g:
                priv_part = g.split(" ON ")[0].replace("GRANT ", "")
                db_part = g.split(" ON ")[1].split(" TO ")[0]
                privileges.append({
                    "database": db_part,
                    "privileges": priv_part
                })

        users.append({
            "user": u["User"],
            "host": u["Host"],
            "privileges": privileges  # <--- key matches frontend
        })

    cursor.close()
    conn.close()
    return jsonify({"users": users})


# ================= CREATE USER =================
@app.route("/create_user", methods=["POST"])
def create_user():
    username = request.json.get("username")
    host = request.json.get("host", "localhost")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE USER '{username}'@'{host}'")
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()

# ================= DROP USER =================
@app.route("/drop_user", methods=["POST"])
def drop_user():
    username = request.json.get("username")
    host = request.json.get("host", "localhost")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DROP USER '{username}'@'{host}'")
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()

# ================= GRANT PRIVILEGES =================
@app.route("/grant_privileges", methods=["POST"])
def grant_privileges():
    username = request.json.get("username")
    host = request.json.get("host", "localhost")
    database = request.json.get("database")
    privileges = request.json.get(
        "privileges",
        "INSERT, UPDATE, DELETE, CREATE"
    )

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"GRANT {privileges} ON `{database}`.* TO '{username}'@'{host}'"
        )
        cursor.execute("FLUSH PRIVILEGES")
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()

# ================= REVOKE PRIVILEGES =================
@app.route("/revoke_privileges", methods=["POST"])
def revoke_privileges():
    username = request.json.get("username")
    host = request.json.get("host", "localhost")
    database = request.json.get("database")
    privileges = request.json.get(
        "privileges",
        "INSERT, UPDATE, DELETE, CREATE"
    )

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"REVOKE {privileges} ON `{database}`.* FROM '{username}'@'{host}'"
        )
        cursor.execute("FLUSH PRIVILEGES")
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.Error as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        cursor.close()
        conn.close()

# ================= RUN APP =================
if __name__ == "__main__":
    app.run(debug=True, port=5000)
