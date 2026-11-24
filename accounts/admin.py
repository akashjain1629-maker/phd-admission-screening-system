
from django.contrib import admin

from .models import (
    Applicant,
    ApplicantDocument,
    UniversityCGPAConversionRule,
    ApplicantCrossDocumentVerification,
)


# ==========================================
# APPLICANT ADMIN
# ==========================================

@admin.register(Applicant)
class ApplicantAdmin(admin.ModelAdmin):

    list_display = (
        "application_id",
        "full_name",
        "email",
        "department",
        "programme",
        "application_status",
        "application_date",
    )

    list_filter = (
        "application_status",
        "department",
        "programme",
    )

    search_fields = (
        "application_id",
        "full_name",
        "email",
        "mobile_number",
    )

    readonly_fields = (
        "application_id",
        "application_date",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)


# ==========================================
# APPLICANT DOCUMENT ADMIN
# ==========================================

@admin.register(ApplicantDocument)
class ApplicantDocumentAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "applicant",
        "document_type",
        "is_mandatory",
        "verification_status",
        "ocr_status",
        "uploaded_at",
        "ocr_processed_at",
    )

    list_filter = (
        "document_type",
        "verification_status",
        "ocr_status",
        "is_mandatory",
        "uploaded_at",
    )

    search_fields = (
        "applicant__application_id",
        "applicant__full_name",
        "applicant__email",
        "remarks",
        "extracted_text",
    )

    readonly_fields = (
        "uploaded_at",
        "updated_at",
        "extracted_text",
        "extracted_data",
        "ocr_status",
        "ocr_processed_at",
    )

    ordering = ("-uploaded_at",)

    fieldsets = (

        ("Applicant Information", {
            "fields": ("applicant",)
        }),

        ("Document Information", {
            "fields": (
                "document_type",
                "document_file",
                "is_mandatory",
            )
        }),

        ("Verification Information", {
            "fields": (
                "verification_status",
                "remarks",
                "verified_by",
                "verified_at",
            )
        }),

        ("OCR Information", {
            "fields": (
                "ocr_status",
                "ocr_processed_at",
                "extracted_text",
                "extracted_data",
            )
        }),

        ("System Information", {
            "fields": (
                "uploaded_at",
                "updated_at",
            )
        }),
    )


# ==========================================
# UNIVERSITY CGPA CONVERSION RULE ADMIN
# ==========================================

@admin.register(UniversityCGPAConversionRule)
class UniversityCGPAConversionRuleAdmin(admin.ModelAdmin):

    list_display = (
        "university_name",
        "degree_duration_years",
        "conversion_method",
        "effective_from",
        "effective_to",
        "is_active",
    )

    list_filter = (
        "university_name",
        "degree_duration_years",
        "conversion_method",
        "is_active",
    )

    search_fields = (
        "university_name",
        "official_reference",
    )

    list_editable = ("is_active",)

    ordering = (
        "university_name",
        "effective_from",
    )

    fieldsets = (

        ("University Information", {
            "fields": (
                "university_name",
                "degree_duration_years",
            )
        }),

        ("Rule Validity", {
            "fields": (
                "effective_from",
                "effective_to",
                "is_active",
            )
        }),

        ("Conversion Method", {
            "fields": (
                "conversion_method",
                "multiplier",
                "offset",
            )
        }),

        ("Cubic Formula Coefficients", {
            "fields": (
                "coefficient_a",
                "coefficient_b",
                "coefficient_c",
                "coefficient_d",
            )
        }),

        ("Official Reference", {
            "fields": ("official_reference",)
        }),

        ("System Information", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


# ==========================================
# CROSS-DOCUMENT VERIFICATION ADMIN
# ==========================================

@admin.register(ApplicantCrossDocumentVerification)
class ApplicantCrossDocumentVerificationAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "applicant",
        "get_status_display",
        "created_at",
    )

    search_fields = (
        "applicant__application_id",
        "applicant__full_name",
        "applicant__email",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = ("-created_at",)
