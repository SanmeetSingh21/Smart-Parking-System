
import cv2
from ultralytics import YOLO
import easyocr
import sqlite3
import time
import random
from datetime import datetime
import numpy as np
import ttkbootstrap as ttk
from tkinter import messagebox, ttk as tkttk



# Initialize YOLO and OCR
model = YOLO("best.pt")
reader = easyocr.Reader(['en'])

# Connect and setup database
def connect_db():
    conn = sqlite3.connect("vehicles.db")
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS parking_slots (
                        slot_number INTEGER PRIMARY KEY,
                        number_plate TEXT,
                        assigned_date TEXT)""")
    for i in range(1, 101):
        cursor.execute("INSERT OR IGNORE INTO parking_slots (slot_number, number_plate, assigned_date) VALUES (?, NULL, NULL)", (i,))
    conn.commit()
    conn.close()

connect_db()

# Preprocessing
def preprocess_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

# Assign parking slot
def assign_random_slot(number_plate):
    conn = sqlite3.connect("vehicles.db")
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT slot_number FROM parking_slots WHERE number_plate IS NULL")
    available_slots = [row[0] for row in cursor.fetchall()]
    if available_slots:
        slot = random.choice(available_slots)
        cursor.execute("UPDATE parking_slots SET number_plate=?, assigned_date=? WHERE slot_number=?",
                       (number_plate, today, slot))
        conn.commit()
        conn.close()
        return slot
    else:
        conn.close()
        return None

def get_assigned_slot(number_plate):
    conn = sqlite3.connect("vehicles.db")
    cursor = conn.cursor()
    cursor.execute("SELECT slot_number FROM parking_slots WHERE number_plate=?", (number_plate,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# Live Detection Function
last_seen = {}

def live_detection():
    cap = cv2.VideoCapture(0)
    global last_seen
    last_seen = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame)
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cropped = frame[y1:y2, x1:x2]
                if cropped.size == 0:
                    continue

                processed_img = preprocess_image(cropped)
                ocr_result = reader.readtext(processed_img)
                if ocr_result:
                    plate_text = ocr_result[0][1]
                    plate_text_clean = ''.join(filter(str.isalnum, plate_text.upper()))
                    current_time = time.time()

                    if plate_text_clean not in last_seen or current_time - last_seen[plate_text_clean] > 5:
                        last_seen[plate_text_clean] = current_time

                        conn = sqlite3.connect("vehicles.db")
                        cursor = conn.cursor()
                        cursor.execute("SELECT owner_name FROM vehicles WHERE number_plate=?", (plate_text_clean,))
                        result = cursor.fetchone()

                        if result:
                            slot = get_assigned_slot(plate_text_clean)
                            if not slot:
                                slot = assign_random_slot(plate_text_clean)
                                if slot:
                                    messagebox.showinfo("Access Granted",
                                                        f"Vehicle: {plate_text_clean}\nOwner: {result[0]}\nSlot: {slot}")
                            else:
                                cursor.execute("UPDATE parking_slots SET number_plate=NULL, assigned_date=NULL WHERE slot_number=?",
                                               (slot,))
                                conn.commit()
                                messagebox.showinfo("Exit Recorded",
                                                    f"Vehicle: {plate_text_clean}\nSlot {slot} is now free")
                        conn.close()
                        refresh_tables()

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, plate_text_clean, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)

        cv2.imshow("Live Vehicle Entry", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

# GUI Setup
root = ttk.Window(themename="superhero")
root.title("Vehicle Entry & Parking Management")
root.state('zoomed')

main_frame = ttk.Frame(root, padding=10)
main_frame.pack(fill='both', expand=True)

# Title
title_label = ttk.Label(main_frame, text="Vehicle Entry & Parking Management", font=("Helvetica", 28, "bold"))
title_label.pack(pady=10)

# Buttons
btn_frame = ttk.Frame(main_frame)
btn_frame.pack(pady=10)

start_button = ttk.Button(btn_frame, text="Start Live Detection", bootstyle="success, outline", width=25, command=live_detection)
start_button.grid(row=0, column=0, padx=10)

refresh_button = ttk.Button(btn_frame, text="Refresh Tables", bootstyle="info, outline", width=25, command=lambda: refresh_tables())
refresh_button.grid(row=0, column=1, padx=10)

exit_button = ttk.Button(btn_frame, text="Exit", bootstyle="danger, outline", width=25, command=root.destroy)
exit_button.grid(row=0, column=2, padx=10)

# Tables
paned = ttk.PanedWindow(main_frame, orient="horizontal")
paned.pack(fill='both', expand=True, pady=10)

vehicle_frame = ttk.Labelframe(paned, text="Registered Vehicles", padding=10)
paned.add(vehicle_frame, weight=1)

vehicle_table = tkttk.Treeview(vehicle_frame, columns=("number", "plate", "owner", "type"), show="headings", height=12)
for col, w in zip(("number", "plate", "owner", "type"), (50, 120, 150, 100)):
    vehicle_table.heading(col, text=col.capitalize())
    vehicle_table.column(col, width=w, anchor="center", stretch=False)
vehicle_table.pack(fill='both', expand=True)

slots_frame = ttk.Labelframe(paned, text="Parking Slots Status", padding=10)
paned.add(slots_frame, weight=1)

slots_table = tkttk.Treeview(slots_frame, columns=("slot", "plate", "owner"), show="headings", height=12)
for col, w in zip(("slot", "plate", "owner"), (80, 120, 150)):
    slots_table.heading(col, text=col.capitalize())
    slots_table.column(col, width=w, anchor="center", stretch=False)
slots_table.pack(fill='both', expand=True)

# New Vehicle Registration
register_frame = ttk.Labelframe(main_frame, text="Register New Vehicle", padding=10)
register_frame.pack(pady=10, fill='x')

labels = ["Number Plate:", "Owner Name:", "Vehicle Type:"]
entries = []
for i, text in enumerate(labels):
    ttk.Label(register_frame, text=text).grid(row=0, column=i*2, padx=5, pady=5)
    entry = ttk.Entry(register_frame, width=20)
    entry.grid(row=0, column=i*2+1, padx=5, pady=5)
    entries.append(entry)

plate_entry, owner_entry, type_entry = entries

def add_vehicle():
    plate = plate_entry.get().upper()
    owner = owner_entry.get()
    vtype = type_entry.get()

    if plate and owner and vtype:
        conn = sqlite3.connect("vehicles.db")
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR IGNORE INTO vehicles (number_plate, owner_name, vehicle_type, allowed) VALUES (?, ?, ?, 1)",
                           (plate, owner, vtype))
            conn.commit()
            messagebox.showinfo("Success", f"Vehicle {plate} registered successfully.")
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", str(e))
        conn.close()

        refresh_tables()
        for e in entries:
            e.delete(0, 'end')
    else:
        messagebox.showerror("Input Error", "Please fill all fields!")

add_btn = ttk.Button(register_frame, text="Add Vehicle", bootstyle="primary", command=add_vehicle)
add_btn.grid(row=0, column=6, padx=10)

def refresh_tables():
    conn = sqlite3.connect("vehicles.db")
    cursor = conn.cursor()

    for row in vehicle_table.get_children():
        vehicle_table.delete(row)

    cursor.execute("SELECT number_plate, owner_name, vehicle_type FROM vehicles")
    vehicles = cursor.fetchall()
    for idx, (plate, owner, vtype) in enumerate(vehicles, start=1):
        vehicle_table.insert("", "end", values=(idx, plate, owner, vtype))

    for row in slots_table.get_children():
        slots_table.delete(row)

    cursor.execute("SELECT slot_number, number_plate FROM parking_slots ORDER BY slot_number")
    slots = cursor.fetchall()
    for slot_number, number_plate in slots:
        owner = "-"
        if number_plate:
            cursor.execute("SELECT owner_name FROM vehicles WHERE number_plate=?", (number_plate,))
            result = cursor.fetchone()
            if result:
                owner = result[0]
        slots_table.insert("", "end", values=(slot_number, number_plate or "-", owner))

    conn.close()

refresh_tables()
root.mainloop()

