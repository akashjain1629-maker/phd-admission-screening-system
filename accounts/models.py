
from django.db import models
from django.conf import settings
import uuid


# ==========================================
# APPLICANT MODEL
# ==========================================

class Applicant(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("UNDER_REVIEW", "Under Review"),
        ("DOCUMENTS_PENDING", "Documents Pending"),
        ("ELIGIBLE", "Eligible"),
        ("NOT_ELIGIBLE", "Not Eligible"),
        ("SELECTED", "Selected"),
        ("REJECTED", "Rejected"),
    ]

    EMPLOYMENT_CATEGORY_CHOICES = [
        ("INDUSTRY", "Industry"),
        ("GOVERNMENT", "Government"),
        ("AUTONOMOUS_BODY", "Autonomous Body"),
        ("PUBLIC_SECTOR", "Public Sector Undertaking"),
        ("OTHER", "Other"),
    ]

    APPLICANT_CATEGORY_CHOICES = [
        ("GENERAL", "General"),
        ("SC", "SC"),
        ("ST", "ST"),
        ("OBC", "OBC"),
        ("PWD", "PwD"),
    ]

    ENTRANCE_STATUS_CHOICES = [
        ("NOT_ASSESSED", "Not Assessed"),
        ("PENDING", "Pending"),
        ("QUALIFIED", "Qualified"),
        ("NOT_QUALIFIED", "Not Qualified"),
    ]

    application_id = models.CharField(
        max_length=25,
        unique=True,
        editable=False
    )

    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    mobile_number = models.CharField(max_length=20)

    date_of_birth = models.DateField(
        null=True,
        blank=True
    )

    degree_award_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date on which the qualifying degree was awarded"
    )

    department = models.CharField(max_length=150)
    programme = models.CharField(max_length=150)
    research_area = models.TextField(blank=True)

    highest_qualification = models.CharField(
        max_length=150,
        blank=True
    )

    university_name = models.CharField(
        max_length=200,
        blank=True
    )

    applicant_category = models.CharField(
        max_length=20,
        choices=APPLICANT_CATEGORY_CHOICES,
        blank=True
    )

    degree_name = models.CharField(
        max_length=150,
        blank=True
    )

    specialization = models.CharField(
        max_length=150,
        blank=True
    )

    aggregate_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    cgpa = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    qualifying_degree_duration = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Duration of qualifying degree in years"
    )

    pg_university_recognized = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text="Whether the PG university is recognised"
    )

    entrance_exam_name = models.CharField(
        max_length=150,
        blank=True
    )

    entrance_exam_status = models.CharField(
        max_length=30,
        choices=ENTRANCE_STATUS_CHOICES,
        default="NOT_ASSESSED"
    )

    work_experience_years = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    employment_category = models.CharField(
        max_length=100,
        choices=EMPLOYMENT_CATEGORY_CHOICES,
        blank=True
    )

    applied_phd_discipline = models.CharField(
        max_length=150,
        blank=True
    )

    application_status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="DRAFT",
        db_index=True
    )

    application_date = models.DateField(
        auto_now_add=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def save(self, *args, **kwargs):

        if not self.application_id:
            self.application_id = (
                "PHDA-" + uuid.uuid4().hex[:10].upper()
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.application_id} - {self.full_name}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Applicant"
        verbose_name_plural = "Applicants"


# ==========================================
# APPLICANT DOCUMENT MODEL
# ==========================================

class ApplicantDocument(models.Model):

    DOCUMENT_TYPE_CHOICES = [
        ("RESUME", "Resume"),
        ("10TH_MARKSHEET", "10th Marksheet"),
        ("12TH_MARKSHEET", "12th Marksheet"),
        ("UG_MARKSHEETS", "UG Marksheets"),
        ("DEGREE_CERTIFICATE", "Degree Certificate"),
        ("GATE_SCORECARD", "GATE Score Card"),
        ("AADHAAR", "Aadhaar Card"),
        ("PAN", "PAN Card"),
        ("VOTER_ID", "Voter ID"),
        ("RESEARCH_CERTIFICATE", "Research Certificate"),
        ("EXPERIENCE_CERTIFICATE", "Experience Certificate"),
        ("OTHER", "Other Document"),
    ]

    VERIFICATION_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("MANUAL_REVIEW", "Manual Review"),
        ("VERIFIED", "Verified"),
        ("REJECTED", "Rejected"),
        ("RESUBMISSION_REQUIRED", "Resubmission Required"),
    ]

    OCR_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PROCESSING", "Processing"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    applicant = models.ForeignKey(
        Applicant,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    document_type = models.CharField(
        max_length=40,
        choices=DOCUMENT_TYPE_CHOICES
    )

    document_file = models.FileField(
        upload_to="applicant_documents/%Y/%m/"
    )

    is_mandatory = models.BooleanField(
        default=False
    )

    verification_status = models.CharField(
        max_length=30,
        choices=VERIFICATION_STATUS_CHOICES,
        default="PENDING",
        db_index=True
    )

    remarks = models.TextField(blank=True)

    # OCR EXTRACTION FIELDS

    extracted_text = models.TextField(
        blank=True,
        help_text="Complete text extracted from the uploaded document"
    )

    extracted_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured information extracted through OCR"
    )

    ocr_status = models.CharField(
        max_length=20,
        choices=OCR_STATUS_CHOICES,
        default="PENDING",
        db_index=True
    )

    ocr_processed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_applicant_documents"
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"{self.applicant.application_id} - "
            f"{self.get_document_type_display()}"
        )

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Applicant Document"
        verbose_name_plural = "Applicant Documents"


# ==========================================
# PHD ELIGIBILITY EVALUATION HISTORY MODEL
# ==========================================

class EligibilityEvaluation(models.Model):

    STATUS_CHOICES = [
        ("ELIGIBLE", "Eligible"),
        ("NOT_ELIGIBLE", "Not Eligible"),
        ("PENDING", "Pending"),
        ("MANUAL_REVIEW", "Manual Review"),
    ]

    applicant = models.ForeignKey(
        Applicant,
        on_delete=models.CASCADE,
        related_name="eligibility_evaluations"
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        db_index=True
    )

    required_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    obtained_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    checks = models.JSONField(
        default=list,
        blank=True
    )

    reasons = models.JSONField(
        default=list,
        blank=True
    )

    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eligibility_evaluations"
    )

    evaluated_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    def __str__(self):
        return (
            f"{self.applicant.application_id} - "
            f"{self.get_status_display()}"
        )

    class Meta:
        ordering = ["-evaluated_at"]
        verbose_name = "Eligibility Evaluation"
        verbose_name_plural = "Eligibility Evaluations"


# ==========================================
# UNIVERSITY CGPA CONVERSION RULE MODEL
# ==========================================

class UniversityCGPAConversionRule(models.Model):

    CONVERSION_METHOD_CHOICES = [
        ("MULTIPLY", "CGPA × Factor"),
        ("MULTIPLY_OFFSET", "CGPA × Factor + Offset"),
        ("CUBIC", "Cubic Formula"),
    ]

    university_name = models.CharField(
        max_length=200,
        db_index=True
    )

    degree_duration_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True
    )

    effective_from = models.DateField(
        null=True,
        blank=True,
        help_text="Degree award date from which this rule applies"
    )

    effective_to = models.DateField(
        null=True,
        blank=True,
        help_text="Last applicable degree award date"
    )

    conversion_method = models.CharField(
        max_length=30,
        choices=CONVERSION_METHOD_CHOICES
    )

    multiplier = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        null=True,
        blank=True
    )

    offset = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        default=0
    )

    coefficient_a = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True
    )

    coefficient_b = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True
    )

    coefficient_c = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True
    )

    coefficient_d = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True
    )

    official_reference = models.TextField(
        help_text="Official university document or notification reference"
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"{self.university_name} - "
            f"{self.get_conversion_method_display()}"
        )

    class Meta:
        ordering = ["university_name", "effective_from"]
        verbose_name = "University CGPA Conversion Rule"
        verbose_name_plural = "University CGPA Conversion Rules"


# ==========================================
# CROSS-DOCUMENT VERIFICATION REPORT MODEL
# ==========================================

class ApplicantCrossDocumentVerification(models.Model):

    STATUS_CHOICES = [
        ("MATCH", "All Details Matched"),
        ("MISMATCH", "Mismatch Found"),
        ("MANUAL_REVIEW", "Manual Review Required"),
    ]

    applicant = models.ForeignKey(
        Applicant,
        on_delete=models.CASCADE,
        related_name="cross_document_verifications"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="MANUAL_REVIEW",
        db_index=True
    )

    comparison_results = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete field-wise comparison results"
    )

    matched_fields = models.JSONField(
        default=list,
        blank=True
    )

    mismatches = models.JSONField(
        default=list,
        blank=True
    )

    warnings = models.JSONField(
        default=list,
        blank=True
    )

    documents_considered = models.JSONField(
        default=list,
        blank=True
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cross_document_verifications"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    def __str__(self):
        return (
            f"{self.applicant.application_id} - "
            f"{self.get_status_display()}"
        )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Cross-Document Verification"
        verbose_name_plural = "Cross-Document Verifications"
