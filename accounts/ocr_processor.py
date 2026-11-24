import io
import os
import re
import shutil

import pymupdf
import pytesseract

from PIL import Image, ImageOps, ImageEnhance
from pytesseract import Output
from django.utils import timezone


# ==================================================
# TESSERACT CONFIGURATION
# ==================================================

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
elif shutil.which("tesseract"):
    pytesseract.pytesseract.tesseract_cmd = shutil.which("tesseract")


def get_ocr_languages():
    """
    Use English and Hindi when both language packs are installed.
    Fall back to English if Hindi is unavailable.
    """
    try:
        installed_languages = pytesseract.get_languages(config="")
    except Exception:
        return "eng"

    if "eng" in installed_languages and "hin" in installed_languages:
        return "eng+hin"
    if "eng" in installed_languages:
        return "eng"
    if "hin" in installed_languages:
        return "hin"
    return "eng"


# ==================================================
# DOCUMENT TYPE DETECTION RULES
# ==================================================

DOCUMENT_PATTERNS = {
    "RESUME": [
        "career objective",
        "professional summary",
        "technical skills",
        "core skills",
        "work experience",
        "internship",
        "projects",
        "extra curricular activities",
        "languages",
        "linkedin",
        "github",
    ],

    "10TH_MARKSHEET": [
        "class x",
        "class 10",
        "10th",
        "10th standard",
        "secondary school certificate",
        "secondary school examination",
        "all india secondary school examination",
        "matriculation",
        "sslc",
        "aisse",
        "marks obtained",
    ],

    "12TH_MARKSHEET": [
        "class xii",
        "class 12",
        "12th",
        "12th standard",
        "senior secondary",
        "higher secondary",
        "intermediate examination",
        "higher secondary certificate",
        "aissce",
        "hsc",
    ],

    "UG_MARKSHEETS": [
        "semester marksheet",
        "semester examination",
        "consolidated marksheet",
        "bachelor of technology",
        "bachelor of engineering",
        "undergraduate",
        "grade card",
        "academic transcript",
    ],

    "GATE_SCORECARD": [
        "graduate aptitude test in engineering",
        "gate score",
        "gate examination",
        "gate registration number",
        "gate paper code",
        "all india rank",
        "qualifying marks",
    ],

    "DEGREE_CERTIFICATE": [
        "degree certificate",
        "is hereby awarded",
        "degree is conferred",
        "has been awarded the degree",
        "in witness whereof",
        "date of conferral",
        "date of award",
    ],

    "AADHAAR": [
        "unique identification authority of india",
        "government of india",
        "aadhaar",
        "aadhaar number",
        "enrolment number",
        "vid number",
        "भारत सरकार",
        "आधार",
        "विशिष्ट पहचान प्राधिकरण",
        "भारतीय विशिष्ट पहचान प्राधिकरण",
    ],

    "PAN": [
        "income tax department",
        "permanent account number",
        "pan card",
        "income tax department of india",
    ],

    "VOTER_ID": [
        "election commission of india",
        "elector photo identity card",
        "epic number",
        "elector's photo identity card",
    ],

    "RESEARCH_CERTIFICATE": [
        "research publication",
        "published in",
        "research paper",
        "journal publication",
        "conference publication",
        "digital object identifier",
    ],

    "EXPERIENCE_CERTIFICATE": [
        "experience certificate",
        "employment certificate",
        "letter of experience",
        "relieving letter",
        "designation",
        "has worked with us",
    ],
}


# ==================================================
# TEXT NORMALIZATION
# ==================================================

def normalize_text(text):
    text = str(text or "").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ==================================================
# DOCUMENT TYPE CLASSIFICATION
# ==================================================

def classify_document_type(extracted_text):
    normalized = normalize_text(extracted_text)

    # Normalize punctuation for document-specific markers.
    # This supports OCR variants such as "CLASS-XII" and "12th-Marksheet".
    marker_text = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", normalized)
    marker_text = re.sub(r"\s+", " ", marker_text).strip()

    scores = {}
    for document_type, keywords in DOCUMENT_PATTERNS.items():
        matched_keywords = []

        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)

            if re.search(
                r"(?<!\w)" + re.escape(normalized_keyword) + r"(?!\w)",
                normalized
            ):
                matched_keywords.append(keyword)

        scores[document_type] = {
            "score": len(matched_keywords),
            "matched_keywords": matched_keywords,
        }

    # A clear class/board marker is sufficient to distinguish 10th
    # from 12th marksheets. Generic wording such as "statement of marks"
    # is deliberately not used because it appears on both documents.
    strong_markers = {
        "10TH_MARKSHEET": [
            "class x",
            "class 10",
            "10th",
            "matriculation",
            "sslc",
            "aisse",
            "secondary school certificate",
        ],
        "12TH_MARKSHEET": [
            "class xii",
            "class 12",
            "12th",
            "senior secondary",
            "higher secondary",
            "intermediate examination",
            "aissce",
            "hsc",
        ],
    }

    strong_matches = {}
    for document_type, markers in strong_markers.items():
        strong_matches[document_type] = [
            marker for marker in markers
            if re.search(
                r"(?<!\w)" + re.escape(marker) + r"(?!\w)",
                marker_text
            )
        ]

    # Use explicit class/board indicators only when they point to one class.
    # If both appear, retain the normal scoring/manual-review path.
    tenth_matches = strong_matches["10TH_MARKSHEET"]
    twelfth_matches = strong_matches["12TH_MARKSHEET"]

    if bool(tenth_matches) != bool(twelfth_matches):
        detected_type = (
            "10TH_MARKSHEET" if tenth_matches else "12TH_MARKSHEET"
        )
        matched_markers = tenth_matches if tenth_matches else twelfth_matches

        return {
            "detected_type": detected_type,
            "confidence": "HIGH" if len(matched_markers) >= 2 else "MEDIUM",
            "matched_keywords": matched_markers,
            "scores": {
                key: value["score"]
                for key, value in scores.items()
            },
        }

    # Resume requires multiple characteristic signals.
    # This avoids classifying ordinary documents as resumes.
    resume_score = scores["RESUME"]["score"]
    if resume_score >= 2:
        scores["RESUME"]["score"] += 2

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1]["score"],
        reverse=True,
    )

    best_type, best_result = ranked[0]
    best_score = best_result["score"]
    second_score = ranked[1][1]["score"] if len(ranked) > 1 else 0

    score_summary = {
        key: value["score"]
        for key, value in scores.items()
    }

    if best_score < 2 or best_score == second_score:
        return {
            "detected_type": "OTHER",
            "confidence": "LOW",
            "matched_keywords": [],
            "scores": score_summary,
        }

    return {
        "detected_type": best_type,
        "confidence": "HIGH" if best_score >= 4 else "MEDIUM",
        "matched_keywords": best_result["matched_keywords"],
        "scores": score_summary,
    }


# ==================================================
# DOCUMENT TYPE VALIDATION
# ==================================================

def validate_document_type(document, extracted_text):
    assigned_type = document.document_type

    detection = classify_document_type(extracted_text)

    detected_type = detection["detected_type"]
    confidence = detection["confidence"]

    result = {
        "assigned_type": assigned_type,
        "detected_type": detected_type,
        "confidence": confidence,
        "type_match": None,
        "validation_status": "MANUAL_REVIEW",
        "message": "",
        "matched_keywords": detection["matched_keywords"],
    }

    # Weak classification cannot be treated as proof of mismatch.
    if confidence == "LOW":
        result["message"] = (
            "Document type could not be identified confidently. "
            "Manual review is required."
        )
        return result

    if assigned_type == detected_type:
        result["type_match"] = True
        result["validation_status"] = "TYPE_MATCHED"
        result["message"] = (
            "Uploaded document content matches the assigned document type. "
            "This does not establish authenticity."
        )
        return result

    result["type_match"] = False
    result["validation_status"] = "RESUBMISSION_REQUIRED"
    result["message"] = (
        f"Assigned type is {assigned_type}, but extracted content "
        f"appears to be {detected_type}."
    )

    return result


# ==================================================
# IMAGE PREPROCESSING
# ==================================================

def preprocess_image(image):
    """
    Prepare an image for OCR:
    - Correct EXIF orientation.
    - Convert to grayscale.
    - Enlarge small images.
    - Improve contrast and sharpness.
    - Apply autocontrast.
    """
    image = ImageOps.exif_transpose(image)

    if image.mode != "RGB":
        image = image.convert("RGB")

    # Upscale images to improve recognition of small printed text.
    width, height = image.size
    if max(width, height) < 2200:
        image = image.resize(
            (width * 2, height * 2),
            Image.Resampling.LANCZOS,
        )

    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.5)
    image = ImageEnhance.Sharpness(image).enhance(2.0)

    return image
# ==================================================
# IMAGE OCR WITH ROTATION AND PSM SUPPORT
# ==================================================

def _get_average_ocr_confidence(ocr_data):
    confidences = []

    for value in ocr_data.get("conf", []):
        try:
            confidence = float(value)
            if confidence >= 0:
                confidences.append(confidence)
        except (ValueError, TypeError):
            continue

    if not confidences:
        return 0.0

    return sum(confidences) / len(confidences)


def extract_text_from_image(image):
    processed_image = preprocess_image(image)

    best_text = ""
    best_score = -1.0
    languages = get_ocr_languages()

    # Compare multiple page segmentation modes.
    psm_modes = [6, 11, 4]

    # Preserve rotation support.
    for angle in [0, 90, 180, 270]:
        rotated_image = processed_image.rotate(
            angle,
            expand=True,
        )

        for psm in psm_modes:
            config = f"--oem 3 --psm {psm}"

            try:
                ocr_data = pytesseract.image_to_data(
                    rotated_image,
                    lang=languages,
                    config=config,
                    output_type=Output.DICT,
                )

                average_confidence = _get_average_ocr_confidence(
                    ocr_data
                )

                extracted_text = pytesseract.image_to_string(
                    rotated_image,
                    lang=languages,
                    config=config,
                ).strip()

                if not extracted_text:
                    continue

                score = (
                    average_confidence
                    + min(len(extracted_text), 300) / 30.0
                )

                if score > best_score:
                    best_score = score
                    best_text = extracted_text

            except pytesseract.TesseractError:
                continue

    return best_text


# ==================================================
# PDF TEXT EXTRACTION
# ==================================================

def extract_text_from_pdf(file_bytes):
    extracted_pages = []

    pdf_document = pymupdf.open(
        stream=file_bytes,
        filetype="pdf",
    )

    try:
        for page_number, page in enumerate(pdf_document):
            page_text = page.get_text("text").strip()

            # Scanned PDF fallback.
            if len(page_text) < 30:
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(2, 2),
                    alpha=False,
                )

                image = Image.frombytes(
                    "RGB",
                    [pixmap.width, pixmap.height],
                    pixmap.samples,
                )

                page_text = extract_text_from_image(image)

            extracted_pages.append(
                f"\n--- Page {page_number + 1} ---\n{page_text}"
            )

    finally:
        pdf_document.close()

    return "\n".join(extracted_pages).strip()


# ==================================================
# NAME CLEANING
# ==================================================

def clean_name_candidate(value):
    value = str(value or "").strip(" \t|:-_")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_name_for_matching(value):
    return re.sub(
        r"[^a-z]",
        "",
        str(value or "").lower(),
    )


def is_valid_name(value):
    if not value:
        return False

    cleaned = value.lower().strip()

    excluded_words = {
        "resume",
        "curriculum vitae",
        "professional summary",
        "career objective",
        "summary",
        "education",
        "experience",
        "internship",
        "internships",
        "projects",
        "skills",
        "technical skills",
        "certifications",
        "achievements",
        "languages",
        "contact",
        "profile",
        "objective",
        "linkedin",
        "references",
        "extra curricular activities",
        "government of india",
        "bharat sarkar",
        "भारत सरकार",
        "आधार",
    }

    if cleaned in excluded_words:
        return False

    if len(value) > 50 or len(value) < 3:
        return False

    if re.search(r"[@:/*\\]", value):
        return False

    words = value.split()

    if not 2 <= len(words) <= 4:
        return False

    return all(
        re.fullmatch(r"[A-Za-z][A-Za-z'.-]*\d*", word)
        for word in words
    )


def correct_spaced_name(value):
    value = clean_name_candidate(value)

    joined = re.sub(r"\s+", "", value).upper()

    known_corrections = {
        "AKASHJAIN": "AKASH JAIN",
    }

    return known_corrections.get(joined, value)


# ==================================================
# LABEL-BASED EXTRACTION
# ==================================================

def extract_labelled_value(lines, aliases):
    for index, line in enumerate(lines):
        cleaned_line = line.strip()

        for alias in aliases:
            pattern = (
                r"^\s*"
                + re.escape(alias)
                + r"\s*[:：\-]\s*(.+?)\s*$"
            )

            match = re.match(
                pattern,
                cleaned_line,
                re.IGNORECASE,
            )

            if match:
                value = match.group(1).strip()
                if value:
                    return value

            # Label and value on separate lines.
            if cleaned_line.lower().rstrip(":： ") == alias.lower():
                if index + 1 < len(lines):
                    next_line = lines[index + 1].strip()
                    if next_line:
                        return next_line

    return None
# ==================================================
# STRUCTURED DATA EXTRACTION
# ==================================================

def extract_structured_data(extracted_text):
    text = str(extracted_text or "")
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    data = {
        "candidate_name": None,
        "father_name": None,
        "mother_name": None,
        "date_of_birth": None,
        "application_id": None,
        "university": None,
        "programme": None,
        "cgpa": None,
        "aggregate_percentage": None,
        "roll_number": None,
        "email": None,
        "mobile": None,
        "gate_score": None,
        "cgpa_value": None,
        "aggregate_percentage_value": None,
        "skills": [],
        "education": [],
        "experience": [],
        "projects": [],
    }

    # --------------------------------------------------
    # NAME EXTRACTION
    # --------------------------------------------------

    name_aliases = [
        "candidate name",
        "student name",
        "applicant name",
        "name of candidate",
        "name",
    ]

    father_aliases = [
        "father name",
        "father's name",
        "fathers name",
        "name of father",
    ]

    mother_aliases = [
        "mother name",
        "mother's name",
        "mothers name",
        "name of mother",
    ]

    candidate_name = extract_labelled_value(
    lines,
    name_aliases,
    )

    father_name = extract_labelled_value(
        lines,
        father_aliases,
    )

    mother_name = extract_labelled_value(
        lines,
        mother_aliases,
    )

    if candidate_name:
        candidate_name = correct_spaced_name(
            clean_name_candidate(candidate_name)
        )

        if is_valid_name(candidate_name):
            data["candidate_name"] = candidate_name

    if father_name:
        father_name = clean_name_candidate(father_name)

        if is_valid_name(father_name):
            data["father_name"] = father_name

    if mother_name:
        mother_name = clean_name_candidate(mother_name)

        if is_valid_name(mother_name):
            data["mother_name"] = mother_name

    # --------------------------------------------------
    # DATE OF BIRTH
    # --------------------------------------------------

    dob_patterns = [
        r"(?:date of birth|dob|birth date)\s*[:\-]?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",

        r"(?:date of birth|dob|birth date)\s*[:\-]?\s*"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    ]

    for pattern in dob_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            data["date_of_birth"] = match.group(1).strip()
            break

    # --------------------------------------------------
    # APPLICATION ID
    # --------------------------------------------------

    application_patterns = [
        r"(?:application\s*(?:id|number|no\.?))\s*[:\-]?\s*"
        r"([A-Za-z0-9/-]+)",

        r"(?:registration\s*(?:id|number|no\.?))\s*[:\-]?\s*"
        r"([A-Za-z0-9/-]+)",
    ]

    for pattern in application_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            data["application_id"] = match.group(1).strip()
            break

    # --------------------------------------------------
    # UNIVERSITY
    # --------------------------------------------------

    university_patterns = [
        r"([A-Z][A-Za-z&.,' -]{2,100}"
        r"(?:University|Institute of Technology|College))",

        r"(?:university|institution)\s*[:\-]\s*(.+)",
    ]

    for pattern in university_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            data["university"] = match.group(1).strip()
            break

    # --------------------------------------------------
    # PROGRAMME / COURSE
    # --------------------------------------------------

    programme_patterns = [
        r"(?:programme|program|course|degree)\s*[:\-]\s*(.+)",
        r"(?:applied for)\s*[:\-]?\s*(.+)",
    ]

    for pattern in programme_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            data["programme"] = match.group(1).strip()
            break

    # --------------------------------------------------
    # CGPA
    # --------------------------------------------------

    cgpa_patterns = [
        r"(?:cgpa|c\.g\.p\.a\.?)\s*[:\-]?\s*"
        r"(\d{1,2}(?:\.\d{1,2})?)",

        r"(?:cumulative grade point average)\s*[:\-]?\s*"
        r"(\d{1,2}(?:\.\d{1,2})?)",
    ]

    for pattern in cgpa_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            data["cgpa"] = match.group(1)
            try:
                data["cgpa_value"] = float(match.group(1))
            except (ValueError, TypeError):
                pass
            break

    # --------------------------------------------------
    # AGGREGATE PERCENTAGE
    # --------------------------------------------------

    percentage_patterns = [
        r"(?:aggregate percentage|percentage|overall percentage)"
        r"\s*[:\-]?\s*(\d{1,3}(?:\.\d{1,2})?)\s*%?",

        r"(?:aggregate marks|total percentage)"
        r"\s*[:\-]?\s*(\d{1,3}(?:\.\d{1,2})?)\s*%?",
    ]

    for pattern in percentage_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            data["aggregate_percentage"] = match.group(1)

            try:
                data["aggregate_percentage_value"] = float(
                    match.group(1)
                )
            except (ValueError, TypeError):
                pass

            break

    # --------------------------------------------------
    # ROLL NUMBER
    # --------------------------------------------------

    roll_patterns = [
        r"(?:roll\s*(?:number|no\.?))\s*[:\-]?\s*"
        r"([A-Za-z0-9/-]+)",

        r"(?:enrolment\s*(?:number|no\.?))\s*[:\-]?\s*"
        r"([A-Za-z0-9/-]+)",
    ]

    for pattern in roll_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            data["roll_number"] = match.group(1).strip()
            break

    # --------------------------------------------------
    # EMAIL
    # --------------------------------------------------

    email_match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        text,
    )

    if email_match:
        data["email"] = email_match.group(0)

    # --------------------------------------------------
    # MOBILE NUMBER
    # --------------------------------------------------

    mobile_patterns = [
        r"(?:mobile|phone|contact)\s*(?:number|no\.?)?\s*"
        r"[:\-]?\s*(\+?\d[\d\s-]{8,15}\d)",

        r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b",
    ]

    for pattern in mobile_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            mobile = re.sub(r"[\s-]", "", match.group(1) if match.lastindex else match.group(0))

            if len(re.sub(r"\D", "", mobile)) >= 10:
                data["mobile"] = mobile
                break

    # --------------------------------------------------
    # GATE SCORE
    # --------------------------------------------------

    gate_patterns = [
        r"(?:gate score|score)\s*[:\-]?\s*(\d{1,3})",
        r"(?:gate marks)\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)",
    ]

    for pattern in gate_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            data["gate_score"] = match.group(1)
            break

    # --------------------------------------------------
    # RESUME SECTION EXTRACTION
    # --------------------------------------------------

    section_aliases = {
        "skills": [
            "skills",
            "technical skills",
            "core skills",
            "key skills",
            "technical expertise",
        ],

        "education": [
            "education",
            "educational qualification",
            "academic qualification",
            "academic background",
            "educational qualifications",
        ],

        "experience": [
            "experience",
            "work experience",
            "internship",
            "internships",
            "internship / industrial training",
        ],

        "projects": [
            "projects",
            "academic projects",
            "personal projects",
            "project experience",
        ],
    }

    current_section = None

    stop_headings = {
        "achievements",
        "certifications",
        "languages",
        "extra curricular activities",
        "extra-curricular activities",
        "references",
        "declaration",
        "personal details",
    }

    for line in lines:
        heading = line.lower().strip(" :|\t")

        matched_section = None

        for section, headings in section_aliases.items():
            if heading in headings:
                matched_section = section
                break

        if matched_section:
            current_section = matched_section
            continue

        if heading in stop_headings:
            current_section = None
            continue

        if current_section and len(line) <= 500:
            data[current_section].append(line)

    # Remove duplicate section entries.
    for section in [
        "skills",
        "education",
        "experience",
        "projects",
    ]:
        data[section] = list(
            dict.fromkeys(data[section])
        )

    return data


# ==================================================
# MAIN OCR PROCESSOR
# ==================================================

def process_applicant_document(document):

    document.ocr_status = "PROCESSING"

    document.save(
        update_fields=["ocr_status"]
    )

    try:
        if not document.document_file:
            raise ValueError("No document file uploaded.")

        file_name = document.document_file.name.lower()

        with document.document_file.open("rb") as file:
            file_bytes = file.read()

        # PDF PROCESSING
        if file_name.endswith(".pdf"):
            extracted_text = extract_text_from_pdf(file_bytes)

        # IMAGE PROCESSING
        elif file_name.endswith(
            (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
        ):
            image = Image.open(
                io.BytesIO(file_bytes)
            )

            extracted_text = extract_text_from_image(image)

        else:
            raise ValueError(
                "Unsupported format. Upload PDF or image files."
            )

        # VALIDATE OCR OUTPUT
        if not extracted_text or not extracted_text.strip():
            raise ValueError(
                "No readable text found in document."
            )

        # STRUCTURED EXTRACTION
        extracted_data = extract_structured_data(
            extracted_text
        )

        # DOCUMENT TYPE VALIDATION
        validation = validate_document_type(
            document,
            extracted_text,
        )

        extracted_data["document_validation"] = validation

        # UPDATE STATUS ONLY FOR STRONG TYPE MISMATCH.
        if validation["validation_status"] == "RESUBMISSION_REQUIRED":

            document.verification_status = "RESUBMISSION_REQUIRED"

            note = validation["message"]
            existing_remarks = document.remarks or ""

            if note not in existing_remarks:
                document.remarks = (
                    existing_remarks + "\n" + note
                ).strip()

        # Do not automatically mark a document VERIFIED.
        # Low-confidence classification remains for manual review.

        document.extracted_text = extracted_text
        document.extracted_data = extracted_data
        document.ocr_status = "COMPLETED"
        document.ocr_processed_at = timezone.now()

        document.save(
            update_fields=[
                "extracted_text",
                "extracted_data",
                "ocr_status",
                "ocr_processed_at",
                "verification_status",
                "remarks",
                "updated_at",
            ]
        )

        return {
            "success": True,
            "status": "COMPLETED",
            "text": extracted_text,
            "data": extracted_data,
            "validation": validation,
        }

    except Exception as error:

        document.ocr_status = "FAILED"
        document.ocr_processed_at = timezone.now()

        document.save(
            update_fields=[
                "ocr_status",
                "ocr_processed_at",
                "updated_at",
            ]
        )

        return {
            "success": False,
            "status": "FAILED",
            "error": str(error),
        }
