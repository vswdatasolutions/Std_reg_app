from flask import Flask, render_template, request, redirect, flash, url_for, send_file
import sqlite3
import os
from werkzeug.utils import secure_filename
import csv
import io

# Flask configuration
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database and upload folder configuration
DATABASE = 'school.db'
UPLOAD_FOLDER = 'static/uploads'  # Ensure files are saved in static/uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper function to connect to the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database
def initialize_database():
    with get_db_connection() as conn:
        conn.executescript('''  
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                father_name TEXT NOT NULL,
                dob TEXT NOT NULL,
                class TEXT NOT NULL,
                gender TEXT NOT NULL,
                academic_year TEXT NOT NULL,
                aadhar TEXT NOT NULL,
                village TEXT NOT NULL,
                taluka TEXT NOT NULL,
                district TEXT NOT NULL,
                pin TEXT NOT NULL,
                religion TEXT NOT NULL,
                caste TEXT NOT NULL,
                nationality TEXT NOT NULL,
                mother_tongue TEXT NOT NULL,
                medium TEXT NOT NULL,
                residential_address TEXT NOT NULL,
                phone1 TEXT NOT NULL,
                phone2 TEXT,
                photo TEXT NOT NULL,
                signature TEXT NOT NULL,
                payment_utr TEXT UNIQUE NOT NULL,
                hall_ticket TEXT UNIQUE,
                verified BOOLEAN DEFAULT FALSE,
                exam_center TEXT NOT NULL
            );
        ''')
        print("Database initialized successfully!")

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route('/')
def register():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register_student():
    try:
        # Extract form data
        student_data = {k: request.form[k] for k in request.form}
        photo = request.files.get('photo')
        signature = request.files.get('signature')

        # Validate file uploads
        if not all([photo, signature]):
            flash("Both photo and signature must be uploaded.", "danger")
            return redirect(url_for('register'))

        if not (allowed_file(photo.filename) and allowed_file(signature.filename)):
            flash("Only PNG, JPG, and JPEG files are allowed.", "danger")
            return redirect(url_for('register'))

        # Save files to the upload folder inside static/uploads
        photo_filename = secure_filename(photo.filename)
        signature_filename = secure_filename(signature.filename)
        photo_path = os.path.join(UPLOAD_FOLDER, photo_filename)
        signature_path = os.path.join(UPLOAD_FOLDER, signature_filename)

        photo.save(photo_path)
        signature.save(signature_path)
        
        # Replace backslashes in the file paths (for Windows compatibility)
        photo_path = photo_path.replace("\\", "/")
        signature_path = signature_path.replace("\\", "/")

        # Insert student data into the database
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(""" 
                INSERT INTO students (
                    name, father_name, dob, class, gender, academic_year, aadhar, village, taluka, district, pin,
                    religion, caste, nationality, mother_tongue, medium, residential_address, phone1, phone2,
                    photo, signature, payment_utr, exam_center
                ) VALUES (
                    :name, :father_name, :dob, :class, :gender, :academic_year, :aadhar, :village, :taluka, :district, :pin,
                    :religion, :caste, :nationality, :mother_tongue, :medium, :residential_address, :phone1, :phone2,
                    :photo, :signature, :payment_utr, :exam_center
                )
            """, {
                **student_data,
                'photo': photo_path,
                'signature': signature_path,
                'payment_utr': student_data.get('payment_utr'),
                'exam_center': student_data.get('exam_center')
            })
            student_id = cursor.lastrowid

            # Generate a unique hall ticket
            hall_ticket = f"HT-{student_id:06}"
            cursor.execute("UPDATE students SET hall_ticket = ? WHERE id = ?", (hall_ticket, student_id))
            conn.commit()

        flash(f"Form submitted successfully! Hall Ticket: {hall_ticket}", "success")
        return redirect(url_for('view_hall_ticket', student_id=student_id))

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('register'))

@app.route('/hallticket/<int:student_id>')
def view_hall_ticket(student_id):
    with get_db_connection() as conn:
        student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if not student:
            flash("Student not found.", "danger")
            return redirect(url_for('admin_dashboard'))
    return render_template('hallticket.html', student=student)

@app.route('/admin')
def admin_dashboard():
    with get_db_connection() as conn:
        students = conn.execute("SELECT * FROM students").fetchall()
    return render_template('admin.html', students=students)

@app.route('/admin/verify/<int:student_id>', methods=['POST'])
def verify_student(student_id):
    try:
        with get_db_connection() as conn:
            conn.execute("UPDATE students SET verified = TRUE WHERE id = ?", (student_id,))
            conn.commit()
        flash("Student data verified successfully!", "success")
    except Exception as e:
        flash(f"An error occurred while verifying: {e}", "danger")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/generate_hall_ticket/<int:student_id>', methods=['POST'])
def generate_hall_ticket(student_id):
    try:
        with get_db_connection() as conn:
            # Fetch the student record
            student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()

            # Ensure the student exists and is verified
            if student and student['verified']:
                # Generate the hall ticket
                hall_ticket = f"HT-{student_id:06}"
                conn.execute("UPDATE students SET hall_ticket = ? WHERE id = ?", (hall_ticket, student_id))
                conn.commit()

                # Flash success message
                flash(f"Hall Ticket Generated: {hall_ticket}", "success")

                # Redirect the admin to the page to view the hall ticket
                return redirect(url_for('view_hall_ticket', student_id=student_id))
            else:
                # If the student is not verified or doesn't exist, show an error message
                flash("Student data is not verified or doesn't exist.", "danger")

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")

    # Redirect back to the admin dashboard if an error occurs
    return redirect(url_for('admin_dashboard'))


@app.route('/download_csv', methods=['GET'])
def download_csv():
    try:
        with get_db_connection() as conn:
            students = conn.execute("SELECT id, hall_ticket, name, class, payment_utr, verified FROM students").fetchall()

        # Create a CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["ID", "Hall Ticket Number", "Name", "Class", "UTR Number", "Status"])
        writer.writeheader()
        for student in students:
            writer.writerow({
                "ID": student["id"],
                "Hall Ticket Number": student["hall_ticket"],
                "Name": student["name"],
                "Class": student["class"],
                "UTR Number": student["payment_utr"],
                "Status": "Verified" if student["verified"] else "Not Verified"
            })
        output.seek(0)

        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='registered_students.csv'
        )
    except Exception as e:
        flash(f"An error occurred while generating CSV: {e}", "danger")
        return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        initialize_database()
    app.run(debug=True)
