"""

Cross-document verification engine.

Safety:

- preview_applicant_documents() is read-only and never creates a database record.

- verify_applicant_documents() preserves the previous save behaviour and creates

  an ApplicantCrossDocumentVerification record when explicitly called.

- This module never changes ApplicantDocument.verification_status.

"""

import hashlib

import re

import unicodedata

from datetime import date, datetime

from decimal import Decimal, InvalidOperation

from django.db import transaction

from accounts.models import (

    Applicant,

    ApplicantDocument,

    ApplicantCrossDocumentVerification,

)

# ---------------------------------------------------------------------

# FIELD CONFIGURATION

# ---------------------------------------------------------------------

FIELD_CONFIG = {

    "candidate_name": {

        "label": "Candidate Name",

        # Identity-bearing sources only. OTHER test/supporting documents are excluded.

        "document_types": [

            "RESUME",

            "10TH_MARKSHEET",

            "12TH_MARKSHEET",

            "UG_MARKSHEETS",

            "DEGREE_CERTIFICATE",

            "AADHAAR",

        ],

        "applicant_field": "full_name",

    },

    "father_name": {

        "label": "Father's Name",

        # Ignore generic OTHER/test uploads as identity evidence.

        "document_types": [

            "RESUME",

            "10TH_MARKSHEET",

            "12TH_MARKSHEET",

            "UG_MARKSHEETS",

            "DEGREE_CERTIFICATE",

            "AADHAAR",

        ],

        "applicant_field": None,

    },

    "mother_name": {

        "label": "Mother's Name",

        # Ignore generic OTHER/test uploads as identity evidence.

        "document_types": [

            "RESUME",

            "10TH_MARKSHEET",

            "12TH_MARKSHEET",

            "UG_MARKSHEETS",

            "DEGREE_CERTIFICATE",

            "AADHAAR",

        ],

        "applicant_field": None,

    },

    "date_of_birth": {

        "label": "Date of Birth",

        # Exclude OTHER OCR test documents from identity comparison.

        "document_types": [

            "RESUME",

            "10TH_MARKSHEET",

            "12TH_MARKSHEET",

            "UG_MARKSHEETS",

            "DEGREE_CERTIFICATE",

            "AADHAAR",

        ],

        "applicant_field": "date_of_birth",

    },

    "application_id": {

        "label": "Application ID",

        # Ignore generic OTHER uploads; only application/resume and exam records

        # are considered potential supporting sources.

        "document_types": ["RESUME"],

        "applicant_field": "application_id",

    },

    "university": {

        "label": "University",

        "document_types": ["UG_MARKSHEETS", "DEGREE_CERTIFICATE"],

        "applicant_field": "university_name",

    },

    "cgpa": {

        "label": "CGPA",

        "document_types": ["UG_MARKSHEETS", "DEGREE_CERTIFICATE"],

        "applicant_field": "cgpa",

        "numeric": True,

    },

    "aggregate_percentage": {

        "label": "Aggregate Percentage",

        "document_types": ["UG_MARKSHEETS", "DEGREE_CERTIFICATE"],

        "applicant_field": "aggregate_percentage",

        "numeric": True,

    },

    "email": {

        "label": "Email",

        # Contact details are compared from resumes, not generic OTHER uploads.

        "document_types": ["RESUME"],

        "applicant_field": "email",

        "email": True,

    },

    "mobile_number": {

        "label": "Mobile Number",

        "document_types": ["RESUME"],

        "applicant_field": "mobile_number",

        "mobile": True,

    },

    "gate_score": {

        "label": "GATE Score",

        "document_types": ["GATE_SCORECARD"],

        "applicant_field": None,

        "numeric": True,

    },

}

DOCUMENT_SPECIFIC_FIELDS = {

    "roll_number": {

        "label": "Roll Number",

        "document_types": [

            "10TH_MARKSHEET",

            "12TH_MARKSHEET",

            "UG_MARKSHEETS",

            "DEGREE_CERTIFICATE",

        ],

    },

}

# These terms are strong indicators that OCR captured a sentence/label

# instead of a person's name. Such values are flagged, not compared.

NAME_NOISE_TERMS = {

    "important",

    "famille",

    "famille.",

    "government",

    "gouvernement",

    "india",

    "identification",

    "authority",

    "republic",

    "uidai",

    "aadhaar",

}

# ---------------------------------------------------------------------

# NORMALIZATION

# ---------------------------------------------------------------------

def _clean_missing(value):

    if value is None:

        return None

    text = str(value).strip()

    if not text or text.casefold() in {

        "none", "null", "n/a", "na", "not provided", "unknown", "-"

    }:

        return None

    return text

def normalize_text(value):

    """Normalize Unicode text while retaining letters and digits."""

    text = _clean_missing(value)

    if text is None:

        return None

    text = unicodedata.normalize("NFKC", text).casefold()

    normalized = "".join(ch for ch in text if ch.isalnum())

    return normalized or None

def normalize_name(value):

    """Normalize a name and reject obvious OCR labels/noise phrases."""

    text = _clean_missing(value)

    if text is None:

        return None, "Name value is empty."

    cleaned = unicodedata.normalize("NFKC", text).strip()

    words = re.findall(r"[^\W\d_]+", cleaned.casefold(), flags=re.UNICODE)

    if not words:

        return None, "OCR value does not contain a readable name."

    if any(word in NAME_NOISE_TERMS for word in words):

        return None, "OCR value appears to contain a document label or sentence, not a name."

    if len(words) < 2:

        return None, "Only one name token was extracted; manual review is recommended."

    normalized = "".join(ch for ch in cleaned.casefold() if ch.isalnum())

    if not normalized:

        return None, "Name could not be normalized."

    return normalized, None

def normalize_numeric(value):

    text = _clean_missing(value)

    if text is None:

        return None

    # Capture the first numeric token, supporting decimal values.

    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))

    if not match:

        return None

    try:

        return str(Decimal(match.group()).normalize())

    except InvalidOperation:

        return None

def normalize_date(value):

    if value is None:

        return None

    if isinstance(value, (date, datetime)):

        return value.strftime("%Y-%m-%d")

    text = str(value).strip()

    if not text:

        return None

    formats = (

        "%d/%m/%Y",

        "%d-%m-%Y",

        "%Y-%m-%d",

        "%d/%m/%y",

        "%d-%m-%y",

        "%d %B %Y",

        "%d %b %Y",

        "%B %d, %Y",

        "%b %d, %Y",

    )

    for date_format in formats:

        try:

            return datetime.strptime(text, date_format).strftime("%Y-%m-%d")

        except ValueError:

            continue

    return None

def normalize_email(value):

    text = _clean_missing(value)

    if text is None:

        return None

    text = text.strip().casefold()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):

        return None

    return text

def normalize_mobile(value):

    text = _clean_missing(value)

    if text is None:

        return None

    digits = re.sub(r"\D", "", text)

    # Normalize common Indian country-code representations.

    if len(digits) == 12 and digits.startswith("91"):

        digits = digits[2:]

    elif len(digits) == 11 and digits.startswith("0"):

        digits = digits[1:]

    return digits if 10 <= len(digits) <= 15 else None

def normalize_field_value(value, field_name, config):

    if field_name == "candidate_name":

        return normalize_name(value)[0]

    if field_name == "date_of_birth":

        return normalize_date(value)

    if config.get("email"):

        return normalize_email(value)

    if config.get("mobile"):

        return normalize_mobile(value)

    if config.get("numeric"):

        return normalize_numeric(value)

    return normalize_text(value)

# ---------------------------------------------------------------------

# FILE HASH / DUPLICATE DETECTION

# ---------------------------------------------------------------------

def get_document_sha256(document):

    """

    Return a SHA-256 digest for the stored file.

    Return None if the file cannot be read; never modify the file.

    """

    file_field = getattr(document, "document_file", None)

    if not file_field:

        return None

    try:

        digest = hashlib.sha256()

        file_field.open("rb")

        try:

            for chunk in file_field.chunks():

                digest.update(chunk)

        finally:

            file_field.close()

        return digest.hexdigest()

    except Exception:

        # Storage backends can raise backend-specific exceptions.

        return None

def build_duplicate_groups(documents):

    """

    Group identical uploaded files. A group is counted once as evidence.

    If identical bytes have different assigned document types, flag the group.

    """

    groups = {}

    for document in documents:

        digest = get_document_sha256(document)

        # A missing/unreadable file is kept separate; it is not assumed duplicate.

        group_key = digest or f"unreadable-file-document-{document.id}"

        entry = groups.setdefault(

            group_key,

            {

                "sha256": digest,

                "documents": [],

                "document_types": set(),

            },

        )

        entry["documents"].append(document)

        entry["document_types"].add(document.document_type)

    duplicate_groups = []

    document_to_group = {}

    for group_key, entry in groups.items():

        docs = entry["documents"]

        types = sorted(entry["document_types"])

        is_duplicate = len(docs) > 1

        type_conflict = len(types) > 1

        group_info = {

            "group_id": group_key,

            "sha256": entry["sha256"],

            "document_ids": [doc.id for doc in docs],

            "document_types": types,

            "is_duplicate": is_duplicate,

            "document_type_conflict": type_conflict,

            "evidence_count": 1,

        }

        if is_duplicate:

            duplicate_groups.append(group_info)

        for document in docs:

            document_to_group[document.id] = group_info

    return duplicate_groups, document_to_group

# ---------------------------------------------------------------------

# VALUE COLLECTION AND COMPARISON

# ---------------------------------------------------------------------

def _document_display_name(document):

    try:

        return document.get_document_type_display()

    except Exception:

        return document.document_type

def _collect_document_values(

    documents,

    document_to_group,

    field_name,

    config,

):

    """

    Collect at most one identical value per physical file.

    Different OCR values from the same physical file are retained and flagged.

    """

    collected = []

    seen = set()

    warnings = []

    allowed_types = config.get("document_types")

    for document in documents:

        if allowed_types and document.document_type not in allowed_types:

            continue

        extracted_data = document.extracted_data or {}

        raw_value = extracted_data.get(field_name)

        if raw_value is None:

            continue

        if field_name == "candidate_name":

            normalized, name_warning = normalize_name(raw_value)

            if name_warning:

                warnings.append({

                    "field": field_name,

                    "document_id": document.id,

                    "document_type": document.document_type,

                    "raw_value": str(raw_value),

                    "message": name_warning,

                })

                continue

        else:

            normalized = normalize_field_value(raw_value, field_name, config)

        if normalized is None:

            warnings.append({

                "field": field_name,

                "document_id": document.id,

                "document_type": document.document_type,

                "raw_value": str(raw_value),

                "message": "Value could not be normalized; manual review may be required.",

            })

            continue

        group = document_to_group.get(document.id, {})

        group_id = group.get("group_id", f"document-{document.id}")

        dedupe_key = (group_id, normalized)

        if dedupe_key in seen:

            continue

        seen.add(dedupe_key)

        collected.append({

            "source": _document_display_name(document),

            "document_id": document.id,

            "document_type": document.document_type,

            "duplicate_group_id": group_id,

            "raw_value": str(raw_value),

            "normalized_value": str(normalized),

            "duplicate_file": bool(group.get("is_duplicate")),

            "document_type_conflict": bool(group.get("document_type_conflict")),

        })

    return collected, warnings

def _get_profile_value(applicant, field_name, config):

    applicant_field = config.get("applicant_field")

    if not applicant_field:

        return None

    raw_value = getattr(applicant, applicant_field, None)

    if raw_value is None:

        return None

    normalized = normalize_field_value(raw_value, field_name, config)

    if normalized is None:

        return None

    return {

        "source": "Applicant Profile",

        "raw_value": str(raw_value),

        "normalized_value": str(normalized),

    }

def compare_field(

    applicant,

    documents,

    document_to_group,

    field_name,

    config,

):

    document_values, extraction_warnings = _collect_document_values(

        documents,

        document_to_group,

        field_name,

        config,

    )

    profile_value = _get_profile_value(applicant, field_name, config)

    values = []

    if profile_value:

        values.append(profile_value)

    values.extend(document_values)

    unique_values = {item["normalized_value"] for item in values}

    # A file uploaded under conflicting document categories is only one physical

    # evidence source, and its document identity is uncertain. For candidate

    # name, do not treat that uncertain category as conclusive proof of mismatch.

    candidate_name_has_only_ambiguous_document_evidence = (

        field_name == "candidate_name"

        and bool(document_values)

        and all(item.get("document_type_conflict") for item in document_values)

    )

    if not values:

        status = "NOT_FOUND"

        message = "No usable value was found in the profile or eligible documents."

    elif candidate_name_has_only_ambiguous_document_evidence:

        status = "MANUAL_REVIEW"

        message = (

            "A different candidate name was extracted, but all document evidence "

            "comes from files uploaded under conflicting document categories. "

            "Confirm the original document type before deciding whether this is a mismatch."

        )

        extraction_warnings.append({

            "field": field_name,

            "message": (

                "Candidate-name evidence is not independent or conclusive because "

                "the exact same file content was assigned multiple document types. "

                "Manual document-category confirmation is required."

            ),

            "document_ids": sorted({item["document_id"] for item in document_values}),

            "duplicate_group_ids": sorted({

                item.get("duplicate_group_id")

                for item in document_values

                if item.get("duplicate_group_id")

            }),

        })

    elif len(values) == 1 and profile_value:

        status = "PROFILE_ONLY"

        message = "Only the Applicant Profile value is available; no document comparison was possible."

    elif len(unique_values) == 1:

        status = "MATCH"

        message = "All usable values match after normalization."

    else:

        status = "MISMATCH"

        message = "Different usable values were found across the profile and eligible documents."

    type_conflict_ids = sorted({

        item["document_id"]

        for item in document_values

        if item.get("document_type_conflict")

    })

    if type_conflict_ids and not candidate_name_has_only_ambiguous_document_evidence:

        extraction_warnings.append({

            "field": field_name,

            "message": (

                "Some identical files were uploaded under different document types. "

                "Their assigned categories need manual confirmation."

            ),

            "document_ids": type_conflict_ids,

        })

    return {

        "field": field_name,

        "label": config["label"],

        "status": status,

        "values": values,

        "message": message,

        "warnings": extraction_warnings,

    }

# ---------------------------------------------------------------------

# DOCUMENT-SPECIFIC COMPARISON

# ---------------------------------------------------------------------

def compare_document_specific_field(

    documents,

    document_to_group,

    field_name,

    config,

):

    grouped_values = {}

    warnings = []

    for document in documents:

        if document.document_type not in config["document_types"]:

            continue

        raw_value = (document.extracted_data or {}).get(field_name)

        normalized = normalize_text(raw_value)

        if normalized is None:

            continue

        group = document_to_group.get(document.id, {})

        group_id = group.get("group_id", f"document-{document.id}")

        dedupe_key = (group_id, normalized)

        category_values = grouped_values.setdefault(document.document_type, {})

        if dedupe_key in category_values:

            continue

        category_values[dedupe_key] = {

            "source": _document_display_name(document),

            "document_id": document.id,

            "document_type": document.document_type,

            "raw_value": str(raw_value),

            "normalized_value": normalized,

            "duplicate_file": bool(group.get("is_duplicate")),

            "document_type_conflict": bool(group.get("document_type_conflict")),

        }

    results = []

    for document_type, value_map in grouped_values.items():

        values = list(value_map.values())

        unique_values = {item["normalized_value"] for item in values}

        status = "MATCH" if len(unique_values) == 1 else "MISMATCH"

        results.append({

            "field": field_name,

            "label": config["label"],

            "document_type": document_type,

            "status": status,

            "values": values,

            "message": (

                "Values match within this document category."

                if status == "MATCH"

                else "Different values were found within this document category."

            ),

        })

    if not results:

        warnings.append({

            "field": field_name,

            "label": config["label"],

            "message": "No document-specific value was found.",

        })

    return results, warnings

# ---------------------------------------------------------------------

# READ-ONLY PREVIEW

# ---------------------------------------------------------------------

def preview_applicant_documents(applicant):

    """

    Build a read-only verification preview.

    This function DOES NOT create/update any database record.

    """

    if isinstance(applicant, int):

        applicant = Applicant.objects.get(id=applicant)

    documents = list(

        ApplicantDocument.objects.filter(

            applicant=applicant,

            ocr_status="COMPLETED",

        ).exclude(

            extracted_data={},

        ).order_by("uploaded_at", "id")

    )

    duplicate_groups, document_to_group = build_duplicate_groups(documents)

    comparison_results = []

    matched_fields = []

    mismatches = []

    warnings = []

    for group in duplicate_groups:

        if group["document_type_conflict"]:

            warnings.append({

                "field": "duplicate_file_detection",

                "message": (

                    "The same file content was uploaded under different document types. "

                    "Please manually confirm the correct document category."

                ),

                "document_ids": group["document_ids"],

                "document_types": group["document_types"],

                "sha256": group["sha256"],

            })

    for field_name, config in FIELD_CONFIG.items():

        result = compare_field(

            applicant,

            documents,

            document_to_group,

            field_name,

            config,

        )

        comparison_results.append(result)

        if result["status"] == "MATCH":

            matched_fields.append(result)

        elif result["status"] == "MISMATCH":

            mismatches.append(result)

        elif result["status"] == "MANUAL_REVIEW":

            warnings.append({

                "field": field_name,

                "message": result["message"],

                "status": "MANUAL_REVIEW",

            })

        warnings.extend(result.get("warnings", []))

    for field_name, config in DOCUMENT_SPECIFIC_FIELDS.items():

        results, field_warnings = compare_document_specific_field(

            documents,

            document_to_group,

            field_name,

            config,

        )

        comparison_results.extend(results)

        warnings.extend(field_warnings)

        for result in results:

            if result["status"] == "MATCH":

                matched_fields.append(result)

            elif result["status"] == "MISMATCH":

                mismatches.append(result)

    review_statuses = {"NOT_FOUND", "PROFILE_ONLY"}

    has_review_fields = any(

        result["status"] in review_statuses

        for result in comparison_results

    )

    if mismatches:

        overall_status = "MISMATCH"

    elif warnings or has_review_fields or not matched_fields:

        overall_status = "MANUAL_REVIEW"

    else:

        overall_status = "MATCH"

    return {

        "status": overall_status,

        "comparison_results": comparison_results,

        "matched_fields": matched_fields,

        "mismatches": mismatches,

        "warnings": warnings,

        "duplicate_file_groups": duplicate_groups,

        "documents_considered": [document.id for document in documents],

        "report_saved": False,

        "message": "Read-only preview. No verification report was saved.",

    }

# ---------------------------------------------------------------------

# DATABASE SAVE FUNCTION

# ---------------------------------------------------------------------

@transaction.atomic

def verify_applicant_documents(applicant, verified_by=None):

    """

    Save a cross-document verification report.

    Call preview_applicant_documents() first when a read-only preview is wanted.

    This function saves only the report; it does not alter document statuses,

    applicant data, or eligibility evaluation history.

    """

    report_data = preview_applicant_documents(applicant)

    if isinstance(applicant, int):

        applicant = Applicant.objects.get(id=applicant)

    # The model permits only MATCH, MISMATCH and MANUAL_REVIEW.

    report_status = report_data["status"]

    if report_status not in {"MATCH", "MISMATCH", "MANUAL_REVIEW"}:

        report_status = "MANUAL_REVIEW"

    # Keep comparison_results as a list for compatibility with existing views/templates.

    report = ApplicantCrossDocumentVerification.objects.create(

        applicant=applicant,

        status=report_status,

        comparison_results=report_data["comparison_results"],

        matched_fields=report_data["matched_fields"],

        mismatches=report_data["mismatches"],

        warnings=report_data["warnings"],

        documents_considered=report_data["documents_considered"],

        verified_by=verified_by,

    )

    return report
