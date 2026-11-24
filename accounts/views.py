from .automatic_document_verification import verify_document_automatically
from .ocr_processor import process_applicant_document
from .eligibility import evaluate_phd_eligibility
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django import forms
from django.db.models import Q
from django.utils import timezone

from .cross_document_verification import (
    preview_applicant_documents,
    verify_applicant_documents,
)

from .models import (
    Applicant,
    ApplicantDocument,
    EligibilityEvaluation,
    ApplicantCrossDocumentVerification,
)

# ==========================================
# MANDATORY DOCUMENTS FOR PHD ADMISSION
# ==========================================

REQUIRED_DOCUMENTS = [
    ("RESUME", "Resume"),
    ("10TH_MARKSHEET", "10th Marksheet"),
    ("12TH_MARKSHEET", "12th Marksheet"),
    ("UG_MARKSHEETS", "UG Marksheets"),
    ("DEGREE_CERTIFICATE", "Degree Certificate"),
    ("GATE_SCORECARD", "GATE Score Card"),
]


# ==========================================
# APPLICANT FORM
# ==========================================

class ApplicantForm(forms.ModelForm):

    class Meta:
        model = Applicant

        fields = [
            "full_name",
            "email",
            "mobile_number",
            "date_of_birth",
            "department",
            "programme",
            "research_area",
            "highest_qualification",
            "university_name",

            # Applicant Category
            "applicant_category",

            # Academic details
            "degree_name",
            "specialization",
            "aggregate_percentage",
            "cgpa",
            "qualifying_degree_duration",
            "degree_award_date",

            # PG University Recognition
            "pg_university_recognized",

            # Entrance Examination
            "entrance_exam_name",
            "entrance_exam_status",

            # Work experience
            "work_experience_years",
            "employment_category",

            # PhD discipline
            "applied_phd_discipline",

            "application_status",
        ]

        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"type": "date"}
            ),

            "qualifying_degree_duration": forms.NumberInput(
                attrs={ "class": "form-control",
                        "placeholder": "Enter degree duration in years",
                        "min": "1",
                        "step": "1" }
            ),

           "degree_award_date": forms.DateInput(
                attrs={"type": "date"}
            ),

            "research_area": forms.Textarea(
                attrs={"rows": 3}
            ),

            "aggregate_percentage": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "max": "100",
                }
            ),

            "cgpa": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "work_experience_years": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
        }

    def clean_aggregate_percentage(self):
        value = self.cleaned_data.get("aggregate_percentage")

        if value is not None and not (0 <= value <= 100):
            raise forms.ValidationError(
                "Percentage must be between 0 and 100."
            )

        return value

    def clean_cgpa(self):
        value = self.cleaned_data.get("cgpa")

        if value is not None and value < 0:
            raise forms.ValidationError(
                "CGPA cannot be negative."
            )

        return value

    def clean_work_experience_years(self):
        value = self.cleaned_data.get("work_experience_years")

        if value is not None and value < 0:
            raise forms.ValidationError(
                "Work experience cannot be negative."
            )

        return value


# ==========================================
# ADMIN ACCESS CHECK
# ==========================================

def check_admin_access(request):

    if not request.user.is_staff:
        messages.error(
            request,
            "You are not authorized to access this page."
        )
        logout(request)
        return False

    return True


# ==========================================
# LOGIN
# ==========================================

def login_view(request):

    if request.user.is_authenticated:

        if request.user.is_staff:
            return redirect("dashboard")

        logout(request)

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        remember_me = request.POST.get("remember_me")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        # Allow login using email
        if user is None and "@" in username:

            from django.contrib.auth.models import User

            try:
                existing_user = User.objects.get(
                    email__iexact=username
                )

                user = authenticate(
                    request,
                    username=existing_user.username,
                    password=password
                )

            except User.DoesNotExist:
                user = None

        if user is not None:

            if user.is_staff:

                login(request, user)

                if not remember_me:
                    request.session.set_expiry(0)

                return redirect("dashboard")

            messages.error(
                request,
                "Only authorized administrators can log in."
            )

        else:

            messages.error(
                request,
                "Invalid username/email or password."
            )

    return render(
        request,
        "accounts/login.html"
    )


# ==========================================
# DASHBOARD
# ==========================================

@login_required(login_url="login")
def dashboard_view(request):

    if not check_admin_access(request):
        return redirect("login")

    total_applicants = Applicant.objects.count()

    submitted_applicants = Applicant.objects.filter(
        application_status="SUBMITTED"
    ).count()

    under_review_applicants = Applicant.objects.filter(
        application_status__in=[
            "UNDER_REVIEW",
            "DOCUMENTS_PENDING"
        ]
    ).count()

    eligible_applicants = Applicant.objects.filter(
        application_status="ELIGIBLE"
    ).count()

    context = {
        "total_applicants": total_applicants,
        "submitted_applicants": submitted_applicants,
        "under_review_applicants": under_review_applicants,
        "eligible_applicants": eligible_applicants,
    }

    return render(
        request,
        "accounts/dashboard.html",
        context
    )


# ==========================================
# LOGOUT
# ==========================================

@login_required(login_url="login")
@require_POST
def logout_view(request):

    logout(request)

    messages.success(
        request,
        "You have been logged out successfully."
    )

    return redirect("login")


# ==========================================
# APPLICANT LIST
# ==========================================

@login_required(login_url="login")
def applicant_list_view(request):

    if not check_admin_access(request):
        return redirect("login")

    applicants = Applicant.objects.all()

    search_query = request.GET.get(
        "search", ""
    ).strip()

    status_filter = request.GET.get(
        "status", ""
    ).strip()

    if search_query:

        applicants = applicants.filter(
            Q(application_id__icontains=search_query)
            | Q(full_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(mobile_number__icontains=search_query)
        )

    if status_filter:

        applicants = applicants.filter(
            application_status=status_filter
        )

    context = {
        "applicants": applicants,
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": Applicant.STATUS_CHOICES,
    }

    return render(
        request,
        "accounts/applicant_list.html",
        context
    )


# ==========================================
# ADD APPLICANT
# ==========================================

@login_required(login_url="login")
def applicant_create_view(request):

    if not check_admin_access(request):
        return redirect("login")

    if request.method == "POST":

        form = ApplicantForm(request.POST)

        if form.is_valid():

            applicant = form.save()

            messages.success(
                request,
                "Applicant added successfully."
            )

            return redirect(
                "applicant_detail",
                pk=applicant.pk
            )

    else:

        form = ApplicantForm()

    return render(
        request,
        "accounts/applicant_form.html",
        {
            "form": form,
            "page_title": "Add Applicant"
        }
    )


# ==========================================
# APPLICANT DETAILS
# ==========================================

@login_required(login_url="login")
def applicant_detail_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(
        Applicant,
        pk=pk
    )

    return render(
        request,
        "accounts/applicant_detail.html",
        {"applicant": applicant}
    )


# ==========================================
# CROSS-DOCUMENT VERIFICATION
# ==========================================

@login_required(login_url="login")
def cross_document_verification_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(
        Applicant,
        pk=pk
    )

    if request.method == "POST":

        report = verify_applicant_documents(
            applicant,
            verified_by=request.user
        )

        messages.success(
            request,
            "Cross-document verification report saved successfully."
        )

        return redirect(
            "cross_document_verification",
            pk=applicant.pk
        )

    preview = preview_applicant_documents(applicant)

    reports = ApplicantCrossDocumentVerification.objects.filter(
        applicant=applicant
    ).order_by("-created_at")

    context = {
        "applicant": applicant,
        "preview": preview,
        "reports": reports,
    }

    return render(
        request,
        "accounts/cross_document_verification.html",
        context
    )
# ==========================================
# CROSS-DOCUMENT VERIFICATION REPORT DETAIL
# ==========================================


@login_required(login_url="login")
def cross_document_verification_report_detail_view(request, pk, report_id):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(
        Applicant,
        pk=pk
    )

    report = get_object_or_404(
        ApplicantCrossDocumentVerification,
        pk=report_id,
        applicant=applicant
    )

    # Retrieve document IDs saved in the historical report
    document_ids = report.documents_considered or []

    # Fetch only documents belonging to this applicant
    documents = ApplicantDocument.objects.filter(
        applicant=applicant,
        id__in=document_ids
    )

    documents_by_id = {
        document.id: document
        for document in documents
    }

    # Preserve the original order of document IDs
    documents_considered_details = []

    for document_id in document_ids:

        document = documents_by_id.get(document_id)

        if document:

            documents_considered_details.append({
                "id": document.id,
                "name": document.get_document_type_display(),
                "file_name": (
                    document.document_file.name.split("/")[-1]
                    if document.document_file
                    else "File name unavailable"
                ),
            })

        else:

            documents_considered_details.append({
                "id": document_id,
                "name": "Document no longer available",
                "file_name": "Not available",
            })

    context = {
        "applicant": applicant,
        "report": report,
        "documents_considered_details": documents_considered_details,
    }

    return render(
        request,
        "accounts/cross_document_verification_report_detail.html",
        context
    )


# ==========================================
# EDIT APPLICANT
# ==========================================

@login_required(login_url="login")
def applicant_edit_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(
        Applicant,
        pk=pk
    )

    if request.method == "POST":

        form = ApplicantForm(
            request.POST,
            instance=applicant
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Applicant details updated successfully."
            )

            return redirect(
                "applicant_detail",
                pk=applicant.pk
            )

    else:

        form = ApplicantForm(
            instance=applicant
        )

    return render(
        request,
        "accounts/applicant_form.html",
        {
            "form": form,
            "applicant": applicant,
            "page_title": "Edit Applicant"
        }
    )


# ==========================================
# DELETE APPLICANT
# ==========================================

@login_required(login_url="login")
@require_POST
def applicant_delete_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(
        Applicant,
        pk=pk
    )

    application_id = applicant.application_id

    applicant.delete()

    messages.success(
        request,
        f"Applicant {application_id} deleted successfully."
    )

    return redirect("applicant_list")


# ==========================================
# DOCUMENT VERIFICATION PAGE
# ==========================================


@login_required(login_url="login")
def document_verification_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(
        Applicant,
        pk=pk
    )

    documents = ApplicantDocument.objects.filter(
        applicant=applicant
    ).order_by("document_type")

    uploaded_types = set(
        documents.values_list("document_type", flat=True)
    )

    verified_types = set(
        documents.filter(
            verification_status="VERIFIED"
        ).values_list("document_type", flat=True)
    )

    missing_documents = []
    pending_required_documents = []
    manual_review_required_documents = []
    rejected_required_documents = []

    for document_code, document_name in REQUIRED_DOCUMENTS:

        if document_code not in uploaded_types:
            missing_documents.append(document_name)
            continue

        if document_code in verified_types:
            continue

        document_statuses = list(
            documents.filter(
                document_type=document_code
            ).values_list(
                "verification_status",
                flat=True
            )
        )

        if "MANUAL_REVIEW" in document_statuses:
            manual_review_required_documents.append(document_name)

        elif any(
            status in ["PENDING", "RESUBMISSION_REQUIRED"]
            for status in document_statuses
        ):
            pending_required_documents.append(document_name)

        else:
            rejected_required_documents.append(document_name)

    total_documents = documents.count()

    verified_documents = documents.filter(
        verification_status="VERIFIED"
    ).count()

    pending_documents = documents.filter(
        verification_status="PENDING"
    ).count()

    manual_review_documents = documents.filter(
        verification_status="MANUAL_REVIEW"
    ).count()

    rejected_documents = documents.filter(
        verification_status__in=[
            "REJECTED",
            "RESUBMISSION_REQUIRED"
        ]
    ).count()

    all_mandatory_uploaded = len(missing_documents) == 0

    all_mandatory_verified = (
        len(missing_documents) == 0
        and len(pending_required_documents) == 0
        and len(manual_review_required_documents) == 0
        and len(rejected_required_documents) == 0
    )

    context = {
        "applicant": applicant,
        "documents": documents,

        "total_documents": total_documents,
        "verified_documents": verified_documents,
        "pending_documents": pending_documents,
        "manual_review_documents": manual_review_documents,
        "rejected_documents": rejected_documents,

        "required_documents": REQUIRED_DOCUMENTS,
        "mandatory_document_codes": [
            code for code, name in REQUIRED_DOCUMENTS
        ],

        "missing_documents": missing_documents,
        "pending_required_documents": pending_required_documents,
        "manual_review_required_documents": manual_review_required_documents,
        "rejected_required_documents": rejected_required_documents,

        "all_mandatory_uploaded": all_mandatory_uploaded,
        "all_mandatory_verified": all_mandatory_verified,
    }

    return render(
        request,
        "accounts/document_verification.html",
        context
    )

# ==========================================
# UPDATE DOCUMENT VERIFICATION
# ==========================================

@login_required(login_url="login")
@require_POST
def update_document_verification_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    document = get_object_or_404(
        ApplicantDocument,
        pk=pk
    )

    status = request.POST.get(
        "verification_status"
    )

    remarks = request.POST.get(
        "remarks", ""
    ).strip()

    allowed_statuses = [
        "PENDING",
        "MANUAL_REVIEW",
        "VERIFIED",
        "REJECTED",
        "RESUBMISSION_REQUIRED",
    ]

    if status not in allowed_statuses:

        messages.error(
            request,
            "Invalid verification status."
        )

        return redirect(
            "document_verification",
            pk=document.applicant.pk
        )

    document.verification_status = status
    document.remarks = remarks

    if status == "VERIFIED":

        document.verified_at = timezone.now()
        document.verified_by = request.user

    else:

        document.verified_at = None
        document.verified_by = None

    document.save()

    messages.success(
        request,
        "Document verification status updated successfully."
    )

    return redirect(
        "document_verification",
        pk=document.applicant.pk
    )


# ==========================================
# APPLICANT DOCUMENT UPLOAD FORM
# ==========================================

class ApplicantDocumentForm(forms.ModelForm):

    class Meta:
        model = ApplicantDocument
        fields = [
            "document_type",
            "document_file",
        ]

    def clean_document_file(self):

        uploaded_file = self.cleaned_data.get("document_file")

        if uploaded_file:

            allowed_extensions = [
                ".pdf",
                ".jpg",
                ".jpeg",
                ".png",
            ]

            file_name = uploaded_file.name.lower()

            if not any(
                file_name.endswith(ext)
                for ext in allowed_extensions
            ):
                raise forms.ValidationError(
                    "Only PDF, JPG, JPEG and PNG files are allowed."
                )

            if uploaded_file.size > 10 * 1024 * 1024:
                raise forms.ValidationError(
                    "File size must not exceed 10 MB."
                )

        return uploaded_file

# ==========================================
# UPLOAD APPLICANT DOCUMENT
# ==========================================


@login_required(login_url="login")
def applicant_document_upload_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(Applicant, pk=pk)

    if request.method == "POST":

        form = ApplicantDocumentForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            document = form.save(commit=False)
            document.applicant = applicant

            mandatory_codes = [
                code for code, name in REQUIRED_DOCUMENTS
            ]

            document.is_mandatory = (
                document.document_type in mandatory_codes
            )

            document.verification_status = "PENDING"
            document.ocr_status = "PENDING"
            document.save()

            try:
                # Step 1: OCR processing
                ocr_result = process_applicant_document(document)

                # Refresh document with latest OCR data
                document.refresh_from_db()

                if ocr_result.get("success"):

                    # Step 2: Automatic internal verification
                    verification_result = (
                        verify_document_automatically(document)
                    )

                    status = verification_result.get("status")

                    if status == "VERIFIED":
                        messages.success(
                            request,
                            "OCR completed. Automatic internal "
                            "document checks passed. Official authenticity "
                            "has not been established."
                        )

                    elif status == "RESUBMISSION_REQUIRED":
                        messages.warning(
                            request,
                            "Document type mismatch. Please upload "
                            "the correct document."
                        )

                    else:
                        messages.warning(
                            request,
                            "OCR completed. Document requires manual review: "
                            + verification_result.get("message", "")
                        )

                else:
                    messages.warning(
                        request,
                        "Document uploaded, but OCR processing failed. "
                        "Automatic verification was not performed."
                    )

            except Exception as error:
                messages.warning(
                    request,
                    "Document uploaded, but processing could not be "
                    "completed: " + str(error)
                )

            return redirect(
                "document_verification",
                pk=applicant.pk
            )

    else:
        form = ApplicantDocumentForm()

    return render(
        request,
        "accounts/document_upload.html",
        {
            "form": form,
            "applicant": applicant,
        }
    )

# ==========================================
# PHD ELIGIBILITY EVALUATION
# ==========================================

@login_required(login_url="login")
def eligibility_evaluation_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(
        Applicant,
        pk=pk
    )

    # ======================================
    # STEP 1: CHECK MANDATORY DOCUMENTS
    # ======================================

    document_checks = []
    missing_documents = []
    pending_documents = []
    manual_review_documents = []
    rejected_documents = []

    for document_code, document_name in REQUIRED_DOCUMENTS:

        documents = ApplicantDocument.objects.filter(
            applicant=applicant,
            document_type=document_code
        )

        if not documents.exists():

            missing_documents.append(document_name)

            document_checks.append({
                "name": document_name,
                "status": "PENDING",
                "message": "Mandatory document has not been uploaded."
            })

            continue

        # At least one verified upload satisfies this document type.
        if documents.filter(verification_status="VERIFIED").exists():

            document_checks.append({
                "name": document_name,
                "status": "PASS",
                "message": "Document uploaded and verified successfully."
            })

            continue

        statuses = list(
            documents.values_list(
                "verification_status",
                flat=True
            )
        )

        if "REJECTED" in statuses:

            rejected_documents.append(document_name)

            document_checks.append({
                "name": document_name,
                "status": "FAIL",
                "message": "Document rejected. Resubmission is required."
            })

        elif "RESUBMISSION_REQUIRED" in statuses:

            rejected_documents.append(document_name)

            document_checks.append({
                "name": document_name,
                "status": "PENDING",
                "message": "Document resubmission is required."
            })

        elif "MANUAL_REVIEW" in statuses:

            manual_review_documents.append(document_name)

            document_checks.append({
                "name": document_name,
                "status": "MANUAL_REVIEW",
                "message": "Document requires manual review by an administrator."
            })

        else:

            pending_documents.append(document_name)

            document_checks.append({
                "name": document_name,
                "status": "PENDING",
                "message": "Document verification is pending."
            })

    # ======================================
    # STEP 2: DOCUMENT VERIFICATION GATE
    # ======================================

    documents_ready = (
        not missing_documents
        and not pending_documents
        and not manual_review_documents
        and not rejected_documents
    )

    # ======================================
    # STEP 3: RUN ELIGIBILITY ENGINE ONLY
    # WHEN ALL MANDATORY DOCUMENTS PASS
    # ======================================

    if documents_ready:

        result = evaluate_phd_eligibility(applicant)
        result["checks"] = document_checks + result["checks"]

    else:

        reasons = []

        for name in missing_documents:
            reasons.append(
                f"Mandatory document missing: {name}."
            )

        for name in pending_documents:
            reasons.append(
                f"Document verification pending: {name}."
            )

        for name in manual_review_documents:
            reasons.append(
                f"Document requires administrator manual review: {name}."
            )

        for name in rejected_documents:
            reasons.append(
                f"Document rejected or resubmission required: {name}."
            )

        evaluation_status = (
            "MANUAL_REVIEW"
            if manual_review_documents
            and not missing_documents
            and not pending_documents
            and not rejected_documents
            else "PENDING"
        )

        result = {
            "status": evaluation_status,
            "required_percentage": None,
            "obtained_percentage": None,
            "checks": document_checks,
            "reasons": reasons,
            "is_eligible": False,
        }

    # ======================================
    # STEP 4: PREPARE DATABASE VALUES
    # ======================================

    required_percentage = (
        Decimal(str(result["required_percentage"]))
        if result["required_percentage"] is not None
        else None
    )

    obtained_percentage = (
        Decimal(str(result["obtained_percentage"]))
        if result["obtained_percentage"] is not None
        else None
    )

    # ======================================
    # STEP 5: SAVE EVERY EVALUATION
    # ======================================

    EligibilityEvaluation.objects.create(
        applicant=applicant,
        status=result["status"],
        required_percentage=required_percentage,
        obtained_percentage=obtained_percentage,
        checks=result["checks"],
        reasons=result["reasons"],
        evaluated_by=request.user
    )

    # ======================================
    # STEP 6: PREPARE TEMPLATE CONTEXT
    # ======================================

    context = {
        "applicant": applicant,
        "result": result,
        "checks": result["checks"],
        "reasons": result["reasons"],
        "documents_ready": documents_ready,
        "missing_documents": missing_documents,
        "pending_documents": pending_documents,
        "manual_review_documents": manual_review_documents,
        "rejected_documents": rejected_documents,
    }

    return render(
        request,
        "accounts/eligibility_result.html",
        context
    )

# ==========================================
# ELIGIBILITY EVALUATION HISTORY
# ==========================================


# ==========================================
# ELIGIBILITY EVALUATION HISTORY
# ==========================================

@login_required(login_url="login")
def eligibility_history_view(request, pk):

    if not check_admin_access(request):
        return redirect("login")

    applicant = get_object_or_404(
        Applicant,
        pk=pk
    )

    evaluations = (
        EligibilityEvaluation.objects
        .filter(applicant=applicant)
        .select_related("evaluated_by")
        .order_by("-evaluated_at")
    )

    context = {
        "applicant": applicant,
        "evaluations": evaluations,
        "total_evaluations": evaluations.count(),
    }

    return render(
        request,
        "accounts/eligibility_history.html",
        context
    )


# ==========================================
# GLOBAL DOCUMENT VERIFICATION APPLICANT LIST
# ==========================================

@login_required(login_url="login")
def all_document_verification_view(request):

    if not check_admin_access(request):
        return redirect("login")

    applicants = Applicant.objects.all().order_by("-id")

    search_query = request.GET.get("search", "").strip()

    if search_query:
        applicants = applicants.filter(
            Q(application_id__icontains=search_query)
            | Q(full_name__icontains=search_query)
            | Q(email__icontains=search_query)
        )

    applicant_data = []

    for applicant in applicants:
        documents = ApplicantDocument.objects.filter(
            applicant=applicant
        )

        applicant_data.append({
            "applicant": applicant,
            "total_documents": documents.count(),
            "verified_documents": documents.filter(
                verification_status="VERIFIED"
            ).count(),
            "pending_documents": documents.filter(
                verification_status="PENDING"
            ).count(),
            "manual_review_documents": documents.filter(
                verification_status="MANUAL_REVIEW"
            ).count(),
            "rejected_documents": documents.filter(
                verification_status__in=[
                    "REJECTED",
                    "RESUBMISSION_REQUIRED"
                ]
            ).count(),
        })

    context = {
        "applicant_data": applicant_data,
        "search_query": search_query,
    }

    return render(
        request,
        "accounts/all_document_verification.html",
        context
    )

