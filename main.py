import cv2
from ultralytics import YOLO
import easyocr
import sqlite3
import time
import threading
from datetime import datetime
import numpy as np
import ttkbootstrap as ttk
from tkinter import messagebox, ttk as tkttk
import re
import serial

try:
    arduino = serial.Serial('COM6', 9600)
    time.sleep(2)
except:
    arduino = None
    print("⚠️ Could not connect to Arduino")

model = YOLO("best.pt")
reader = easyocr.Reader(['en'])

conn = sqlite3.connect("vehicles.db")
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS parking_slots (
                    slot_number INTEGER PRIMARY KEY,
                    number_plate TEXT,
                    assigned_date TEXT)""")
for i in range(1, 21):
    cursor.execute("INSERT OR IGNORE INTO parking_slots (slot_number, number_plate, assigned_date) VALUES (?, NULL, NULL)", (i,))
cursor.execute("""CREATE TABLE IF NOT EXISTS vehicles (
                    number_plate TEXT PRIMARY KEY,
                    owner_name TEXT,
                    vehicle_type TEXT,
                    allowed INTEGER NOT NULL CHECK(allowed IN (0, 1))
                )""")
conn.commit()
conn.close()

def preprocess_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def assign_next_available_slot(number_plate):
    conn = sqlite3.connect("vehicles.db")
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT slot_number FROM parking_slots WHERE number_plate IS NULL ORDER BY slot_number ASC")
    row = cursor.fetchone()
    if row:
        slot = row[0]
        cursor.execute("UPDATE parking_slots SET number_plate=?, assigned_date=? WHERE slot_number=?",
                       (number_plate, today, slot))
        conn.commit()
        conn.close()
        return slot
    conn.close()
    return None

def get_assigned_slot(number_plate):
    conn = sqlite3.connect("vehicles.db")
    cursor = conn.cursor()
    cursor.execute("SELECT slot_number FROM parking_slots WHERE number_plate=?", (number_plate,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

last_seen = {}

def run_detection():
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

                    if re.match(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$", plate_text_clean):
                        if plate_text_clean not in last_seen or current_time - last_seen[plate_text_clean] > 5:
                            last_seen[plate_text_clean] = current_time

                            conn = sqlite3.connect("vehicles.db")
                            cursor = conn.cursor()
                            cursor.execute("SELECT owner_name FROM vehicles WHERE number_plate=?", (plate_text_clean,))
                            result = cursor.fetchone()

                            if result:
                                slot = get_assigned_slot(plate_text_clean)
                                if not slot:
                                    slot = assign_next_available_slot(plate_text_clean)
                                    if slot:
                                        if arduino:
                                            arduino.write(b'O')
                                            time.sleep(3)
                                            arduino.write(b'C')
                                        messagebox.showinfo("Access Granted",
                                                            f"Vehicle: {plate_text_clean}\nOwner: {result[0]}\nSlot: {slot}")
                                else:
                                    time.sleep(5)
                                    cursor.execute("UPDATE parking_slots SET number_plate=NULL, assigned_date=NULL WHERE slot_number=?",
                                                   (slot,))
                                    conn.commit()
                                    if arduino:
                                        arduino.write(b'O')
                                        time.sleep(3)
                                        arduino.write(b'C')
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

def live_detection():
    thread = threading.Thread(target=run_detection)
    thread.daemon = True
    thread.start()

# GUI
root = ttk.Window(themename="superhero")
root.title("Vehicle Entry & Parking Management")
root.state('zoomed')

main_frame = ttk.Frame(root, padding=10)
main_frame.pack(fill='both', expand=True)

title_label = ttk.Label(main_frame, text="Vehicle Entry & Parking Management", font=("Helvetica", 28, "bold"))
title_label.pack(pady=10)

btn_frame = ttk.Frame(main_frame)
btn_frame.pack(pady=10)

start_button = ttk.Button(btn_frame, text="Start Live Detection", bootstyle="success, outline", width=25, command=live_detection)
start_button.grid(row=0, column=0, padx=10)

refresh_button = ttk.Button(btn_frame, text="Refresh Tables", bootstyle="info, outline", width=25, command=lambda: refresh_tables())
refresh_button.grid(row=0, column=1, padx=10)

exit_button = ttk.Button(btn_frame, text="Exit", bootstyle="danger, outline", width=25, command=root.destroy)
exit_button.grid(row=0, column=2, padx=10)

paned = ttk.PanedWindow(main_frame, orient="horizontal")
paned.pack(fill='both', expand=True, pady=10)

vehicle_frame = ttk.Labelframe(paned, text="Registered Vehicles", padding=10)
paned.add(vehicle_frame, weight=1)

vehicle_table = tkttk.Treeview(vehicle_frame, columns=("number", "plate", "owner", "type"), show="headings", height=12)
for col, w in zip(("number", "plate", "owner", "type"), (50, 120, 150, 100)):
    vehicle_table.heading(col, text=col.capitalize())
    vehicle_table.column(col, width=w, anchor="center", stretch=False)
vehicle_table.pack(fill='both', expand=True)

edit_btn = ttk.Button(vehicle_frame, text="Edit Selected", bootstyle="warning", command=lambda: edit_selected_vehicle())
edit_btn.pack(pady=5)

delete_btn = ttk.Button(vehicle_frame, text="Delete Selected", bootstyle="danger", command=lambda: delete_selected_vehicle())
delete_btn.pack(pady=5)

slots_frame = ttk.Labelframe(paned, text="Parking Slots Status", padding=10)
paned.add(slots_frame, weight=1)

slots_table = tkttk.Treeview(slots_frame, columns=("slot", "plate", "owner"), show="headings", height=12)
for col, w in zip(("slot", "plate", "owner"), (80, 120, 150)):
    slots_table.heading(col, text=col.capitalize())
    slots_table.column(col, width=w, anchor="center", stretch=False)
slots_table.pack(fill='both', expand=True)

register_frame = ttk.Labelframe(main_frame, text="Register New Vehicle", padding=10)
register_frame.pack(pady=10, fill='x')

labels = ["Number Plate:", "Owner Name:", "Vehicle Type:"]
entries = []
for i, text in enumerate(labels):
    ttk.Label(register_frame, text=text).grid(row=0, column=i*2, padx=5, pady=5)
    entry = ttk.Entry(register_frame, width=20)
    entry.grid(row=0, column=i*2+1, padx=5, pady=5)
    entries.append(entry)

submit_btn = ttk.Button(register_frame, text="Submit", bootstyle="success", command=lambda: add_vehicle())
submit_btn.grid(row=0, column=6, padx=10)

plate_entry, owner_entry, type_entry = entries

def is_valid_plate(plate):
    return re.match(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$", plate) is not None

def add_vehicle():
    plate = plate_entry.get().upper()
    owner = owner_entry.get()
    vtype = type_entry.get()

    if plate and owner and vtype:
        if not is_valid_plate(plate):
            messagebox.showerror("Invalid Format", "Enter valid Indian number plate format (e.g., MH04AB1234).")
            return

        conn = sqlite3.connect("vehicles.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vehicles WHERE number_plate=?", (plate,))
        if cursor.fetchone():
            cursor.execute("UPDATE vehicles SET owner_name=?, vehicle_type=? WHERE number_plate=?", (owner, vtype, plate))
            msg = "Vehicle updated successfully."
        else:
            cursor.execute("INSERT INTO vehicles (number_plate, owner_name, vehicle_type, allowed) VALUES (?, ?, ?, 1)", (plate, owner, vtype))
            msg = "Vehicle registered successfully."
        conn.commit()
        conn.close()
        messagebox.showinfo("Success", msg)
        refresh_tables()
        for e in entries:
            e.delete(0, 'end')
    else:
        messagebox.showerror("Input Error", "Please fill all fields!")

def edit_selected_vehicle():
    selected = vehicle_table.selection()
    if selected:
        values = vehicle_table.item(selected[0], 'values')
        plate_entry.delete(0, 'end')
        plate_entry.insert(0, values[1])
        owner_entry.delete(0, 'end')
        owner_entry.insert(0, values[2])
        type_entry.delete(0, 'end')
        type_entry.insert(0, values[3])

def delete_selected_vehicle():
    selected = vehicle_table.selection()
    if selected:
        values = vehicle_table.item(selected[0], 'values')
        plate = values[1]
        if messagebox.askyesno("Confirm Delete", f"Delete vehicle {plate}?"):
            conn = sqlite3.connect("vehicles.db")
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vehicles WHERE number_plate=?", (plate,))
            cursor.execute("UPDATE parking_slots SET number_plate=NULL, assigned_date=NULL WHERE number_plate=?", (plate,))
            conn.commit()
            conn.close()
            refresh_tables()

def refresh_tables():
    conn = sqlite3.connect("vehicles.db")
    cursor = conn.cursor()

    for row in vehicle_table.get_children():
        vehicle_table.delete(row)
    cursor.execute("SELECT number_plate, owner_name, vehicle_type FROM vehicles")
    for idx, (plate, owner, vtype) in enumerate(cursor.fetchall(), start=1):
        vehicle_table.insert("", "end", values=(idx, plate, owner, vtype))

    for row in slots_table.get_children():
        slots_table.delete(row)
    cursor.execute("SELECT slot_number, number_plate FROM parking_slots ORDER BY slot_number")
    for slot_number, number_plate in cursor.fetchall():
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
