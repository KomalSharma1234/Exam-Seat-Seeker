"""
=============================================================
 Exam Seat Seeker — Chitkara University
=============================================================
 Flask Backend Application

 Features:
   • Upload PDF with student exam seating data
   • Extract data using pdfplumber + NLP techniques
   • Store in-memory (no database)
   • Search by roll number with fuzzy matching
   • REST API with JSON responses

 Routes:
   GET  /          → Serve the frontend page
   POST /upload    → Upload and process PDF
   POST /search    → Search student by roll number
   GET  /status    → Check data load status
   GET  /stats     → Get loaded data statistics

 Run:  python app.py
 URL:  http://127.0.0.1:5000
=============================================================
"""

# =============================================
#  IMPORTS
# =============================================
import os
import logging
from flask import Flask, request, jsonify, render_template

# Our custom NLP processor module
from nlp_processor import process_pdf, fuzzy_search

# =============================================
#  LOGGING SETUP
# =============================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# =============================================
#  FLASK APP SETUP
# =============================================
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

# =============================================
#  IN-MEMORY DATA STORAGE
# =============================================
# Global list storing extracted student dictionaries.
# Each dict: {"roll", "name", "block", "room", "seat"}
# Reset on each new PDF upload. Lost on server restart.
student_data = []
upload_info = {"filename": None, "record_count": 0}


# =============================================================
#  ROUTE: GET /  — Serve frontend
# =============================================================
@app.route("/")
def index():
    """Serve the single-page frontend."""
    return render_template("index.html")


# =============================================================
#  ROUTE: POST /upload — Upload & process PDF
# =============================================================
@app.route("/upload", methods=["POST"])
def upload_pdf():
    """
    Upload a PDF file containing student exam seating data.

    The NLP processor extracts data using:
      1. pdfplumber table detection
      2. Regex-based entity extraction (fallback)
      3. Text preprocessing & cleaning

    Returns JSON with success status and record count.
    """
    global student_data, upload_info

    # ---- Validate: file present? ----
    if "pdf_file" not in request.files:
        return jsonify({
            "success": False,
            "error": "No file uploaded. Please select a PDF file."
        }), 400

    file = request.files["pdf_file"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "error": "No file selected. Please choose a PDF."
        }), 400

    # ---- Validate: is it a PDF? ----
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({
            "success": False,
            "error": "Invalid file type. Only .pdf files are accepted."
        }), 400

    # ---- Process with NLP pipeline ----
    try:
        extracted = process_pdf(file)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("PDF processing failed: %s", str(e))
        return jsonify({
            "success": False,
            "error": "Failed to process the PDF. Ensure it contains a valid seating table."
        }), 500

    # ---- Validate: data found? ----
    if not extracted:
        return jsonify({
            "success": False,
            "error": "No student data found in the PDF. "
                     "Ensure it contains a table with: Roll Number, Name, Block, Room, Seat."
        }), 400

    # ---- Store in memory ----
    student_data = extracted
    upload_info = {
        "filename": file.filename,
        "record_count": len(extracted),
    }

    logger.info("✅ PDF processed: '%s' — %d records", file.filename, len(extracted))

    # Compute quick stats for the response
    blocks = list(set(s["block"] for s in extracted if s["block"]))
    rows = list(set(s["row"] for s in extracted if s["row"]))

    return jsonify({
        "success": True,
        "message": f"Data Loaded Successfully! {len(extracted)} student records extracted.",
        "total_records": len(extracted),
        "filename": file.filename,
        "blocks_found": sorted(blocks),
        "rows_found": sorted(rows),
        "preview": extracted[:5],  # First 5 records as preview
    }), 200


# =============================================================
#  ROUTE: POST /search — Search by roll number
# =============================================================
@app.route("/search", methods=["POST"])
def search_student():
    """
    Search for a student's exam seat by roll number.

    Uses NLP-based fuzzy matching to handle typos
    and approximate roll number inputs.

    JSON body: { "roll_number": "101" }
    """
    global student_data

    # ---- Check: data loaded? ----
    if not student_data:
        return jsonify({
            "success": False,
            "error": "No data loaded yet. Please upload a PDF first."
        }), 400

    # ---- Get roll number ----
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body must be JSON."}), 400

    roll_number = data.get("roll_number", "").strip()
    if not roll_number:
        return jsonify({"success": False, "error": "Roll number cannot be empty."}), 400

    # ---- Search using fuzzy matching (NLP) ----
    result = fuzzy_search(roll_number, student_data, threshold=70)

    if result:
        student = result["match"]
        confidence = result["confidence"]
        match_type = result["match_type"]

        # Optional extra string building for message
        date_time_str = ""
        if student.get("exam_date") or student.get("time"):
            date_time_str = f" on {student.get('exam_date')} at {student.get('time')}"

        response = {
            "success": True,
            "found": True,
            "message": (
                f"Your exam is in Block {student['block']}, "
                f"Row {student['row']}, Seat {student['seat']}"
                f"{date_time_str}"
            ),
            "data": student,
            "confidence": confidence,
            "match_type": match_type,
        }

        # If it was a fuzzy match, add a note
        if match_type == "fuzzy":
            response["note"] = (
                f"Did you mean roll number '{result['corrected_to']}'? "
                f"(Match confidence: {confidence}%)"
            )

        logger.info("🔍 Search: '%s' → Found '%s' (%s, %d%%)",
                     roll_number, student["roll_no"], match_type, confidence)
        return jsonify(response), 200
    else:
        logger.info("🔍 Search: '%s' → Not found", roll_number)
        return jsonify({
            "success": True,
            "found": False,
            "message": "Invalid Roll Number. No matching record found.",
        }), 200


# =============================================================
#  ROUTE: GET /status — Data load status
# =============================================================
@app.route("/status", methods=["GET"])
def get_status():
    """Check if data is loaded and how many records."""
    return jsonify({
        "data_available": len(student_data) > 0,
        "records_loaded": len(student_data),
        "filename": upload_info.get("filename"),
    }), 200


# =============================================================
#  ROUTE: GET /stats — Detailed statistics
# =============================================================
@app.route("/stats", methods=["GET"])
def get_stats():
    """Return statistics about the loaded data."""
    if not student_data:
        return jsonify({"success": False, "error": "No data loaded"}), 400

    blocks = {}
    rows = set()
    for s in student_data:
        b = s.get("block", "Unknown")
        blocks[b] = blocks.get(b, 0) + 1
        if s.get("row"):
            rows.add(s.get("row"))

    return jsonify({
        "success": True,
        "total_students": len(student_data),
        "total_blocks": len(blocks),
        "total_rows": len(rows),
        "block_distribution": blocks,
        "filename": upload_info.get("filename"),
    }), 200


# =============================================================
#  ERROR HANDLERS
# =============================================================
@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "Page not found"}), 404

@app.errorhandler(413)
def too_large(e):
    return jsonify({"success": False, "error": "File too large. Max 16 MB."}), 413

@app.errorhandler(500)
def server_error(e):
    return jsonify({"success": False, "error": "Internal server error"}), 500


# =============================================================
#  RUN SERVER
# =============================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("   🎓 EXAM SEAT SEEKER — Chitkara University")
    print("=" * 60)
    print("   Server:  http://127.0.0.1:5001")
    print("")
    print("   Steps:")
    print("     1. Open the URL in your browser")
    print("     2. Upload a PDF with exam seating data")
    print("     3. Search by roll number to find your seat")
    print("")
    print("   Tech: Flask + pdfplumber + NLP + Fuzzy Matching")
    print("   Storage: In-memory (no database)")
    print("=" * 60 + "\n")

    app.run(debug=True, port=5001)