/* ==============================================
   Exam Seat Seeker — Main JavaScript
   Chitkara University
   ==============================================
   Handles:
     1. PDF file upload (drag & drop + click)
     2. Send PDF to Flask /upload endpoint
     3. Roll number search via /search endpoint
     4. Dynamic result display
     5. Stats & preview rendering
   ============================================== */


// =============================================
//  DOM REFERENCES
// =============================================
const uploadArea = document.getElementById("upload-area");
const pdfInput = document.getElementById("pdf-input");
const browseBtn = document.getElementById("browse-btn");
const fileInfoDiv = document.getElementById("file-info");
const fileNameSpan = document.getElementById("file-name");
const fileSizeSpan = document.getElementById("file-size");
const btnRemove = document.getElementById("btn-remove");
const btnUpload = document.getElementById("btn-upload");
const uploadResult = document.getElementById("upload-result");

const rollInput = document.getElementById("roll-input");
const btnSearch = document.getElementById("btn-search");
const searchResult = document.getElementById("search-result");

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");

const statsSection = document.getElementById("stats-section");
const previewSection = document.getElementById("preview-section");
const previewTbody = document.getElementById("preview-tbody");
const previewDesc = document.getElementById("preview-desc");

// Selected file reference
let selectedFile = null;


// =============================================
//  1. FILE SELECTION (Click + Drag & Drop)
// =============================================

// Click the upload area or browse button to open file dialog
uploadArea.addEventListener("click", () => pdfInput.click());
browseBtn.addEventListener("click", (e) => { e.stopPropagation(); pdfInput.click(); });

// File selected via dialog
pdfInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) selectFile(e.target.files[0]);
});

// Drag & Drop
uploadArea.addEventListener("dragover", (e) => { e.preventDefault(); uploadArea.classList.add("drag-over"); });
uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("drag-over"));
uploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadArea.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) selectFile(e.dataTransfer.files[0]);
});

// Remove selected file
btnRemove.addEventListener("click", clearFile);


/**
 * Validate and show the selected file info.
 * @param {File} file - The selected file object
 */
function selectFile(file) {
    // Validate: must be PDF
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        showResult(uploadResult, "❌ Only PDF files are allowed.", "error");
        return;
    }

    selectedFile = file;

    // Show file details
    fileNameSpan.textContent = file.name;
    fileSizeSpan.textContent = formatSize(file.size);
    fileInfoDiv.style.display = "flex";
    uploadArea.style.display = "none";
    btnUpload.disabled = false;
    uploadResult.style.display = "none";
}


/**
 * Clear the selected file and reset UI.
 */
function clearFile() {
    selectedFile = null;
    pdfInput.value = "";
    fileInfoDiv.style.display = "none";
    uploadArea.style.display = "block";
    btnUpload.disabled = true;
}


/**
 * Format bytes to a human-readable string.
 * @param {number} bytes
 * @returns {string}
 */
function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}


// =============================================
//  2. UPLOAD PDF
// =============================================

btnUpload.addEventListener("click", async () => {
    if (!selectedFile) {
        showResult(uploadResult, "❌ Please select a PDF file first.", "error");
        return;
    }

    // Show loading state on button
    setButtonLoading(btnUpload, true);

    try {
        // Build FormData with the PDF file
        const formData = new FormData();
        formData.append("pdf_file", selectedFile);

        // Send POST /upload
        const response = await fetch("/upload", {
            method: "POST",
            body: formData,
        });

        const data = await response.json();

        if (data.success) {
            // Success — show message
            let html = `<strong>✅ ${data.message}</strong>`;
            if (data.blocks_found && data.blocks_found.length > 0) {
                html += `<br><span style="font-size:0.82rem;color:var(--text-2)">Blocks: ${data.blocks_found.join(", ")} | Rows: ${data.rows_found.join(", ")}</span>`;
            }
            showResult(uploadResult, html, "success");

            // Update status indicator (navbar)
            statusDot.classList.add("online");
            statusText.textContent = `${data.total_records} records loaded`;

            // Show stats cards
            showStats(data);

            // Show preview table
            showPreview(data.preview, data.total_records);
        } else {
            showResult(uploadResult, `❌ ${data.error}`, "error");
        }
    } catch (err) {
        showResult(uploadResult, "❌ Network error. Is the server running?", "error");
    } finally {
        setButtonLoading(btnUpload, false);
    }
});


// =============================================
//  3. SEARCH BY ROLL NUMBER
// =============================================

btnSearch.addEventListener("click", performSearch);
rollInput.addEventListener("keypress", (e) => { if (e.key === "Enter") performSearch(); });


/**
 * Send roll number to /search and display the result.
 * Handles exact matches, fuzzy matches, and not-found.
 */
async function performSearch() {
    const roll = rollInput.value.trim();

    if (!roll) {
        showResult(searchResult, "⚠️ Please enter a roll number.", "error");
        return;
    }

    // Loading state
    setButtonLoading(btnSearch, true);

    try {
        const response = await fetch("/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ roll_number: roll }),
        });

        const data = await response.json();

        if (!data.success) {
            // Error — e.g. no data loaded
            showResult(searchResult, `⚠️ ${data.error}`, "error");
        } else if (data.found) {
            // ---- FOUND: Show detailed seat info ----
            const s = data.data;
            let html = `<strong>✅ ${data.message}</strong>`;

            // Seat info cards
            html += `
                <div class="seat-result">
                    <div class="seat-card">
                        <div class="seat-label">Block</div>
                        <div class="seat-value">${s.block || "—"}</div>
                    </div>
                    <div class="seat-card">
                        <div class="seat-label">Row</div>
                        <div class="seat-value">${s.row || "—"}</div>
                    </div>
                    <div class="seat-card">
                        <div class="seat-label">Seat No.</div>
                        <div class="seat-value">${s.seat || "—"}</div>
                    </div>
                </div>
            `;

            // Student details line
            let date_time = "";
            if (s.exam_date || s.time) {
                date_time = `&nbsp;|&nbsp; ` + (s.exam_date ? `Date: <strong>${s.exam_date}</strong> ` : '') + (s.time ? `Time: <strong>${s.time}</strong>` : '');
            }
            html += `<div class="student-detail">👤 <strong>${s.name || "—"}</strong> &nbsp;|&nbsp; Roll: <strong>${s.roll_no}</strong> ${date_time}</div>`;

            // Fuzzy match note (if applicable)
            if (data.match_type === "fuzzy" && data.note) {
                html += `
                    <div class="fuzzy-note">
                        🧠 <strong>Fuzzy Match:</strong> ${data.note}
                        <div class="confidence-bar">
                            <div class="confidence-fill" style="width:${data.confidence}%"></div>
                        </div>
                    </div>
                `;
            }

            searchResult.style.display = "block";
            searchResult.className = "result-box result-success";
            searchResult.innerHTML = html;
        } else {
            // ---- NOT FOUND ----
            showResult(searchResult, `❌ ${data.message}`, "error");
        }
    } catch (err) {
        showResult(searchResult, "❌ Network error. Is the server running?", "error");
    } finally {
        setButtonLoading(btnSearch, false);
    }
}


// =============================================
//  4. HELPER FUNCTIONS
// =============================================

/**
 * Display a result message in a result-box element.
 * @param {HTMLElement} el   - Result box div
 * @param {string} message   - HTML content
 * @param {string} type      - "success", "error", "info", "warning"
 */
function showResult(el, message, type) {
    el.style.display = "block";
    el.className = `result-box result-${type}`;
    el.innerHTML = message;
}


/**
 * Toggle button loading state.
 * Uses .btn-content and .btn-loading spans inside the button.
 * @param {HTMLElement} btn
 * @param {boolean} loading
 */
function setButtonLoading(btn, loading) {
    const content = btn.querySelector(".btn-content");
    const loader = btn.querySelector(".btn-loading");
    if (content && loader) {
        content.style.display = loading ? "none" : "inline-flex";
        loader.style.display = loading ? "inline-flex" : "none";
    }
    btn.disabled = loading;
}


/**
 * Show statistics cards after PDF upload.
 * @param {Object} data - Response from /upload
 */
function showStats(data) {
    statsSection.style.display = "grid";
    document.getElementById("stat-students").textContent = data.total_records;
    document.getElementById("stat-blocks").textContent = data.blocks_found ? data.blocks_found.length : 0;
    document.getElementById("stat-rows").textContent = data.rows_found ? data.rows_found.length : 0;
    document.getElementById("stat-file").textContent = data.filename || "—";
    document.getElementById("stat-file").style.fontSize = "0.7rem";
}


/**
 * Show the data preview table.
 * @param {Array} records - Array of student objects (first 5)
 * @param {number} total  - Total number of records
 */
function showPreview(records, total) {
    if (!records || records.length === 0) {
        previewSection.style.display = "none";
        return;
    }

    previewSection.style.display = "block";
    previewDesc.textContent = `Showing first ${records.length} of ${total} extracted records.`;

    previewTbody.innerHTML = records.map((s, i) => `
        <tr>
            <td>${i + 1}</td>
            <td><code>${s.roll_no}</code></td>
            <td>${s.name}</td>
            <td>${s.block}</td>
            <td>${s.row}</td>
            <td><strong>${s.seat}</strong></td>
        </tr>
    `).join("");
}


// =============================================
//  5. ON PAGE LOAD — Check if data already loaded
// =============================================
window.addEventListener("DOMContentLoaded", async () => {
    try {
        const res = await fetch("/status");
        const data = await res.json();

        if (data.data_available) {
            statusDot.classList.add("online");
            statusText.textContent = `${data.records_loaded} records loaded`;
        }
    } catch (e) {
        // Server not running — that's okay
    }
});
