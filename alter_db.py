import sqlite3

conn = sqlite3.connect('Artify.db')
cursor = conn.cursor()

cursor.execute("ALTER TABLE orders ADD COLUMN transaction_id TEXT;")

conn.commit()
conn.close()