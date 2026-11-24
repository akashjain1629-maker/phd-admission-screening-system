
from decimal import Decimal, InvalidOperation
from django.db.models import Q
from django.utils import timezone

from .models import UniversityCGPAConversionRule


# ==========================================
# PHD ELIGIBILITY CONFIGURATION
# ==========================================

CATEGORY_PERCENTAGE_RULES = {
    "GENERAL": Decimal("60.00"),
    "SC": Decimal("55.00"),
    "ST": Decimal("55.00"),
    "OBC": Decimal("55.00"),
    "PWD": Decimal("55.00"),
}


# ==========================================
# MANDATORY DOCUMENT CONFIGURATION
# ==========================================

MANDATORY_DOCUMENTS = {
    "RESUME": "Resume",
    "10TH_MARKSHEET": "10th Marksheet",
    "12TH_MARKSHEET": "12th Marksheet",
    "UG_MARKSHEETS": "UG Marksheets",
    "DEGREE_CERTIFICATE": "Degree Certificate",
    "GATE_SCORECARD": "GATE Score Card",
}


# ==========================================
# CGPA CONVERSION HELPER
# ==========================================

def convert_cgpa_to_percentage(applicant):
    """
    Convert CGPA using the university rule that matches:
    1. University name
    2. Qualifying degree duration
    3. Degree award date within the rule's effective period

    If the required inputs or a unique rule are unavailable, return
    manual-review details instead of guessing a conversion formula.
    """

    result = {
        "success": False,
        "percentage": None,
        "method": None,
        "university": None,
        "reference": None,
        "degree_duration_years": None,
        "degree_award_date": None,
        "message": "",
    }

    cgpa = applicant.cgpa
    university_name = (applicant.university_name or "").strip()
    degree_duration = applicant.qualifying_degree_duration
    degree_award_date = applicant.degree_award_date

    if cgpa is None:
        result["message"] = "CGPA is not available."
        return result

    if not university_name:
        result["message"] = "University name is missing."
        return result

    if degree_duration is None:
        result["message"] = (
            "Qualifying degree duration is missing. "
            "Manual verification required."
        )
        return result

    if degree_award_date is None:
        result["message"] = (
            "Degree award date is missing. The applicable rule cannot "
            "be selected. Manual verification required."
        )
        return result

    try:
        cgpa = Decimal(str(cgpa))
        degree_duration = Decimal(str(degree_duration))

        if (
            not cgpa.is_finite()
            or cgpa < Decimal("0")
            or cgpa > Decimal("10")
        ):
            result["message"] = (
                "Invalid CGPA. CGPA must be between 0 and 10."
            )
            return result

        if (
            not degree_duration.is_finite()
            or degree_duration <= Decimal("0")
            or degree_duration != degree_duration.to_integral_value()
        ):
            result["message"] = (
                "Invalid qualifying degree duration. Enter a positive "
                "whole number of years."
            )
            return result

    except (InvalidOperation, ValueError, TypeError):
        result["message"] = (
            "Invalid CGPA or qualifying degree duration."
        )
        return result

    result["degree_duration_years"] = int(degree_duration)
    result["degree_award_date"] = degree_award_date.isoformat()

    # The award date, not today's date, determines which rule applies.
    rules = UniversityCGPAConversionRule.objects.filter(
        university_name__iexact=university_name,
        degree_duration_years=int(degree_duration),
        is_active=True,
        effective_from__lte=degree_award_date,
    ).filter(
        Q(effective_to__isnull=True)
        | Q(effective_to__gte=degree_award_date)
    )

    rules = list(rules)

    if not rules:
        result["message"] = (
            f"No active conversion rule matches {university_name}, "
            f"a {int(degree_duration)}-year qualifying degree, and "
            f"award date {degree_award_date}. Check the transcript and "
            "the applicable official university/PhD ordinance rule. "
            "Manual verification required."
        )
        return result

    if len(rules) > 1:
        result["message"] = (
            "Multiple conversion rules match this university, degree "
            "duration and award date. Resolve the overlapping rules "
            "before conversion. Manual verification required."
        )
        return result

    rule = rules[0]

    try:
        if rule.conversion_method == "MULTIPLY":
            multiplier = Decimal(str(rule.multiplier))
            if not multiplier.is_finite() or multiplier <= 0:
                raise InvalidOperation
            percentage = cgpa * multiplier

        elif rule.conversion_method == "MULTIPLY_OFFSET":
            multiplier = Decimal(str(rule.multiplier))
            offset = Decimal(str(rule.offset))
            if (
                not multiplier.is_finite()
                or not offset.is_finite()
                or multiplier <= 0
            ):
                raise InvalidOperation
            percentage = (cgpa * multiplier) + offset

        elif rule.conversion_method == "CUBIC":
            a = Decimal(str(rule.coefficient_a))
            b = Decimal(str(rule.coefficient_b))
            c = Decimal(str(rule.coefficient_c))
            d = Decimal(str(rule.coefficient_d))

            if not all(value.is_finite() for value in (a, b, c, d)):
                raise InvalidOperation

            percentage = (
                a * (cgpa ** 3)
                + b * (cgpa ** 2)
                + c * cgpa
                + d
            )

        else:
            result["message"] = (
                "Unknown CGPA conversion method. "
                "Manual verification required."
            )
            return result

        if (
            not percentage.is_finite()
            or percentage < Decimal("0")
            or percentage > Decimal("100")
        ):
            result["message"] = (
                "Calculated percentage is outside the valid 0-100 "
                "range. Manual review required."
            )
            return result

        percentage = percentage.quantize(Decimal("0.01"))

        result.update({
            "success": True,
            "percentage": percentage,
            "method": rule.get_conversion_method_display(),
            "university": rule.university_name,
            "reference": rule.official_reference,
            "message": (
                f"CGPA {cgpa} converted to {percentage}% using the "
                f"matched university rule for a {int(degree_duration)}-"
                f"year degree awarded on {degree_award_date}."
            ),
        })
        return result

    except (
        InvalidOperation,
        ValueError,
        TypeError,
        AttributeError,
    ):
        result["message"] = (
            "Conversion rule contains invalid or incomplete formula "
            "values. Manual verification required."
        )
        return result


# ==========================================
# MAIN ELIGIBILITY ENGINE
# ==========================================

def evaluate_phd_eligibility(applicant):

    checks = []
    failures = []
    pending_items = []
    manual_review_items = []

    required_percentage = None
    obtained_percentage = None

    conversion_details = None

    # ======================================
    # HELPER FUNCTION
    # ======================================

    def add_check(name, status, message):

        checks.append({
            "name": name,
            "status": status,
            "message": message,
        })

    # ======================================
    # 1. APPLICANT CATEGORY CHECK
    # ======================================

    category = (
        applicant.applicant_category or ""
    ).strip().upper()

    if not category:

        manual_review_items.append(
            "Applicant category is missing."
        )

        add_check(
            "Applicant Category",
            "MANUAL_REVIEW",
            "Category information is required."
        )

    elif category not in CATEGORY_PERCENTAGE_RULES:

        manual_review_items.append(
            "Applicant category is not recognised."
        )

        add_check(
            "Applicant Category",
            "MANUAL_REVIEW",
            "Invalid applicant category."
        )

    else:

        required_percentage = (
            CATEGORY_PERCENTAGE_RULES[category]
        )

        add_check(
            "Applicant Category",
            "PASS",
            f"Category: {category}. "
            f"Minimum required percentage: "
            f"{required_percentage}%."
        )

    # ======================================
    # 2. POSTGRADUATE QUALIFICATION CHECK
    # ======================================

    qualification = (
        applicant.highest_qualification or ""
    ).strip()

    if not qualification:

        pending_items.append(
            "Highest qualification details are missing."
        )

        add_check(
            "Postgraduate Qualification",
            "PENDING",
            "Qualification details are required."
        )

    else:

        add_check(
            "Postgraduate Qualification",
            "PASS",
            qualification
        )

    # ======================================
    # 3. ACADEMIC PERCENTAGE CHECK
    # ======================================

    raw_percentage = applicant.aggregate_percentage

    # --------------------------------------
    # DIRECT PERCENTAGE AVAILABLE
    # --------------------------------------

    if raw_percentage is not None:

        try:

            percentage = Decimal(str(raw_percentage))

            if (
                not percentage.is_finite()
                or percentage < Decimal("0")
                or percentage > Decimal("100")
            ):
                raise InvalidOperation

            obtained_percentage = percentage

            add_check(
                "Academic Percentage",
                "PASS",
                f"Official aggregate percentage: "
                f"{percentage}%."
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError
        ):

            manual_review_items.append(
                "Academic percentage contains an invalid value."
            )

            add_check(
                "Academic Percentage",
                "MANUAL_REVIEW",
                "Invalid percentage value."
            )

    # --------------------------------------
    # CGPA TO PERCENTAGE CONVERSION
    # --------------------------------------

    elif applicant.cgpa is not None:

        conversion_details = convert_cgpa_to_percentage(
            applicant
        )

        if conversion_details["success"]:

            obtained_percentage = (
                conversion_details["percentage"]
            )

            add_check(
                "CGPA Conversion",
                "PASS",
                (
                    f"University: "
                    f"{conversion_details['university']}. "
                    f"Method: "
                    f"{conversion_details['method']}. "
                    f"Converted percentage: "
                    f"{obtained_percentage}%. "
                    f"Reference: "
                    f"{conversion_details['reference']}"
                )
            )

        else:

            manual_review_items.append(
                conversion_details["message"]
            )

            add_check(
                "CGPA Conversion",
                "MANUAL_REVIEW",
                conversion_details["message"]
            )

    # --------------------------------------
    # NO ACADEMIC DATA
    # --------------------------------------

    else:

        pending_items.append(
            "Postgraduate aggregate percentage "
            "and CGPA are missing."
        )

        add_check(
            "Academic Percentage",
            "PENDING",
            "Percentage or CGPA information is required."
        )

    # ======================================
    # 4. MINIMUM PERCENTAGE COMPARISON
    # ======================================

    if obtained_percentage is not None:

        if required_percentage is None:

            manual_review_items.append(
                "Applicant category must be verified before "
                "applying percentage criteria."
            )

            add_check(
                "Minimum Percentage Criteria",
                "MANUAL_REVIEW",
                "Minimum percentage cannot be determined."
            )

        elif obtained_percentage < required_percentage:

            failures.append(
                f"Obtained percentage {obtained_percentage}% "
                f"is below the required "
                f"{required_percentage}%."
            )

            add_check(
                "Minimum Percentage Criteria",
                "FAIL",
                f"{obtained_percentage}% obtained; "
                f"{required_percentage}% required."
            )

        else:

            add_check(
                "Minimum Percentage Criteria",
                "PASS",
                f"{obtained_percentage}% obtained; "
                f"{required_percentage}% required."
            )

    # ======================================
    # 5. UNIVERSITY RECOGNITION CHECK
    # ======================================

    university_name = (
        applicant.university_name or ""
    ).strip()

    if not university_name:

        pending_items.append(
            "PG university name is missing."
        )

        add_check(
            "University Recognition",
            "PENDING",
            "University name is required."
        )

    elif applicant.pg_university_recognized is None:

        manual_review_items.append(
            "PG university recognition has not been verified."
        )

        add_check(
            "University Recognition",
            "MANUAL_REVIEW",
            "University recognition needs verification."
        )

    elif applicant.pg_university_recognized is False:

        failures.append(
            "PG university is marked as not recognised."
        )

        add_check(
            "University Recognition",
            "FAIL",
            "University is not recognised."
        )

    else:

        add_check(
            "University Recognition",
            "PASS",
            "PG university is recognised."
        )

    # ======================================
    # 6. ENTRANCE EXAMINATION CHECK
    # ======================================

    exam_name = (
        applicant.entrance_exam_name or ""
    ).strip()

    exam_status = applicant.entrance_exam_status

    if not exam_name:

        pending_items.append(
            "Entrance examination name is missing."
        )

        add_check(
            "Entrance Examination",
            "PENDING",
            "Entrance examination details are required."
        )

    elif exam_status == "QUALIFIED":

        add_check(
            "Entrance Examination",
            "PASS",
            f"{exam_name}: Qualified."
        )

    elif exam_status == "NOT_QUALIFIED":

        failures.append(
            f"Applicant has not qualified the "
            f"{exam_name} examination."
        )

        add_check(
            "Entrance Examination",
            "FAIL",
            f"{exam_name}: Not Qualified."
        )

    elif exam_status == "PENDING":

        pending_items.append(
            "Entrance examination result is pending."
        )

        add_check(
            "Entrance Examination",
            "PENDING",
            f"{exam_name}: Result pending."
        )

    else:

        pending_items.append(
            "Entrance examination has not been assessed."
        )

        add_check(
            "Entrance Examination",
            "PENDING",
            f"{exam_name}: Not assessed."
        )

    # ======================================
    # 7. DOCUMENT COMPLETENESS CHECK
    # ======================================

    uploaded_documents = applicant.documents.all().order_by(
        "-uploaded_at",
        "-pk"
    )

    latest_documents = {}

    # Only latest uploaded document is considered.

    for document in uploaded_documents:

        if document.document_type not in latest_documents:

            latest_documents[document.document_type] = document

    for document_type, document_name in MANDATORY_DOCUMENTS.items():

        document = latest_documents.get(document_type)

        # ----------------------------------
        # DOCUMENT NOT UPLOADED
        # ----------------------------------

        if document is None:

            pending_items.append(
                f"{document_name} has not been uploaded."
            )

            add_check(
                document_name,
                "PENDING",
                "Mandatory document is missing."
            )

        # ----------------------------------
        # DOCUMENT VERIFIED
        # ----------------------------------

        elif document.verification_status == "VERIFIED":

            add_check(
                document_name,
                "PASS",
                "Document uploaded and verified successfully."
            )

        # ----------------------------------
        # DOCUMENT REJECTED
        # ----------------------------------

        elif document.verification_status == "REJECTED":

            pending_items.append(
                f"{document_name} has been rejected. "
                "Resubmission is required."
            )

            add_check(
                document_name,
                "PENDING",
                document.remarks or
                "Document rejected. Please upload a valid document."
            )

        # ----------------------------------
        # RESUBMISSION REQUIRED
        # ----------------------------------

        elif document.verification_status == "RESUBMISSION_REQUIRED":

            pending_items.append(
                f"{document_name} requires resubmission."
            )

            add_check(
                document_name,
                "PENDING",
                document.remarks or
                "Please upload the document again."
            )

        # ----------------------------------
        # VERIFICATION PENDING
        # ----------------------------------

        elif document.verification_status == "PENDING":

            pending_items.append(
                f"{document_name} verification is pending."
            )

            add_check(
                document_name,
                "PENDING",
                "Document is awaiting verification."
            )

        # ----------------------------------
        # UNKNOWN STATUS
        # ----------------------------------

        else:

            manual_review_items.append(
                f"{document_name} has an unknown "
                "verification status."
            )

            add_check(
                document_name,
                "MANUAL_REVIEW",
                "Document status requires manual review."
            )

    # ======================================
    # 8. FINAL ELIGIBILITY DECISION
    # ======================================

    # Priority:
    # 1. Manual Review
    # 2. Pending Information/Documents
    # 3. Academic Failure
    # 4. Eligible

    if manual_review_items:

        final_status = "MANUAL_REVIEW"

        reasons = (
            manual_review_items
            + pending_items
            + failures
        )

    elif pending_items:

        final_status = "PENDING"

        reasons = pending_items + failures

    elif failures:

        final_status = "NOT_ELIGIBLE"

        reasons = failures

    else:

        final_status = "ELIGIBLE"

        reasons = [
            "All academic eligibility checks and mandatory "
            "document verification checks have been satisfied."
        ]

    # ======================================
    # 9. RETURN FINAL RESULT
    # ======================================

    return {

        "status": final_status,

        "required_percentage": (
            float(required_percentage)
            if required_percentage is not None
            else None
        ),

        "obtained_percentage": (
            float(obtained_percentage)
            if obtained_percentage is not None
            else None
        ),

        "checks": checks,

        "reasons": reasons,

        "conversion_details": conversion_details,

        "is_eligible": final_status == "ELIGIBLE",

    }
