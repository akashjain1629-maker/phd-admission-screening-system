import re
import unicodedata

from decimal import Decimal, InvalidOperation

from django.utils import timezone

from accounts.models import (
    Applicant,
    ApplicantDocument,
    ApplicantCrossDocumentVerification,
)


# ==========================================
# FIELD CONFIGURATION
# ==========================================

FIELD_CONFIG = {
    "candidate_name": {
        "label": "Candidate Name",
        "document_types": None,
        "applicant_field": "full_name",
    },

    "father_name": {
        "label": "Father's Name",
        "document_types": None,
        "applicant_field": None,
    },

    "mother_name": {
        "label": "Mother's Name",
        "document_types": None,
        "applicant_field": None,
    },

    "date_of_birth": {
        "label": "Date of Birth",
        "document_types": None,
        "applicant_field": "date_of_birth",
    },

    "application_id": {
        "label": "Application ID",
        "document_types": None,
        "applicant_field": "application_id",
    },

    "university": {
        "label": "University",
        "document_types": [
            "UG_MARKSHEETS",
            "DEGREE_CERTIFICATE",
        ],
        "applicant_field": "university_name",
    },

    "programme": {
        "label": "Programme",
        "document_types": [
            "UG_MARKSHEETS",
            "DEGREE_CERTIFICATE",
        ],
        "applicant_field": "programme",
    },

    "cgpa": {
        "label": "CGPA",
        "document_types": [
            "UG_MARKSHEETS",
            "DEGREE_CERTIFICATE",
        ],
        "applicant_field": "cgpa",
        "numeric": True,
    },

    "aggregate_percentage": {
        "label": "Aggregate Percentage",
        "document_types": [
            "UG_MARKSHEETS",
            "DEGREE_CERTIFICATE",
        ],
        "applicant_field": "aggregate_percentage",
        "numeric": True,
    },

    "email": {
        "label": "Email",
        "document_types": None,
        "applicant_field": "email",
    },

    "mobile_number": {
        "label": "Mobile Number",
        "document_types": None,
        "applicant_field": "mobile_number",
    },

    "gate_score": {
        "label": "GATE Score",
        "document_types": [
            "GATE_SCORECARD",
        ],
        "applicant_field": None,
        "numeric": True,
    },
}


# ==========================================
# DOCUMENT-SPECIFIC FIELD CONFIGURATION
# ==========================================

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


# ==========================================
# TEXT NORMALIZATION
# ==========================================

def normalize_text(value):
    """
    Normalize English and Hindi text for comparison.
    Preserve Unicode letters and numbers.
    """

    if value is None:
        return None

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = value.strip().casefold()

    if value in (
        "",
        "none",
        "null",
        "n/a",
        "na",
        "not provided",
    ):
        return None

    # Preserve Unicode letters and numbers.
    value = "".join(
        character
        for character in value
        if character.isalnum()
    )

    return value or None


# ==========================================
# NUMERIC NORMALIZATION
# ==========================================

def normalize_numeric(value):
    """
    Extract the first numeric value for comparison.
    Example: '8.25 / 10.00' becomes Decimal('8.25').
    """

    if value is None:
        return None

    match = re.search(
        r"\d+(?:\.\d+)?",
        str(value),
    )

    if not match:
        return None

    try:
        return Decimal(match.group())
    except InvalidOperation:
        return None


def normalize_value(value, numeric=False):
    if numeric:
        return normalize_numeric(value)

    return normalize_text(value)


# ==========================================
# DATE NORMALIZATION
# ==========================================

def normalize_date(value):
    """
    Normalize common date formats.
    """

    if value is None:
        return None

    value = str(value).strip()

    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d %B %Y",
        "%d %b %Y",
    ]

    from datetime import datetime

    for date_format in formats:
        try:
            parsed = datetime.strptime(
                value,
                date_format,
            )
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return normalize_text(value)
# ==========================================
# FIELD VALUE EXTRACTION
# ==========================================

def normalize_field_value(value, field_name, config):
    """
    Apply the correct normalization according to field type.
    """

    if field_name == "date_of_birth":
        return normalize_date(value)

    return normalize_value(
        value,
        numeric=config.get("numeric", False),
    )


def get_document_field_values(
    documents,
    field_name,
    allowed_document_types=None,
):
    """
    Extract a field's value from eligible OCR-completed documents.
    """

    results = []

    for document in documents:

        if allowed_document_types:
            if document.document_type not in allowed_document_types:
                continue

        extracted_data = document.extracted_data or {}

        raw_value = extracted_data.get(field_name)

        normalized_value = normalize_field_value(
            raw_value,
            field_name,
            FIELD_CONFIG.get(field_name, {}),
        )

        if normalized_value is None:
            continue

        results.append({
            "document_id": document.id,
            "document_type": document.document_type,
            "document_name": document.get_document_type_display(),
            "raw_value": str(raw_value),
            "normalized_value": str(normalized_value),
        })

    return results


# ==========================================
# APPLICANT PROFILE VALUE
# ==========================================

def get_applicant_profile_value(applicant, field_name, config):
    """
    Read the corresponding value from the applicant profile.
    """

    applicant_field = config.get("applicant_field")

    if not applicant_field:
        return None

    raw_value = getattr(
        applicant,
        applicant_field,
        None,
    )

    if raw_value is None:
        return None

    normalized_value = normalize_field_value(
        raw_value,
        field_name,
        config,
    )

    if normalized_value is None:
        return None

    return {
        "source": "Applicant Profile",
        "raw_value": str(raw_value),
        "normalized_value": str(normalized_value),
    }


# ==========================================
# FIELD COMPARISON
# ==========================================

def compare_field(
    applicant,
    documents,
    field_name,
    config,
):
    """
    Compare one field across available documents
    and the applicant profile.
    """

    document_values = get_document_field_values(
        documents,
        field_name,
        config.get("document_types"),
    )

    profile_value = get_applicant_profile_value(
        applicant,
        field_name,
        config,
    )

    comparison_values = []

    if profile_value:
        comparison_values.append(profile_value)

    for item in document_values:
        comparison_values.append({
            "source": item["document_name"],
            "document_id": item["document_id"],
            "raw_value": item["raw_value"],
            "normalized_value": item["normalized_value"],
        })

    if not comparison_values:
        return {
            "field": field_name,
            "label": config["label"],
            "status": "NOT_FOUND",
            "values": [],
            "message": "No value found for comparison.",
        }

    unique_values = {
        item["normalized_value"]
        for item in comparison_values
    }

    if len(unique_values) == 1:
        status = "MATCH"
        message = "All available values match."
    else:
        status = "MISMATCH"
        message = "Different values found across available sources."

    return {
        "field": field_name,
        "label": config["label"],
        "status": status,
        "values": comparison_values,
        "message": message,
    }


# ==========================================
# DOCUMENT-SPECIFIC COMPARISON
# ==========================================

def compare_document_specific_field(
    documents,
    field_name,
    config,
):
    """
    Compare document-specific fields only within the same
    document category.

    Example:
    10th roll number is not compared with 12th roll number.
    """

    grouped_values = {}

    for document in documents:

        if document.document_type not in config["document_types"]:
            continue

        extracted_data = document.extracted_data or {}

        raw_value = extracted_data.get(field_name)

        normalized_value = normalize_text(raw_value)

        if normalized_value is None:
            continue

        grouped_values.setdefault(
            document.document_type,
            [],
        )

        grouped_values[document.document_type].append({
            "document_id": document.id,
            "document_type": document.document_type,
            "document_name": document.get_document_type_display(),
            "raw_value": str(raw_value),
            "normalized_value": normalized_value,
        })

    results = []

    for document_type, values in grouped_values.items():

        unique_values = {
            item["normalized_value"]
            for item in values
        }

        if len(unique_values) == 1:
            status = "MATCH"
            message = "Values match within this document category."

        else:
            status = "MISMATCH"
            message = "Different values found within this document category."

        results.append({
            "field": field_name,
            "label": config["label"],
            "document_type": document_type,
            "status": status,
            "values": values,
            "message": message,
        })

    return results
# ==========================================
# MAIN CROSS-DOCUMENT VERIFICATION ENGINE
# ==========================================

def verify_applicant_documents(
    applicant,
    verified_by=None,
):
    """
    Verify applicant information across OCR-processed documents
    and the applicant profile.

    This function does not change document verification statuses.
    It creates/updates a cross-document verification report.
    """

    if isinstance(applicant, int):
        applicant = Applicant.objects.get(id=applicant)

    documents = ApplicantDocument.objects.filter(
        applicant=applicant,
        ocr_status="COMPLETED",
    ).exclude(
        extracted_data={},
    ).order_by("uploaded_at")

    comparison_results = []
    matched_fields = []
    mismatches = []
    warnings = []

    # --------------------------------------
    # 1. COMMON FIELD COMPARISONS
    # --------------------------------------

    for field_name, config in FIELD_CONFIG.items():

        result = compare_field(
            applicant,
            documents,
            field_name,
            config,
        )

        comparison_results.append(result)

        if result["status"] == "MATCH":
            matched_fields.append(result)

        elif result["status"] == "MISMATCH":
            mismatches.append(result)

        else:
            warnings.append({
                "field": field_name,
                "label": config["label"],
                "message": result["message"],
            })

    # --------------------------------------
    # 2. DOCUMENT-SPECIFIC FIELD COMPARISONS
    # --------------------------------------

    for field_name, config in DOCUMENT_SPECIFIC_FIELDS.items():

        results = compare_document_specific_field(
            documents,
            field_name,
            config,
        )

        if not results:
            warnings.append({
                "field": field_name,
                "label": config["label"],
                "message": "No document-specific value found.",
            })

        for result in results:

            comparison_results.append(result)

            if result["status"] == "MATCH":
                matched_fields.append(result)

            elif result["status"] == "MISMATCH":
                mismatches.append(result)

    # --------------------------------------
    # 3. OVERALL VERIFICATION STATUS
    # --------------------------------------

    if mismatches:
        overall_status = "MISMATCH"

    elif matched_fields and not warnings:
        overall_status = "MATCH"

    else:
        overall_status = "MANUAL_REVIEW"

    # --------------------------------------
    # 4. PREPARE REPORT DATA
    # --------------------------------------

    report_data = {
        "status": overall_status,
        "comparison_results": comparison_results,
        "matched_fields": matched_fields,
        "mismatches": mismatches,
        "warnings": warnings,
        "documents_considered": list(
            documents.values_list("id", flat=True)
        ),
        "verified_by": verified_by,
    }

    # --------------------------------------
    # 5. SAVE CROSS-DOCUMENT REPORT
    # --------------------------------------

    report = ApplicantCrossDocumentVerification.objects.create(
        applicant=applicant,
        status=report_data["status"],
        comparison_results=report_data["comparison_results"],
        matched_fields=report_data["matched_fields"],
        mismatches=report_data["mismatches"],
        warnings=report_data["warnings"],
        documents_considered=report_data["documents_considered"],
        verified_by=verified_by,
    )

    return report