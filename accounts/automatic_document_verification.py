
import re
from django.utils import timezone


def normalize_name(value):
    """Normalize names for comparison."""
    return re.sub(r"[^a-z]", "", str(value or "").lower())


def normalize_digits(value):
    """Keep digits only."""
    return re.sub(r"\D", "", str(value or ""))


def add_remark(document, message):
    """Append a remark without duplication."""
    existing = document.remarks or ""

    if message not in existing:
        document.remarks = f"{existing}\n{message}".strip()


def save_pending(document, message):
    """Keep documents pending when OCR is incomplete."""
    document.verification_status = "PENDING"

    add_remark(document, message)

    document.save(
        update_fields=[
            "verification_status",
            "remarks",
            "updated_at",
        ]
    )

    return {
        "success": False,
        "status": "PENDING",
        "message": message,
    }


def save_manual_review(document, message):
    """Mark uncertain documents for administrator review."""
    document.verification_status = "MANUAL_REVIEW"
    document.verified_at = None
    document.verified_by = None

    add_remark(document, message)

    document.save(
        update_fields=[
            "verification_status",
            "verified_at",
            "verified_by",
            "remarks",
            "updated_at",
        ]
    )

    return {
        "success": False,
        "status": "MANUAL_REVIEW",
        "message": message,
    }


def get_document_requirements(document_type):
    """Return document-specific OCR requirements."""

    requirements = {
        "RESUME": [
            "candidate_name",
            "education",
        ],

        "10TH_MARKSHEET": [
            "candidate_name",
            "aggregate_percentage",
        ],

        "12TH_MARKSHEET": [
            "candidate_name",
            "aggregate_percentage",
        ],

        "UG_MARKSHEETS": [
            "candidate_name",
            "university",
        ],

        "DEGREE_CERTIFICATE": [
            "candidate_name",
            "university",
            "programme",
        ],

        "GATE_SCORECARD": [
            "candidate_name",
            "gate_score",
            "roll_number",
        ],
    }

    return requirements.get(document_type)


def verify_document_automatically(document):
    """
    Perform conservative internal document checks.

    This does not establish official authenticity.
    """

    # 1. OCR completion check
    if document.ocr_status != "COMPLETED":
        return save_pending(
            document,
            "Automatic verification pending: OCR is not completed."
        )

    extracted_data = document.extracted_data or {}

    # 2. Document type validation
    validation = extracted_data.get("document_validation") or {}

    validation_status = validation.get("validation_status")

    if validation_status == "RESUBMISSION_REQUIRED":

        document.verification_status = "RESUBMISSION_REQUIRED"
        document.verified_at = None
        document.verified_by = None

        add_remark(
            document,
            "Automatic verification: uploaded document type "
            "does not match the selected document category."
        )

        document.save(
            update_fields=[
                "verification_status",
                "verified_at",
                "verified_by",
                "remarks",
                "updated_at",
            ]
        )

        return {
            "success": False,
            "status": "RESUBMISSION_REQUIRED",
            "message": "Document type mismatch.",
        }

    if validation_status != "TYPE_MATCHED":
        return save_manual_review(
            document,
            "Manual review required: document type could not "
            "be confirmed confidently."
        )

    # 3. Document-specific requirements
    required_fields = get_document_requirements(
        document.document_type
    )

    if not required_fields:
        return save_manual_review(
            document,
            "Manual review required: no automatic verification "
            "rules are configured for this document category."
        )

    missing_fields = []

    for field in required_fields:
        value = extracted_data.get(field)

        if value is None or str(value).strip() == "":
            missing_fields.append(field)

    if missing_fields:
        return save_manual_review(
            document,
            "Manual review required: OCR could not extract "
            "the following required fields: "
            + ", ".join(missing_fields)
        )

    # 4. Candidate name comparison
    applicant = document.applicant

    extracted_name = extracted_data.get("candidate_name")
    applicant_name = getattr(applicant, "full_name", "")

    normalized_extracted = normalize_name(extracted_name)
    normalized_applicant = normalize_name(applicant_name)

    if not normalized_extracted or not normalized_applicant:
        return save_manual_review(
            document,
            "Manual review required: candidate name is missing."
        )

    if normalized_extracted != normalized_applicant:
        return save_manual_review(
            document,
            "Manual review required: candidate name does not "
            "match the applicant profile."
        )

    # 5. Email comparison, when available
    extracted_email = extracted_data.get("email")
    applicant_email = getattr(applicant, "email", "")

    if extracted_email and applicant_email:

        if (
            extracted_email.strip().lower()
            != applicant_email.strip().lower()
        ):
            return save_manual_review(
                document,
                "Manual review required: email does not match "
                "the applicant profile."
            )

    # 6. Mobile comparison, when available
    extracted_mobile = extracted_data.get("mobile")
    applicant_mobile = getattr(applicant, "mobile_number", "")

    if extracted_mobile and applicant_mobile:

        extracted_digits = normalize_digits(extracted_mobile)
        applicant_digits = normalize_digits(applicant_mobile)

        if (
            len(extracted_digits) < 10
            or len(applicant_digits) < 10
            or extracted_digits[-10:] != applicant_digits[-10:]
        ):
            return save_manual_review(
                document,
                "Manual review required: mobile number does not "
                "match the applicant profile."
            )

    # 7. Internal checks passed
    document.verification_status = "VERIFIED"
    document.verified_at = timezone.now()
    document.verified_by = None

    add_remark(
        document,
        "Automatic internal document checks passed. "
        "Required OCR fields and candidate name matched. "
        "Official document authenticity has NOT been established."
    )

    document.save(
        update_fields=[
            "verification_status",
            "verified_at",
            "verified_by",
            "remarks",
            "updated_at",
        ]
    )

    return {
        "success": True,
        "status": "VERIFIED",
        "message": "Internal document checks passed.",
    }
