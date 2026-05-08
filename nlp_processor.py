"""
=============================================================
 NLP Processor Module — Exam Seat Seeker
=============================================================
 This module handles:
   1. PDF text extraction using pdfplumber
   2. NLP-based text cleaning & preprocessing
   3. Regex-based entity extraction (Roll, Name, Block, etc.)
   4. Table-based extraction as fallback
   5. Fuzzy matching for approximate roll number search

 The module converts unstructured PDF text into structured
 data (list of dictionaries) using NLP techniques.
=============================================================
"""

import re
import logging
import pdfplumber
from thefuzz import fuzz, process  # Fuzzy string matching library

# =============================================
#  LOGGING
# =============================================
logger = logging.getLogger(__name__)


# =============================================
#  TEXT PREPROCESSING (NLP Step)
# =============================================
def preprocess_text(raw_text):
    """
    Clean and normalize raw text extracted from PDF.

    NLP Preprocessing Steps:
      1. Remove extra whitespace and blank lines
      2. Normalize unicode characters
      3. Strip leading/trailing spaces per line
      4. Remove special characters that break parsing
      5. Normalize separators (tabs → spaces)

    Args:
        raw_text (str): Raw text from pdfplumber

    Returns:
        str: Cleaned, normalized text
    """
    if not raw_text:
        return ""

    # Step 1: Replace tabs with spaces
    text = raw_text.replace("\t", "  ")

    # Step 2: Normalize multiple spaces to single space
    text = re.sub(r" {2,}", "  ", text)

    # Step 3: Remove non-printable characters (keep newlines)
    text = re.sub(r"[^\S\n]+", " ", text)

    # Step 4: Strip each line individually
    lines = [line.strip() for line in text.split("\n")]

    # Step 5: Remove completely empty lines
    lines = [line for line in lines if line]

    # Step 6: Rejoin
    cleaned = "\n".join(lines)

    logger.info("Text preprocessed: %d chars → %d chars", len(raw_text), len(cleaned))
    return cleaned


# =============================================
#  REGEX-BASED ENTITY EXTRACTION (NLP Step)
# =============================================
def extract_entities_from_text(text):
    """
    Use regex patterns and NLP techniques to extract
    structured student data from unstructured PDF text.

    This handles PDFs that have text-based layouts
    (not tables), where data might look like:

        Roll No: 101  Name: Rahul  Block: A  Row: 1  Seat: 5 Date: 2025-05-10 Time: 10:00AM
        or
        101 | Rahul Sharma | Block A | Row 1 | Seat 5 | 2025-05-10 | 10:00AM

    The function tries multiple regex patterns to be
    flexible with different PDF formats.

    Args:
        text (str): Preprocessed text from PDF

    Returns:
        list: List of student dictionaries
    """
    students = []

    # ---- Pattern 1: Key-Value format ----
    # Matches: Roll No: 101  Name: Rahul  Block: A  Row: 1  Seat: 5 Date: 2025-05-10 Time: 10:00AM
    pattern_kv = re.compile(
        r"(?:Roll\s*(?:No|Number)?\.?\s*:?\s*)"  # Roll Number label
        r"(\S+)"                                    # Roll value
        r"[\s|,;]+"                                 # Separator
        r"(?:Name\s*:?\s*)"                         # Name label
        r"([A-Za-z\s\.]+?)"                         # Name value
        r"[\s|,;]+"                                 # Separator
        r"(?:Block\s*:?\s*)"                        # Block label
        r"(\S+)"                                    # Block value
        r"[\s|,;]+"                                 # Separator
        r"(?:Row\s*(?:No|Number)?\.?\s*:?\s*)"      # Row label
        r"(\S+)"                                    # Row value
        r"[\s|,;]+"                                 # Separator
        r"(?:Seat\s*(?:No|Number)?\.?\s*:?\s*)"     # Seat label
        r"(\S+)"                                    # Seat value
        r"(?:[\s|,;]+(?:Date|Exam\s*Date)?\s*:?\s*([0-9]{2,4}[-/][0-9]{2}[-/][0-9]{2,4}))?"  # Optional Date
        r"(?:[\s|,;]+(?:Time)?\s*:?\s*([0-9]{1,2}:[0-9]{2}\s*(?:AM|PM|am|pm)?))?",             # Optional Time
        re.IGNORECASE
    )

    for match in pattern_kv.finditer(text):
        students.append({
            "roll_no": match.group(1).strip(),
            "name":    match.group(2).strip(),
            "block":   match.group(3).strip(),
            "row":     match.group(4).strip(),
            "seat":    match.group(5).strip(),
            "exam_date": match.group(6).strip() if match.group(6) else "",
            "time":      match.group(7).strip() if match.group(7) else "",
        })

    if students:
        logger.info("Pattern KV matched: %d records", len(students))
        return students

    # ---- Pattern 2: Pipe/Tab-separated format ----
    # Matches: 101 | Rahul Sharma | A | 1 | 5 | 2025-05-10 | 10:00AM
    pattern_pipe = re.compile(
        r"(\d{2,10})"                   # Roll (2-10 digit number)
        r"\s*[|]\s*"                     # Pipe separator
        r"([A-Za-z\s\.]+?)"             # Name
        r"\s*[|]\s*"                     # Pipe separator
        r"([A-Za-z0-9\-]+)"             # Block
        r"\s*[|]\s*"                     # Pipe separator
        r"([A-Za-z0-9\-]+)"             # Row
        r"\s*[|]\s*"                     # Pipe separator
        r"(\d+)"                         # Seat number
        r"(?:\s*[|]\s*([0-9]{2,4}[-/][0-9]{2}[-/][0-9]{2,4}))?"  # Optional Date
        r"(?:\s*[|]\s*([0-9]{1,2}:[0-9]{2}\s*(?:AM|PM|am|pm)?))?", # Optional Time
        re.IGNORECASE
    )

    for match in pattern_pipe.finditer(text):
        students.append({
            "roll_no": match.group(1).strip(),
            "name":    match.group(2).strip(),
            "block":   match.group(3).strip(),
            "row":     match.group(4).strip(),
            "seat":    match.group(5).strip(),
            "exam_date": match.group(6).strip() if match.group(6) else "",
            "time":      match.group(7).strip() if match.group(7) else "",
        })

    if students:
        logger.info("Pattern PIPE matched: %d records", len(students))
        return students

    # ---- Pattern 3: Space-separated rows ----
    # Matches lines like: 101  Rahul Sharma  A  1  5 2025-05-10 10:00AM
    # This is a looser pattern used as a last resort
    pattern_space = re.compile(
        r"^(\d{2,10})"                  # Roll number at start of line
        r"\s{2,}"                        # Multiple spaces
        r"([A-Za-z][A-Za-z\s\.]{2,30})" # Name (letters, at least 3 chars)
        r"\s{2,}"                        # Multiple spaces
        r"([A-Za-z0-9\-]+)"             # Block
        r"\s{2,}"                        # Multiple spaces
        r"([A-Za-z0-9\-]+)"             # Row
        r"\s{2,}"                        # Multiple spaces
        r"(\d+)"                         # Seat
        r"(?:\s{2,}([0-9]{2,4}[-/][0-9]{2}[-/][0-9]{2,4}))?"  # Optional Date
        r"(?:\s{2,}([0-9]{1,2}:[0-9]{2}\s*(?:AM|PM|am|pm)?))?", # Optional Time
        re.MULTILINE
    )

    for match in pattern_space.finditer(text):
        name = match.group(2).strip()
        # NLP filter: skip if "name" looks like a header word
        if name.lower() in ["name", "student", "roll", "block", "row", "seat", "date", "time"]:
            continue
        students.append({
            "roll_no": match.group(1).strip(),
            "name":    name,
            "block":   match.group(3).strip(),
            "row":     match.group(4).strip(),
            "seat":    match.group(5).strip(),
            "exam_date": match.group(6).strip() if match.group(6) else "",
            "time":      match.group(7).strip() if match.group(7) else "",
        })

    if students:
        logger.info("Pattern SPACE matched: %d records", len(students))

    return students


# =============================================
#  TABLE-BASED EXTRACTION (Primary Method)
# =============================================
def extract_from_tables(pdf_file):
    """
    Extract student data from tables in the PDF using
    pdfplumber's table detection engine.

    This is the primary extraction method. It detects
    tables, identifies column headers using NLP-based
    fuzzy matching, and extracts row data.

    Args:
        pdf_file: File-like object of the uploaded PDF

    Returns:
        list: List of student dictionaries
    """
    students = []

    try:
        with pdfplumber.open(pdf_file) as pdf:
            logger.info("PDF opened: %d page(s)", len(pdf.pages))

            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()

                if not tables:
                    logger.info("Page %d: No tables detected", page_num)
                    continue

                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    # ---- NLP: Identify column headers ----
                    col_map = _identify_columns(table[0])

                    if not col_map:
                        # Fallback: assume positional order
                        if len(table[0]) >= 5:
                            col_map = {"roll_no": 0, "name": 1, "block": 2, "row": 3, "seat": 4, "exam_date": 5, "time": 6}
                            logger.info("Page %d: Using positional column mapping", page_num)
                        else:
                            continue

                    # ---- Extract data rows ----
                    for doc_row in table[1:]:
                        if not doc_row:
                            continue

                        student = {
                            "roll_no": _safe_cell(doc_row, col_map.get("roll_no")),
                            "name":    _safe_cell(doc_row, col_map.get("name")),
                            "block":   _safe_cell(doc_row, col_map.get("block")),
                            "row":     _safe_cell(doc_row, col_map.get("row")),
                            "seat":    _safe_cell(doc_row, col_map.get("seat")),
                            "exam_date": _safe_cell(doc_row, col_map.get("exam_date")),
                            "time":      _safe_cell(doc_row, col_map.get("time")),
                        }

                        # Validate: must have at least roll number
                        if student["roll_no"] and not _is_header_word(student["roll_no"]):
                            students.append(student)

    except Exception as e:
        logger.error("Table extraction error: %s", str(e))
        raise

    logger.info("Table extraction: %d records found", len(students))
    return students


def _identify_columns(header_row):
    """
    Use NLP-based fuzzy matching to identify which
    column corresponds to Roll, Name, Block, Room, Seat.

    This handles variations like:
      "Roll No" → roll, "Student Name" → name,
      "Blk" → block, "Room No." → room, etc.

    Args:
        header_row: List of header cell strings

    Returns:
        dict: Mapping of field name → column index
    """
    if not header_row:
        return None

    # Known patterns for each field (used for fuzzy matching)
    field_patterns = {
        "roll_no":  ["roll", "roll no", "roll number", "enrollment", "reg no", "registration"],
        "name":  ["name", "student name", "student", "full name", "candidate"],
        "block": ["block", "block name", "wing", "building", "blk"],
        "row":  ["row", "room", "room no", "room number", "classroom", "hall", "class"],
        "seat":  ["seat", "seat no", "seat number", "desk", "position"],
        "exam_date": ["date", "exam date", "examination date", "day"],
        "time": ["time", "exam time", "start time"],
    }

    col_map = {}
    used_indices = set()

    for field, patterns in field_patterns.items():
        best_score = 0
        best_index = -1

        for i, cell in enumerate(header_row):
            if cell is None or i in used_indices:
                continue

            cell_clean = cell.strip().lower()
            if not cell_clean:
                continue

            # Use fuzzy matching to compare header with known patterns
            for pattern in patterns:
                score = fuzz.ratio(cell_clean, pattern)
                # Also check if pattern is a substring
                if pattern in cell_clean:
                    score = max(score, 85)

                if score > best_score and score >= 60:
                    best_score = score
                    best_index = i

        if best_index >= 0:
            col_map[field] = best_index
            used_indices.add(best_index)
            logger.debug("Column '%s' → index %d (score: %d)",
                        field, best_index, best_score)

    # Need at least 3 columns identified
    if len(col_map) >= 3:
        logger.info("Column mapping (NLP): %s", col_map)
        return col_map

    return None


def _safe_cell(row, col_index):
    """Safely retrieve a cell value from a row."""
    if col_index is None or col_index >= len(row):
        return ""
    val = row[col_index]
    return val.strip() if val else ""


def _is_header_word(text):
    """Check if a cell value is actually a header label, not data."""
    headers = {"roll", "name", "block", "room", "seat", "number", "no", "student",
               "sr", "s.no", "sno", "serial", "roll no", "roll number"}
    return text.strip().lower() in headers


# =============================================
#  FULL-TEXT EXTRACTION (Fallback Method)
# =============================================
def extract_from_text(pdf_file):
    """
    Fallback method: extract all text from the PDF,
    preprocess it with NLP, then use regex patterns
    to find student records.

    Used when table-based extraction finds nothing.

    Args:
        pdf_file: File-like object

    Returns:
        list: List of student dictionaries
    """
    all_text = ""

    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    all_text += page_text + "\n"
    except Exception as e:
        logger.error("Text extraction error: %s", str(e))
        raise

    if not all_text.strip():
        return []

    # NLP Step: Preprocess the raw text
    cleaned = preprocess_text(all_text)

    # NLP Step: Extract entities using regex patterns
    students = extract_entities_from_text(cleaned)

    return students


# =============================================
#  MAIN EXTRACTION PIPELINE
# =============================================
def process_pdf(pdf_file):
    """
    Main entry point — processes an uploaded PDF file
    and returns structured student data.

    Pipeline:
      1. Try table-based extraction (most reliable)
      2. If no tables found, fall back to text + NLP extraction
      3. Deduplicate results
      4. Return structured list

    Args:
        pdf_file: File-like object from Flask upload

    Returns:
        list: List of student dictionaries
    """
    logger.info("=== Starting PDF Processing Pipeline ===")

    # Step 1: Try table extraction first
    students = extract_from_tables(pdf_file)

    # Step 2: Fallback to text-based NLP extraction
    if not students:
        logger.info("No tables found. Trying text-based NLP extraction...")
        pdf_file.seek(0)  # Reset file pointer
        students = extract_from_text(pdf_file)

    # Step 3: Deduplicate by roll number
    seen_rolls = set()
    unique_students = []
    for s in students:
        roll_key = s["roll_no"].lower().strip()
        if roll_key and roll_key not in seen_rolls:
            seen_rolls.add(roll_key)
            unique_students.append(s)

    logger.info("=== Pipeline Complete: %d unique records ===", len(unique_students))
    return unique_students


# =============================================
#  FUZZY SEARCH (NLP Feature)
# =============================================
def fuzzy_search(query, data, threshold=75):
    """
    Search for a student by roll number using fuzzy matching.

    This handles cases where the student enters a slightly
    incorrect roll number (e.g., "10l" instead of "101",
    or "2024CSE01" instead of "2024CSE001").

    Uses the Levenshtein distance algorithm via thefuzz library.

    Args:
        query (str): The roll number to search for
        data (list): List of student dictionaries
        threshold (int): Minimum match score (0-100)

    Returns:
        dict or None: Best matching student, or None
    """
    if not query or not data:
        return None

    query = query.strip().lower()

    # Step 1: Try exact match first
    for student in data:
        if student["roll_no"].strip().lower() == query:
            return {"match": student, "confidence": 100, "match_type": "exact"}

    # Step 2: Fuzzy match
    roll_numbers = [s["roll_no"] for s in data]
    best_match = process.extractOne(query, roll_numbers, scorer=fuzz.ratio)

    if best_match and best_match[1] >= threshold:
        matched_roll = best_match[0]
        confidence = best_match[1]

        # Find the student with this roll number
        for student in data:
            if student["roll_no"] == matched_roll:
                return {
                    "match": student,
                    "confidence": confidence,
                    "match_type": "fuzzy",
                    "searched": query,
                    "corrected_to": matched_roll,
                }

    return None
