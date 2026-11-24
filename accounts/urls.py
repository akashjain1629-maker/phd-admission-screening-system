
from django.urls import path
from . import views


urlpatterns = [

    # Login, Dashboard and Logout
    path("", views.login_view, name="login"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("logout/", views.logout_view, name="logout"),

    # Global Document Verification
    path(
        "documents/",
        views.all_document_verification_view,
        name="all_document_verification"
    ),

    # PhD Eligibility Evaluation
    path(
        "applicants/<int:pk>/eligibility/",
        views.eligibility_evaluation_view,
        name="eligibility_evaluation"
    ),

    # Eligibility Evaluation History
    path(
        "applicants/<int:pk>/eligibility/history/",
        views.eligibility_history_view,
        name="eligibility_history"
    ),

    # Applicant Management
    path(
        "applicants/",
        views.applicant_list_view,
        name="applicant_list"
    ),

    path(
        "applicants/add/",
        views.applicant_create_view,
        name="applicant_create"
    ),

    path(
        "applicants/<int:pk>/",
        views.applicant_detail_view,
        name="applicant_detail"
    ),

    path(
        "applicants/<int:pk>/edit/",
        views.applicant_edit_view,
        name="applicant_edit"
    ),

    path(
        "applicants/<int:pk>/delete/",
        views.applicant_delete_view,
        name="applicant_delete"
    ),

    # Individual Applicant Document Verification
    path(
        "applicants/<int:pk>/documents/",
        views.document_verification_view,
        name="document_verification"
    ),

    # Update Document Verification Status
    path(
        "documents/<int:pk>/update/",
        views.update_document_verification_view,
        name="update_document_verification"
    ),

    # Document Upload
    path(
        "applicants/<int:pk>/documents/upload/",
        views.applicant_document_upload_view,
        name="applicant_document_upload"
    ),

    # Cross-Document Verification Report Detail
    path(
        "applicants/<int:pk>/cross-document-verification/reports/<int:report_id>/",
        views.cross_document_verification_report_detail_view,
        name="cross_document_verification_report_detail"
    ),

    # Cross-Document Verification
    path(
        "applicants/<int:pk>/cross-document-verification/",
        views.cross_document_verification_view,
        name="cross_document_verification"
    ),
]
