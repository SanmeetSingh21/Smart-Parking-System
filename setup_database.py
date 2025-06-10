import sqlite3
import os

# Delete existing DB if it exists (CAUTION: Deletes all previous data!)
if os.path.exists("vehicles.db"):
    os.remove("vehicles.db")
    print("Old database removed.")

# Connect to new DB
conn = sqlite3.connect("vehicles.db")
cursor = conn.cursor()

# Create vehicles table
cursor.execute("""
CREATE TABLE vehicles (
    number_plate TEXT PRIMARY KEY,
    owner_name TEXT,
    vehicle_type TEXT,
    allowed INTEGER NOT NULL CHECK(allowed IN (0, 1))
)
""")

# Create parking_slots table
cursor.execute("""
CREATE TABLE parking_slots (
    slot_number INTEGER PRIMARY KEY,
    number_plate TEXT,
    assigned_date TEXT
)
""")

# Insert only 20 parking slots
for i in range(1, 21):
    cursor.execute("INSERT INTO parking_slots (slot_number, number_plate, assigned_date) VALUES (?, NULL, NULL)", (i,))

# Sample vehicles (optional)
vehicles = [
    ("MH04FZ8259", "Ravi Kumar", "Car", 1),
    ("DL8CAF7654", "Raihan", "Bike", 1),
    ("KA03MN4567", "Amit Joshi", "Truck", 0),
    ("RJ14CV0002", "Sanmeet Singh", "Car", 1)
]

for vehicle in vehicles:
    cursor.execute("INSERT INTO vehicles (number_plate, owner_name, vehicle_type, allowed) VALUES (?, ?, ?, ?)", vehicle)

conn.commit()
conn.close()
print("✅ New database with 20 slots created.")
