# attendance/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Public views
    path('', views.home, name='home'),
    path('register/student/', views.register_student, name='register_student'),
    path('register/admin/', views.register_admin, name='register_admin'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Student views
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/get-qr/', views.get_qr_code, name='get_qr_code'),
    path('student/history/', views.attendance_history, name='attendance_history'),
    
    # Admin views
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/session/create/', views.create_session, name='create_session'),
    path('admin/session/<int:session_id>/scan/', views.scan_qr, name='scan_qr'),
    path('admin/session/<int:session_id>/attendance/', views.view_session_attendance, name='view_attendance'),
    path('admin/session/<int:session_id>/export/csv/', views.export_attendance_csv, name='export_csv'),
    path('admin/session/<int:session_id>/export/excel/', views.export_attendance_excel, name='export_excel'),
    path('admin/students/', views.manage_students, name='manage_students'),
    
    # API endpoints
    path('api/session/<int:session_id>/scan/', views.api_scan_qr, name='api_scan_qr'),
]

